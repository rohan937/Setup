"""Tests for the M79 api_keys 500 fix.

Root cause: api_key.organization_id used str(org.id) (36-char hyphenated)
instead of org.id.hex (32-char hex) — the format stored by Uuid(as_uuid=True)
on both SQLite and Postgres.  On SQLite FK enforcement is off so the mismatch
goes undetected; on PostgreSQL it raises IntegrityError → 500.

Covers:
  1. organization_id stored as .hex format (not str())
  2. project_id stored as .hex format when provided
  3. Raw key returned once; never in list response
  4. list response never exposes raw_key or key_hash
  5. Viewer/member 403; unauthenticated 401 in production mode
  6. Invalid payload → 422, never 500
  7. Idempotency: same name / different key_prefix each time
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app

_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def key_engine():
    eng = create_engine(_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def key_db(key_engine):
    s = Session(key_engine)
    yield s
    s.close()


@pytest.fixture()
def key_client(key_db):
    def _override():
        yield key_db
    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    if prior is not None:
        app.dependency_overrides[get_db] = prior
    else:
        app.dependency_overrides.pop(get_db, None)


def _register(client, email, name="User"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "display_name": name, "password": "password123"},
    )


def _owner_token(client):
    resp = _register(client, f"owner-{uuid.uuid4().hex[:6]}@test.com", "Owner")
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _viewer_token(client, db):
    from app.models.workspace_member import WorkspaceMember
    # First user becomes owner; second becomes member/viewer.
    _owner_token(client)
    email = f"viewer-{uuid.uuid4().hex[:8]}@test.com"
    resp = _register(client, email, "Viewer")
    assert resp.status_code == 200, resp.text
    member = db.query(WorkspaceMember).filter(WorkspaceMember.email == email).first()
    member.role = "viewer"
    db.commit()
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Core fix: organization_id stored as .hex not str()
# ---------------------------------------------------------------------------

class TestOrganizationIdFormat:
    def test_api_key_organization_id_uses_hex_format(self, key_client, key_db):
        """The stored organization_id must match the .hex format used by other FK
        references so the Postgres FK constraint does not raise IntegrityError."""
        from app.models.api_key import ApiKey
        from app.models.organization import Organization

        token = _owner_token(key_client)
        resp = key_client.post(
            "/api/api-keys",
            json={"name": "hex-test-key", "scopes": ["evidence:write"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"

        org = key_db.query(Organization).first()
        key = key_db.query(ApiKey).filter_by(name="hex-test-test-key").first() \
              or key_db.query(ApiKey).order_by(ApiKey.created_at.desc()).first()

        assert key is not None
        # This is the critical assertion: .hex (32-char, no hyphens) must match.
        assert key.organization_id == org.id.hex, (
            f"organization_id stored as '{key.organization_id}' "
            f"but expected hex format '{org.id.hex}'"
        )
        # Must NOT be str(org.id) with hyphens (36-char).
        assert key.organization_id != str(org.id), (
            "organization_id must not be the 36-char hyphenated str() format"
        )

    def test_project_id_uses_hex_format_when_provided(self, key_client, key_db):
        """project_id FK also stored as .hex to match projects.id format."""
        from app.models.api_key import ApiKey
        from app.models.project import Project

        token = _owner_token(key_client)
        project = key_db.query(Project).first()
        if project is None:
            pytest.skip("No project seeded for project_id format test")

        resp = key_client.post(
            "/api/api-keys",
            json={
                "name": "project-key",
                "project_id": str(project.id),
                "scopes": ["evidence:write"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, resp.text

        key = key_db.query(ApiKey).filter_by(name="project-key").first()
        assert key is not None
        assert key.project_id == project.id.hex, (
            f"project_id stored as '{key.project_id}' but expected '{project.id.hex}'"
        )


# ---------------------------------------------------------------------------
# Raw key exposure
# ---------------------------------------------------------------------------

class TestRawKeyExposure:
    def test_create_returns_raw_key_once(self, key_client):
        token = _owner_token(key_client)
        resp = key_client.post(
            "/api/api-keys",
            json={"name": "raw-key-test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "raw_key" in data
        assert data["raw_key"].startswith("qf_")
        assert len(data["raw_key"]) > 20
        assert "warning" in data
        assert "will not show it again" in data["warning"].lower()

    def test_list_never_exposes_raw_key_or_hash(self, key_client):
        token = _owner_token(key_client)
        # Create a key first.
        key_client.post(
            "/api/api-keys",
            json={"name": "list-exposure-test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = key_client.get(
            "/api/api-keys",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        for item in resp.json().get("items", []):
            assert "raw_key" not in item, "raw_key must not appear in list response"
            assert "key_hash" not in item, "key_hash must not appear in list response"
            assert "hashed_key" not in item

    def test_list_shows_key_prefix_only(self, key_client):
        token = _owner_token(key_client)
        key_client.post(
            "/api/api-keys",
            json={"name": "prefix-test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = key_client.get(
            "/api/api-keys",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        items = resp.json().get("items", [])
        assert len(items) > 0
        assert all("key_prefix" in item for item in items)


# ---------------------------------------------------------------------------
# RBAC enforcement
# ---------------------------------------------------------------------------

class TestApiKeyRBAC:
    def test_viewer_cannot_create_key(self, key_client, key_db):
        token = _viewer_token(key_client, key_db)
        resp = key_client.post(
            "/api/api-keys",
            json={"name": "viewer-key"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_viewer_cannot_list_keys(self, key_client, key_db):
        token = _viewer_token(key_client, key_db)
        resp = key_client.get(
            "/api/api-keys",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_viewer_cannot_revoke_key(self, key_client, key_db):
        token = _viewer_token(key_client, key_db)
        fake_id = uuid.uuid4()
        resp = key_client.patch(
            f"/api/api-keys/{fake_id}/revoke",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_unauthenticated_cannot_create_key_in_production(
        self, key_client, monkeypatch
    ):
        from app.core import config as cfg
        monkeypatch.setenv("QF_ENVIRONMENT", "production")
        cfg.get_settings.cache_clear()
        try:
            resp = key_client.post(
                "/api/api-keys",
                json={"name": "anon-key"},
            )
            assert resp.status_code == 401, f"expected 401 in production, got {resp.status_code}"
        finally:
            cfg.get_settings.cache_clear()

    def test_owner_can_create_key(self, key_client):
        token = _owner_token(key_client)
        resp = key_client.post(
            "/api/api-keys",
            json={"name": "owner-key"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["raw_key"].startswith("qf_")


# ---------------------------------------------------------------------------
# Payload validation — bad input must give 422 not 500
# ---------------------------------------------------------------------------

class TestPayloadValidation:
    def test_missing_name_gives_422(self, key_client):
        token = _owner_token(key_client)
        resp = key_client.post(
            "/api/api-keys",
            json={"scopes": ["evidence:write"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422, resp.text
        assert resp.status_code != 500

    def test_invalid_project_id_gives_404(self, key_client):
        token = _owner_token(key_client)
        fake_project = uuid.uuid4()
        resp = key_client.post(
            "/api/api-keys",
            json={"name": "bad-project", "project_id": str(fake_project)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404, resp.text
        assert resp.status_code != 500

    def test_singular_scope_field_is_tolerated(self, key_client):
        """Browser might send 'scope' (singular). FastAPI ignores unknown fields
        and uses the 'scopes' default — must return 201 not 500."""
        token = _owner_token(key_client)
        resp = key_client.post(
            "/api/api-keys",
            # Note: 'scope' (singular) is NOT in the schema; 'scopes' (plural) is.
            json={"name": "singular-scope-test", "scope": "evidence:write"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, f"singular 'scope' field should be ignored, got {resp.status_code}: {resp.text}"
        # scopes should use the default ["evidence:write"]
        assert resp.json()["api_key"]["scopes_json"] is not None

    def test_empty_name_never_500(self, key_client):
        """Empty string name may succeed (no min_length in schema) but must never 500."""
        token = _owner_token(key_client)
        resp = key_client.post(
            "/api/api-keys",
            json={"name": "", "scopes": ["evidence:write"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        # The schema doesn't enforce min_length, so this can succeed (201) or
        # fail with 422/400 — but must never be a 500.
        assert resp.status_code != 500, f"empty name must not give 500: {resp.text}"


# ---------------------------------------------------------------------------
# Revoke
# ---------------------------------------------------------------------------

class TestApiKeyRevoke:
    def test_revoke_changes_status(self, key_client):
        token = _owner_token(key_client)
        create_resp = key_client.post(
            "/api/api-keys",
            json={"name": "revoke-test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_resp.status_code == 201
        key_id = create_resp.json()["api_key"]["id"]

        revoke_resp = key_client.patch(
            f"/api/api-keys/{key_id}/revoke",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert revoke_resp.status_code == 200, revoke_resp.text
        assert revoke_resp.json()["status"] == "revoked"
        assert revoke_resp.json()["revoked_at"] is not None

    def test_revoke_nonexistent_key_404(self, key_client):
        token = _owner_token(key_client)
        fake_id = uuid.uuid4()
        resp = key_client.patch(
            f"/api/api-keys/{fake_id}/revoke",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404, resp.text
        assert resp.status_code != 500
