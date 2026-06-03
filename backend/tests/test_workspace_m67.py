"""M67 tests: Workspace Settings + Members Foundation.

Tests for:
  GET    /api/workspace/settings            — workspace summary
  PATCH  /api/workspace/settings            — update workspace settings
  GET    /api/workspace/members             — list members, filter by status
  POST   /api/workspace/members             — create, duplicate email, bad role/status/email
  PATCH  /api/workspace/members/{id}        — update role and status
  DELETE /api/workspace/members/{id}        — soft-delete, last-owner guard
  Timeline events for member add and settings update
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.core.constants import EventType
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.organization import Organization
from app.models.workspace_member import WorkspaceMember


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_org(db):
    return db.query(Organization).first()


def _create_member(client, *, display_name=None, email=None, role="member", status="active",
                   title=None, notes=None):
    payload = {
        "display_name": display_name or f"Test User {uuid.uuid4().hex[:6]}",
        "email": email or f"test-{uuid.uuid4().hex[:8]}@example.com",
        "role": role,
        "status": status,
    }
    if title is not None:
        payload["title"] = title
    if notes is not None:
        payload["notes"] = notes
    return client.post("/api/workspace/members", json=payload)


def _cleanup_member(db, member_id):
    if isinstance(member_id, str):
        try:
            member_id_uuid = uuid.UUID(member_id)
        except ValueError:
            member_id_uuid = None
    else:
        member_id_uuid = member_id

    # Try both str and UUID matching
    m = db.query(WorkspaceMember).filter(WorkspaceMember.id == member_id_uuid).first()
    if m is None:
        m = db.query(WorkspaceMember).filter(WorkspaceMember.id == str(member_id)).first()
    if m is not None:
        db.delete(m)
        db.commit()


# ---------------------------------------------------------------------------
# TestWorkspaceSettings
# ---------------------------------------------------------------------------

class TestWorkspaceSettings:
    def test_get_settings_returns_org(self, client, db):
        resp = client.get("/api/workspace/settings")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "workspace_id" in data
        assert data["workspace_id"] is not None
        assert "workspace_name" in data
        assert isinstance(data["workspace_name"], str)
        assert len(data["workspace_name"]) > 0

    def test_get_settings_includes_projects(self, client, db):
        resp = client.get("/api/workspace/settings")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "projects" in data
        assert isinstance(data["projects"], list)

    def test_patch_settings_updates_display_name(self, client, db):
        org = _get_org(db)
        assert org is not None
        new_name = f"Display Name {uuid.uuid4().hex[:6]}"
        resp = client.patch(
            "/api/workspace/settings",
            json={"display_name": new_name},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["display_name"] == new_name
        # Restore
        db.refresh(org)

    def test_patch_settings_updates_description(self, client, db):
        org = _get_org(db)
        assert org is not None
        new_desc = f"A test description {uuid.uuid4().hex[:8]}"
        resp = client.patch(
            "/api/workspace/settings",
            json={"description": new_desc},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["description"] == new_desc
        db.refresh(org)

    def test_workspace_summary_counts(self, client, db):
        resp = client.get("/api/workspace/settings")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        for key in ("project_count", "strategy_count", "member_count",
                    "active_member_count", "api_key_count"):
            assert isinstance(data[key], int), f"{key} should be int, got {data[key]!r}"
            assert data[key] >= 0


# ---------------------------------------------------------------------------
# TestWorkspaceMembers
# ---------------------------------------------------------------------------

class TestWorkspaceMembers:
    def test_list_members_empty(self, client, db):
        """Members endpoint returns a valid list structure."""
        resp = client.get("/api/workspace/members")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)
        assert data["total"] == len(data["items"])

    def test_create_member_success(self, client, db):
        resp = _create_member(client)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "id" in data
        assert data["role"] == "member"
        assert data["status"] == "active"
        _cleanup_member(db, data["id"])

    def test_create_member_duplicate_email_409(self, client, db):
        email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
        resp1 = _create_member(client, email=email)
        assert resp1.status_code == 201, resp1.text
        member_id = resp1.json()["id"]
        try:
            resp2 = _create_member(client, email=email)
            assert resp2.status_code == 409, f"Expected 409, got {resp2.status_code}: {resp2.text}"
        finally:
            _cleanup_member(db, member_id)

    def test_create_member_invalid_role(self, client, db):
        resp = _create_member(client, role="superuser")
        assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}"

    def test_create_member_invalid_status(self, client, db):
        resp = _create_member(client, status="pending")
        assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}"

    def test_create_member_invalid_email(self, client, db):
        resp = _create_member(client, email="not-an-email")
        assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}"

    def test_update_member_role(self, client, db):
        resp = _create_member(client, role="member")
        assert resp.status_code == 201, resp.text
        member_id = resp.json()["id"]
        try:
            patch_resp = client.patch(
                f"/api/workspace/members/{member_id}",
                json={"role": "admin"},
            )
            assert patch_resp.status_code == 200, patch_resp.text
            data = patch_resp.json()
            assert data["role"] == "admin"
        finally:
            _cleanup_member(db, member_id)

    def test_update_member_status(self, client, db):
        resp = _create_member(client)
        assert resp.status_code == 201, resp.text
        member_id = resp.json()["id"]
        try:
            patch_resp = client.patch(
                f"/api/workspace/members/{member_id}",
                json={"status": "disabled"},
            )
            assert patch_resp.status_code == 200, patch_resp.text
            data = patch_resp.json()
            assert data["status"] == "disabled"
        finally:
            _cleanup_member(db, member_id)

    def test_remove_member_disables(self, client, db):
        resp = _create_member(client)
        assert resp.status_code == 201, resp.text
        member_id = resp.json()["id"]
        try:
            del_resp = client.delete(f"/api/workspace/members/{member_id}")
            assert del_resp.status_code == 200, del_resp.text
            data = del_resp.json()
            assert data.get("success") is True

            # Verify status is now disabled
            list_resp = client.get("/api/workspace/members")
            assert list_resp.status_code == 200
            items = list_resp.json()["items"]
            matching = [i for i in items if str(i["id"]) == str(member_id)]
            if matching:
                assert matching[0]["status"] == "disabled"
        finally:
            _cleanup_member(db, member_id)

    def test_cannot_remove_last_owner(self, client, db):
        # Create an owner member
        resp = _create_member(client, role="owner")
        assert resp.status_code == 201, resp.text
        member_id = resp.json()["id"]
        try:
            # Attempt to remove the only owner — should return 400
            del_resp = client.delete(f"/api/workspace/members/{member_id}")
            assert del_resp.status_code == 400, (
                f"Expected 400 for last owner removal, got {del_resp.status_code}: {del_resp.text}"
            )
        finally:
            # Force-remove for cleanup (bypass service check)
            m = db.query(WorkspaceMember).filter(
                WorkspaceMember.id == uuid.UUID(member_id)
            ).first()
            if m is None:
                m = db.query(WorkspaceMember).filter(
                    WorkspaceMember.id == member_id
                ).first()
            if m is not None:
                db.delete(m)
                db.commit()

    def test_list_members_filter_by_status(self, client, db):
        # Create two members: one active, one invited
        resp_a = _create_member(client, status="active")
        resp_i = _create_member(client, status="invited")
        assert resp_a.status_code == 201, resp_a.text
        assert resp_i.status_code == 201, resp_i.text
        id_a = resp_a.json()["id"]
        id_i = resp_i.json()["id"]
        try:
            # Filter for active
            active_resp = client.get("/api/workspace/members?status=active")
            assert active_resp.status_code == 200, active_resp.text
            active_items = active_resp.json()["items"]
            assert all(item["status"] == "active" for item in active_items)

            # Filter for invited
            invited_resp = client.get("/api/workspace/members?status=invited")
            assert invited_resp.status_code == 200, invited_resp.text
            invited_items = invited_resp.json()["items"]
            assert all(item["status"] == "invited" for item in invited_items)
            invited_ids = [str(i["id"]) for i in invited_items]
            assert str(id_i) in invited_ids
        finally:
            _cleanup_member(db, id_a)
            _cleanup_member(db, id_i)


# ---------------------------------------------------------------------------
# TestWorkspaceTimeline
# ---------------------------------------------------------------------------

class TestWorkspaceTimeline:
    def test_member_add_creates_timeline_event(self, client, db):
        resp = _create_member(client)
        assert resp.status_code == 201, resp.text
        member_id = resp.json()["id"]
        try:
            events = db.query(AuditTimelineEvent).filter(
                AuditTimelineEvent.event_type == EventType.workspace_member_added,
                AuditTimelineEvent.source_id == member_id,
            ).all()
            assert len(events) >= 1, (
                f"Expected at least one workspace_member_added event for {member_id}"
            )
        finally:
            _cleanup_member(db, member_id)

    def test_settings_update_creates_timeline_event(self, client, db):
        org = _get_org(db)
        assert org is not None

        before_count = db.query(AuditTimelineEvent).filter(
            AuditTimelineEvent.event_type == EventType.workspace_settings_updated,
        ).count()

        resp = client.patch(
            "/api/workspace/settings",
            json={"display_name": f"Timeline Test {uuid.uuid4().hex[:6]}"},
        )
        assert resp.status_code == 200, resp.text

        after_count = db.query(AuditTimelineEvent).filter(
            AuditTimelineEvent.event_type == EventType.workspace_settings_updated,
        ).count()
        assert after_count > before_count, (
            "Expected a workspace_settings_updated timeline event to be created"
        )
