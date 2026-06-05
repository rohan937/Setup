"""M69 RBAC: Role-Based Access Control + Workspace/Project access gates.

This module provides:

* Role ordering (``viewer < member < admin < owner``) and permission predicates.
* A :class:`MemberContext` describing the resolved caller (role + organization).
* FastAPI dependencies that resolve the current workspace member from the M68
  JWT user and enforce role requirements.
* Workspace/project/strategy scope helpers.

Local-dev / permissive behaviour
--------------------------------
M69 is the *foundation* milestone. To avoid breaking the large existing test
and local-dev surface (most of which calls the API without a bearer token),
enforcement is intentionally permissive in two cases:

1. ``QF_RBAC_ENABLED`` is ``False`` — enforcement is skipped entirely.
2. ``QF_RBAC_ENABLED`` is ``True`` but the request carries **no** authenticated
   user (no/invalid bearer token) — the caller is treated as a local-dev
   pseudo-owner.

When a request *does* carry a valid bearer token, the caller's real workspace
role is resolved and enforced. A signed-in user with no linked workspace member
is rejected with HTTP 403. See README "RBAC foundation" for the limitation note.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_optional_current_user
from app.core.config import get_settings
from app.core.constants import UserRole
from app.db.session import get_db
from app.models.workspace_member import WorkspaceMember

# ---------------------------------------------------------------------------
# Role ordering
# ---------------------------------------------------------------------------

# viewer < member < admin < owner
ROLE_ORDER: dict[str, int] = {
    UserRole.viewer: 0,
    UserRole.member: 1,
    UserRole.admin: 2,
    UserRole.owner: 3,
}


def role_rank(role: str) -> int:
    """Return the numeric rank of *role*; unknown roles rank below viewer."""
    return ROLE_ORDER.get(role, -1)


# ---------------------------------------------------------------------------
# Member context
# ---------------------------------------------------------------------------


@dataclass
class MemberContext:
    """The resolved caller for an RBAC-protected request."""

    role: str
    organization_id: str | None
    member_id: str | None
    # True when synthesised for local-dev / RBAC-disabled (no real membership).
    is_pseudo: bool = False

    @classmethod
    def pseudo_owner(cls, organization_id: str | None = None) -> "MemberContext":
        """A permissive local-dev owner used when enforcement is skipped."""
        return cls(
            role=UserRole.owner,
            organization_id=organization_id,
            member_id=None,
            is_pseudo=True,
        )

    @classmethod
    def from_member(cls, member: WorkspaceMember) -> "MemberContext":
        return cls(
            role=member.role,
            organization_id=str(member.organization_id),
            member_id=str(member.id),
            is_pseudo=False,
        )


# ---------------------------------------------------------------------------
# Permission predicates (operate on anything with a ``.role`` attribute)
# ---------------------------------------------------------------------------


def can_read_workspace(member: MemberContext) -> bool:
    """Any role (viewer and above) may read workspace research data."""
    return role_rank(member.role) >= ROLE_ORDER[UserRole.viewer]


# Alias used by research read gates.
can_read_research = can_read_workspace


def can_write_research(member: MemberContext) -> bool:
    """member/admin/owner may create or mutate research data; viewer cannot."""
    return role_rank(member.role) >= ROLE_ORDER[UserRole.member]


def can_manage_workspace(member: MemberContext) -> bool:
    """owner/admin may update workspace settings."""
    return role_rank(member.role) >= ROLE_ORDER[UserRole.admin]


def can_manage_members(member: MemberContext) -> bool:
    """owner/admin may add/update/remove workspace members."""
    return role_rank(member.role) >= ROLE_ORDER[UserRole.admin]


def can_manage_api_keys(member: MemberContext) -> bool:
    """owner/admin may create/revoke workspace API keys."""
    return role_rank(member.role) >= ROLE_ORDER[UserRole.admin]


def can_seed_demo(member: MemberContext) -> bool:
    """owner/admin may seed/reset demo data."""
    return role_rank(member.role) >= ROLE_ORDER[UserRole.admin]


def permission_set(member: MemberContext) -> dict[str, bool]:
    """Return the full permission map for a member context."""
    return {
        "can_read_research": can_read_workspace(member),
        "can_write_research": can_write_research(member),
        "can_manage_workspace": can_manage_workspace(member),
        "can_manage_members": can_manage_members(member),
        "can_manage_api_keys": can_manage_api_keys(member),
        "can_seed_demo": can_seed_demo(member),
    }


# ---------------------------------------------------------------------------
# Member resolution
# ---------------------------------------------------------------------------


def get_current_workspace_member(db: Session, current_user) -> MemberContext:
    """Resolve the calling user's workspace membership into a MemberContext.

    Honours the permissive local-dev rules documented in the module docstring.
    Raises HTTP 403 only when RBAC is enabled, a real user is present, and that
    user has no active workspace membership.
    """
    settings = get_settings()

    # (1) RBAC disabled — fully permissive.
    if not settings.QF_RBAC_ENABLED:
        return MemberContext.pseudo_owner()

    # (2) No authenticated user.
    # Local dev / non-production: permissive pseudo-owner so scripts and tests
    # work without a token.  In production the fallback is disabled so that an
    # anonymous caller cannot inherit owner-level access via this shortcut.
    if current_user is None:
        if settings.is_production:
            raise HTTPException(
                status_code=401,
                detail=(
                    "Authentication required. "
                    "Include 'Authorization: Bearer <token>' in your request."
                ),
            )
        return MemberContext.pseudo_owner()

    # (3) Authenticated user — resolve their real membership.
    member = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.user_id == str(current_user.id))
        .order_by(WorkspaceMember.created_at.asc())
        .first()
    )
    if member is None:
        raise HTTPException(
            status_code=403,
            detail="No workspace membership for this account. Ask an admin to add you.",
        )
    if member.status == "disabled":
        raise HTTPException(
            status_code=403,
            detail="Your workspace membership is disabled.",
        )
    return MemberContext.from_member(member)


# ---------------------------------------------------------------------------
# Dependency factories
# ---------------------------------------------------------------------------


def _deny(detail: str) -> HTTPException:
    return HTTPException(status_code=403, detail=detail)


def require_workspace_read_access(
    current_user=Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> MemberContext:
    """Any authenticated workspace member (viewer and above) may proceed."""
    ctx = get_current_workspace_member(db, current_user)
    if not can_read_workspace(ctx):
        raise _deny("Read access to this workspace is required.")
    return ctx


def require_workspace_write_access(
    current_user=Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> MemberContext:
    """member/admin/owner may proceed; viewers are rejected (Owner/Admin/Member only)."""
    ctx = get_current_workspace_member(db, current_user)
    if not can_write_research(ctx):
        raise _deny("Write access requires member, admin, or owner role.")
    return ctx


def require_workspace_member_or_admin(
    current_user=Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> MemberContext:
    """Alias for write access (member and above)."""
    ctx = get_current_workspace_member(db, current_user)
    if not can_write_research(ctx):
        raise _deny("Member, admin, or owner role required.")
    return ctx


def require_workspace_admin(
    current_user=Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> MemberContext:
    """owner/admin only."""
    ctx = get_current_workspace_member(db, current_user)
    if not can_manage_workspace(ctx):
        raise _deny("Admin access required (Owner/Admin only).")
    return ctx


def require_can_manage_members(
    current_user=Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> MemberContext:
    """owner/admin only — member management."""
    ctx = get_current_workspace_member(db, current_user)
    if not can_manage_members(ctx):
        raise _deny("Managing members requires Owner/Admin role.")
    return ctx


def require_can_manage_api_keys(
    current_user=Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> MemberContext:
    """owner/admin only — API key management."""
    ctx = get_current_workspace_member(db, current_user)
    if not can_manage_api_keys(ctx):
        raise _deny("Managing API keys requires Owner/Admin role.")
    return ctx


def require_can_seed_demo(
    current_user=Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> MemberContext:
    """owner/admin only — demo seed/reset."""
    ctx = get_current_workspace_member(db, current_user)
    if not can_seed_demo(ctx):
        raise _deny("Seeding demo data requires Owner/Admin role.")
    return ctx


def require_workspace_role(*allowed_roles: str):
    """Build a dependency enforcing membership in *allowed_roles*.

    Permissive contexts (RBAC disabled / no auth) always pass.
    """
    allowed = set(allowed_roles)

    def _dep(
        current_user=Depends(get_optional_current_user),
        db: Session = Depends(get_db),
    ) -> MemberContext:
        ctx = get_current_workspace_member(db, current_user)
        if ctx.is_pseudo:
            return ctx
        if ctx.role not in allowed:
            raise _deny(
                f"This action requires one of the following roles: {', '.join(sorted(allowed))}."
            )
        return ctx

    return _dep


# ---------------------------------------------------------------------------
# Project / strategy scope helpers
# ---------------------------------------------------------------------------

# Permission name -> predicate used by assert_*_access.
_PERMISSION_CHECKS = {
    "read": can_read_workspace,
    "write": can_write_research,
}


def _org_matches(member: MemberContext, organization_id) -> bool:
    """True when the member's org matches *organization_id* (or context is pseudo)."""
    if member.is_pseudo or member.organization_id is None:
        return True
    return str(organization_id) == str(member.organization_id)


def assert_project_access(
    db: Session,
    member: MemberContext,
    project_id,
    permission: str = "read",
) -> None:
    """Ensure *member* can access *project_id* with *permission*.

    Fails closed (403) when the project's organization does not match the
    member's organization in auth-enabled mode.
    """
    from app.models.project import Project

    check = _PERMISSION_CHECKS.get(permission, can_read_workspace)
    if not check(member):
        raise _deny(f"{permission.title()} access to this project is required.")

    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not _org_matches(member, project.organization_id):
        raise _deny("This project belongs to a different workspace.")


def assert_strategy_access(
    db: Session,
    member: MemberContext,
    strategy_id,
    permission: str = "read",
) -> None:
    """Ensure *member* can access *strategy_id* (via its project's org)."""
    from app.models.project import Project
    from app.models.strategy import Strategy

    check = _PERMISSION_CHECKS.get(permission, can_read_workspace)
    if not check(member):
        raise _deny(f"{permission.title()} access to this strategy is required.")

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    project = db.query(Project).filter(Project.id == strategy.project_id).first()
    if project is not None and not _org_matches(member, project.organization_id):
        raise _deny("This strategy belongs to a different workspace.")


def require_project_access(project_id, permission: str = "read"):
    """Build a dependency enforcing access to *project_id*."""

    def _dep(
        current_user=Depends(get_optional_current_user),
        db: Session = Depends(get_db),
    ) -> MemberContext:
        ctx = get_current_workspace_member(db, current_user)
        assert_project_access(db, ctx, project_id, permission)
        return ctx

    return _dep


def require_strategy_access(strategy_id, permission: str = "read"):
    """Build a dependency enforcing access to *strategy_id*."""

    def _dep(
        current_user=Depends(get_optional_current_user),
        db: Session = Depends(get_db),
    ) -> MemberContext:
        ctx = get_current_workspace_member(db, current_user)
        assert_strategy_access(db, ctx, strategy_id, permission)
        return ctx

    return _dep
