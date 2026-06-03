"""M67 Workspace Settings + Members Foundation routes.

GET    /api/workspace/settings            — workspace summary
PATCH  /api/workspace/settings            — update workspace settings
GET    /api/workspace/members             — list workspace members
POST   /api/workspace/members             — add a workspace member
PATCH  /api/workspace/members/{member_id} — update a workspace member
DELETE /api/workspace/members/{member_id} — remove (soft-delete) a workspace member
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.workspace import (
    WorkspaceMemberCreate,
    WorkspaceMemberListResponse,
    WorkspaceMemberRead,
    WorkspaceMemberUpdate,
    WorkspaceSettingsRead,
    WorkspaceSettingsUpdate,
    WorkspaceSummaryRead,
)
from app.services import workspaces as svc

router = APIRouter(tags=["workspace"])


# ---------------------------------------------------------------------------
# Workspace settings
# ---------------------------------------------------------------------------

@router.get("/workspace/settings", response_model=WorkspaceSummaryRead)
def get_workspace_settings(db: Session = Depends(get_db)) -> WorkspaceSummaryRead:
    """Return the workspace summary including counts and project list."""
    summary = svc.get_workspace_summary(db)
    return WorkspaceSummaryRead(**summary)


@router.patch("/workspace/settings", response_model=WorkspaceSettingsRead)
def update_workspace_settings(
    body: WorkspaceSettingsUpdate,
    db: Session = Depends(get_db),
) -> WorkspaceSettingsRead:
    """Update top-level workspace settings (display_name, description, website)."""
    org = svc.get_workspace_settings(db)
    if org is None:
        raise HTTPException(status_code=404, detail="No organization found")

    try:
        updated_org = svc.update_workspace_settings(
            db, str(org.id), body.model_dump(exclude_none=False)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    db.refresh(updated_org)

    # Build summary for response
    summary = svc.get_workspace_summary(db)
    return WorkspaceSettingsRead(
        workspace_id=str(updated_org.id),
        workspace_name=updated_org.name,
        display_name=updated_org.display_name,
        description=updated_org.description,
        website=updated_org.website,
        created_at=updated_org.created_at,
        updated_at=updated_org.updated_at,
        projects=summary["projects"],
        readiness_note=summary["readiness_note"],
    )


# ---------------------------------------------------------------------------
# Workspace members
# ---------------------------------------------------------------------------

@router.get("/workspace/members", response_model=WorkspaceMemberListResponse)
def list_workspace_members(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> WorkspaceMemberListResponse:
    """List workspace members with optional status filter."""
    org = svc.get_workspace_settings(db)
    if org is None:
        raise HTTPException(status_code=404, detail="No organization found")

    members = svc.get_workspace_members(db, str(org.id), status=status)
    return WorkspaceMemberListResponse(
        items=[WorkspaceMemberRead.model_validate(m) for m in members],
        total=len(members),
    )


@router.post("/workspace/members", response_model=WorkspaceMemberRead, status_code=201)
def create_workspace_member(
    body: WorkspaceMemberCreate,
    db: Session = Depends(get_db),
) -> WorkspaceMemberRead:
    """Add a new member to the workspace."""
    org = svc.get_workspace_settings(db)
    if org is None:
        raise HTTPException(status_code=404, detail="No organization found")

    try:
        member = svc.create_workspace_member(db, str(org.id), body.model_dump())
    except ValueError as exc:
        msg = str(exc)
        if "duplicate email" in msg:
            raise HTTPException(status_code=409, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    db.commit()
    db.refresh(member)
    return WorkspaceMemberRead.model_validate(member)


@router.patch(
    "/workspace/members/{member_id}", response_model=WorkspaceMemberRead
)
def update_workspace_member(
    member_id: str,
    body: WorkspaceMemberUpdate,
    db: Session = Depends(get_db),
) -> WorkspaceMemberRead:
    """Update a workspace member's fields."""
    try:
        member = svc.update_workspace_member(
            db, member_id, body.model_dump(exclude_none=True)
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    db.commit()
    db.refresh(member)
    return WorkspaceMemberRead.model_validate(member)


@router.delete("/workspace/members/{member_id}")
def remove_workspace_member(
    member_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Soft-delete a workspace member by setting status to 'disabled'."""
    try:
        svc.remove_workspace_member(db, member_id)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    db.commit()
    return {"success": True}
