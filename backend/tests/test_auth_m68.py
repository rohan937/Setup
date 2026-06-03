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
        # organization_id must use .hex (32-char) — the format SQLAlchemy 2.0 stores
        # Uuid(as_uuid=True) columns as on SQLite, which _link_or_create_member now
        # also uses to avoid FK constraint failures.
        pre_member = WorkspaceMember(
            organization_id=organization.id.hex,
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


# ---------------------------------------------------------------------------
# TestRegistrationFKFix — regression for M68/M71 FK bug
# ---------------------------------------------------------------------------
# Root cause: organizations.id in the real quantfidelity.db was stored as
# 32-char hex (no hyphens) by the legacy seed, but _link_or_create_member used
# str(org.id) which returns 36-char hyphenated format.  SQLite's FK check is a
# byte-exact string comparison, so the formats don't match → FOREIGN KEY
# constraint failed.
#
# This test reproduces the exact failure mode by:
# 1. Enabling PRAGMA foreign_keys=ON on the test engine (mimics production).
# 2. Storing the organization ID as 32-char hex (mimics the legacy seeded DB).
# 3. Attempting registration — must succeed, not raise IntegrityError.
# ---------------------------------------------------------------------------

from sqlalchemy import event as sa_event, text as sa_text


@pytest.fixture()
def fk_engine():
    """In-memory SQLite with FK enforcement ON — mimics production DB."""
    engine = create_engine(
        _AUTH_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    def _enable_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    sa_event.listen(engine, "connect", _enable_fk)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def fk_db(fk_engine):
    session = Session(fk_engine)
    yield session
    session.close()


@pytest.fixture()
def fk_org_32char(fk_db):
    """Seed an organization whose id is stored as 32-char hex (no hyphens).

    This reproduces the legacy quantfidelity.db format that triggered the FK
    failure in production.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    org_uuid = uuid.uuid4()
    # Insert via raw SQL so the id is stored as 32-char hex — exactly as the
    # legacy Alembic seed stored it.
    fk_db.execute(
        sa_text(
            "INSERT INTO organizations (id, name, slug, created_at, updated_at) "
            "VALUES (:id, :name, :slug, :cat, :uat)"
        ),
        {
            "id": org_uuid.hex,  # 32-char hex, no hyphens
            "name": "FK Test Org",
            "slug": f"fk-test-{org_uuid.hex[:6]}",
            "cat": now,
            "uat": now,
        },
    )
    fk_db.commit()
    return org_uuid


@pytest.fixture()
def fk_client(fk_db, fk_org_32char):  # noqa: ARG001 — org must exist
    def _override():
        yield fk_db

    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


class TestRegistrationFKFix:
    """Regression tests for the FOREIGN KEY constraint failure on registration.

    Previously, _link_or_create_member used str(org.id) (36-char hyphenated)
    when the real DB stored organizations.id as 32-char hex.  SQLite's FK check
    then failed with IntegrityError: FOREIGN KEY constraint failed.
    """

    def test_register_succeeds_with_32char_org_id(self, fk_client):
        """Registration must succeed even when org ID is stored as 32-char hex."""
        email = f"fkfix-{uuid.uuid4().hex[:8]}@test.com"
        resp = fk_client.post(
            "/api/auth/register",
            json={"email": email, "display_name": "FK Fix User", "password": "password123"},
        )
        assert resp.status_code == 200, (
            f"Registration failed — likely FK mismatch: {resp.text}"
        )
        data = resp.json()
        assert "access_token" in data

    def test_registered_user_has_workspace_member(self, fk_client, fk_db):
        """After registration, the user must have a linked WorkspaceMember row."""
        email = f"fkfix2-{uuid.uuid4().hex[:8]}@test.com"
        resp = fk_client.post(
            "/api/auth/register",
            json={"email": email, "display_name": "FK Fix 2", "password": "password123"},
        )
        assert resp.status_code == 200, resp.text
        fk_db.expire_all()
        member = (
            fk_db.query(WorkspaceMember)
            .filter(WorkspaceMember.email == email)
            .first()
        )
        assert member is not None, "WorkspaceMember must be created on registration"
        assert member.user_id is not None, "WorkspaceMember must be linked to the AuthUser"

    def test_first_user_is_owner_with_32char_org(self, fk_client, fk_db):
        """First registered user must get owner role even with 32-char org ID."""
        email = f"fkowner-{uuid.uuid4().hex[:8]}@test.com"
        resp = fk_client.post(
            "/api/auth/register",
            json={"email": email, "display_name": "FK Owner", "password": "password123"},
        )
        assert resp.status_code == 200, resp.text
        fk_db.expire_all()
        member = (
            fk_db.query(WorkspaceMember)
            .filter(WorkspaceMember.email == email)
            .first()
        )
        assert member is not None
        assert member.role == "owner", f"Expected owner, got {member.role}"

    def test_workspace_member_org_id_matches_stored_org_id(self, fk_client, fk_db, fk_org_32char):
        """The workspace_members.organization_id must exactly match organizations.id."""
        email = f"fkmatch-{uuid.uuid4().hex[:8]}@test.com"
        resp = fk_client.post(
            "/api/auth/register",
            json={"email": email, "display_name": "FK Match", "password": "password123"},
        )
        assert resp.status_code == 200, resp.text
        fk_db.expire_all()

        # Get the actual stored org ID (32-char hex)
        row = fk_db.execute(sa_text("SELECT id FROM organizations LIMIT 1")).fetchone()
        stored_org_id = row[0]

        member = (
            fk_db.query(WorkspaceMember)
            .filter(WorkspaceMember.email == email)
            .first()
        )
        assert member is not None
        assert member.organization_id == stored_org_id, (
            f"organization_id mismatch: member has {member.organization_id!r} "
            f"but organizations.id is {stored_org_id!r}"
        )
