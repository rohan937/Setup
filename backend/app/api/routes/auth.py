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
    UserLoginRequest,
    UserRead,
    UserRegisterRequest,
)
from app.services.auth_users import authenticate_user, register_user

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
    org_id_strs = {m.organization_id for m in memberships}
    # Organization.id is Uuid(as_uuid=True) — convert strings to uuid.UUID for query
    org_uuids = [_uuid_module.UUID(s) for s in org_id_strs if s]
    orgs = {
        str(o.id): o
        for o in db.query(Organization)
        .filter(Organization.id.in_(org_uuids))
        .all()
    }
    membership_list = [
        CurrentUserWorkspaceMembership(
            member_id=str(m.id),
            organization_id=str(m.organization_id),
            workspace_name=getattr(orgs.get(str(m.organization_id)), "name", "Unknown"),
            role=m.role,
            status=m.status,
            linked=True,
        )
        for m in memberships
    ]
    return CurrentUserResponse(
        user=UserRead.model_validate(current_user),
        workspace_memberships=membership_list,
    )


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
