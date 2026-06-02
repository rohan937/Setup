"""M60 Parameter Sweep Reliability Analysis — Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ParameterSweepAnalysisRequest(BaseModel):
    parameter_key: str | None = None
    analysis_label: str | None = None
    persist: bool = True


class DetectedParameter(BaseModel):
    parameter_key: str
    value_count: int
    numeric: bool
    unique_values: list[Any] = []
    coverage_rate: float
    examples: list[Any] = []


class ParameterSweepVariant(BaseModel):
    experiment_run_id: str
    run_id: str
    run_name: str
    run_type: str
    variant_label: str | None
    parameter_key: str | None
    parameter_value: str | None
    parameter_value_numeric: float | None
    sharpe: float | None
    annual_return: float | None
    max_drawdown: float | None
    volatility: float | None
    turnover: float | None
    hit_rate: float | None
    trade_count: int | None
    dataset_health: float | None
    signal_quality: float | None
    backtest_trust: float | None
    evidence_score: float
    variant_status: str
    review_reasons: list[str] = []
    suggested_checks: list[str] = []


class ParameterSweepMetricComparison(BaseModel):
    metric_key: str
    available_count: int
    min_value: float | None
    max_value: float | None
    mean_value: float | None
    range_value: float | None
    values_by_run_id: dict[str, Any] = {}


class ParameterSweepRegion(BaseModel):
    region_key: str
    label: str
    parameter_min: float | None
    parameter_max: float | None
    variant_count: int
    run_ids: list[str] = []
    status: str
    evidence_score_avg: float | None
    backtest_trust_avg: float | None
    metric_stability_score: float | None
    reason: str
    suggested_check: str | None


class ParameterSweepFragilitySignals(BaseModel):
    fragile_variant_count: int
    review_variant_count: int
    under_instrumented_variant_count: int
    narrow_peak_detected: bool
    evidence_degradation_detected: bool
    trust_degradation_detected: bool
    metric_instability_detected: bool


class ParameterSweepRankingItem(BaseModel):
    rank: int
    run_id: str
    variant_label: str | None
    parameter_value: str | None
    score: float | None
    reason: str


class ParameterSweepAnalysisResponse(BaseModel):
    experiment_id: str
    strategy_id: str
    parameter_key: str | None
    generated_at: datetime
    sweep_status: str
    sweep_reliability_score: float | None
    detected_parameters: list[DetectedParameter] = []
    variant_summaries: list[ParameterSweepVariant] = []
    metric_comparisons: list[ParameterSweepMetricComparison] = []
    regions: list[ParameterSweepRegion] = []
    fragility_signals: ParameterSweepFragilitySignals
    rankings: list[ParameterSweepRankingItem] = []
    suggested_checks: list[str] = []
    deterministic_summary: str
    analysis_id: str | None = None
