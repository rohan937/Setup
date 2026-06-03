"""M70 tests: Backend Deployment Prep / Render + PostgreSQL Readiness.

Tests for:
  - Config: SQLite URL accepted, postgres:// normalised, production safety properties
  - Scripts: backend_migrate.sh and backend_start.sh exist and are executable
  - Health endpoint: GET /api/health/deployment returns 200, correct structure
  - No secrets in health response
  - Deployment readiness includes Render prep category with new M70 checks
"""

from __future__ import annotations

import os
import stat

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app

# ---------------------------------------------------------------------------
# Test DB fixtures (isolated in-memory, same pattern as other M* tests)
# ---------------------------------------------------------------------------

_TEST_DB_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def m70_engine():
    engine = create_engine(
        _TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def m70_db(m70_engine):
    session = Session(m70_engine)
    yield session
    session.close()


@pytest.fixture()
def m70_client(m70_db):
    def _override():
        yield m70_db

    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestConfigM70:
    def test_sqlite_url_accepted(self):
        from app.core.config import Settings
        s = Settings(database_url="sqlite+pysqlite:///./test.db")
        assert s.is_sqlite is True
        assert s.is_production is False

    def test_postgres_url_normalised_from_render_format(self):
        """Render provides postgres:// — must be normalised to postgresql://."""
        from app.core.config import Settings
        s = Settings(database_url="postgres://user:pass@host:5432/mydb")
        assert s.database_url.startswith("postgresql://")
        assert not s.database_url.startswith("postgres://")

    def test_postgresql_url_unchanged(self):
        from app.core.config import Settings
        s = Settings(database_url="postgresql+psycopg2://user:pass@host:5432/mydb")
        assert s.database_url == "postgresql+psycopg2://user:pass@host:5432/mydb"

    def test_sqlite_is_not_production(self):
        from app.core.config import Settings
        s = Settings(database_url="sqlite+pysqlite:///./dev.db")
        assert s.is_sqlite is True

    def test_postgresql_is_not_sqlite(self):
        from app.core.config import Settings
        s = Settings(database_url="postgresql://user:pass@host:5432/mydb")
        assert s.is_sqlite is False

    def test_dev_jwt_secret_detected(self):
        """The dev default JWT secret should be flagged as unsafe."""
        from app.core.config import Settings
        s = Settings()
        assert s.jwt_secret_is_dev_default is True

    def test_custom_jwt_secret_is_safe(self):
        from app.core.config import Settings
        s = Settings(QF_JWT_SECRET_KEY="a-very-long-random-secret-not-the-default-value")
        assert s.jwt_secret_is_dev_default is False

    def test_production_with_dev_secret_is_unsafe(self):
        from app.core.config import Settings
        s = Settings(environment="production")
        # dev default JWT secret in production → unsafe
        assert s.production_jwt_secret_unsafe is True

    def test_production_with_strong_secret_is_safe(self):
        from app.core.config import Settings
        s = Settings(
            environment="production",
            QF_JWT_SECRET_KEY="strong-production-secret-not-the-default-abc123xyz",
        )
        assert s.production_jwt_secret_unsafe is False

    def test_cors_origin_list_parsed(self):
        from app.core.config import Settings
        s = Settings(cors_origins="https://app.example.com,https://staging.example.com")
        assert "https://app.example.com" in s.cors_origin_list
        assert len(s.cors_origin_list) == 2


# ---------------------------------------------------------------------------
# Script tests
# ---------------------------------------------------------------------------


class TestScriptsM70:
    def test_backend_migrate_sh_exists(self):
        path = os.path.join(SCRIPTS_DIR, "backend_migrate.sh")
        assert os.path.isfile(path), f"backend_migrate.sh not found at {path}"

    def test_backend_start_sh_exists(self):
        path = os.path.join(SCRIPTS_DIR, "backend_start.sh")
        assert os.path.isfile(path), f"backend_start.sh not found at {path}"

    def test_backend_migrate_sh_is_executable(self):
        path = os.path.join(SCRIPTS_DIR, "backend_migrate.sh")
        assert os.access(path, os.X_OK), "backend_migrate.sh is not executable"

    def test_backend_start_sh_is_executable(self):
        path = os.path.join(SCRIPTS_DIR, "backend_start.sh")
        assert os.access(path, os.X_OK), "backend_start.sh is not executable"

    def test_backend_migrate_sh_syntax(self):
        """bash -n validates syntax without running the script."""
        path = os.path.join(SCRIPTS_DIR, "backend_migrate.sh")
        result = os.system(f"bash -n {path}")
        assert result == 0, "backend_migrate.sh has syntax errors"

    def test_backend_start_sh_syntax(self):
        path = os.path.join(SCRIPTS_DIR, "backend_start.sh")
        result = os.system(f"bash -n {path}")
        assert result == 0, "backend_start.sh has syntax errors"

    def test_backend_migrate_sh_contains_alembic(self):
        path = os.path.join(SCRIPTS_DIR, "backend_migrate.sh")
        content = open(path).read()
        assert "alembic upgrade head" in content

    def test_backend_start_sh_contains_uvicorn(self):
        path = os.path.join(SCRIPTS_DIR, "backend_start.sh")
        content = open(path).read()
        assert "uvicorn" in content

    def test_backend_start_sh_uses_port_env(self):
        """Start script must honour the PORT env var (required by Render)."""
        path = os.path.join(SCRIPTS_DIR, "backend_start.sh")
        content = open(path).read()
        assert "PORT" in content


# ---------------------------------------------------------------------------
# Deployment health endpoint tests
# ---------------------------------------------------------------------------


class TestDeploymentHealthEndpoint:
    def test_deployment_health_returns_200(self, m70_client):
        resp = m70_client.get("/api/health/deployment")
        assert resp.status_code == 200, resp.text

    def test_deployment_health_has_required_fields(self, m70_client):
        resp = m70_client.get("/api/health/deployment")
        data = resp.json()
        required = [
            "status", "environment", "version",
            "database_configured", "database_reachable", "database_driver",
            "migrations_note", "auth_enabled", "rbac_enabled",
            "cors_configured", "jwt_secret_safe", "production_warnings",
        ]
        for field in required:
            assert field in data, f"Missing field: {field}"

    def test_deployment_health_does_not_expose_jwt_secret(self, m70_client):
        """The response must never contain the actual JWT secret."""
        from app.core.config import get_settings
        settings = get_settings()
        resp = m70_client.get("/api/health/deployment")
        text = resp.text
        assert settings.QF_JWT_SECRET_KEY not in text

    def test_deployment_health_does_not_expose_database_url(self, m70_client):
        """The response must not include the raw database URL."""
        from app.core.config import get_settings
        settings = get_settings()
        resp = m70_client.get("/api/health/deployment")
        text = resp.text
        # The database URL would contain :// — ensure it's not directly in the response
        # (driver string like "sqlite" is fine, but the full URL is not)
        assert "sqlite+pysqlite:///" not in text

    def test_deployment_health_status_ok(self, m70_client):
        resp = m70_client.get("/api/health/deployment")
        assert resp.json()["status"] == "ok"

    def test_deployment_health_sqlite_is_reachable(self, m70_client):
        """With in-memory SQLite the DB should be reported as reachable."""
        resp = m70_client.get("/api/health/deployment")
        data = resp.json()
        assert data["database_reachable"] is True

    def test_deployment_health_sqlite_database_configured_false(self, m70_client):
        """SQLite counts as 'not configured for production' (not a PostgreSQL URL)."""
        resp = m70_client.get("/api/health/deployment")
        data = resp.json()
        # SQLite is the dev default → database_configured = False
        assert data["database_configured"] is False

    def test_deployment_health_auth_and_rbac_enabled(self, m70_client):
        resp = m70_client.get("/api/health/deployment")
        data = resp.json()
        # Default settings have both enabled
        assert data["auth_enabled"] is True
        assert data["rbac_enabled"] is True

    def test_deployment_health_cors_configured(self, m70_client):
        resp = m70_client.get("/api/health/deployment")
        data = resp.json()
        # Default settings have localhost CORS origins
        assert data["cors_configured"] is True

    def test_deployment_health_jwt_unsafe_in_dev(self, m70_client):
        """Dev default JWT secret → jwt_secret_safe = False."""
        resp = m70_client.get("/api/health/deployment")
        data = resp.json()
        assert data["jwt_secret_safe"] is False

    def test_deployment_health_production_warnings_list(self, m70_client):
        resp = m70_client.get("/api/health/deployment")
        data = resp.json()
        assert isinstance(data["production_warnings"], list)

    def test_liveness_health_still_works(self, m70_client):
        """Existing /health endpoint must remain functional after M70."""
        resp = m70_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# Deployment readiness includes M70 checks
# ---------------------------------------------------------------------------


class TestDeploymentReadinessM70Checks:
    def test_render_prep_category_in_readiness(self, m70_client):
        resp = m70_client.get("/api/admin/deployment-readiness")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        cats = [c["category_key"] for c in data["categories"]]
        assert "render_deployment" in cats, f"render_deployment category missing; found: {cats}"

    def test_migrate_script_check_passes(self, m70_client):
        resp = m70_client.get("/api/admin/deployment-readiness")
        data = resp.json()
        render_cat = next(
            c for c in data["categories"] if c["category_key"] == "render_deployment"
        )
        check_keys = {c["check_key"] for c in render_cat["checks"]}
        assert "backend_migrate_sh_exists" in check_keys
        # The script exists and should pass
        migrate_check = next(c for c in render_cat["checks"] if c["check_key"] == "backend_migrate_sh_exists")
        assert migrate_check["status"] == "pass", f"migrate check failed: {migrate_check}"

    def test_start_script_check_passes(self, m70_client):
        resp = m70_client.get("/api/admin/deployment-readiness")
        data = resp.json()
        render_cat = next(
            c for c in data["categories"] if c["category_key"] == "render_deployment"
        )
        start_check = next(
            (c for c in render_cat["checks"] if c["check_key"] == "backend_start_sh_exists"),
            None,
        )
        assert start_check is not None
        assert start_check["status"] == "pass", f"start check failed: {start_check}"

    def test_psycopg2_check_passes(self, m70_client):
        resp = m70_client.get("/api/admin/deployment-readiness")
        data = resp.json()
        render_cat = next(
            c for c in data["categories"] if c["category_key"] == "render_deployment"
        )
        psycopg_check = next(
            (c for c in render_cat["checks"] if c["check_key"] == "psycopg2_in_requirements"),
            None,
        )
        assert psycopg_check is not None
        assert psycopg_check["status"] == "pass", f"psycopg2 check failed: {psycopg_check}"

    def test_deployment_health_endpoint_check_passes(self, m70_client):
        resp = m70_client.get("/api/admin/deployment-readiness")
        data = resp.json()
        render_cat = next(
            c for c in data["categories"] if c["category_key"] == "render_deployment"
        )
        ep_check = next(
            (c for c in render_cat["checks"] if c["check_key"] == "deployment_health_endpoint_exists"),
            None,
        )
        assert ep_check is not None
        assert ep_check["status"] == "pass", f"endpoint check failed: {ep_check}"

    def test_render_docs_check_passes(self, m70_client):
        resp = m70_client.get("/api/admin/deployment-readiness")
        data = resp.json()
        render_cat = next(
            c for c in data["categories"] if c["category_key"] == "render_deployment"
        )
        docs_check = next(
            (c for c in render_cat["checks"] if c["check_key"] == "render_backend_docs_exist"),
            None,
        )
        assert docs_check is not None
        assert docs_check["status"] == "pass", f"docs check failed: {docs_check}"
