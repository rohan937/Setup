"""Pydantic schemas for M30 evidence trends endpoint."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TrendPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    value: Optional[float] = None
    status: Optional[str] = None
    timestamp: datetime
    metadata_json: Optional[dict] = None


class TrendSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    points: list[TrendPoint]
    latest_value: Optional[float] = None
    previous_value: Optional[float] = None
    delta: Optional[float] = None
    direction: str
    point_count: int
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    average_value: Optional[float] = None
    latest_label: Optional[str] = None
    latest_at: Optional[datetime] = None
    deterministic_summary: str


class EvidenceCoverageCurrentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_coverage_score: float
    missing_count: int
    review_count: int
    complete_count: int


class StrategyEvidenceTrendsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    generated_at: datetime
    reliability_trend: TrendSummary
    data_health_trend: TrendSummary
    backtest_trust_trend: TrendSummary
    signal_quality_trend: TrendSummary
    coverage_current: Optional[EvidenceCoverageCurrentSummary] = None
    overall_summary: str
    suggested_checks: list[str] = []
