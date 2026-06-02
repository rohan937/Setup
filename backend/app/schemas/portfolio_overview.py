"""Pydantic schemas for the Portfolio Overview endpoint (M32)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PortfolioTrendFlags(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reliability_deteriorating: bool
    data_health_deteriorating: bool
    backtest_trust_deteriorating: bool
    signal_quality_deteriorating: bool


class PortfolioStrategyItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    name: str
    slug: str
    asset_class: str
    status: str
    health_score: float | None
    health_status: str
    primary_concern: str
    reliability_score: float | None
    reliability_status: str | None
    evidence_coverage_score: float
    open_alert_count: int
    high_critical_alert_count: int
    latest_run_at: datetime | None
    days_since_latest_run: int | None
    trend_flags: PortfolioTrendFlags
    missing_evidence_count: int
    review_reason: str | None


class PortfolioRecentActivityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_name: str
    event_type: str
    description: str
    timestamp: datetime


class PortfolioOverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    generated_at: datetime
    strategy_count: int
    active_strategy_count: int
    archived_strategy_count: int
    average_health_score: float | None
    average_reliability_score: float | None
    average_evidence_coverage_score: float | None
    open_alert_count: int
    high_critical_alert_count: int
    strategies_by_health_status: dict[str, int]
    strategies_by_reliability_status: dict[str, int]
    strategies_by_asset_class: dict[str, int]
    all_items: list[PortfolioStrategyItem]
    top_review_strategies: list[PortfolioStrategyItem]
    most_under_instrumented_strategies: list[PortfolioStrategyItem]
    strongest_evidence_strategies: list[PortfolioStrategyItem]
    deteriorating_trend_strategies: list[PortfolioStrategyItem]
    recent_activity: list[PortfolioRecentActivityItem]
    suggested_next_steps: list[str]
    deterministic_summary: str
