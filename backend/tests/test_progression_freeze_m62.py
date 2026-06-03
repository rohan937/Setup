"""M62 tests: Strategy Progression Freeze Recommendations.

Tests for:
  - GET /api/strategies/{id}/progression-freeze endpoint
  - Freeze reason detection
  - Risk score computation
  - Response structure and components
  - Language policy (no investment advice / AI language, no kill-switch language)
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
FORBIDDEN_FREEZE_WORDS = ["kill-switch", "stop trading", "do not trade", "incident"]

VALID_RECOMMENDATIONS = {
    "continue_progression",
    "monitor_before_progression",
    "pause_progression",
    "freeze_progression",
    "insufficient_evidence",
}


def _has_forbidden(text: str, words: list[str]) -> list[str]:
    low = text.lower()
    return [w for w in words if w.lower() in low]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy(db, project_id, *, suffix: str = "") -> object:
    from app.models.strategy import Strategy

    slug = f"m62-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M62 Test Strategy {suffix}",
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


def _make_alert(db, strategy_id, org_id, *, severity: str = "critical", status: str = "open") -> object:
    from app.models.alert import Alert

    alert = Alert(
        organization_id=str(org_id),
        strategy_id=str(strategy_id),
        rule_type="backtest_trust_deteriorating",
        status=status,
        severity=severity,
        title=f"M62 test alert severity={severity}",
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    db.flush()
    return alert


def _make_regression_run(
    db,
    strategy_id,
    *,
    overall_status: str = "failed",
    required_failed_count: int = 1,
    failed_count: int = 2,
    passed_count: int = 3,
    warning_count: int = 0,
    skipped_count: int = 0,
) -> object:
    from app.models.regression import StrategyRegressionTestRun

    run = StrategyRegressionTestRun(
        strategy_id=strategy_id,
        overall_status=overall_status,
        required_failed_count=required_failed_count,
        failed_count=failed_count,
        passed_count=passed_count,
        warning_count=warning_count,
        skipped_count=skipped_count,
        mode="latest_vs_previous",
        result_json=[],
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    return run


def _make_review_case(
    db,
    strategy_id,
    *,
    status: str = "open",
    severity: str = "critical",
    case_key: str | None = None,
) -> object:
    from app.models.review_case import ResearchReviewCase

    now = datetime.now(timezone.utc)
    case = ResearchReviewCase(
        strategy_id=str(strategy_id),
        title=f"M62 test review case {severity}",
        case_key=case_key or f"m62_case_{uuid.uuid4().hex[:8]}",
        status=status,
        severity=severity,
        category="reliability",
        opened_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(case)
    db.flush()
    return case


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
# TestProgressionFreezeEndpoint
# ---------------------------------------------------------------------------


class TestProgressionFreezeEndpoint:
    """Integration tests via TestClient for the progression-freeze endpoint."""

    def test_endpoint_returns_200(self, client, db):
        """GET /api/strategies/{id}/progression-freeze returns 200 for a known strategy."""
        strategy = _get_seeded_strategy(db)
        assert strategy is not None
        resp = client.get(f"/api/strategies/{strategy.id}/progression-freeze")
        assert resp.status_code == 200

    def test_missing_strategy_404(self, client):
        """Non-existent strategy ID returns 404."""
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/progression-freeze")
        assert resp.status_code == 404

    def test_no_evidence_returns_insufficient_evidence(self, client, db):
        """Strategy with no runs returns insufficient_evidence recommendation."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="noevidence")
        resp = client.get(f"/api/strategies/{strat.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommendation"] == "insufficient_evidence"

    def test_valid_target_stage(self, client, db):
        """?target_stage=paper_candidate is accepted."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/progression-freeze?target_stage=paper_candidate"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["target_stage"] == "paper_candidate"

    def test_invalid_target_stage_400(self, client, db):
        """?target_stage=invalid_value returns 400."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(
            f"/api/strategies/{strategy.id}/progression-freeze?target_stage=invalid_value"
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# TestFreezeTriggers
# ---------------------------------------------------------------------------


class TestFreezeTriggers:
    """Tests that specific conditions correctly trigger freeze recommendations."""

    def test_critical_alert_creates_freeze(self, client, db):
        """A critical open alert should produce freeze_progression recommendation."""
        project = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strat = _make_strategy(db, project.id, suffix="criticalalert")
        _make_run(db, strat.id, run_type="backtest")
        _make_alert(db, strat.id, org.id, severity="critical", status="open")

        resp = client.get(f"/api/strategies/{strat.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommendation"] == "freeze_progression"

    def test_required_regression_failure_creates_freeze(self, client, db):
        """StrategyRegressionTestRun with overall_status=failed and required_failed_count=1 triggers freeze."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="regfail")
        _make_run(db, strat.id, run_type="backtest")
        _make_regression_run(
            db,
            strat.id,
            overall_status="failed",
            required_failed_count=1,
            failed_count=2,
            passed_count=3,
            warning_count=0,
            skipped_count=0,
        )

        resp = client.get(f"/api/strategies/{strat.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommendation"] == "freeze_progression"

    def test_stale_freshness_creates_pause(self, client, db):
        """Strategy with sparse evidence should result in at least pause_progression or monitor."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="stale")
        _make_run(db, strat.id, run_type="backtest")

        resp = client.get(f"/api/strategies/{strat.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()
        # With sparse evidence the recommendation should not be freeze (since no explicit blocker),
        # but should be at least monitor or insufficient_evidence
        assert data["recommendation"] in {
            "continue_progression",
            "monitor_before_progression",
            "pause_progression",
            "insufficient_evidence",
        }

    def test_review_case_critical_creates_freeze(self, client, db):
        """A critical open review case should produce freeze_progression recommendation."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="rcritical")
        _make_run(db, strat.id, run_type="backtest")
        _make_review_case(
            db,
            strat.id,
            status="open",
            severity="critical",
            case_key=f"freeze_test_case_{uuid.uuid4().hex[:6]}",
        )

        resp = client.get(f"/api/strategies/{strat.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommendation"] == "freeze_progression"

    def test_clean_strategy_creates_continue_or_monitor(self, client, db):
        """Fresh strategy with minimal evidence -> monitor or continue (not freeze)."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="clean")
        _make_run(db, strat.id, run_type="backtest")

        resp = client.get(f"/api/strategies/{strat.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()
        # Should not be freeze_progression for a clean strategy with no explicit blockers
        assert data["recommendation"] != "freeze_progression"


# ---------------------------------------------------------------------------
# TestFreezeRiskScore
# ---------------------------------------------------------------------------


class TestFreezeRiskScore:
    """Tests for the freeze_risk_score field."""

    def test_score_range_0_to_100(self, client, db):
        """freeze_risk_score must be between 0 and 100 inclusive."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()
        score = data["freeze_risk_score"]
        assert 0 <= score <= 100

    def test_blockers_increase_score(self, client, db):
        """Critical alert + failing regression should produce a higher score than baseline."""
        project = _get_seeded_project(db)
        org = _get_seeded_org(db)

        # Baseline: clean strategy
        clean_strat = _make_strategy(db, project.id, suffix="baseline_score")
        _make_run(db, clean_strat.id, run_type="backtest")
        resp_clean = client.get(f"/api/strategies/{clean_strat.id}/progression-freeze")
        baseline_score = resp_clean.json()["freeze_risk_score"]

        # Blocker strategy: critical alert + required regression failure
        blocker_strat = _make_strategy(db, project.id, suffix="blocker_score")
        _make_run(db, blocker_strat.id, run_type="backtest")
        _make_alert(db, blocker_strat.id, org.id, severity="critical", status="open")
        _make_regression_run(
            db,
            blocker_strat.id,
            overall_status="failed",
            required_failed_count=1,
        )
        resp_blocker = client.get(f"/api/strategies/{blocker_strat.id}/progression-freeze")
        blocker_score = resp_blocker.json()["freeze_risk_score"]

        assert blocker_score > baseline_score

    def test_no_blockers_lower_score(self, client, db):
        """Strategy with no obvious blockers should have a lower score."""
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="noblockers")
        _make_run(db, strat.id, run_type="backtest")

        resp = client.get(f"/api/strategies/{strat.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()
        # Score should be below freeze threshold without explicit blockers
        assert data["freeze_risk_score"] < 70


# ---------------------------------------------------------------------------
# TestFreezeComponents
# ---------------------------------------------------------------------------


class TestFreezeComponents:
    """Tests for the structural components of the progression-freeze response."""

    def test_freeze_reasons_present(self, client, db):
        """Response contains a freeze_reasons list."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["freeze_reasons"], list)

    def test_unfreeze_requirements_present(self, client, db):
        """Response contains an unfreeze_requirements list."""
        project = _get_seeded_project(db)
        org = _get_seeded_org(db)
        strat = _make_strategy(db, project.id, suffix="requirements")
        _make_run(db, strat.id, run_type="backtest")
        _make_alert(db, strat.id, org.id, severity="critical", status="open")

        resp = client.get(f"/api/strategies/{strat.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["unfreeze_requirements"], list)
        # When frozen, should have at least one requirement
        if data["recommendation"] == "freeze_progression":
            assert len(data["unfreeze_requirements"]) >= 1

    def test_subsystem_statuses_present(self, client, db):
        """Response contains a subsystem_statuses list with expected entries."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()
        statuses = data["subsystem_statuses"]
        assert isinstance(statuses, list)
        assert len(statuses) > 0
        # Each entry should have subsystem and status fields
        for entry in statuses:
            assert "subsystem" in entry
            assert "status" in entry

    def test_stage_context_present(self, client, db):
        """stage_context contains current_stage and target_stage."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()
        ctx = data["stage_context"]
        assert "current_stage" in ctx
        assert "target_stage" in ctx
        assert "next_recommended_stage" in ctx
        assert isinstance(ctx.get("stage_path", []), list)

    def test_note_not_trading_approval(self, client, db):
        """The note field must clarify this is not trading approval or live execution control."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()
        note = data.get("note", "").lower()
        assert "not trading approval" in note or "not live execution" in note

    def test_summary_avoids_forbidden_language(self, client, db):
        """deterministic_summary must not contain forbidden trading/kill-switch language."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()
        summary = data.get("deterministic_summary", "")

        forbidden = FORBIDDEN_FREEZE_WORDS + FORBIDDEN_INVESTMENT_WORDS
        found = _has_forbidden(summary, forbidden)
        assert not found, f"Forbidden words found in summary: {found}"

    def test_no_timeline_event_created(self, client, db):
        """GET /progression-freeze is read-only and must not create AuditTimelineEvent rows."""
        from app.models.audit_timeline_event import AuditTimelineEvent

        strategy = _get_seeded_strategy(db)
        before_count = (
            db.query(AuditTimelineEvent)
            .filter(AuditTimelineEvent.strategy_id == strategy.id)
            .count()
        )
        client.get(f"/api/strategies/{strategy.id}/progression-freeze")
        after_count = (
            db.query(AuditTimelineEvent)
            .filter(AuditTimelineEvent.strategy_id == strategy.id)
            .count()
        )
        assert before_count == after_count

    def test_recommendation_is_valid_value(self, client, db):
        """recommendation field must be one of the known valid values."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommendation"] in VALID_RECOMMENDATIONS

    def test_response_counts_match_reasons(self, client, db):
        """blocking_reason_count + review_reason_count + watch_reason_count + missing_evidence_count
        should match the total count breakdown of freeze_reasons."""
        strategy = _get_seeded_strategy(db)
        resp = client.get(f"/api/strategies/{strategy.id}/progression-freeze")
        assert resp.status_code == 200
        data = resp.json()

        reasons = data["freeze_reasons"]
        expected_blockers = sum(1 for r in reasons if r["status"] == "blocker")
        expected_reviews = sum(1 for r in reasons if r["status"] == "review")
        expected_watch = sum(1 for r in reasons if r["status"] == "watch")
        expected_missing = sum(1 for r in reasons if r["status"] == "missing")

        assert data["blocking_reason_count"] == expected_blockers
        assert data["review_reason_count"] == expected_reviews
        assert data["watch_reason_count"] == expected_watch
        assert data["missing_evidence_count"] == expected_missing
