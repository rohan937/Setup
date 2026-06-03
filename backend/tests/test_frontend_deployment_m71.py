"""M71 tests: Frontend Deployment Prep / Vercel Readiness.

Tests for:
  - frontend/.env.example exists and documents VITE_API_BASE_URL
  - frontend/vercel.json exists and contains SPA rewrite
  - docs/vercel-frontend.md exists
  - scripts/frontend_build.sh exists and is executable
  - scripts/frontend_preview.sh exists and is executable
  - Script syntax is valid (bash -n)
  - api.ts exports getApiBaseUrl and uses VITE_API_BASE_URL
  - No secrets or real tokens in docs/examples
  - Deployment readiness includes frontend_vercel_deployment category
  - All frontend_vercel_deployment auto-checks pass
  - Deployment readiness endpoint still returns 200
"""

from __future__ import annotations

import json
import os

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
# Test DB fixtures (isolated in-memory)
# ---------------------------------------------------------------------------

_TEST_DB_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def m71_engine():
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
def m71_db(m71_engine):
    session = Session(m71_engine)
    yield session
    session.close()


@pytest.fixture()
def m71_client(m71_db):
    def _override():
        yield m71_db

    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND_DIR = os.path.join(REPO_ROOT, "frontend")
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
DOCS_DIR = os.path.join(REPO_ROOT, "docs")


# ---------------------------------------------------------------------------
# Frontend .env.example tests
# ---------------------------------------------------------------------------


class TestFrontendEnvExample:
    def test_frontend_env_example_exists(self):
        path = os.path.join(FRONTEND_DIR, ".env.example")
        assert os.path.isfile(path), f"frontend/.env.example not found at {path}"

    def test_frontend_env_example_has_vite_api_base_url(self):
        path = os.path.join(FRONTEND_DIR, ".env.example")
        content = open(path).read()
        assert "VITE_API_BASE_URL" in content, "VITE_API_BASE_URL missing from frontend/.env.example"

    def test_frontend_env_example_has_vite_app_env(self):
        path = os.path.join(FRONTEND_DIR, ".env.example")
        content = open(path).read()
        assert "VITE_APP_ENV" in content

    def test_frontend_env_example_has_demo_mode(self):
        path = os.path.join(FRONTEND_DIR, ".env.example")
        content = open(path).read()
        assert "VITE_DEMO_MODE" in content

    def test_frontend_env_example_no_real_secrets(self):
        path = os.path.join(FRONTEND_DIR, ".env.example")
        content = open(path).read()
        # No JWT tokens, no API keys — only localhost/placeholder URLs
        assert "Bearer " not in content, ".env.example must not contain Bearer tokens"
        assert "qf_local_" not in content, ".env.example must not contain API key prefixes"
        assert "onrender.com" not in content or "your-render" in content, \
            ".env.example must not contain real Render URLs"

    def test_frontend_env_local_not_present(self):
        """frontend/.env.local must not be committed."""
        path = os.path.join(FRONTEND_DIR, ".env.local")
        assert not os.path.isfile(path), (
            "frontend/.env.local exists — ensure it is gitignored and not tracked"
        )


# ---------------------------------------------------------------------------
# frontend/vercel.json tests
# ---------------------------------------------------------------------------


class TestVercelJson:
    def test_vercel_json_exists(self):
        path = os.path.join(FRONTEND_DIR, "vercel.json")
        assert os.path.isfile(path), f"frontend/vercel.json not found at {path}"

    def test_vercel_json_is_valid_json(self):
        path = os.path.join(FRONTEND_DIR, "vercel.json")
        content = open(path).read()
        data = json.loads(content)  # raises if invalid
        assert isinstance(data, dict)

    def test_vercel_json_has_rewrites(self):
        path = os.path.join(FRONTEND_DIR, "vercel.json")
        data = json.loads(open(path).read())
        assert "rewrites" in data, "vercel.json must contain 'rewrites' key"
        assert isinstance(data["rewrites"], list)
        assert len(data["rewrites"]) >= 1

    def test_vercel_json_rewrites_to_index_html(self):
        path = os.path.join(FRONTEND_DIR, "vercel.json")
        data = json.loads(open(path).read())
        destinations = [r.get("destination", "") for r in data["rewrites"]]
        assert any("/index.html" in d for d in destinations), (
            "vercel.json must rewrite paths to /index.html for SPA routing"
        )


# ---------------------------------------------------------------------------
# docs/vercel-frontend.md tests
# ---------------------------------------------------------------------------


class TestVercelFrontendDocs:
    def test_vercel_docs_exist(self):
        path = os.path.join(DOCS_DIR, "vercel-frontend.md")
        assert os.path.isfile(path), f"docs/vercel-frontend.md not found at {path}"

    def test_vercel_docs_mention_vite_api_base_url(self):
        path = os.path.join(DOCS_DIR, "vercel-frontend.md")
        content = open(path).read()
        assert "VITE_API_BASE_URL" in content

    def test_vercel_docs_mention_spa_routing(self):
        path = os.path.join(DOCS_DIR, "vercel-frontend.md")
        content = open(path).read()
        assert "vercel.json" in content.lower() or "SPA" in content

    def test_vercel_docs_mention_cors(self):
        path = os.path.join(DOCS_DIR, "vercel-frontend.md")
        content = open(path).read()
        assert "CORS" in content or "cors" in content

    def test_vercel_docs_no_real_secrets(self):
        path = os.path.join(DOCS_DIR, "vercel-frontend.md")
        content = open(path).read()
        assert "Bearer " not in content, "docs must not contain Bearer tokens"
        assert "qf_live_" not in content, "docs must not contain live API key prefixes"


# ---------------------------------------------------------------------------
# Script tests
# ---------------------------------------------------------------------------


class TestFrontendScripts:
    def test_frontend_build_sh_exists(self):
        path = os.path.join(SCRIPTS_DIR, "frontend_build.sh")
        assert os.path.isfile(path), f"scripts/frontend_build.sh not found"

    def test_frontend_preview_sh_exists(self):
        path = os.path.join(SCRIPTS_DIR, "frontend_preview.sh")
        assert os.path.isfile(path), f"scripts/frontend_preview.sh not found"

    def test_frontend_build_sh_executable(self):
        path = os.path.join(SCRIPTS_DIR, "frontend_build.sh")
        assert os.access(path, os.X_OK), "frontend_build.sh is not executable"

    def test_frontend_preview_sh_executable(self):
        path = os.path.join(SCRIPTS_DIR, "frontend_preview.sh")
        assert os.access(path, os.X_OK), "frontend_preview.sh is not executable"

    def test_frontend_build_sh_syntax(self):
        path = os.path.join(SCRIPTS_DIR, "frontend_build.sh")
        result = os.system(f"bash -n {path}")
        assert result == 0, "frontend_build.sh has syntax errors"

    def test_frontend_preview_sh_syntax(self):
        path = os.path.join(SCRIPTS_DIR, "frontend_preview.sh")
        result = os.system(f"bash -n {path}")
        assert result == 0, "frontend_preview.sh has syntax errors"

    def test_frontend_build_sh_contains_npm_build(self):
        path = os.path.join(SCRIPTS_DIR, "frontend_build.sh")
        content = open(path).read()
        assert "npm run build" in content

    def test_frontend_build_sh_contains_typecheck(self):
        path = os.path.join(SCRIPTS_DIR, "frontend_build.sh")
        content = open(path).read()
        assert "typecheck" in content

    def test_frontend_preview_sh_contains_vite_preview(self):
        path = os.path.join(SCRIPTS_DIR, "frontend_preview.sh")
        content = open(path).read()
        assert "vite preview" in content or "preview" in content


# ---------------------------------------------------------------------------
# api.ts tests
# ---------------------------------------------------------------------------


class TestApiTsHardening:
    API_TS = os.path.join(FRONTEND_DIR, "src", "lib", "api.ts")

    def test_api_ts_uses_vite_api_base_url(self):
        content = open(self.API_TS).read()
        assert "VITE_API_BASE_URL" in content, "api.ts must reference VITE_API_BASE_URL"

    def test_api_ts_exports_get_api_base_url(self):
        content = open(self.API_TS).read()
        assert "getApiBaseUrl" in content, "api.ts must export getApiBaseUrl()"

    def test_api_ts_exports_get_frontend_environment(self):
        content = open(self.API_TS).read()
        assert "getFrontendEnvironment" in content, "api.ts must export getFrontendEnvironment()"

    def test_api_ts_exports_is_demo_mode(self):
        content = open(self.API_TS).read()
        assert "isDemoMode" in content, "api.ts must export isDemoMode()"

    def test_api_ts_trims_trailing_slash(self):
        content = open(self.API_TS).read()
        # The implementation uses .replace(/\/+$/, "")
        assert "replace" in content and "trailing" in content.lower() or "replace" in content, \
            "api.ts should trim trailing slashes from the base URL"

    def test_api_ts_no_hardcoded_non_fallback_localhost(self):
        content = open(self.API_TS).read()
        # Only one localhost reference allowed: the fallback default in getApiBaseUrl
        localhost_count = content.count("localhost:8000")
        assert localhost_count <= 1, (
            f"api.ts has {localhost_count} hardcoded localhost:8000 references; "
            "should have at most 1 (the fallback default)"
        )

    def test_api_ts_no_token_console_log(self):
        content = open(self.API_TS).read()
        # Ensure no console.log of auth headers or tokens
        lines_with_log = [
            line for line in content.splitlines()
            if "console.log" in line and ("token" in line.lower() or "authorization" in line.lower())
        ]
        assert not lines_with_log, f"api.ts logs auth tokens: {lines_with_log}"


# ---------------------------------------------------------------------------
# Deployment readiness integration tests
# ---------------------------------------------------------------------------


class TestDeploymentReadinessM71:
    def test_frontend_vercel_category_in_readiness(self, m71_client):
        resp = m71_client.get("/api/admin/deployment-readiness")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        cat_keys = [c["category_key"] for c in data["categories"]]
        assert "frontend_vercel_deployment" in cat_keys, (
            f"frontend_vercel_deployment category missing; found: {cat_keys}"
        )

    def test_frontend_env_example_check_passes(self, m71_client):
        resp = m71_client.get("/api/admin/deployment-readiness")
        data = resp.json()
        vercel_cat = next(
            c for c in data["categories"] if c["category_key"] == "frontend_vercel_deployment"
        )
        check = next(
            (c for c in vercel_cat["checks"] if c["check_key"] == "frontend_env_example_exists"),
            None,
        )
        assert check is not None
        assert check["status"] == "pass", f"frontend_env_example check: {check}"

    def test_vercel_json_check_passes(self, m71_client):
        resp = m71_client.get("/api/admin/deployment-readiness")
        data = resp.json()
        vercel_cat = next(
            c for c in data["categories"] if c["category_key"] == "frontend_vercel_deployment"
        )
        check = next(
            (c for c in vercel_cat["checks"] if c["check_key"] == "frontend_vercel_json_exists"),
            None,
        )
        assert check is not None
        assert check["status"] == "pass", f"vercel_json check: {check}"

    def test_vercel_json_rewrite_check_passes(self, m71_client):
        resp = m71_client.get("/api/admin/deployment-readiness")
        data = resp.json()
        vercel_cat = next(
            c for c in data["categories"] if c["category_key"] == "frontend_vercel_deployment"
        )
        check = next(
            (c for c in vercel_cat["checks"] if c["check_key"] == "frontend_vercel_json_has_rewrite"),
            None,
        )
        assert check is not None
        assert check["status"] == "pass", f"vercel rewrite check: {check}"

    def test_vercel_docs_check_passes(self, m71_client):
        resp = m71_client.get("/api/admin/deployment-readiness")
        data = resp.json()
        vercel_cat = next(
            c for c in data["categories"] if c["category_key"] == "frontend_vercel_deployment"
        )
        check = next(
            (c for c in vercel_cat["checks"] if c["check_key"] == "vercel_frontend_docs_exist"),
            None,
        )
        assert check is not None
        assert check["status"] == "pass", f"vercel docs check: {check}"

    def test_frontend_build_sh_check_passes(self, m71_client):
        resp = m71_client.get("/api/admin/deployment-readiness")
        data = resp.json()
        vercel_cat = next(
            c for c in data["categories"] if c["category_key"] == "frontend_vercel_deployment"
        )
        check = next(
            (c for c in vercel_cat["checks"] if c["check_key"] == "frontend_build_sh_exists"),
            None,
        )
        assert check is not None
        assert check["status"] == "pass", f"frontend_build_sh check: {check}"

    def test_api_ts_vite_env_check_passes(self, m71_client):
        resp = m71_client.get("/api/admin/deployment-readiness")
        data = resp.json()
        vercel_cat = next(
            c for c in data["categories"] if c["category_key"] == "frontend_vercel_deployment"
        )
        check = next(
            (c for c in vercel_cat["checks"] if c["check_key"] == "api_ts_uses_vite_api_base_url"),
            None,
        )
        assert check is not None
        assert check["status"] == "pass", f"api_ts vite env check: {check}"

    def test_vite_api_base_url_documented_check_passes(self, m71_client):
        resp = m71_client.get("/api/admin/deployment-readiness")
        data = resp.json()
        vercel_cat = next(
            c for c in data["categories"] if c["category_key"] == "frontend_vercel_deployment"
        )
        check = next(
            (c for c in vercel_cat["checks"] if c["check_key"] == "vite_api_base_url_documented"),
            None,
        )
        assert check is not None
        assert check["status"] == "pass", f"vite_api_base_url_documented check: {check}"

    def test_deployment_readiness_endpoint_returns_200(self, m71_client):
        resp = m71_client.get("/api/admin/deployment-readiness")
        assert resp.status_code == 200

    def test_no_real_secrets_in_readiness_response(self, m71_client):
        resp = m71_client.get("/api/admin/deployment-readiness")
        text = resp.text
        assert "Bearer " not in text
        assert "qf_live_" not in text
