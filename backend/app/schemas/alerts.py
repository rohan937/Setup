"""Pydantic schemas for the Alerts Engine (M11)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertRead(BaseModel):
    """Full alert record — returned from GET endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    rule_type: str
    status: str
    severity: str
    title: str
    description: str | None
    source_type: str | None
    source_id: str | None
    strategy_id: uuid.UUID | None
    triggered_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    snoozed_until: datetime | None
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class AlertListResponse(BaseModel):
    """Paginated list of alerts."""

    items: list[AlertRead]
    total: int
    limit: int
    offset: int


class AlertGenerateResponse(BaseModel):
    """Summary returned after running the alert-generation service."""

    alerts_created: int
    alerts_skipped_duplicate: int
    total_alerts_open: int


class AlertUpdateRequest(BaseModel):
    """Partial update — only ``status`` may be changed via the API."""

    status: str
