"""M76 Strategy Lifecycle schema.

Deterministic stage inference for the lifecycle visual. No AI, no external
data, no trading recommendations — purely derived from existing evidence,
promotion gates, and the action queue.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LifecycleStage(BaseModel):
    key: str
    label: str
    index: int
    state: str  # completed | current | blocked | upcoming


class LifecycleBlocker(BaseModel):
    reason: str
    detail: str
    severity: str            # critical | high | medium | low | info
    action_type: str         # link_evidence | navigate | create_policy | ...
    action_label: str
    target_tab: str | None = None
    related_run_id: str | None = None


class StrategyLifecycleResponse(BaseModel):
    strategy_id: str
    strategy_name: str
    generated_at: datetime
    stages: list[LifecycleStage] = []
    current_stage: str
    current_stage_label: str
    next_stage: str | None = None
    next_stage_label: str | None = None
    blocked: bool = False
    blocked_stage: str | None = None
    blocked_stage_label: str | None = None
    blockers: list[LifecycleBlocker] = []
    suggested_actions: list[str] = []
    deterministic_summary: str
    disclaimer: str = (
        "Lifecycle stage is inferred from research evidence. It is not a trading "
        "recommendation."
    )
