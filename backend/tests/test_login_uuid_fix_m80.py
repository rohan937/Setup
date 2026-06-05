"""Tests for the login 500 caused by an auth_users.id UUID/VARCHAR mismatch.

Root cause (confirmed by Render logs):
  ``auth_users.id`` is created by migration 0025 as ``sa.String(36)`` (VARCHAR
  on PostgreSQL), but the ORM declared the column as
  ``sqlalchemy.types.Uuid(as_uuid=True)``.  On PostgreSQL that type casts every
  bind parameter to the native UUID type, so login emitted::

      UPDATE auth_users SET last_login_at=..., updated_at=...
      WHERE auth_users.id = %(id)s::UUID

  Comparing ``character varying = uuid`` has no operator in PostgreSQL →
  ``operator does not exist: character varying = uuid`` → HTTP 500.  It worked
  on SQLite (no native UUID type) which is why it passed locally.

The fix: a ``GUID`` TypeDecorator (``app.models.base.GUID``) that renders as
``String(36)`` on every dialect — never emitting a ``::UUID`` cast — while
preserving the exact per-dialect storage format the old ``Uuid`` type wrote
(``uuid.hex`` on SQLite, ``str(uuid)`` on PostgreSQL) so existing data keeps
matching.  ``UUIDPrimaryKeyMixin`` and every FK column now use ``GUID``.

These integration tests run on in-memory SQLite.  The PostgreSQL-specific
behaviour (no ``::UUID`` cast) is verified by compiling statements against the
``postgresql`` dialect and asserting the cast is absent.

Fixtures are prefixed ``lf_`` to avoid colliding with the session-scoped
``seed_data(db)`` fixture chain in conftest.py.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register all mappers)
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.auth_user import AuthUser

_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def lf_engine():
    eng = create_engine(_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def lf_db(lf_engine):
    s = Session(lf_engine)
    yield s
    s.close()


@pytest.fixture()
def lf_client(lf_db):
    def _override():
        yield lf_db

    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    if prior is not None:
        app.dependency_overrides[get_db] = prior
    else:
        app.dependency_overrides.pop(get_db, None)


def _register(client, email, password="password123", name="User"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "display_name": name, "password": password},
    )


def _login(client, email, password="password123"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ---------------------------------------------------------------------------
# 1. No ::UUID cast is emitted on PostgreSQL (the exact production failure)
# ---------------------------------------------------------------------------

class TestNoUuidCastOnPostgres:
    def test_login_update_emits_no_uuid_cast(self):
        """The exact failing query — UPDATE auth_users WHERE id = ... — must not
        cast the bind parameter to ::UUID on PostgreSQL."""
        u = uuid.UUID("dc8c94a8-0c0f-449d-87f7-30c87f9db9f8")
        stmt = update(AuthUser).where(AuthUser.id == u).values(status="active")
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "::UUID" not in sql, sql
        assert "CAST" not in sql.upper(), sql

    def test_select_by_id_emits_no_uuid_cast(self):
        """/api/auth/me looks up the user by id — must not cast either."""
        u = uuid.uuid4()
        stmt = select(AuthUser).where(AuthUser.id == u)
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "::UUID" not in sql, sql

    def test_select_by_string_id_emits_no_uuid_cast(self):
        """A string subject (as decoded from a JWT) must also avoid the cast."""
        stmt = select(AuthUser).where(
            AuthUser.id == "dc8c94a8-0c0f-449d-87f7-30c87f9db9f8"
        )
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "::UUID" not in sql, sql


# ---------------------------------------------------------------------------
# 2. ORM column type matches the migration (String/VARCHAR, not native UUID)
# ---------------------------------------------------------------------------

class TestOrmTypeMatchesMigration:
    def test_auth_user_id_is_guid_backed_by_string(self):
        from app.models.base import GUID

        col = AuthUser.__table__.c.id
        assert isinstance(col.type, GUID), type(col.type)
        # GUID renders as VARCHAR on PostgreSQL (matches migration String(36)).
        assert "VARCHAR" in col.type.compile(dialect=postgresql.dialect()).upper()

    def test_migration_0025_creates_auth_users_id_as_string(self):
        import pathlib

        mig = pathlib.Path(__file__).resolve().parents[1] / (
            "migrations/versions/0025_m68_users.py"
        )
        src = mig.read_text()
        assert "'auth_users'" in src
        # The id column is VARCHAR(36), so the ORM must not be native UUID.
        assert "sa.Column('id', sa.String(36)" in src

    def test_workspace_members_user_id_is_string36(self):
        from app.models.workspace_member import WorkspaceMember

        col = WorkspaceMember.__table__.c.user_id
        # FK column stays String(36) and is populated with str(user.id); it must
        # not emit a ::UUID cast on PostgreSQL.
        stmt = select(WorkspaceMember).where(
            WorkspaceMember.user_id == "dc8c94a8-0c0f-449d-87f7-30c87f9db9f8"
        )
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "::UUID" not in sql, sql
        assert "VARCHAR" in col.type.compile(dialect=postgresql.dialect()).upper()


# ---------------------------------------------------------------------------
# 3. GUID storage format is per-dialect and backward compatible
# ---------------------------------------------------------------------------

class TestGuidStorageFormat:
    def test_postgres_format_is_36_char_hyphenated(self):
        from sqlalchemy.dialects import postgresql as pg

        from app.models.base import GUID

        u = uuid.UUID("dc8c94a8-0c0f-449d-87f7-30c87f9db9f8")
        out = GUID().process_bind_param(u, pg.dialect())
        # Must match the value already stored for the production user.
        assert out == "dc8c94a8-0c0f-449d-87f7-30c87f9db9f8"
        assert len(out) == 36

    def test_sqlite_format_is_32_char_hex(self):
        from sqlalchemy.dialects import sqlite as sl

        from app.models.base import GUID

        u = uuid.UUID("dc8c94a8-0c0f-449d-87f7-30c87f9db9f8")
        out = GUID().process_bind_param(u, sl.dialect())
        assert out == u.hex
        assert len(out) == 32
        assert "-" not in out

    def test_result_value_returns_uuid(self):
        from sqlalchemy.dialects import postgresql as pg
        from sqlalchemy.dialects import sqlite as sl

        from app.models.base import GUID

        u = uuid.UUID("dc8c94a8-0c0f-449d-87f7-30c87f9db9f8")
        assert GUID().process_result_value(u.hex, sl.dialect()) == u
        assert GUID().process_result_value(str(u), pg.dialect()) == u

    def test_accepts_string_input(self):
        from sqlalchemy.dialects import postgresql as pg

        from app.models.base import GUID

        u = uuid.UUID("dc8c94a8-0c0f-449d-87f7-30c87f9db9f8")
        assert GUID().process_bind_param(str(u), pg.dialect()) == str(u)


# ---------------------------------------------------------------------------
# 4. Login updates last_login_at without a 500
# ---------------------------------------------------------------------------

class TestLoginUpdatesLastLogin:
    def test_login_sets_last_login_at(self, lf_client, lf_db):
        _register(lf_client, "login@test.com")
        before = lf_db.query(AuthUser).filter_by(email="login@test.com").first()
        assert before.last_login_at is None

        resp = _login(lf_client, "login@test.com")
        assert resp.status_code == 200, resp.text
        assert "access_token" in resp.json()

        lf_db.expire_all()
        after = lf_db.query(AuthUser).filter_by(email="login@test.com").first()
        assert after.last_login_at is not None

    def test_login_then_me_works(self, lf_client):
        token = _register(lf_client, "flow@test.com").json()["access_token"]
        # /me with the registration token
        me = lf_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        assert me.json()["user"]["email"] == "flow@test.com"

        # full register -> login -> /me
        login_token = _login(lf_client, "flow@test.com").json()["access_token"]
        me2 = lf_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {login_token}"}
        )
        assert me2.status_code == 200, me2.text
        assert me2.json()["user"]["email"] == "flow@test.com"

    def test_wrong_password_returns_401_not_500(self, lf_client):
        _register(lf_client, "wrongpw@test.com", password="correcthorse1")
        resp = _login(lf_client, "wrongpw@test.com", password="totallywrong9")
        assert resp.status_code == 401, resp.text
        assert resp.status_code != 500


# ---------------------------------------------------------------------------
# 5. An existing user whose id is already stored can still log in
# ---------------------------------------------------------------------------

class TestExistingStoredUserCanLogin:
    def test_existing_user_login_and_update(self, lf_client, lf_engine):
        """Register a user (id persisted to the DB), then log in again — this
        is the production scenario: the row already exists and login must
        UPDATE last_login_at by id without a cast mismatch."""
        _register(lf_client, "existing@test.com")

        # Confirm the id is stored as a plain string in the VARCHAR column.
        raw = lf_engine.connect().execute(
            text("SELECT id FROM auth_users WHERE email = 'existing@test.com'")
        ).scalar()
        assert isinstance(raw, str)
        assert uuid.UUID(raw)  # round-trips back to a valid UUID

        # Log in twice — exercises UPDATE ... WHERE id = :id repeatedly.
        assert _login(lf_client, "existing@test.com").status_code == 200
        assert _login(lf_client, "existing@test.com").status_code == 200

    def test_id_lookup_finds_user(self, lf_client, lf_db):
        """The service-layer get_user(id) path used after token decode must find
        the row using the stored id value."""
        from app.services.auth_users import get_user

        _register(lf_client, "lookup@test.com")
        user = lf_db.query(AuthUser).filter_by(email="lookup@test.com").first()
        # get_user accepts the canonical str(uuid) subject from the JWT.
        found = get_user(lf_db, str(user.id))
        assert found is not None
        assert found.email == "lookup@test.com"
