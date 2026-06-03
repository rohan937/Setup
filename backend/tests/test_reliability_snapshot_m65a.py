"""M65A tests: Strategy Reliability Snapshot Cache.

Tests for:
  - POST /api/strategies/{id}/reliability-snapshot/refresh
  - GET  /api/strategies/{id}/reliability-snapshot
  - GET  /api/strategies/{id}/reliability-snapshots
  - Snapshot reuse when source data unchanged
  - force=True always creates a new snapshot
  - Staleness detection (stale_after, new alert, new review case)
  - Content: command_status, top_blockers, action_queue
  - AuditTimelineEvent created on new snapshot, not on reuse
  - Language policy (no forbidden words in deterministic_summary)

All tests use the shared session-scoped fixtures from conftest.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

# ---------------------------------------------------------------------------
# Language policy constants
# ---------------------------------------------------------------------------

FORBIDDEN_AI_WORDS = ["AI", "approved", "guaranteed"]


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

    slug = f"m65a-test-{suffix}-{uuid.uuid4().hex[:8]}"
    strat = Strategy(
        project_id=project_id,
        name=f"M65A Test Strategy {suffix}",
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


def _make_review_case(db, strategy_id) -> object:
    from app.models.review_case import ResearchReviewCase

    case = ResearchReviewCase(
        strategy_id=str(strategy_id),
        title="Test review case",
        case_key=f"test-case-{uuid.uuid4().hex[:8]}",
        status="open",
        severity="high",
        category="backtest",
        opened_at=datetime.now(timezone.utc),
    )
    db.add(case)
    db.flush()
    return case


# ---------------------------------------------------------------------------
# TestSnapshotEndpoints
# ---------------------------------------------------------------------------


class TestSnapshotEndpoints:
    def test_refresh_creates_snapshot(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="refresh")
        db.commit()

        resp = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["strategy_id"] == str(strat.id)
        assert "id" in data
        assert "snapshot_status" in data
        assert data["snapshot_status"] in ("fresh", "error")

    def test_get_latest_snapshot(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="getlatest")
        db.commit()

        client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")

        resp = client.get(f"/api/strategies/{strat.id}/reliability-snapshot")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["strategy_id"] == str(strat.id)
        assert "is_stale" in data
        assert isinstance(data["stale_reasons"], list)

    def test_get_latest_no_snapshot_returns_404(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="nosnapshot")
        db.commit()

        resp = client.get(f"/api/strategies/{strat.id}/reliability-snapshot")
        assert resp.status_code == 404
        assert "refresh" in resp.json()["detail"].lower()

    def test_list_snapshots_history(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="history")
        db.commit()

        client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh?force=true")
        client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh?force=true")

        resp = client.get(f"/api/strategies/{strat.id}/reliability-snapshots")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 2

    def test_missing_strategy_refresh_404(self, client, db):
        fake_id = str(uuid.uuid4())
        resp = client.post(f"/api/strategies/{fake_id}/reliability-snapshot/refresh")
        assert resp.status_code == 404

    def test_missing_strategy_get_404(self, client, db):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/strategies/{fake_id}/reliability-snapshot")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestSnapshotReuse
# ---------------------------------------------------------------------------


class TestSnapshotReuse:
    def test_refresh_reuses_when_source_unchanged(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="reuse")
        db.commit()

        resp1 = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")
        assert resp1.status_code == 200
        id1 = resp1.json()["id"]

        resp2 = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")
        assert resp2.status_code == 200
        id2 = resp2.json()["id"]

        # Same source data — same snapshot should be returned
        assert id1 == id2

    def test_refresh_force_creates_new(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="force")
        db.commit()

        resp1 = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")
        assert resp1.status_code == 200
        id1 = resp1.json()["id"]

        resp2 = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh?force=true")
        assert resp2.status_code == 200
        id2 = resp2.json()["id"]

        # force=True must always create a new snapshot
        assert id1 != id2

    def test_source_hash_computed(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="hash")
        db.commit()

        resp = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")
        assert resp.status_code == 200
        data = resp.json()
        # source_hash may be None or a string — field must be present
        assert "source_hash" in data
        if data["source_hash"] is not None:
            assert isinstance(data["source_hash"], str)
            assert len(data["source_hash"]) > 0


# ---------------------------------------------------------------------------
# TestSnapshotStaleness
# ---------------------------------------------------------------------------


class TestSnapshotStaleness:
    def test_snapshot_fresh_initially(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="fresh")
        db.commit()

        resp = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")
        assert resp.status_code == 200
        data = resp.json()
        # A brand-new snapshot without any data changes should not be stale
        assert data["is_stale"] is False

    def test_snapshot_stale_when_new_alert_added(self, client, db):
        from app.models.reliability_snapshot import StrategyReliabilitySnapshot
        from app.services.reliability_snapshots import is_snapshot_stale

        project = _get_seeded_project(db)
        org = _get_seeded_organization(db)
        strat = _make_strategy(db, project.id, suffix="stalealert")
        db.commit()

        # Create snapshot
        resp = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")
        assert resp.status_code == 200
        snap_id = resp.json()["id"]

        # Add an alert AFTER the snapshot was created — use a future timestamp
        snapshot = db.query(StrategyReliabilitySnapshot).filter(
            StrategyReliabilitySnapshot.id == uuid.UUID(snap_id)
        ).first()
        assert snapshot is not None

        # Add alert with triggered_at in the future relative to snapshot
        from app.models.alert import Alert
        future_time = datetime.now(timezone.utc) + timedelta(minutes=1)
        alert = Alert(
            organization_id=str(org.id),
            strategy_id=str(strat.id),
            rule_type="data_health_below_threshold",
            status="open",
            severity="high",
            title="Post-snapshot alert",
            triggered_at=future_time,
        )
        db.add(alert)
        db.flush()

        is_stale, reasons = is_snapshot_stale(db, snapshot)
        assert is_stale is True
        assert any("alert" in r.lower() for r in reasons)

    def test_snapshot_stale_when_stale_after_passed(self, client, db):
        from app.models.reliability_snapshot import StrategyReliabilitySnapshot
        from app.services.reliability_snapshots import is_snapshot_stale

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="staleafter")
        db.commit()

        resp = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")
        assert resp.status_code == 200
        snap_id = resp.json()["id"]

        snapshot = db.query(StrategyReliabilitySnapshot).filter(
            StrategyReliabilitySnapshot.id == uuid.UUID(snap_id)
        ).first()
        assert snapshot is not None

        # Force stale_after into the past
        past = datetime.now(timezone.utc) - timedelta(hours=48)
        snapshot.stale_after = past
        db.flush()

        is_stale, reasons = is_snapshot_stale(db, snapshot)
        assert is_stale is True
        assert any("24 hours" in r for r in reasons)

    def test_stale_reasons_present(self, client, db):
        from app.models.reliability_snapshot import StrategyReliabilitySnapshot
        from app.services.reliability_snapshots import is_snapshot_stale

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="reasons")
        db.commit()

        resp = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")
        assert resp.status_code == 200
        snap_id = resp.json()["id"]

        snapshot = db.query(StrategyReliabilitySnapshot).filter(
            StrategyReliabilitySnapshot.id == uuid.UUID(snap_id)
        ).first()

        # Make it stale by setting stale_after to past
        snapshot.stale_after = datetime.now(timezone.utc) - timedelta(hours=1)
        db.flush()

        is_stale, reasons = is_snapshot_stale(db, snapshot)
        assert is_stale is True
        assert isinstance(reasons, list)
        assert len(reasons) > 0
        for r in reasons:
            assert isinstance(r, str)


# ---------------------------------------------------------------------------
# TestSnapshotContent
# ---------------------------------------------------------------------------


class TestSnapshotContent:
    def test_snapshot_extracts_command_status(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="cmdstatus")
        db.commit()

        resp = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")
        assert resp.status_code == 200
        data = resp.json()
        # command_status field must be present (may be None if cc errored)
        assert "command_status" in data

    def test_snapshot_stores_top_blockers(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="blockers")
        db.commit()

        resp = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert "top_blockers_json" in data
        # Must be a list (possibly empty) or None
        assert data["top_blockers_json"] is None or isinstance(data["top_blockers_json"], list)

    def test_snapshot_stores_action_queue(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="actions")
        db.commit()

        resp = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert "action_queue_json" in data
        assert data["action_queue_json"] is None or isinstance(data["action_queue_json"], list)

    def test_timeline_event_created_on_new_refresh(self, client, db):
        from app.models.audit_timeline_event import AuditTimelineEvent
        from app.core.constants import EventType

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="timeline")
        db.commit()

        before_count = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == strat.id,
                AuditTimelineEvent.event_type == EventType.reliability_snapshot_refreshed,
            )
            .count()
        )

        resp = client.post(
            f"/api/strategies/{strat.id}/reliability-snapshot/refresh?force=true"
        )
        assert resp.status_code == 200

        after_count = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == strat.id,
                AuditTimelineEvent.event_type == EventType.reliability_snapshot_refreshed,
            )
            .count()
        )
        assert after_count == before_count + 1

    def test_timeline_event_not_created_when_reused(self, client, db):
        from app.models.audit_timeline_event import AuditTimelineEvent
        from app.core.constants import EventType

        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="noevent")
        db.commit()

        # First call — creates snapshot + event
        resp1 = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")
        assert resp1.status_code == 200

        count_after_first = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == strat.id,
                AuditTimelineEvent.event_type == EventType.reliability_snapshot_refreshed,
            )
            .count()
        )

        # Second call with same data — should reuse snapshot and NOT create a new event
        resp2 = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")
        assert resp2.status_code == 200
        assert resp2.json()["id"] == resp1.json()["id"]  # confirm reuse

        count_after_second = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == strat.id,
                AuditTimelineEvent.event_type == EventType.reliability_snapshot_refreshed,
            )
            .count()
        )
        assert count_after_second == count_after_first

    def test_summary_avoids_forbidden_language(self, client, db):
        project = _get_seeded_project(db)
        strat = _make_strategy(db, project.id, suffix="language")
        db.commit()

        resp = client.post(f"/api/strategies/{strat.id}/reliability-snapshot/refresh")
        assert resp.status_code == 200
        data = resp.json()

        summary = data.get("deterministic_summary") or ""
        found = _has_forbidden(summary, FORBIDDEN_AI_WORDS)
        assert not found, (
            f"Forbidden language found in deterministic_summary: {found!r}\n"
            f"Summary: {summary!r}"
        )
