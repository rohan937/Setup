"""M62: Pydantic schemas for Strategy Progression Freeze Recommendations."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ProgressionFreezeReason(BaseModel):
    reason_key: str
    title: str
    category: str
    severity: str
    status: str
    evidence_summary: str
    source_label: str
    source_id: str | None = None
    suggested_resolution: str = ""
    required_to_unfreeze: bool = False


class ProgressionUnfreezeRequirement(BaseModel):
    requirement_key: str
    title: str
    priority: str
    required: bool
    current_status: str
    target_status: str
    suggested_action: str
    endpoint_hint: str | None = None


class ProgressionSubsystemStatus(BaseModel):
    subsystem: str
    status: str
    summary: str | None = None
    score: float | None = None


class ProgressionStageContext(BaseModel):
    current_stage: str
    target_stage: str
    next_recommended_stage: str
    stage_path: list[str] = []


class StrategyProgressionFreezeResponse(BaseModel):
    strategy_id: str
    strategy_name: str
    generated_at: datetime
    target_stage: str
    current_stage: str
    recommendation: str
    recommendation_label: str
    freeze_risk_score: float
    deterministic_summary: str
    freeze_reasons: list[ProgressionFreezeReason] = []
    unfreeze_requirements: list[ProgressionUnfreezeRequirement] = []
    blocking_reason_count: int = 0
    review_reason_count: int = 0
    watch_reason_count: int = 0
    missing_evidence_count: int = 0
    subsystem_statuses: list[ProgressionSubsystemStatus] = []
    stage_context: ProgressionStageContext
    note: str
