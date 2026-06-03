"""M69 tests: RBAC + Workspace/Project Access Control.

Verifies role enforcement on workspace, member, API key, admin, and
representative research-write endpoints. Uses an isolated in-memory DB
(function-scoped) with its own organization + project, registers users via the
auth flow, and assigns roles directly on the linked WorkspaceMember.

Permissive local-dev behaviour (no bearer token) and the RBAC-disabled flag are
exercised explicitly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registers all ORM metadata
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.project import Project
from app.models.workspace_member import WorkspaceMember

_DB_URL = "sqlite+pysqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures — isolated DB + org + project
# ---------------------------------------------------------------------------


@pytest.fixture()
def rbac_engine():
    engine = create_engine(
        _DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def rbac_db(rbac_engine):
    session = Session(rbac_engine)
    yield session
    session.close()


@pytest.fixture()
def org_and_project(rbac_db):
    now = datetime.now(timezone.utc)
    org = Organization(name="RBAC Workspace", slug="rbac-ws", created_at=now, updated_at=now)
    rbac_db.add(org)
    rbac_db.commit()
    rbac_db.refresh(org)
    project = Project(
        organization_id=org.id,
        name="RBAC Project",
        slug="rbac-project",
        created_at=now,
        updated_at=now,
    )
    rbac_db.add(project)
    rbac_db.commit()
    rbac_db.refresh(project)
    return org, project


@pytest.fixture()
def client(rbac_db, org_and_project):  # noqa: ARG001 — org/project must exist
    def _override():
        yield rbac_db

    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient, email: str, password: str = "password123") -> str:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "display_name": email.split("@")[0], "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _set_role(db: Session, email: str, role: str) -> None:
    member = db.query(WorkspaceMember).filter(WorkspaceMember.email == email).first()
    assert member is not None, f"no member for {email}"
    member.role = role
    db.commit()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_user(client: TestClient, db: Session, role: str) -> str:
    """Register a fresh user, force their membership role, return a token."""
    email = f"{role}-{uuid.uuid4().hex[:8]}@test.com"
    token = _register(client, email)
    _set_role(db, email, role)
    return token


# ---------------------------------------------------------------------------
# Workspace settings
# ---------------------------------------------------------------------------


class TestWorkspaceSettingsRBAC:
    def test_owner_can_update_settings(self, client, rbac_db):
        # First registered user becomes owner automatically.
        token = _make_user(client, rbac_db, "owner")
        resp = client.patch(
            "/api/workspace/settings", json={"display_name": "Owned"}, headers=_auth(token)
        )
        assert resp.status_code == 200, resp.text

    def test_member_cannot_update_settings(self, client, rbac_db):
        token = _make_user(client, rbac_db, "member")
        resp = client.patch(
            "/api/workspace/settings", json={"display_name": "Nope"}, headers=_auth(token)
        )
        assert resp.status_code == 403, resp.text

    def test_viewer_cannot_update_settings(self, client, rbac_db):
        token = _make_user(client, rbac_db, "viewer")
        resp = client.patch(
            "/api/workspace/settings", json={"display_name": "Nope"}, headers=_auth(token)
        )
        assert resp.status_code == 403, resp.text

    def test_viewer_can_read_settings(self, client, rbac_db):
        token = _make_user(client, rbac_db, "viewer")
        resp = client.get("/api/workspace/settings", headers=_auth(token))
        assert resp.status_code == 200, resp.text

    def test_viewer_can_read_members(self, client, rbac_db):
        token = _make_user(client, rbac_db, "viewer")
        resp = client.get("/api/workspace/members", headers=_auth(token))
        assert resp.status_code == 200, resp.text

    def test_no_token_is_permissive_local_dev(self, client, rbac_db):
        # No bearer token -> local-dev pseudo-owner -> allowed.
        resp = client.patch("/api/workspace/settings", json={"display_name": "Local"})
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------


class TestMemberManagementRBAC:
    def _create_payload(self) -> dict:
        return {
            "display_name": "New Person",
            "email": f"new-{uuid.uuid4().hex[:8]}@test.com",
            "role": "member",
            "status": "active",
        }

    def test_owner_can_create_member(self, client, rbac_db):
        token = _make_user(client, rbac_db, "owner")
        resp = client.post(
            "/api/workspace/members", json=self._create_payload(), headers=_auth(token)
        )
        assert resp.status_code == 201, resp.text

    def test_admin_can_create_member(self, client, rbac_db):
        token = _make_user(client, rbac_db, "admin")
        resp = client.post(
            "/api/workspace/members", json=self._create_payload(), headers=_auth(token)
        )
        assert resp.status_code == 201, resp.text

    def test_member_cannot_create_member(self, client, rbac_db):
        token = _make_user(client, rbac_db, "member")
        resp = client.post(
            "/api/workspace/members", json=self._create_payload(), headers=_auth(token)
        )
        assert resp.status_code == 403, resp.text

    def test_viewer_cannot_create_member(self, client, rbac_db):
        token = _make_user(client, rbac_db, "viewer")
        resp = client.post(
            "/api/workspace/members", json=self._create_payload(), headers=_auth(token)
        )
        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


class TestApiKeyRBAC:
    def _payload(self, org) -> dict:
        return {"name": f"key-{uuid.uuid4().hex[:6]}", "organization_id": str(org.id)}

    def test_owner_can_create_api_key(self, client, rbac_db, org_and_project):
        org, _ = org_and_project
        token = _make_user(client, rbac_db, "owner")
        resp = client.post("/api/api-keys", json=self._payload(org), headers=_auth(token))
        assert resp.status_code == 201, resp.text

    def test_admin_can_create_api_key(self, client, rbac_db, org_and_project):
        org, _ = org_and_project
        token = _make_user(client, rbac_db, "admin")
        resp = client.post("/api/api-keys", json=self._payload(org), headers=_auth(token))
        assert resp.status_code == 201, resp.text

    def test_member_cannot_create_api_key(self, client, rbac_db, org_and_project):
        org, _ = org_and_project
        token = _make_user(client, rbac_db, "member")
        resp = client.post("/api/api-keys", json=self._payload(org), headers=_auth(token))
        assert resp.status_code == 403, resp.text

    def test_viewer_cannot_create_api_key(self, client, rbac_db, org_and_project):
        org, _ = org_and_project
        token = _make_user(client, rbac_db, "viewer")
        resp = client.post("/api/api-keys", json=self._payload(org), headers=_auth(token))
        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


class TestAdminRBAC:
    def test_owner_can_access_system_health(self, client, rbac_db):
        token = _make_user(client, rbac_db, "owner")
        resp = client.get("/api/admin/system-health", headers=_auth(token))
        assert resp.status_code == 200, resp.text

    def test_admin_can_access_system_health(self, client, rbac_db):
        token = _make_user(client, rbac_db, "admin")
        resp = client.get("/api/admin/system-health", headers=_auth(token))
        assert resp.status_code == 200, resp.text

    def test_member_cannot_access_system_health(self, client, rbac_db):
        token = _make_user(client, rbac_db, "member")
        resp = client.get("/api/admin/system-health", headers=_auth(token))
        assert resp.status_code == 403, resp.text

    def test_viewer_cannot_access_system_health(self, client, rbac_db):
        token = _make_user(client, rbac_db, "viewer")
        resp = client.get("/api/admin/system-health", headers=_auth(token))
        assert resp.status_code == 403, resp.text

    def test_member_cannot_seed_demo(self, client, rbac_db):
        token = _make_user(client, rbac_db, "member")
        resp = client.post(
            "/api/admin/seed-demo", json={"mode": "extend"}, headers=_auth(token)
        )
        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Research write endpoints
# ---------------------------------------------------------------------------


class TestResearchWriteRBAC:
    def _strategy_payload(self, project) -> dict:
        return {
            "project_id": str(project.id),
            "name": f"Strat {uuid.uuid4().hex[:6]}",
            "asset_class": "equity",
            "status": "active",
        }

    def test_member_can_create_strategy(self, client, rbac_db, org_and_project):
        _, project = org_and_project
        token = _make_user(client, rbac_db, "member")
        resp = client.post(
            "/api/strategies", json=self._strategy_payload(project), headers=_auth(token)
        )
        assert resp.status_code == 201, resp.text

    def test_viewer_cannot_create_strategy(self, client, rbac_db, org_and_project):
        _, project = org_and_project
        token = _make_user(client, rbac_db, "viewer")
        resp = client.post(
            "/api/strategies", json=self._strategy_payload(project), headers=_auth(token)
        )
        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# No-membership + /auth/me + RBAC flag
# ---------------------------------------------------------------------------


class TestRBACEdgeCases:
    def test_user_without_membership_gets_403(self, client, rbac_db):
        # Register a (first) user, then remove their membership entirely.
        email = f"orphan-{uuid.uuid4().hex[:8]}@test.com"
        token = _register(client, email)
        member = (
            rbac_db.query(WorkspaceMember)
            .filter(WorkspaceMember.email == email)
            .first()
        )
        assert member is not None
        rbac_db.delete(member)
        rbac_db.commit()

        resp = client.patch(
            "/api/workspace/settings", json={"display_name": "x"}, headers=_auth(token)
        )
        assert resp.status_code == 403, resp.text

    def test_me_returns_permissions(self, client, rbac_db):
        token = _make_user(client, rbac_db, "owner")
        resp = client.get("/api/auth/me", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["role"] == "owner"
        assert data["organization_id"] is not None
        perms = data["permissions"]
        assert perms["can_manage_workspace"] is True
        assert perms["can_manage_members"] is True
        assert perms["can_manage_api_keys"] is True
        assert perms["can_seed_demo"] is True
        assert perms["can_write_research"] is True
        assert perms["can_read_research"] is True

    def test_me_viewer_permissions_are_readonly(self, client, rbac_db):
        token = _make_user(client, rbac_db, "viewer")
        resp = client.get("/api/auth/me", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        perms = resp.json()["permissions"]
        assert perms["can_read_research"] is True
        assert perms["can_write_research"] is False
        assert perms["can_manage_workspace"] is False
        assert perms["can_manage_members"] is False
        assert perms["can_manage_api_keys"] is False
        assert perms["can_seed_demo"] is False

    def test_rbac_disabled_flag_permits_viewer(self, client, rbac_db):
        from unittest.mock import patch

        token = _make_user(client, rbac_db, "viewer")
        settings = get_settings()
        with patch.object(settings, "QF_RBAC_ENABLED", False):
            resp = client.patch(
                "/api/workspace/settings",
                json={"display_name": "FlagOff"},
                headers=_auth(token),
            )
            assert resp.status_code == 200, resp.text
