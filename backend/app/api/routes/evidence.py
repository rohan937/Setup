"""Evidence endpoints (M21, M22).

GET /api/evidence/coverage — evidence coverage matrix for all strategies.
POST /api/strategies/{strategy_id}/evidence-bundles — ingest an evidence bundle.
GET  /api/strategies/{strategy_id}/evidence-bundles/example — example payload.

Design rules:
  - Deterministic — no AI, no live market data, no external calls.
  - Approved language: "Evidence Coverage", "Instrumentation Coverage",
    "Missing Evidence", "Review Required", "Suggested Next Steps".
  - Forbidden: AI recommendations, investment advice, alpha language.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.organization import Organization
from app.models.project import Project
from app.models.strategy import Strategy
from app.schemas.evidence_coverage import (
    EvidenceCoverageCell,
    EvidenceCoverageSummary,
    EvidenceCoverageMatrixResponse,
    StrategyEvidenceCoverageRow,
)
from app.schemas.evidence_ingestion import (
    EvidenceBundleObjectRef,
    EvidenceBundleRequest,
    EvidenceBundleResponse,
)
from app.services.evidence_coverage import (
    EvidenceCellData,
    EvidenceCoverageMatrixData,
    StrategyEvidenceCoverageRowData,
    get_evidence_coverage_matrix,
)
from app.services.evidence_ingestion import EvidenceBundleResult, ingest_evidence_bundle

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


def _get_default_org(db: Session) -> Organization:
    org = db.query(Organization).first()
    if org is None:
        raise HTTPException(status_code=500, detail="No organization found in database")
    return org


def _build_bundle_response(result: EvidenceBundleResult) -> EvidenceBundleResponse:
    objects: dict[str, EvidenceBundleObjectRef | None] = {}
    for key, val in result.objects.items():
        if val is not None:
            objects[key] = EvidenceBundleObjectRef(
                id=val["id"],
                name=val["name"],
                type=val["type"],
                status=val["status"],
            )
        else:
            objects[key] = None
    return EvidenceBundleResponse(
        strategy_id=result.strategy_id,
        created_count=result.created_count,
        reused_count=result.reused_count,
        actions_run=result.actions_run,
        objects=objects,
        alerts_generated=result.alerts_generated,
        warnings=result.warnings,
        summary=result.summary,
        timeline_events_created=result.timeline_events_created,
        generated_at=result.generated_at,
    )


# ---------------------------------------------------------------------------
# GET /api/strategies/{strategy_id}/evidence-bundles/example
# Must be declared BEFORE the POST to avoid ambiguity (path vs body).
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/evidence-bundles/example",
    response_model=None,
    tags=["evidence"],
    summary="Return an example evidence bundle payload",
)
def get_evidence_bundle_example(strategy_id: uuid.UUID) -> Any:
    """Return a fully-populated example EvidenceBundleRequest payload.

    Useful for documentation and the frontend 'Load Example' button.
    """
    return {
        "strategy_version": {
            "version_label": "v2.0.0",
            "git_commit": "abc123def456",
            "branch_name": "main",
            "code_path": "strategies/mean_reversion.py",
            "signal_name": "z_score",
            "signal_description": "Z-score of 20-day rolling return",
        },
        "config_snapshot": {
            "label": "config-v2",
            "source_type": "manual_json",
            "config_json": {
                "params": {"lookback": 20, "entry_z": 2.0, "exit_z": 0.5},
                "assumptions": {
                    "transaction_cost_bps": 5,
                    "fill_model": "next_open",
                },
            },
        },
        "universe_snapshot": {
            "label": "sp500-2024",
            "symbols": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
            "metadata_json": {"universe_type": "sp500", "rebalance_freq": "monthly"},
        },
        "signal_snapshot": {
            "label": "z-score-signals-2024",
            "signal_name": "z_score",
            "signal_column": "signal",
            "rows": [
                {"symbol": "AAPL", "timestamp": "2024-01-02", "signal": 1.5},
                {"symbol": "MSFT", "timestamp": "2024-01-02", "signal": -0.8},
            ],
        },
        "dataset": {
            "name": "SP500 OHLCV 2024",
            "description": "Daily OHLCV data for S&P 500 constituents",
            "dataset_type": "equity_prices",
            "source_type": "csv_upload",
        },
        "dataset_snapshot": {
            "snapshot_label": "2024-q1",
            "rows": [
                {
                    "symbol": "AAPL",
                    "timestamp": "2024-01-02",
                    "open": 185.0,
                    "high": 188.0,
                    "low": 184.5,
                    "close": 187.2,
                    "volume": 50000000,
                },
            ],
        },
        "strategy_run": {
            "run_name": "backtest-2024-q1",
            "run_type": "backtest",
            "status": "completed",
            "params_json": {"lookback": 20},
            "assumptions_json": {"transaction_cost_bps": 5, "fill_model": "next_open"},
            "metrics_json": {
                "sharpe": 1.4,
                "annual_return": 0.18,
                "max_drawdown": -0.12,
                "num_trades": 124,
            },
        },
        "actions": {
            "run_backtest_audit": True,
            "compute_reliability_score": True,
            "generate_strategy_report": False,
            "generate_alerts": False,
        },
    }


# ---------------------------------------------------------------------------
# POST /api/strategies/{strategy_id}/evidence-bundles
# ---------------------------------------------------------------------------

@router.post(
    "/strategies/{strategy_id}/evidence-bundles",
    response_model=EvidenceBundleResponse,
    status_code=201,
    tags=["evidence"],
    summary="Ingest an evidence bundle for a strategy",
)
def ingest_bundle(
    strategy_id: uuid.UUID,
    bundle: EvidenceBundleRequest,
    db: Session = Depends(get_db),
) -> EvidenceBundleResponse:
    """Ingest a structured evidence bundle for a strategy in a single transaction.

    Accepts any combination of: strategy_version, config_snapshot,
    universe_snapshot, signal_snapshot, dataset, dataset_snapshot,
    strategy_run, and post-ingestion actions.

    Returns 404 if the strategy does not exist.
    Returns 422 on validation errors.
    Returns 500 on unexpected errors (transaction is rolled back).
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    project = db.query(Project).filter(Project.id == strategy.project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    org = _get_default_org(db)

    try:
        result = ingest_evidence_bundle(
            strategy_id=strategy_id,
            bundle=bundle,
            db=db,
            org_id=org.id,
            project_id=project.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Evidence bundle ingestion failed: {exc}",
        ) from exc

    db.commit()
    return _build_bundle_response(result)


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
