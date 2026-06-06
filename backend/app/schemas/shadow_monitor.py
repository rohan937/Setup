"""Pydantic schemas for the M88 shadow monitor endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ShadowDriftMetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    baseline_value: Optional[float]
    comparison_value: Optional[float]
    absolute_delta: Optional[float]
    percent_delta: Optional[float]
    status: str   # pass | watch | fail | missing
    severity: str  # info | low | medium | high | critical
    explanation: str


class ShadowRunRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: Optional[uuid.UUID]
    run_name: Optional[str]
    run_type: Optional[str]


class ShadowMonitorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    baseline_run: Optional[ShadowRunRef]
    comparison_run: Optional[ShadowRunRef]
    verdict: str           # stable | watch | drifted | insufficient_data
    drift_score: Optional[float]  # 0-100
    severity: str          # low | medium | high | critical
    primary_concern: Optional[str]
    metrics: list[ShadowDriftMetricOut]
    top_concerns: list[str]
    suggested_actions: list[str]
    blockers: list[str]
    missing_metric_keys: list[str]
    missing_metric_coverage: float  # 0.0-1.0
    generated_at: datetime
    disclaimer: str


class ShadowMonitorReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    format: str
    content: str
    generated_at: datetime
