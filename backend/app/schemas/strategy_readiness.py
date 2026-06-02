"""Pydantic schemas for Strategy Readiness (M49).

GET /api/strategies/{strategy_id}/readiness → StrategyReadinessResponse
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StrategyReadinessDimension(BaseModel):
    dimension_key: str
    title: str
    score: float | None
    status: str
    evidence_summary: str
    blockers: list[str]
    warnings: list[str]
    suggested_actions: list[str]

    model_config = ConfigDict(from_attributes=True)


class StrategyProgressionPath(BaseModel):
    current_stage: str
    next_recommended_stage: str
    required_before_next_stage: list[str]

    model_config = ConfigDict(from_attributes=True)


class StrategyReadinessResponse(BaseModel):
    strategy_id: uuid.UUID
    strategy_name: str
    generated_at: datetime
    readiness_score: float | None
    readiness_verdict: str
    verdict_label: str
    verdict_summary: str
    deterministic_summary: str
    dimension_scorecards: list[StrategyReadinessDimension]
    blockers: list[str]
    review_items: list[str]
    suggested_next_actions: list[str]
    progression_path: StrategyProgressionPath

    model_config = ConfigDict(from_attributes=True)
