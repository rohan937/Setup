"""M88 tests: Shadow Monitor drift engine.

Tests for:
  - ShadowDriftThresholds: per-metric drift computation (unit level)
  - ShadowMonitorService: compare_backtest_to_paper service function
  - ShadowMonitorEndpoints: POST /refresh, GET /report, GET /run-drift
  - ShadowAlertIntegration: paper_backtest_drift alert generation
  - PortfolioShadowFields: shadow_verdict / has_paper_run in portfolio rows

All tests use the shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m88-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M88 Test Strategy {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.flush()
    return strat


def _make_run(
    db,
    strategy_id,
    *,
    run_type: str = "backtest",
    status: str = "completed",
    metrics: dict | None = None,
) -> object:
    from app.models.strategy_run import StrategyRun

    run = StrategyRun(
        strategy_id=strategy_id,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status=status,
        completed_at=datetime.now(timezone.utc),
        metrics_json=metrics or {},
        assumptions_json={},
    )
    db.add(run)
    db.flush()
    return run


def _get_seeded_strategy(db):
    from app.models.strategy import Strategy

    return db.query(Strategy).filter(Strategy.status != "archived").first()


def _get_seeded_project(db):
    from app.models.project import Project

    return db.query(Project).first()


def _get_seeded_org(db):
    from app.models.organization import Organization

    return db.query(Organization).first()


def _cleanup(db, *objs):
    for obj in reversed(objs):
        try:
            db.delete(obj)
        except Exception:
            pass
    db.flush()


# ---------------------------------------------------------------------------
# TestShadowDriftThresholds
# ---------------------------------------------------------------------------


class TestShadowDriftThresholds:
    """Unit-level tests for the per-metric drift computation logic."""

    def test_return_drift_computed_correctly(self):
        """baseline sharpe=2.0, paper sharpe=1.0 → 50% degradation → fail."""
        from app.services.shadow_monitor import _compute_single_metric_drift

        result = _compute_single_metric_drift("sharpe", 2.0, 1.0)
        # degradation = (2.0 - 1.0) / 2.0 = 50% → fail threshold
        assert result.status == "fail"
        assert result.severity == "high"
        assert result.key == "sharpe"
        assert result.baseline_value == 2.0
        assert result.comparison_value == 1.0

    def test_volatility_drift_computed_correctly(self):
        """baseline vol=0.14, paper vol=0.22 → 57% increase → fail (> 50% threshold)."""
        from app.services.shadow_monitor import _compute_single_metric_drift

        result = _compute_single_metric_drift("volatility", 0.14, 0.22)
        # increase = (0.22 - 0.14) / 0.14 = 0.571 → >= 0.50 → fail
        assert result.status == "fail"
        assert result.key == "volatility"

    def test_turnover_drift_computed_correctly(self):
        """baseline turnover=0.35, paper turnover=0.72 → ~105% increase → fail."""
        from app.services.shadow_monitor import _compute_single_metric_drift

        result = _compute_single_metric_drift("turnover", 0.35, 0.72)
        # increase = (0.72 - 0.35) / 0.35 ≈ 1.057 → >= 1.0 → fail
        assert result.status == "fail"
        assert result.key == "turnover"

    def test_drawdown_drift_computed_correctly(self):
        """baseline=-0.10, paper=-0.22 → 12pp worse → fail (> 10pp threshold)."""
        from app.services.shadow_monitor import _compute_single_metric_drift

        result = _compute_single_metric_drift("max_drawdown", -0.10, -0.22)
        # pp_worse = -0.10 - (-0.22) = 0.12 >= 0.10 → fail
        assert result.status == "fail"
        assert result.key == "max_drawdown"
        assert result.baseline_value == -0.10
        assert result.comparison_value == -0.22

    def test_trade_count_drift_computed_correctly(self):
        """baseline=450, paper=950 → ~111% increase → fail."""
        from app.services.shadow_monitor import _compute_single_metric_drift

        result = _compute_single_metric_drift("trade_count", 450, 950)
        # increase = (950 - 450) / 450 ≈ 1.11 → >= 1.0 → fail
        assert result.status == "fail"
        assert result.key == "trade_count"

    def test_missing_metrics_handled(self):
        """One metric missing in comparison → status='missing', still returns cleanly."""
        from app.services.shadow_monitor import _compute_single_metric_drift

        result = _compute_single_metric_drift("sharpe", 1.5, None)
        assert result.status == "missing"
        assert result.severity == "info"
        assert result.baseline_value == 1.5
        assert result.comparison_value is None
        assert result.absolute_delta is None

    def test_all_metrics_missing(self):
        """Both baseline and comparison None → status='missing'."""
        from app.services.shadow_monitor import _compute_single_metric_drift

        result = _compute_single_metric_drift("sharpe", None, None)
        assert result.status == "missing"
        assert result.baseline_value is None
        assert result.comparison_value is None

    def test_missing_metrics_insufficient_data_verdict(self):
        """If all metrics are missing, compute_shadow_drift_score yields insufficient_data."""
        from app.services.shadow_monitor import (
            _compute_single_metric_drift,
            compute_shadow_drift_score,
            KEY_METRICS,
        )

        metrics = [_compute_single_metric_drift(k, None, None) for k in KEY_METRICS]
        _, _, verdict = compute_shadow_drift_score(metrics)
        assert verdict == "insufficient_data"


# ---------------------------------------------------------------------------
# TestShadowMonitorService
# ---------------------------------------------------------------------------


class TestShadowMonitorService:
    """Service-level tests for compare_backtest_to_paper."""

    def test_no_paper_run_returns_insufficient_data(self, db):
        """Only backtest run present → verdict='insufficient_data' (not an exception)."""
        from app.services.shadow_monitor import compare_backtest_to_paper

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-nopaper")
        bt = _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 1.5})
        try:
            result = compare_backtest_to_paper(strat.id, db)
            assert result.verdict == "insufficient_data"
            assert result.drift_score is None
            assert result.comparison_run_id is None
        finally:
            _cleanup(db, bt, strat)

    def test_no_baseline_returns_insufficient_data(self, db):
        """Only paper run present → verdict='insufficient_data' (not an exception)."""
        from app.services.shadow_monitor import compare_backtest_to_paper

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-nobaseline")
        paper = _make_run(db, strat.id, run_type="paper", metrics={"sharpe": 1.0})
        try:
            result = compare_backtest_to_paper(strat.id, db)
            assert result.verdict == "insufficient_data"
            assert result.drift_score is None
            assert result.baseline_run_id is None
        finally:
            _cleanup(db, paper, strat)

    def test_stable_run_returns_stable(self, db):
        """Identical metrics in backtest and paper → verdict='stable'."""
        from app.services.shadow_monitor import compare_backtest_to_paper

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-stable")
        metrics = {
            "sharpe": 1.8,
            "annual_return": 0.20,
            "max_drawdown": -0.08,
            "volatility": 0.12,
            "turnover": 0.30,
            "trade_count": 400,
        }
        bt = _make_run(db, strat.id, run_type="backtest", metrics=metrics)
        paper = _make_run(db, strat.id, run_type="paper", metrics=metrics)
        try:
            result = compare_backtest_to_paper(strat.id, db)
            assert result.verdict in ("stable",)
        finally:
            _cleanup(db, paper, bt, strat)

    def test_high_drift_returns_drifted(self, db):
        """sharpe drops 60%, drawdown worsens 15pp → verdict='drifted'."""
        from app.services.shadow_monitor import compare_backtest_to_paper

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-drifted")
        bt_metrics = {"sharpe": 2.5, "max_drawdown": -0.08}
        paper_metrics = {"sharpe": 1.0, "max_drawdown": -0.23}
        bt = _make_run(db, strat.id, run_type="backtest", metrics=bt_metrics)
        paper = _make_run(db, strat.id, run_type="paper", metrics=paper_metrics)
        try:
            result = compare_backtest_to_paper(strat.id, db)
            assert result.verdict == "drifted"
        finally:
            _cleanup(db, paper, bt, strat)

    def test_drift_score_not_none_when_runs_exist(self, db):
        """Both baseline and paper runs present → drift_score is not None."""
        from app.services.shadow_monitor import compare_backtest_to_paper

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-driftscore")
        bt = _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 1.5})
        paper = _make_run(db, strat.id, run_type="paper", metrics={"sharpe": 1.3})
        try:
            result = compare_backtest_to_paper(strat.id, db)
            assert result.drift_score is not None
            assert 0.0 <= result.drift_score <= 100.0
        finally:
            _cleanup(db, paper, bt, strat)


# ---------------------------------------------------------------------------
# TestShadowMonitorEndpoints
# ---------------------------------------------------------------------------


class TestShadowMonitorEndpoints:
    """Integration tests via TestClient for the M88 shadow monitor endpoints."""

    def test_refresh_endpoint_returns_200(self, client, db):
        """POST /api/strategies/{id}/shadow-monitor/refresh → 200."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.post(f"/api/strategies/{strategy.id}/shadow-monitor/refresh")
        assert resp.status_code == 200

    def test_refresh_returns_correct_verdict(self, client, db):
        """Add backtest + paper run, call refresh → response has verdict field."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="ep-refresh")
        bt = _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 1.8})
        paper = _make_run(db, strat.id, run_type="paper", metrics={"sharpe": 1.7})
        try:
            resp = client.post(f"/api/strategies/{strat.id}/shadow-monitor/refresh")
            assert resp.status_code == 200
            data = resp.json()
            assert "verdict" in data
            assert data["verdict"] in ("stable", "watch", "drifted", "insufficient_data")
        finally:
            _cleanup(db, paper, bt, strat)

    def test_refresh_response_has_required_fields(self, client, db):
        """Refresh response contains all expected fields from ShadowMonitorResponse."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="ep-fields")
        bt = _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 1.5})
        paper = _make_run(db, strat.id, run_type="paper", metrics={"sharpe": 1.4})
        try:
            resp = client.post(f"/api/strategies/{strat.id}/shadow-monitor/refresh")
            assert resp.status_code == 200
            data = resp.json()
            for field in (
                "strategy_id", "strategy_name", "verdict", "drift_score",
                "severity", "metrics", "top_concerns", "suggested_actions",
                "blockers", "missing_metric_keys", "missing_metric_coverage",
                "generated_at", "disclaimer",
            ):
                assert field in data, f"Missing field: {field}"
        finally:
            _cleanup(db, paper, bt, strat)

    def test_report_json_works(self, client, db):
        """GET /api/strategies/{id}/shadow-monitor/report?format=json → 200, has 'content'."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/shadow-monitor/report?format=json"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
        assert isinstance(data["content"], str)
        assert len(data["content"]) > 0

    def test_report_markdown_works(self, client, db):
        """GET /api/strategies/{id}/shadow-monitor/report?format=markdown → 200, content is string."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/shadow-monitor/report?format=markdown"
        )
        assert resp.status_code == 200
        content = resp.text
        assert isinstance(content, str)
        assert len(content) > 0
        # Markdown should contain the header
        assert "Shadow Monitor Report" in content

    def test_report_invalid_format_returns_400(self, client, db):
        """GET report with unsupported format → 400."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/shadow-monitor/report?format=xlsx"
        )
        assert resp.status_code == 400

    def test_report_unknown_strategy_404(self, client):
        """GET report with unknown strategy ID → 404."""
        fake_id = uuid.uuid4()
        resp = client.get(
            f"/api/strategies/{fake_id}/shadow-monitor/report?format=json"
        )
        assert resp.status_code == 404

    def test_run_drift_endpoint_works(self, client, db):
        """GET /api/strategies/{id}/run-drift?baseline_run_id=X&comparison_run_id=Y → 200."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="ep-rundrift")
        bt = _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 1.8})
        paper = _make_run(db, strat.id, run_type="paper", metrics={"sharpe": 1.6})
        try:
            resp = client.get(
                f"/api/strategies/{strat.id}/run-drift"
                f"?baseline_run_id={bt.id}&comparison_run_id={paper.id}"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "verdict" in data
            assert data["baseline_run"]["run_id"] == str(bt.id)
            assert data["comparison_run"]["run_id"] == str(paper.id)
        finally:
            _cleanup(db, paper, bt, strat)

    def test_run_drift_missing_params_returns_400(self, client, db):
        """GET /run-drift without both run IDs → 400."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/run-drift")
        assert resp.status_code == 400

    def test_refresh_unknown_strategy_404(self, client):
        """POST refresh with unknown strategy ID → 404."""
        fake_id = uuid.uuid4()
        resp = client.post(f"/api/strategies/{fake_id}/shadow-monitor/refresh")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestShadowAlertIntegration
# ---------------------------------------------------------------------------


class TestShadowAlertIntegration:
    """Tests for alert generation driven by shadow monitor drift."""

    def test_alert_generated_for_high_drift(self, db):
        """Create strategy with huge drift → generate_alerts → paper_backtest_drift alert present."""
        from app.services.alerts import generate_alerts_for_strategy
        from app.models.alert import Alert

        project = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strat = _make_strategy(db, project.id, suffix="alert-drift")

        # Massive sharpe degradation + drawdown worsening → drifted + critical
        bt_metrics = {
            "sharpe": 3.0,
            "max_drawdown": -0.05,
            "volatility": 0.10,
            "annual_return": 0.40,
            "turnover": 0.20,
            "trade_count": 300,
        }
        paper_metrics = {
            "sharpe": 0.5,           # 83% degradation → fail
            "max_drawdown": -0.25,   # 20pp worse → fail
            "volatility": 0.25,      # 150% increase → fail
            "annual_return": 0.05,   # 87.5% degradation → fail
            "turnover": 0.45,        # 125% increase → fail
            "trade_count": 900,      # 200% increase → fail
        }
        bt = _make_run(db, strat.id, run_type="backtest", metrics=bt_metrics)
        paper = _make_run(db, strat.id, run_type="paper", metrics=paper_metrics)

        try:
            generate_alerts_for_strategy(db, str(strat.id))

            alerts = (
                db.query(Alert)
                .filter(
                    Alert.strategy_id == str(strat.id),
                    Alert.rule_type == "paper_backtest_drift",
                )
                .all()
            )
            assert len(alerts) >= 1, (
                "Expected at least one paper_backtest_drift alert for highly drifted strategy"
            )
        finally:
            # Clean up alerts first, then runs, then strategy
            db.query(Alert).filter(Alert.strategy_id == str(strat.id)).delete()
            db.flush()
            _cleanup(db, paper, bt, strat)

    def test_no_duplicate_alerts(self, db):
        """Call generate_alerts_for_strategy twice → only one paper_backtest_drift alert (idempotent)."""
        from app.services.alerts import generate_alerts_for_strategy
        from app.models.alert import Alert

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="alert-dedup")

        bt_metrics = {
            "sharpe": 3.0,
            "max_drawdown": -0.05,
            "volatility": 0.10,
            "annual_return": 0.40,
            "turnover": 0.20,
            "trade_count": 300,
        }
        paper_metrics = {
            "sharpe": 0.5,
            "max_drawdown": -0.25,
            "volatility": 0.25,
            "annual_return": 0.05,
            "turnover": 0.45,
            "trade_count": 900,
        }
        bt = _make_run(db, strat.id, run_type="backtest", metrics=bt_metrics)
        paper = _make_run(db, strat.id, run_type="paper", metrics=paper_metrics)

        try:
            # Call twice — should be idempotent (reconcile deduplicates)
            generate_alerts_for_strategy(db, str(strat.id))
            generate_alerts_for_strategy(db, str(strat.id))

            alerts = (
                db.query(Alert)
                .filter(
                    Alert.strategy_id == str(strat.id),
                    Alert.rule_type == "paper_backtest_drift",
                    Alert.status == "open",
                )
                .all()
            )
            # Idempotency: at most one open alert per rule_type per strategy
            assert len(alerts) <= 1, (
                f"Expected at most 1 open paper_backtest_drift alert, got {len(alerts)}"
            )
        finally:
            db.query(Alert).filter(Alert.strategy_id == str(strat.id)).delete()
            db.flush()
            _cleanup(db, paper, bt, strat)


# ---------------------------------------------------------------------------
# TestPortfolioShadowFields
# ---------------------------------------------------------------------------


class TestPortfolioShadowFields:
    """Tests that portfolio reliability rows expose shadow_verdict and has_paper_run."""

    def test_portfolio_reliability_includes_shadow_fields(self, db):
        """Call build_portfolio_reliability → rows have shadow_verdict, has_paper_run fields."""
        from app.services.portfolio_reliability import build_portfolio_reliability

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="portfolio-shadow")
        bt = _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 1.5})
        paper = _make_run(db, strat.id, run_type="paper", metrics={"sharpe": 1.4})

        try:
            result = build_portfolio_reliability(db, project_id=project.id)
            # The return dict uses "strategies" key (not "rows")
            rows = result.get("strategies", result.get("rows", []))
            assert len(rows) > 0, "Expected at least one row in portfolio reliability"

            # Find our strategy in the rows
            our_row = next(
                (r for r in rows if str(r.get("strategy_id")) == str(strat.id)),
                None,
            )
            assert our_row is not None, f"Strategy {strat.id} not found in portfolio rows"
            assert "shadow_verdict" in our_row, "Row missing 'shadow_verdict' field"
            assert "has_paper_run" in our_row, "Row missing 'has_paper_run' field"
            # Since we added a paper run, has_paper_run should be True
            assert our_row["has_paper_run"] is True
            # shadow_verdict should be a string (or None), not missing
            # When a paper run is present and metrics exist, verdict should not be None
            assert our_row["shadow_verdict"] is not None
        finally:
            _cleanup(db, paper, bt, strat)

    def test_portfolio_row_no_paper_run_has_paper_run_false(self, db):
        """Strategy with only a backtest run → has_paper_run=False in portfolio row."""
        from app.services.portfolio_reliability import build_portfolio_reliability

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="portfolio-nopaperrun")
        bt = _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 1.5})

        try:
            result = build_portfolio_reliability(db, project_id=project.id)
            # The return dict uses "strategies" key (not "rows")
            rows = result.get("strategies", result.get("rows", []))

            our_row = next(
                (r for r in rows if str(r.get("strategy_id")) == str(strat.id)),
                None,
            )
            assert our_row is not None, f"Strategy {strat.id} not found in portfolio rows"
            assert "has_paper_run" in our_row
            assert our_row["has_paper_run"] is False
        finally:
            _cleanup(db, bt, strat)
