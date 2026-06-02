"""M50 tests: Shadow Production Monitor.

Tests for:
  - GET /api/strategies/{id}/shadow-monitor endpoint
  - Run selection (latest / selected modes)
  - Shadow stability scoring
  - Production checks generation
  - Language policy (no investment advice)
  - Read-only: no AuditTimelineEvent created

All tests use the shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FORBIDDEN_AI_WORDS = ["AI", "prediction", "guaranteed"]
FORBIDDEN_INVESTMENT_WORDS = ["buy", "sell", "investment advice", "unprofitable"]


def _has_forbidden(text: str, words: list[str]) -> list[str]:
    low = text.lower()
    return [w for w in words if w.lower() in low]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m50-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M50 Test Strategy {suffix}",
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


def _make_alert(db, org_id, strategy_id, *, severity: str = "high", status: str = "open") -> object:
    from app.models.alert import Alert

    a = Alert(
        organization_id=str(org_id),
        strategy_id=str(strategy_id),
        rule_type="test_m50_rule",
        status=status,
        severity=severity,
        title=f"M50 Test alert {severity}",
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(a)
    db.flush()
    return a


def _get_seeded_strategy(db):
    from app.models.strategy import Strategy

    return db.query(Strategy).filter(Strategy.status != "archived").first()


def _get_seeded_project(db):
    from app.models.project import Project

    return db.query(Project).first()


def _get_seeded_org(db):
    from app.models.organization import Organization

    return db.query(Organization).first()


# ---------------------------------------------------------------------------
# TestShadowMonitorEndpoint
# ---------------------------------------------------------------------------


class TestShadowMonitorEndpoint:
    """Integration tests via TestClient for the shadow-monitor endpoint."""

    def test_endpoint_returns_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(f"/api/strategies/{strategy.id}/shadow-monitor")
        assert resp.status_code == 200

    def test_no_shadow_runs_status(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="noshadow")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/shadow-monitor")
            assert resp.status_code == 200
            data = resp.json()
            assert data["monitor_status"] == "no_shadow_runs"
            assert data["shadow_stability_score"] is None
        finally:
            db.delete(run)
            db.delete(strat)
            db.flush()

    def test_no_baseline_status(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="nobaseline")
        run = _make_run(db, strat.id, run_type="paper")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/shadow-monitor")
            assert resp.status_code == 200
            data = resp.json()
            assert data["monitor_status"] == "insufficient_baseline"
            assert data["shadow_stability_score"] is None
        finally:
            db.delete(run)
            db.delete(strat)
            db.flush()

    def test_response_fields(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/shadow-monitor")
        data = resp.json()
        assert "monitor_status" in data
        assert "shadow_stability_score" in data
        assert "production_checks" in data
        assert "strategy_id" in data
        assert "strategy_name" in data
        assert "generated_at" in data
        assert "deterministic_summary" in data
        assert "highlighted_findings" in data
        assert "blockers" in data
        assert "suggested_actions" in data
        assert "metric_comparisons" in data
        assert "evidence_comparisons" in data
        assert "assumption_changes" in data
        assert "trust_comparison" in data

    def test_unknown_strategy_404(self, client):
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/shadow-monitor")
        assert resp.status_code == 404

    def test_invalid_mode_400(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/shadow-monitor?mode=invalid")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# TestRunSelection
# ---------------------------------------------------------------------------


class TestRunSelection:
    """Tests for run selection logic."""

    def test_latest_mode_selects_backtest_baseline(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="btbase")
        research = _make_run(db, strat.id, run_type="research")
        backtest = _make_run(db, strat.id, run_type="backtest")
        paper = _make_run(db, strat.id, run_type="paper")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/shadow-monitor")
            data = resp.json()
            assert data["baseline_run"] is not None
            # backtest should be selected over research (backtest listed last = preferred)
            assert data["baseline_run"]["run_type"] == "backtest"
        finally:
            db.delete(paper)
            db.delete(backtest)
            db.delete(research)
            db.delete(strat)
            db.flush()

    def test_latest_mode_selects_paper_shadow(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="papershadow")
        backtest = _make_run(db, strat.id, run_type="backtest")
        paper = _make_run(db, strat.id, run_type="paper")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/shadow-monitor")
            data = resp.json()
            assert data["shadow_run"] is not None
            assert data["shadow_run"]["run_type"] in ("paper", "live")
        finally:
            db.delete(paper)
            db.delete(backtest)
            db.delete(strat)
            db.flush()

    def test_selected_mode_validates_ownership(self, client, db):
        """Baseline run from different strategy should fail."""
        project = _get_seeded_project(db)
        strat_a = _make_strategy(db, project.id, suffix="selown-a")
        strat_b = _make_strategy(db, project.id, suffix="selown-b")
        run_a = _make_run(db, strat_a.id, run_type="backtest")
        run_b = _make_run(db, strat_b.id, run_type="paper")
        try:
            resp = client.get(
                f"/api/strategies/{strat_b.id}/shadow-monitor"
                f"?mode=selected&baseline_run_id={run_a.id}&shadow_run_id={run_b.id}"
            )
            assert resp.status_code == 400
        finally:
            db.delete(run_b)
            db.delete(run_a)
            db.delete(strat_b)
            db.delete(strat_a)
            db.flush()

    def test_selected_mode_uses_provided_runs(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="selruns")
        baseline = _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 1.2})
        shadow = _make_run(db, strat.id, run_type="paper", metrics={"sharpe": 1.1})
        try:
            resp = client.get(
                f"/api/strategies/{strat.id}/shadow-monitor"
                f"?mode=selected&baseline_run_id={baseline.id}&shadow_run_id={shadow.id}"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["baseline_run"]["run_id"] == str(baseline.id)
            assert data["shadow_run"]["run_id"] == str(shadow.id)
        finally:
            db.delete(shadow)
            db.delete(baseline)
            db.delete(strat)
            db.flush()


# ---------------------------------------------------------------------------
# TestShadowScoring
# ---------------------------------------------------------------------------


class TestShadowScoring:
    """Tests for scoring and status logic."""

    def test_no_shadow_score_null(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="nullscore")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/shadow-monitor")
            data = resp.json()
            assert data["shadow_stability_score"] is None
        finally:
            db.delete(run)
            db.delete(strat)
            db.flush()

    def test_stable_with_similar_runs(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="similar")
        metrics = {"sharpe": 1.2, "annual_return": 0.15, "max_drawdown": -0.1}
        baseline = _make_run(db, strat.id, run_type="backtest", metrics=metrics)
        shadow = _make_run(db, strat.id, run_type="paper", metrics=metrics)
        try:
            resp = client.get(f"/api/strategies/{strat.id}/shadow-monitor")
            data = resp.json()
            assert data["monitor_status"] in ("stable", "watch", "review")
            if data["shadow_stability_score"] is not None:
                # Similar metrics should produce a reasonable score
                assert data["shadow_stability_score"] >= 0
        finally:
            db.delete(shadow)
            db.delete(baseline)
            db.delete(strat)
            db.flush()

    def test_severe_with_sharpe_drop(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="sharpedrop")
        baseline = _make_run(db, strat.id, run_type="backtest", metrics={"sharpe": 2.0})
        shadow = _make_run(db, strat.id, run_type="paper", metrics={"sharpe": 0.3})
        try:
            resp = client.get(f"/api/strategies/{strat.id}/shadow-monitor")
            data = resp.json()
            assert data["monitor_status"] in ("review", "severe", "watch")
            # Large sharpe drop should lower the score
            if data["shadow_stability_score"] is not None:
                assert data["shadow_stability_score"] < 100
        finally:
            db.delete(shadow)
            db.delete(baseline)
            db.delete(strat)
            db.flush()

    def test_production_checks_generated(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="prodchk")
        baseline = _make_run(db, strat.id, run_type="backtest")
        shadow = _make_run(db, strat.id, run_type="paper")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/shadow-monitor")
            data = resp.json()
            assert "production_checks" in data
            checks = data["production_checks"]
            # When shadow run exists, all 11 checks should be present
            assert len(checks) == 11
            check_keys = {c["check_key"] for c in checks}
            from app.services.shadow_production import PRODUCTION_CHECK_KEYS
            assert check_keys == set(PRODUCTION_CHECK_KEYS)
        finally:
            db.delete(shadow)
            db.delete(baseline)
            db.delete(strat)
            db.flush()

    def test_no_high_alerts_check_passes(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="noalerts")
        baseline = _make_run(db, strat.id, run_type="backtest")
        shadow = _make_run(db, strat.id, run_type="paper")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/shadow-monitor")
            data = resp.json()
            checks = {c["check_key"]: c for c in data["production_checks"]}
            assert "no_high_or_critical_alerts" in checks
            assert checks["no_high_or_critical_alerts"]["passed"] is True
        finally:
            db.delete(shadow)
            db.delete(baseline)
            db.delete(strat)
            db.flush()

    def test_high_alert_check_fails(self, client, db):
        project = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strat = _make_strategy(db, project.id, suffix="highalert")
        baseline = _make_run(db, strat.id, run_type="backtest")
        shadow = _make_run(db, strat.id, run_type="paper")
        alert = _make_alert(db, org.id, strat.id, severity="critical", status="open")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/shadow-monitor")
            data = resp.json()
            checks = {c["check_key"]: c for c in data["production_checks"]}
            assert "no_high_or_critical_alerts" in checks
            assert checks["no_high_or_critical_alerts"]["passed"] is False
        finally:
            db.delete(alert)
            db.delete(shadow)
            db.delete(baseline)
            db.delete(strat)
            db.flush()


# ---------------------------------------------------------------------------
# TestSummaryLanguage
# ---------------------------------------------------------------------------


class TestSummaryLanguage:
    """Tests for language policy compliance."""

    def test_no_ai_language(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/shadow-monitor")
        data = resp.json()
        summary = data.get("deterministic_summary", "")
        found = _has_forbidden(summary, FORBIDDEN_AI_WORDS)
        assert not found, f"Forbidden AI words found in summary: {found}"

    def test_no_investment_language(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/shadow-monitor")
        data = resp.json()
        summary = data.get("deterministic_summary", "")
        found = _has_forbidden(summary, FORBIDDEN_INVESTMENT_WORDS)
        assert not found, f"Forbidden investment words found in summary: {found}"

    def test_no_timeline_event(self, client, db):
        from app.models.audit_timeline_event import AuditTimelineEvent

        strategy = _get_seeded_strategy(db)
        before_count = db.query(AuditTimelineEvent).count()
        client.get(f"/api/strategies/{strategy.id}/shadow-monitor")
        after_count = db.query(AuditTimelineEvent).count()
        assert after_count == before_count, (
            "Shadow monitor endpoint must not create AuditTimelineEvent records"
        )
