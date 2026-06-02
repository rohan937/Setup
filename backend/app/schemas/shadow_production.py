"""Pydantic schemas for the shadow production monitor endpoint (M50)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ShadowRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: uuid.UUID
    run_name: str
    run_type: str
    status: str
    run_health_label: str
    created_at: datetime
    completed_at: datetime | None
    strategy_version_label: str | None
    dataset_health: float | None
    signal_quality: float | None
    backtest_trust: float | None
    universe_symbol_count: int | None
    metrics_json: dict | None
    assumptions_json: dict | None


class ShadowMetricComparison(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metric_key: str
    direction: str
    severity: str
    explanation: str
    baseline_value: float | None
    comparison_value: float | None
    absolute_delta: float | None
    percent_delta: float | None


class ShadowEvidenceComparison(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_type: str
    severity: str
    explanation: str
    baseline_value: float | None
    comparison_value: float | None
    delta: float | None


class ShadowAssumptionChange(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key_path: str
    change_type: str
    impact_level: str
    old_value: Any
    new_value: Any
    impact_reason: str | None
    suggested_check: str | None


class ShadowTrustComparison(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dimension: str
    severity: str
    explanation: str
    baseline_value: float | None
    comparison_value: float | None
    delta: float | None


class ShadowProductionCheck(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    check_key: str
    title: str
    severity: str
    evidence: str
    passed: bool
    suggested_action: str | None


class StrategyShadowMonitorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    monitor_status: str
    deterministic_summary: str
    generated_at: datetime
    shadow_stability_score: float | None
    baseline_run: ShadowRunSummary | None
    shadow_run: ShadowRunSummary | None
    metric_comparisons: list[ShadowMetricComparison]
    evidence_comparisons: list[ShadowEvidenceComparison]
    assumption_changes: list[ShadowAssumptionChange]
    trust_comparison: list[ShadowTrustComparison]
    production_checks: list[ShadowProductionCheck]
    highlighted_findings: list[str]
    blockers: list[str]
    suggested_actions: list[str]
