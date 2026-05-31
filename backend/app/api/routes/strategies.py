"""Strategy endpoints:
  POST /api/strategies
  GET  /api/strategies
  GET  /api/strategies/{strategy_id}
  POST /api/strategies/{strategy_id}/runs
  GET  /api/strategies/{strategy_id}/runs/compare  ← M5
  GET  /api/strategies/{strategy_id}/runs

  M15 version + config-snapshot endpoints:
  POST /api/strategies/{strategy_id}/versions
  GET  /api/strategies/{strategy_id}/versions
  POST /api/strategies/{strategy_id}/config-snapshots
  GET  /api/strategies/{strategy_id}/config-snapshots
  GET  /api/strategies/{strategy_id}/config-snapshots/compare
  GET  /api/config-snapshots/{snapshot_id}
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
from app.models.data_quality_issue import DataQualityIssue
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.project import Project
from app.models.strategy import Strategy
from app.models.strategy_config_snapshot import StrategyConfigSnapshot
from app.models.strategy_run import StrategyRun
from app.models.strategy_version import StrategyVersion
from app.schemas.comparison import RunComparisonResponse
from app.schemas.strategy import (
    ConfigComparisonResponse,
    ConfigComparisonSectionOut,
    ConfigKeyChangeOut,
    DataEvidenceSummary,
    StrategyConfigSnapshotCreate,
    StrategyConfigSnapshotDetail,
    StrategyConfigSnapshotRead,
    StrategyCreate,
    StrategyDetailOut,
    StrategyListItemOut,
    StrategyRunCreate,
    StrategyRunOut,
    StrategyVersionCreate,
    StrategyVersionOut,
)
from app.schemas.timeline import TimelineEventOut, TimelineListResponse
from app.services.config_snapshots import (
    compare_config_snapshots,
    compute_config_hash,
    count_assumptions,
    count_params,
)
from app.services.run_comparison import compare_runs

router = APIRouter(tags=["strategies"])

# ---------------------------------------------------------------------------
# Severity ordering for worst-severity computation
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]


def _worst_severity(severities: list[str]) -> str | None:
    """Return the most severe level from a list, or None if empty."""
    for sev in _SEVERITY_ORDER:
        if sev in severities:
            return sev
    return None


# ---------------------------------------------------------------------------
# Snapshot stats helper
# ---------------------------------------------------------------------------

def _compute_snapshot_stats(rows: list[dict] | None) -> dict:
    """Compute lightweight stats from stored rows_json.

    Returns column_count, symbol_count, min_timestamp, max_timestamp.
    Safe to call with None or empty list.
    """
    if not rows:
        return {
            "column_count": 0,
            "symbol_count": 0,
            "min_timestamp": None,
            "max_timestamp": None,
        }

    # Union of all keys across rows.
    all_keys: set[str] = set()
    for row in rows:
        all_keys.update(row.keys())
    column_count = len(all_keys)

    # Distinct non-null symbols.
    symbols = {row.get("symbol") for row in rows if row.get("symbol") is not None}
    symbol_count = len(symbols)

    # Min/max timestamp strings (sort lexicographically — ISO dates sort correctly).
    ts_list = [str(row["timestamp"]) for row in rows if row.get("timestamp") is not None]
    if ts_list:
        ts_list_sorted = sorted(ts_list)
        min_timestamp = ts_list_sorted[0]
        max_timestamp = ts_list_sorted[-1]
    else:
        min_timestamp = None
        max_timestamp = None

    return {
        "column_count": column_count,
        "symbol_count": symbol_count,
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
    }


# ---------------------------------------------------------------------------
# Evidence summary builder
# ---------------------------------------------------------------------------

def _build_evidence_summary(
    snap: DatasetSnapshot,
) -> DataEvidenceSummary:
    """Build DataEvidenceSummary from a loaded snapshot.

    Requires snap.dataset and snap.issues to be loaded (via selectinload).
    """
    stats = _compute_snapshot_stats(snap.rows_json)
    issue_severities = [iss.severity for iss in (snap.issues or [])]
    return DataEvidenceSummary(
        id=snap.id,
        dataset_id=snap.dataset_id,
        dataset_name=snap.dataset.name if snap.dataset else "—",
        snapshot_label=snap.version_label,
        health_score=snap.health_score,
        row_count=snap.row_count,
        column_count=stats["column_count"],
        symbol_count=stats["symbol_count"],
        min_timestamp=stats["min_timestamp"],
        max_timestamp=stats["max_timestamp"],
        issue_count=len(issue_severities),
        worst_severity=_worst_severity(issue_severities),
    )


# ---------------------------------------------------------------------------
# Run → StrategyRunOut builder
# ---------------------------------------------------------------------------

def _build_run_out(run: StrategyRun) -> StrategyRunOut:
    """Build StrategyRunOut from a run that may have .snapshot eagerly loaded.

    If run.snapshot is None (no link or not loaded), dataset_snapshot is None.
    """
    evidence: DataEvidenceSummary | None = None
    if run.snapshot is not None:
        evidence = _build_evidence_summary(run.snapshot)

    return StrategyRunOut(
        id=run.id,
        strategy_id=run.strategy_id,
        strategy_version_id=run.strategy_version_id,
        dataset_snapshot_id=run.dataset_snapshot_id,
        run_name=run.run_name,
        run_type=run.run_type,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        params_json=run.params_json,
        assumptions_json=run.assumptions_json,
        metrics_json=run.metrics_json,
        universe_name=run.universe_name,
        dataset_version=run.dataset_version,
        notes=run.notes,
        created_at=run.created_at,
        updated_at=run.updated_at,
        dataset_snapshot=evidence,
    )


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
        description=(
            f"Strategy '{strategy.name}' registered in project '{project.name}'. "
            f"Asset class: {strategy.asset_class}. Status: {strategy.status}."
        ),
        source_type="strategy",
        source_id=str(strategy.id),
        severity=Severity.info,
        metadata_json={
            "strategy_name": strategy.name,
            "asset_class": strategy.asset_class,
            "status": strategy.status,
            "project_name": project.name,
        },
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
            selectinload(Strategy.runs)
            .selectinload(StrategyRun.snapshot)
            .selectinload(DatasetSnapshot.dataset),
            selectinload(Strategy.runs)
            .selectinload(StrategyRun.snapshot)
            .selectinload(DatasetSnapshot.issues),
            selectinload(Strategy.config_snapshots),
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

    sorted_runs = sorted(strategy.runs, key=lambda x: x.created_at, reverse=True)

    # Compute per-version config_snapshot_count from the eagerly loaded snapshots.
    version_snapshot_counts: dict[uuid.UUID, int] = {}
    for cs in (strategy.config_snapshots or []):
        if cs.strategy_version_id is not None:
            version_snapshot_counts[cs.strategy_version_id] = (
                version_snapshot_counts.get(cs.strategy_version_id, 0) + 1
            )

    # Build version list with counts, newest-first.
    sorted_versions = sorted(strategy.versions, key=lambda v: v.created_at, reverse=True)
    version_outs: list[StrategyVersionOut] = []
    for v in sorted_versions:
        vout = StrategyVersionOut.model_validate(v)
        vout.config_snapshot_count = version_snapshot_counts.get(v.id, 0)
        version_outs.append(vout)

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
        versions=version_outs,
        runs=[_build_run_out(r) for r in sorted_runs],
        config_snapshots=[
            StrategyConfigSnapshotRead.model_validate(cs)
            for cs in strategy.config_snapshots
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
) -> StrategyRunOut:
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
    strategy = (
        db.query(Strategy)
        .options(selectinload(Strategy.project))
        .filter(Strategy.id == strategy_id)
        .first()
    )
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

    # M7: Validate dataset_snapshot_id when provided.
    snap: DatasetSnapshot | None = None
    if body.dataset_snapshot_id is not None:
        snap = (
            db.query(DatasetSnapshot)
            .options(
                selectinload(DatasetSnapshot.dataset),
                selectinload(DatasetSnapshot.issues),
            )
            .filter(DatasetSnapshot.id == body.dataset_snapshot_id)
            .first()
        )
        if snap is None:
            raise HTTPException(
                status_code=404, detail="Dataset snapshot not found"
            )
        # Snapshot's dataset must belong to the same project as the strategy.
        if snap.dataset is None or snap.dataset.project_id != strategy.project_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Dataset snapshot does not belong to the same project as this strategy"
                ),
            )

    # Auto-set completed_at when status is completed and no value was supplied
    completed_at = body.completed_at
    if body.status == RunStatus.completed and completed_at is None:
        completed_at = datetime.now(timezone.utc)

    run = StrategyRun(
        strategy_id=strategy_id,
        strategy_version_id=body.strategy_version_id,
        dataset_snapshot_id=body.dataset_snapshot_id,
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

    event = AuditTimelineEvent(
        organization_id=strategy.project.organization_id,
        project_id=strategy.project_id,
        strategy_id=strategy_id,
        event_type=EventType.strategy_run_logged,
        title=f"Run logged: {run.run_name}",
        description=(
            f"{run.run_type.capitalize()} run '{run.run_name}' logged for strategy "
            f"'{strategy.name}'. Status: {run.status}."
            + (f" Universe: {run.universe_name}." if run.universe_name else "")
        ),
        source_type="strategy_run",
        source_id=str(run.id),
        severity=Severity.info,
        metadata_json={
            "run_type": run.run_type,
            "status": run.status,
            "universe_name": run.universe_name,
            "dataset_snapshot_id": str(body.dataset_snapshot_id) if body.dataset_snapshot_id else None,
            "strategy_name": strategy.name,
        },
    )
    db.add(event)
    db.commit()
    db.refresh(run)

    # Attach the already-loaded snapshot object so _build_run_out can build evidence.
    run.snapshot = snap  # type: ignore[assignment]

    return _build_run_out(run)


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
# GET /api/strategies/{strategy_id}/timeline  (M10)
# NOTE: registered BEFORE the bare /runs route so the literal "/timeline"
# segment is matched before the run-list handler.
# ---------------------------------------------------------------------------

@router.get("/strategies/{strategy_id}/timeline", response_model=TimelineListResponse)
def get_strategy_timeline(
    strategy_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> TimelineListResponse:
    """Return audit timeline events for a single strategy, newest-first.

    Only events whose ``strategy_id`` matches are returned.  Use the global
    ``GET /api/timeline?strategy_id=...`` endpoint if you also need events
    from sub-resources that may not carry a strategy_id (e.g. dataset snapshots).
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    q = db.query(AuditTimelineEvent).filter(
        AuditTimelineEvent.strategy_id == strategy_id
    )
    total: int = q.count()
    items = (
        q.order_by(AuditTimelineEvent.event_time.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return TimelineListResponse(
        items=[TimelineEventOut.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# GET /api/strategies/{strategy_id}/runs
# ---------------------------------------------------------------------------

@router.get("/strategies/{strategy_id}/runs", response_model=list[StrategyRunOut])
def list_strategy_runs(
    strategy_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[StrategyRunOut]:
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    runs = (
        db.query(StrategyRun)
        .options(
            selectinload(StrategyRun.snapshot).selectinload(DatasetSnapshot.dataset),
            selectinload(StrategyRun.snapshot).selectinload(DatasetSnapshot.issues),
        )
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(StrategyRun.created_at.desc())
        .all()
    )

    return [_build_run_out(r) for r in runs]


# ---------------------------------------------------------------------------
# M15: POST /api/strategies/{strategy_id}/versions
# ---------------------------------------------------------------------------

@router.post(
    "/strategies/{strategy_id}/versions",
    response_model=StrategyVersionOut,
    status_code=201,
)
def create_strategy_version(
    strategy_id: uuid.UUID,
    body: StrategyVersionCreate,
    db: Session = Depends(get_db),
) -> StrategyVersionOut:
    """Create a new strategy version.

    Validates that the strategy exists and that version_label is unique within
    the strategy.  Emits an audit timeline event on success.
    """
    strategy = (
        db.query(Strategy)
        .options(selectinload(Strategy.project))
        .filter(Strategy.id == strategy_id)
        .first()
    )
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # Prevent duplicate version_label within the same strategy.
    existing = (
        db.query(StrategyVersion)
        .filter(
            StrategyVersion.strategy_id == strategy_id,
            StrategyVersion.version_label == body.version_label,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Version label '{body.version_label}' already exists for this strategy",
        )

    version = StrategyVersion(
        strategy_id=strategy_id,
        version_label=body.version_label,
        git_commit=body.git_commit,
        branch_name=body.branch_name,
        code_path=body.code_path,
        signal_name=body.signal_name,
        signal_description=body.signal_description,
    )
    db.add(version)
    db.flush()

    event = AuditTimelineEvent(
        organization_id=strategy.project.organization_id,
        project_id=strategy.project_id,
        strategy_id=strategy_id,
        event_type=EventType.strategy_version_created,
        title=f"Version created: {version.version_label}",
        description=(
            f"Strategy version '{version.version_label}' created for strategy '{strategy.name}'."
            + (f" Branch: {version.branch_name}." if version.branch_name else "")
            + (f" Signal: {version.signal_name}." if version.signal_name else "")
        ),
        source_type="strategy_version",
        source_id=str(version.id),
        severity=Severity.info,
        metadata_json={
            "version_label": version.version_label,
            "git_commit": version.git_commit,
            "branch_name": version.branch_name,
            "signal_name": version.signal_name,
            "strategy_name": strategy.name,
        },
    )
    db.add(event)
    db.commit()
    db.refresh(version)

    vout = StrategyVersionOut.model_validate(version)
    vout.config_snapshot_count = 0
    return vout


# ---------------------------------------------------------------------------
# M15: GET /api/strategies/{strategy_id}/versions
# NOTE: registered BEFORE the config-snapshots routes so literal "versions"
# is matched before any path-param sub-routes below it.
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/versions",
    response_model=list[StrategyVersionOut],
)
def list_strategy_versions(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[StrategyVersionOut]:
    """List all versions for a strategy, newest-first, with config_snapshot_count."""
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    versions = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.created_at.desc())
        .all()
    )

    if not versions:
        return []

    version_ids = [v.id for v in versions]
    counts: dict = dict(
        db.query(
            StrategyConfigSnapshot.strategy_version_id,
            func.count(StrategyConfigSnapshot.id),
        )
        .filter(StrategyConfigSnapshot.strategy_version_id.in_(version_ids))
        .group_by(StrategyConfigSnapshot.strategy_version_id)
        .all()
    )

    results: list[StrategyVersionOut] = []
    for v in versions:
        vout = StrategyVersionOut.model_validate(v)
        vout.config_snapshot_count = counts.get(v.id, 0)
        results.append(vout)
    return results


# ---------------------------------------------------------------------------
# M15: GET /api/strategies/{strategy_id}/config-snapshots/compare
# NOTE: registered BEFORE the list route (/config-snapshots) so the literal
# "/compare" segment is matched before any query-only /config-snapshots handler.
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/config-snapshots/compare",
    response_model=ConfigComparisonResponse,
)
def compare_strategy_config_snapshots(
    strategy_id: uuid.UUID,
    snapshot_a_id: uuid.UUID = Query(..., description="ID of the baseline config snapshot (A)"),
    snapshot_b_id: uuid.UUID = Query(..., description="ID of the comparison config snapshot (B)"),
    db: Session = Depends(get_db),
) -> ConfigComparisonResponse:
    """Deterministically compare two config snapshots belonging to this strategy.

    Read-only — no audit event is emitted.
    Returns structured diffs for top-level keys, params, and assumptions,
    plus highlighted change bullets.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    snap_a = (
        db.query(StrategyConfigSnapshot)
        .filter(
            StrategyConfigSnapshot.id == snapshot_a_id,
            StrategyConfigSnapshot.strategy_id == strategy_id,
        )
        .first()
    )
    if snap_a is None:
        raise HTTPException(status_code=404, detail="Config snapshot A not found")

    snap_b = (
        db.query(StrategyConfigSnapshot)
        .filter(
            StrategyConfigSnapshot.id == snapshot_b_id,
            StrategyConfigSnapshot.strategy_id == strategy_id,
        )
        .first()
    )
    if snap_b is None:
        raise HTTPException(status_code=404, detail="Config snapshot B not found")

    result = compare_config_snapshots(
        snap_a_id=str(snap_a.id),
        snap_b_id=str(snap_b.id),
        snap_a_label=snap_a.label,
        snap_b_label=snap_b.label,
        config_a=snap_a.config_json,
        config_b=snap_b.config_json,
    )

    def _section_out(section):  # type: ignore[no-untyped-def]
        return ConfigComparisonSectionOut(
            added=[ConfigKeyChangeOut(key=c.key, old_value=c.old_value, new_value=c.new_value, change_type=c.change_type) for c in section.added],
            removed=[ConfigKeyChangeOut(key=c.key, old_value=c.old_value, new_value=c.new_value, change_type=c.change_type) for c in section.removed],
            changed=[ConfigKeyChangeOut(key=c.key, old_value=c.old_value, new_value=c.new_value, change_type=c.change_type) for c in section.changed],
            total_changes=section.total_changes,
        )

    return ConfigComparisonResponse(
        snapshot_a_id=snap_a.id,
        snapshot_b_id=snap_b.id,
        snapshot_a_label=result.snapshot_a_label,
        snapshot_b_label=result.snapshot_b_label,
        is_same_config=result.is_same_config,
        top_level=_section_out(result.top_level),
        params=_section_out(result.params),
        assumptions=_section_out(result.assumptions),
        highlighted_changes=result.highlighted_changes,
        total_changes=result.total_changes,
    )


# ---------------------------------------------------------------------------
# M15: POST /api/strategies/{strategy_id}/config-snapshots
# ---------------------------------------------------------------------------

@router.post(
    "/strategies/{strategy_id}/config-snapshots",
    response_model=StrategyConfigSnapshotRead,
    status_code=201,
)
def create_config_snapshot(
    strategy_id: uuid.UUID,
    body: StrategyConfigSnapshotCreate,
    db: Session = Depends(get_db),
) -> StrategyConfigSnapshotRead:
    """Create a config snapshot for a strategy.

    config_json must be a JSON object (dict); arrays and scalars are rejected.
    If strategy_version_id is provided it must belong to this strategy.
    Computes deterministic config_hash, param_count, and assumption_count.
    Emits an audit timeline event on success.
    """
    strategy = (
        db.query(Strategy)
        .options(selectinload(Strategy.project))
        .filter(Strategy.id == strategy_id)
        .first()
    )
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    if not isinstance(body.config_json, dict):
        raise HTTPException(
            status_code=422,
            detail="config_json must be a JSON object (dict), not an array or scalar",
        )

    # Validate strategy_version_id belongs to this strategy when provided.
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

    config_hash = compute_config_hash(body.config_json)
    param_count = count_params(body.config_json)
    assumption_count = count_assumptions(body.config_json)

    snapshot = StrategyConfigSnapshot(
        strategy_id=strategy_id,
        strategy_version_id=body.strategy_version_id,
        label=body.label,
        source_type=body.source_type,
        source_filename=body.source_filename,
        config_json=body.config_json,
        config_hash=config_hash,
        param_count=param_count,
        assumption_count=assumption_count,
    )
    db.add(snapshot)
    db.flush()

    event = AuditTimelineEvent(
        organization_id=strategy.project.organization_id,
        project_id=strategy.project_id,
        strategy_id=strategy_id,
        event_type=EventType.strategy_config_snapshot_logged,
        title=f"Config snapshot logged: {snapshot.label}",
        description=(
            f"Config snapshot '{snapshot.label}' logged for strategy '{strategy.name}'. "
            f"Source: {snapshot.source_type}. "
            f"Params: {param_count}. Assumptions: {assumption_count}."
        ),
        source_type="strategy_config_snapshot",
        source_id=str(snapshot.id),
        severity=Severity.info,
        metadata_json={
            "snapshot_label": snapshot.label,
            "source_type": snapshot.source_type,
            "config_hash": config_hash,
            "param_count": param_count,
            "assumption_count": assumption_count,
            "strategy_name": strategy.name,
        },
    )
    db.add(event)
    db.commit()
    db.refresh(snapshot)

    return StrategyConfigSnapshotRead.model_validate(snapshot)


# ---------------------------------------------------------------------------
# M15: GET /api/strategies/{strategy_id}/config-snapshots
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/config-snapshots",
    response_model=list[StrategyConfigSnapshotRead],
)
def list_config_snapshots(
    strategy_id: uuid.UUID,
    version_id: uuid.UUID | None = Query(default=None, description="Filter by strategy_version_id"),
    db: Session = Depends(get_db),
) -> list[StrategyConfigSnapshotRead]:
    """List config snapshots for a strategy, newest-first.

    Pass ``version_id`` to filter by a specific strategy version.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    q = db.query(StrategyConfigSnapshot).filter(
        StrategyConfigSnapshot.strategy_id == strategy_id
    )
    if version_id is not None:
        q = q.filter(StrategyConfigSnapshot.strategy_version_id == version_id)

    snapshots = q.order_by(StrategyConfigSnapshot.created_at.desc()).all()
    return [StrategyConfigSnapshotRead.model_validate(s) for s in snapshots]


# ---------------------------------------------------------------------------
# M15: GET /api/config-snapshots/{snapshot_id}
# ---------------------------------------------------------------------------

@router.get(
    "/config-snapshots/{snapshot_id}",
    response_model=StrategyConfigSnapshotDetail,
)
def get_config_snapshot(
    snapshot_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StrategyConfigSnapshotDetail:
    """Return full config snapshot detail including the config_json payload."""
    snapshot = (
        db.query(StrategyConfigSnapshot)
        .filter(StrategyConfigSnapshot.id == snapshot_id)
        .first()
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Config snapshot not found")

    return StrategyConfigSnapshotDetail.model_validate(snapshot)
