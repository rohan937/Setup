"""M68 Auth routes: register, login, /me, logout, status."""

from __future__ import annotations

import uuid as _uuid_module

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.auth_user import AuthUser
from app.models.organization import Organization
from app.models.workspace_member import WorkspaceMember
from app.schemas.auth import (
    AuthStatusResponse,
    AuthTokenResponse,
    CurrentUserResponse,
    CurrentUserWorkspaceMembership,
    PermissionSet,
    UserLoginRequest,
    UserRead,
    UserRegisterRequest,
)
from app.services.auth_users import (
    authenticate_user,
    bootstrap_owner,
    owner_exists,
    register_user,
)

router = APIRouter()


@router.post("/auth/register", response_model=AuthTokenResponse)
def register(payload: UserRegisterRequest, db: Session = Depends(get_db)):
    """Register a new user and return a JWT token."""
    try:
        user = register_user(db, payload.email, payload.display_name, payload.password)
        db.commit()
        db.refresh(user)
    except ValueError as e:
        db.rollback()
        msg = str(e)
        if "duplicate" in msg:
            raise HTTPException(status_code=409, detail="Email already registered")
        if "too short" in msg:
            raise HTTPException(
                status_code=422, detail="Password must be at least 8 characters"
            )
        raise HTTPException(status_code=400, detail=msg)
    settings = get_settings()
    token = create_access_token(
        str(user.id), user.email, settings.QF_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return AuthTokenResponse(
        access_token=token, user=UserRead.model_validate(user)
    )


@router.post("/auth/login", response_model=AuthTokenResponse)
def login(payload: UserLoginRequest, db: Session = Depends(get_db)):
    """Authenticate a user and return a JWT token."""
    try:
        user = authenticate_user(db, payload.email, payload.password)
        db.commit()
        db.refresh(user)
    except ValueError:
        db.rollback()
        raise HTTPException(status_code=401, detail="Invalid email or password")
    settings = get_settings()
    token = create_access_token(
        str(user.id), user.email, settings.QF_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return AuthTokenResponse(
        access_token=token, user=UserRead.model_validate(user)
    )


@router.get("/auth/me", response_model=CurrentUserResponse)
def get_me(
    current_user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the currently authenticated user and their workspace memberships."""
    memberships = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.user_id == str(current_user.id))
        .all()
    )
    # workspace_members.organization_id is stored as a 32-char hex string, while
    # Organization.id stringifies to a 36-char hyphenated UUID. Normalize both to
    # the canonical hex form so the lookup matches regardless of source format.
    def _norm_org_id(value) -> str | None:
        if not value:
            return None
        try:
            return _uuid_module.UUID(str(value)).hex
        except (ValueError, AttributeError, TypeError):
            return None

    org_id_strs = {m.organization_id for m in memberships}
    # Organization.id is Uuid(as_uuid=True) — convert strings to uuid.UUID for query
    org_uuids = [_uuid_module.UUID(s) for s in org_id_strs if s and _norm_org_id(s)]
    # Key the org map by the normalized (hex) id so lookups by member.organization_id
    # (32-char hex) succeed even though str(Organization.id) is 36-char hyphenated.
    orgs = {
        _norm_org_id(o.id): o
        for o in db.query(Organization)
        .filter(Organization.id.in_(org_uuids))
        .all()
    }

    def _workspace_name(org) -> str:
        if org is None:
            return "Unknown"
        return getattr(org, "display_name", None) or getattr(org, "name", None) or "Unknown"

    membership_list = [
        CurrentUserWorkspaceMembership(
            member_id=str(m.id),
            organization_id=str(m.organization_id),
            workspace_name=_workspace_name(orgs.get(_norm_org_id(m.organization_id))),
            role=m.role,
            status=m.status,
            linked=True,
        )
        for m in memberships
    ]

    # M69: derive role + permissions from the primary (earliest, active-preferred)
    # membership so the frontend can hide/disable unauthorized actions.
    from app.core.rbac import MemberContext, permission_set

    primary = None
    if memberships:
        active = [m for m in memberships if m.status == "active"]
        pool = active if active else memberships
        primary = sorted(pool, key=lambda m: m.created_at)[0]

    if primary is not None:
        ctx = MemberContext.from_member(primary)
        role = primary.role
        organization_id = str(primary.organization_id)
        perms = PermissionSet(**permission_set(ctx))
    else:
        role = None
        organization_id = None
        perms = PermissionSet()

    return CurrentUserResponse(
        user=UserRead.model_validate(current_user),
        workspace_memberships=membership_list,
        role=role,
        organization_id=organization_id,
        permissions=perms,
    )


@router.post("/auth/bootstrap-first-owner", response_model=CurrentUserResponse)
def bootstrap_first_owner(
    current_user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One-time first-owner bootstrap for a fresh deployment.

    Promotes the **currently authenticated** user to owner of the default
    workspace (creating the workspace if none exists). Allowed ONLY while no
    owner exists anywhere — once any owner exists this returns 409, so it can
    never be used to escalate privileges on an established workspace.
    """
    if owner_exists(db):
        raise HTTPException(
            status_code=409,
            detail="An owner already exists. First-owner bootstrap is disabled.",
        )
    try:
        bootstrap_owner(
            db,
            email=current_user.email,
            display_name=current_user.display_name,
            require_no_owner=True,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    # Return the refreshed /me payload so the client updates role + permissions.
    return get_me(current_user=current_user, db=db)


@router.post("/auth/logout")
def logout():
    """Stateless logout — client must discard its local token."""
    return {"success": True, "message": "Logged out. Delete your local token."}


@router.get("/auth/status", response_model=AuthStatusResponse)
def auth_status(db: Session = Depends(get_db)):
    """Return auth configuration and whether any users exist."""
    settings = get_settings()
    has_users = db.query(AuthUser).count() > 0
    return AuthStatusResponse(
        auth_enabled=settings.QF_AUTH_ENABLED,
        has_users=has_users,
        registration_enabled=True,
    )
