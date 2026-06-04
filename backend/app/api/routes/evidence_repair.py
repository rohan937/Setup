"""M75 Evidence Repair + Strategy Management endpoints.

GET    /api/strategies/{strategy_id}/repair-options          — linkable evidence
PATCH  /api/strategies/{strategy_id}/runs/{run_id}/links      — link run evidence
PATCH  /api/strategies/{strategy_id}                          — update strategy
DELETE /api/strategies/{strategy_id}                          — archive strategy (soft)

Report / audit / alert / governance "create defaults" actions reuse existing
endpoints (reports, backtests, alerts, regression, config-policies, evidence-sla)
— no duplicate routes are added here.

Deterministic — no AI, no live market data, no external calls, no trading.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.constants import EventType, Severity
from app.core.rbac import require_workspace_write_access
from app.db.session import get_db
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.strategy import Strategy
from app.schemas.evidence_repair import (
    RepairOptionsResponse,
    RunLinkSummary,
    RunLinkUpdateRequest,
    StrategyManagementSummary,
    StrategyUpdateRequest,
)
from app.services.evidence_repair import (
    RepairNotFound,
    RepairValidation,
    archive_strategy,
    get_repair_options,
    link_run_evidence,
    update_strategy,
)

router = APIRouter(tags=["evidence-repair"])


def _strategy_or_404(strategy_id: uuid.UUID, db: Session) -> Strategy:
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


# ---------------------------------------------------------------------------
# GET repair options
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/repair-options",
    response_model=RepairOptionsResponse,
)
def repair_options(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> RepairOptionsResponse:
    """Return evidence objects that can be linked to repair missing run links."""
    try:
        payload = get_repair_options(strategy_id, db)
    except RepairNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return RepairOptionsResponse(**payload)


# ---------------------------------------------------------------------------
# PATCH run links
# ---------------------------------------------------------------------------

@router.patch(
    "/strategies/{strategy_id}/runs/{run_id}/links",
    response_model=RunLinkSummary,
)
def patch_run_links(
    strategy_id: uuid.UUID,
    run_id: uuid.UUID,
    body: RunLinkUpdateRequest,
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_write_access),
) -> RunLinkSummary:
    """Link existing evidence to a run (partial update). RBAC: write access."""
    try:
        summary = link_run_evidence(
            strategy_id,
            run_id,
            dataset_snapshot_id=body.dataset_snapshot_id,
            signal_snapshot_id=body.signal_snapshot_id,
            universe_snapshot_id=body.universe_snapshot_id,
            strategy_version_id=body.strategy_version_id,
            db=db,
        )
    except RepairNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RepairValidation as e:
        raise HTTPException(status_code=400, detail=str(e))

    strategy = _strategy_or_404(strategy_id, db)

    # Timeline event — run_evidence_linked.
    event = AuditTimelineEvent(
        organization_id=strategy.project.organization_id,
        project_id=strategy.project_id,
        strategy_id=strategy_id,
        event_type=EventType.run_evidence_linked,
        title=f"Evidence linked: {summary['run_name']}",
        description=(
            f"Linked {', '.join(summary['linked_fields'])} to run "
            f"'{summary['run_name']}' for strategy '{strategy.name}'."
        ),
        source_type="strategy_run",
        source_id=str(run_id),
        severity=Severity.info,
        metadata_json={
            "linked_fields": summary["linked_fields"],
            "dataset_snapshot_id": summary["dataset_snapshot_id"],
            "signal_snapshot_id": summary["signal_snapshot_id"],
            "universe_snapshot_id": summary["universe_snapshot_id"],
            "strategy_version_id": summary["strategy_version_id"],
        },
    )
    db.add(event)
    db.commit()

    # Best-effort reliability snapshot refresh — never blocks the repair.
    try:
        from app.services.reliability_snapshots import (
            refresh_strategy_reliability_snapshot,
        )

        refresh_strategy_reliability_snapshot(db, str(strategy_id), force=True)
        db.commit()
    except Exception:
        db.rollback()

    return RunLinkSummary(**summary)


# ---------------------------------------------------------------------------
# PATCH strategy (update)
# ---------------------------------------------------------------------------

@router.patch(
    "/strategies/{strategy_id}",
    response_model=StrategyManagementSummary,
)
def patch_strategy(
    strategy_id: uuid.UUID,
    body: StrategyUpdateRequest,
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_write_access),
) -> StrategyManagementSummary:
    """Update strategy name/description/status/asset_class. RBAC: write access."""
    try:
        summary = update_strategy(
            strategy_id,
            name=body.name,
            description=body.description,
            status=body.status,
            asset_class=body.asset_class,
            db=db,
        )
    except RepairNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RepairValidation as e:
        raise HTTPException(status_code=400, detail=str(e))

    strategy = _strategy_or_404(strategy_id, db)
    event = AuditTimelineEvent(
        organization_id=strategy.project.organization_id,
        project_id=strategy.project_id,
        strategy_id=strategy_id,
        event_type=EventType.strategy_updated,
        title=f"Strategy updated: {strategy.name}",
        description=summary["message"],
        source_type="strategy",
        source_id=str(strategy_id),
        severity=Severity.info,
        metadata_json={"status": summary["status"], "asset_class": summary["asset_class"]},
    )
    db.add(event)
    db.commit()

    return StrategyManagementSummary(**summary)


# ---------------------------------------------------------------------------
# DELETE strategy (archive — soft delete)
# ---------------------------------------------------------------------------

@router.delete(
    "/strategies/{strategy_id}",
    response_model=StrategyManagementSummary,
)
def delete_strategy(
    strategy_id: uuid.UUID,
    confirm: bool = Query(False, description="Must be true to archive."),
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_write_access),
) -> StrategyManagementSummary:
    """Archive (soft delete) a strategy. RBAC: write access.

    Hard delete is intentionally not offered: a strategy fans out into many
    cascade relationships (runs, versions, snapshots, audits, reports, alerts,
    timeline events). Archiving preserves the evidence trail.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Archiving requires confirm=true.",
        )
    try:
        summary = archive_strategy(strategy_id, db)
    except RepairNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))

    strategy = _strategy_or_404(strategy_id, db)
    event = AuditTimelineEvent(
        organization_id=strategy.project.organization_id,
        project_id=strategy.project_id,
        strategy_id=strategy_id,
        event_type=EventType.strategy_archived,
        title=f"Strategy archived: {strategy.name}",
        description=summary["message"],
        source_type="strategy",
        source_id=str(strategy_id),
        severity=Severity.info,
        metadata_json={"status": summary["status"]},
    )
    db.add(event)
    db.commit()

    return StrategyManagementSummary(**summary)
