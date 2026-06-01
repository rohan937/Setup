"""Evidence coverage matrix endpoint (M21).

GET /api/evidence/coverage — returns an evidence coverage matrix for all
non-archived strategies (by default), with per-strategy per-column cell
statuses and an aggregate summary.

Design rules:
  - Deterministic — no AI, no live market data, no external calls.
  - Read-only — no audit timeline event is created.
  - Approved language: "Evidence Coverage", "Instrumentation Coverage",
    "Missing Evidence", "Review Required", "Suggested Next Steps".
  - Forbidden: AI recommendations, investment advice, alpha language.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.evidence_coverage import (
    EvidenceCoverageCell,
    EvidenceCoverageSummary,
    EvidenceCoverageMatrixResponse,
    StrategyEvidenceCoverageRow,
)
from app.services.evidence_coverage import (
    EvidenceCellData,
    EvidenceCoverageMatrixData,
    StrategyEvidenceCoverageRowData,
    get_evidence_coverage_matrix,
)

router = APIRouter(tags=["evidence"])


def _cell(c: EvidenceCellData) -> EvidenceCoverageCell:
    return EvidenceCoverageCell(
        status=c.status,
        count=c.count,
        latest_at=c.latest_at,
        summary=c.summary,
        suggested_check=c.suggested_check,
    )


def _row(r: StrategyEvidenceCoverageRowData) -> StrategyEvidenceCoverageRow:
    return StrategyEvidenceCoverageRow(
        strategy_id=r.strategy_id,
        name=r.name,
        slug=r.slug,
        asset_class=r.asset_class,
        status=r.status,
        evidence_coverage_score=r.evidence_coverage_score,
        missing_count=r.missing_count,
        review_count=r.review_count,
        partial_count=r.partial_count,
        complete_count=r.complete_count,
        strategy_runs=_cell(r.strategy_runs),
        backtest_runs=_cell(r.backtest_runs),
        dataset_evidence=_cell(r.dataset_evidence),
        backtest_audits=_cell(r.backtest_audits),
        config_snapshots=_cell(r.config_snapshots),
        universe_snapshots=_cell(r.universe_snapshots),
        signal_snapshots=_cell(r.signal_snapshots),
        alerts=_cell(r.alerts),
        reports=_cell(r.reports),
        reliability_scores=_cell(r.reliability_scores),
        timeline_events=_cell(r.timeline_events),
        suggested_next_steps=r.suggested_next_steps,
    )


@router.get("/evidence/coverage", response_model=EvidenceCoverageMatrixResponse)
def get_evidence_coverage(
    include_archived: bool = Query(
        default=False,
        description="Include archived strategies in the matrix.",
    ),
    asset_class: str | None = Query(
        default=None,
        description="Filter by asset_class (exact match, e.g. 'equity').",
    ),
    status: str | None = Query(
        default=None,
        description="Filter by strategy status (exact match, e.g. 'active').",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of rows to return (1–500).",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Pagination offset.",
    ),
    db: Session = Depends(get_db),
) -> EvidenceCoverageMatrixResponse:
    """Return the evidence coverage matrix for strategies.

    For each strategy, returns a row with 11 evidence columns, each with a
    status (complete/partial/review/missing), count, latest_at timestamp,
    summary text, and optional suggested_check.

    The response also includes an aggregate ``summary`` computed over *all*
    matched strategies (not just the current page), showing average coverage
    score and the most commonly missing evidence layers.

    Evidence coverage score (0–100):
      Average of per-cell status weights × 100
      complete=1.0, partial=0.6, review=0.4, missing=0.0

    Read-only — no audit timeline event created.
    Not investment advice.
    """
    result: EvidenceCoverageMatrixData = get_evidence_coverage_matrix(
        db,
        include_archived=include_archived,
        asset_class=asset_class,
        status=status,
        limit=limit,
        offset=offset,
    )

    summary = EvidenceCoverageSummary(
        strategy_count=result.summary.strategy_count,
        average_coverage_score=result.summary.average_coverage_score,
        complete_cell_count=result.summary.complete_cell_count,
        partial_cell_count=result.summary.partial_cell_count,
        review_cell_count=result.summary.review_cell_count,
        missing_cell_count=result.summary.missing_cell_count,
        most_common_missing_evidence=result.summary.most_common_missing_evidence,
    )

    return EvidenceCoverageMatrixResponse(
        items=[_row(r) for r in result.items],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
        generated_at=result.generated_at,
        summary=summary,
    )
