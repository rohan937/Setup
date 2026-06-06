"""Pydantic schemas for the Portfolio Reliability endpoints (M86).

The service returns plain dicts; routes construct these models via
``Model(**payload)``.  ``from_attributes`` is enabled so the models can also be
built from dataclasses / ORM objects where convenient.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PortfolioReliabilityTopBlocker(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    severity: str
    category: str
    recommended_action: str
    target_tab: str


class PortfolioReliabilityRecentScoreChange(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    delta: float
    latest: float
    previous: float
    direction: str  # up | down | flat


class PortfolioReliabilityPendingReview(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_id: str
    target_stage: str
    status: str
    reviewer_user_id: str | None = None


class PortfolioReliabilityStrategyRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    name: str
    slug: str
    project_id: uuid.UUID | None
    project_name: str | None
    asset_class: str
    status: str
    reliability_score: float | None
    reliability_status: str | None
    health_classification: str  # blocked | review | healthy
    health_status: str
    promotion_stage: str | None
    open_alert_count: int
    high_critical_alert_count: int
    top_blocker: PortfolioReliabilityTopBlocker | None
    stale_evidence_count: int
    missing_report: bool
    recent_score_change: PortfolioReliabilityRecentScoreChange | None
    latest_run_at: datetime | None
    days_since_latest_run: int | None
    owner_user_id: str | None
    owner_name: str | None
    regression_failed_count: int
    pending_review: PortfolioReliabilityPendingReview | None = None
    shadow_verdict: str | None = None
    shadow_drift_score: float | None = None
    shadow_primary_concern: str | None = None
    has_paper_run: bool = False
    has_shadow_run: bool = False


class PortfolioReliabilitySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_strategies: int
    healthy_count: int
    review_count: int
    blocked_count: int
    average_reliability: float | None
    strategies_with_stale_evidence: int
    strategies_missing_reports: int
    open_high_critical_alerts: int
    ready_for_paper_candidate: int
    ready_for_production_candidate: int


class PortfolioWorstBlockerItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    blocker_title: str
    severity: str
    recommended_action: str
    category: str
    target_tab: str


class PortfolioStaleEvidenceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    stale_count: int
    missing_count: int
    aging_count: int


class PortfolioMissingReportItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    latest_run_at: datetime | None


class PortfolioRecentScoreChangeItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    delta: float
    latest: float
    previous: float
    direction: str


class PortfolioReliabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    generated_at: datetime
    summary: PortfolioReliabilitySummary
    strategies: list[PortfolioReliabilityStrategyRow]
    worst_blockers: list[PortfolioWorstBlockerItem]
    stale_evidence: list[PortfolioStaleEvidenceItem]
    missing_reports: list[PortfolioMissingReportItem]
    recent_score_changes: list[PortfolioRecentScoreChangeItem]
    disclaimer: str


class PortfolioExportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    filename: str
    format: str
    content: str | None
