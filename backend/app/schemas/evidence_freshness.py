"""Pydantic schemas for Evidence Freshness (M48)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EvidenceFreshnessItem(BaseModel):
    """Freshness data for one evidence type."""

    model_config = ConfigDict(from_attributes=True)

    evidence_type: str
    label: str
    status: str
    severity: str
    summary: str
    latest_at: datetime | None
    days_since_latest: int | None
    count: int
    threshold_days: int
    suggested_check: str | None
    latest_object_id: str | None
    latest_object_label: str | None


class StrategyEvidenceFreshnessResponse(BaseModel):
    """Full evidence freshness response for a strategy (M48 endpoint)."""

    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    freshness_status: str
    deterministic_summary: str
    generated_at: datetime
    overall_freshness_score: float | None
    stale_count: int
    missing_count: int
    aging_count: int
    fresh_count: int
    evidence_items: list[EvidenceFreshnessItem]
    oldest_evidence_type: str | None
    freshest_evidence_type: str | None
    suggested_refresh_order: list[str]
