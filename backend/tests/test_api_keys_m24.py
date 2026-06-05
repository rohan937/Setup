"""M24 tests: API Key Foundation + SDK Auth.

Tests for:
  - POST /api/api-keys         — create, raw key returned once, warning present
  - GET  /api/api-keys         — list, no raw_key or key_hash in response
  - PATCH /api/api-keys/{id}/revoke — revoke, status becomes "revoked"
  - Timeline events on create and revoke
  - Auth dependency: bearer token, x-qf-api-key header, 401 enforcement
  - last_used_at updated on authenticated request
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest

from app.core.constants import EventType
from app.models.api_key import ApiKey
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.organization import Organization
from app.models.project import Project
from app.models.strategy import Strategy
from app.services.api_keys import (
    generate_api_key,
    hash_api_key,
    verify_api_key,
    extract_api_key_from_request,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_strategy(db, org, project, *, name=None):
    slug = (name or f"test-{uuid.uuid4().hex[:6]}").lower().replace(" ", "-")
    s = Strategy(
        project_id=project.id,
        name=name or f"TestStrat-{uuid.uuid4().hex[:6]}",
        slug=slug,
        asset_class="equity",
        status="active",
    )
    db.add(s)
    db.flush()
    return s


def _cleanup_strategy(db, strategy):
    from sqlalchemy import inspect as sa_inspect
    state = sa_inspect(strategy)
    if state.detached or state.deleted:
        fresh = db.query(Strategy).filter(Strategy.id == strategy.id).first()
        if fresh is not None:
            db.delete(fresh)
            db.commit()
        return
    if not state.transient:
        try:
            db.delete(strategy)
            db.commit()
        except Exception:
            db.rollback()


def _cleanup_key(db, key_id):
    # key_id may come from JSON as a str — convert to uuid.UUID for Uuid(as_uuid=True) column
    if isinstance(key_id, str):
        key_id = uuid.UUID(key_id)
    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if key is not None:
        db.delete(key)
        db.commit()


def _get_org_project(db):
    org = db.query(Organization).first()
    project = db.query(Project).filter(Project.organization_id == org.id).first()
    return org, project


_INGESTION_BUNDLE = {
    "strategy_version": {
        "version_label": "v1.0.0",
        "git_commit": "abc123",
        "branch_name": "main",
        "code_path": "strategies/test.py",
        "signal_name": "z_score",
        "signal_description": "Test signal",
    }
}


# ---------------------------------------------------------------------------
# TestApiKeyService
# ---------------------------------------------------------------------------


class TestApiKeyService:
    def test_generate_api_key_format(self):
        raw_key, _ = generate_api_key(env="local")
        assert raw_key.startswith("qf_local_"), f"Expected qf_local_ prefix, got {raw_key[:20]}"

    def test_generate_api_key_prefix(self):
        _, prefix = generate_api_key(env="local")
        assert len(prefix) <= 20, f"Prefix too long: {len(prefix)}"
        assert prefix.startswith("qf_"), f"Prefix should start with qf_, got {prefix}"

    def test_hash_api_key(self):
        raw_key, _ = generate_api_key()
        h = hash_api_key(raw_key)
        assert len(h) == 64, f"Expected 64-char hex, got {len(h)}"
        # Should be valid hex
        int(h, 16)

    def test_verify_api_key_correct(self):
        raw_key, _ = generate_api_key()
        h = hash_api_key(raw_key)
        assert verify_api_key(raw_key, h) is True

    def test_verify_api_key_wrong(self):
        raw_key, _ = generate_api_key()
        h = hash_api_key(raw_key)
        assert verify_api_key("wrong_key", h) is False

    def test_hash_with_secret(self):
        raw_key, _ = generate_api_key()
        h_no_secret = hash_api_key(raw_key, "")
        h_with_secret = hash_api_key(raw_key, "my_secret")
        assert h_no_secret != h_with_secret

    def test_constant_time_comparison(self):
        """verify_api_key should use hmac.compare_digest (constant-time)."""
        import inspect
        import hmac as _hmac
        src = inspect.getsource(verify_api_key)
        assert "compare_digest" in src, "verify_api_key should use hmac.compare_digest"


# ---------------------------------------------------------------------------
# TestApiKeyCRUD
# ---------------------------------------------------------------------------


class TestApiKeyCRUD:
    def test_create_api_key(self, client, db):
        org, _ = _get_org_project(db)
        resp = client.post("/api/api-keys", json={
            "name": "Test Key CRUD",
            "organization_id": str(org.id),
            "scopes": ["evidence:write"],
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "raw_key" in data
        assert data["raw_key"].startswith("qf_")
        # Cleanup
        _cleanup_key(db, data["api_key"]["id"])

    def test_create_api_key_has_warning(self, client, db):
        org, _ = _get_org_project(db)
        resp = client.post("/api/api-keys", json={
            "name": "Test Key Warning",
            "organization_id": str(org.id),
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "warning" in data
        assert "not show it again" in data["warning"]
        _cleanup_key(db, data["api_key"]["id"])

    def test_list_api_keys(self, client, db):
        org, _ = _get_org_project(db)
        # Create a key first
        create_resp = client.post("/api/api-keys", json={
            "name": "Test Key List",
            "organization_id": str(org.id),
        })
        assert create_resp.status_code == 201
        key_id = create_resp.json()["api_key"]["id"]
        try:
            resp = client.get(f"/api/api-keys?organization_id={org.id}")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert "items" in data
            assert "total" in data
            assert data["total"] >= 1
        finally:
            _cleanup_key(db, key_id)

    def test_list_api_keys_no_raw_key(self, client, db):
        org, _ = _get_org_project(db)
        create_resp = client.post("/api/api-keys", json={
            "name": "Test Key No Raw",
            "organization_id": str(org.id),
        })
        assert create_resp.status_code == 201
        key_id = create_resp.json()["api_key"]["id"]
        try:
            resp = client.get(f"/api/api-keys?organization_id={org.id}")
            assert resp.status_code == 200
            data = resp.json()
            for item in data["items"]:
                assert "raw_key" not in item
                assert "key_hash" not in item
        finally:
            _cleanup_key(db, key_id)

    def test_revoke_api_key(self, client, db):
        org, _ = _get_org_project(db)
        create_resp = client.post("/api/api-keys", json={
            "name": "Test Key Revoke",
            "organization_id": str(org.id),
        })
        assert create_resp.status_code == 201
        key_id = create_resp.json()["api_key"]["id"]
        try:
            revoke_resp = client.patch(f"/api/api-keys/{key_id}/revoke")
            assert revoke_resp.status_code == 200, revoke_resp.text
            data = revoke_resp.json()
            assert data["status"] == "revoked"
            assert data["revoked_at"] is not None
        finally:
            _cleanup_key(db, key_id)

    def test_revoked_key_appears_in_list(self, client, db):
        org, _ = _get_org_project(db)
        create_resp = client.post("/api/api-keys", json={
            "name": "Test Key Revoke Visible",
            "organization_id": str(org.id),
        })
        assert create_resp.status_code == 201
        key_id = create_resp.json()["api_key"]["id"]
        try:
            client.patch(f"/api/api-keys/{key_id}/revoke")
            list_resp = client.get(f"/api/api-keys?organization_id={org.id}")
            assert list_resp.status_code == 200
            items = list_resp.json()["items"]
            revoked = [i for i in items if i["id"] == key_id]
            assert len(revoked) == 1
            assert revoked[0]["status"] == "revoked"
        finally:
            _cleanup_key(db, key_id)

    def test_timeline_event_created(self, client, db):
        org, _ = _get_org_project(db)
        create_resp = client.post("/api/api-keys", json={
            "name": "Test Key Timeline",
            "organization_id": str(org.id),
        })
        assert create_resp.status_code == 201
        key_id = create_resp.json()["api_key"]["id"]
        try:
            events = db.query(AuditTimelineEvent).filter(
                AuditTimelineEvent.event_type == EventType.api_key_created,
                AuditTimelineEvent.source_id == key_id,
            ).all()
            assert len(events) >= 1
        finally:
            _cleanup_key(db, key_id)

    def test_revoke_timeline_event(self, client, db):
        org, _ = _get_org_project(db)
        create_resp = client.post("/api/api-keys", json={
            "name": "Test Key Revoke Timeline",
            "organization_id": str(org.id),
        })
        assert create_resp.status_code == 201
        key_id = create_resp.json()["api_key"]["id"]
        try:
            client.patch(f"/api/api-keys/{key_id}/revoke")
            events = db.query(AuditTimelineEvent).filter(
                AuditTimelineEvent.event_type == EventType.api_key_revoked,
                AuditTimelineEvent.source_id == key_id,
            ).all()
            assert len(events) >= 1
        finally:
            _cleanup_key(db, key_id)


# ---------------------------------------------------------------------------
# TestApiKeyAuth
# ---------------------------------------------------------------------------


class TestApiKeyAuth:
    """Tests for the auth dependency on the evidence bundle ingestion endpoint.

    Each test that calls the evidence bundle endpoint creates its own isolated
    strategy and cleans it up afterwards to avoid polluting shared seed data.
    """

    def _create_temp_strategy(self, db):
        """Create a throwaway strategy for auth tests (avoids mutating seed data)."""
        org, project = _get_org_project(db)
        return _make_strategy(db, org, project, name=f"auth-test-{uuid.uuid4().hex[:8]}")

    def _create_key_and_get_raw(self, client, db):
        org, _ = _get_org_project(db)
        resp = client.post("/api/api-keys", json={
            "name": f"Auth Test Key {uuid.uuid4().hex[:6]}",
            "organization_id": str(org.id),
            "scopes": ["evidence:write"],
        })
        assert resp.status_code == 201
        data = resp.json()
        return data["api_key"]["id"], data["raw_key"]

    def test_ingest_no_key_allowed_when_not_required(self, client, db):
        """Without a key, ingestion works when the flag is False (default)."""
        strategy = self._create_temp_strategy(db)
        try:
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=_INGESTION_BUNDLE,
            )
            # 201 or possibly 500 on internal error, but NOT 401
            assert resp.status_code != 401, f"Should not require auth when flag=False, got {resp.status_code}"
        finally:
            _cleanup_strategy(db, strategy)

    def test_ingest_valid_key_via_bearer(self, client, db):
        """Valid Bearer token allows ingestion."""
        strategy = self._create_temp_strategy(db)
        key_id, raw_key = self._create_key_and_get_raw(client, db)
        try:
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=_INGESTION_BUNDLE,
                headers={"Authorization": f"Bearer {raw_key}"},
            )
            assert resp.status_code != 401, f"Valid Bearer key rejected: {resp.text}"
        finally:
            _cleanup_key(db, key_id)
            _cleanup_strategy(db, strategy)

    def test_ingest_valid_key_via_x_header(self, client, db):
        """Valid X-QF-Api-Key header allows ingestion."""
        strategy = self._create_temp_strategy(db)
        key_id, raw_key = self._create_key_and_get_raw(client, db)
        try:
            resp = client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=_INGESTION_BUNDLE,
                headers={"X-QF-Api-Key": raw_key},
            )
            assert resp.status_code != 401, f"Valid X-QF-Api-Key rejected: {resp.text}"
        finally:
            _cleanup_key(db, key_id)
            _cleanup_strategy(db, strategy)

    def test_ingest_invalid_key_rejected_when_required(self, client, db):
        """Invalid key returns 401 when flag=True."""
        from app.core import config as _config_mod
        strategy = self._create_temp_strategy(db)
        try:
            orig_settings = _config_mod.get_settings()
            with patch.object(orig_settings, "require_api_key_for_ingestion", True):
                resp = client.post(
                    f"/api/strategies/{strategy.id}/evidence-bundles",
                    json=_INGESTION_BUNDLE,
                    headers={"Authorization": "Bearer qf_local_invalidkeyvalue"},
                )
                assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        finally:
            _cleanup_strategy(db, strategy)

    def test_ingest_missing_key_rejected_when_required(self, client, db):
        """No key returns 401 when flag=True."""
        from app.core import config as _config_mod
        strategy = self._create_temp_strategy(db)
        try:
            orig_settings = _config_mod.get_settings()
            with patch.object(orig_settings, "require_api_key_for_ingestion", True):
                resp = client.post(
                    f"/api/strategies/{strategy.id}/evidence-bundles",
                    json=_INGESTION_BUNDLE,
                )
                assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        finally:
            _cleanup_strategy(db, strategy)

    def test_ingest_revoked_key_rejected(self, client, db):
        """Revoked key is rejected even if flag=True."""
        from app.core import config as _config_mod
        strategy = self._create_temp_strategy(db)
        key_id, raw_key = self._create_key_and_get_raw(client, db)
        try:
            client.patch(f"/api/api-keys/{key_id}/revoke")
            orig_settings = _config_mod.get_settings()
            with patch.object(orig_settings, "require_api_key_for_ingestion", True):
                resp = client.post(
                    f"/api/strategies/{strategy.id}/evidence-bundles",
                    json=_INGESTION_BUNDLE,
                    headers={"Authorization": f"Bearer {raw_key}"},
                )
                assert resp.status_code == 401, (
                    f"Revoked key should return 401, got {resp.status_code}"
                )
        finally:
            _cleanup_key(db, key_id)
            _cleanup_strategy(db, strategy)

    def test_last_used_at_updated(self, client, db):
        """last_used_at is populated after a valid authenticated request."""
        strategy = self._create_temp_strategy(db)
        key_id, raw_key = self._create_key_and_get_raw(client, db)
        key_uuid = uuid.UUID(key_id)
        try:
            # Verify key exists before use
            key_before = db.query(ApiKey).filter(ApiKey.id == key_uuid).first()
            db.refresh(key_before)

            # Make an authenticated request
            client.post(
                f"/api/strategies/{strategy.id}/evidence-bundles",
                json=_INGESTION_BUNDLE,
                headers={"Authorization": f"Bearer {raw_key}"},
            )

            # Refresh from DB and check last_used_at was updated
            db.expire(key_before)
            key_after = db.query(ApiKey).filter(ApiKey.id == key_uuid).first()
            assert key_after.last_used_at is not None, "last_used_at should be set after use"
        finally:
            _cleanup_key(db, key_id)
            _cleanup_strategy(db, strategy)
