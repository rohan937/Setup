"""M51 tests: Promotion Gates.

Tests for:
  - GET /api/strategies/{id}/promotion-gates endpoint
  - Stage inference from run types
  - Gate rule logic per target stage
  - Verdict / score computation
  - Language policy (no AI/investment/approval language)
  - Read-only: no AuditTimelineEvent created

All tests use the shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# Valid verdict set
# ---------------------------------------------------------------------------

VALID_VERDICTS = {
    "pass",
    "conditional_pass",
    "requires_review",
    "blocked",
    "insufficient_evidence",
}

FORBIDDEN_AI_WORDS = ["AI", "prediction", "guarantee", "approved to trade"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_seeded_strategy(db):
    from app.models.strategy import Strategy

    return db.query(Strategy).filter(Strategy.status != "archived").first()


def _get_seeded_org(db):
    from app.models.organization import Organization

    return db.query(Organization).first()


def _get_seeded_project(db):
    from app.models.project import Project

    return db.query(Project).first()


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m51-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M51 Test Strategy {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.flush()
    return strat


def _make_run(
    db, strategy_id, *, run_type: str = "backtest", status: str = "completed"
) -> object:
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


def _make_alert(
    db, org_id, strategy_id, *, severity: str = "high", status: str = "open"
) -> object:
    from app.models.alert import Alert

    a = Alert(
        organization_id=str(org_id),
        strategy_id=str(strategy_id),
        rule_type="test_m51_rule",
        status=status,
        severity=severity,
        title=f"M51 Test alert {severity}",
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(a)
    db.flush()
    return a


def _make_backtest_audit(
    db, run_id, *, trust_score: int = 80, overall_status: str = "good"
) -> object:
    from app.models.backtest_audit import BacktestAudit

    audit = BacktestAudit(
        strategy_run_id=run_id,
        trust_score=trust_score,
        overall_status=overall_status,
        summary=f"M51 test audit ts={trust_score}",
    )
    db.add(audit)
    db.flush()
    return audit


# ---------------------------------------------------------------------------
# TestPromotionGatesEndpoint
# ---------------------------------------------------------------------------


class TestPromotionGatesEndpoint:
    """Integration tests via TestClient for the promotion-gates endpoint."""

    def test_endpoint_backtest_review(self, client, db):
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(
            f"/api/strategies/{strategy.id}/promotion-gates",
            params={"target_stage": "backtest_review"},
        )
        assert resp.status_code == 200

    def test_endpoint_paper_candidate(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/promotion-gates",
            params={"target_stage": "paper_candidate"},
        )
        assert resp.status_code == 200

    def test_invalid_stage(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/promotion-gates",
            params={"target_stage": "bogus"},
        )
        assert resp.status_code == 400

    def test_missing_stage_param(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/promotion-gates")
        assert resp.status_code == 422

    def test_unknown_strategy(self, client):
        fake_id = uuid.uuid4()
        resp = client.get(
            f"/api/strategies/{fake_id}/promotion-gates",
            params={"target_stage": "backtest_review"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestStageInference
# ---------------------------------------------------------------------------


class TestStageInference:
    """Test current_stage inference from run types."""

    def test_no_runs_idea_stage(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="no-runs")
        try:
            resp = client.get(
                f"/api/strategies/{strat.id}/promotion-gates",
                params={"target_stage": "backtest_review"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["current_stage"] == "idea"
        finally:
            db.delete(strat)
            db.flush()

    def test_research_run_research_stage(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="research")
        run = None
        try:
            run = _make_run(db, strat.id, run_type="research")
            resp = client.get(
                f"/api/strategies/{strat.id}/promotion-gates",
                params={"target_stage": "backtest_review"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["current_stage"] == "research"
        finally:
            if run:
                db.delete(run)
                db.flush()
            db.delete(strat)
            db.flush()

    def test_backtest_run_backtest_review_stage(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="bt")
        run = None
        try:
            run = _make_run(db, strat.id, run_type="backtest")
            resp = client.get(
                f"/api/strategies/{strat.id}/promotion-gates",
                params={"target_stage": "paper_candidate"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["current_stage"] == "backtest_review"
        finally:
            if run:
                db.delete(run)
                db.flush()
            db.delete(strat)
            db.flush()

    def test_paper_run_paper_candidate_stage(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="paper")
        run = None
        try:
            run = _make_run(db, strat.id, run_type="paper")
            resp = client.get(
                f"/api/strategies/{strat.id}/promotion-gates",
                params={"target_stage": "shadow_production"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["current_stage"] == "paper_candidate"
        finally:
            if run:
                db.delete(run)
                db.flush()
            db.delete(strat)
            db.flush()


# ---------------------------------------------------------------------------
# TestGateRules
# ---------------------------------------------------------------------------


class TestGateRules:
    """Test gate logic for various scenarios."""

    def test_backtest_review_no_runs_insufficient(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="noruns-btr")
        try:
            resp = client.get(
                f"/api/strategies/{strat.id}/promotion-gates",
                params={"target_stage": "backtest_review"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["promotion_verdict"] == "insufficient_evidence"
        finally:
            db.delete(strat)
            db.flush()

    def test_backtest_review_research_run_satisfies(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="res-run-btr")
        run = None
        try:
            run = _make_run(db, strat.id, run_type="research")
            resp = client.get(
                f"/api/strategies/{strat.id}/promotion-gates",
                params={"target_stage": "backtest_review"},
            )
            assert resp.status_code == 200
            data = resp.json()
            # Find the has-run check
            checks = data["gate_checks"]
            run_check = next(
                (c for c in checks if "research" in c["gate_key"].lower() or "backtest" in c["gate_key"].lower()),
                None,
            )
            assert run_check is not None
            assert run_check["passed"] is True
        finally:
            if run:
                db.delete(run)
                db.flush()
            db.delete(strat)
            db.flush()

    def test_critical_alert_blocks(self, client, db):
        project = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strat = _make_strategy(db, project.id, suffix="crit-alert")
        alert = None
        try:
            alert = _make_alert(
                db, org.id, strat.id, severity="critical", status="open"
            )
            resp = client.get(
                f"/api/strategies/{strat.id}/promotion-gates",
                params={"target_stage": "backtest_review"},
            )
            assert resp.status_code == 200
            data = resp.json()
            checks = data["gate_checks"]
            alert_check = next(
                (c for c in checks if "critical" in c["gate_key"].lower()),
                None,
            )
            assert alert_check is not None
            assert alert_check["passed"] is False
            assert alert_check["severity"] in ("high", "critical")
        finally:
            if alert:
                db.delete(alert)
                db.flush()
            db.delete(strat)
            db.flush()

    def test_high_alert_review(self, client, db):
        project = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strat = _make_strategy(db, project.id, suffix="high-alert-pc")
        alert = None
        try:
            alert = _make_alert(
                db, org.id, strat.id, severity="high", status="open"
            )
            resp = client.get(
                f"/api/strategies/{strat.id}/promotion-gates",
                params={"target_stage": "paper_candidate"},
            )
            assert resp.status_code == 200
            data = resp.json()
            checks = data["gate_checks"]
            alert_check = next(
                (c for c in checks if "high" in c["gate_key"].lower() and "alert" in c["gate_key"].lower()),
                None,
            )
            assert alert_check is not None
            assert alert_check["passed"] is False
        finally:
            if alert:
                db.delete(alert)
                db.flush()
            db.delete(strat)
            db.flush()

    def test_backtest_audit_missing_blocks_paper(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="no-audit-pc")
        run = None
        try:
            run = _make_run(db, strat.id, run_type="backtest")
            resp = client.get(
                f"/api/strategies/{strat.id}/promotion-gates",
                params={"target_stage": "paper_candidate"},
            )
            assert resp.status_code == 200
            data = resp.json()
            checks = data["gate_checks"]
            # Find a required backtest audit check that is not passed
            audit_checks = [
                c
                for c in checks
                if "backtest" in c["gate_key"].lower()
                and c["required"] is True
                and c["passed"] is False
            ]
            assert len(audit_checks) >= 1
        finally:
            if run:
                db.delete(run)
                db.flush()
            db.delete(strat)
            db.flush()

    def test_coverage_below_threshold_review(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/promotion-gates",
            params={"target_stage": "backtest_review"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Gate checks should exist for coverage
        checks = data["gate_checks"]
        coverage_check = next(
            (c for c in checks if "coverage" in c["gate_key"].lower()),
            None,
        )
        assert coverage_check is not None

    def test_gate_score_computed(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/promotion-gates",
            params={"target_stage": "backtest_review"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # gate_score is float or null
        assert data["gate_score"] is None or isinstance(data["gate_score"], (int, float))

    def test_required_fail_count_correct(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="fail-count")
        try:
            resp = client.get(
                f"/api/strategies/{strat.id}/promotion-gates",
                params={"target_stage": "paper_candidate"},
            )
            assert resp.status_code == 200
            data = resp.json()
            # Manually count required failing checks
            required_fails = sum(
                1 for c in data["gate_checks"]
                if c["required"] and not c["passed"]
            )
            assert data["required_fail_count"] == required_fails
        finally:
            db.delete(strat)
            db.flush()


# ---------------------------------------------------------------------------
# TestSummaryLanguage
# ---------------------------------------------------------------------------


class TestSummaryLanguage:
    """Test language policy in the promotion gate response."""

    def test_no_ai_language(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/promotion-gates",
            params={"target_stage": "backtest_review"},
        )
        assert resp.status_code == 200
        data = resp.json()
        summary = data.get("deterministic_summary", "")
        for word in FORBIDDEN_AI_WORDS:
            assert word.lower() not in summary.lower(), (
                f"Forbidden word '{word}' found in summary: {summary!r}"
            )

    def test_note_present(self, client, db):
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/promotion-gates",
            params={"target_stage": "backtest_review"},
        )
        assert resp.status_code == 200
        data = resp.json()
        note = data.get("note", "")
        assert "not trading approval" in note.lower(), (
            f"'not trading approval' not found in note: {note!r}"
        )

    def test_verdict_values_valid(self, client, db):
        strategy = _get_seeded_strategy(db)
        for stage in ("backtest_review", "paper_candidate", "shadow_production", "production_candidate"):
            resp = client.get(
                f"/api/strategies/{strategy.id}/promotion-gates",
                params={"target_stage": stage},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["promotion_verdict"] in VALID_VERDICTS, (
                f"Unexpected verdict {data['promotion_verdict']!r} for stage {stage}"
            )

    def test_no_timeline_event(self, client, db):
        from app.models.audit_timeline_event import AuditTimelineEvent

        strategy = _get_seeded_strategy(db)
        before_count = db.query(AuditTimelineEvent).count()
        client.get(
            f"/api/strategies/{strategy.id}/promotion-gates",
            params={"target_stage": "backtest_review"},
        )
        after_count = db.query(AuditTimelineEvent).count()
        assert before_count == after_count, (
            "Endpoint must not create AuditTimelineEvent records"
        )
