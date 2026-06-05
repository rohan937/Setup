"""Stage 4 RBAC action audit tests.

Covers:
  1. Production pseudo-owner loophole: unauthenticated requests get 401 in
     production (QF_ENVIRONMENT=production), not pseudo-owner access.
  2. Last-owner demotion guard: cannot PATCH the last owner to a lower role.
  3. Alert mutations require write access.
  4. Report generation requires write access.
  5. Review-case acknowledge/resolve require write access.
  6. Reliability-snapshot refresh requires write access.
  7. API key CRUD requires can_manage_api_keys (owner/admin only).
  8. Seed demo requires can_seed_demo (owner/admin only).
  9. Viewer cannot write-mutate guarded routes.
 10. Unauthenticated calls to guarded routes return 401 in production mode.

All tests use isolated in-memory DBs so the shared session DB is untouched.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

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


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def action_engine():
    eng = create_engine(_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def action_db(action_engine):
    s = Session(action_engine)
    yield s
    s.close()


@pytest.fixture()
def action_client(action_db):
    """TestClient on an isolated DB — no org seeded (non-production env)."""
    def _override():
        yield action_db
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


def _make_viewer_token(client, db) -> str:
    from app.models.workspace_member import WorkspaceMember
    # Owner must exist first.
    _register(client, f"owner-{uuid.uuid4().hex[:6]}@test.com", "Owner")
    email = f"viewer-{uuid.uuid4().hex[:8]}@test.com"
    resp = _register(client, email, "Viewer")
    assert resp.status_code == 200, resp.text
    member = db.query(WorkspaceMember).filter(WorkspaceMember.email == email).first()
    member.role = "viewer"
    db.commit()
    return resp.json()["access_token"]


def _seed_org_and_strategy(db) -> tuple:
    from app.models.organization import Organization
    from app.models.project import Project
    from app.models.strategy import Strategy
    now = datetime.now(timezone.utc)
    org = Organization(name="Action WS", slug="action-ws", created_at=now, updated_at=now)
    db.add(org)
    db.flush()
    proj = Project(organization_id=org.id, name="Action P", slug="action-p",
                   created_at=now, updated_at=now)
    db.add(proj)
    db.flush()
    strat = Strategy(project_id=proj.id, name="Action Strat",
                     slug="action-strat", asset_class="equity", status="active")
    db.add(strat)
    db.flush()
    db.commit()
    return org, strat


# ---------------------------------------------------------------------------
# 1. Production pseudo-owner loophole
# ---------------------------------------------------------------------------

class TestProductionPseudoOwnerFix:
    """In production mode, unauthenticated callers must get 401 not pseudo-owner."""

    def test_unauthenticated_guarded_route_is_401_in_production(
        self, action_client, action_db, monkeypatch
    ):
        from app.core import config as cfg
        monkeypatch.setenv("QF_ENVIRONMENT", "production")
        cfg.get_settings.cache_clear()
        try:
            # No Authorization header → must be 401, not 200/201.
            resp = action_client.post("/api/alerts/generate")
            assert resp.status_code == 401, f"expected 401, got {resp.status_code}"
        finally:
            cfg.get_settings.cache_clear()

    def test_unauthenticated_seed_demo_is_401_in_production(
        self, action_client, monkeypatch
    ):
        from app.core import config as cfg
        monkeypatch.setenv("QF_ENVIRONMENT", "production")
        cfg.get_settings.cache_clear()
        try:
            resp = action_client.post(
                "/api/admin/seed-demo",
                json={"mode": "extend"},
            )
            assert resp.status_code == 401, f"expected 401, got {resp.status_code}"
        finally:
            cfg.get_settings.cache_clear()

    def test_authenticated_owner_not_blocked_in_production(
        self, action_client, action_db, monkeypatch
    ):
        from app.core import config as cfg
        # Bootstrap an owner so auth works.
        token = _register(action_client, "prod-owner@test.com", "Prod Owner").json()["access_token"]
        monkeypatch.setenv("QF_ENVIRONMENT", "production")
        cfg.get_settings.cache_clear()
        try:
            # Authenticated owner should still work.
            resp = action_client.post(
                "/api/admin/seed-demo",
                json={"mode": "extend"},
                headers={"Authorization": f"Bearer {token}"},
            )
            # 200 or 4xx for missing org is fine — NOT 401.
            assert resp.status_code != 401
        finally:
            cfg.get_settings.cache_clear()

    def test_non_production_unauthenticated_still_gets_pseudo_owner(
        self, action_client
    ):
        """Non-production env keeps the local-dev pseudo-owner behavior."""
        # In non-production, no token → pseudo-owner → can call guarded route.
        # POST /api/alerts/generate with no org will 404 on "No organisation found",
        # but NOT 401 (pseudo-owner passes the RBAC check).
        resp = action_client.post("/api/alerts/generate")
        assert resp.status_code != 401, "non-prod should not require auth"


# ---------------------------------------------------------------------------
# 2. Last-owner demotion guard
# ---------------------------------------------------------------------------

class TestLastOwnerDemotionGuard:
    def test_cannot_demote_last_owner(self, action_client, action_db):
        token = _register(action_client, "owner@test.com", "Owner").json()["access_token"]
        from app.models.workspace_member import WorkspaceMember
        member = action_db.query(WorkspaceMember).filter_by(email="owner@test.com").first()
        assert member.role == "owner"

        resp = action_client.patch(
            f"/api/workspace/members/{member.id}",
            json={"role": "member"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400, f"expected 400 last-owner guard, got {resp.status_code}"
        assert "last owner" in resp.json().get("detail", "").lower()

    def test_can_demote_owner_when_another_exists(self, action_client, action_db):
        from app.models.workspace_member import WorkspaceMember
        from app.services.auth_users import register_user

        token = _register(action_client, "owner1@test.com", "Owner1").json()["access_token"]
        # Create a second owner directly.
        user2 = register_user(action_db, "owner2@test.com", "Owner2", "password123")
        action_db.commit()
        from app.models.organization import Organization
        org = action_db.query(Organization).first()
        from app.services.workspaces import _org_id_str
        m2 = WorkspaceMember(
            organization_id=_org_id_str(org.id),
            display_name="Owner2",
            email="owner2@test.com",
            role="owner",
            status="active",
            user_id=str(user2.id),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        action_db.add(m2)
        action_db.commit()

        member1 = action_db.query(WorkspaceMember).filter_by(email="owner1@test.com").first()
        resp = action_client.patch(
            f"/api/workspace/members/{member1.id}",
            json={"role": "admin"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == "admin"

    def test_cannot_remove_last_owner(self, action_client, action_db):
        token = _register(action_client, "owner@test.com", "Owner").json()["access_token"]
        from app.models.workspace_member import WorkspaceMember
        member = action_db.query(WorkspaceMember).filter_by(email="owner@test.com").first()

        resp = action_client.delete(
            f"/api/workspace/members/{member.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (400, 422), f"expected 4xx last-owner guard, got {resp.status_code}"
        detail = resp.json().get("detail", "").lower()
        assert "last owner" in detail or "owner" in detail


# ---------------------------------------------------------------------------
# 3. Alert mutations require write access
# ---------------------------------------------------------------------------

class TestAlertMutationRBAC:
    def test_viewer_cannot_generate_alerts(self, action_client, action_db):
        token = _make_viewer_token(action_client, action_db)
        resp = action_client.post(
            "/api/alerts/generate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_viewer_cannot_update_alert_status(self, action_client, action_db):
        token = _make_viewer_token(action_client, action_db)
        fake_id = uuid.uuid4()
        resp = action_client.patch(
            f"/api/alerts/{fake_id}",
            json={"status": "acknowledged"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # 403 because viewer is blocked before we even look up the alert.
        assert resp.status_code == 403, resp.text

    def test_owner_can_call_generate_alerts(self, action_client):
        token = _register(action_client, "owner@test.com", "Owner").json()["access_token"]
        resp = action_client.post(
            "/api/alerts/generate",
            headers={"Authorization": f"Bearer {token}"},
        )
        # 404 "No organisation found" is acceptable — it passed RBAC.
        assert resp.status_code != 403, resp.text
        assert resp.status_code != 401, resp.text


# ---------------------------------------------------------------------------
# 4. Report generation requires write access
# ---------------------------------------------------------------------------

class TestReportGenerationRBAC:
    def test_viewer_cannot_generate_strategy_report(self, action_client, action_db):
        token = _make_viewer_token(action_client, action_db)
        fake_id = uuid.uuid4()
        resp = action_client.post(
            f"/api/reports/strategy/{fake_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_viewer_cannot_generate_backtest_report(self, action_client, action_db):
        token = _make_viewer_token(action_client, action_db)
        fake_id = uuid.uuid4()
        resp = action_client.post(
            f"/api/reports/backtest-audit/{fake_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_viewer_cannot_generate_snapshot_report(self, action_client, action_db):
        token = _make_viewer_token(action_client, action_db)
        fake_id = uuid.uuid4()
        resp = action_client.post(
            f"/api/reports/dataset-snapshot/{fake_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_owner_can_generate_report(self, action_client, action_db):
        token = _register(action_client, "owner@test.com", "Owner").json()["access_token"]
        _, strat = _seed_org_and_strategy(action_db)
        resp = action_client.post(
            f"/api/reports/strategy/{strat.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        # RBAC passes; may succeed or return 4xx for strategy reasons.
        assert resp.status_code not in (401, 403), resp.text


# ---------------------------------------------------------------------------
# 5. Review case acknowledge/resolve require write access
# ---------------------------------------------------------------------------

class TestReviewCaseMutationRBAC:
    def test_viewer_cannot_acknowledge_review_case(self, action_client, action_db):
        token = _make_viewer_token(action_client, action_db)
        fake_id = uuid.uuid4()
        resp = action_client.post(
            f"/api/review-cases/{fake_id}/acknowledge",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_viewer_cannot_resolve_review_case(self, action_client, action_db):
        token = _make_viewer_token(action_client, action_db)
        fake_id = uuid.uuid4()
        resp = action_client.post(
            f"/api/review-cases/{fake_id}/resolve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_owner_can_call_acknowledge(self, action_client):
        token = _register(action_client, "owner@test.com", "Owner").json()["access_token"]
        fake_id = uuid.uuid4()
        resp = action_client.post(
            f"/api/review-cases/{fake_id}/acknowledge",
            headers={"Authorization": f"Bearer {token}"},
        )
        # RBAC passes; 404 for nonexistent case is expected.
        assert resp.status_code in (404, 200), resp.text
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# 6. Reliability snapshot refresh requires write access
# ---------------------------------------------------------------------------

class TestSnapshotRefreshRBAC:
    def test_viewer_cannot_refresh_snapshot(self, action_client, action_db):
        token = _make_viewer_token(action_client, action_db)
        fake_id = uuid.uuid4()
        resp = action_client.post(
            f"/api/strategies/{fake_id}/reliability-snapshot/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_owner_can_refresh_snapshot(self, action_client, action_db):
        token = _register(action_client, "owner@test.com", "Owner").json()["access_token"]
        _, strat = _seed_org_and_strategy(action_db)
        resp = action_client.post(
            f"/api/strategies/{strat.id}/reliability-snapshot/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        # RBAC passes; may succeed or return 4xx for data reasons.
        assert resp.status_code not in (401, 403), resp.text


# ---------------------------------------------------------------------------
# 7. API key CRUD requires can_manage_api_keys
# ---------------------------------------------------------------------------

class TestApiKeyRBAC:
    def test_viewer_cannot_create_api_key(self, action_client, action_db):
        token = _make_viewer_token(action_client, action_db)
        resp = action_client.post(
            "/api/api-keys",
            json={"name": "my-key", "project_id": None},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_member_cannot_create_api_key(self, action_client, action_db):
        from app.models.workspace_member import WorkspaceMember
        _register(action_client, f"owner-{uuid.uuid4().hex[:6]}@test.com", "Owner")
        email = f"member-{uuid.uuid4().hex[:8]}@test.com"
        token = _register(action_client, email, "Member").json()["access_token"]
        # Second user is automatically "member"
        resp = action_client.post(
            "/api/api-keys",
            json={"name": "my-key", "project_id": None},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_owner_can_create_api_key(self, action_client):
        token = _register(action_client, "owner@test.com", "Owner").json()["access_token"]
        resp = action_client.post(
            "/api/api-keys",
            json={"name": "my-key", "project_id": None},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code not in (401, 403), resp.text

    def test_api_key_list_does_not_expose_secret(self, action_client):
        token = _register(action_client, "owner@test.com", "Owner").json()["access_token"]
        # Create a key.
        action_client.post(
            "/api/api-keys",
            json={"name": "test-key"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # List should not contain raw_key or hash.
        resp = action_client.get(
            "/api/api-keys",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        for item in resp.json().get("items", []):
            assert "raw_key" not in item
            assert "hashed_key" not in item


# ---------------------------------------------------------------------------
# 8. Demo seed requires can_seed_demo
# ---------------------------------------------------------------------------

class TestDemoSeedRBAC:
    def test_viewer_cannot_seed_demo(self, action_client, action_db):
        token = _make_viewer_token(action_client, action_db)
        resp = action_client.post(
            "/api/admin/seed-demo",
            json={"mode": "extend"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_owner_can_seed_demo(self, action_client):
        token = _register(action_client, "owner@test.com", "Owner").json()["access_token"]
        resp = action_client.post(
            "/api/admin/seed-demo",
            json={"mode": "extend"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code not in (401, 403), resp.text

    def test_advanced_demo_seed_requires_can_seed_demo(self, action_client, action_db):
        token = _make_viewer_token(action_client, action_db)
        resp = action_client.post(
            "/api/admin/demo/advanced-strategy",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text
