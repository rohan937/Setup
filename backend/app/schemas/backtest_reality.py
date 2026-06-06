"""Pydantic schemas for the M93 Backtest Reality Score service."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BacktestRealityCheckOut(BaseModel):
    """One individual Backtest Reality check result."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    title: str
    status: str  # pass | watch | fail | missing
    severity: str  # low | medium | high | critical
    explanation: str
    recommended_fix: str | None = None
    evidence_type: str  # assumptions | metrics | shadow | evidence | audit | oos | bias
    evidence_id: str | None = None


class BacktestRealityResponse(BaseModel):
    """Full Backtest Reality Score response for a strategy."""

    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    run_id: uuid.UUID | None = None
    strategy_name: str
    backtest_reality_score: float
    verdict: str  # realistic | acceptable | review | weak | insufficient_data
    severity: str  # low | medium | high | critical
    primary_concern: str | None = None
    checks: list[BacktestRealityCheckOut]
    top_concerns: list[str]
    suggested_actions: list[str]
    generated_at: datetime
    disclaimer: str


class BacktestRealityReportResponse(BaseModel):
    """Response wrapping a rendered Backtest Reality report (JSON or Markdown)."""

    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    format: str  # json | markdown
    content: str
    generated_at: datetime
