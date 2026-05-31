"""Strategy endpoints:
  POST /api/strategies
  GET  /api/strategies
  GET  /api/strategies/{strategy_id}
  POST /api/strategies/{strategy_id}/runs
  GET  /api/strategies/{strategy_id}/runs/compare  ← M5
  GET  /api/strategies/{strategy_id}/runs
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.core.constants import AssetClass, EventType, RunStatus, RunType, Severity, StrategyStatus
from app.core.utils import slugify
from app.db.session import get_db
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.project import Project
from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun
from app.models.strategy_version import StrategyVersion
from app.schemas.comparison import RunComparisonResponse
from app.schemas.strategy import (
    StrategyCreate,
    StrategyDetailOut,
    StrategyListItemOut,
    StrategyRunCreate,
    StrategyRunOut,
    StrategyVersionOut,
)
from app.services.run_comparison import compare_runs

router = APIRouter(tags=["strategies"])


# ---------------------------------------------------------------------------
# POST /api/strategies
# ---------------------------------------------------------------------------

@router.post("/strategies", response_model=StrategyListItemOut, status_code=201)
def create_strategy(body: StrategyCreate, db: Session = Depends(get_db)) -> StrategyListItemOut:
    try:
        AssetClass(body.asset_class)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid asset_class '{body.asset_class}'")

    try:
        StrategyStatus(body.status)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid status '{body.status}'")

    project = db.query(Project).filter(Project.id == body.project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    slug = body.slug or slugify(body.name)
    if not slug:
        slug = str(uuid.uuid4())[:8]

    existing = (
        db.query(Strategy)
        .filter_by(project_id=project.id, slug=slug)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"A strategy with slug '{slug}' already exists in this project",
        )

    strategy = Strategy(
        project_id=project.id,
        name=body.name,
        slug=slug,
        description=body.description,
        asset_class=body.asset_class,
        status=body.status,
    )
    db.add(strategy)
    db.flush()

    event = AuditTimelineEvent(
        organization_id=project.organization_id,
        project_id=project.id,
        strategy_id=strategy.id,
        event_type=EventType.strategy_created,
        title=f"Strategy created: {strategy.name}",
        source_type="strategy",
        source_id=str(strategy.id),
        severity=Severity.info,
    )
    db.add(event)
    db.commit()
    db.refresh(strategy)

    return StrategyListItemOut(
        id=strategy.id,
        project_id=strategy.project_id,
        project_name=project.name,
        name=strategy.name,
        slug=strategy.slug,
        description=strategy.description,
        asset_class=strategy.asset_class,
        status=strategy.status,
        run_count=0,
        latest_run_at=None,
        created_at=strategy.created_at,
        updated_at=strategy.updated_at,
    )


# ---------------------------------------------------------------------------
# GET /api/strategies
# ---------------------------------------------------------------------------

@router.get("/strategies", response_model=list[StrategyListItemOut])
def list_strategies(db: Session = Depends(get_db)) -> list[StrategyListItemOut]:
    strategies = (
        db.query(Strategy)
        .options(selectinload(Strategy.project))
        .order_by(Strategy.created_at)
        .all()
    )

    if not strategies:
        return []

    strategy_ids = [s.id for s in strategies]

    run_counts: dict = dict(
        db.query(StrategyRun.strategy_id, func.count(StrategyRun.id))
        .filter(StrategyRun.strategy_id.in_(strategy_ids))
        .group_by(StrategyRun.strategy_id)
        .all()
    )

    latest_runs: dict = dict(
        db.query(StrategyRun.strategy_id, func.max(StrategyRun.created_at))
        .filter(StrategyRun.strategy_id.in_(strategy_ids))
        .group_by(StrategyRun.strategy_id)
        .all()
    )

    return [
        StrategyListItemOut(
            id=s.id,
            project_id=s.project_id,
            project_name=s.project.name,
            name=s.name,
            slug=s.slug,
            description=s.description,
            asset_class=s.asset_class,
            status=s.status,
            run_count=run_counts.get(s.id, 0),
            latest_run_at=latest_runs.get(s.id),
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in strategies
    ]


# ---------------------------------------------------------------------------
# GET /api/strategies/{strategy_id}
# ---------------------------------------------------------------------------

@router.get("/strategies/{strategy_id}", response_model=StrategyDetailOut)
def get_strategy(
    strategy_id: uuid.UUID, db: Session = Depends(get_db)
) -> StrategyDetailOut:
    strategy = (
        db.query(Strategy)
        .options(
            selectinload(Strategy.project),
            selectinload(Strategy.versions),
            selectinload(Strategy.runs),
        )
        .filter(Strategy.id == strategy_id)
        .first()
    )
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    run_count: int = (
        db.query(func.count(StrategyRun.id))
        .filter(StrategyRun.strategy_id == strategy_id)
        .scalar()
    ) or 0

    latest_run_at = (
        db.query(func.max(StrategyRun.created_at))
        .filter(StrategyRun.strategy_id == strategy_id)
        .scalar()
    )

    return StrategyDetailOut(
        id=strategy.id,
        project_id=strategy.project_id,
        project_name=strategy.project.name,
        name=strategy.name,
        slug=strategy.slug,
        description=strategy.description,
        asset_class=strategy.asset_class,
        status=strategy.status,
        run_count=run_count,
        latest_run_at=latest_run_at,
        created_at=strategy.created_at,
        updated_at=strategy.updated_at,
        versions=[StrategyVersionOut.model_validate(v) for v in strategy.versions],
        runs=[
            StrategyRunOut.model_validate(r)
            for r in sorted(strategy.runs, key=lambda x: x.created_at, reverse=True)
        ],
    )


# ---------------------------------------------------------------------------
# POST /api/strategies/{strategy_id}/runs
# ---------------------------------------------------------------------------

@router.post("/strategies/{strategy_id}/runs", response_model=StrategyRunOut, status_code=201)
def create_strategy_run(
    strategy_id: uuid.UUID,
    body: StrategyRunCreate,
    db: Session = Depends(get_db),
) -> StrategyRun:
    # Validate run_type
    try:
        RunType(body.run_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid run_type '{body.run_type}'")

    # Validate status
    try:
        RunStatus(body.status)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid status '{body.status}'")

    # Check strategy exists
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # Validate strategy_version_id belongs to this strategy when provided
    if body.strategy_version_id is not None:
        version = (
            db.query(StrategyVersion)
            .filter(
                StrategyVersion.id == body.strategy_version_id,
                StrategyVersion.strategy_id == strategy_id,
            )
            .first()
        )
        if version is None:
            raise HTTPException(status_code=404, detail="Strategy version not found")

    # Auto-set completed_at when status is completed and no value was supplied
    completed_at = body.completed_at
    if body.status == RunStatus.completed and completed_at is None:
        completed_at = datetime.now(timezone.utc)

    run = StrategyRun(
        strategy_id=strategy_id,
        strategy_version_id=body.strategy_version_id,
        run_name=body.run_name,
        run_type=body.run_type,
        status=body.status,
        started_at=body.started_at,
        completed_at=completed_at,
        params_json=body.params_json,
        assumptions_json=body.assumptions_json,
        metrics_json=body.metrics_json,
        universe_name=body.universe_name,
        dataset_version=body.dataset_version,
        notes=body.notes,
    )
    db.add(run)
    db.flush()

    # Load project to get organization_id for the audit event
    project = db.query(Project).filter(Project.id == strategy.project_id).first()

    event = AuditTimelineEvent(
        organization_id=project.organization_id,
        project_id=strategy.project_id,
        strategy_id=strategy_id,
        event_type=EventType.strategy_run_logged,
        title=f"Run logged: {run.run_name}",
        source_type="strategy_run",
        source_id=str(run.id),
        severity=Severity.info,
        metadata_json={
            "run_type": run.run_type,
            "status": run.status,
            "universe_name": run.universe_name,
        },
    )
    db.add(event)
    db.commit()
    db.refresh(run)

    return run


# ---------------------------------------------------------------------------
# GET /api/strategies/{strategy_id}/runs/compare  (M5)
# NOTE: registered BEFORE the bare /runs route so Starlette matches
# the literal "/compare" segment ahead of the query-only /runs handler.
# ---------------------------------------------------------------------------

@router.get("/strategies/{strategy_id}/runs/compare", response_model=RunComparisonResponse)
def compare_strategy_runs(
    strategy_id: uuid.UUID,
    run_a_id: uuid.UUID = Query(..., description="ID of the baseline run (Run A)"),
    run_b_id: uuid.UUID = Query(..., description="ID of the comparison run (Run B)"),
    db: Session = Depends(get_db),
) -> RunComparisonResponse:
    """Deterministically compare two runs from the same strategy.

    Read-only analysis — no AuditTimelineEvent is created.
    Returns structured diffs for params, assumptions, metrics, and metadata,
    plus highlighted changes and a hedged plain-language explanation.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    run_a = db.query(StrategyRun).filter(StrategyRun.id == run_a_id).first()
    if run_a is None:
        raise HTTPException(status_code=404, detail="Run A not found")

    run_b = db.query(StrategyRun).filter(StrategyRun.id == run_b_id).first()
    if run_b is None:
        raise HTTPException(status_code=404, detail="Run B not found")

    if run_a.strategy_id != strategy_id:
        raise HTTPException(
            status_code=400, detail="Run A does not belong to this strategy"
        )
    if run_b.strategy_id != strategy_id:
        raise HTTPException(
            status_code=400, detail="Run B does not belong to this strategy"
        )

    return compare_runs(run_a, run_b)


# ---------------------------------------------------------------------------
# GET /api/strategies/{strategy_id}/runs
# ---------------------------------------------------------------------------

@router.get("/strategies/{strategy_id}/runs", response_model=list[StrategyRunOut])
def list_strategy_runs(
    strategy_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[StrategyRun]:
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(StrategyRun.created_at.desc())
        .all()
    )
