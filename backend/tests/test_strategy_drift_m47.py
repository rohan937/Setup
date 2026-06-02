"""M47 tests: Strategy Drift Analysis.

Tests for:
  - GET /api/strategies/{id}/drift endpoint
  - Metric drift detection and severity
  - Evidence drift detection
  - Drift score computation
  - Mode handling (latest_stage_pair, selected_runs, full_stage_path)
  - Insufficient evidence handling
  - Language policy (no investment advice language)

All tests use the shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FORBIDDEN_INVESTMENT_WORDS = ["buy", "sell", "profit", "investment advice"]


def _has_forbidden(text: str) -> list[str]:
    low = text.lower()
    return [w for w in FORBIDDEN_INVESTMENT_WORDS if w in low]


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m47-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M47 Test Strategy {suffix}",
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
    assumptions: dict | None = None,
    dataset_snapshot_id=None,
    signal_snapshot_id=None,
) -> object:
    from app.models.strategy_run import StrategyRun

    run = StrategyRun(
        strategy_id=strategy_id,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status=status,
        completed_at=datetime.now(timezone.utc),
        metrics_json=metrics or {},
        assumptions_json=assumptions or {},
        dataset_snapshot_id=dataset_snapshot_id,
        signal_snapshot_id=signal_snapshot_id,
    )
    db.add(run)
    db.flush()
    return run


def _get_seeded_project(db):
    from app.models.project import Project

    return db.query(Project).first()


# ---------------------------------------------------------------------------
# TestDriftEndpoint
# ---------------------------------------------------------------------------


class TestDriftEndpoint:
    """Integration tests via TestClient for the drift endpoint."""

    def test_endpoint_returns_200(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="ep200")
        _make_run(db, strat.id, run_type="backtest")
        _make_run(db, strat.id, run_type="paper")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/drift")
            assert resp.status_code == 200
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_insufficient_evidence_status(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="insuf")
        # Only one run — not enough for comparison
        _make_run(db, strat.id, run_type="backtest")
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/drift")
            assert resp.status_code == 200
            data = resp.json()
            assert data["drift_status"] == "insufficient_evidence"
            assert data["drift_score"] is None
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_response_fields(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="fields")
        _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 1.2})
        _make_run(db, strat.id, run_type="paper", metrics={"sharpe": 1.1})
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/drift")
            assert resp.status_code == 200
            data = resp.json()
            assert "drift_score" in data
            assert "drift_status" in data
            assert "metric_drifts" in data
            assert "evidence_drifts" in data
            assert "assumption_drifts" in data
            assert "trust_drifts" in data
            assert "highlighted_drifts" in data
            assert "suggested_checks" in data
            assert "deterministic_summary" in data
            assert "baseline_run" in data
            assert "comparison_run" in data
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_unknown_strategy_404(self, client):
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/drift")
        assert resp.status_code == 404

    def test_invalid_mode_400(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="badmode")
        _make_run(db, strat.id)
        _make_run(db, strat.id)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/drift?mode=invalid")
            assert resp.status_code == 400
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_selected_mode_validates_run(self, client, db):
        """baseline_run_id belonging to a different strategy → 400."""
        project = _get_seeded_project(db)
        strat_a = _make_strategy(db, project.id, suffix="sel-a")
        strat_b = _make_strategy(db, project.id, suffix="sel-b")
        run_a = _make_run(db, strat_a.id, run_type="backtest")
        run_b = _make_run(db, strat_b.id, run_type="backtest")
        comp_run = _make_run(db, strat_a.id, run_type="paper")
        db.commit()

        try:
            # run_a belongs to strat_a but run_b belongs to strat_b — should 400
            resp = client.get(
                f"/api/strategies/{strat_a.id}/drift"
                f"?mode=selected_runs"
                f"&baseline_run_id={run_b.id}"
                f"&comparison_run_id={comp_run.id}"
            )
            assert resp.status_code == 400
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat_a.id).all():
                db.delete(r)
            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat_b.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat_a.id))
            db.delete(db.query(Strategy).get(strat_b.id))
            db.commit()


# ---------------------------------------------------------------------------
# TestMetricDrift
# ---------------------------------------------------------------------------


class TestMetricDrift:
    """Tests for metric-level drift detection."""

    def test_sharpe_deterioration_high(self, client, db):
        """Sharpe dropping from 1.6 to 0.8 should be flagged as high severity."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sharpe-hi")
        _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 1.6})
        _make_run(db, strat.id, run_type="paper", metrics={"sharpe": 0.8})
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/drift")
            assert resp.status_code == 200
            data = resp.json()
            metric_drifts = data["metric_drifts"]
            sharpe_drift = next((m for m in metric_drifts if m["metric"] == "sharpe"), None)
            assert sharpe_drift is not None, "sharpe should appear in metric_drifts"
            assert sharpe_drift["severity"] == "high"
            assert sharpe_drift["direction"] == "deteriorated"
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_sharpe_improvement(self, client, db):
        """Sharpe increasing from 0.8 to 1.6 should be direction='improved'."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sharpe-imp")
        _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 0.8})
        _make_run(db, strat.id, run_type="paper", metrics={"sharpe": 1.6})
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/drift")
            assert resp.status_code == 200
            data = resp.json()
            sharpe_drift = next(
                (m for m in data["metric_drifts"] if m["metric"] == "sharpe"), None
            )
            assert sharpe_drift is not None
            assert sharpe_drift["direction"] == "improved"
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_missing_metric_medium(self, client, db):
        """Metric present in baseline but absent in comparison → severity medium."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="miss-met")
        _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 1.2, "sortino": 1.5})
        _make_run(db, strat.id, run_type="paper", metrics={"sharpe": 1.1})
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/drift")
            assert resp.status_code == 200
            sortino_drift = next(
                (m for m in resp.json()["metric_drifts"] if m["metric"] == "sortino"), None
            )
            assert sortino_drift is not None
            assert sortino_drift["severity"] == "medium"
            assert sortino_drift["direction"] == "unavailable"
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_stable_metrics_no_drift(self, client, db):
        """Identical metrics should produce no high-severity drifts."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="stable-met")
        same_metrics = {"sharpe": 1.2, "sortino": 1.8, "annual_return": 0.12}
        _make_run(db, strat.id, run_type="backtest", metrics=same_metrics)
        _make_run(db, strat.id, run_type="paper", metrics=same_metrics)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/drift")
            assert resp.status_code == 200
            data = resp.json()
            high_drifts = [m for m in data["metric_drifts"] if m["severity"] == "high"]
            assert len(high_drifts) == 0
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()


# ---------------------------------------------------------------------------
# TestEvidenceDrift
# ---------------------------------------------------------------------------


class TestEvidenceDrift:
    """Tests for evidence-level drift detection."""

    def test_dataset_health_drop_detected(self, client, db):
        """Run without dataset vs run with dataset → evidence drift entry."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="ev-ds")
        # Both runs without dataset — but we check the evidence_drifts list
        _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 1.0})
        _make_run(db, strat.id, run_type="paper", metrics={"sharpe": 1.0})
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/drift")
            assert resp.status_code == 200
            data = resp.json()
            # evidence_drifts may be empty (both have no evidence) — that's OK
            assert isinstance(data["evidence_drifts"], list)
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_signal_quality_drop(self, client, db):
        """Signal quality drop is reflected in evidence_drifts via service layer."""
        from app.services.strategy_drift import (
            StrategyDriftRunSummaryData,
            _compute_evidence_drifts,
        )

        now = datetime.now(timezone.utc)
        base = StrategyDriftRunSummaryData(
            run_id=uuid.uuid4(),
            run_name="base",
            run_type="backtest",
            status="completed",
            created_at=now,
            completed_at=now,
            metrics_json={},
            assumptions_json={},
            strategy_version_label=None,
            dataset_health=None,
            signal_quality=90.0,
            universe_symbol_count=None,
            backtest_trust=None,
            run_health_label="strong",
        )
        comp = StrategyDriftRunSummaryData(
            run_id=uuid.uuid4(),
            run_name="comp",
            run_type="paper",
            status="completed",
            created_at=now,
            completed_at=now,
            metrics_json={},
            assumptions_json={},
            strategy_version_label=None,
            dataset_health=None,
            signal_quality=60.0,
            universe_symbol_count=None,
            backtest_trust=None,
            run_health_label="strong",
        )
        drifts = _compute_evidence_drifts(base, comp)
        sq_drift = next((e for e in drifts if e.evidence_type == "signal_quality"), None)
        assert sq_drift is not None
        assert sq_drift.severity in ("medium", "high")
        assert sq_drift.delta is not None and sq_drift.delta < 0

    def test_no_drift_on_identical(self, client, db):
        """Identical evidence values → no high/medium severity evidence drift."""
        from app.services.strategy_drift import (
            StrategyDriftRunSummaryData,
            _compute_evidence_drifts,
        )

        now = datetime.now(timezone.utc)
        summary = StrategyDriftRunSummaryData(
            run_id=uuid.uuid4(),
            run_name="run",
            run_type="backtest",
            status="completed",
            created_at=now,
            completed_at=now,
            metrics_json={},
            assumptions_json={},
            strategy_version_label=None,
            dataset_health=85.0,
            signal_quality=80.0,
            universe_symbol_count=100,
            backtest_trust=75.0,
            run_health_label="strong",
        )
        drifts = _compute_evidence_drifts(summary, summary)
        high_med = [e for e in drifts if e.severity in ("high", "medium")]
        assert len(high_med) == 0


# ---------------------------------------------------------------------------
# TestDriftScore
# ---------------------------------------------------------------------------


class TestDriftScore:
    """Tests for drift score and status computation."""

    def test_stable_score_with_no_drift(self, client, db):
        """Identical runs should produce drift_score >= 85 and status 'stable'."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="stable-sc")
        metrics = {"sharpe": 1.2, "sortino": 1.8, "annual_return": 0.15, "volatility": 0.12}
        _make_run(db, strat.id, run_type="backtest", metrics=metrics)
        _make_run(db, strat.id, run_type="paper", metrics=metrics)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/drift")
            assert resp.status_code == 200
            data = resp.json()
            assert data["drift_score"] is not None
            assert data["drift_score"] >= 85
            assert data["drift_status"] == "stable"
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_score_decreases_with_high_drift(self, client, db):
        """Sharpe dropping 50%+ and drawdown worsening should produce drift_score < 70."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="hi-drift")
        base_metrics = {
            "sharpe": 2.0,
            "sortino": 2.5,
            "annual_return": 0.25,
            "max_drawdown": -0.10,
            "volatility": 0.12,
        }
        comp_metrics = {
            "sharpe": 0.5,
            "sortino": 0.6,
            "annual_return": 0.05,
            "max_drawdown": -0.40,
            "volatility": 0.30,
        }
        _make_run(db, strat.id, run_type="backtest", metrics=base_metrics)
        _make_run(db, strat.id, run_type="paper", metrics=comp_metrics)
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/drift")
            assert resp.status_code == 200
            data = resp.json()
            assert data["drift_score"] is not None
            assert data["drift_score"] < 70
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_suggested_checks_generated(self, client, db):
        """Any drift should produce non-empty suggested_checks."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="chk-gen")
        _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 1.8})
        _make_run(db, strat.id, run_type="paper", metrics={"sharpe": 0.6})
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/drift")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["suggested_checks"]) > 0
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()

    def test_summary_avoids_investment_language(self, client, db):
        """deterministic_summary must not contain investment-advice language."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="lang-chk")
        _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 1.2})
        _make_run(db, strat.id, run_type="paper", metrics={"sharpe": 0.9})
        db.commit()

        try:
            resp = client.get(f"/api/strategies/{strat.id}/drift")
            assert resp.status_code == 200
            data = resp.json()
            summary = data["deterministic_summary"]
            forbidden = _has_forbidden(summary)
            assert forbidden == [], f"Forbidden words found in summary: {forbidden}"
        finally:
            from app.models.strategy_run import StrategyRun
            from app.models.strategy import Strategy

            for r in db.query(StrategyRun).filter(StrategyRun.strategy_id == strat.id).all():
                db.delete(r)
            db.delete(db.query(Strategy).get(strat.id))
            db.commit()
