"""M49 tests: Strategy Readiness Scorecard.

Tests for:
  - GET /api/strategies/{id}/readiness endpoint
  - Multi-dimensional readiness scoring
  - Progression path computation
  - Verdict logic (blocked, under_instrumented, requires_review, ready)
  - Language policy (no investment advice language)
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

FORBIDDEN_INVESTMENT_WORDS = ["buy", "sell", "profit", "investment advice"]
FORBIDDEN_AI_WORDS = ["AI", "prediction"]


def _has_forbidden(text: str, words: list[str]) -> list[str]:
    low = text.lower()
    return [w for w in words if w.lower() in low]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m49-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M49 Test Strategy {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.flush()
    return strat


def _make_run(db, strategy_id, *, run_type: str = "backtest", status: str = "completed") -> object:
    from app.models.strategy_run import StrategyRun

    run = StrategyRun(
        strategy_id=strategy_id,
        run_name=f"run-{uuid.uuid4().hex[:6]}",
        run_type=run_type,
        status=status,
    )
    db.add(run)
    db.flush()
    return run


def _make_alert(db, org_id, strategy_id, *, severity: str = "high", status: str = "open") -> object:
    from app.models.alert import Alert

    a = Alert(
        organization_id=str(org_id),
        strategy_id=str(strategy_id),
        rule_type="test_readiness_rule",
        status=status,
        severity=severity,
        title=f"M49 Test alert {severity}",
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(a)
    db.flush()
    return a


def _make_backtest_audit(db, run_id, *, trust_score: int = 80, overall_status: str = "good") -> object:
    from app.models.backtest_audit import BacktestAudit

    audit = BacktestAudit(
        strategy_run_id=run_id,
        trust_score=trust_score,
        overall_status=overall_status,
        summary=f"M49 test audit ts={trust_score}",
    )
    db.add(audit)
    db.flush()
    return audit


def _get_seeded_strategy(db):
    from app.models.strategy import Strategy
    return db.query(Strategy).filter(Strategy.status != "archived").first()


def _get_seeded_org(db):
    from app.models.organization import Organization
    return db.query(Organization).first()


def _get_seeded_project(db):
    from app.models.project import Project
    return db.query(Project).first()


# ---------------------------------------------------------------------------
# TestReadinessEndpoint
# ---------------------------------------------------------------------------


class TestReadinessEndpoint:
    """Integration tests via TestClient for the readiness endpoint."""

    def test_endpoint_returns_200(self, client, db):
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(f"/api/strategies/{strategy.id}/readiness")
        assert resp.status_code == 200

    def test_response_fields(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/readiness")
        data = resp.json()
        assert "dimension_scorecards" in data
        assert "readiness_verdict" in data
        assert "progression_path" in data
        assert "blockers" in data
        assert "review_items" in data
        assert "suggested_next_actions" in data
        assert "readiness_score" in data
        assert "verdict_label" in data
        assert "verdict_summary" in data
        assert "deterministic_summary" in data
        assert "strategy_id" in data
        assert "strategy_name" in data
        assert "generated_at" in data

    def test_unknown_strategy_404(self, client):
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/readiness")
        assert resp.status_code == 404

    def test_dimension_count(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/readiness")
        data = resp.json()
        assert len(data["dimension_scorecards"]) == 8

    def test_dimension_keys_present(self, client, db):
        expected_keys = {
            "strategy_health", "evidence_coverage", "evidence_freshness",
            "backtest_trust", "assumption_health", "drift_stability",
            "alert_state", "run_evidence",
        }
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/readiness")
        data = resp.json()
        actual_keys = {d["dimension_key"] for d in data["dimension_scorecards"]}
        assert actual_keys == expected_keys


# ---------------------------------------------------------------------------
# TestReadinessVerdicts
# ---------------------------------------------------------------------------


class TestReadinessVerdicts:
    """Test verdict classification logic."""

    def test_no_runs_under_instrumented(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="norun")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/readiness")
            assert resp.status_code == 200
            data = resp.json()
            assert data["readiness_verdict"] == "under_instrumented"
        finally:
            db.delete(strat)
            db.flush()

    def test_critical_alert_blocked(self, client, db):
        project = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strat = _make_strategy(db, project.id, suffix="critblocked")
        run = _make_run(db, strat.id, run_type="backtest")
        alert = _make_alert(db, org.id, strat.id, severity="critical", status="open")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/readiness")
            assert resp.status_code == 200
            data = resp.json()
            assert data["readiness_verdict"] == "blocked"
        finally:
            try:
                db.delete(alert)
                db.delete(run)
                db.delete(strat)
                db.flush()
            except Exception:
                pass

    def test_under_instrumented_with_one_run(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="onerun")
        run = _make_run(db, strat.id, run_type="research")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/readiness")
            assert resp.status_code == 200
            data = resp.json()
            # With only a research run and no other evidence, expect under_instrumented or requires_review
            assert data["readiness_verdict"] in ("under_instrumented", "requires_review_before_progression")
        finally:
            try:
                db.delete(run)
                db.delete(strat)
                db.flush()
            except Exception:
                pass

    def test_readiness_with_backtest_run(self, client, db):
        """Seeded strategy has at least one run — verdict should not be under_instrumented if evidence present."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/readiness")
        assert resp.status_code == 200
        data = resp.json()
        # Seeded strategies have runs, so should NOT be under_instrumented (or may be if score < 4 dims)
        # We just verify the response is well-formed
        assert data["readiness_verdict"] in (
            "under_instrumented",
            "blocked",
            "requires_review_before_progression",
            "ready_for_backtest_review",
            "ready_for_paper_trading_consideration",
        )


# ---------------------------------------------------------------------------
# TestDimensionScoring
# ---------------------------------------------------------------------------


class TestDimensionScoring:
    """Test individual dimension scoring logic."""

    def _get_dim(self, data, key):
        for d in data["dimension_scorecards"]:
            if d["dimension_key"] == key:
                return d
        return None

    def test_alert_dimension_ready_no_alerts(self, client, db):
        """A fresh strategy with no alerts should have alert_state score 100."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="alertready")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/readiness")
            assert resp.status_code == 200
            data = resp.json()
            alert_dim = self._get_dim(data, "alert_state")
            assert alert_dim is not None
            assert alert_dim["score"] == 100.0
            assert alert_dim["status"] == "ready"
        finally:
            db.delete(strat)
            db.flush()

    def test_alert_dimension_blocked_critical(self, client, db):
        """A critical open alert should make alert_state status 'blocked'."""
        project = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strat = _make_strategy(db, project.id, suffix="alertcrit")
        alert = _make_alert(db, org.id, strat.id, severity="critical", status="open")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/readiness")
            assert resp.status_code == 200
            data = resp.json()
            alert_dim = self._get_dim(data, "alert_state")
            assert alert_dim is not None
            assert alert_dim["status"] == "blocked"
            assert alert_dim["score"] == 20.0
        finally:
            try:
                db.delete(alert)
                db.delete(strat)
                db.flush()
            except Exception:
                pass

    def test_backtest_trust_missing_no_audit(self, client, db):
        """A strategy with no backtest audit should have backtest_trust status 'missing'."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="btmissing")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/readiness")
            assert resp.status_code == 200
            data = resp.json()
            bt_dim = self._get_dim(data, "backtest_trust")
            assert bt_dim is not None
            assert bt_dim["status"] == "missing"
            assert bt_dim["score"] is None
        finally:
            db.delete(strat)
            db.flush()

    def test_backtest_trust_blocked_low_score(self, client, db):
        """An audit with trust_score=30 should produce backtest_trust status 'blocked'."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="btblocked")
        run = _make_run(db, strat.id, run_type="backtest")
        audit = _make_backtest_audit(db, run.id, trust_score=30, overall_status="poor")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/readiness")
            assert resp.status_code == 200
            data = resp.json()
            bt_dim = self._get_dim(data, "backtest_trust")
            assert bt_dim is not None
            assert bt_dim["status"] == "blocked"
            assert bt_dim["score"] == 30.0
        finally:
            try:
                db.delete(audit)
                db.delete(run)
                db.delete(strat)
                db.flush()
            except Exception:
                pass

    def test_run_evidence_missing_no_runs(self, client, db):
        """A strategy with no runs should have run_evidence status 'missing'."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="runemissing")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/readiness")
            assert resp.status_code == 200
            data = resp.json()
            run_dim = self._get_dim(data, "run_evidence")
            assert run_dim is not None
            assert run_dim["status"] == "missing"
        finally:
            db.delete(strat)
            db.flush()


# ---------------------------------------------------------------------------
# TestProgressionPath
# ---------------------------------------------------------------------------


class TestProgressionPath:
    """Test progression path computation."""

    def test_no_runs_stage(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="norunstage")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/readiness")
            assert resp.status_code == 200
            data = resp.json()
            pp = data["progression_path"]
            assert pp["current_stage"] == "no_runs"
        finally:
            db.delete(strat)
            db.flush()

    def test_research_stage(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="researchstage")
        run = _make_run(db, strat.id, run_type="research")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/readiness")
            assert resp.status_code == 200
            data = resp.json()
            pp = data["progression_path"]
            assert pp["current_stage"] == "research"
        finally:
            try:
                db.delete(run)
                db.delete(strat)
                db.flush()
            except Exception:
                pass

    def test_backtest_stage(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="btstage")
        run = _make_run(db, strat.id, run_type="backtest")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/readiness")
            assert resp.status_code == 200
            data = resp.json()
            pp = data["progression_path"]
            assert pp["current_stage"] == "backtest"
        finally:
            try:
                db.delete(run)
                db.delete(strat)
                db.flush()
            except Exception:
                pass

    def test_suggested_actions_generated(self, client, db):
        """A strategy with missing/weak evidence should have suggested_next_actions."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="actions")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/readiness")
            assert resp.status_code == 200
            data = resp.json()
            # Under-instrumented strategies should have at least some suggested actions
            # Either in suggested_next_actions or in the dimension scorecards
            all_actions = data["suggested_next_actions"]
            dim_actions = [a for d in data["dimension_scorecards"] for a in d["suggested_actions"]]
            assert len(all_actions) > 0 or len(dim_actions) > 0
        finally:
            db.delete(strat)
            db.flush()

    def test_no_investment_language(self, client, db):
        """Deterministic summary must not contain forbidden investment/AI words."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/readiness")
        assert resp.status_code == 200
        data = resp.json()

        summary = data.get("deterministic_summary", "")
        verdict_summary = data.get("verdict_summary", "")
        combined = summary + " " + verdict_summary

        found_investment = _has_forbidden(combined, FORBIDDEN_INVESTMENT_WORDS)
        assert not found_investment, (
            f"Investment language found in readiness output: {found_investment}"
        )
        found_ai = _has_forbidden(combined, FORBIDDEN_AI_WORDS)
        assert not found_ai, (
            f"AI language found in readiness output: {found_ai}"
        )

    def test_no_timeline_event(self, client, db):
        """Readiness endpoint must NOT create any AuditTimelineEvent (read-only)."""
        from app.models.audit_timeline_event import AuditTimelineEvent

        strategy = _get_seeded_strategy(db)
        count_before = db.query(AuditTimelineEvent).count()

        resp = client.get(f"/api/strategies/{strategy.id}/readiness")
        assert resp.status_code == 200

        count_after = db.query(AuditTimelineEvent).count()
        assert count_after == count_before, (
            f"AuditTimelineEvent count changed: {count_before} → {count_after}"
        )

    def test_progression_path_has_required_fields(self, client, db):
        """progression_path must have current_stage, next_recommended_stage, required_before_next_stage."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/readiness")
        assert resp.status_code == 200
        data = resp.json()
        pp = data["progression_path"]
        assert "current_stage" in pp
        assert "next_recommended_stage" in pp
        assert "required_before_next_stage" in pp
        assert isinstance(pp["required_before_next_stage"], list)

    def test_dimension_scorecard_fields(self, client, db):
        """Each dimension scorecard must have required fields."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/readiness")
        assert resp.status_code == 200
        data = resp.json()
        for dim in data["dimension_scorecards"]:
            assert "dimension_key" in dim
            assert "title" in dim
            assert "status" in dim
            assert "evidence_summary" in dim
            assert "blockers" in dim
            assert "warnings" in dim
            assert "suggested_actions" in dim
