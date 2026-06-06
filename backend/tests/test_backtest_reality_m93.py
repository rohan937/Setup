"""M93 tests: Backtest Reality Score engine.

Tests for:
  - TestBacktestRealityService: compute_backtest_reality_check service function
  - TestBacktestRealityEndpoints: GET /backtest-reality, POST /refresh, GET /report
  - TestBacktestRealityAlerts: backtest_reality_weak alert generation
  - TestPortfolioRealityFields: backtest_reality_score in portfolio rows

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

    slug = f"m93-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M93 Test Strategy {suffix}",
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


def _cleanup(db, *objs):
    for obj in reversed(objs):
        try:
            db.delete(obj)
        except Exception:
            pass
    db.flush()


# ---------------------------------------------------------------------------
# TestBacktestRealityService
# ---------------------------------------------------------------------------


class TestBacktestRealityService:
    """Service-level tests for compute_backtest_reality_check."""

    def test_no_backtest_run_returns_insufficient_data(self, db):
        """Strategy with no runs or only paper runs -> verdict=='insufficient_data'."""
        from app.services.backtest_reality_score import compute_backtest_reality_check

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-noruns")
        # Add only a paper run (not a backtest)
        paper = _make_run(db, strat.id, run_type="paper")
        try:
            result = compute_backtest_reality_check(strat.id, db)
            assert result.verdict == "insufficient_data", (
                f"Expected insufficient_data, got {result.verdict}"
            )
        finally:
            _cleanup(db, paper, strat)

    def test_zero_costs_watch_check(self, db):
        """Run with assumptions {'transaction_cost_bps': 0} -> check with zero/cost key.

        The M93 service maps existing BacktestAudit issues to checks. Without a
        BacktestAudit the native 'no_backtest_audit' check is returned instead.
        We verify that either the audit-based zero_transaction_cost key or the
        native no_backtest_audit/cost-related key is present.
        """
        from app.services.backtest_reality_score import compute_backtest_reality_check
        from app.services.backtest_reality import run_backtest_audit
        from app.models.backtest_audit import BacktestAudit
        from app.models.backtest_issue import BacktestIssue

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-zerocost")
        run = _make_run(
            db,
            strat.id,
            assumptions={"transaction_cost_bps": 0},
            metrics={"sharpe": 1.2, "annual_return": 0.15, "trade_count": 100},
        )

        # Post an M8 audit so M93 can pick up the zero_transaction_cost issue key
        audit_result = run_backtest_audit(run)
        audit = BacktestAudit(
            strategy_run_id=run.id,
            trust_score=audit_result.trust_score,
            lookahead_risk_score=audit_result.lookahead_risk_score,
            cost_realism_score=audit_result.cost_realism_score,
            fill_realism_score=audit_result.fill_realism_score,
            liquidity_realism_score=audit_result.liquidity_realism_score,
            borrow_realism_score=audit_result.borrow_realism_score,
            data_quality_score=audit_result.data_quality_score,
            overall_status=audit_result.overall_status,
            summary=audit_result.summary,
        )
        db.add(audit)
        db.flush()
        issues_objs = []
        for issue in audit_result.issues:
            bi = BacktestIssue(
                backtest_audit_id=audit.id,
                issue_type=issue.issue_type,
                severity=issue.severity,
                title=issue.title,
                description=issue.description,
                suggested_check=issue.suggested_check,
            )
            db.add(bi)
            issues_objs.append(bi)
        db.flush()

        try:
            result = compute_backtest_reality_check(strat.id, db)
            check_keys = [c.key for c in result.checks]
            # With the audit present, zero_transaction_cost should appear
            assert any(
                "zero" in k or "cost" in k or "transaction" in k or "audit" in k
                for k in check_keys
            ), f"Expected zero/cost/audit check in checks, got: {check_keys}"
        finally:
            for bi in issues_objs:
                _cleanup(db, bi)
            _cleanup(db, audit, run, strat)

    def test_missing_slippage_check(self, db):
        """Run with no slippage assumption -> check related to fill/slippage or audit recommendation.

        M93 surfacse missing fill/slippage via either:
        - The native 'no_backtest_audit' check (recommending the audit which detects fill issues)
        - Or via BacktestAudit issue keys 'missing_fill_model' / 'mid_fill_no_slippage'
          when an audit is posted.
        We verify that at minimum some check is present (non-empty checks list).
        """
        from app.services.backtest_reality_score import compute_backtest_reality_check
        from app.services.backtest_reality import run_backtest_audit
        from app.models.backtest_audit import BacktestAudit
        from app.models.backtest_issue import BacktestIssue

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-noslippage")
        # Provide cost but no fill model or slippage -> audit detects missing_fill_model
        run = _make_run(
            db,
            strat.id,
            assumptions={"transaction_cost_bps": 5},
            metrics={"sharpe": 1.2, "trade_count": 100},
        )

        # Post an M8 audit so M93 can pick up missing_fill_model issue
        audit_result = run_backtest_audit(run)
        audit = BacktestAudit(
            strategy_run_id=run.id,
            trust_score=audit_result.trust_score,
            lookahead_risk_score=audit_result.lookahead_risk_score,
            cost_realism_score=audit_result.cost_realism_score,
            fill_realism_score=audit_result.fill_realism_score,
            liquidity_realism_score=audit_result.liquidity_realism_score,
            borrow_realism_score=audit_result.borrow_realism_score,
            data_quality_score=audit_result.data_quality_score,
            overall_status=audit_result.overall_status,
            summary=audit_result.summary,
        )
        db.add(audit)
        db.flush()
        issues_objs = []
        for issue in audit_result.issues:
            bi = BacktestIssue(
                backtest_audit_id=audit.id,
                issue_type=issue.issue_type,
                severity=issue.severity,
                title=issue.title,
                description=issue.description,
                suggested_check=issue.suggested_check,
            )
            db.add(bi)
            issues_objs.append(bi)
        db.flush()

        try:
            result = compute_backtest_reality_check(strat.id, db)
            check_keys = [c.key for c in result.checks]
            # With the audit, missing_fill_model should appear directly
            has_fill_or_slippage = any(
                "fill" in k or "slippage" in k or "cost" in k for k in check_keys
            )
            assert has_fill_or_slippage, (
                f"Expected fill/slippage-related check, got: {check_keys}"
            )
        finally:
            for bi in issues_objs:
                _cleanup(db, bi)
            _cleanup(db, audit, run, strat)

    def test_high_turnover_no_costs_caps_score(self, db):
        """Run with metrics turnover=2.0, no costs -> score <= 60."""
        from app.services.backtest_reality_score import compute_backtest_reality_check

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-highto")
        run = _make_run(
            db,
            strat.id,
            assumptions={},
            metrics={"turnover": 2.0, "sharpe": 1.5, "annual_return": 0.20, "trade_count": 200},
        )
        try:
            result = compute_backtest_reality_check(strat.id, db)
            assert result.backtest_reality_score <= 60, (
                f"Expected score <= 60 with high turnover and no costs, "
                f"got {result.backtest_reality_score}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_low_trade_count_lowers_score(self, db):
        """Run with metrics trade_count=3 -> score < 100."""
        from app.services.backtest_reality_score import compute_backtest_reality_check

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-lowtrades")
        run = _make_run(
            db,
            strat.id,
            assumptions={"transaction_cost_bps": 5, "fill_model": "vwap", "slippage_bps": 2},
            metrics={"sharpe": 1.2, "annual_return": 0.10, "trade_count": 3},
        )
        try:
            result = compute_backtest_reality_check(strat.id, db)
            assert result.backtest_reality_score < 100, (
                f"Expected score < 100 for low trade_count, got {result.backtest_reality_score}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_high_sharpe_few_trades_lowers_score(self, db):
        """Run sharpe=5.0, trade_count=5 -> score < 100."""
        from app.services.backtest_reality_score import compute_backtest_reality_check

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-highsharpe")
        run = _make_run(
            db,
            strat.id,
            assumptions={"transaction_cost_bps": 5, "fill_model": "vwap", "slippage_bps": 2},
            metrics={"sharpe": 5.0, "annual_return": 0.50, "trade_count": 5},
        )
        try:
            result = compute_backtest_reality_check(strat.id, db)
            assert result.backtest_reality_score < 100, (
                f"Expected score < 100 for implausible sharpe + few trades, "
                f"got {result.backtest_reality_score}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_survivorship_bias_check(self, db):
        """Run with no survivorship_bias assumption -> survivorship check present."""
        from app.services.backtest_reality_score import compute_backtest_reality_check

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-surv")
        # Assumptions that do NOT declare survivorship_bias or universe_construction
        run = _make_run(
            db,
            strat.id,
            assumptions={"transaction_cost_bps": 5, "fill_model": "vwap"},
            metrics={"sharpe": 1.5, "trade_count": 100},
        )
        try:
            result = compute_backtest_reality_check(strat.id, db)
            check_keys = [c.key for c in result.checks]
            assert any("survivorship" in k for k in check_keys), (
                f"Expected a survivorship-related check, got: {check_keys}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_lookahead_bias_check(self, db):
        """Run with no lookahead_control assumption -> lookahead check present."""
        from app.services.backtest_reality_score import compute_backtest_reality_check

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-lookahead")
        # Assumptions that do NOT declare lookahead_control or data_snooping
        run = _make_run(
            db,
            strat.id,
            assumptions={"transaction_cost_bps": 5, "fill_model": "vwap"},
            metrics={"sharpe": 1.5, "trade_count": 100},
        )
        try:
            result = compute_backtest_reality_check(strat.id, db)
            check_keys = [c.key for c in result.checks]
            assert any("lookahead" in k for k in check_keys), (
                f"Expected a lookahead-related check, got: {check_keys}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_no_paper_run_check(self, db):
        """Strategy with only backtest runs -> check with key 'no_paper_or_shadow_run'."""
        from app.services.backtest_reality_score import compute_backtest_reality_check

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-nopaper")
        run = _make_run(
            db,
            strat.id,
            run_type="backtest",
            assumptions={"transaction_cost_bps": 5, "fill_model": "vwap"},
            metrics={"sharpe": 1.5, "trade_count": 100},
        )
        try:
            result = compute_backtest_reality_check(strat.id, db)
            check_keys = [c.key for c in result.checks]
            assert "no_paper_or_shadow_run" in check_keys or any(
                "paper" in k or "shadow" in k for k in check_keys
            ), f"Expected no_paper_or_shadow_run check, got: {check_keys}"
        finally:
            _cleanup(db, run, strat)

    def test_strong_realistic_backtest_scores_high(self, db):
        """Run with good costs, slippage, metrics -> score >= 60."""
        from app.services.backtest_reality_score import compute_backtest_reality_check

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-good")
        run = _make_run(
            db,
            strat.id,
            assumptions={
                "transaction_cost_bps": 10,
                "fill_model": "vwap",
                "slippage_bps": 3,
                "survivorship_bias": False,
                "lookahead_control": True,
            },
            metrics={
                "sharpe": 1.4,
                "annual_return": 0.18,
                "trade_count": 200,
                "turnover": 0.5,
            },
        )
        try:
            result = compute_backtest_reality_check(strat.id, db)
            assert result.backtest_reality_score >= 60, (
                f"Expected score >= 60 for realistic run, got {result.backtest_reality_score}"
            )
        finally:
            _cleanup(db, run, strat)

    def test_root_disclaimer_present(self, db):
        """Disclaimer contains 'not trading advice'."""
        from app.services.backtest_reality_score import compute_backtest_reality_check

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="svc-disclaimer")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            result = compute_backtest_reality_check(strat.id, db)
            assert "not trading advice" in result.disclaimer.lower(), (
                f"Expected 'not trading advice' in disclaimer, got: {result.disclaimer!r}"
            )
        finally:
            _cleanup(db, run, strat)


# ---------------------------------------------------------------------------
# TestBacktestRealityEndpoints
# ---------------------------------------------------------------------------


class TestBacktestRealityEndpoints:
    """Integration tests via TestClient for the M93 backtest reality endpoints."""

    def test_get_endpoint_200(self, client, db):
        """GET /api/strategies/{id}/backtest-reality -> 200."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(f"/api/strategies/{strategy.id}/backtest-reality")
        assert resp.status_code == 200

    def test_unknown_strategy_404(self, client):
        """GET with fake strategy id -> 404."""
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/backtest-reality")
        assert resp.status_code == 404

    def test_refresh_endpoint_200(self, client, db):
        """POST /api/strategies/{id}/backtest-reality/refresh -> 200."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.post(f"/api/strategies/{strategy.id}/backtest-reality/refresh")
        assert resp.status_code == 200

    def test_report_json_200(self, client, db):
        """GET /report?format=json -> 200, has 'content' key."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/backtest-reality/report?format=json"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data, f"Missing 'content' in response: {list(data.keys())}"
        assert isinstance(data["content"], str)
        assert len(data["content"]) > 0

    def test_report_markdown_200(self, client, db):
        """GET /report?format=markdown -> 200, response is text."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/backtest-reality/report?format=markdown"
        )
        assert resp.status_code == 200
        content = resp.text
        assert isinstance(content, str)
        assert len(content) > 0
        assert "Backtest Reality Report" in content

    def test_report_invalid_format_400(self, client, db):
        """GET /report?format=xml -> 400."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/backtest-reality/report?format=xml"
        )
        assert resp.status_code == 400

    def test_response_has_required_fields(self, client, db):
        """GET -> response has backtest_reality_score, verdict, checks, disclaimer."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/backtest-reality")
        assert resp.status_code == 200
        data = resp.json()
        for field in ("backtest_reality_score", "verdict", "checks", "disclaimer"):
            assert field in data, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# TestBacktestRealityAlerts
# ---------------------------------------------------------------------------


class TestBacktestRealityAlerts:
    """Tests for alert generation driven by backtest reality score weakness."""

    def _make_weak_strategy(self, db, *, suffix="alert-brw"):
        """Helper: create a strategy+run+audit with score < 60 to trigger backtest_reality_weak.

        The combination of zero transaction cost + vwap fill + high turnover +
        implausible sharpe yields an M8 trust_score of ~55 which maps to M93
        verdict='review' and backtest_reality_score < 60 — triggering the alert.
        """
        from app.services.backtest_reality import run_backtest_audit
        from app.models.backtest_audit import BacktestAudit
        from app.models.backtest_issue import BacktestIssue

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix=suffix)
        # zero cost + implausible sharpe + high turnover -> audit trust_score ~55 (< 60)
        run = _make_run(
            db,
            strat.id,
            run_type="backtest",
            assumptions={"transaction_cost_bps": 0, "fill_model": "vwap"},
            metrics={
                "sharpe": 4.5,
                "annual_return": 0.50,
                "turnover": 2.0,
                "trade_count": 100,
            },
        )
        # Post M8 audit so M93 uses the trust_score (expected < 60) as base
        audit_result = run_backtest_audit(run)
        audit = BacktestAudit(
            strategy_run_id=run.id,
            trust_score=audit_result.trust_score,
            lookahead_risk_score=audit_result.lookahead_risk_score,
            cost_realism_score=audit_result.cost_realism_score,
            fill_realism_score=audit_result.fill_realism_score,
            liquidity_realism_score=audit_result.liquidity_realism_score,
            borrow_realism_score=audit_result.borrow_realism_score,
            data_quality_score=audit_result.data_quality_score,
            overall_status=audit_result.overall_status,
            summary=audit_result.summary,
        )
        db.add(audit)
        db.flush()
        issues_objs = []
        for issue in audit_result.issues:
            bi = BacktestIssue(
                backtest_audit_id=audit.id,
                issue_type=issue.issue_type,
                severity=issue.severity,
                title=issue.title,
                description=issue.description,
                suggested_check=issue.suggested_check,
            )
            db.add(bi)
            issues_objs.append(bi)
        db.flush()
        return strat, run, audit, issues_objs

    def test_alert_for_weak_reality(self, db):
        """Strategy with a weak M8 audit (score < 60) -> generate_alerts -> backtest_reality_weak alert."""
        from app.services.alerts import generate_alerts_for_strategy
        from app.models.alert import Alert

        strat, run, audit, issues_objs = self._make_weak_strategy(db)
        try:
            generate_alerts_for_strategy(db, str(strat.id))

            alerts = (
                db.query(Alert)
                .filter(
                    Alert.strategy_id == str(strat.id),
                    Alert.rule_type == "backtest_reality_weak",
                )
                .all()
            )
            assert len(alerts) >= 1, (
                "Expected at least one backtest_reality_weak alert for strategy "
                "with weak backtest reality score (< 60)"
            )
        finally:
            db.query(Alert).filter(Alert.strategy_id == str(strat.id)).delete()
            db.flush()
            for bi in issues_objs:
                _cleanup(db, bi)
            _cleanup(db, audit, run, strat)

    def test_no_duplicate_alerts(self, db):
        """generate_alerts twice -> only one backtest_reality_weak alert (idempotent)."""
        from app.services.alerts import generate_alerts_for_strategy
        from app.models.alert import Alert

        strat, run, audit, issues_objs = self._make_weak_strategy(db, suffix="alert-brwdedup")
        try:
            generate_alerts_for_strategy(db, str(strat.id))
            generate_alerts_for_strategy(db, str(strat.id))

            alerts = (
                db.query(Alert)
                .filter(
                    Alert.strategy_id == str(strat.id),
                    Alert.rule_type == "backtest_reality_weak",
                    Alert.status == "open",
                )
                .all()
            )
            assert len(alerts) <= 1, (
                f"Expected at most 1 open backtest_reality_weak alert, got {len(alerts)}"
            )
        finally:
            db.query(Alert).filter(Alert.strategy_id == str(strat.id)).delete()
            db.flush()
            for bi in issues_objs:
                _cleanup(db, bi)
            _cleanup(db, audit, run, strat)


# ---------------------------------------------------------------------------
# TestPortfolioRealityFields
# ---------------------------------------------------------------------------


class TestPortfolioRealityFields:
    """Tests that portfolio reliability rows expose backtest_reality_score."""

    def test_portfolio_has_reality_fields(self, db):
        """build_portfolio_reliability -> rows have 'backtest_reality_score' key."""
        from app.services.portfolio_reliability import build_portfolio_reliability

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="portfolio-br")
        run = _make_run(
            db,
            strat.id,
            run_type="backtest",
            metrics={"sharpe": 1.5, "annual_return": 0.15, "trade_count": 100},
        )
        try:
            result = build_portfolio_reliability(db, project_id=project.id)
            rows = result.get("strategies", result.get("rows", []))
            assert len(rows) > 0, "Expected at least one row in portfolio reliability"

            our_row = next(
                (r for r in rows if str(r.get("strategy_id")) == str(strat.id)),
                None,
            )
            assert our_row is not None, f"Strategy {strat.id} not found in portfolio rows"
            assert "backtest_reality_score" in our_row, (
                "Row missing 'backtest_reality_score' field"
            )
        finally:
            _cleanup(db, run, strat)

    def test_portfolio_row_reality_score_present(self, db):
        """Strategy with backtest run -> backtest_reality_score is not None."""
        from app.services.portfolio_reliability import build_portfolio_reliability

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="portfolio-brscore")
        run = _make_run(
            db,
            strat.id,
            run_type="backtest",
            assumptions={
                "transaction_cost_bps": 5,
                "fill_model": "vwap",
            },
            metrics={"sharpe": 1.8, "annual_return": 0.20, "trade_count": 150},
        )
        try:
            result = build_portfolio_reliability(db, project_id=project.id)
            rows = result.get("strategies", result.get("rows", []))

            our_row = next(
                (r for r in rows if str(r.get("strategy_id")) == str(strat.id)),
                None,
            )
            assert our_row is not None, f"Strategy {strat.id} not found in portfolio rows"
            score = our_row.get("backtest_reality_score")
            assert score is not None, (
                "Expected backtest_reality_score to be non-None for strategy with backtest run"
            )
            assert isinstance(score, (int, float)), (
                f"backtest_reality_score should be numeric, got {type(score)}"
            )
        finally:
            _cleanup(db, run, strat)
