"""Tests for the "Register Strategy modal stuck on Loading" fix.

Root cause:
  First-user bootstrap created a default *organization* and *workspace member*
  but **no project**.  Strategies require a ``project_id``, so ``GET /api/projects``
  returned ``200 []`` for a fresh account and the modal's Project dropdown had
  nothing to select (the frontend rendered "Loading…" for an empty list).

Backend fixes covered here:
  * first-user registration / owner bootstrap now creates a default project;
  * a new ``POST /api/projects`` endpoint lets an account that already exists
    (registered before this fix) create a project from the modal empty state;
  * a strategy can be created against the default project end-to-end.

Frontend fixes (no JS test runner in this repo) are covered by typecheck +
build: the dropdown distinguishes loading / populated / empty+error states and
always ends loading via ``.finally()``.

Fixtures are prefixed ``dp_`` to avoid colliding with conftest's session-scoped
``seed_data(db)`` fixture chain.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register all mappers)
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.project import Project

_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def dp_engine():
    eng = create_engine(_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def dp_db(dp_engine):
    s = Session(dp_engine)
    yield s
    s.close()


@pytest.fixture()
def dp_client(dp_db):
    def _override():
        yield dp_db

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


def _auth(client, email, password="password123"):
    tok = _register(client, email, password).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


# ---------------------------------------------------------------------------
# Bootstrap creates a default project
# ---------------------------------------------------------------------------

class TestBootstrapCreatesProject:
    def test_first_user_registration_creates_default_project(self, dp_client, dp_db):
        _register(dp_client, "first@test.com")
        projects = dp_db.query(Project).all()
        assert len(projects) == 1
        assert projects[0].name == "Default Project"
        assert projects[0].slug == "default-project"
        # project belongs to the bootstrapped default org
        org = dp_db.query(Organization).first()
        assert projects[0].organization_id == org.id

    def test_get_projects_returns_200_and_nonempty_after_register(self, dp_client):
        H = _auth(dp_client, "owner@test.com")
        r = dp_client.get("/api/projects", headers=H)
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) >= 1
        assert body[0]["name"] == "Default Project"

    def test_second_registration_does_not_duplicate_default_project(self, dp_client, dp_db):
        _register(dp_client, "first@test.com")
        _register(dp_client, "second@test.com")
        assert dp_db.query(Project).count() == 1

    def test_bootstrap_owner_creates_default_project(self, dp_db):
        from app.services.auth_users import bootstrap_owner

        result = bootstrap_owner(dp_db, email="boss@test.com", display_name="Boss")
        dp_db.commit()
        assert result["role"] == "owner"
        assert dp_db.query(Project).count() == 1
        assert dp_db.query(Project).first().name == "Default Project"


# ---------------------------------------------------------------------------
# Register Strategy flow works end-to-end
# ---------------------------------------------------------------------------

class TestRegisterStrategyFlow:
    def test_register_then_create_strategy_with_default_project(self, dp_client):
        H = _auth(dp_client, "owner@test.com")
        projects = dp_client.get("/api/projects", headers=H).json()
        assert projects, "modal must have a project to select"
        pid = projects[0]["id"]

        r = dp_client.post(
            "/api/strategies",
            json={"project_id": pid, "name": "Mean Reversion", "asset_class": "equity", "status": "active"},
            headers=H,
        )
        assert r.status_code == 201, r.text
        assert r.json()["name"] == "Mean Reversion"


# ---------------------------------------------------------------------------
# POST /api/projects (empty-state "Create default project" path)
# ---------------------------------------------------------------------------

class TestCreateProjectEndpoint:
    def test_create_project_resolves_default_org(self, dp_client):
        H = _auth(dp_client, "owner@test.com")
        r = dp_client.post("/api/projects", json={"name": "Alpha Research"}, headers=H)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "Alpha Research"
        assert body["slug"] == "alpha-research"
        assert body["organization_id"]

    def test_create_project_duplicate_slug_409(self, dp_client):
        H = _auth(dp_client, "owner@test.com")
        # "Default Project" already exists from bootstrap
        r = dp_client.post("/api/projects", json={"name": "Default Project"}, headers=H)
        assert r.status_code == 409, r.text

    def test_create_project_blank_name_422(self, dp_client):
        H = _auth(dp_client, "owner@test.com")
        r = dp_client.post("/api/projects", json={"name": "   "}, headers=H)
        assert r.status_code == 422, r.text

    def test_existing_org_without_project_can_create_one(self, dp_client, dp_db):
        """Simulates the production user who registered BEFORE this fix: an
        organization exists but has no project. The modal's "Create default
        project" button (POST /api/projects) must unblock them."""
        # Create an org with no project directly (pre-fix state).
        org = Organization(name="Legacy Org", display_name="Legacy Org", slug="legacy-org")
        dp_db.add(org)
        dp_db.commit()
        assert dp_db.query(Project).count() == 0

        # No auth token needed in non-production (pseudo-owner), but send one
        # anyway via a registered user is not possible without re-bootstrapping;
        # here RBAC is permissive in test mode so the call is allowed.
        r = dp_client.post("/api/projects", json={"name": "Default Project"})
        assert r.status_code == 201, r.text

        listing = dp_client.get("/api/projects").json()
        assert any(p["name"] == "Default Project" for p in listing)

    def test_created_project_usable_for_strategy(self, dp_client):
        H = _auth(dp_client, "owner@test.com")
        pid = dp_client.post("/api/projects", json={"name": "Vol Targeting"}, headers=H).json()["id"]
        r = dp_client.post(
            "/api/strategies",
            json={"project_id": pid, "name": "VT Strat", "asset_class": "equity", "status": "active"},
            headers=H,
        )
        assert r.status_code == 201, r.text
