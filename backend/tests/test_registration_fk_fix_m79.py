"""Tests for the FK format fix that caused POST /api/auth/register → 500 on PostgreSQL.

Root cause (confirmed by Render logs):
  psycopg2 stores uuid.UUID objects in VARCHAR(36) columns via the UUID adapter
  which produces the 36-char hyphenated string (e.g. 747d9ecd-c0a4-4b5c-...).
  The old `_org_id_for_member` used `org.id.hex` (32-char, no hyphens) which
  does NOT match that stored value → FK violation → 500.

SQLite stores the 32-char hex form (Uuid non-native path uses uuid.hex) so the
old code passed locally while failing in production.

The fix: _uuid_to_fk_str() picks the correct format per dialect:
  SQLite    → org.id.hex   (32-char hex)
  Postgres  → str(org.id)  (36-char hyphenated)

All tests run on isolated in-memory SQLite so they exercise the SQLite path.
The logic for the Postgres path is covered by unit-testing _uuid_to_fk_str()
with a mocked is_sqlite=False setting.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app

_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def reg_engine():
    eng = create_engine(_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def reg_db(reg_engine):
    s = Session(reg_engine)
    yield s
    s.close()


@pytest.fixture()
def reg_client(reg_db):
    def _override():
        yield reg_db
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


def _login(client, email):
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
    )


# ---------------------------------------------------------------------------
# _uuid_to_fk_str unit tests (the core fix)
# ---------------------------------------------------------------------------

class TestUuidToFkStr:
    def test_sqlite_returns_hex_format(self, monkeypatch):
        """On SQLite, return 32-char hex (no hyphens) to match Uuid storage."""
        from app.core import config as cfg
        from app.services.auth_users import _uuid_to_fk_str

        # Ensure is_sqlite = True
        monkeypatch.setenv("QF_DATABASE_URL", "sqlite:///./quantfidelity.db")
        cfg.get_settings.cache_clear()
        try:
            u = uuid.UUID("747d9ecd-c0a4-4b5c-9b50-98fcf5c46dc5")
            result = _uuid_to_fk_str(u)
            assert result == "747d9ecdc0a44b5c9b5098fcf5c46dc5"
            assert len(result) == 32
            assert "-" not in result
        finally:
            cfg.get_settings.cache_clear()

    def test_postgres_returns_hyphenated_format(self, monkeypatch):
        """On PostgreSQL, return 36-char hyphenated UUID to match psycopg2 storage."""
        from app.core import config as cfg
        from app.services.auth_users import _uuid_to_fk_str

        # Ensure is_sqlite = False (simulate PostgreSQL)
        monkeypatch.setenv("QF_DATABASE_URL", "postgresql://user:pass@host/db")
        cfg.get_settings.cache_clear()
        try:
            u = uuid.UUID("747d9ecd-c0a4-4b5c-9b50-98fcf5c46dc5")
            result = _uuid_to_fk_str(u)
            assert result == "747d9ecd-c0a4-4b5c-9b50-98fcf5c46dc5"
            assert len(result) == 36
            assert "-" in result
        finally:
            cfg.get_settings.cache_clear()

    def test_postgres_fk_would_match_stored_value(self, monkeypatch):
        """Confirm the fixed format matches what PostgreSQL stores in VARCHAR(36)."""
        from app.core import config as cfg
        from app.services.auth_users import _uuid_to_fk_str

        monkeypatch.setenv("QF_DATABASE_URL", "postgresql://user:pass@host/db")
        cfg.get_settings.cache_clear()
        try:
            u = uuid.UUID("747d9ecd-c0a4-4b5c-9b50-98fcf5c46dc5")
            # Simulate: PostgreSQL stores via psycopg2 UUID adapter = str(uuid)
            postgres_stored_org_id = str(u)  # "747d9ecd-c0a4-4b5c-9b50-98fcf5c46dc5"
            fk_value = _uuid_to_fk_str(u)
            assert fk_value == postgres_stored_org_id, (
                "workspace_member.organization_id must exactly equal "
                "organizations.id as stored in PostgreSQL"
            )
        finally:
            cfg.get_settings.cache_clear()

    def test_old_hex_would_fail_fk_on_postgres(self, monkeypatch):
        """Demonstrate that the old org.id.hex approach FAILS the FK on PostgreSQL."""
        u = uuid.UUID("747d9ecd-c0a4-4b5c-9b50-98fcf5c46dc5")
        postgres_stored_org_id = str(u)  # "747d9ecd-..." (36-char)
        old_broken_fk = u.hex              # "747d9ecd..." (32-char)
        assert postgres_stored_org_id != old_broken_fk, (
            "Sanity check: str(uuid) and uuid.hex must differ so we can "
            "verify the fix chose the right one"
        )


# ---------------------------------------------------------------------------
# Registration integration tests
# ---------------------------------------------------------------------------

class TestRegistrationCreatesOrgAndMember:
    def test_first_user_registration_returns_200(self, reg_client):
        resp = _register(reg_client, "first@test.com")
        assert resp.status_code == 200, resp.text
        assert "access_token" in resp.json()

    def test_first_user_gets_owner_role(self, reg_client, reg_db):
        from app.models.workspace_member import WorkspaceMember
        _register(reg_client, "owner@test.com")
        member = reg_db.query(WorkspaceMember).filter_by(email="owner@test.com").first()
        assert member is not None
        assert member.role == "owner"
        assert member.status == "active"

    def test_organization_created_for_first_user(self, reg_client, reg_db):
        from app.models.organization import Organization
        _register(reg_client, "first@test.com")
        org = reg_db.query(Organization).first()
        assert org is not None
        assert org.name == "Quant Research Workspace"

    def test_workspace_member_org_id_exactly_matches_organizations_id(
        self, reg_client, reg_db, reg_engine
    ):
        """Critical: workspace_members.organization_id must byte-exactly equal
        the value stored in organizations.id. A format mismatch is the root
        cause of the production FK violation (works on SQLite but fails on
        PostgreSQL because the two dialects store UUIDs in different formats)."""
        _register(reg_client, "fk@test.com")

        # Read the raw stored value of organizations.id (bypass ORM type conversion).
        raw_org_id = reg_engine.connect().execute(
            text("SELECT id FROM organizations LIMIT 1")
        ).scalar()

        from app.models.workspace_member import WorkspaceMember
        member = reg_db.query(WorkspaceMember).filter_by(email="fk@test.com").first()

        assert member.organization_id == raw_org_id, (
            f"workspace_member.organization_id={member.organization_id!r} "
            f"does not match organizations.id={raw_org_id!r} — "
            f"this would cause a FK violation on PostgreSQL"
        )

    def test_second_user_registration_does_not_crash(self, reg_client):
        _register(reg_client, "first@test.com")
        resp = _register(reg_client, "second@test.com")
        assert resp.status_code == 200, resp.text

    def test_second_user_gets_member_role(self, reg_client, reg_db):
        from app.models.workspace_member import WorkspaceMember
        _register(reg_client, "first@test.com")
        _register(reg_client, "second@test.com")
        member = reg_db.query(WorkspaceMember).filter_by(email="second@test.com").first()
        assert member is not None
        assert member.role == "member"

    def test_login_works_after_registration(self, reg_client):
        _register(reg_client, "login@test.com")
        resp = _login(reg_client, "login@test.com")
        assert resp.status_code == 200, resp.text
        assert "access_token" in resp.json()

    def test_me_returns_owner_role_and_workspace_name(self, reg_client):
        token = _register(reg_client, "me@test.com").json()["access_token"]
        data = reg_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        ).json()
        assert data["role"] == "owner"
        assert data["workspace_memberships"][0]["workspace_name"] == "Quant Research Workspace"
        assert data["workspace_memberships"][0]["workspace_name"] != "Unknown"

    def test_duplicate_email_registration_409(self, reg_client):
        _register(reg_client, "dup@test.com")
        resp = _register(reg_client, "dup@test.com")
        assert resp.status_code == 409, resp.text
        # Must not be 500 — duplicate check should happen before any DB write
        assert resp.status_code != 500

    def test_short_password_registration_422(self, reg_client):
        resp = reg_client.post(
            "/api/auth/register",
            json={"email": "pw@test.com", "display_name": "Test", "password": "short"},
        )
        assert resp.status_code == 422, resp.text
        assert resp.status_code != 500

    def test_no_orphaned_user_on_member_creation_failure(self, reg_db):
        """If workspace_member creation fails, the auth_user should also be
        rolled back so no orphaned users accumulate in the DB."""
        from app.models.auth_user import AuthUser
        from app.services.auth_users import register_user

        pre_count = reg_db.query(AuthUser).count()

        # Simulate FK failure by patching _link_or_create_member to raise
        import app.services.auth_users as aus
        original = aus._link_or_create_member

        def _raise(db, user):
            raise RuntimeError("simulated FK failure")

        aus._link_or_create_member = _raise
        try:
            try:
                register_user(reg_db, "orphan@test.com", "Orphan", "password123")
                reg_db.commit()
            except Exception:
                reg_db.rollback()
        finally:
            aus._link_or_create_member = original

        post_count = reg_db.query(AuthUser).count()
        assert post_count == pre_count, (
            "A failed registration must not leave orphaned auth_user rows"
        )


# ---------------------------------------------------------------------------
# No-duplicate-org guard
# ---------------------------------------------------------------------------

class TestNoDuplicateOrg:
    def test_two_registrations_create_only_one_org(self, reg_client, reg_db):
        from app.models.organization import Organization
        _register(reg_client, "first@test.com")
        _register(reg_client, "second@test.com")
        count = reg_db.query(Organization).count()
        assert count == 1, f"Expected 1 org, got {count}"
