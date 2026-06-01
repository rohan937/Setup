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

  M16 universe snapshot endpoints:
  POST /api/strategies/{strategy_id}/universe-snapshots
  GET  /api/strategies/{strategy_id}/universe-snapshots
  GET  /api/strategies/{strategy_id}/universe-snapshots/compare
  GET  /api/universe-snapshots/{snapshot_id}

  M17 signal snapshot endpoints:
  POST /api/strategies/{strategy_id}/signal-snapshots
  GET  /api/strategies/{strategy_id}/signal-snapshots
  GET  /api/strategies/{strategy_id}/signal-snapshots/compare
  GET  /api/signal-snapshots/{snapshot_id}
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.core.constants import AssetClass, EventType, ReliabilityScoreStatus, RunStatus, RunType, Severity, StrategyStatus
from app.core.utils import slugify
from app.db.session import get_db
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.data_quality_issue import DataQualityIssue
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.project import Project
from app.models.signal_snapshot import SignalSnapshot
from app.models.strategy import Strategy
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.models.strategy_config_snapshot import StrategyConfigSnapshot
from app.models.strategy_run import StrategyRun
from app.models.strategy_version import StrategyVersion
from app.models.universe_snapshot import UniverseSnapshot
from app.schemas.comparison import RunComparisonResponse
from app.schemas.strategy import (
    ConfigComparisonResponse,
    ConfigComparisonSectionOut,
    ConfigKeyChangeOut,
    DataEvidenceSummary,
    EvidenceCountDelta as _EvidenceCountDelta,
    ReliabilityComponentDelta as _ReliabilityComponentDelta,
    ReliabilityScoreComparisonResponse,
    ReliabilityScoreTrendResponse,
    SignalComparisonResponse,
    SignalRowChangeOut,
    SignalSnapshotCreate,
    SignalSnapshotDetail,
    SignalSnapshotRead,
    SignalSnapshotSummary,
    StrategyComparisonItem,
    StrategyComparisonRankingItem,
    StrategyComparisonRequest,
    StrategyComparisonResponse,
    StrategyConfigSnapshotCreate,
    StrategyConfigSnapshotDetail,
    StrategyConfigSnapshotRead,
    StrategyCreate,
    StrategyDetailOut,
    StrategyEvidenceCoverage,
    StrategyListItemOut,
    StrategyReliabilityScoreHistoryResponse,
    StrategyReliabilityScoreRead,
    StrategyRunCreate,
    StrategyRunOut,
    StrategyVersionCreate,
    StrategyVersionOut,
    UniverseComparisonResponse,
    UniverseSnapshotCreate,
    UniverseSnapshotDetail,
    UniverseSnapshotRead,
    UniverseSnapshotSummary,
)
from app.services.strategy_reliability import (
    compare_reliability_scores,
    compute_reliability_score,
)
from app.schemas.timeline import TimelineEventOut, TimelineListResponse
from app.services.config_snapshots import (
    compare_config_snapshots,
    compute_config_hash,
    count_assumptions,
    count_params,
)
from app.services.run_comparison import compare_runs
from app.services.universe_snapshots import (
    compare_universe_snapshots,
    compute_universe_hash,
    normalize_symbols,
)
from app.services.signal_snapshots import (
    compare_signal_snapshots,
    compute_signal_hash,
    normalize_signal_rows,
    summarize_signal_snapshot,
)

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

def _build_universe_summary(us: "UniverseSnapshot") -> UniverseSnapshotSummary:
    """Build a lightweight UniverseSnapshotSummary from a loaded universe snapshot."""
    return UniverseSnapshotSummary(
        id=us.id,
        label=us.label,
        symbol_count=us.symbol_count,
        universe_hash=us.universe_hash,
        strategy_version_id=us.strategy_version_id,
        created_at=us.created_at,
    )


def _build_signal_summary(ss: "SignalSnapshot") -> SignalSnapshotSummary:
    """Build a lightweight SignalSnapshotSummary from a loaded signal snapshot."""
    return SignalSnapshotSummary(
        id=ss.id,
        label=ss.label,
        signal_name=ss.signal_name,
        row_count=ss.row_count,
        symbol_count=ss.symbol_count,
        signal_value_count=ss.signal_value_count,
        missing_signal_count=ss.missing_signal_count,
        quality_score=ss.quality_score,
        mean_value=ss.mean_value,
        stddev_value=ss.stddev_value,
        created_at=ss.created_at,
    )


def _build_run_out(run: StrategyRun) -> StrategyRunOut:
    """Build StrategyRunOut from a run that may have .snapshot / .universe_snapshot / .signal_snapshot loaded.

    If run.snapshot is None (no link or not loaded), dataset_snapshot is None.
    If run.universe_snapshot is None, universe_snapshot is None.
    If run.signal_snapshot is None, signal_snapshot is None.
    """
    evidence: DataEvidenceSummary | None = None
    if run.snapshot is not None:
        evidence = _build_evidence_summary(run.snapshot)

    uni_evidence: UniverseSnapshotSummary | None = None
    if run.universe_snapshot is not None:
        uni_evidence = _build_universe_summary(run.universe_snapshot)

    sig_evidence: SignalSnapshotSummary | None = None
    if run.signal_snapshot is not None:
        sig_evidence = _build_signal_summary(run.signal_snapshot)

    return StrategyRunOut(
        id=run.id,
        strategy_id=run.strategy_id,
        strategy_version_id=run.strategy_version_id,
        dataset_snapshot_id=run.dataset_snapshot_id,
        universe_snapshot_id=run.universe_snapshot_id,
        signal_snapshot_id=run.signal_snapshot_id,
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
        universe_snapshot=uni_evidence,
        signal_snapshot=sig_evidence,
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

    # M18: load latest reliability score per strategy
    latest_score_map: dict = {}
    if strategy_ids:
        # Subquery: for each strategy_id, find max generated_at
        subq = (
            db.query(
                StrategyReliabilityScore.strategy_id,
                func.max(StrategyReliabilityScore.generated_at).label("max_gen"),
            )
            .filter(StrategyReliabilityScore.strategy_id.in_(strategy_ids))
            .group_by(StrategyReliabilityScore.strategy_id)
            .subquery()
        )
        latest_scores = (
            db.query(StrategyReliabilityScore)
            .join(
                subq,
                (StrategyReliabilityScore.strategy_id == subq.c.strategy_id)
                & (StrategyReliabilityScore.generated_at == subq.c.max_gen),
            )
            .all()
        )
        for score in latest_scores:
            latest_score_map[score.strategy_id] = score

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
            latest_reliability_score=(
                StrategyReliabilityScoreRead.model_validate(latest_score_map[s.id])
                if s.id in latest_score_map
                else None
            ),
        )
        for s in strategies
    ]


# ---------------------------------------------------------------------------
# POST /api/strategies/compare  (M20)
# Must be registered BEFORE GET /strategies/{strategy_id} so "compare" is
# not captured as a strategy_id path parameter on GET requests.
# ---------------------------------------------------------------------------

@router.post("/strategies/compare", response_model=StrategyComparisonResponse, status_code=200)
def compare_strategies_endpoint(
    payload: StrategyComparisonRequest,
    db: Session = Depends(get_db),
) -> StrategyComparisonResponse:
    """Compare 2–8 strategies side-by-side using existing logged evidence.

    Evidence-based comparison only — never investment advice.
    """
    from app.services.strategy_comparison import (
        compare_strategies as _compare,
        StrategyComparisonResult,
        StrategyComparisonItemData,
        StrategyEvidenceCoverageData,
    )

    if len(payload.strategy_ids) < 2:
        raise HTTPException(
            status_code=422, detail="At least 2 strategy IDs required for comparison."
        )
    if len(payload.strategy_ids) > 8:
        raise HTTPException(
            status_code=422, detail="At most 8 strategy IDs may be compared at once."
        )

    try:
        ids = [uuid.UUID(sid) for sid in payload.strategy_ids]
    except ValueError:
        raise HTTPException(status_code=422, detail="One or more strategy IDs are not valid UUIDs.")

    # Validate existence
    strategies = db.query(Strategy).filter(Strategy.id.in_(ids)).all()
    found_ids = {s.id for s in strategies}
    missing = [str(sid) for sid in ids if sid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Strategies not found: {missing}",
        )

    # Validate archived
    if not payload.include_archived:
        archived_names = [s.name for s in strategies if s.status == "archived"]
        if archived_names:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Archived strategies cannot be compared without include_archived=true: "
                    f"{archived_names}"
                ),
            )

    result: StrategyComparisonResult = _compare(
        ids, db, include_archived=payload.include_archived
    )

    def _cov_schema(cov: StrategyEvidenceCoverageData) -> StrategyEvidenceCoverage:
        return StrategyEvidenceCoverage(
            run_count=cov.run_count,
            backtest_run_count=cov.backtest_run_count,
            research_run_count=cov.research_run_count,
            paper_run_count=cov.paper_run_count,
            live_run_count=cov.live_run_count,
            dataset_snapshot_linked_count=cov.dataset_snapshot_linked_count,
            backtest_audit_count=cov.backtest_audit_count,
            config_snapshot_count=cov.config_snapshot_count,
            universe_snapshot_count=cov.universe_snapshot_count,
            signal_snapshot_count=cov.signal_snapshot_count,
            open_alert_count=cov.open_alert_count,
            report_count=cov.report_count,
            timeline_event_count=cov.timeline_event_count,
            evidence_coverage_score=cov.evidence_coverage_score,
        )

    def _item_schema(item: StrategyComparisonItemData) -> StrategyComparisonItem:
        return StrategyComparisonItem(
            strategy_id=item.strategy_id,
            name=item.name,
            slug=item.slug,
            asset_class=item.asset_class,
            status=item.status,
            overall_reliability_score=item.overall_reliability_score,
            reliability_status=item.reliability_status,
            reliability_generated_at=item.reliability_generated_at,
            strategy_activity_score=item.strategy_activity_score,
            data_evidence_score=item.data_evidence_score,
            backtest_trust_score=item.backtest_trust_score,
            config_evidence_score=item.config_evidence_score,
            universe_evidence_score=item.universe_evidence_score,
            signal_evidence_score=item.signal_evidence_score,
            alert_penalty_score=item.alert_penalty_score,
            report_coverage_score=item.report_coverage_score,
            missing_evidence=item.missing_evidence,
            suggested_checks=item.suggested_checks,
            coverage=_cov_schema(item.coverage),
            latest_run_at=item.latest_run_at,
            latest_backtest_trust_score=item.latest_backtest_trust_score,
            latest_data_health_score=item.latest_data_health_score,
            latest_signal_quality_score=item.latest_signal_quality_score,
            latest_report_score=item.latest_report_score,
            highest_severity_open_alert=item.highest_severity_open_alert,
            gaps=item.gaps,
        )

    return StrategyComparisonResponse(
        strategies=[_item_schema(i) for i in result.strategies],
        ranked_by_reliability=[
            StrategyComparisonRankingItem(
                rank=r.rank,
                strategy_id=r.strategy_id,
                name=r.name,
                score=r.score,
                score_label=r.score_label,
                status=r.status,
            )
            for r in result.ranked_by_reliability
        ],
        ranked_by_evidence_coverage=[
            StrategyComparisonRankingItem(
                rank=r.rank,
                strategy_id=r.strategy_id,
                name=r.name,
                score=r.score,
                score_label=r.score_label,
                status=r.status,
            )
            for r in result.ranked_by_evidence_coverage
        ],
        strongest_strategy_id=result.strongest_strategy_id,
        weakest_strategy_id=result.weakest_strategy_id,
        shared_gaps=result.shared_gaps,
        differentiators=result.differentiators,
        deterministic_explanation=result.deterministic_explanation,
        generated_at=result.generated_at,
    )


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
            selectinload(Strategy.runs)
            .selectinload(StrategyRun.universe_snapshot),
            selectinload(Strategy.runs)
            .selectinload(StrategyRun.signal_snapshot),
            selectinload(Strategy.config_snapshots),
            selectinload(Strategy.universe_snapshots),
            selectinload(Strategy.signal_snapshots),
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
    version_config_counts: dict[uuid.UUID, int] = {}
    for cs in (strategy.config_snapshots or []):
        if cs.strategy_version_id is not None:
            version_config_counts[cs.strategy_version_id] = (
                version_config_counts.get(cs.strategy_version_id, 0) + 1
            )

    # Compute per-version universe_snapshot_count.
    version_uni_counts: dict[uuid.UUID, int] = {}
    for us in (strategy.universe_snapshots or []):
        if us.strategy_version_id is not None:
            version_uni_counts[us.strategy_version_id] = (
                version_uni_counts.get(us.strategy_version_id, 0) + 1
            )

    # Compute per-version signal_snapshot_count.
    version_sig_counts: dict[uuid.UUID, int] = {}
    for ss in (strategy.signal_snapshots or []):
        if ss.strategy_version_id is not None:
            version_sig_counts[ss.strategy_version_id] = (
                version_sig_counts.get(ss.strategy_version_id, 0) + 1
            )

    # Build version list with all counts, newest-first.
    sorted_versions = sorted(strategy.versions, key=lambda v: v.created_at, reverse=True)
    version_outs: list[StrategyVersionOut] = []
    for v in sorted_versions:
        vout = StrategyVersionOut.model_validate(v)
        vout.config_snapshot_count = version_config_counts.get(v.id, 0)
        vout.universe_snapshot_count = version_uni_counts.get(v.id, 0)
        vout.signal_snapshot_count = version_sig_counts.get(v.id, 0)
        version_outs.append(vout)

    # M18: load latest reliability score
    latest_rel_score = (
        db.query(StrategyReliabilityScore)
        .filter(StrategyReliabilityScore.strategy_id == strategy_id)
        .order_by(StrategyReliabilityScore.generated_at.desc())
        .first()
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
        versions=version_outs,
        runs=[_build_run_out(r) for r in sorted_runs],
        config_snapshots=[
            StrategyConfigSnapshotRead.model_validate(cs)
            for cs in strategy.config_snapshots
        ],
        universe_snapshots=[
            UniverseSnapshotRead.model_validate(us)
            for us in strategy.universe_snapshots
        ],
        signal_snapshots=[
            SignalSnapshotRead.model_validate(ss)
            for ss in strategy.signal_snapshots
        ],
        latest_reliability_score=(
            StrategyReliabilityScoreRead.model_validate(latest_rel_score)
            if latest_rel_score is not None
            else None
        ),
    )


# ---------------------------------------------------------------------------
# M19: GET /api/strategies/{strategy_id}/reliability-scores/compare
# NOTE: registered BEFORE /reliability-scores (history) so the literal
# '/compare' segment is matched before any future parameterised sub-path.
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/reliability-scores/compare",
    response_model=ReliabilityScoreComparisonResponse,
)
def compare_strategy_reliability_score_pair(
    strategy_id: uuid.UUID,
    score_a_id: uuid.UUID = Query(..., description="Earlier (baseline) score ID"),
    score_b_id: uuid.UUID = Query(..., description="Later (current) score ID"),
    db: Session = Depends(get_db),
) -> ReliabilityScoreComparisonResponse:
    """Compare two reliability score rows for the same strategy.

    Score A is the baseline (older); score B is the current (newer).
    Returns structured deltas, evidence changes, and a deterministic explanation.
    No timeline event created — this is a read-only comparison.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    score_a = (
        db.query(StrategyReliabilityScore)
        .filter(
            StrategyReliabilityScore.id == score_a_id,
            StrategyReliabilityScore.strategy_id == strategy_id,
        )
        .first()
    )
    if score_a is None:
        raise HTTPException(
            status_code=404,
            detail=f"Score A ({score_a_id}) not found for this strategy",
        )

    score_b = (
        db.query(StrategyReliabilityScore)
        .filter(
            StrategyReliabilityScore.id == score_b_id,
            StrategyReliabilityScore.strategy_id == strategy_id,
        )
        .first()
    )
    if score_b is None:
        raise HTTPException(
            status_code=404,
            detail=f"Score B ({score_b_id}) not found for this strategy",
        )

    result = compare_reliability_scores(score_a, score_b)

    return ReliabilityScoreComparisonResponse(
        score_a_id=result.score_a_id,
        score_b_id=result.score_b_id,
        score_a_generated_at=result.score_a_generated_at,
        score_b_generated_at=result.score_b_generated_at,
        overall_score_a=result.overall_score_a,
        overall_score_b=result.overall_score_b,
        overall_delta=result.overall_delta,
        status_a=result.status_a,
        status_b=result.status_b,
        status_changed=result.status_changed,
        component_deltas=[
            _ReliabilityComponentDelta(
                component=d.component,
                label=d.label,
                score_a=d.score_a,
                score_b=d.score_b,
                delta=d.delta,
                became_available=d.became_available,
                became_null=d.became_null,
            )
            for d in result.component_deltas
        ],
        evidence_count_deltas=[
            _EvidenceCountDelta(
                key=e.key,
                count_a=e.count_a,
                count_b=e.count_b,
                delta=e.delta,
            )
            for e in result.evidence_count_deltas
        ],
        newly_available_evidence=result.newly_available_evidence,
        resolved_missing_evidence=result.resolved_missing_evidence,
        still_missing_evidence=result.still_missing_evidence,
        highlighted_changes=result.highlighted_changes,
        deterministic_explanation=result.deterministic_explanation,
    )


# ---------------------------------------------------------------------------
# M19: GET /api/strategies/{strategy_id}/reliability-scores  (history)
# NOTE: registered AFTER /compare so 'compare' is matched as a literal.
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/reliability-scores",
    response_model=StrategyReliabilityScoreHistoryResponse,
)
def get_strategy_reliability_score_history(
    strategy_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> StrategyReliabilityScoreHistoryResponse:
    """Return the reliability score history for a strategy, newest-first.

    Each item is a full score row including all component scores and evidence
    metadata.  Use ``limit`` and ``offset`` for pagination.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    q = db.query(StrategyReliabilityScore).filter(
        StrategyReliabilityScore.strategy_id == strategy_id
    )
    total: int = q.count()
    items = (
        q.order_by(StrategyReliabilityScore.generated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return StrategyReliabilityScoreHistoryResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[StrategyReliabilityScoreRead.model_validate(s) for s in items],
    )


# ---------------------------------------------------------------------------
# M19: GET /api/strategies/{strategy_id}/reliability-score/trend
# NOTE: registered BEFORE the plain /reliability-score GET so the '/trend'
# literal is matched before any future sub-path of reliability-score.
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/reliability-score/trend",
    response_model=ReliabilityScoreTrendResponse,
)
def get_strategy_reliability_score_trend(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ReliabilityScoreTrendResponse:
    """Return the latest vs. previous reliability score comparison.

    ``has_trend`` is False when fewer than two scores exist — no fake data.
    When two or more scores exist, returns the latest score, the previous score,
    and a deterministic comparison between them (previous=A, latest=B).
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    scores = (
        db.query(StrategyReliabilityScore)
        .filter(StrategyReliabilityScore.strategy_id == strategy_id)
        .order_by(StrategyReliabilityScore.generated_at.desc())
        .limit(2)
        .all()
    )

    if len(scores) < 2:
        return ReliabilityScoreTrendResponse(
            has_trend=False,
            message=(
                "Not enough history. Compute at least two reliability scores "
                "to see trend."
            ),
            latest=StrategyReliabilityScoreRead.model_validate(scores[0])
            if scores
            else None,
            previous=None,
            comparison=None,
        )

    latest_score, prev_score = scores[0], scores[1]
    result = compare_reliability_scores(prev_score, latest_score)

    comparison_out = ReliabilityScoreComparisonResponse(
        score_a_id=result.score_a_id,
        score_b_id=result.score_b_id,
        score_a_generated_at=result.score_a_generated_at,
        score_b_generated_at=result.score_b_generated_at,
        overall_score_a=result.overall_score_a,
        overall_score_b=result.overall_score_b,
        overall_delta=result.overall_delta,
        status_a=result.status_a,
        status_b=result.status_b,
        status_changed=result.status_changed,
        component_deltas=[
            _ReliabilityComponentDelta(
                component=d.component,
                label=d.label,
                score_a=d.score_a,
                score_b=d.score_b,
                delta=d.delta,
                became_available=d.became_available,
                became_null=d.became_null,
            )
            for d in result.component_deltas
        ],
        evidence_count_deltas=[
            _EvidenceCountDelta(
                key=e.key,
                count_a=e.count_a,
                count_b=e.count_b,
                delta=e.delta,
            )
            for e in result.evidence_count_deltas
        ],
        newly_available_evidence=result.newly_available_evidence,
        resolved_missing_evidence=result.resolved_missing_evidence,
        still_missing_evidence=result.still_missing_evidence,
        highlighted_changes=result.highlighted_changes,
        deterministic_explanation=result.deterministic_explanation,
    )

    return ReliabilityScoreTrendResponse(
        has_trend=True,
        message="Trend available. Comparing previous score to latest score.",
        latest=StrategyReliabilityScoreRead.model_validate(latest_score),
        previous=StrategyReliabilityScoreRead.model_validate(prev_score),
        comparison=comparison_out,
    )


# ---------------------------------------------------------------------------
# M18: GET /api/strategies/{strategy_id}/reliability-score
# NOTE: registered BEFORE POST to avoid Starlette path conflicts if any.
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/reliability-score",
    response_model=StrategyReliabilityScoreRead,
)
def get_strategy_reliability_score(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StrategyReliabilityScoreRead:
    """Return the latest computed reliability score for a strategy.

    404 if no score has been computed yet.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    score = (
        db.query(StrategyReliabilityScore)
        .filter(StrategyReliabilityScore.strategy_id == strategy_id)
        .order_by(StrategyReliabilityScore.generated_at.desc())
        .first()
    )
    if score is None:
        raise HTTPException(
            status_code=404,
            detail="No reliability score computed yet for this strategy",
        )

    return StrategyReliabilityScoreRead.model_validate(score)


# ---------------------------------------------------------------------------
# M18: POST /api/strategies/{strategy_id}/reliability-score
# ---------------------------------------------------------------------------

@router.post(
    "/strategies/{strategy_id}/reliability-score",
    response_model=StrategyReliabilityScoreRead,
    status_code=201,
)
def compute_strategy_reliability_score(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StrategyReliabilityScoreRead:
    """Compute and persist a reliability score for a strategy.

    Deterministic — scores all available evidence (runs, snapshots, audits,
    alerts, reports) and returns a structured score.
    No AI, no live market data, no external calls.
    """
    strategy = (
        db.query(Strategy)
        .options(selectinload(Strategy.project))
        .filter(Strategy.id == strategy_id)
        .first()
    )
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    score_data = compute_reliability_score(str(strategy_id), db)

    score_row = StrategyReliabilityScore(**score_data)
    db.add(score_row)
    db.flush()

    event = AuditTimelineEvent(
        organization_id=strategy.project.organization_id,
        project_id=strategy.project_id,
        strategy_id=strategy_id,
        event_type=EventType.strategy_reliability_scored,
        title=f"Reliability scored: {score_row.status}",
        description=(
            f"Reliability score computed for strategy '{strategy.name}'. "
            f"Overall: {score_row.overall_score if score_row.overall_score is not None else 'N/A'}/100. "
            f"Status: {score_row.status}."
        ),
        source_type="strategy_reliability_score",
        source_id=str(score_row.id),
        severity=Severity.info,
        metadata_json={
            "overall_score": score_row.overall_score,
            "status": score_row.status,
            "strategy_name": strategy.name,
        },
    )
    db.add(event)
    db.commit()
    db.refresh(score_row)

    return StrategyReliabilityScoreRead.model_validate(score_row)


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

    # M16: Validate universe_snapshot_id when provided.
    uni_snap: UniverseSnapshot | None = None
    if body.universe_snapshot_id is not None:
        uni_snap = (
            db.query(UniverseSnapshot)
            .filter(UniverseSnapshot.id == body.universe_snapshot_id)
            .first()
        )
        if uni_snap is None:
            raise HTTPException(
                status_code=404, detail="Universe snapshot not found"
            )
        if uni_snap.strategy_id != strategy_id:
            raise HTTPException(
                status_code=400,
                detail="Universe snapshot does not belong to this strategy",
            )

    # M17: Validate signal_snapshot_id when provided.
    sig_snap: SignalSnapshot | None = None
    if body.signal_snapshot_id is not None:
        sig_snap = (
            db.query(SignalSnapshot)
            .filter(SignalSnapshot.id == body.signal_snapshot_id)
            .first()
        )
        if sig_snap is None:
            raise HTTPException(status_code=404, detail="Signal snapshot not found")
        if sig_snap.strategy_id != strategy_id:
            raise HTTPException(
                status_code=400,
                detail="Signal snapshot does not belong to this strategy",
            )
        # Version mismatch check: if both run and signal have versions, they must match
        if (
            body.strategy_version_id is not None
            and sig_snap.strategy_version_id is not None
            and sig_snap.strategy_version_id != body.strategy_version_id
        ):
            raise HTTPException(
                status_code=400,
                detail="Signal snapshot is linked to a different strategy version than the run",
            )
        # Universe mismatch check
        if (
            body.universe_snapshot_id is not None
            and sig_snap.universe_snapshot_id is not None
            and sig_snap.universe_snapshot_id != body.universe_snapshot_id
        ):
            raise HTTPException(
                status_code=400,
                detail="Signal snapshot is linked to a different universe snapshot than the run",
            )

    # Auto-set completed_at when status is completed and no value was supplied
    completed_at = body.completed_at
    if body.status == RunStatus.completed and completed_at is None:
        completed_at = datetime.now(timezone.utc)

    run = StrategyRun(
        strategy_id=strategy_id,
        strategy_version_id=body.strategy_version_id,
        dataset_snapshot_id=body.dataset_snapshot_id,
        universe_snapshot_id=body.universe_snapshot_id,
        signal_snapshot_id=body.signal_snapshot_id,
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
            + (
                f" Universe snapshot: {uni_snap.label} ({uni_snap.symbol_count} symbols)."
                if uni_snap else ""
            )
        ),
        source_type="strategy_run",
        source_id=str(run.id),
        severity=Severity.info,
        metadata_json={
            "run_type": run.run_type,
            "status": run.status,
            "universe_name": run.universe_name,
            "dataset_snapshot_id": str(body.dataset_snapshot_id) if body.dataset_snapshot_id else None,
            "universe_snapshot_id": str(body.universe_snapshot_id) if body.universe_snapshot_id else None,
            "universe_snapshot_label": uni_snap.label if uni_snap else None,
            "universe_symbol_count": uni_snap.symbol_count if uni_snap else None,
            "signal_snapshot_id": str(body.signal_snapshot_id) if body.signal_snapshot_id else None,
            "signal_snapshot_label": sig_snap.label if sig_snap else None,
            "signal_row_count": sig_snap.row_count if sig_snap else None,
            "strategy_name": strategy.name,
        },
    )
    db.add(event)
    db.commit()
    db.refresh(run)

    # Attach the already-loaded objects so _build_run_out can build evidence.
    run.snapshot = snap  # type: ignore[assignment]
    run.universe_snapshot = uni_snap  # type: ignore[assignment]
    run.signal_snapshot = sig_snap  # type: ignore[assignment]

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
            selectinload(StrategyRun.universe_snapshot),
            selectinload(StrategyRun.signal_snapshot),
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
    vout.universe_snapshot_count = 0
    vout.signal_snapshot_count = 0
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
    config_counts: dict = dict(
        db.query(
            StrategyConfigSnapshot.strategy_version_id,
            func.count(StrategyConfigSnapshot.id),
        )
        .filter(StrategyConfigSnapshot.strategy_version_id.in_(version_ids))
        .group_by(StrategyConfigSnapshot.strategy_version_id)
        .all()
    )
    uni_counts: dict = dict(
        db.query(
            UniverseSnapshot.strategy_version_id,
            func.count(UniverseSnapshot.id),
        )
        .filter(UniverseSnapshot.strategy_version_id.in_(version_ids))
        .group_by(UniverseSnapshot.strategy_version_id)
        .all()
    )
    sig_counts: dict = dict(
        db.query(
            SignalSnapshot.strategy_version_id,
            func.count(SignalSnapshot.id),
        )
        .filter(SignalSnapshot.strategy_version_id.in_(version_ids))
        .group_by(SignalSnapshot.strategy_version_id)
        .all()
    )

    results: list[StrategyVersionOut] = []
    for v in versions:
        vout = StrategyVersionOut.model_validate(v)
        vout.config_snapshot_count = config_counts.get(v.id, 0)
        vout.universe_snapshot_count = uni_counts.get(v.id, 0)
        vout.signal_snapshot_count = sig_counts.get(v.id, 0)
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


# ---------------------------------------------------------------------------
# M16: GET /api/strategies/{strategy_id}/universe-snapshots/compare
# NOTE: registered BEFORE the list route (/universe-snapshots) so the literal
# "/compare" segment is matched before any query-only /universe-snapshots handler.
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/universe-snapshots/compare",
    response_model=UniverseComparisonResponse,
)
def compare_universe_snapshots_route(
    strategy_id: uuid.UUID,
    snapshot_a_id: uuid.UUID = Query(..., description="ID of the baseline universe snapshot (A)"),
    snapshot_b_id: uuid.UUID = Query(..., description="ID of the comparison universe snapshot (B)"),
    db: Session = Depends(get_db),
) -> UniverseComparisonResponse:
    """Deterministically compare two universe snapshots belonging to this strategy.

    Read-only — no audit event is emitted.
    Returns set-based diff: added/removed/common symbol counts, overlap ratio,
    Jaccard similarity, capped symbol lists (≤50 each), and a hedged explanation.
    Language is hedged throughout — no causal claims are made.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    snap_a = (
        db.query(UniverseSnapshot)
        .filter(
            UniverseSnapshot.id == snapshot_a_id,
            UniverseSnapshot.strategy_id == strategy_id,
        )
        .first()
    )
    if snap_a is None:
        raise HTTPException(status_code=404, detail="Universe snapshot A not found")

    snap_b = (
        db.query(UniverseSnapshot)
        .filter(
            UniverseSnapshot.id == snapshot_b_id,
            UniverseSnapshot.strategy_id == strategy_id,
        )
        .first()
    )
    if snap_b is None:
        raise HTTPException(status_code=404, detail="Universe snapshot B not found")

    result = compare_universe_snapshots(
        snap_a_id=str(snap_a.id),
        snap_b_id=str(snap_b.id),
        snap_a_label=snap_a.label,
        snap_b_label=snap_b.label,
        symbols_a=snap_a.symbols_json or [],
        symbols_b=snap_b.symbols_json or [],
        hash_a=snap_a.universe_hash,
        hash_b=snap_b.universe_hash,
    )

    return UniverseComparisonResponse(
        snapshot_a_id=snap_a.id,
        snapshot_b_id=snap_b.id,
        snapshot_a_label=result.snapshot_a_label,
        snapshot_b_label=result.snapshot_b_label,
        snapshot_a_symbol_count=result.snapshot_a_symbol_count,
        snapshot_b_symbol_count=result.snapshot_b_symbol_count,
        is_same_universe=result.is_same_universe,
        added_count=result.added_count,
        removed_count=result.removed_count,
        common_symbols_count=result.common_symbols_count,
        symbol_count_delta=result.symbol_count_delta,
        overlap_ratio=result.overlap_ratio,
        jaccard_similarity=result.jaccard_similarity,
        added_symbols=result.added_symbols,
        removed_symbols=result.removed_symbols,
        highlighted_changes=result.highlighted_changes,
        deterministic_explanation=result.deterministic_explanation,
    )


# ---------------------------------------------------------------------------
# M16: POST /api/strategies/{strategy_id}/universe-snapshots
# ---------------------------------------------------------------------------

@router.post(
    "/strategies/{strategy_id}/universe-snapshots",
    response_model=UniverseSnapshotRead,
    status_code=201,
)
def create_universe_snapshot(
    strategy_id: uuid.UUID,
    body: UniverseSnapshotCreate,
    db: Session = Depends(get_db),
) -> UniverseSnapshotRead:
    """Create a universe snapshot for a strategy.

    Symbols are normalized (trimmed, uppercased, deduplicated, sorted) before
    storage.  Empty or whitespace-only symbols are silently dropped.
    A deterministic SHA-256 universe_hash is computed from the normalized
    symbols + optional metadata.
    If strategy_version_id is provided it must belong to this strategy.
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

    if not body.symbols:
        raise HTTPException(
            status_code=422,
            detail="symbols must be a non-empty list",
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

    normalized = normalize_symbols(body.symbols)
    if not normalized:
        raise HTTPException(
            status_code=422,
            detail="symbols list contains no valid symbols after normalization",
        )

    universe_hash = compute_universe_hash(normalized, body.metadata_json)

    snapshot = UniverseSnapshot(
        strategy_id=strategy_id,
        strategy_version_id=body.strategy_version_id,
        label=body.label,
        source_type=body.source_type,
        source_filename=body.source_filename,
        symbols_json=normalized,
        symbol_count=len(normalized),
        metadata_json=body.metadata_json,
        universe_hash=universe_hash,
    )
    db.add(snapshot)
    db.flush()

    event = AuditTimelineEvent(
        organization_id=strategy.project.organization_id,
        project_id=strategy.project_id,
        strategy_id=strategy_id,
        event_type=EventType.universe_snapshot_logged,
        title=f"Universe snapshot logged: {snapshot.label}",
        description=(
            f"Universe snapshot '{snapshot.label}' logged for strategy '{strategy.name}'. "
            f"Source: {snapshot.source_type}. "
            f"Symbols: {snapshot.symbol_count}."
        ),
        source_type="universe_snapshot",
        source_id=str(snapshot.id),
        severity=Severity.info,
        metadata_json={
            "snapshot_label": snapshot.label,
            "source_type": snapshot.source_type,
            "universe_hash": universe_hash,
            "symbol_count": snapshot.symbol_count,
            "strategy_name": strategy.name,
        },
    )
    db.add(event)
    db.commit()
    db.refresh(snapshot)

    return UniverseSnapshotRead.model_validate(snapshot)


# ---------------------------------------------------------------------------
# M16: GET /api/strategies/{strategy_id}/universe-snapshots
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/universe-snapshots",
    response_model=list[UniverseSnapshotRead],
)
def list_universe_snapshots(
    strategy_id: uuid.UUID,
    version_id: uuid.UUID | None = Query(default=None, description="Filter by strategy_version_id"),
    db: Session = Depends(get_db),
) -> list[UniverseSnapshotRead]:
    """List universe snapshots for a strategy, newest-first.

    Pass ``version_id`` to filter by a specific strategy version.
    The symbols_json payload is not included; use the detail endpoint for that.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    q = db.query(UniverseSnapshot).filter(
        UniverseSnapshot.strategy_id == strategy_id
    )
    if version_id is not None:
        q = q.filter(UniverseSnapshot.strategy_version_id == version_id)

    snapshots = q.order_by(UniverseSnapshot.created_at.desc()).all()
    return [UniverseSnapshotRead.model_validate(s) for s in snapshots]


# ---------------------------------------------------------------------------
# M16: GET /api/universe-snapshots/{snapshot_id}
# ---------------------------------------------------------------------------

@router.get(
    "/universe-snapshots/{snapshot_id}",
    response_model=UniverseSnapshotDetail,
)
def get_universe_snapshot(
    snapshot_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> UniverseSnapshotDetail:
    """Return full universe snapshot detail including the symbols_json payload."""
    snapshot = (
        db.query(UniverseSnapshot)
        .filter(UniverseSnapshot.id == snapshot_id)
        .first()
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Universe snapshot not found")

    return UniverseSnapshotDetail.model_validate(snapshot)


# ---------------------------------------------------------------------------
# M17: GET /api/strategies/{strategy_id}/signal-snapshots/compare
# NOTE: registered BEFORE the list route (/signal-snapshots) so the literal
# "/compare" segment is matched before any query-only /signal-snapshots handler.
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/signal-snapshots/compare",
    response_model=SignalComparisonResponse,
)
def compare_signal_snapshots_route(
    strategy_id: uuid.UUID,
    snapshot_a_id: uuid.UUID = Query(..., description="ID of the baseline signal snapshot (A)"),
    snapshot_b_id: uuid.UUID = Query(..., description="ID of the comparison signal snapshot (B)"),
    db: Session = Depends(get_db),
) -> SignalComparisonResponse:
    """Deterministically compare two signal snapshots belonging to this strategy.

    Read-only — no audit event is emitted.
    Returns set-based diff for symbols, keyed row-level changes (when available),
    distribution delta, quality delta, and hedged highlighted changes.
    Language is hedged throughout — no causal claims are made.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    snap_a = (
        db.query(SignalSnapshot)
        .filter(
            SignalSnapshot.id == snapshot_a_id,
            SignalSnapshot.strategy_id == strategy_id,
        )
        .first()
    )
    if snap_a is None:
        raise HTTPException(status_code=404, detail="Signal snapshot A not found")

    snap_b = (
        db.query(SignalSnapshot)
        .filter(
            SignalSnapshot.id == snapshot_b_id,
            SignalSnapshot.strategy_id == strategy_id,
        )
        .first()
    )
    if snap_b is None:
        raise HTTPException(status_code=404, detail="Signal snapshot B not found")

    # Extract signal_column from metadata_json if stored there, else default "signal"
    sig_col_a = (snap_a.metadata_json or {}).get("signal_column", "signal")
    sig_col_b = (snap_b.metadata_json or {}).get("signal_column", "signal")

    snap_a_data = {
        "symbols_json": snap_a.symbols_json or [],
        "rows_json": snap_a.rows_json or [],
        "row_count": snap_a.row_count,
        "symbol_count": snap_a.symbol_count,
        "mean_value": snap_a.mean_value,
        "min_value": snap_a.min_value,
        "max_value": snap_a.max_value,
        "stddev_value": snap_a.stddev_value,
        "quality_score": snap_a.quality_score,
        "missing_signal_count": snap_a.missing_signal_count,
        "signal_hash": snap_a.signal_hash,
        "signal_column": sig_col_a,
    }
    snap_b_data = {
        "symbols_json": snap_b.symbols_json or [],
        "rows_json": snap_b.rows_json or [],
        "row_count": snap_b.row_count,
        "symbol_count": snap_b.symbol_count,
        "mean_value": snap_b.mean_value,
        "min_value": snap_b.min_value,
        "max_value": snap_b.max_value,
        "stddev_value": snap_b.stddev_value,
        "quality_score": snap_b.quality_score,
        "missing_signal_count": snap_b.missing_signal_count,
        "signal_hash": snap_b.signal_hash,
        "signal_column": sig_col_b,
    }

    result = compare_signal_snapshots(
        snap_a_id=str(snap_a.id),
        snap_b_id=str(snap_b.id),
        snap_a_label=snap_a.label,
        snap_b_label=snap_b.label,
        snap_a_data=snap_a_data,
        snap_b_data=snap_b_data,
    )

    return SignalComparisonResponse(
        snapshot_a_id=snap_a.id,
        snapshot_b_id=snap_b.id,
        snapshot_a_label=result.snapshot_a_label,
        snapshot_b_label=result.snapshot_b_label,
        snapshot_a_row_count=result.snapshot_a_row_count,
        snapshot_b_row_count=result.snapshot_b_row_count,
        snapshot_a_symbol_count=result.snapshot_a_symbol_count,
        snapshot_b_symbol_count=result.snapshot_b_symbol_count,
        is_same_snapshot=result.is_same_snapshot,
        row_count_delta=result.row_count_delta,
        symbol_count_delta=result.symbol_count_delta,
        added_count=result.added_count,
        removed_count=result.removed_count,
        common_symbols_count=result.common_symbols_count,
        overlap_ratio=result.overlap_ratio,
        mean_value_delta=result.mean_value_delta,
        min_value_delta=result.min_value_delta,
        max_value_delta=result.max_value_delta,
        stddev_value_delta=result.stddev_value_delta,
        quality_score_delta=result.quality_score_delta,
        missing_signal_delta=result.missing_signal_delta,
        keyed_comparison_available=result.keyed_comparison_available,
        added_rows_count=result.added_rows_count,
        removed_rows_count=result.removed_rows_count,
        changed_rows_count=result.changed_rows_count,
        examples=[
            SignalRowChangeOut(
                symbol=ex.symbol,
                timestamp=ex.timestamp,
                change_type=ex.change_type,
                old_value=ex.old_value,
                new_value=ex.new_value,
                delta=ex.delta,
            )
            for ex in result.examples
        ],
        added_symbols=result.added_symbols,
        removed_symbols=result.removed_symbols,
        highlighted_changes=result.highlighted_changes,
        deterministic_explanation=result.deterministic_explanation,
        warnings=result.warnings,
    )


# ---------------------------------------------------------------------------
# M17: POST /api/strategies/{strategy_id}/signal-snapshots
# ---------------------------------------------------------------------------

@router.post(
    "/strategies/{strategy_id}/signal-snapshots",
    response_model=SignalSnapshotRead,
    status_code=201,
)
def create_signal_snapshot(
    strategy_id: uuid.UUID,
    body: SignalSnapshotCreate,
    db: Session = Depends(get_db),
) -> SignalSnapshotRead:
    """Create a signal snapshot for a strategy.

    rows must be a non-empty JSON array of objects.
    Computes summary statistics, quality score, and a deterministic signal_hash.
    If strategy_version_id is provided it must belong to this strategy.
    If universe_snapshot_id is provided it must belong to this strategy.
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

    # Validate rows
    if not body.rows:
        raise HTTPException(
            status_code=422,
            detail="rows must be a non-empty list of objects",
        )

    # Validate row objects
    try:
        normalize_signal_rows(body.rows, body.signal_column)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

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

    # Validate universe_snapshot_id belongs to this strategy when provided.
    if body.universe_snapshot_id is not None:
        uni_snap_ref = (
            db.query(UniverseSnapshot)
            .filter(
                UniverseSnapshot.id == body.universe_snapshot_id,
                UniverseSnapshot.strategy_id == strategy_id,
            )
            .first()
        )
        if uni_snap_ref is None:
            raise HTTPException(status_code=404, detail="Universe snapshot not found")

    # Compute stats and hash
    summary = summarize_signal_snapshot(body.rows, body.signal_column)
    signal_hash = compute_signal_hash(body.rows, body.metadata_json, body.signal_column)

    # Store signal_column in metadata_json if not default
    stored_meta = dict(body.metadata_json) if body.metadata_json else {}
    if body.signal_column and body.signal_column != "signal":
        stored_meta["signal_column"] = body.signal_column
    metadata_to_store = stored_meta if stored_meta else None

    snapshot = SignalSnapshot(
        strategy_id=strategy_id,
        strategy_version_id=body.strategy_version_id,
        universe_snapshot_id=body.universe_snapshot_id,
        label=body.label,
        signal_name=body.signal_name,
        source_type=body.source_type,
        source_filename=body.source_filename,
        rows_json=body.rows,
        row_count=summary.row_count,
        symbol_count=summary.symbol_count,
        symbols_json=summary.symbols,
        min_timestamp=summary.min_timestamp,
        max_timestamp=summary.max_timestamp,
        signal_value_count=summary.signal_value_count,
        missing_signal_count=summary.missing_signal_count,
        mean_value=summary.mean_value,
        min_value=summary.min_value,
        max_value=summary.max_value,
        stddev_value=summary.stddev_value,
        signal_hash=signal_hash,
        quality_score=summary.quality_score,
        metadata_json=metadata_to_store,
    )
    db.add(snapshot)
    db.flush()

    event = AuditTimelineEvent(
        organization_id=strategy.project.organization_id,
        project_id=strategy.project_id,
        strategy_id=strategy_id,
        event_type=EventType.signal_snapshot_logged,
        title=f"Signal snapshot logged: {snapshot.label}",
        description=(
            f"Signal snapshot '{snapshot.label}' logged for strategy '{strategy.name}'. "
            f"Source: {snapshot.source_type}. "
            f"Rows: {snapshot.row_count}. Symbols: {snapshot.symbol_count}. "
            f"Quality: {snapshot.quality_score}/100."
        ),
        source_type="signal_snapshot",
        source_id=str(snapshot.id),
        severity=Severity.info,
        metadata_json={
            "snapshot_label": snapshot.label,
            "source_type": snapshot.source_type,
            "signal_hash": signal_hash,
            "row_count": snapshot.row_count,
            "symbol_count": snapshot.symbol_count,
            "quality_score": snapshot.quality_score,
            "signal_name": snapshot.signal_name,
            "strategy_name": strategy.name,
        },
    )
    db.add(event)
    db.commit()
    db.refresh(snapshot)

    return SignalSnapshotRead.model_validate(snapshot)


# ---------------------------------------------------------------------------
# M17: GET /api/strategies/{strategy_id}/signal-snapshots
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/signal-snapshots",
    response_model=list[SignalSnapshotRead],
)
def list_signal_snapshots(
    strategy_id: uuid.UUID,
    version_id: uuid.UUID | None = Query(default=None, description="Filter by strategy_version_id"),
    db: Session = Depends(get_db),
) -> list[SignalSnapshotRead]:
    """List signal snapshots for a strategy, newest-first.

    Pass ``version_id`` to filter by a specific strategy version.
    The rows_json payload is not included; use the detail endpoint for that.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    q = db.query(SignalSnapshot).filter(
        SignalSnapshot.strategy_id == strategy_id
    )
    if version_id is not None:
        q = q.filter(SignalSnapshot.strategy_version_id == version_id)

    snapshots = q.order_by(SignalSnapshot.created_at.desc()).all()
    return [SignalSnapshotRead.model_validate(s) for s in snapshots]


# ---------------------------------------------------------------------------
# M17: GET /api/signal-snapshots/{snapshot_id}
# ---------------------------------------------------------------------------

@router.get(
    "/signal-snapshots/{snapshot_id}",
    response_model=SignalSnapshotDetail,
)
def get_signal_snapshot(
    snapshot_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> SignalSnapshotDetail:
    """Return full signal snapshot detail including the rows_json payload."""
    snapshot = (
        db.query(SignalSnapshot)
        .filter(SignalSnapshot.id == snapshot_id)
        .first()
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Signal snapshot not found")

    return SignalSnapshotDetail.model_validate(snapshot)
