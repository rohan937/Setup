"""Pydantic schemas for M9: Unified Reliability Dashboard summary endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------

class DashboardCounts(BaseModel):
    """Raw counts of persisted evidence objects."""

    # Strategies
    total_strategies: int
    active_strategies: int
    archived_strategies: int
    strategies_by_asset_class: dict[str, int]

    # Runs
    total_runs: int
    backtest_run_count: int
    research_run_count: int
    paper_run_count: int
    live_run_count: int
    latest_run_at: datetime | None

    # Data
    total_datasets: int
    total_dataset_snapshots: int
    snapshots_with_issues: int
    total_data_quality_issues: int
    data_issues_by_severity: dict[str, int]

    # Backtest audits
    total_backtest_audits: int
    total_backtest_issues: int
    backtest_issues_by_severity: dict[str, int]
    audits_by_status: dict[str, int]

    # Alerts (M11)
    open_alert_count: int
    high_critical_alert_count: int


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------

class DashboardScores(BaseModel):
    """Aggregated reliability scores.

    All scores are 0–100 or ``None`` when no evidence exists.
    ``None`` is the correct value when a dimension has not been instrumented —
    we never return a fake score.
    """

    # Average health score across all dataset snapshots; null if no snapshots.
    data_health_score: float | None
    # Lowest single snapshot health score; null if no snapshots.
    lowest_data_health_score: int | None
    # Average trust score across all backtest audits; null if no audits.
    backtest_trust_score: float | None
    # Lowest single audit trust score; null if no audits.
    lowest_backtest_trust_score: int | None
    # Simple deterministic score based on strategy count and recent activity.
    strategy_activity_score: float | None
    # Weighted average of available non-null dimension scores.
    overall_reliability_score: float | None


# ---------------------------------------------------------------------------
# Alert summary item (M11)
# ---------------------------------------------------------------------------

class DashboardAlertItem(BaseModel):
    """Lightweight alert row for the dashboard panel."""

    id: uuid.UUID
    rule_type: str
    severity: str
    status: str
    title: str
    triggered_at: datetime
    strategy_id: uuid.UUID | None


# ---------------------------------------------------------------------------
# Recent evidence items (lightweight)
# ---------------------------------------------------------------------------

class RecentEvidenceItem(BaseModel):
    """One entry in a recent-evidence list.

    Kept lightweight: no raw payloads, just the key display fields.
    """

    id: uuid.UUID
    item_type: str           # "run" | "snapshot" | "audit" | "timeline_event"
    title: str
    strategy_name: str | None
    score: float | None      # health_score, trust_score, etc. where applicable
    status: str | None       # overall_status, severity, run_status, etc.
    timestamp: datetime


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------

class DashboardSummary(BaseModel):
    """Full dashboard summary response from GET /api/dashboard/summary."""

    generated_at: datetime
    counts: DashboardCounts
    scores: DashboardScores
    # Recent evidence arrays — most-recent-first, capped at small N.
    recent_runs: list[RecentEvidenceItem]
    recent_snapshots: list[RecentEvidenceItem]
    recent_audits: list[RecentEvidenceItem]
    recent_timeline_events: list[RecentEvidenceItem]
    # Alerts (M11) — most-recent open alerts first
    recent_alerts: list[DashboardAlertItem]
