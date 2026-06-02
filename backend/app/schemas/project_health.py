"""Pydantic schemas for project health — M28."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectHealthRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: uuid.UUID
    project_name: str
    organization_id: uuid.UUID
    health_score: float | None
    health_status: str
    strategy_count: int
    healthy_strategy_count: int
    watch_strategy_count: int
    review_strategy_count: int
    critical_strategy_count: int
    insufficient_evidence_strategy_count: int
    average_strategy_health_score: float | None
    average_reliability_score: float | None
    average_evidence_coverage_score: float | None
    open_alert_count: int
    high_critical_alert_count: int
    recent_failed_ingestion_count: int
    latest_activity_at: datetime | None
    primary_concern: str
    suggested_checks: list[str]
    generated_at: datetime


class ProjectHealthListResponse(BaseModel):
    items: list[ProjectHealthRead]
    total: int
    limit: int
    offset: int
    generated_at: datetime
