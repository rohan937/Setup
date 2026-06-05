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

# Default workspace created for the very first user on a fresh deployment.
DEFAULT_WORKSPACE_NAME = "Quant Research Workspace"
DEFAULT_WORKSPACE_SLUG = "quant-research-workspace"


def get_or_create_default_org(db: Session) -> Organization:
    """Return the earliest organization, creating the default one if none exists.

    Never creates a duplicate: if any organization already exists it is reused.
    """
    org = db.query(Organization).order_by(Organization.created_at).first()
    if org is not None:
        return org
    org = Organization(
        name=DEFAULT_WORKSPACE_NAME,
        display_name=DEFAULT_WORKSPACE_NAME,
        slug=DEFAULT_WORKSPACE_SLUG,
    )
    db.add(org)
    db.flush()
    return org


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
    # AuthUser.id comes from UUIDPrimaryKeyMixin (now the GUID type, stored as
    # VARCHAR). Passing a uuid.UUID is fine — GUID accepts it and serialises it
    # to the dialect-correct string (hex on SQLite, str(uuid) on PostgreSQL).
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


def _uuid_to_fk_str(u: uuid.UUID) -> str:
    """Convert a UUID to the string format used when storing it in a String(36)
    FK column that references a Uuid(as_uuid=True) primary-key column.

    Storage formats differ by dialect:

    * **SQLite** — ``Uuid(as_uuid=True)`` stores via its non-native path using
      ``uuid.hex`` (32-char, no hyphens, e.g. ``747d9ecdc0a44b5c9b5098fcf5c46dc5``).
    * **PostgreSQL** — the migration creates ``VARCHAR(36)`` columns; psycopg2's
      UUID adapter serialises ``uuid.UUID`` objects via ``str(uuid)`` (36-char
      hyphenated, e.g. ``747d9ecd-c0a4-4b5c-9b50-98fcf5c46dc5``).

    Using ``org.id.hex`` on PostgreSQL causes the FK to reference a value that
    does not exist in the parent table → ``ForeignKeyViolation`` → 500 during
    first-user registration.  This helper picks the correct format per dialect.
    """
    from app.core.config import get_settings
    return u.hex if get_settings().is_sqlite else str(u)


def _org_id_for_member(org: Organization) -> str:
    """Return org.id in the exact format stored in ``organizations.id``."""
    return _uuid_to_fk_str(org.id)


def _link_or_create_member(db: Session, user: AuthUser) -> None:
    org = db.query(Organization).order_by(Organization.created_at).first()
    member_count = db.query(WorkspaceMember).count()
    # A genuine first-user bootstrap: a fresh deployment with no organization and
    # no workspace members yet. Only then do we auto-create the default workspace
    # and make this user the owner — never for later registrants.
    is_first_user = db.query(AuthUser).count() <= 1
    if org is None:
        if is_first_user and member_count == 0:
            org = get_or_create_default_org(db)
        else:
            # An org should exist but doesn't, and this is not a bootstrap case;
            # leave the user unlinked. The UI shows "ask an owner to invite you".
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
    # The first user (who just bootstrapped the workspace, or is the first member
    # of a pre-existing org) becomes owner; later registrants become members.
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


def owner_exists(db: Session) -> bool:
    """True if any workspace member already holds the owner role (any org)."""
    return (
        db.query(WorkspaceMember).filter(WorkspaceMember.role == "owner").first()
        is not None
    )


def _slugify(value: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or DEFAULT_WORKSPACE_SLUG


def bootstrap_owner(
    db: Session,
    *,
    email: str,
    display_name: str | None = None,
    workspace_name: str | None = None,
    require_no_owner: bool = True,
) -> dict:
    """Make *email* the owner of the (single) workspace, creating it if missing.

    Idempotent and safe:
      - reuses the existing organization (never creates a duplicate);
      - creates the default workspace only when none exists;
      - creates or upgrades the member to role=owner / status=active and links
        the matching auth user (if one exists);
      - when ``require_no_owner`` is True, refuses to run once a *different*
        owner already exists (used by the public bootstrap endpoint).

    Returns a summary dict. Does NOT commit — the caller commits.
    """
    email = email.lower().strip()
    user = get_user_by_email(db, email)

    org = db.query(Organization).order_by(Organization.created_at).first()
    created_org = False
    if org is None:
        name = (workspace_name or DEFAULT_WORKSPACE_NAME).strip() or DEFAULT_WORKSPACE_NAME
        slug = DEFAULT_WORKSPACE_SLUG if name == DEFAULT_WORKSPACE_NAME else _slugify(name)
        org = Organization(name=name, display_name=name, slug=slug)
        db.add(org)
        db.flush()
        created_org = True

    org_id_str = _org_id_for_member(org)

    if require_no_owner:
        existing_owner = (
            db.query(WorkspaceMember)
            .filter(WorkspaceMember.role == "owner")
            .first()
        )
        if existing_owner is not None and existing_owner.email != email:
            raise ValueError("an owner already exists")

    now = datetime.now(timezone.utc)
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.organization_id == org_id_str,
            WorkspaceMember.email == email,
        )
        .first()
    )
    created_member = False
    if member is None:
        member = WorkspaceMember(
            organization_id=org_id_str,
            display_name=display_name or (user.display_name if user else email),
            email=email,
            role="owner",
            status="active",
            user_id=str(user.id) if user else None,
            created_at=now,
            updated_at=now,
        )
        db.add(member)
        created_member = True
    else:
        member.role = "owner"
        member.status = "active"
        if display_name:
            member.display_name = display_name
        if user and not member.user_id:
            member.user_id = str(user.id)
        member.updated_at = now
    db.flush()

    return {
        "email": email,
        "user_found": user is not None,
        "user_id": str(user.id) if user else None,
        "organization_id": str(org.id),
        "organization_name": org.name,
        "organization_created": created_org,
        "member_id": str(member.id),
        "member_created": created_member,
        "role": member.role,
        "status": member.status,
        "linked": member.user_id is not None,
    }


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
