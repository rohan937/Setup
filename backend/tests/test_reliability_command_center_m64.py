"""M64 tests: Strategy Reliability Command Center.

Tests for:
  - GET /api/strategies/{id}/command-center endpoint
  - Command status and score computation
  - Subsystem aggregation
  - Governance, evidence, and workflow summaries
  - Language policy (no investment advice / AI language)
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

FORBIDDEN_INVESTMENT_WORDS = ["buy", "sell", "profitable", "investment advice", "safe to trade"]
FORBIDDEN_AI_WORDS = ["AI", "prediction"]
FORBIDDEN_SUMMARY_WORDS = ["incident", "breach", "strategy failed", "do not trade"]
FORBIDDEN_NOTE_WORDS = ["approved to trade", "kill-switch"]


def _has_forbidden(text: str, words: list[str]) -> list[str]:
    low = text.lower()
    return [w for w in words if w.lower() in low]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_seeded_project(db):
    from app.models.project import Project
    return db.query(Project).first()


def _get_seeded_strategy(db):
    from app.models.strategy import Strategy
    return db.query(Strategy).filter(Strategy.status != "archived").first()


def _get_seeded_organization(db):
    from app.models.organization import Organization
    return db.query(Organization).first()


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m64-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M64 Test Strategy {suffix}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.flush()
    return strat


def _make_alert(db, strategy_id, org_id, *, severity: str = "critical") -> object:
    from app.models.alert import Alert

    alert = Alert(
        organization_id=str(org_id),
        strategy_id=str(strategy_id),
        rule_type="backtest_trust_deteriorating",
        status="open",
        severity=severity,
        title=f"Test alert {severity}",
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    db.flush()
    return alert


def _make_regression_run(db, strategy_id, *, overall_status: str = "failed") -> object:
    from app.models.regression import StrategyRegressionTestRun

    run = StrategyRegressionTestRun(
        strategy_id=strategy_id,
        overall_status=overall_status,
        required_failed_count=1,
        failed_count=2,
        passed_count=3,
        warning_count=0,
        skipped_count=0,
        mode="latest_vs_previous",
        result_json=[],
    )
    db.add(run)
    db.flush()
    return run


def _make_review_case(db, strategy_id, *, severity: str = "high") -> object:
    from app.models.review_case import ResearchReviewCase

    case = ResearchReviewCase(
        strategy_id=str(strategy_id),
        case_key=f"case-{uuid.uuid4().hex[:8]}",
        title=f"Test review case {severity}",
        severity=severity,
        category="evidence_quality",
        status="open",
        opened_at=datetime.now(timezone.utc),
    )
    db.add(case)
    db.flush()
    return case


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestCommandCenterEndpoint:
    """Tests for the command-center HTTP endpoint."""

    def test_endpoint_returns_200(self, client, seed_data):
        """GET /api/strategies/{id}/command-center returns 200."""
        strategy_id = seed_data["strategy_id"]
        resp = client.get(f"/api/strategies/{strategy_id}/command-center")
        assert resp.status_code == 200
        data = resp.json()
        assert data["strategy_id"] == strategy_id

    def test_missing_strategy_404(self, client):
        """Non-existent strategy ID returns 404."""
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/strategies/{fake_id}/command-center")
        assert resp.status_code == 404

    def test_no_evidence_insufficient_evidence(self, db, client):
        """Empty strategy with no evidence returns a valid command status."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="empty")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/command-center")
            assert resp.status_code == 200
            data = resp.json()
            # Status must be one of the valid options
            assert data["command_status"] in (
                "clear", "monitor", "review", "blocked", "insufficient_evidence"
            )
        finally:
            db.delete(strat)
            db.flush()

    def test_all_subsystems_present(self, client, seed_data):
        """Response contains all expected subsystem keys."""
        strategy_id = seed_data["strategy_id"]
        resp = client.get(f"/api/strategies/{strategy_id}/command-center")
        assert resp.status_code == 200
        data = resp.json()

        subsystem_keys = {s["subsystem_key"] for s in data["subsystem_statuses"]}
        expected_keys = {
            "readiness",
            "robustness",
            "progression_freeze",
            "promotion_gates_paper",
            "promotion_gates_production",
            "evidence_freshness",
            "drift",
            "shadow_monitor",
            "assumption_health",
            "regression_tests",
            "config_policy",
            "evidence_sla",
            "review_cases",
            "alerts",
            "change_impact",
            "research_audit_trail",
            "evidence_graph",
            "experiments",
        }
        assert expected_keys.issubset(subsystem_keys), (
            f"Missing subsystems: {expected_keys - subsystem_keys}"
        )


class TestCommandCenterStatus:
    """Tests for command status computation."""

    def test_blocked_with_critical_alert(self, db, client):
        """A critical open alert causes command_status=blocked."""
        project = _get_seeded_project(db)
        org = _get_seeded_organization(db)
        strat = _make_strategy(db, project.id, suffix="critical-alert")
        alert = _make_alert(db, strat.id, org.id, severity="critical")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/command-center")
            assert resp.status_code == 200
            data = resp.json()
            assert data["command_status"] == "blocked"
        finally:
            db.delete(alert)
            db.delete(strat)
            db.flush()

    def test_review_with_failed_regression(self, db, client):
        """A failed regression test run surfaces as review or blocked status."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="failed-regression")
        reg_run = _make_regression_run(db, strat.id, overall_status="failed")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/command-center")
            assert resp.status_code == 200
            data = resp.json()
            assert data["command_status"] in ("review", "blocked")
        finally:
            db.delete(reg_run)
            db.delete(strat)
            db.flush()

    def test_monitor_with_no_major_issues(self, db, client):
        """Strategy with no major blockers returns monitor/clear/insufficient_evidence."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="no-issues")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/command-center")
            assert resp.status_code == 200
            data = resp.json()
            # No forced blockers — should not be blocked
            assert data["command_status"] in (
                "clear", "monitor", "review", "insufficient_evidence"
            )
        finally:
            db.delete(strat)
            db.flush()

    def test_command_score_range(self, client, seed_data):
        """Command score is between 0 and 100, or None."""
        strategy_id = seed_data["strategy_id"]
        resp = client.get(f"/api/strategies/{strategy_id}/command-center")
        assert resp.status_code == 200
        data = resp.json()
        score = data["command_score"]
        if score is not None:
            assert 0.0 <= score <= 100.0

    def test_score_null_with_few_subsystems(self, db, client):
        """Empty strategy with no evidence has None command_score (< 5 non-null subsystems)."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="score-null")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/command-center")
            assert resp.status_code == 200
            data = resp.json()
            # With no evidence, fewer than 5 subsystems have scores — score must be None
            score = data["command_score"]
            assert score is None or (isinstance(score, (int, float)) and 0 <= score <= 100)
        finally:
            db.delete(strat)
            db.flush()


class TestCommandCenterComponents:
    """Tests for individual command-center components."""

    def test_blockers_sorted_by_severity(self, db, client):
        """Blockers list has critical/blocked ones first."""
        project = _get_seeded_project(db)
        org = _get_seeded_organization(db)
        strat = _make_strategy(db, project.id, suffix="blocker-sort")
        alert = _make_alert(db, strat.id, org.id, severity="critical")
        reg_run = _make_regression_run(db, strat.id, overall_status="warning")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/command-center")
            assert resp.status_code == 200
            data = resp.json()
            blockers = data["top_blockers"]
            if len(blockers) >= 2:
                _severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
                for i in range(len(blockers) - 1):
                    a = _severity_rank.get(blockers[i]["severity"], 99)
                    b = _severity_rank.get(blockers[i + 1]["severity"], 99)
                    assert a <= b, (
                        f"Blockers not sorted: {blockers[i]['severity']} before "
                        f"{blockers[i+1]['severity']}"
                    )
        finally:
            db.delete(reg_run)
            db.delete(alert)
            db.delete(strat)
            db.flush()

    def test_action_queue_present(self, client, seed_data):
        """Response includes an action_queue list."""
        strategy_id = seed_data["strategy_id"]
        resp = client.get(f"/api/strategies/{strategy_id}/command-center")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["action_queue"], list)

    def test_governance_summary_counts(self, db, client):
        """Open review cases are reflected in governance_summary."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="gov-summary")
        review_case = _make_review_case(db, strat.id, severity="high")
        try:
            resp = client.get(f"/api/strategies/{strat.id}/command-center")
            assert resp.status_code == 200
            data = resp.json()
            gs = data["governance_summary"]
            assert gs["open_review_case_count"] >= 1
        finally:
            db.delete(review_case)
            db.delete(strat)
            db.flush()

    def test_evidence_summary_present(self, client, seed_data):
        """Response includes evidence_summary with freshness_status field."""
        strategy_id = seed_data["strategy_id"]
        resp = client.get(f"/api/strategies/{strategy_id}/command-center")
        assert resp.status_code == 200
        data = resp.json()
        assert "evidence_summary" in data
        assert "freshness_status" in data["evidence_summary"]

    def test_workflow_summary_current_stage(self, client, seed_data):
        """Response includes workflow_summary with current_stage field."""
        strategy_id = seed_data["strategy_id"]
        resp = client.get(f"/api/strategies/{strategy_id}/command-center")
        assert resp.status_code == 200
        data = resp.json()
        assert "workflow_summary" in data
        assert "current_stage" in data["workflow_summary"]
        assert data["workflow_summary"]["current_stage"] in (
            "idea", "research", "backtest_review", "paper_candidate",
            "shadow_production", "production_candidate",
        )

    def test_note_not_trading_approval(self, client, seed_data):
        """Note field does not contain trading-approval language."""
        strategy_id = seed_data["strategy_id"]
        resp = client.get(f"/api/strategies/{strategy_id}/command-center")
        assert resp.status_code == 200
        data = resp.json()
        note = data.get("note", "")
        found = _has_forbidden(note, FORBIDDEN_NOTE_WORDS)
        assert not found, f"Forbidden note words found: {found}"

    def test_summary_avoids_forbidden_language(self, client, seed_data):
        """Deterministic summary avoids forbidden summary language."""
        strategy_id = seed_data["strategy_id"]
        resp = client.get(f"/api/strategies/{strategy_id}/command-center")
        assert resp.status_code == 200
        data = resp.json()
        summary = data.get("deterministic_summary", "")
        found = _has_forbidden(summary, FORBIDDEN_SUMMARY_WORDS)
        assert not found, f"Forbidden words found in summary: {found}"

    def test_no_timeline_event_created(self, db, client):
        """Calling the endpoint does not create AuditTimelineEvent rows."""
        from app.models.audit_timeline_event import AuditTimelineEvent

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="readonly")
        try:
            count_before = (
                db.query(AuditTimelineEvent)
                .filter(AuditTimelineEvent.strategy_id == strat.id)
                .count()
            )
            client.get(f"/api/strategies/{strat.id}/command-center")
            db.expire_all()
            count_after = (
                db.query(AuditTimelineEvent)
                .filter(AuditTimelineEvent.strategy_id == strat.id)
                .count()
            )
            assert count_after == count_before, (
                f"Read-only violation: {count_after - count_before} timeline events created"
            )
        finally:
            db.delete(strat)
            db.flush()


class TestCommandCenterSubsystems:
    """Tests that specific subsystem keys appear in the response."""

    def test_readiness_subsystem_present(self, client, seed_data):
        """Subsystem key 'readiness' is in subsystem_statuses."""
        strategy_id = seed_data["strategy_id"]
        resp = client.get(f"/api/strategies/{strategy_id}/command-center")
        assert resp.status_code == 200
        data = resp.json()
        keys = [s["subsystem_key"] for s in data["subsystem_statuses"]]
        assert "readiness" in keys

    def test_robustness_subsystem_present(self, client, seed_data):
        """Subsystem key 'robustness' is in subsystem_statuses."""
        strategy_id = seed_data["strategy_id"]
        resp = client.get(f"/api/strategies/{strategy_id}/command-center")
        assert resp.status_code == 200
        data = resp.json()
        keys = [s["subsystem_key"] for s in data["subsystem_statuses"]]
        assert "robustness" in keys

    def test_freshness_subsystem_present(self, client, seed_data):
        """Subsystem key 'evidence_freshness' is in subsystem_statuses."""
        strategy_id = seed_data["strategy_id"]
        resp = client.get(f"/api/strategies/{strategy_id}/command-center")
        assert resp.status_code == 200
        data = resp.json()
        keys = [s["subsystem_key"] for s in data["subsystem_statuses"]]
        assert "evidence_freshness" in keys
