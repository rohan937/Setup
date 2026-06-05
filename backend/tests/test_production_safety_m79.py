"""Production safety and auth persistence tests.

Covers the account-disappearance root causes and their fixes:

1. Production + SQLite → RuntimeError at startup (data lost on every Render deploy)
2. Production + dev JWT secret → RuntimeError at startup (token forgery possible)
3. Non-production never blocks startup regardless of settings
4. database_persistent_safe is False for SQLite, True for Postgres URLs
5. Deployment health endpoint includes database_persistent_safe field
6. Registration persists to the same DB; login survives a session restart
7. Changing JWT secret invalidates existing tokens but does NOT delete users
8. Seed/migration/demo code never wipes auth_users or workspace_members
9. Config normalises postgres:// → postgresql:// URLs automatically
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app


_DB_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def persist_engine():
    eng = create_engine(_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def persist_db(persist_engine):
    s = Session(persist_engine)
    yield s
    s.close()


@pytest.fixture()
def persist_client(persist_db):
    def _override():
        yield persist_db
    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    if prior is not None:
        app.dependency_overrides[get_db] = prior
    else:
        app.dependency_overrides.pop(get_db, None)


def _register(client, email="user@test.com", name="Test", pw="password123"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "display_name": name, "password": pw},
    )


def _login(client, email="user@test.com", pw="password123"):
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": pw},
    )


# ---------------------------------------------------------------------------
# 1 + 2. Startup guards — production config safety
# ---------------------------------------------------------------------------

class TestProductionStartupGuards:
    def test_production_sqlite_raises_at_startup(self, monkeypatch):
        """Production + SQLite must raise RuntimeError before serving traffic."""
        from app.core import config as cfg

        monkeypatch.setenv("QF_ENVIRONMENT", "production")
        monkeypatch.setenv("QF_DATABASE_URL", "sqlite:///./quantfidelity.db")
        monkeypatch.setenv("QF_JWT_SECRET_KEY", "a-very-long-strong-random-secret-key-12345")
        cfg.get_settings.cache_clear()
        try:
            s = cfg.get_settings()
            with pytest.raises(RuntimeError, match="SQLite"):
                s.assert_production_safe()
        finally:
            cfg.get_settings.cache_clear()

    def test_production_default_jwt_raises_at_startup(self, monkeypatch):
        """Production + dev-default JWT secret must raise RuntimeError."""
        from app.core import config as cfg

        monkeypatch.setenv("QF_ENVIRONMENT", "production")
        monkeypatch.setenv("QF_DATABASE_URL", "postgresql://user:pass@host/db")
        # Leave QF_JWT_SECRET_KEY unset → uses the dev default
        monkeypatch.delenv("QF_JWT_SECRET_KEY", raising=False)
        cfg.get_settings.cache_clear()
        try:
            s = cfg.get_settings()
            with pytest.raises(RuntimeError, match="JWT"):
                s.assert_production_safe()
        finally:
            cfg.get_settings.cache_clear()

    def test_production_both_unsafe_raises_once(self, monkeypatch):
        """Both problems in one deployment → single RuntimeError with both messages."""
        from app.core import config as cfg

        monkeypatch.setenv("QF_ENVIRONMENT", "production")
        monkeypatch.setenv("QF_DATABASE_URL", "sqlite:///./quantfidelity.db")
        monkeypatch.delenv("QF_JWT_SECRET_KEY", raising=False)
        cfg.get_settings.cache_clear()
        try:
            s = cfg.get_settings()
            with pytest.raises(RuntimeError) as exc_info:
                s.assert_production_safe()
            msg = str(exc_info.value)
            assert "SQLite" in msg
            assert "JWT" in msg
        finally:
            cfg.get_settings.cache_clear()

    def test_production_safe_config_does_not_raise(self, monkeypatch):
        """Production with Postgres URL + strong secret must not raise."""
        from app.core import config as cfg

        monkeypatch.setenv("QF_ENVIRONMENT", "production")
        monkeypatch.setenv("QF_DATABASE_URL", "postgresql://user:pass@host/db")
        # Correct env var — QF_ prefix + field name (jwt_secret_key) = QF_JWT_SECRET_KEY
        monkeypatch.setenv("QF_JWT_SECRET_KEY", "a-very-long-strong-random-secret-key-12345")
        cfg.get_settings.cache_clear()
        try:
            s = cfg.get_settings()
            assert not s.jwt_secret_is_dev_default, "strong secret must override the dev default"
            s.assert_production_safe()  # must not raise
        finally:
            cfg.get_settings.cache_clear()

    def test_local_environment_never_blocks_startup(self, monkeypatch):
        """Local dev (default) environment must never block startup."""
        from app.core import config as cfg

        monkeypatch.setenv("QF_ENVIRONMENT", "local")
        # Leave everything else at insecure defaults
        cfg.get_settings.cache_clear()
        try:
            s = cfg.get_settings()
            s.assert_production_safe()  # must not raise for local
        finally:
            cfg.get_settings.cache_clear()

    def test_staging_environment_does_not_block(self, monkeypatch):
        """Only 'production' triggers the safety checks."""
        from app.core import config as cfg

        monkeypatch.setenv("QF_ENVIRONMENT", "staging")
        cfg.get_settings.cache_clear()
        try:
            s = cfg.get_settings()
            s.assert_production_safe()  # staging is not enforced
        finally:
            cfg.get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 3 + 4. Config properties
# ---------------------------------------------------------------------------

class TestConfigProperties:
    def test_sqlite_is_not_persistent_safe(self, monkeypatch):
        from app.core import config as cfg

        monkeypatch.setenv("QF_DATABASE_URL", "sqlite:///./quantfidelity.db")
        cfg.get_settings.cache_clear()
        try:
            assert cfg.get_settings().database_persistent_safe is False
        finally:
            cfg.get_settings.cache_clear()

    def test_postgres_is_persistent_safe(self, monkeypatch):
        from app.core import config as cfg

        monkeypatch.setenv("QF_DATABASE_URL", "postgresql://user:pass@host/db")
        cfg.get_settings.cache_clear()
        try:
            assert cfg.get_settings().database_persistent_safe is True
        finally:
            cfg.get_settings.cache_clear()

    def test_postgres_shorthand_url_is_normalised(self, monkeypatch):
        """Render provides postgres:// URLs; they must be normalised to postgresql://."""
        from app.core import config as cfg

        monkeypatch.setenv("QF_DATABASE_URL", "postgres://user:pass@host/db")
        cfg.get_settings.cache_clear()
        try:
            s = cfg.get_settings()
            assert s.database_url.startswith("postgresql://")
            assert s.database_persistent_safe is True
        finally:
            cfg.get_settings.cache_clear()

    def test_dev_default_jwt_is_unsafe(self):
        from app.core import config as cfg
        s = cfg.get_settings()
        assert s.jwt_secret_is_dev_default is True
        # jwt_secret_is_dev_default is the canonical property on Settings.
        # The health endpoint derives jwt_secret_safe = not jwt_secret_is_dev_default.
        assert not s.jwt_secret_is_dev_default is False

    def test_custom_jwt_is_safe(self, monkeypatch):
        from app.core import config as cfg

        # QF_JWT_SECRET_KEY is the correct env var (env_prefix + field name jwt_secret_key)
        monkeypatch.setenv("QF_JWT_SECRET_KEY", "my-very-long-custom-production-jwt-secret-key")
        cfg.get_settings.cache_clear()
        try:
            assert cfg.get_settings().jwt_secret_is_dev_default is False
        finally:
            cfg.get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 5. Deployment health endpoint includes new field
# ---------------------------------------------------------------------------

class TestDeploymentHealthEndpoint:
    def test_deployment_health_includes_persistent_safe(self, persist_client):
        resp = persist_client.get("/api/health/deployment")
        assert resp.status_code == 200
        data = resp.json()
        assert "database_persistent_safe" in data
        # We're using SQLite in tests so this should be False
        assert data["database_persistent_safe"] is False

    def test_deployment_health_shows_all_required_fields(self, persist_client):
        resp = persist_client.get("/api/health/deployment")
        data = resp.json()
        required = {
            "environment", "database_driver", "database_configured",
            "database_persistent_safe", "database_reachable",
            "jwt_secret_safe", "auth_enabled", "rbac_enabled",
            "cors_configured", "production_warnings",
        }
        for field in required:
            assert field in data, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# 6. Registration persists; login survives session restart
# ---------------------------------------------------------------------------

class TestAuthPersistence:
    def test_registration_creates_user_in_db(self, persist_client, persist_db):
        from app.models.auth_user import AuthUser

        resp = _register(persist_client, "persist@test.com")
        assert resp.status_code == 200, resp.text

        user = persist_db.query(AuthUser).filter_by(email="persist@test.com").first()
        assert user is not None
        assert user.email == "persist@test.com"
        assert user.hashed_password  # password must NOT be stored in plain text
        assert user.hashed_password != "password123"

    def test_login_works_after_registration(self, persist_client):
        _register(persist_client, "login@test.com")
        resp = _login(persist_client, "login@test.com")
        assert resp.status_code == 200, resp.text
        assert "access_token" in resp.json()

    def test_token_grants_me_access(self, persist_client):
        _register(persist_client, "me@test.com")
        token = _login(persist_client, "me@test.com").json()["access_token"]
        resp = persist_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == "me@test.com"

    def test_login_works_after_new_client_session(self, persist_db):
        """Login must succeed with a fresh TestClient sharing the same DB session.

        Simulates 'app restart with same database' — the critical scenario
        that SQLite on Render's ephemeral disk would silently break.
        """
        def _override():
            yield persist_db
        prior = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = _override

        # First client: register
        with TestClient(app, raise_server_exceptions=True) as c1:
            _register(c1, "restart@test.com")

        # Second client (separate HTTP session, same DB): login must succeed
        with TestClient(app, raise_server_exceptions=True) as c2:
            resp = _login(c2, "restart@test.com")
            assert resp.status_code == 200, "Login must work after session restart with same DB"
            assert "access_token" in resp.json()

        if prior is not None:
            app.dependency_overrides[get_db] = prior
        else:
            app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 7. Changing JWT secret invalidates tokens but does NOT delete users
# ---------------------------------------------------------------------------

class TestJwtSecretRotation:
    def test_old_token_rejected_after_secret_change(self, persist_db, monkeypatch):
        """Changing QF_JWT_SECRET_KEY invalidates old tokens (expected behavior)
        but must never delete auth_users or workspace_members rows.

        Note: security.py reads get_settings() each call (not at import time),
        so clearing lru_cache in between is sufficient for the new secret to apply.
        """
        from app.core import config as cfg
        from app.models.auth_user import AuthUser

        def _override():
            yield persist_db
        prior = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = _override

        try:
            # Register + get a token with the original (dev) secret.
            with TestClient(app, raise_server_exceptions=True) as c:
                _register(c, "rotate@test.com")
                token = _login(c, "rotate@test.com").json()["access_token"]
                # Token works with the current (dev) secret.
                assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

            # Simulate operator rotating the JWT secret.
            monkeypatch.setenv("QF_JWT_SECRET_KEY", "brand-new-strong-secret-after-rotation-xyz")
            cfg.get_settings.cache_clear()

            with TestClient(app, raise_server_exceptions=True) as c2:
                # Old token must be REJECTED (signed with old secret).
                resp = c2.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
                assert resp.status_code == 401, (
                    f"Old token must be invalid after secret rotation (got {resp.status_code})"
                )

                # User MUST still exist in the database — rotation does NOT delete users.
                user = persist_db.query(AuthUser).filter_by(email="rotate@test.com").first()
                assert user is not None, "User must still exist after JWT secret rotation"

                # Re-login with new secret works (credentials are in the DB, not the token).
                new_resp = _login(c2, "rotate@test.com")
                assert new_resp.status_code == 200, "Re-login must work after secret rotation"
                new_token = new_resp.json()["access_token"]
                assert c2.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"}).status_code == 200
        finally:
            cfg.get_settings.cache_clear()
            if prior is not None:
                app.dependency_overrides[get_db] = prior
            else:
                app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 8. Seed/migration code never wipes auth_users or workspace_members
# ---------------------------------------------------------------------------

class TestSeedSafety:
    def test_extend_mode_seed_does_not_wipe_auth_users(self, persist_client, persist_db):
        """The 'extend' demo seed must never touch auth_users or workspace_members."""
        from app.models.auth_user import AuthUser
        from app.models.workspace_member import WorkspaceMember

        _register(persist_client, "protected@test.com", "Protected User")
        pre_user_count = persist_db.query(AuthUser).count()
        pre_member_count = persist_db.query(WorkspaceMember).count()

        # Run extend-mode seed.
        persist_client.post(
            "/api/admin/seed-demo",
            json={"mode": "extend", "include_alerts": False, "include_backtest_audits": False},
        )

        post_user_count = persist_db.query(AuthUser).count()
        post_member_count = persist_db.query(WorkspaceMember).count()

        assert post_user_count >= pre_user_count, \
            "Seed must never decrease auth_users count"
        assert post_member_count >= pre_member_count, \
            "Seed must never decrease workspace_members count"
        # Original user still exists
        user = persist_db.query(AuthUser).filter_by(email="protected@test.com").first()
        assert user is not None, "Original user must survive seed operation"

    def test_migration_wipe_tables_list_excludes_auth_and_members(self):
        """_TABLES_TO_WIPE in demo_seed must not include auth_users or workspace_members."""
        from app.services.demo_seed import _TABLES_TO_WIPE  # noqa: F401

        safe = {"auth_users", "workspace_members", "organizations"}
        for table in _TABLES_TO_WIPE:
            assert table not in safe, (
                f"_TABLES_TO_WIPE must not include '{table}' — "
                "it would delete user accounts and org memberships."
            )
