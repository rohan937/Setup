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


def _org_id_for_member(org: Organization) -> str:
    """Return the organization ID in the format SQLAlchemy stores it on SQLite.

    Root cause of the registration FK bug
    --------------------------------------
    SQLAlchemy 2.0's ``Uuid(as_uuid=True)`` stores UUIDs on SQLite as a
    32-char hex string **without hyphens** (e.g. ``0437a06aff484208...``).
    Python's ``str(uuid.UUID(...))`` returns a 36-char hyphenated string
    (e.g. ``0437a06a-ff48-4208-...``).  ``workspace_members.organization_id``
    is a plain ``String`` column with a FK to ``organizations.id``.  SQLite
    enforces FK constraints via a byte-exact string comparison, so passing
    ``str(org.id)`` (36-char) against a 32-char stored value raises::

        sqlite3.IntegrityError: FOREIGN KEY constraint failed

    Using ``org.id.hex`` (32-char, no hyphens) matches the stored format and
    fixes the constraint failure in production.  Tests use the same engine
    and ``Uuid`` type, so ``org.id.hex`` is consistent across environments.
    """
    return org.id.hex  # 32-char hex, no hyphens — matches Uuid storage format


def _link_or_create_member(db: Session, user: AuthUser) -> None:
    org = db.query(Organization).order_by(Organization.created_at).first()
    if not org:
        return
    # WorkspaceMember.organization_id is String(36) — use the exact stored
    # format (32-char hex) to pass the SQLite FK constraint.
    org_id_str = _org_id_for_member(org)
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
