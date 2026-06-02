"""Pydantic schemas for Assumption Health (M41)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AssumptionCategoryScorecard(BaseModel):
    """Scorecard for one assumption category."""

    model_config = ConfigDict(from_attributes=True)

    category_key: str
    title: str
    status: str
    score: float | None
    evidence_count: int
    positive_evidence: list[str]
    review_items: list[str]
    weakening_changes: list[str]
    suggested_checks: list[str]


class ConfigDiffAssumptionSummary(BaseModel):
    """Summary of assumption-related changes between the two most recent config snapshots."""

    model_config = ConfigDict(from_attributes=True)

    snapshot_a_label: str | None = None
    snapshot_b_label: str | None = None
    total_changes: int = 0
    positive_change_count: int = 0
    weakening_change_count: int = 0
    review_change_count: int = 0
    key_assumption_changes: list[dict[str, Any]] = []
    warning: str | None = None


class BacktestAuditAssumptionSummary(BaseModel):
    """Relevant assumption-quality fields from the most recent backtest audit."""

    model_config = ConfigDict(from_attributes=True)

    backtest_audit_id: str
    trust_score: int
    overall_status: str
    cost_fragility_level: str | None = None
    fill_realism_level: str | None = None
    largest_penalty_category: str | None = None
    top_improvement_checks: list[Any] = []


class StrategyAssumptionHealthResponse(BaseModel):
    """Full assumption health response for a strategy (M41 endpoint)."""

    model_config = ConfigDict(from_attributes=True)

    strategy_id: str
    strategy_name: str
    status: str
    overall_assumption_score: float | None
    generated_at: datetime
    category_scorecards: list[AssumptionCategoryScorecard]
    latest_config_diff_summary: ConfigDiffAssumptionSummary | None = None
    latest_backtest_audit_summary: BacktestAuditAssumptionSummary | None = None
    key_assumption_changes: list[dict[str, Any]] = []
    weakening_change_count: int = 0
    positive_change_count: int = 0
    review_change_count: int = 0
    suggested_checks: list[str] = []
    deterministic_summary: str
