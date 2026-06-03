"""Auth user service: registration, login, and workspace linking (M68)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.auth_user import AuthUser
from app.models.organization import Organization
from app.models.workspace_member import WorkspaceMember


def get_user_by_email(db: Session, email: str) -> AuthUser | None:
    return db.query(AuthUser).filter(
        AuthUser.email == email.lower().strip()
    ).first()


def get_user(db: Session, user_id: str) -> AuthUser | None:
    return db.query(AuthUser).filter(AuthUser.id == user_id).first()


def register_user(
    db: Session, email: str, display_name: str, password: str
) -> AuthUser:
    email = email.lower().strip()
    if len(password) < 8:
        raise ValueError("password too short")
    if get_user_by_email(db, email):
        raise ValueError("duplicate email")
    hashed = hash_password(password)
    now = datetime.now(timezone.utc)
    # AuthUser.id comes from UUIDPrimaryKeyMixin (Uuid as_uuid=True).
    # Pass a real uuid.UUID, not a string.
    user = AuthUser(
        id=uuid.uuid4(),
        email=email,
        display_name=display_name,
        hashed_password=hashed,
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    _link_or_create_member(db, user)
    _create_timeline_event(db, user, "user_registered", "User registered")
    return user


def authenticate_user(db: Session, email: str, password: str) -> AuthUser:
    user = get_user_by_email(db, email)
    if not user:
        raise ValueError("invalid credentials")
    if not verify_password(password, user.hashed_password):
        raise ValueError("invalid credentials")
    if user.status != "active":
        raise ValueError("account disabled")
    user.last_login_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    db.flush()
    return user


def _link_or_create_member(db: Session, user: AuthUser) -> None:
    org = db.query(Organization).order_by(Organization.created_at).first()
    if not org:
        return
    # WorkspaceMember.organization_id is String(36) — use str(org.id)
    org_id_str = str(org.id)
    existing_member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.organization_id == org_id_str,
            WorkspaceMember.email == user.email,
        )
        .first()
    )
    if existing_member:
        existing_member.user_id = str(user.id)
        existing_member.updated_at = datetime.now(timezone.utc)
        db.flush()
        return
    is_first_user = db.query(AuthUser).count() <= 1
    role = "owner" if is_first_user else "member"
    now = datetime.now(timezone.utc)
    # WorkspaceMember.id uses UUIDPrimaryKeyMixin — omit id to use the default.
    member = WorkspaceMember(
        organization_id=org_id_str,
        display_name=user.display_name,
        email=user.email,
        role=role,
        status="active",
        user_id=str(user.id),
        created_at=now,
        updated_at=now,
    )
    db.add(member)
    db.flush()


def _create_timeline_event(
    db: Session, user: AuthUser, event_type_value: str, title: str
) -> None:
    try:
        org = db.query(Organization).order_by(Organization.created_at).first()
        if not org:
            return
        now = datetime.now(timezone.utc)
        # AuditTimelineEvent.id uses UUIDPrimaryKeyMixin — omit to use default.
        event = AuditTimelineEvent(
            strategy_id=None,
            organization_id=org.id,  # Uuid(as_uuid=True) column — pass uuid.UUID
            project_id=None,
            event_type=event_type_value,
            source_type="user",
            source_id=str(user.id),
            severity="info",
            title=title,
            description=None,
            metadata_json={"user_id": str(user.id), "email": user.email},
            event_time=now,
            created_at=now,
        )
        db.add(event)
        db.flush()
    except Exception:
        # Timeline events are informational — never crash auth operations.
        pass
