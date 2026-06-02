"""Pydantic schemas for timeline analytics (M43)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TimelineAnalyticsBucket(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bucket_start: datetime
    bucket_end: datetime
    total_events: int
    event_type_counts: dict[str, int]
    source_type_counts: dict[str, int]
    evidence_category_counts: dict[str, int]


class TimelineInactivityGap(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gap_start: datetime
    gap_end: datetime
    gap_days: int
    previous_event_title: str | None
    next_event_title: str | None


class StrategyTimelineAnalyticsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    generated_at: datetime
    bucket: str
    lookback_days: int
    total_events: int
    active_bucket_count: int
    empty_bucket_count: int
    latest_event_at: datetime | None
    days_since_latest_event: int | None
    most_active_bucket_start: datetime | None
    most_active_bucket_event_count: int
    dominant_event_type: str | None
    dominant_evidence_category: str | None
    longest_inactivity_gap_days: int | None
    buckets: list[TimelineAnalyticsBucket]
    gaps: list[TimelineInactivityGap]
    staleness_status: str
    deterministic_summary: str
    suggested_checks: list[str]
