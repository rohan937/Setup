"""Pydantic schemas for M67 Workspace Settings + Members Foundation."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WorkspaceProjectSummary(BaseModel):
    project_id: str
    name: str
    strategy_count: int
    created_at: datetime


class WorkspaceSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: str
    workspace_name: str
    display_name: str | None
    description: str | None
    website: str | None
    created_at: datetime
    updated_at: datetime
    projects: list[WorkspaceProjectSummary] = []
    readiness_note: str = ""


class WorkspaceSummaryRead(BaseModel):
    workspace_id: str | None
    workspace_name: str
    display_name: str | None = None
    description: str | None = None
    website: str | None = None
    project_count: int
    strategy_count: int
    member_count: int
    active_member_count: int
    api_key_count: int
    created_at: datetime | None
    updated_at: datetime | None
    projects: list[WorkspaceProjectSummary] = []
    readiness_note: str = ""


class WorkspaceSettingsUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    website: str | None = None


class WorkspaceMemberCreate(BaseModel):
    display_name: str
    email: str
    role: str = "member"
    status: str = "active"
    title: str | None = None
    notes: str | None = None


class WorkspaceMemberUpdate(BaseModel):
    display_name: str | None = None
    email: str | None = None
    role: str | None = None
    status: str | None = None
    title: str | None = None
    notes: str | None = None


class WorkspaceMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: str
    display_name: str
    email: str
    role: str
    status: str
    title: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class WorkspaceMemberListResponse(BaseModel):
    items: list[WorkspaceMemberRead]
    total: int
