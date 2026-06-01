"""Pydantic schemas for the evidence coverage matrix (M21).

GET /api/evidence/coverage → EvidenceCoverageMatrixResponse
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class EvidenceCoverageCell(BaseModel):
    """Coverage status and metadata for a single evidence layer."""

    status: str          # "complete" | "partial" | "review" | "missing"
    count: int
    latest_at: datetime | None
    summary: str
    suggested_check: str | None


class StrategyEvidenceCoverageRow(BaseModel):
    """Full coverage row for one strategy across all 11 evidence columns."""

    strategy_id: uuid.UUID
    name: str
    slug: str
    asset_class: str
    status: str

    # Overall coverage score (0–100)
    evidence_coverage_score: float

    # Per-status cell counts
    missing_count: int
    review_count: int
    partial_count: int
    complete_count: int

    # Per-column evidence cells
    strategy_runs: EvidenceCoverageCell
    backtest_runs: EvidenceCoverageCell
    dataset_evidence: EvidenceCoverageCell
    backtest_audits: EvidenceCoverageCell
    config_snapshots: EvidenceCoverageCell
    universe_snapshots: EvidenceCoverageCell
    signal_snapshots: EvidenceCoverageCell
    alerts: EvidenceCoverageCell
    reports: EvidenceCoverageCell
    reliability_scores: EvidenceCoverageCell
    timeline_events: EvidenceCoverageCell

    # Prioritised list of actions to improve coverage (missing first, then review, partial)
    suggested_next_steps: list[str]


class EvidenceCoverageSummary(BaseModel):
    """Aggregate summary computed over ALL matched strategies (not just the page)."""

    strategy_count: int
    average_coverage_score: float

    # Cell counts across all strategies × all columns
    complete_cell_count: int
    partial_cell_count: int
    review_cell_count: int
    missing_cell_count: int

    # Top evidence columns that are missing or under review (most common first)
    most_common_missing_evidence: list[str]


class EvidenceCoverageMatrixResponse(BaseModel):
    """Paginated evidence coverage matrix response."""

    items: list[StrategyEvidenceCoverageRow]
    total: int
    limit: int
    offset: int
    generated_at: datetime
    summary: EvidenceCoverageSummary
