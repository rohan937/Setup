"""Pydantic schemas for the audit timeline (M2 / M10)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TimelineEventOut(BaseModel):
    """One audit timeline event — read-only."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID | None
    strategy_id: uuid.UUID | None
    event_type: str
    title: str
    description: str | None
    source_type: str | None
    source_id: str | None
    severity: str
    event_time: datetime
    metadata_json: dict | None
    created_at: datetime


class TimelineListResponse(BaseModel):
    """Paginated list of timeline events."""

    items: list[TimelineEventOut]
    total: int
    limit: int
    offset: int
