"""Pydantic schemas for M59 Experiment Registry."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


def _to_str(v: Any) -> str:
    if v is None:
        return v  # type: ignore[return-value]
    return str(v)


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------

class StrategyExperimentCreate(BaseModel):
    name: str
    description: str | None = None
    experiment_type: str | None = None
    hypothesis: str | None = None
    slug: str | None = None
    metadata_json: dict[str, Any] | None = None


class StrategyExperimentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_id: str
    name: str
    slug: str
    description: str | None
    experiment_type: str | None
    hypothesis: str | None
    status: str
    metadata_json: dict[str, Any] | None
    run_count: int = 0
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "strategy_id", mode="before")
    @classmethod
    def coerce_ids(cls, v: Any) -> str:
        return str(v)


class StrategyExperimentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    experiment_id: str
    strategy_run_id: str
    variant_label: str | None
    variant_key: str | None
    variant_params_json: dict[str, Any] | None
    notes: str | None
    created_at: datetime

    @field_validator("id", "experiment_id", "strategy_run_id", mode="before")
    @classmethod
    def coerce_ids(cls, v: Any) -> str:
        return str(v)


class StrategyExperimentDetail(StrategyExperimentRead):
    experiment_runs: list[StrategyExperimentRunRead] = []


# ---------------------------------------------------------------------------
# Run membership
# ---------------------------------------------------------------------------

class ExperimentRunAddRequest(BaseModel):
    strategy_run_id: str
    variant_label: str | None = None
    variant_key: str | None = None
    variant_params_json: dict[str, Any] | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Analysis schemas
# ---------------------------------------------------------------------------

class ExperimentMetricComparison(BaseModel):
    metric_key: str
    available_count: int
    min_value: float | None
    max_value: float | None
    mean_value: float | None
    spread: float | None
    values_by_run_id: dict[str, float]


class ExperimentVariantSummary(BaseModel):
    experiment_run_id: str
    run_id: str
    run_name: str
    run_type: str
    variant_label: str | None
    variant_key: str | None
    variant_params_json: dict[str, Any] | None
    evidence_score: int
    trust_score: float | None
    dataset_health: float | None
    signal_quality: float | None
    replay_completeness: float | None = None
    variant_status: str
    review_reasons: list[str]


class ExperimentRankingItem(BaseModel):
    rank: int
    run_id: str
    variant_label: str | None
    score: float | None
    reason: str


class StrategyExperimentAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    experiment_id: str
    analysis_label: str | None
    overall_status: str
    variant_count: int
    run_count: int
    best_evidenced_run_id: str | None
    weakest_evidence_run_id: str | None
    deterministic_summary: str | None
    result_json: dict[str, Any] | None
    created_at: datetime

    @field_validator("id", "experiment_id", mode="before")
    @classmethod
    def coerce_ids(cls, v: Any) -> str:
        return str(v)


class StrategyExperimentAnalysisListResponse(BaseModel):
    items: list[StrategyExperimentAnalysisRead]
    total: int
