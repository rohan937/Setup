"""M67 Workspace Settings + Members Foundation service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.api_key import ApiKey
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.organization import Organization
from app.models.project import Project
from app.models.strategy import Strategy
from app.models.workspace_member import WorkspaceMember
from app.core.constants import EventType

VALID_ROLES = {"owner", "admin", "member", "viewer"}
VALID_STATUSES = {"active", "invited", "disabled"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _default_org(db: Session) -> Organization | None:
    return db.query(Organization).order_by(Organization.created_at).first()


def _create_timeline_event(
    db: Session,
    org: Organization,
    event_type: EventType,
    title: str,
    source_id: str,
    metadata_json: dict[str, Any] | None,
) -> None:
    try:
        project = (
            db.query(Project)
            .filter(Project.organization_id == org.id)
            .order_by(Project.created_at)
            .first()
        )
        event = AuditTimelineEvent(
            organization_id=org.id,
            project_id=project.id if project else None,
            event_type=str(event_type),
            title=title,
            source_type="workspace",
            source_id=source_id,
            severity="info",
            event_time=datetime.now(timezone.utc),
            metadata_json=metadata_json,
        )
        db.add(event)
        db.flush()
    except Exception:
        pass


def _validate_email(email: str) -> bool:
    return "@" in email and len(email) > 3


# ---------------------------------------------------------------------------
# Workspace summary
# ---------------------------------------------------------------------------

def get_workspace_summary(db: Session) -> dict:
    org = _default_org(db)
    if org is None:
        return {
            "workspace_id": None,
            "workspace_name": "No workspace found",
            "display_name": None,
            "description": None,
            "website": None,
            "project_count": 0,
            "strategy_count": 0,
            "member_count": 0,
            "active_member_count": 0,
            "api_key_count": 0,
            "created_at": None,
            "updated_at": None,
            "projects": [],
            "readiness_note": "No organization found. Seed demo data to create a workspace.",
        }

    projects = (
        db.query(Project).filter(Project.organization_id == org.id).all()
    )
    project_ids = [p.id for p in projects]

    if project_ids:
        strategy_count = (
            db.query(Strategy)
            .filter(Strategy.project_id.in_(project_ids))
            .count()
        )
    else:
        strategy_count = 0

    org_id_str = str(org.id)
    member_count = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.organization_id == org_id_str)
        .count()
    )
    active_member_count = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.organization_id == org_id_str,
            WorkspaceMember.status == "active",
        )
        .count()
    )
    api_key_count = (
        db.query(ApiKey)
        .filter(ApiKey.organization_id == org_id_str)
        .count()
    )

    projects_list = []
    for p in projects:
        s_count = (
            db.query(Strategy).filter(Strategy.project_id == p.id).count()
        )
        projects_list.append(
            {
                "project_id": str(p.id),
                "name": p.name,
                "strategy_count": s_count,
                "created_at": p.created_at,
            }
        )

    return {
        "workspace_id": str(org.id),
        "workspace_name": org.name,
        "display_name": getattr(org, "display_name", None),
        "description": getattr(org, "description", None),
        "website": getattr(org, "website", None),
        "project_count": len(projects),
        "strategy_count": strategy_count,
        "member_count": member_count,
        "active_member_count": active_member_count,
        "api_key_count": api_key_count,
        "created_at": org.created_at,
        "updated_at": org.updated_at,
        "projects": projects_list,
        "readiness_note": "",
    }


# ---------------------------------------------------------------------------
# Workspace settings
# ---------------------------------------------------------------------------

def get_workspace_settings(
    db: Session, organization_id: str | None = None
) -> Organization | None:
    if organization_id is not None:
        import uuid as _uuid
        try:
            org_uuid = _uuid.UUID(str(organization_id))
        except (ValueError, AttributeError):
            org_uuid = organization_id  # type: ignore[assignment]
        return (
            db.query(Organization)
            .filter(Organization.id == org_uuid)
            .first()
        )
    return _default_org(db)


def update_workspace_settings(
    db: Session, organization_id: str, payload: dict
) -> Organization:
    import uuid as _uuid
    try:
        org_uuid = _uuid.UUID(str(organization_id))
    except (ValueError, AttributeError):
        org_uuid = organization_id  # type: ignore[assignment]
    org = db.query(Organization).filter(Organization.id == org_uuid).first()
    if org is None:
        raise ValueError(f"Organization {organization_id} not found")

    if "display_name" in payload and payload["display_name"] is not None:
        org.display_name = payload["display_name"]
    if "description" in payload and payload["description"] is not None:
        org.description = payload["description"]
    if "website" in payload and payload["website"] is not None:
        org.website = payload["website"]

    org.updated_at = datetime.now(timezone.utc)
    db.flush()

    _create_timeline_event(
        db,
        org,
        EventType.workspace_settings_updated,
        f"Workspace settings updated: {org.name}",
        str(org.id),
        {k: v for k, v in payload.items() if v is not None},
    )
    return org


# ---------------------------------------------------------------------------
# Workspace members
# ---------------------------------------------------------------------------

def get_workspace_members(
    db: Session, organization_id: str, status: str | None = None
) -> list[WorkspaceMember]:
    q = db.query(WorkspaceMember).filter(
        WorkspaceMember.organization_id == str(organization_id)
    )
    if status is not None:
        q = q.filter(WorkspaceMember.status == status)
    return q.order_by(WorkspaceMember.created_at.asc()).all()


def create_workspace_member(
    db: Session, organization_id: str, payload: dict
) -> WorkspaceMember:
    import uuid as _uuid
    try:
        org_uuid = _uuid.UUID(str(organization_id))
    except (ValueError, AttributeError):
        org_uuid = organization_id  # type: ignore[assignment]
    org = db.query(Organization).filter(Organization.id == org_uuid).first()
    if org is None:
        raise ValueError(f"Organization {organization_id} not found")

    email = payload.get("email", "")
    if not _validate_email(email):
        raise ValueError("invalid email")

    existing = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.organization_id == str(organization_id),
            WorkspaceMember.email == email,
        )
        .first()
    )
    if existing is not None:
        raise ValueError("duplicate email")

    role = payload.get("role", "member")
    if role not in VALID_ROLES:
        raise ValueError(f"invalid role: {role!r}")

    status = payload.get("status", "active")
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status!r}")

    now = datetime.now(timezone.utc)
    member = WorkspaceMember(
        organization_id=str(organization_id),
        display_name=payload["display_name"],
        email=email,
        role=role,
        status=status,
        title=payload.get("title"),
        notes=payload.get("notes"),
        created_at=now,
        updated_at=now,
    )
    db.add(member)
    db.flush()

    _create_timeline_event(
        db,
        org,
        EventType.workspace_member_added,
        f"Workspace member added: {member.display_name} ({member.email})",
        str(member.id),
        {"email": email, "role": role, "status": status},
    )
    return member


def _member_uuid(member_id: str):
    import uuid as _uuid
    try:
        return _uuid.UUID(str(member_id))
    except (ValueError, AttributeError):
        return member_id


def update_workspace_member(
    db: Session, member_id: str, payload: dict
) -> WorkspaceMember:
    member = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.id == _member_uuid(member_id))
        .first()
    )
    if member is None:
        raise ValueError(f"WorkspaceMember {member_id} not found")

    if "display_name" in payload and payload["display_name"] is not None:
        member.display_name = payload["display_name"]
    if "email" in payload and payload["email"] is not None:
        member.email = payload["email"]
    if "role" in payload and payload["role"] is not None:
        role = payload["role"]
        if role not in VALID_ROLES:
            raise ValueError(f"invalid role: {role!r}")
        member.role = role
    if "status" in payload and payload["status"] is not None:
        status = payload["status"]
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {status!r}")
        member.status = status
    if "title" in payload:
        member.title = payload["title"]
    if "notes" in payload:
        member.notes = payload["notes"]

    member.updated_at = datetime.now(timezone.utc)
    db.flush()

    import uuid as _uuid
    try:
        org_uuid_for_update = _uuid.UUID(str(member.organization_id))
    except (ValueError, AttributeError):
        org_uuid_for_update = member.organization_id  # type: ignore[assignment]
    org = (
        db.query(Organization)
        .filter(Organization.id == org_uuid_for_update)
        .first()
    )
    if org is not None:
        _create_timeline_event(
            db,
            org,
            EventType.workspace_member_updated,
            f"Workspace member updated: {member.display_name} ({member.email})",
            str(member.id),
            {k: v for k, v in payload.items() if v is not None},
        )
    return member


def remove_workspace_member(db: Session, member_id: str) -> bool:
    member = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.id == _member_uuid(member_id))
        .first()
    )
    if member is None:
        raise ValueError(f"WorkspaceMember {member_id} not found")

    if member.role == "owner":
        member_uuid = _member_uuid(member_id)
        other_owners = (
            db.query(WorkspaceMember)
            .filter(
                WorkspaceMember.organization_id == member.organization_id,
                WorkspaceMember.role == "owner",
                WorkspaceMember.id != member_uuid,
                WorkspaceMember.status != "disabled",
            )
            .count()
        )
        if other_owners == 0:
            raise ValueError("cannot remove last owner")

    import uuid as _uuid
    try:
        org_uuid_for_remove = _uuid.UUID(str(member.organization_id))
    except (ValueError, AttributeError):
        org_uuid_for_remove = member.organization_id  # type: ignore[assignment]
    org = (
        db.query(Organization)
        .filter(Organization.id == org_uuid_for_remove)
        .first()
    )

    member.status = "disabled"
    member.updated_at = datetime.now(timezone.utc)
    db.flush()

    if org is not None:
        _create_timeline_event(
            db,
            org,
            EventType.workspace_member_removed,
            f"Workspace member removed: {member.display_name} ({member.email})",
            str(member.id),
            {"email": member.email, "role": member.role},
        )
    return True
