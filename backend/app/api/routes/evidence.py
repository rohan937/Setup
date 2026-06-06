"""Evidence endpoints (M21, M22, M25).

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

import hashlib
import json as json_lib
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.auth import require_api_key_if_enabled
from app.core.rbac import require_verified_email, require_workspace_write_access
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.organization import Organization
from app.models.project import Project
from app.models.sdk_ingestion_batch import SdkIngestionBatch
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
from app.schemas.evidence_bundle_grader import (
    BundleGradeResponse,
    BundleIncludedItem,
    BundleMissingItem,
    BundleGradeReportResponse,
)
from app.services.evidence_bundle_grader import (
    grade_evidence_bundle,
    generate_bundle_quality_report,
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


def _get_default_org(db: Session) -> Organization:
    org = db.query(Organization).first()
    if org is None:
        raise HTTPException(status_code=500, detail="No organization found in database")
    return org


def _compute_request_hash(bundle: EvidenceBundleRequest) -> str:
    """Compute a deterministic SHA-256 hash of the bundle payload (excluding idempotency_key)."""
    payload = bundle.model_dump(exclude={"idempotency_key"})
    return hashlib.sha256(
        json_lib.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


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
    api_key: ApiKey | None = Depends(require_api_key_if_enabled),
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    # M72: enforce M69 RBAC write-access for web/JWT users (viewer -> 403).
    # SDK/CI callers authenticate with an API key (no JWT) and resolve to a
    # permissive local pseudo-owner, so this does not break SDK ingestion.
    _member=Depends(require_workspace_write_access),
    _verified=Depends(require_verified_email),
) -> EvidenceBundleResponse:
    """Ingest a structured evidence bundle for a strategy in a single transaction.

    Accepts any combination of: strategy_version, config_snapshot,
    universe_snapshot, signal_snapshot, dataset, dataset_snapshot,
    strategy_run, and post-ingestion actions.

    Returns 404 if the strategy does not exist.
    Returns 422 on validation errors.
    Returns 409 if the idempotency key was already used with a different payload.
    Returns 500 on unexpected errors (transaction is rolled back).
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    project = db.query(Project).filter(Project.id == strategy.project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Enforce API key scopes and project scope (M28)
    if api_key is not None:
        # Enforce evidence:write scope
        scopes = api_key.scopes_json or []
        if scopes and "evidence:write" not in scopes:
            raise HTTPException(
                status_code=403,
                detail="API key does not have evidence:write scope.",
            )

        # Enforce project scope if api_key.project_id is set
        # api_key.project_id is String(36); strategy.project_id is Uuid(as_uuid=True)
        # Compare both as strings to avoid type mismatch.
        if api_key.project_id is not None:
            key_proj = str(api_key.project_id)
            strat_proj = str(strategy.project_id)
            if key_proj != strat_proj:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "API key is scoped to a different project. "
                        "This strategy belongs to a different project."
                    ),
                )

    org = _get_default_org(db)

    # Resolve idempotency key (header takes precedence over body)
    idem_key = idempotency_key_header or bundle.idempotency_key
    now = datetime.now(timezone.utc)
    existing_batch: SdkIngestionBatch | None = None
    batch_prior_status: str | None = None

    if idem_key:
        request_hash = _compute_request_hash(bundle)

        existing_batch = (
            db.query(SdkIngestionBatch)
            .filter(
                SdkIngestionBatch.strategy_id == strategy_id,
                SdkIngestionBatch.idempotency_key == idem_key,
            )
            .first()
        )

        if existing_batch is not None:
            if existing_batch.status == "completed" and existing_batch.request_hash == request_hash:
                # REPLAY: return stored response unchanged
                stored = dict(existing_batch.response_json or {})
                stored["idempotency_status"] = "replayed"
                stored["idempotency_key"] = idem_key
                stored["ingestion_batch_id"] = str(existing_batch.id)
                return EvidenceBundleResponse(**stored)
            elif existing_batch.status == "completed":
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key already used with a different payload.",
                )
            elif existing_batch.status == "received":
                raise HTTPException(
                    status_code=409,
                    detail="Ingestion already in progress for this idempotency key.",
                )
            elif existing_batch.status == "failed":
                # Allow retry: reset to received
                batch_prior_status = "failed"
                existing_batch.status = "received"
                existing_batch.request_hash = request_hash
                existing_batch.error_json = None
                existing_batch.received_at = now
                db.flush()
        else:
            # Create new batch record
            org_id_str: str | None = None
            if project is not None:
                org_id_str = str(project.organization_id) if project.organization_id else None
            api_key_id_val = uuid.UUID(str(api_key.id)) if api_key is not None else None
            batch = SdkIngestionBatch(
                strategy_id=strategy_id,
                organization_id=org_id_str,
                project_id=str(project.id) if project is not None else None,
                idempotency_key=idem_key,
                request_hash=request_hash,
                status="received",
                received_at=now,
                api_key_id=api_key_id_val,
            )
            db.add(batch)
            db.flush()
            existing_batch = batch

    try:
        result = ingest_evidence_bundle(
            strategy_id=strategy_id,
            bundle=bundle,
            db=db,
            org_id=org.id,
            project_id=project.id,
        )
    except ValueError as exc:
        if idem_key and existing_batch is not None:
            existing_batch.status = "failed"
            existing_batch.error_json = {"detail": str(exc)}
            db.flush()
            db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        if idem_key and existing_batch is not None:
            existing_batch.status = "failed"
            existing_batch.error_json = {"detail": str(exc)}
            try:
                db.flush()
            except Exception:
                pass
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Evidence bundle ingestion failed: {exc}",
        ) from exc

    bundle_response = _build_bundle_response(result)

    # Attach idempotency metadata and persist the batch record
    if idem_key and existing_batch is not None:
        bundle_response.idempotency_key = idem_key
        bundle_response.idempotency_status = (
            "retried_after_failure" if batch_prior_status == "failed" else "new"
        )
        bundle_response.ingestion_batch_id = existing_batch.id
        existing_batch.status = "completed"
        existing_batch.completed_at = datetime.now(timezone.utc)
        existing_batch.response_json = bundle_response.model_dump(mode="json")
        existing_batch.created_object_refs_json = bundle_response.model_dump(mode="json").get("objects")
        db.flush()

    db.commit()
    return bundle_response


# ---------------------------------------------------------------------------
# M97: Evidence Bundle Quality Grader endpoints (read-only, no strategy_id, no DB writes)
# ---------------------------------------------------------------------------


def _build_grade_response(data) -> BundleGradeResponse:
    return BundleGradeResponse(
        quality_score=data.quality_score,
        letter_grade=data.letter_grade,
        verdict=data.verdict,
        stage_sufficiency=data.stage_sufficiency,
        sufficient_for=data.sufficient_for,
        not_sufficient_for=data.not_sufficient_for,
        included=[
            BundleIncludedItem(
                key=i.key,
                label=i.label,
                status=i.status,
                quality=i.quality,
                details=i.details,
            )
            for i in data.included
        ],
        missing=[
            BundleMissingItem(
                key=m.key,
                label=m.label,
                severity=m.severity,
                why_it_matters=m.why_it_matters,
            )
            for m in data.missing
        ],
        warnings=data.warnings,
        recommended_fixes=data.recommended_fixes,
        generated_at=data.generated_at,
        disclaimer=data.disclaimer,
    )


@router.post(
    "/evidence-bundles/grade",
    response_model=BundleGradeResponse,
    tags=["evidence"],
)
def grade_bundle(bundle: EvidenceBundleRequest) -> BundleGradeResponse:
    """Grade an evidence bundle before ingestion. Read-only structural analysis — no DB writes."""
    data = grade_evidence_bundle(bundle.model_dump())
    return _build_grade_response(data)


@router.post(
    "/evidence-bundles/grade/report",
    tags=["evidence"],
)
def grade_bundle_report(
    bundle: EvidenceBundleRequest,
    format: str = Query(default="json"),
):
    """Generate a quality report for an evidence bundle. Read-only — no DB writes."""
    if format not in ("json", "markdown"):
        raise HTTPException(
            status_code=400,
            detail="format must be one of: 'json', 'markdown'.",
        )
    content = generate_bundle_quality_report(bundle.model_dump(), format=format)
    if format == "markdown":
        return PlainTextResponse(content=content, media_type="text/markdown")
    return BundleGradeReportResponse(
        format="json",
        content=content,
        generated_at=datetime.now(timezone.utc),
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
