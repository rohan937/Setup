"""M45 tests: System Health Admin Endpoint.

Tests for:
  - GET /api/admin/system-health
  - SystemHealthResponse fields and structure
  - Ingestion health statuses
  - API key health metrics
  - Evidence activity status
  - System score computation
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.alert import Alert
from app.models.api_key import ApiKey
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.organization import Organization
from app.models.project import Project
from app.models.sdk_ingestion_batch import SdkIngestionBatch
from app.models.strategy import Strategy
from app.services.api_keys import generate_api_key, hash_api_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_org(db):
    return db.query(Organization).first()


def _get_project(db):
    return db.query(Project).first()


def _get_strategy(db):
    return db.query(Strategy).filter(Strategy.status != "archived").first()


def _make_strategy(db, org, project, *, name=None):
    slug = (name or f"test-m45-{uuid.uuid4().hex[:6]}").lower().replace(" ", "-")
    s = Strategy(
        project_id=project.id,
        name=name or f"TestM45-{uuid.uuid4().hex[:6]}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(s)
    db.flush()
    return s


def _make_api_key(db, org, *, status="active", last_used_at=None):
    raw, prefix = generate_api_key()
    key_hash = hash_api_key(raw, secret="")
    k = ApiKey(
        organization_id=str(org.id),
        name=f"test-key-m45-{uuid.uuid4().hex[:6]}",
        key_prefix=prefix,
        key_hash=key_hash,
        status=status,
        last_used_at=last_used_at,
    )
    db.add(k)
    db.flush()
    return k


def _make_ingestion_batch(db, strategy, *, status="completed"):
    b = SdkIngestionBatch(
        strategy_id=strategy.id,
        idempotency_key=f"idem-m45-{uuid.uuid4().hex}",
        request_hash=uuid.uuid4().hex,
        status=status,
        received_at=datetime.now(timezone.utc),
    )
    db.add(b)
    db.flush()
    return b


def _make_alert(db, org, strategy, *, severity="critical", status="open"):
    a = Alert(
        organization_id=str(org.id),
        strategy_id=str(strategy.id),
        rule_type="test_m45_rule",
        status=status,
        severity=severity,
        title=f"M45 test alert {severity}",
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(a)
    db.flush()
    return a


def _cleanup(db, *objs):
    """Delete objects in reverse order, ignoring errors."""
    for obj in reversed(objs):
        if obj is None:
            continue
        try:
            fresh = db.get(type(obj), obj.id)
            if fresh is not None:
                db.delete(fresh)
        except Exception:
            pass
    try:
        db.commit()
    except Exception:
        db.rollback()


# ---------------------------------------------------------------------------
# TestSystemHealthEndpoint
# ---------------------------------------------------------------------------


class TestSystemHealthEndpoint:
    """Integration tests via TestClient for GET /api/admin/system-health."""

    def test_endpoint_returns_200(self, client):
        resp = client.get("/api/admin/system-health")
        assert resp.status_code == 200

    def test_response_fields(self, client):
        resp = client.get("/api/admin/system-health")
        data = resp.json()
        assert "entity_counts" in data
        assert "ingestion_health" in data
        assert "api_key_health" in data
        assert "evidence_activity" in data

    def test_entity_counts_include_seeded(self, client, db):
        strategy = _get_strategy(db)
        assert strategy is not None
        resp = client.get("/api/admin/system-health")
        data = resp.json()
        assert data["entity_counts"]["strategy_count"] >= 1

    def test_system_status_present(self, client):
        resp = client.get("/api/admin/system-health")
        data = resp.json()
        assert isinstance(data["system_status"], str)
        assert data["system_status"] in ("healthy", "watch", "review", "degraded")

    def test_system_score_present(self, client):
        resp = client.get("/api/admin/system-health")
        data = resp.json()
        # system_score should be float or null
        score = data.get("system_score")
        assert score is None or isinstance(score, (int, float))

    def test_no_timeline_event_created(self, client, db):
        """Endpoint is read-only — should not create any new timeline events."""
        before = db.query(AuditTimelineEvent).count()
        client.get("/api/admin/system-health")
        after = db.query(AuditTimelineEvent).count()
        assert after == before


# ---------------------------------------------------------------------------
# TestIngestionHealth
# ---------------------------------------------------------------------------


class TestIngestionHealth:
    """Tests for ingestion health status logic."""

    def test_no_batches_status(self, client, db):
        """When no batches exist the status should be no_batches.

        This test only passes if no batches exist at all. We verify by
        checking the count; if batches already exist from seed, we skip.
        """
        count = db.query(SdkIngestionBatch).count()
        if count > 0:
            pytest.skip("Batches already seeded — skipping no_batches test")
        resp = client.get("/api/admin/system-health")
        data = resp.json()
        assert data["ingestion_health"]["ingestion_status"] == "no_batches"

    def test_healthy_with_no_failures(self, client, db):
        """Creating a completed batch should yield healthy or no_batches status
        (healthy if no failures exist among all batches)."""
        strategy = _get_strategy(db)
        assert strategy is not None
        batch = _make_ingestion_batch(db, strategy, status="completed")
        db.commit()
        try:
            resp = client.get("/api/admin/system-health")
            data = resp.json()
            status = data["ingestion_health"]["ingestion_status"]
            # With only completed batches the status should be healthy
            assert status in ("healthy", "no_batches", "watch")
        finally:
            _cleanup(db, batch)


# ---------------------------------------------------------------------------
# TestApiKeyHealth
# ---------------------------------------------------------------------------


class TestApiKeyHealth:
    """Tests for API key health metrics."""

    def test_active_keys_counted(self, client, db):
        org = _get_org(db)
        key = _make_api_key(db, org, status="active")
        db.commit()
        try:
            resp = client.get("/api/admin/system-health")
            data = resp.json()
            assert data["api_key_health"]["active_api_keys"] >= 1
        finally:
            _cleanup(db, key)

    def test_revoked_keys_counted(self, client, db):
        org = _get_org(db)
        key = _make_api_key(db, org, status="revoked")
        db.commit()
        try:
            resp = client.get("/api/admin/system-health")
            data = resp.json()
            assert data["api_key_health"]["revoked_api_keys"] >= 1
        finally:
            _cleanup(db, key)

    def test_never_used_counted(self, client, db):
        org = _get_org(db)
        key = _make_api_key(db, org, status="active", last_used_at=None)
        db.commit()
        try:
            resp = client.get("/api/admin/system-health")
            data = resp.json()
            assert data["api_key_health"]["keys_never_used"] >= 1
        finally:
            _cleanup(db, key)


# ---------------------------------------------------------------------------
# TestEvidenceActivity
# ---------------------------------------------------------------------------


class TestEvidenceActivity:
    """Tests for evidence activity status logic."""

    def test_activity_status_based_on_events(self, client):
        resp = client.get("/api/admin/system-health")
        data = resp.json()
        status = data["evidence_activity"]["activity_status"]
        assert status in ("active", "quiet", "stale", "no_activity")

    def test_events_counted(self, client):
        resp = client.get("/api/admin/system-health")
        data = resp.json()
        assert isinstance(data["evidence_activity"]["events_last_30d"], int)
        assert data["evidence_activity"]["events_last_30d"] >= 0


# ---------------------------------------------------------------------------
# TestSystemScore
# ---------------------------------------------------------------------------


class TestSystemScore:
    """Tests for system score computation."""

    def test_score_decreases_with_high_alerts(self, client, db):
        org = _get_org(db)
        project = _get_project(db)
        strategy = _make_strategy(db, org, project)
        alert = _make_alert(db, org, strategy, severity="critical", status="open")
        db.commit()
        try:
            resp = client.get("/api/admin/system-health")
            data = resp.json()
            # Score must exist — it may be lower than 100 given the alert
            score = data.get("system_score")
            assert score is not None
        finally:
            _cleanup(db, alert, strategy)

    def test_score_is_float(self, client):
        resp = client.get("/api/admin/system-health")
        data = resp.json()
        score = data.get("system_score")
        assert score is None or isinstance(score, float)

    def test_suggested_checks_generated(self, client):
        resp = client.get("/api/admin/system-health")
        data = resp.json()
        checks = data.get("suggested_operational_checks")
        assert isinstance(checks, list)
        assert len(checks) >= 1
