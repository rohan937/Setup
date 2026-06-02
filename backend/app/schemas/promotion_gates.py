"""Pydantic schemas for Promotion Gates (M51).

GET /api/strategies/{strategy_id}/promotion-gates → StrategyPromotionGateResponse
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PromotionGateCheck(BaseModel):
    gate_key: str
    title: str
    category: str
    required: bool
    passed: bool
    status: str
    severity: str
    observed_value: Optional[str] = None
    required_value: Optional[str] = None
    evidence_summary: str
    suggested_action: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class StrategyPromotionGateResponse(BaseModel):
    strategy_id: uuid.UUID
    strategy_name: str
    generated_at: datetime
    current_stage: str
    target_stage: str
    stage_path: list[str]
    promotion_verdict: str
    gate_score: Optional[float] = None
    gate_checks: list[PromotionGateCheck]
    required_pass_count: int
    required_fail_count: int
    recommended_pass_count: int
    recommended_fail_count: int
    blocker_count: int
    review_count: int
    blockers: list[str]
    warnings: list[str]
    suggested_actions: list[str]
    deterministic_summary: str
    note: str

    model_config = ConfigDict(from_attributes=True)
