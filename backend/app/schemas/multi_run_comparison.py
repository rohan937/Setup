"""Pydantic schemas for multi-run cross-strategy comparison (M34).

No AI, no causal inference — strictly structured comparisons of logged run data.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RunMetricsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sharpe: float | None = None
    sortino: float | None = None
    annual_return: float | None = None
    volatility: float | None = None
    max_drawdown: float | None = None
    turnover: float | None = None
    hit_rate: float | None = None
    trade_count: float | None = None
    alpha_bps: float | None = None
    transaction_cost_bps: float | None = None
    slippage_bps: float | None = None


class RunAssumptionsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_cost_bps: float | None = None
    slippage_bps: float | None = None
    fill_model: str | None = None
    borrow_cost_bps: float | None = None
    short_enabled: bool | None = None
    execution_timing: str | None = None


class RunEvidenceSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_health_score: float | None = None
    dataset_issue_count: int = 0
    dataset_label: str | None = None
    signal_quality_score: float | None = None
    signal_missing_count: int = 0
    signal_label: str | None = None
    universe_symbol_count: int | None = None
    universe_label: str | None = None
    backtest_trust_score: float | None = None
    backtest_status: str | None = None
    backtest_issue_count: int = 0
    cost_fragility_level: str | None = None
    fill_realism_level: str | None = None
    run_health_label: str


class MultiRunItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    asset_class: str
    status: str
    run_id: uuid.UUID
    run_name: str
    run_type: str
    run_status: str
    completed_at: datetime | None = None
    created_at: datetime
    strategy_version_label: str | None = None
    open_alert_count: int
    reliability_score: float | None = None
    reliability_status: str | None = None
    evidence_coverage_score: float | None = None
    metrics: RunMetricsSchema
    assumptions: RunAssumptionsSchema
    evidence: RunEvidenceSummarySchema


class MultiRunRankingItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    strategy_id: uuid.UUID
    strategy_name: str
    value: float | None = None
    value_label: str
    run_name: str


class MultiRunComparisonRequest(BaseModel):
    strategy_ids: list[str]
    mode: str = "latest"
    run_ids: list[str] | None = None


class MultiRunComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    compared_at: datetime
    mode: str
    items: list[MultiRunItemSchema]
    metric_matrix: dict[str, Any]
    assumption_matrix: dict[str, Any]
    evidence_matrix: dict[str, Any]
    rankings: dict[str, list[MultiRunRankingItemSchema]]
    gaps: dict[str, list[str]]
    shared_gaps: list[str]
    highlighted_differences: list[str]
    deterministic_explanation: str
