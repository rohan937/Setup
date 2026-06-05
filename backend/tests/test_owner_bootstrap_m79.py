"""Tests for first-user workspace bootstrap + owner repair.

Covers:
  - first registered user on an EMPTY db (no org/members) becomes owner of a
    newly-created default workspace
  - second registered user does not become owner (and no duplicate org)
  - /api/auth/me returns owner permissions for the first user
  - bootstrap_owner service is idempotent and never duplicates the org
  - POST /api/auth/bootstrap-first-owner promotes the current user only while no
    owner exists; blocked once an owner exists
  - create_workspace_member links an existing auth user by email + role support
"""
from __future__ import annotations

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
def boot_engine():
    eng = create_engine(_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def boot_db(boot_engine):
    s = Session(boot_engine)
    yield s
    s.close()


@pytest.fixture()
def boot_client(boot_db):
    """TestClient on an EMPTY db — no organization seeded (the production case)."""
    def _override():
        yield boot_db
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


# ---------------------------------------------------------------------------
# First-user bootstrap (the production fix)
# ---------------------------------------------------------------------------

class TestFirstUserBootstrap:
    def test_first_user_becomes_owner_on_empty_db(self, boot_client, boot_db):
        from app.models.organization import Organization
        from app.models.workspace_member import WorkspaceMember

        assert boot_db.query(Organization).count() == 0
        resp = _register(boot_client, "first@x.com", "First")
        assert resp.status_code == 200, resp.text

        org = boot_db.query(Organization).first()
        assert org is not None
        assert org.name == "Quant Research Workspace"
        assert org.slug == "quant-research-workspace"

        member = boot_db.query(WorkspaceMember).filter_by(email="first@x.com").first()
        assert member is not None
        assert member.role == "owner"
        assert member.status == "active"
        assert member.user_id is not None

    def test_me_returns_owner_permissions_for_first_user(self, boot_client):
        resp = _register(boot_client, "owner@x.com", "Owner")
        token = resp.json()["access_token"]
        me = boot_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        data = me.json()
        assert data["role"] == "owner"
        p = data["permissions"]
        assert p["can_manage_workspace"] is True
        assert p["can_manage_members"] is True
        assert p["can_seed_demo"] is True

    def test_me_resolves_workspace_name_for_bootstrapped_owner(self, boot_client):
        token = _register(boot_client, "owner@x.com", "Owner").json()["access_token"]
        data = boot_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        ).json()
        assert len(data["workspace_memberships"]) >= 1
        ws = data["workspace_memberships"][0]["workspace_name"]
        assert ws == "Quant Research Workspace"
        assert ws != "Unknown"

    def test_me_workspace_name_with_32char_hex_org_id(self, boot_client, boot_db):
        """The production case: workspace_members.organization_id stored as a
        32-char hex string while Organization.id stringifies to 36-char UUID."""
        from app.models.organization import Organization
        from app.models.workspace_member import WorkspaceMember

        token = _register(boot_client, "owner@x.com", "Owner").json()["access_token"]
        org = boot_db.query(Organization).first()
        member = boot_db.query(WorkspaceMember).filter_by(email="owner@x.com").first()
        # Sanity: the membership stores the 32-char hex form (no hyphens).
        assert member.organization_id == org.id.hex
        assert len(member.organization_id) == 32 and "-" not in member.organization_id
        # Give the org a distinct display_name to confirm it is preferred.
        org.display_name = "Acme Research"
        boot_db.commit()

        data = boot_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        ).json()
        assert data["workspace_memberships"][0]["workspace_name"] == "Acme Research"

    def test_me_falls_back_to_name_when_no_display_name(self, boot_client, boot_db):
        from app.models.organization import Organization

        token = _register(boot_client, "owner@x.com", "Owner").json()["access_token"]
        org = boot_db.query(Organization).first()
        org.display_name = None  # force fallback to name
        boot_db.commit()
        data = boot_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        ).json()
        assert data["workspace_memberships"][0]["workspace_name"] == org.name

    def test_second_user_not_owner_and_no_duplicate_org(self, boot_client, boot_db):
        from app.models.organization import Organization
        from app.models.workspace_member import WorkspaceMember

        _register(boot_client, "first@x.com", "First")
        _register(boot_client, "second@x.com", "Second")

        assert boot_db.query(Organization).count() == 1  # no duplicate
        m2 = boot_db.query(WorkspaceMember).filter_by(email="second@x.com").first()
        assert m2 is not None
        assert m2.role != "owner"

    def test_no_duplicate_member_for_same_email(self, boot_client, boot_db):
        from app.models.workspace_member import WorkspaceMember

        _register(boot_client, "dup@x.com", "Dup")
        resp = _register(boot_client, "dup@x.com", "Dup")
        assert resp.status_code == 409
        assert boot_db.query(WorkspaceMember).filter_by(email="dup@x.com").count() == 1


# ---------------------------------------------------------------------------
# bootstrap_owner service (script-backing) — idempotency + linking
# ---------------------------------------------------------------------------

class TestBootstrapOwnerService:
    def test_idempotent_no_duplicate_org_or_member(self, boot_db):
        from app.services.auth_users import bootstrap_owner, register_user
        from app.models.organization import Organization
        from app.models.workspace_member import WorkspaceMember

        user = register_user(boot_db, "broken@x.com", "Broken", "password123")
        boot_db.commit()
        # Emulate the production breakage: user exists, no org / membership.
        boot_db.query(WorkspaceMember).delete()
        boot_db.query(Organization).delete()
        boot_db.commit()
        assert boot_db.query(Organization).count() == 0

        r1 = bootstrap_owner(boot_db, email="broken@x.com", display_name="Broken",
                             require_no_owner=False)
        boot_db.commit()
        r2 = bootstrap_owner(boot_db, email="broken@x.com", display_name="Broken",
                             require_no_owner=False)
        boot_db.commit()

        assert r1["role"] == "owner"
        assert r2["role"] == "owner"
        assert boot_db.query(Organization).count() == 1
        assert boot_db.query(WorkspaceMember).filter_by(email="broken@x.com").count() == 1
        m = boot_db.query(WorkspaceMember).filter_by(email="broken@x.com").first()
        assert m.user_id == str(user.id)  # linked to the existing auth user

    def test_reuses_existing_org(self, boot_db):
        from datetime import datetime, timezone
        from app.services.auth_users import bootstrap_owner
        from app.models.organization import Organization

        now = datetime.now(timezone.utc)
        org = Organization(name="Existing Co", slug="existing-co", created_at=now, updated_at=now)
        boot_db.add(org)
        boot_db.commit()
        bootstrap_owner(boot_db, email="someone@x.com", require_no_owner=False)
        boot_db.commit()
        assert boot_db.query(Organization).count() == 1  # reused, not duplicated


# ---------------------------------------------------------------------------
# bootstrap-first-owner endpoint
# ---------------------------------------------------------------------------

class TestBootstrapEndpoint:
    def test_promotes_current_user_when_no_owner(self, boot_client, boot_db):
        from app.models.workspace_member import WorkspaceMember
        from app.models.organization import Organization

        token = _register(boot_client, "fixme@x.com", "Fix Me").json()["access_token"]
        boot_db.query(WorkspaceMember).delete()
        boot_db.query(Organization).delete()
        boot_db.commit()

        resp = boot_client.post(
            "/api/auth/bootstrap-first-owner",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == "owner"
        assert resp.json()["permissions"]["can_manage_members"] is True

    def test_blocked_once_owner_exists(self, boot_client):
        _register(boot_client, "theowner@x.com", "The Owner")
        token2 = _register(boot_client, "intruder@x.com", "Intruder").json()["access_token"]
        resp = boot_client.post(
            "/api/auth/bootstrap-first-owner",
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert resp.status_code == 409, resp.text

    def test_requires_auth(self, boot_client):
        resp = boot_client.post("/api/auth/bootstrap-first-owner")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Member creation links existing users + role support
# ---------------------------------------------------------------------------

class TestMemberCreation:
    def test_owner_can_add_roles_and_link_existing_user(self, boot_client, boot_db):
        from app.services.auth_users import register_user
        from app.models.workspace_member import WorkspaceMember

        _register(boot_client, "owner@x.com", "Owner")
        # An existing auth user who is NOT yet a member (membership removed).
        existing = register_user(boot_db, "analyst@x.com", "Analyst", "password123")
        boot_db.commit()
        boot_db.query(WorkspaceMember).filter_by(email="analyst@x.com").delete()
        boot_db.commit()

        # Owner can add members in all four roles.
        for role in ("admin", "member", "viewer"):
            resp = boot_client.post(
                "/api/workspace/members",
                json={"display_name": f"{role} person", "email": f"{role}@x.com", "role": role},
            )
            assert resp.status_code == 201, resp.text
            assert resp.json()["role"] == role

        # Adding an existing auth user by email links their user_id.
        resp = boot_client.post(
            "/api/workspace/members",
            json={"display_name": "Analyst", "email": "analyst@x.com", "role": "member"},
        )
        assert resp.status_code == 201, resp.text
        m = boot_db.query(WorkspaceMember).filter_by(email="analyst@x.com").first()
        assert m.user_id == str(existing.id)
