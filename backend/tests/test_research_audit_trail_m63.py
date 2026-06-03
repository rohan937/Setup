"""M63 tests: Research Audit Trail v2.

Tests for:
  - GET /api/strategies/{id}/research-audit-trail
  - Event enrichment: category, importance, phase, status transitions
  - Summary stats: category_counts, high_importance_count
  - Open alert and unresolved review case counts
  - Language policy: no forbidden words
  - Filters: category, severity, include_context
  - Read-only guarantee: no AuditTimelineEvent created

All tests use the shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.alert import Alert
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.organization import Organization
from app.models.project import Project
from app.models.review_case import ResearchReviewCase
from app.models.strategy import Strategy


# ---------------------------------------------------------------------------
# Language policy constants
# ---------------------------------------------------------------------------

FORBIDDEN_WORDS = [
    "incident",
    "breach",
    "strategy failed",
    "do not trade",
    "buy",
    "sell",
    "investment advice",
    "profitable",
    "safe to trade",
    "prediction",
    " AI ",
]


def _has_forbidden(text: str) -> list[str]:
    low = text.lower()
    return [w for w in FORBIDDEN_WORDS if w.lower() in low]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_org(db) -> Organization:
    return db.query(Organization).first()


def _get_project(db) -> Project:
    org = _get_org(db)
    return db.query(Project).filter(Project.organization_id == org.id).first()


def _make_strategy(db, *, suffix: str = "") -> Strategy:
    project = _get_project(db)
    slug = f"m63-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project.id,
        name=f"M63 Test {suffix or uuid.uuid4().hex[:6]}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(strat)
    db.flush()
    return strat


def _make_event(
    db,
    strategy: Strategy,
    *,
    event_type: str = "strategy_run_logged",
    source_type: str | None = "strategy_run",
    source_id: str | None = None,
    severity: str = "info",
    title: str | None = None,
    event_time: datetime | None = None,
    metadata_json: dict | None = None,
) -> AuditTimelineEvent:
    org = _get_org(db)
    ev = AuditTimelineEvent(
        organization_id=org.id,
        project_id=strategy.project_id,
        strategy_id=strategy.id,
        event_type=event_type,
        title=title or f"Event {uuid.uuid4().hex[:6]}",
        description="Test event description",
        source_type=source_type,
        source_id=source_id or str(uuid.uuid4()),
        severity=severity,
        event_time=event_time or datetime.now(timezone.utc),
        metadata_json=metadata_json or {},
    )
    db.add(ev)
    db.flush()
    return ev


def _make_alert(db, strategy: Strategy, *, status: str = "open") -> Alert:
    org = _get_org(db)
    alert = Alert(
        organization_id=str(org.id),
        strategy_id=str(strategy.id),
        rule_type="test_rule",
        status=status,
        severity="high",
        title="Test alert",
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    db.flush()
    return alert


def _make_review_case(db, strategy: Strategy, *, status: str = "open") -> ResearchReviewCase:
    now = datetime.now(timezone.utc)
    case = ResearchReviewCase(
        strategy_id=str(strategy.id),
        title="Test review case",
        case_key=f"test_key_{uuid.uuid4().hex[:8]}",
        status=status,
        severity="medium",
        category="reliability",
        opened_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(case)
    db.flush()
    return case


def _cleanup(db, *objs) -> None:
    for obj in reversed(objs):
        try:
            fresh = db.query(type(obj)).filter(type(obj).id == obj.id).first()
            if fresh is not None:
                db.delete(fresh)
        except Exception:
            pass
    try:
        db.commit()
    except Exception:
        db.rollback()


# ---------------------------------------------------------------------------
# TestAuditTrailEndpoint
# ---------------------------------------------------------------------------


class TestAuditTrailEndpoint:
    def test_endpoint_returns_200(self, client, db):
        """GET /api/strategies/{id}/research-audit-trail returns 200."""
        s = _make_strategy(db, suffix="ep200")
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert "strategy_id" in data
            assert "events" in data
            assert "deterministic_summary" in data
        finally:
            _cleanup(db, s)

    def test_missing_strategy_404(self, client, db):
        """Non-existent strategy ID returns 404."""
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/strategies/{fake_id}/research-audit-trail")
        assert resp.status_code == 404

    def test_no_events_returns_empty(self, client, db):
        """Strategy with no timeline events returns empty events list without error."""
        s = _make_strategy(db, suffix="noevents")
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["events"] == []
            assert data["total_events"] == 0
            assert data["returned_count"] == 0
        finally:
            _cleanup(db, s)

    def test_limit_works(self, client, db):
        """limit query param caps returned events."""
        s = _make_strategy(db, suffix="limit")
        events = [_make_event(db, s) for _ in range(5)]
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail?limit=2")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert len(data["events"]) == 2
            assert data["returned_count"] == 2
        finally:
            _cleanup(db, *events, s)

    def test_offset_works(self, client, db):
        """offset query param skips events."""
        s = _make_strategy(db, suffix="offset")
        events = [_make_event(db, s) for _ in range(5)]
        try:
            resp_all = client.get(f"/api/strategies/{s.id}/research-audit-trail?limit=5")
            assert resp_all.status_code == 200
            all_ids = [e["event_id"] for e in resp_all.json()["events"]]

            resp_off = client.get(f"/api/strategies/{s.id}/research-audit-trail?limit=2&offset=2")
            assert resp_off.status_code == 200
            off_ids = [e["event_id"] for e in resp_off.json()["events"]]

            # Offset events should not overlap with first 2
            assert len(off_ids) == 2
            assert off_ids[0] not in all_ids[:2]
        finally:
            _cleanup(db, *events, s)


# ---------------------------------------------------------------------------
# TestAuditTrailEnrichment
# ---------------------------------------------------------------------------


class TestAuditTrailEnrichment:
    def test_category_mapping_for_run_event(self, client, db):
        """event_type='regression_tests_run' -> category='regression'."""
        s = _make_strategy(db, suffix="cat-reg")
        ev = _make_event(
            db, s,
            event_type="regression_tests_run",
            source_type=None,
        )
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            events = resp.json()["events"]
            reg_events = [e for e in events if e["event_id"] == str(ev.id)]
            assert reg_events, "Expected event not found in response"
            assert reg_events[0]["category"] == "regression"
        finally:
            _cleanup(db, ev, s)

    def test_category_mapping_for_config_event(self, client, db):
        """event_type='config_policy_evaluated' -> category='policy'."""
        s = _make_strategy(db, suffix="cat-pol")
        ev = _make_event(
            db, s,
            event_type="config_policy_evaluated",
            source_type=None,
        )
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            events = resp.json()["events"]
            pol_events = [e for e in events if e["event_id"] == str(ev.id)]
            assert pol_events
            assert pol_events[0]["category"] == "policy"
        finally:
            _cleanup(db, ev, s)

    def test_importance_high_for_governance(self, client, db):
        """Governance category events get at least medium importance."""
        from app.services.research_audit_trail import (
            GOVERNANCE_CATEGORIES,
            _get_category,
            _get_importance,
        )
        s = _make_strategy(db, suffix="imp-gov")
        ev = _make_event(
            db, s,
            event_type="regression_tests_run",
            source_type=None,
            severity="info",
        )
        try:
            category = _get_category(ev.event_type, ev.source_type)
            assert category in GOVERNANCE_CATEGORIES
            importance = _get_importance(ev, category)
            assert importance in ("medium", "high", "critical")
        finally:
            _cleanup(db, ev, s)

    def test_research_phase_computed(self, client, db):
        """Run events get 'evidence_logging' phase, regression gets 'progression_review'."""
        s = _make_strategy(db, suffix="phase")
        ev_run = _make_event(db, s, event_type="strategy_run_logged", source_type="strategy_run")
        ev_reg = _make_event(db, s, event_type="regression_tests_run", source_type=None)
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            events = resp.json()["events"]
            ev_map = {e["event_id"]: e for e in events}

            run_event = ev_map.get(str(ev_run.id))
            assert run_event is not None
            assert run_event["research_phase"] == "evidence_logging"

            reg_event = ev_map.get(str(ev_reg.id))
            assert reg_event is not None
            assert reg_event["research_phase"] == "progression_review"
        finally:
            _cleanup(db, ev_run, ev_reg, s)

    def test_status_transition_extracted(self, client, db):
        """regression_tests_run with metadata_json.overall_status -> status_transition.new_status."""
        s = _make_strategy(db, suffix="transition-reg")
        ev = _make_event(
            db, s,
            event_type="regression_tests_run",
            source_type=None,
            metadata_json={"overall_status": "failed"},
        )
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            events = resp.json()["events"]
            found = [e for e in events if e["event_id"] == str(ev.id)]
            assert found
            transition = found[0]["status_transition"]
            assert transition is not None
            assert transition["new_status"] == "failed"
            assert transition["status_type"] == "regression_status"
        finally:
            _cleanup(db, ev, s)

    def test_status_transition_for_policy(self, client, db):
        """config_policy_evaluated with overall_status -> status_transition extracted."""
        s = _make_strategy(db, suffix="transition-pol")
        ev = _make_event(
            db, s,
            event_type="config_policy_evaluated",
            source_type=None,
            metadata_json={"overall_status": "passed"},
        )
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            events = resp.json()["events"]
            found = [e for e in events if e["event_id"] == str(ev.id)]
            assert found
            transition = found[0]["status_transition"]
            assert transition is not None
            assert transition["new_status"] == "passed"
            assert transition["status_type"] == "policy_status"
        finally:
            _cleanup(db, ev, s)

    def test_suggested_action_for_regression(self, client, db):
        """Regression event with failed status -> suggested_action present."""
        s = _make_strategy(db, suffix="suggest-reg")
        ev = _make_event(
            db, s,
            event_type="regression_tests_run",
            source_type=None,
            severity="warning",
            metadata_json={"overall_status": "failed"},
        )
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            events = resp.json()["events"]
            found = [e for e in events if e["event_id"] == str(ev.id)]
            assert found
            suggested = found[0]["suggested_action"]
            assert suggested is not None
            assert len(suggested) > 0
        finally:
            _cleanup(db, ev, s)

    def test_linked_object_built_with_route_hint(self, client, db):
        """Event with source_id -> linked_object has route_hint."""
        s = _make_strategy(db, suffix="linked")
        source_id = str(uuid.uuid4())
        ev = _make_event(
            db, s,
            event_type="strategy_run_logged",
            source_type="strategy_run",
            source_id=source_id,
        )
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            events = resp.json()["events"]
            found = [e for e in events if e["event_id"] == str(ev.id)]
            assert found
            linked = found[0]["linked_object"]
            assert linked is not None
            assert linked["object_id"] == source_id
            assert linked["route_hint"] is not None
        finally:
            _cleanup(db, ev, s)


# ---------------------------------------------------------------------------
# TestAuditTrailSummary
# ---------------------------------------------------------------------------


class TestAuditTrailSummary:
    def test_category_counts_computed(self, client, db):
        """Multiple events of different types -> category_counts dict populated."""
        s = _make_strategy(db, suffix="catcounts")
        ev1 = _make_event(db, s, event_type="strategy_run_logged", source_type="strategy_run")
        ev2 = _make_event(db, s, event_type="strategy_run_logged", source_type="strategy_run")
        ev3 = _make_event(db, s, event_type="regression_tests_run", source_type=None)
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            data = resp.json()
            cats = data["category_counts"]
            assert cats.get("run", 0) >= 2
            assert cats.get("regression", 0) >= 1
        finally:
            _cleanup(db, ev1, ev2, ev3, s)

    def test_high_importance_count(self, client, db):
        """Events with high/critical severity -> high_importance_count reflects it."""
        s = _make_strategy(db, suffix="highimp")
        ev1 = _make_event(
            db, s,
            event_type="regression_tests_run",
            source_type=None,
            severity="error",
        )
        ev2 = _make_event(
            db, s,
            event_type="strategy_run_logged",
            source_type="strategy_run",
            severity="info",
        )
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            data = resp.json()
            assert data["high_importance_count"] >= 1
        finally:
            _cleanup(db, ev1, ev2, s)

    def test_open_alert_count(self, client, db):
        """Open Alert for strategy -> open_alert_count >= 1."""
        s = _make_strategy(db, suffix="alertcnt")
        alert = _make_alert(db, s, status="open")
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            data = resp.json()
            assert data["open_alert_count"] >= 1
        finally:
            _cleanup(db, alert, s)

    def test_closed_alert_not_counted(self, client, db):
        """Resolved Alert does not increment open_alert_count."""
        s = _make_strategy(db, suffix="alertresolved")
        alert = _make_alert(db, s, status="resolved")
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            data = resp.json()
            assert data["open_alert_count"] == 0
        finally:
            _cleanup(db, alert, s)

    def test_unresolved_review_case_count(self, client, db):
        """Open ResearchReviewCase -> unresolved_review_case_count >= 1."""
        s = _make_strategy(db, suffix="rccount")
        rc = _make_review_case(db, s, status="open")
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            data = resp.json()
            assert data["unresolved_review_case_count"] >= 1
        finally:
            _cleanup(db, rc, s)

    def test_resolved_review_case_not_counted(self, client, db):
        """Resolved ResearchReviewCase does not increment unresolved count."""
        s = _make_strategy(db, suffix="rcresolved")
        rc = _make_review_case(db, s, status="resolved")
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            data = resp.json()
            assert data["unresolved_review_case_count"] == 0
        finally:
            _cleanup(db, rc, s)

    def test_summary_avoids_forbidden_language(self, client, db):
        """deterministic_summary and suggested_checks contain no forbidden language."""
        s = _make_strategy(db, suffix="lang")
        ev = _make_event(db, s, event_type="regression_tests_run", source_type=None)
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            data = resp.json()

            summary = data["deterministic_summary"]
            forbidden_found = _has_forbidden(summary)
            assert not forbidden_found, f"Forbidden words in summary: {forbidden_found}"

            for check in data["suggested_checks"]:
                forbidden_found = _has_forbidden(check)
                assert not forbidden_found, f"Forbidden words in suggested_check: {forbidden_found}"

            for event in data["events"]:
                if event.get("suggested_action"):
                    forbidden_found = _has_forbidden(event["suggested_action"])
                    assert not forbidden_found, (
                        f"Forbidden words in suggested_action: {forbidden_found}"
                    )
        finally:
            _cleanup(db, ev, s)

    def test_no_timeline_event_created(self, client, db):
        """Endpoint is read-only: no new AuditTimelineEvent is created."""
        s = _make_strategy(db, suffix="readonly")
        before_count = (
            db.query(AuditTimelineEvent)
            .filter(AuditTimelineEvent.strategy_id == s.id)
            .count()
        )
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            after_count = (
                db.query(AuditTimelineEvent)
                .filter(AuditTimelineEvent.strategy_id == s.id)
                .count()
            )
            assert after_count == before_count
        finally:
            _cleanup(db, s)


# ---------------------------------------------------------------------------
# TestAuditTrailFilters
# ---------------------------------------------------------------------------


class TestAuditTrailFilters:
    def test_category_filter(self, client, db):
        """?category=regression returns only regression events."""
        s = _make_strategy(db, suffix="filtcat")
        ev_reg = _make_event(db, s, event_type="regression_tests_run", source_type=None)
        ev_run = _make_event(db, s, event_type="strategy_run_logged", source_type="strategy_run")
        try:
            resp = client.get(
                f"/api/strategies/{s.id}/research-audit-trail?category=regression"
            )
            assert resp.status_code == 200
            events = resp.json()["events"]
            # All returned events should be category=regression
            for e in events:
                assert e["category"] == "regression", f"Unexpected category: {e['category']}"
            # The regression event should be present
            ids = [e["event_id"] for e in events]
            assert str(ev_reg.id) in ids
            # The run event should NOT be present
            assert str(ev_run.id) not in ids
        finally:
            _cleanup(db, ev_reg, ev_run, s)

    def test_severity_filter(self, client, db):
        """?severity=warning returns only warning-severity events."""
        s = _make_strategy(db, suffix="filtsev")
        ev_warn = _make_event(
            db, s,
            event_type="strategy_run_logged",
            source_type="strategy_run",
            severity="warning",
        )
        ev_info = _make_event(
            db, s,
            event_type="strategy_run_logged",
            source_type="strategy_run",
            severity="info",
        )
        try:
            resp = client.get(
                f"/api/strategies/{s.id}/research-audit-trail?severity=warning"
            )
            assert resp.status_code == 200
            events = resp.json()["events"]
            for e in events:
                assert e["severity"] == "warning"
            ids = [e["event_id"] for e in events]
            assert str(ev_warn.id) in ids
            assert str(ev_info.id) not in ids
        finally:
            _cleanup(db, ev_warn, ev_info, s)

    def test_include_context_false(self, client, db):
        """?include_context=false -> downstream_context is None for all events."""
        s = _make_strategy(db, suffix="nocontext")
        ev = _make_event(
            db, s,
            event_type="strategy_run_logged",
            source_type="strategy_run",
        )
        try:
            resp = client.get(
                f"/api/strategies/{s.id}/research-audit-trail?include_context=false"
            )
            assert resp.status_code == 200
            events = resp.json()["events"]
            for e in events:
                assert e["downstream_context"] is None, (
                    f"Expected no downstream_context when include_context=false, got {e['downstream_context']}"
                )
        finally:
            _cleanup(db, ev, s)

    def test_response_shape(self, client, db):
        """Response includes all required top-level fields."""
        s = _make_strategy(db, suffix="shape")
        ev = _make_event(db, s)
        required_fields = {
            "strategy_id",
            "strategy_name",
            "generated_at",
            "total_events",
            "returned_count",
            "category_counts",
            "importance_counts",
            "phase_counts",
            "high_importance_count",
            "latest_event_at",
            "unresolved_review_case_count",
            "open_alert_count",
            "deterministic_summary",
            "suggested_checks",
            "events",
        }
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            data = resp.json()
            missing = required_fields - set(data.keys())
            assert not missing, f"Missing fields: {missing}"
        finally:
            _cleanup(db, ev, s)

    def test_event_shape(self, client, db):
        """Each returned event includes all required fields."""
        s = _make_strategy(db, suffix="evshape")
        ev = _make_event(
            db, s,
            event_type="strategy_run_logged",
            source_type="strategy_run",
        )
        required_event_fields = {
            "event_id",
            "event_time",
            "event_type",
            "title",
            "severity",
            "category",
            "importance",
            "research_phase",
            "evidence_summary_json",
        }
        try:
            resp = client.get(f"/api/strategies/{s.id}/research-audit-trail")
            assert resp.status_code == 200
            events = resp.json()["events"]
            assert events, "Expected at least one event"
            ev_data = events[0]
            missing = required_event_fields - set(ev_data.keys())
            assert not missing, f"Missing event fields: {missing}"
        finally:
            _cleanup(db, ev, s)
