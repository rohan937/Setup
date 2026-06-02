"""Pydantic schemas for Backtest Reality Check (M8 + M13)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class BacktestIssueRead(BaseModel):
    """One detected realism concern."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    issue_type: str
    severity: str
    title: str
    description: str
    evidence_json: dict | None = None
    suggested_check: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# M13: Typed nested schemas for cost sensitivity, fill realism, fragility
# ---------------------------------------------------------------------------


class CostSensitivityScenario(BaseModel):
    """Estimated performance at a single cost scenario (read-only, never persisted)."""

    cost_bps: float
    incremental_cost_drag: float | None = None
    adjusted_annual_return: float | None = None
    adjusted_sharpe: float | None = None
    sharpe_delta: float | None = None


class CostSensitivityResult(BaseModel):
    """Full cost sensitivity analysis blob.

    All numeric values are *estimates* — not a full re-backtest.
    """

    assumed_cost_bps: float | None = None
    turnover: float | None = None
    base_annual_return: float | None = None
    base_sharpe: float | None = None
    scenarios: list[CostSensitivityScenario] = []
    warnings: list[str] = []
    cost_fragility_level: str = "unknown"


class FillRealismFinding(BaseModel):
    """A single observation from fill realism analysis."""

    code: str
    severity: str
    message: str


class FillRealismResult(BaseModel):
    """Full fill realism analysis blob."""

    fill_model: str | None = None
    slippage_bps: float | None = None
    execution_timing: str | None = None
    participation_rate: float | None = None
    liquidity_filter_present: bool | None = None
    fill_realism_level: str = "unknown"
    findings: list[FillRealismFinding] = []


class FragilitySummary(BaseModel):
    """Rolled-up fragility from cost sensitivity + fill realism."""

    overall_fragility: str = "unknown"
    cost_fragility_level: str = "unknown"
    fill_realism_level: str = "unknown"
    key_concerns: list[str] = []


# ---------------------------------------------------------------------------
# Core audit schemas
# ---------------------------------------------------------------------------


class BacktestAuditRead(BaseModel):
    """Core audit fields — no issues list.

    Used as a base for ``BacktestAuditDetail`` and ``BacktestAuditListItem``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_run_id: uuid.UUID
    trust_score: int
    lookahead_risk_score: int
    cost_realism_score: int
    fill_realism_score: int
    liquidity_realism_score: int
    borrow_realism_score: int
    data_quality_score: int
    overall_status: str
    summary: str
    # M13: optional JSON analysis blobs (None when insufficient input data)
    cost_sensitivity_json: dict[str, Any] | None = None
    fill_realism_json: dict[str, Any] | None = None
    fragility_summary_json: dict[str, Any] | None = None
    # M36: extended v3 analysis blobs (None for audits created before M36)
    cost_sensitivity_sweep_json: dict[str, Any] | None = None
    fill_sensitivity_json: dict[str, Any] | None = None
    penalty_attribution_json: dict[str, Any] | None = None
    improvement_checks_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class BacktestAuditDetail(BacktestAuditRead):
    """Full audit with all issues — returned by POST and GET single-audit."""

    issues: list[BacktestIssueRead]


class BacktestAuditListItem(BacktestAuditRead):
    """Audit enriched with run/strategy context for the global list view."""

    strategy_id: uuid.UUID
    strategy_name: str
    run_name: str
    run_type: str
    issue_count: int
    # Top 3 issues ordered by severity (most severe first).
    top_issues: list[BacktestIssueRead]
    # M13: extracted fragility levels for quick display (None when not available).
    cost_fragility_level: str | None = None
    fill_realism_level: str | None = None
    # M36: extracted quick-display fields for list view.
    largest_penalty_category: str | None = None
    most_fragile_cost_scenario: str | None = None
    worst_fill_scenario: str | None = None
