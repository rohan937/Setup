"""M43 tests: Timeline Analytics endpoint and computation.

Tests for:
  - GET /api/strategies/{id}/timeline/analytics
  - Bucket computation (day, week, month)
  - Inactivity gap detection
  - Staleness status (active / watch / stale / no_activity)
  - Dominant event type and evidence category
  - Summary language: no AI language, no investment advice
  - Read-only guarantee: no AuditTimelineEvent created
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.organization import Organization
from app.models.project import Project
from app.models.strategy import Strategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy(db, *, name=None) -> Strategy:
    org = db.query(Organization).first()
    project = db.query(Project).filter(Project.organization_id == org.id).first()
    slug = (name or f"ta-{uuid.uuid4().hex[:8]}").lower().replace(" ", "-")
    s = Strategy(
        project_id=project.id,
        name=name or f"TA-{uuid.uuid4().hex[:6]}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(s)
    db.flush()
    return s


def _make_event(
    db,
    strategy: Strategy,
    *,
    event_type: str = "strategy_run_logged",
    source_type: str | None = "strategy_run",
    title: str | None = None,
    event_time: datetime | None = None,
) -> AuditTimelineEvent:
    org = db.query(Organization).first()
    ev = AuditTimelineEvent(
        organization_id=org.id,
        project_id=strategy.project_id,
        strategy_id=strategy.id,
        event_type=event_type,
        title=title or f"Event {uuid.uuid4().hex[:6]}",
        description="Test event",
        source_type=source_type,
        source_id=str(uuid.uuid4()),
        severity="info",
        event_time=event_time or datetime.now(timezone.utc),
        metadata_json={},
    )
    db.add(ev)
    db.flush()
    return ev


def _cleanup(db, *objs):
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
# TestTimelineAnalyticsEndpoint
# ---------------------------------------------------------------------------


class TestTimelineAnalyticsEndpoint:
    def test_endpoint_returns_200(self, client, db):
        """GET /api/strategies/{id}/timeline/analytics returns 200 for valid strategy."""
        s = _make_strategy(db)
        try:
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics")
            assert resp.status_code == 200, resp.text
        finally:
            _cleanup(db, s)

    def test_response_fields(self, client, db):
        """Response contains required top-level fields."""
        s = _make_strategy(db)
        ev = _make_event(db, s)
        try:
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics")
            assert resp.status_code == 200
            data = resp.json()
            for field in (
                "strategy_id",
                "strategy_name",
                "generated_at",
                "bucket",
                "lookback_days",
                "total_events",
                "active_bucket_count",
                "empty_bucket_count",
                "staleness_status",
                "deterministic_summary",
                "suggested_checks",
                "buckets",
                "gaps",
                "dominant_event_type",
                "dominant_evidence_category",
                "most_active_bucket_event_count",
                "longest_inactivity_gap_days",
            ):
                assert field in data, f"Missing field: {field}"
            assert isinstance(data["buckets"], list)
            assert isinstance(data["gaps"], list)
            assert isinstance(data["suggested_checks"], list)
        finally:
            _cleanup(db, ev, s)

    def test_unknown_strategy_404(self, client):
        """Unknown strategy UUID returns 404."""
        resp = client.get(f"/api/strategies/{uuid.uuid4()}/timeline/analytics")
        assert resp.status_code == 404

    def test_invalid_bucket_400(self, client, db):
        """Invalid bucket parameter returns 400."""
        s = _make_strategy(db)
        try:
            resp = client.get(
                f"/api/strategies/{s.id}/timeline/analytics?bucket=year"
            )
            assert resp.status_code == 400
        finally:
            _cleanup(db, s)

    def test_no_events_returns_no_activity(self, client, db):
        """New strategy with no events has staleness_status='no_activity'."""
        s = _make_strategy(db)
        try:
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics")
            assert resp.status_code == 200
            data = resp.json()
            assert data["staleness_status"] == "no_activity"
            assert data["total_events"] == 0
        finally:
            _cleanup(db, s)

    def test_week_bucket_default(self, client, db):
        """Default bucket gives week buckets in response."""
        s = _make_strategy(db)
        ev = _make_event(db, s)
        try:
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics")
            assert resp.status_code == 200
            data = resp.json()
            assert data["bucket"] == "week"
        finally:
            _cleanup(db, ev, s)

    def test_day_bucket(self, client, db):
        """bucket=day returns day-granularity buckets."""
        s = _make_strategy(db)
        ev = _make_event(db, s)
        try:
            resp = client.get(
                f"/api/strategies/{s.id}/timeline/analytics?bucket=day"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["bucket"] == "day"
            assert len(data["buckets"]) > 0
        finally:
            _cleanup(db, ev, s)

    def test_month_bucket(self, client, db):
        """bucket=month returns month-granularity buckets."""
        s = _make_strategy(db)
        ev = _make_event(db, s)
        try:
            resp = client.get(
                f"/api/strategies/{s.id}/timeline/analytics?bucket=month"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["bucket"] == "month"
            assert len(data["buckets"]) > 0
        finally:
            _cleanup(db, ev, s)


# ---------------------------------------------------------------------------
# TestTimelineAnalyticsComputation
# ---------------------------------------------------------------------------


class TestTimelineAnalyticsComputation:
    def test_total_events_counted(self, client, db):
        """Strategy with seeded timeline events has total_events > 0."""
        s = _make_strategy(db)
        ev1 = _make_event(db, s, event_type="strategy_run_logged")
        ev2 = _make_event(db, s, event_type="backtest_audit_computed")
        try:
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_events"] >= 2
        finally:
            _cleanup(db, ev1, ev2, s)

    def test_event_type_counts_present(self, client, db):
        """event_type_counts dict present in first non-empty bucket."""
        s = _make_strategy(db)
        ev = _make_event(db, s, event_type="strategy_run_logged")
        try:
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics")
            assert resp.status_code == 200
            data = resp.json()
            non_empty = [b for b in data["buckets"] if b["total_events"] > 0]
            assert len(non_empty) > 0
            bucket = non_empty[0]
            assert "event_type_counts" in bucket
            assert isinstance(bucket["event_type_counts"], dict)
        finally:
            _cleanup(db, ev, s)

    def test_evidence_category_counts_present(self, client, db):
        """evidence_category_counts dict present in non-empty bucket."""
        s = _make_strategy(db)
        ev = _make_event(db, s, event_type="strategy_run_logged", source_type="strategy_run")
        try:
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics")
            assert resp.status_code == 200
            data = resp.json()
            non_empty = [b for b in data["buckets"] if b["total_events"] > 0]
            assert len(non_empty) > 0
            bucket = non_empty[0]
            assert "evidence_category_counts" in bucket
            assert isinstance(bucket["evidence_category_counts"], dict)
        finally:
            _cleanup(db, ev, s)

    def test_latest_event_at_computed(self, client, db):
        """latest_event_at is a datetime string when events exist."""
        s = _make_strategy(db)
        ev = _make_event(db, s)
        try:
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics")
            assert resp.status_code == 200
            data = resp.json()
            assert data["latest_event_at"] is not None
            # Should be parseable as a datetime string
            datetime.fromisoformat(data["latest_event_at"].replace("Z", "+00:00"))
        finally:
            _cleanup(db, ev, s)

    def test_days_since_computed(self, client, db):
        """days_since_latest_event is an int when events exist."""
        s = _make_strategy(db)
        ev = _make_event(db, s)
        try:
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["days_since_latest_event"], int)
        finally:
            _cleanup(db, ev, s)

    def test_staleness_active_for_recent_event(self, client, db):
        """Strategy with recent event (today) has staleness_status='active'."""
        s = _make_strategy(db)
        ev = _make_event(db, s, event_time=datetime.now(timezone.utc))
        try:
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics")
            assert resp.status_code == 200
            data = resp.json()
            assert data["staleness_status"] == "active"
        finally:
            _cleanup(db, ev, s)

    def test_staleness_stale_for_old_event(self, client, db):
        """Strategy with event 60+ days ago has staleness_status='stale'."""
        s = _make_strategy(db)
        old_time = datetime.now(timezone.utc) - timedelta(days=65)
        ev = _make_event(db, s, event_time=old_time)
        try:
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics?lookback_days=730")
            assert resp.status_code == 200
            data = resp.json()
            assert data["staleness_status"] == "stale"
        finally:
            _cleanup(db, ev, s)

    def test_dominant_event_type_computed(self, client, db):
        """dominant_event_type is a string when events exist."""
        s = _make_strategy(db)
        ev = _make_event(db, s, event_type="strategy_run_logged")
        try:
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["dominant_event_type"], str)
        finally:
            _cleanup(db, ev, s)

    def test_most_active_bucket_computed(self, client, db):
        """most_active_bucket_event_count is a non-negative int."""
        s = _make_strategy(db)
        ev = _make_event(db, s)
        try:
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["most_active_bucket_event_count"], int)
            assert data["most_active_bucket_event_count"] >= 0
        finally:
            _cleanup(db, ev, s)


# ---------------------------------------------------------------------------
# TestInactivityGaps
# ---------------------------------------------------------------------------


class TestInactivityGaps:
    def test_gap_detected_for_long_silence(self, client, db):
        """Events far apart produce a gap with gap_days >= 14."""
        s = _make_strategy(db)
        now = datetime.now(timezone.utc)
        ev1 = _make_event(
            db, s, event_time=now - timedelta(days=60), title="Old event"
        )
        ev2 = _make_event(
            db, s, event_time=now - timedelta(days=5), title="Recent event"
        )
        try:
            resp = client.get(
                f"/api/strategies/{s.id}/timeline/analytics?lookback_days=730"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["gaps"]) > 0
            assert data["gaps"][0]["gap_days"] >= 14
        finally:
            _cleanup(db, ev1, ev2, s)

    def test_gap_includes_event_titles(self, client, db):
        """Gap objects include previous_event_title and next_event_title."""
        s = _make_strategy(db)
        now = datetime.now(timezone.utc)
        ev1 = _make_event(
            db, s, event_time=now - timedelta(days=60), title="First event title"
        )
        ev2 = _make_event(
            db, s, event_time=now - timedelta(days=5), title="Second event title"
        )
        try:
            resp = client.get(
                f"/api/strategies/{s.id}/timeline/analytics?lookback_days=730"
            )
            assert resp.status_code == 200
            data = resp.json()
            # Find the between-events gap (not the tail gap)
            between_gaps = [
                g for g in data["gaps"] if g["next_event_title"] is not None
            ]
            if between_gaps:
                gap = between_gaps[0]
                assert gap["previous_event_title"] is not None
                assert gap["next_event_title"] is not None
        finally:
            _cleanup(db, ev1, ev2, s)

    def test_no_gap_for_frequent_events(self, client, db):
        """Events less than 14 days apart produce no between-events gaps."""
        s = _make_strategy(db)
        now = datetime.now(timezone.utc)
        # Three events spread over 10 days total — no single gap >= 14
        ev1 = _make_event(db, s, event_time=now - timedelta(days=10))
        ev2 = _make_event(db, s, event_time=now - timedelta(days=5))
        ev3 = _make_event(db, s, event_time=now - timedelta(days=1))
        try:
            resp = client.get(
                f"/api/strategies/{s.id}/timeline/analytics?lookback_days=30"
            )
            assert resp.status_code == 200
            data = resp.json()
            between_gaps = [
                g for g in data["gaps"] if g["next_event_title"] is not None
            ]
            assert len(between_gaps) == 0
        finally:
            _cleanup(db, ev1, ev2, ev3, s)

    def test_lookback_limits_events(self, client, db):
        """lookback_days=7 excludes older events from the count."""
        s = _make_strategy(db)
        now = datetime.now(timezone.utc)
        ev_old = _make_event(db, s, event_time=now - timedelta(days=30))
        ev_new = _make_event(db, s, event_time=now - timedelta(days=1))
        try:
            resp_short = client.get(
                f"/api/strategies/{s.id}/timeline/analytics?lookback_days=7"
            )
            assert resp_short.status_code == 200
            short_count = resp_short.json()["total_events"]

            resp_long = client.get(
                f"/api/strategies/{s.id}/timeline/analytics?lookback_days=60"
            )
            assert resp_long.status_code == 200
            long_count = resp_long.json()["total_events"]

            assert short_count < long_count
        finally:
            _cleanup(db, ev_old, ev_new, s)


# ---------------------------------------------------------------------------
# TestSummaryLanguage
# ---------------------------------------------------------------------------


class TestSummaryLanguage:
    def test_no_ai_language(self, client, db):
        """deterministic_summary does not contain AI/prediction/forecast."""
        s = _make_strategy(db)
        ev = _make_event(db, s)
        try:
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics")
            assert resp.status_code == 200
            summary = resp.json()["deterministic_summary"].lower()
            for banned in ("ai", "prediction", "forecast", "machine learning", "llm"):
                assert banned not in summary, f"Found banned term {banned!r} in summary"
        finally:
            _cleanup(db, ev, s)

    def test_no_investment_language(self, client, db):
        """deterministic_summary does not contain investment advice language."""
        s = _make_strategy(db)
        ev = _make_event(db, s)
        try:
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics")
            assert resp.status_code == 200
            summary = resp.json()["deterministic_summary"].lower()
            for banned in ("buy", "sell", "profit", "investment advice"):
                assert banned not in summary, f"Found banned term {banned!r} in summary"
        finally:
            _cleanup(db, ev, s)

    def test_no_timeline_event_created(self, client, db):
        """GET analytics endpoint does not create any AuditTimelineEvent rows."""
        s = _make_strategy(db)
        try:
            count_before = (
                db.query(AuditTimelineEvent)
                .filter(AuditTimelineEvent.strategy_id == s.id)
                .count()
            )
            resp = client.get(f"/api/strategies/{s.id}/timeline/analytics")
            assert resp.status_code == 200
            count_after = (
                db.query(AuditTimelineEvent)
                .filter(AuditTimelineEvent.strategy_id == s.id)
                .count()
            )
            assert count_before == count_after, (
                f"Expected no new events, got {count_after - count_before} created"
            )
        finally:
            _cleanup(db, s)
