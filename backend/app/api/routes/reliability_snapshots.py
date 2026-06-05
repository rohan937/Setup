"""M65A Strategy Reliability Snapshot Cache API routes.

Endpoints:
  POST /api/strategies/{strategy_id}/reliability-snapshot/refresh
  GET  /api/strategies/{strategy_id}/reliability-snapshot
  GET  /api/strategies/{strategy_id}/reliability-snapshots
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.rbac import require_workspace_write_access
from app.db.session import get_db
from app.models.strategy import Strategy
from app.schemas.reliability_snapshot import (
    StrategyReliabilitySnapshotListResponse,
    StrategyReliabilitySnapshotRead,
)
from typing import Any
from app.services.reliability_snapshots import (
    get_latest_strategy_reliability_snapshot,
    get_strategy_reliability_snapshot_history,
    is_snapshot_stale,
    refresh_strategy_reliability_snapshot,
)

router = APIRouter()


def _parse_strategy_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Strategy not found")


def _load_strategy(db: Session, strategy_id: str) -> Strategy:
    sid = _parse_strategy_uuid(strategy_id)
    strategy = db.query(Strategy).filter(Strategy.id == sid).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


def _enrich_snapshot(
    db: Session,
    snapshot,
) -> StrategyReliabilitySnapshotRead:
    """Convert ORM snapshot to schema, computing staleness inline."""
    stale, reasons = is_snapshot_stale(db, snapshot)
    data = StrategyReliabilitySnapshotRead.model_validate(snapshot)
    data.is_stale = stale
    data.stale_reasons = reasons
    return data


# ---------------------------------------------------------------------------
# IMPORTANT: literal path (/refresh) MUST be declared before any
# parameterised sibling — FastAPI matches routes in declaration order.
# ---------------------------------------------------------------------------

@router.post(
    "/strategies/{strategy_id}/reliability-snapshot/refresh",
    response_model=StrategyReliabilitySnapshotRead,
)
def refresh_snapshot(
    strategy_id: str,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_write_access),
) -> StrategyReliabilitySnapshotRead:
    """Refresh (or reuse) the reliability snapshot for a strategy.

    With ``force=true`` a new snapshot is always created.
    With ``force=false`` an existing snapshot is reused if the source data
    has not changed and the snapshot is not stale.
    """
    _load_strategy(db, strategy_id)

    try:
        snapshot = refresh_strategy_reliability_snapshot(db, strategy_id, force=force)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    db.commit()
    db.refresh(snapshot)
    return _enrich_snapshot(db, snapshot)


@router.get(
    "/strategies/{strategy_id}/reliability-snapshot",
    response_model=StrategyReliabilitySnapshotRead | None,
)
def get_latest_snapshot(
    strategy_id: str,
    db: Session = Depends(get_db),
) -> Any:
    """Return the latest reliability snapshot for a strategy.

    Returns ``null`` (200) when no snapshot exists yet — POST to
    ``/reliability-snapshot/refresh`` to create one.  Returns null rather
    than 404 so the frontend can distinguish "strategy not found" (404) from
    "no snapshot yet" (200 null) and avoid spurious console errors.
    """
    _load_strategy(db, strategy_id)

    snapshot = get_latest_strategy_reliability_snapshot(db, strategy_id)
    if snapshot is None:
        # 200 null — the frontend already handles this gracefully and checks
        # for null before rendering.  A 404 here causes unnecessary console
        # errors and CORS pre-flight failures on some browsers.
        return JSONResponse(content=None, status_code=200)
    return _enrich_snapshot(db, snapshot)


@router.get(
    "/strategies/{strategy_id}/reliability-snapshots",
    response_model=StrategyReliabilitySnapshotListResponse,
)
def list_snapshots(
    strategy_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> StrategyReliabilitySnapshotListResponse:
    """Return the snapshot history for a strategy, newest first."""
    _load_strategy(db, strategy_id)

    snapshots = get_strategy_reliability_snapshot_history(
        db, strategy_id, limit=limit, offset=offset
    )
    items = [_enrich_snapshot(db, s) for s in snapshots]
    return StrategyReliabilitySnapshotListResponse(items=items, total=len(items))
