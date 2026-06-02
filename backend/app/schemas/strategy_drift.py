"""Pydantic schemas for the strategy drift endpoint (M47)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class StrategyDriftRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: uuid.UUID
    run_name: str
    run_type: str
    status: str
    created_at: datetime
    completed_at: datetime | None
    metrics_json: dict | None
    assumptions_json: dict | None
    strategy_version_label: str | None
    dataset_health: float | None
    signal_quality: float | None
    universe_symbol_count: int | None
    backtest_trust: float | None
    run_health_label: str


class MetricDriftItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metric: str
    baseline_value: float | None
    comparison_value: float | None
    absolute_delta: float | None
    percent_delta: float | None
    direction: str
    severity: str


class EvidenceDriftItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_type: str
    baseline_value: float | None
    comparison_value: float | None
    delta: float | None
    severity: str
    explanation: str


class AssumptionDriftItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key_path: str
    old_value: Any
    new_value: Any
    change_type: str
    impact_level: str
    suggested_check: str | None


class TrustDriftItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dimension: str
    baseline_value: float | None
    comparison_value: float | None
    delta: float | None
    severity: str
    explanation: str


class StrategyDriftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    mode: str
    generated_at: datetime
    drift_score: float | None
    drift_status: str
    deterministic_summary: str
    baseline_run: StrategyDriftRunSummary | None
    comparison_run: StrategyDriftRunSummary | None
    stage_path: list
    metric_drifts: list[MetricDriftItem]
    evidence_drifts: list[EvidenceDriftItem]
    assumption_drifts: list[AssumptionDriftItem]
    trust_drifts: list[TrustDriftItem]
    highlighted_drifts: list[str]
    suggested_checks: list[str]
