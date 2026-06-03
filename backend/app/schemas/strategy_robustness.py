"""M61: Strategy Robustness Score — Pydantic response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RobustnessDimensionScorecard(BaseModel):
    dimension_key: str
    title: str
    score: float | None = None
    status: str
    evidence_count: int = 0
    fragility_signals: list[str] = []
    positive_evidence: list[str] = []
    review_items: list[str] = []
    suggested_actions: list[str] = []
    source_refs_json: dict[str, Any] | None = None


class RobustnessFragilitySignal(BaseModel):
    signal_key: str
    title: str
    severity: str
    evidence_summary: str
    suggested_action: str
    source_dimension: str


class StrategyRobustnessResponse(BaseModel):
    strategy_id: str
    strategy_name: str
    generated_at: datetime
    robustness_score: float | None = None
    robustness_status: str
    robustness_verdict: str
    verdict_label: str
    deterministic_summary: str
    dimension_scorecards: list[RobustnessDimensionScorecard] = []
    fragility_signals: list[RobustnessFragilitySignal] = []
    top_review_drivers: list[str] = []
    suggested_actions: list[str] = []
    evidence_gaps: list[str] = []
    robustness_vs_readiness_note: str
