"""M68 Auth routes: register, login, /me, logout, status."""

from __future__ import annotations

import uuid as _uuid_module
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.db.session import get_db
from app.models.auth_user import AuthUser
from app.models.organization import Organization
from app.models.workspace_member import WorkspaceMember
from app.schemas.auth import (
    AuthStatusResponse,
    AuthTokenResponse,
    ChangePasswordRequest,
    CurrentUserResponse,
    CurrentUserWorkspaceMembership,
    ForgotPasswordRequest,
    MessageResponse,
    PermissionSet,
    ResetPasswordRequest,
    UserLoginRequest,
    UserRead,
    UserRegisterRequest,
    VerifyEmailRequest,
)
from app.services.auth_users import (
    authenticate_user,
    bootstrap_owner,
    owner_exists,
    register_user,
)
from app.services.email import send_password_reset_email, send_verification_email
from app.services.email_tokens import consume_email_token, create_email_token

router = APIRouter()


@router.post("/auth/register", response_model=AuthTokenResponse)
def register(payload: UserRegisterRequest, db: Session = Depends(get_db)):
    """Register a new user and return a JWT token."""
    settings = get_settings()
    if settings.invite_only_registration:
        raise HTTPException(
            status_code=403,
            detail=(
                "Public registration is disabled (invite-only). "
                "Contact an administrator for access."
            ),
        )
    # NOTE: full invite-token redemption (payload.invite_token) is intentionally
    # future work — for now invite_only acts purely as a registration guard.
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

    # New users start UNVERIFIED (model default email_verified=False). Issue an
    # email-verification token and send the link. Email failures must never 500
    # the registration — the user is created and logged in either way.
    raw = create_email_token(
        db, user, "email_verification", settings.email_verification_expire_hours
    )
    db.commit()
    try:
        send_verification_email(settings, user, raw)
    except Exception:
        pass  # never 500 registration on email failure

    token = create_access_token(
        str(user.id), user.email, settings.access_token_expire_minutes
    )
    return AuthTokenResponse(
        access_token=token, user=UserRead.model_validate(user)
    )


@router.post("/auth/verify-email", response_model=MessageResponse)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    """Consume an email-verification token and mark the user verified."""
    user = consume_email_token(db, payload.token, "email_verification")
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link.")
    now = datetime.now(timezone.utc)
    user.email_verified = True
    user.email_verified_at = now
    user.updated_at = now
    db.commit()
    return MessageResponse(message="Email verified successfully.")


@router.post("/auth/resend-verification", response_model=MessageResponse)
def resend_verification(
    current_user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Re-send the email-verification link to the current user."""
    if current_user.email_verified:
        return MessageResponse(message="Your email is already verified.")
    settings = get_settings()
    raw = create_email_token(
        db,
        current_user,
        "email_verification",
        settings.email_verification_expire_hours,
    )
    db.commit()
    try:
        send_verification_email(settings, current_user, raw)
    except Exception:
        pass
    return MessageResponse(message="Verification email sent. Check your inbox.")


@router.post("/auth/forgot-password", response_model=MessageResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Begin a password reset. Always returns the same message (no enumeration)."""
    settings = get_settings()
    email = payload.email.lower().strip()
    user = db.query(AuthUser).filter(AuthUser.email == email).first()
    if user is not None:
        raw = create_email_token(
            db, user, "password_reset", settings.password_reset_expire_hours
        )
        db.commit()
        try:
            send_password_reset_email(settings, user, raw)
        except Exception:
            pass
    # ALWAYS the same response — never reveal whether the email exists.
    return MessageResponse(
        message="If an account exists for that email, a password reset link has been sent."
    )


@router.post("/auth/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Reset a password using a valid password-reset token."""
    try:
        validate_password_strength(payload.new_password)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Password must be at least 8 characters"
        )
    user = consume_email_token(db, payload.token, "password_reset")
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")
    user.hashed_password = hash_password(payload.new_password)
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    return MessageResponse(
        message="Password reset successful. You can now sign in with your new password."
    )


@router.post("/auth/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    current_user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the current user's password (requires the current password)."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    try:
        validate_password_strength(payload.new_password)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Password must be at least 8 characters"
        )
    current_user.hashed_password = hash_password(payload.new_password)
    current_user.updated_at = datetime.now(timezone.utc)
    db.commit()
    return MessageResponse(message="Password changed successfully.")


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
        str(user.id), user.email, settings.access_token_expire_minutes
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
        auth_enabled=settings.auth_enabled,
        has_users=has_users,
        registration_enabled=True,
    )
