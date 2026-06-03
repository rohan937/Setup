"""M68 tests: Auth + User Accounts.

Tests for:
  POST /api/auth/register  — register new user, duplicate, short password
  POST /api/auth/login     — login success, wrong password, unknown email
  GET  /api/auth/me        — protected, returns user + memberships
  POST /api/auth/logout    — stateless, always succeeds
  GET  /api/auth/status    — auth config + has_users flag
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registers all ORM metadata
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.auth_user import AuthUser
from app.models.organization import Organization
from app.models.workspace_member import WorkspaceMember

# ---------------------------------------------------------------------------
# Isolated in-memory DB + client fixtures (function-scoped for isolation)
# ---------------------------------------------------------------------------

_AUTH_DB_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def auth_engine():
    engine = create_engine(
        _AUTH_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def auth_db(auth_engine):
    session = Session(auth_engine)
    yield session
    session.close()


@pytest.fixture()
def organization(auth_db):
    """Seed a single organization so _link_or_create_member finds one."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    org = Organization(
        # Organization.id uses Uuid(as_uuid=True) — pass a uuid.UUID object
        name="Test Workspace",
        slug="test-workspace",
        created_at=now,
        updated_at=now,
    )
    auth_db.add(org)
    auth_db.commit()
    auth_db.refresh(org)
    yield org


@pytest.fixture()
def api_client(auth_db, organization):  # noqa: ARG001 — org must exist
    """FastAPI TestClient wired to the isolated auth_db."""

    def _override():
        yield auth_db

    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register(client: TestClient, email: str, password: str = "password123",
               display_name: str = "Test User") -> dict:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "display_name": display_name, "password": password},
    )
    return resp


def _login(client: TestClient, email: str, password: str = "password123") -> dict:
    resp = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    return resp


# ---------------------------------------------------------------------------
# TestUserRegistration
# ---------------------------------------------------------------------------

class TestUserRegistration:
    def test_register_success(self, api_client):
        resp = _register(api_client, f"user-{uuid.uuid4().hex[:8]}@test.com")
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
        assert data["user"]["email"].endswith("@test.com")
        assert data["user"]["status"] == "active"

    def test_register_duplicate_email_409(self, api_client):
        email = f"dup-{uuid.uuid4().hex[:8]}@test.com"
        r1 = _register(api_client, email)
        assert r1.status_code == 200
        r2 = _register(api_client, email)
        assert r2.status_code == 409

    def test_register_password_too_short(self, api_client):
        resp = _register(
            api_client,
            f"short-{uuid.uuid4().hex[:8]}@test.com",
            password="short",
        )
        assert resp.status_code in (400, 422)

    def test_register_first_user_becomes_owner(self, api_client, auth_db):
        email = f"owner-{uuid.uuid4().hex[:8]}@test.com"
        r = _register(api_client, email)
        assert r.status_code == 200
        member = (
            auth_db.query(WorkspaceMember)
            .filter(WorkspaceMember.email == email)
            .first()
        )
        assert member is not None
        assert member.role == "owner"

    def test_register_second_user_becomes_member(self, api_client, auth_db):
        email1 = f"first-{uuid.uuid4().hex[:8]}@test.com"
        email2 = f"second-{uuid.uuid4().hex[:8]}@test.com"
        r1 = _register(api_client, email1)
        assert r1.status_code == 200
        r2 = _register(api_client, email2)
        assert r2.status_code == 200
        member2 = (
            auth_db.query(WorkspaceMember)
            .filter(WorkspaceMember.email == email2)
            .first()
        )
        assert member2 is not None
        assert member2.role == "member"

    def test_register_password_not_stored_plain(self, api_client, auth_db):
        plain = "my-secret-password"
        email = f"plain-{uuid.uuid4().hex[:8]}@test.com"
        r = _register(api_client, email, password=plain)
        assert r.status_code == 200
        auth_db.expire_all()
        user = (
            auth_db.query(AuthUser).filter(AuthUser.email == email).first()
        )
        assert user is not None
        assert user.hashed_password != plain
        assert ":" in user.hashed_password  # pbkdf2 format: salt:hash

    def test_register_links_existing_member(self, api_client, auth_db, organization):
        from datetime import datetime, timezone

        email = f"link-{uuid.uuid4().hex[:8]}@test.com"
        now = datetime.now(timezone.utc)
        # Pre-create workspace member with same email (no user_id yet).
        # WorkspaceMember.id uses UUIDPrimaryKeyMixin (Uuid as_uuid=True) — let it default.
        pre_member = WorkspaceMember(
            organization_id=str(organization.id),
            display_name="Pre-existing Member",
            email=email,
            role="admin",
            status="active",
            user_id=None,
            created_at=now,
            updated_at=now,
        )
        auth_db.add(pre_member)
        auth_db.commit()

        r = _register(api_client, email)
        assert r.status_code == 200
        auth_db.expire_all()
        member = (
            auth_db.query(WorkspaceMember)
            .filter(WorkspaceMember.email == email)
            .first()
        )
        assert member is not None
        assert member.user_id is not None
        user = auth_db.query(AuthUser).filter(AuthUser.email == email).first()
        assert str(member.user_id) == str(user.id)


# ---------------------------------------------------------------------------
# TestUserLogin
# ---------------------------------------------------------------------------

class TestUserLogin:
    def test_login_success(self, api_client):
        email = f"login-ok-{uuid.uuid4().hex[:8]}@test.com"
        _register(api_client, email)
        resp = _login(api_client, email)
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["email"] == email

    def test_login_wrong_password_401(self, api_client):
        email = f"login-bad-{uuid.uuid4().hex[:8]}@test.com"
        _register(api_client, email)
        resp = _login(api_client, email, password="wrongpassword")
        assert resp.status_code == 401

    def test_login_unknown_email_401(self, api_client):
        resp = _login(api_client, f"nobody-{uuid.uuid4().hex[:8]}@test.com")
        assert resp.status_code == 401

    def test_login_updates_last_login_at(self, api_client, auth_db):
        email = f"last-login-{uuid.uuid4().hex[:8]}@test.com"
        _register(api_client, email)

        # last_login_at should be None before first login (register doesn't log in)
        auth_db.expire_all()
        user_before = auth_db.query(AuthUser).filter(AuthUser.email == email).first()
        # (last_login_at may or may not be set after register — login sets it)

        _login(api_client, email)
        auth_db.expire_all()
        user_after = auth_db.query(AuthUser).filter(AuthUser.email == email).first()
        assert user_after is not None
        assert user_after.last_login_at is not None


# ---------------------------------------------------------------------------
# TestCurrentUser
# ---------------------------------------------------------------------------

class TestCurrentUser:
    def _get_token(self, client: TestClient) -> str:
        email = f"me-{uuid.uuid4().hex[:8]}@test.com"
        r = _register(client, email)
        assert r.status_code == 200
        return r.json()["access_token"]

    def test_me_with_valid_token(self, api_client):
        token = self._get_token(api_client)
        resp = api_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "user" in data
        assert "workspace_memberships" in data

    def test_me_without_token_401(self, api_client):
        resp = api_client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_invalid_token_401(self, api_client):
        resp = api_client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )
        assert resp.status_code == 401

    def test_me_includes_workspace_memberships(self, api_client):
        token = self._get_token(api_client)
        resp = api_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # First user auto-creates a workspace member entry
        assert len(data["workspace_memberships"]) >= 1
        m = data["workspace_memberships"][0]
        assert "member_id" in m
        assert "role" in m
        assert m["linked"] is True


# ---------------------------------------------------------------------------
# TestAuthHelpers
# ---------------------------------------------------------------------------

class TestAuthHelpers:
    def test_logout_returns_success(self, api_client):
        resp = api_client.post("/api/auth/logout")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_auth_status_no_users(self, api_client):
        resp = api_client.get("/api/auth/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_users"] is False
        assert "auth_enabled" in data
        assert "registration_enabled" in data

    def test_auth_status_after_register(self, api_client):
        _register(api_client, f"status-{uuid.uuid4().hex[:8]}@test.com")
        resp = api_client.get("/api/auth/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_users"] is True
