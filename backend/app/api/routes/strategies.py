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

  M38 signal quality drilldown:
  GET  /api/signal-snapshots/{snapshot_id}/quality-drilldown

  M39 universe coverage analysis:
  GET  /api/universe-snapshots/{snapshot_id}/coverage-analysis

  M41 assumption health:
  GET  /api/strategies/{strategy_id}/assumption-health
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.core.constants import AssetClass, EventType, ReliabilityScoreStatus, RunStatus, RunType, Severity, StrategyStatus
from app.core.rbac import require_workspace_write_access
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
from app.schemas.multi_run_comparison import (
    MultiRunComparisonRequest,
    MultiRunComparisonResponse,
    MultiRunItemSchema,
    MultiRunRankingItemSchema,
    RunAssumptionsSchema,
    RunEvidenceSummarySchema,
    RunMetricsSchema,
)
from app.schemas.strategy import (
    ConfigComparisonResponse,
    ConfigComparisonSectionOut,
    ConfigDiffSection,
    ConfigFieldChange,
    ConfigKeyChangeOut,
    ConfigSnapshotComparisonV2Response,
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
from app.schemas.version_lineage import (
    StrategyVersionLineageItem,
    StrategyVersionLineageSummary,
    StrategyVersionTransition,
    StrategyVersionLineageResponse,
)
from app.schemas.strategy_drift import (
    AssumptionDriftItem,
    EvidenceDriftItem,
    MetricDriftItem,
    StrategyDriftResponse,
    StrategyDriftRunSummary,
    TrustDriftItem,
)
from app.services.strategy_drift import (
    StrategyDriftData,
    StrategyDriftRunSummaryData,
    compute_strategy_drift,
)
from app.services.version_lineage import (
    get_strategy_version_lineage,
    StrategyVersionLineageData,
    StrategyVersionLineageItemData,
    StrategyVersionLineageSummaryData,
    StrategyVersionTransitionData,
)
from app.schemas.strategy_health import StrategyHealthListResponse, StrategyHealthRead
from app.services.strategy_health import compute_strategy_health, get_strategies_health
from app.schemas.assumption_health import (
    AssumptionCategoryScorecard,
    BacktestAuditAssumptionSummary,
    ConfigDiffAssumptionSummary,
    StrategyAssumptionHealthResponse,
)
from app.services.assumption_health import compute_assumption_health
from app.services.strategy_reliability import (
    compare_reliability_scores,
    compute_reliability_score,
)
from app.schemas.timeline import TimelineEventOut, TimelineListResponse
from app.schemas.run_history import (
    BacktestAuditSummarySchema,
    DatasetEvidence,
    SignalEvidence,
    StrategyRunHistoryItem as RunHistItem,
    StrategyRunHistorySummary,
    StrategyRunHistoryResponse,
    StrategyTimelineDrilldownItem as TLDItem,
    StrategyTimelineDrilldownSummary,
    StrategyTimelineDrilldownResponse,
    StrategyVersionSummary,
    UniverseEvidence,
)
from app.services.strategy_run_history import get_strategy_run_history as _get_run_history
from app.services.strategy_timeline import get_strategy_timeline_drilldown as _get_tl_drilldown
from app.schemas.evidence_trends import (
    TrendPoint,
    TrendSummary,
    EvidenceCoverageCurrentSummary,
    StrategyEvidenceTrendsResponse,
)
from app.services.evidence_trends import (
    get_strategy_evidence_trends as _get_evidence_trends,
    TrendPointData,
    TrendSummaryData,
)
from app.schemas.strategy_export import (
    StrategyExportSection,
    StrategyExportMetadata,
    StrategyExportResponse,
)
from app.services.strategy_export import (
    generate_strategy_export,
    StrategyExportData,
    StrategyExportSectionData,
    StrategyExportMetadataData,
)
from app.schemas.strategy_comparison_report import (
    StrategyComparisonReportRequest,
    StrategyComparisonReportMetadata,
    StrategyComparisonReportSection,
    StrategyComparisonReportStrategySummary,
    StrategyComparisonReportResponse,
)
from app.services.strategy_comparison_report import (
    generate_strategy_comparison_report,
    StrategyComparisonReportData,
)
from app.services.config_snapshots import (
    compare_config_snapshots,
    compare_config_snapshots_enriched,
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
from app.schemas.signal_quality import (
    SignalDistributionRead,
    SignalQualityDrilldownResponse,
    SignalQualitySummaryRead,
    SignalRowQualitySampleRead,
    SignalRowQualitySamplesRead,
    SignalTimestampCoverageRead,
    SymbolSignalQualityRead,
)
from app.schemas.timeline_analytics import (
    TimelineAnalyticsBucket,
    TimelineInactivityGap,
    StrategyTimelineAnalyticsResponse,
)
from app.services.timeline_analytics import (
    compute_strategy_timeline_analytics,
    TimelineAnalyticsBucketData,
    TimelineInactivityGapData,
    StrategyTimelineAnalyticsData,
)
from app.schemas.strategy_readiness import (
    StrategyReadinessDimension,
    StrategyProgressionPath,
    StrategyReadinessResponse,
)
from app.services.strategy_readiness import compute_strategy_readiness, StrategyReadinessData
from app.schemas.promotion_gates import PromotionGateCheck, StrategyPromotionGateResponse
from app.services.promotion_gates import (
    evaluate_promotion_gates,
    StrategyPromotionGateData,
    PromotionGateCheckData,
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
def create_strategy(
    body: StrategyCreate,
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_write_access),
) -> StrategyListItemOut:
    """Create a strategy. RBAC: Owner/Admin/Member (viewers read-only)."""
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
# POST /api/strategies/compare/report  (M44)
# Registered BEFORE GET /strategies/{strategy_id} to avoid path collision.
# ---------------------------------------------------------------------------

@router.post(
    "/strategies/compare/report",
    response_model=StrategyComparisonReportResponse,
    status_code=200,
)
def generate_comparison_report(
    payload: StrategyComparisonReportRequest,
    db: Session = Depends(get_db),
) -> StrategyComparisonReportResponse:
    """Generate a deterministic side-by-side comparison report for 2–4 strategies.

    Evidence-based report only — never investment advice.
    """
    if len(payload.strategy_ids) < 2:
        raise HTTPException(status_code=422, detail="At least 2 strategy IDs required.")
    if len(payload.strategy_ids) > 4:
        raise HTTPException(status_code=422, detail="At most 4 strategy IDs may be compared.")
    if payload.format not in ("json", "markdown"):
        raise HTTPException(status_code=400, detail="format must be 'json' or 'markdown'")

    try:
        ids = [uuid.UUID(s) for s in payload.strategy_ids]
    except ValueError:
        raise HTTPException(
            status_code=422, detail="One or more strategy IDs are not valid UUIDs."
        )

    try:
        result: StrategyComparisonReportData = generate_strategy_comparison_report(
            ids, db, format=payload.format, include_raw_json=payload.include_raw_json
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return StrategyComparisonReportResponse(
        format=result.format,
        filename=result.filename,
        metadata=StrategyComparisonReportMetadata(
            report_id=result.metadata.report_id,
            generated_at=result.metadata.generated_at,
            format=result.metadata.format,
            note=result.metadata.note,
            strategy_count=result.metadata.strategy_count,
            strategy_ids=result.metadata.strategy_ids,
        ),
        sections=[
            StrategyComparisonReportSection(
                section_key=sec.section_key,
                title=sec.title,
                summary=sec.summary,
                severity=sec.severity,
                evidence_json=sec.evidence_json,
            )
            for sec in result.sections
        ],
        strategy_summaries=[
            StrategyComparisonReportStrategySummary(
                strategy_id=s.strategy_id,
                name=s.name,
                asset_class=s.asset_class,
                status=s.status,
                health_status=s.health_status,
                health_score=s.health_score,
                primary_concern=s.primary_concern,
                reliability_score=s.reliability_score,
                reliability_status=s.reliability_status,
                evidence_coverage_score=s.evidence_coverage_score,
                assumption_status=s.assumption_status,
                assumption_score=s.assumption_score,
                weakening_change_count=s.weakening_change_count,
                positive_change_count=s.positive_change_count,
                open_alert_count=s.open_alert_count,
                high_critical_alert_count=s.high_critical_alert_count,
                reliability_trend=s.reliability_trend,
                data_health_trend=s.data_health_trend,
                backtest_trust_trend=s.backtest_trust_trend,
                signal_quality_trend=s.signal_quality_trend,
                suggested_checks=s.suggested_checks,
            )
            for s in result.strategy_summaries
        ],
        rankings=result.rankings,
        suggested_review_agenda=result.suggested_review_agenda,
        content=result.content,
        raw_evidence=result.raw_evidence,
    )


# ---------------------------------------------------------------------------
# POST /api/strategies/runs/compare-multi  (M34)
# Must be registered BEFORE GET /strategies/{strategy_id} so "runs" is not
# captured as a strategy_id path parameter.
# ---------------------------------------------------------------------------

@router.post("/strategies/runs/compare-multi", response_model=MultiRunComparisonResponse)
def compare_multi_runs(
    payload: MultiRunComparisonRequest,
    db: Session = Depends(get_db),
) -> MultiRunComparisonResponse:
    """Compare the latest (or selected) run from 2–4 strategies side-by-side.

    Evidence-based, deterministic — never investment advice or causal claims.
    """
    from app.services.multi_run_comparison import (
        compare_multi_strategy_runs,
        MultiRunItemData,
        RunEvidenceSummaryData,
    )

    if len(payload.strategy_ids) < 2:
        raise HTTPException(status_code=422, detail="At least 2 strategy IDs required.")
    if len(payload.strategy_ids) > 4:
        raise HTTPException(status_code=422, detail="At most 4 strategy IDs may be compared.")

    try:
        ids = [uuid.UUID(s) for s in payload.strategy_ids]
    except ValueError:
        raise HTTPException(status_code=422, detail="One or more strategy IDs are not valid UUIDs.")

    run_ids: list[uuid.UUID] | None = None
    if payload.run_ids:
        try:
            run_ids = [uuid.UUID(r) for r in payload.run_ids]
        except ValueError:
            raise HTTPException(status_code=422, detail="One or more run IDs are not valid UUIDs.")

    try:
        result = compare_multi_strategy_runs(ids, db, mode=payload.mode, run_ids=run_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    def _evidence_schema(ev: RunEvidenceSummaryData) -> RunEvidenceSummarySchema:
        return RunEvidenceSummarySchema(
            dataset_health_score=ev.dataset_health_score,
            dataset_issue_count=ev.dataset_issue_count,
            dataset_label=ev.dataset_label,
            signal_quality_score=ev.signal_quality_score,
            signal_missing_count=ev.signal_missing_count,
            signal_label=ev.signal_label,
            universe_symbol_count=ev.universe_symbol_count,
            universe_label=ev.universe_label,
            backtest_trust_score=ev.backtest_trust_score,
            backtest_status=ev.backtest_status,
            backtest_issue_count=ev.backtest_issue_count,
            cost_fragility_level=ev.cost_fragility_level,
            fill_realism_level=ev.fill_realism_level,
            run_health_label=ev.run_health_label,
        )

    def _item_schema(item: MultiRunItemData) -> MultiRunItemSchema:
        return MultiRunItemSchema(
            strategy_id=item.strategy_id,
            strategy_name=item.strategy_name,
            asset_class=item.asset_class,
            status=item.status,
            run_id=item.run_id,
            run_name=item.run_name,
            run_type=item.run_type,
            run_status=item.run_status,
            completed_at=item.completed_at,
            created_at=item.created_at,
            strategy_version_label=item.strategy_version_label,
            open_alert_count=item.open_alert_count,
            reliability_score=item.reliability_score,
            reliability_status=item.reliability_status,
            evidence_coverage_score=item.evidence_coverage_score,
            metrics=RunMetricsSchema(
                sharpe=item.metrics.sharpe,
                sortino=item.metrics.sortino,
                annual_return=item.metrics.annual_return,
                volatility=item.metrics.volatility,
                max_drawdown=item.metrics.max_drawdown,
                turnover=item.metrics.turnover,
                hit_rate=item.metrics.hit_rate,
                trade_count=item.metrics.trade_count,
                alpha_bps=item.metrics.alpha_bps,
                transaction_cost_bps=item.metrics.transaction_cost_bps,
                slippage_bps=item.metrics.slippage_bps,
            ),
            assumptions=RunAssumptionsSchema(
                transaction_cost_bps=item.assumptions.transaction_cost_bps,
                slippage_bps=item.assumptions.slippage_bps,
                fill_model=item.assumptions.fill_model,
                borrow_cost_bps=item.assumptions.borrow_cost_bps,
                short_enabled=item.assumptions.short_enabled,
                execution_timing=item.assumptions.execution_timing,
            ),
            evidence=_evidence_schema(item.evidence),
        )

    def _ranking_schema(r) -> MultiRunRankingItemSchema:  # type: ignore[type-arg]
        return MultiRunRankingItemSchema(
            rank=r.rank,
            strategy_id=r.strategy_id,
            strategy_name=r.strategy_name,
            value=r.value,
            value_label=r.value_label,
            run_name=r.run_name,
        )

    rankings_out: dict[str, list[MultiRunRankingItemSchema]] = {
        dim: [_ranking_schema(r) for r in ranking_list]
        for dim, ranking_list in result.rankings.items()
    }

    return MultiRunComparisonResponse(
        compared_at=result.compared_at,
        mode=result.mode,
        items=[_item_schema(i) for i in result.items],
        metric_matrix=result.metric_matrix,
        assumption_matrix=result.assumption_matrix,
        evidence_matrix=result.evidence_matrix,
        rankings=rankings_out,
        gaps=result.gaps,
        shared_gaps=result.shared_gaps,
        highlighted_differences=result.highlighted_differences,
        deterministic_explanation=result.deterministic_explanation,
    )


# ---------------------------------------------------------------------------
# GET /api/strategies/health  (M27)
# Must be registered BEFORE GET /strategies/{strategy_id} so "health" is
# not captured as a strategy_id path parameter.
# ---------------------------------------------------------------------------

@router.get("/strategies/health", response_model=StrategyHealthListResponse)
def list_strategies_health(
    status: str | None = Query(default=None),
    asset_class: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> StrategyHealthListResponse:
    """Return current health snapshots for non-archived strategies.
    Computed on read — not persisted. Deterministic, no AI.
    """
    items, total = get_strategies_health(
        db, status=status, asset_class=asset_class, limit=limit, offset=offset
    )
    return StrategyHealthListResponse(
        items=[
            StrategyHealthRead(
                strategy_id=s.strategy_id,
                strategy_name=s.strategy_name,
                asset_class=s.asset_class,
                status=s.status,
                health_score=s.health_score,
                health_status=s.health_status,
                primary_concern=s.primary_concern,
                latest_run_at=s.latest_run_at,
                days_since_latest_run=s.days_since_latest_run,
                latest_reliability_score=s.latest_reliability_score,
                reliability_status=s.reliability_status,
                evidence_coverage_score=s.evidence_coverage_score,
                open_alert_count=s.open_alert_count,
                high_critical_alert_count=s.high_critical_alert_count,
                latest_ingestion_status=s.latest_ingestion_status,
                latest_ingestion_at=s.latest_ingestion_at,
                latest_backtest_trust_score=s.latest_backtest_trust_score,
                latest_data_health_score=s.latest_data_health_score,
                latest_signal_quality_score=s.latest_signal_quality_score,
                latest_report_score=s.latest_report_score,
                missing_evidence=s.missing_evidence,
                suggested_checks=s.suggested_checks,
                generated_at=s.generated_at,
            )
            for s in items
        ],
        total=total,
        limit=limit,
        offset=offset,
        generated_at=datetime.now(timezone.utc),
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
# M27: GET /api/strategies/{strategy_id}/health
# ---------------------------------------------------------------------------

@router.get("/strategies/{strategy_id}/health", response_model=StrategyHealthRead)
def get_strategy_health(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StrategyHealthRead:
    """Return current health snapshot for a strategy. Computed on read, not persisted.
    Deterministic — no AI, no live market data.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    try:
        snap = compute_strategy_health(strategy_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return StrategyHealthRead(
        strategy_id=snap.strategy_id,
        strategy_name=snap.strategy_name,
        asset_class=snap.asset_class,
        status=snap.status,
        health_score=snap.health_score,
        health_status=snap.health_status,
        primary_concern=snap.primary_concern,
        latest_run_at=snap.latest_run_at,
        days_since_latest_run=snap.days_since_latest_run,
        latest_reliability_score=snap.latest_reliability_score,
        reliability_status=snap.reliability_status,
        evidence_coverage_score=snap.evidence_coverage_score,
        open_alert_count=snap.open_alert_count,
        high_critical_alert_count=snap.high_critical_alert_count,
        latest_ingestion_status=snap.latest_ingestion_status,
        latest_ingestion_at=snap.latest_ingestion_at,
        latest_backtest_trust_score=snap.latest_backtest_trust_score,
        latest_data_health_score=snap.latest_data_health_score,
        latest_signal_quality_score=snap.latest_signal_quality_score,
        latest_report_score=snap.latest_report_score,
        missing_evidence=snap.missing_evidence,
        suggested_checks=snap.suggested_checks,
        generated_at=snap.generated_at,
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
    _member=Depends(require_workspace_write_access),
) -> StrategyReliabilityScoreRead:
    """Compute and persist a reliability score for a strategy.

    RBAC: Owner/Admin/Member (viewers read-only).

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
    _member=Depends(require_workspace_write_access),
) -> StrategyRunOut:
    """Log a strategy run. RBAC: Owner/Admin/Member (viewers read-only)."""
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
# M43: GET /api/strategies/{strategy_id}/timeline/analytics
# NOTE: registered BEFORE /drilldown and /timeline so "analytics" is matched
# as a literal path segment.
# ---------------------------------------------------------------------------


@router.get(
    "/strategies/{strategy_id}/timeline/analytics",
    response_model=StrategyTimelineAnalyticsResponse,
)
def get_strategy_timeline_analytics(
    strategy_id: uuid.UUID,
    bucket: str = Query(default="week", description="Bucket size: day, week, or month"),
    lookback_days: int = Query(default=180, ge=1, le=730),
    db: Session = Depends(get_db),
) -> StrategyTimelineAnalyticsResponse:
    """Return deterministic timeline activity analytics for a strategy.

    Buckets events by day/week/month, computes inactivity gaps, staleness
    status, and suggested checks.  No AI, no live market data, read-only.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if bucket not in ("day", "week", "month"):
        raise HTTPException(status_code=400, detail=f"Invalid bucket: {bucket!r}")
    try:
        result = compute_strategy_timeline_analytics(
            strategy_id, db, bucket=bucket, lookback_days=lookback_days
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return StrategyTimelineAnalyticsResponse(
        strategy_id=result.strategy_id,
        strategy_name=result.strategy_name,
        generated_at=result.generated_at,
        bucket=result.bucket,
        lookback_days=result.lookback_days,
        total_events=result.total_events,
        active_bucket_count=result.active_bucket_count,
        empty_bucket_count=result.empty_bucket_count,
        latest_event_at=result.latest_event_at,
        days_since_latest_event=result.days_since_latest_event,
        most_active_bucket_start=result.most_active_bucket_start,
        most_active_bucket_event_count=result.most_active_bucket_event_count,
        dominant_event_type=result.dominant_event_type,
        dominant_evidence_category=result.dominant_evidence_category,
        longest_inactivity_gap_days=result.longest_inactivity_gap_days,
        buckets=[
            TimelineAnalyticsBucket(
                bucket_start=b.bucket_start,
                bucket_end=b.bucket_end,
                total_events=b.total_events,
                event_type_counts=b.event_type_counts,
                source_type_counts=b.source_type_counts,
                evidence_category_counts=b.evidence_category_counts,
            )
            for b in result.buckets
        ],
        gaps=[
            TimelineInactivityGap(
                gap_start=g.gap_start,
                gap_end=g.gap_end,
                gap_days=g.gap_days,
                previous_event_title=g.previous_event_title,
                next_event_title=g.next_event_title,
            )
            for g in result.gaps
        ],
        staleness_status=result.staleness_status,
        deterministic_summary=result.deterministic_summary,
        suggested_checks=result.suggested_checks,
    )


# ---------------------------------------------------------------------------
# M29: GET /api/strategies/{strategy_id}/timeline/drilldown
# NOTE: registered BEFORE the /timeline endpoint so the literal "/drilldown"
# segment is matched before the generic timeline handler.
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/timeline/drilldown",
    response_model=StrategyTimelineDrilldownResponse,
)
def get_strategy_timeline_drilldown_route(
    strategy_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = Query(default=None, description="Filter by event_type"),
    source_type: str | None = Query(default=None, description="Filter by source_type"),
    db: Session = Depends(get_db),
) -> StrategyTimelineDrilldownResponse:
    """Return enriched, per-strategy timeline events with evidence_category,
    source_label, and linked_url_hint fields.

    Deterministic — no AI, no live market data, no external calls.
    All filters are AND-combined.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    items_data, summary_data = _get_tl_drilldown(
        strategy_id, db, limit=limit, offset=offset,
        event_type=event_type, source_type=source_type,
    )

    items = [
        TLDItem(
            event_id=i.event_id,
            event_type=i.event_type,
            title=i.title,
            description=i.description,
            severity=i.severity,
            event_time=i.event_time,
            created_at=i.created_at,
            source_type=i.source_type,
            source_id=i.source_id,
            evidence_category=i.evidence_category,
            source_label=i.source_label,
            linked_url_hint=i.linked_url_hint,
        )
        for i in items_data
    ]

    summary = StrategyTimelineDrilldownSummary(
        total_events=summary_data.total_events,
        event_type_counts=summary_data.event_type_counts,
        source_type_counts=summary_data.source_type_counts,
        latest_event_at=summary_data.latest_event_at,
    )

    return StrategyTimelineDrilldownResponse(
        items=items,
        total=summary_data.total_events,
        limit=limit,
        offset=offset,
        summary=summary,
    )


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
# M29: GET /api/strategies/{strategy_id}/run-history
# NOTE: registered BEFORE the bare /runs route so the literal "/run-history"
# segment is matched before the run-list handler.
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/run-history",
    response_model=StrategyRunHistoryResponse,
)
def get_strategy_run_history_route(
    strategy_id: uuid.UUID,
    run_type: str | None = Query(default=None, description="Filter by run_type"),
    status: str | None = Query(default=None, description="Filter by run status"),
    evidence_status: str | None = Query(
        default=None,
        description=(
            "Filter by evidence completeness: complete, missing_dataset, missing_signal, "
            "missing_universe, missing_audit, review, weak"
        ),
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> StrategyRunHistoryResponse:
    """Return enriched run history for a strategy with per-run evidence indicators.

    Each run includes linked dataset, universe, signal, and backtest audit evidence,
    plus a deterministic run_health_label (strong/usable/review/weak/insufficient_evidence).
    Deterministic — no AI, no live market data, no external calls.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    items_data, summary_data = _get_run_history(
        strategy_id, db,
        run_type=run_type, status=status, evidence_status=evidence_status,
        limit=limit, offset=offset,
    )

    items = [
        RunHistItem(
            run_id=i.run_id,
            run_name=i.run_name,
            run_type=i.run_type,
            status=i.status,
            started_at=i.started_at,
            completed_at=i.completed_at,
            created_at=i.created_at,
            params_json=i.params_json,
            assumptions_json=i.assumptions_json,
            metrics_json=i.metrics_json,
            notes=i.notes,
            strategy_version=(
                StrategyVersionSummary(
                    version_id=i.strategy_version.version_id,
                    version_label=i.strategy_version.version_label,
                    git_commit=i.strategy_version.git_commit,
                    branch_name=i.strategy_version.branch_name,
                    signal_name=i.strategy_version.signal_name,
                )
                if i.strategy_version is not None else None
            ),
            dataset_evidence=(
                DatasetEvidence(
                    dataset_snapshot_id=i.dataset_evidence.dataset_snapshot_id,
                    dataset_name=i.dataset_evidence.dataset_name,
                    snapshot_label=i.dataset_evidence.snapshot_label,
                    health_score=i.dataset_evidence.health_score,
                    issue_count=i.dataset_evidence.issue_count,
                    worst_severity=i.dataset_evidence.worst_severity,
                )
                if i.dataset_evidence is not None else None
            ),
            universe_evidence=(
                UniverseEvidence(
                    universe_snapshot_id=i.universe_evidence.universe_snapshot_id,
                    label=i.universe_evidence.label,
                    symbol_count=i.universe_evidence.symbol_count,
                    universe_hash=i.universe_evidence.universe_hash,
                )
                if i.universe_evidence is not None else None
            ),
            signal_evidence=(
                SignalEvidence(
                    signal_snapshot_id=i.signal_evidence.signal_snapshot_id,
                    label=i.signal_evidence.label,
                    signal_name=i.signal_evidence.signal_name,
                    quality_score=i.signal_evidence.quality_score,
                    missing_signal_count=i.signal_evidence.missing_signal_count,
                    symbol_count=i.signal_evidence.symbol_count,
                    mean_value=i.signal_evidence.mean_value,
                    stddev_value=i.signal_evidence.stddev_value,
                )
                if i.signal_evidence is not None else None
            ),
            backtest_audit=(
                BacktestAuditSummarySchema(
                    audit_id=i.backtest_audit.audit_id,
                    trust_score=i.backtest_audit.trust_score,
                    overall_status=i.backtest_audit.overall_status,
                    issue_count=i.backtest_audit.issue_count,
                    high_critical_issue_count=i.backtest_audit.high_critical_issue_count,
                    cost_fragility_level=i.backtest_audit.cost_fragility_level,
                    fill_realism_level=i.backtest_audit.fill_realism_level,
                )
                if i.backtest_audit is not None else None
            ),
            has_dataset_evidence=i.has_dataset_evidence,
            has_universe_evidence=i.has_universe_evidence,
            has_signal_evidence=i.has_signal_evidence,
            has_backtest_audit=i.has_backtest_audit,
            has_strategy_version=i.has_strategy_version,
            run_health_label=i.run_health_label,
        )
        for i in items_data
    ]

    summary = StrategyRunHistorySummary(
        total_runs=summary_data.total_runs,
        strong_count=summary_data.strong_count,
        usable_count=summary_data.usable_count,
        review_count=summary_data.review_count,
        weak_count=summary_data.weak_count,
        insufficient_evidence_count=summary_data.insufficient_evidence_count,
        runs_missing_dataset=summary_data.runs_missing_dataset,
        runs_missing_signal=summary_data.runs_missing_signal,
        runs_missing_universe=summary_data.runs_missing_universe,
        runs_missing_audit=summary_data.runs_missing_audit,
        latest_run_at=summary_data.latest_run_at,
    )

    return StrategyRunHistoryResponse(
        items=items,
        total=summary_data.total_runs,
        limit=limit,
        offset=offset,
        summary=summary,
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
# M40: GET /api/strategies/{strategy_id}/config-snapshots/compare-v2
# Enriched comparison with assumption classification.
# Registered BEFORE the list route so the literal "/compare-v2" is matched first.
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/config-snapshots/compare-v2",
    response_model=ConfigSnapshotComparisonV2Response,
)
def compare_config_snapshots_v2(
    strategy_id: uuid.UUID,
    snapshot_a_id: uuid.UUID = Query(..., description="ID of the baseline config snapshot (A)"),
    snapshot_b_id: uuid.UUID = Query(..., description="ID of the comparison config snapshot (B)"),
    db: Session = Depends(get_db),
) -> ConfigSnapshotComparisonV2Response:
    """Enriched deterministic comparison of two config snapshots.

    Read-only — no audit event is emitted.
    Extends M15 comparison with per-field assumption impact classification
    across params, assumptions, portfolio, and risk/constraints sections.
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

    result = compare_config_snapshots_enriched(snap_a, snap_b)

    def _to_field_changes(changes: list[dict]) -> list[ConfigFieldChange]:
        return [ConfigFieldChange(**c) for c in changes]

    def _to_diff_section(section: dict) -> ConfigDiffSection:
        return ConfigDiffSection(
            changes=_to_field_changes(section["changes"]),
            unchanged_count=section["unchanged_count"],
            added_count=section["added_count"],
            removed_count=section["removed_count"],
            changed_count=section["changed_count"],
        )

    return ConfigSnapshotComparisonV2Response(
        snapshot_a_id=snap_a.id,
        snapshot_b_id=snap_b.id,
        snapshot_a_label=result["snapshot_a_label"],
        snapshot_b_label=result["snapshot_b_label"],
        is_same_config=result["is_same_config"],
        total_changes=result["total_changes"],
        params_diff=_to_diff_section(result["params_diff"]),
        assumptions_diff=_to_diff_section(result["assumptions_diff"]),
        portfolio_diff=_to_diff_section(result["portfolio_diff"]),
        risk_diff=_to_diff_section(result["risk_diff"]),
        all_changes=_to_field_changes(result["all_changes"]),
        weakening_changes=_to_field_changes(result["weakening_changes"]),
        positive_changes=_to_field_changes(result["positive_changes"]),
        review_changes=_to_field_changes(result["review_changes"]),
        highlighted_changes=result["highlighted_changes"],
        suggested_checks=result["suggested_checks"],
        deterministic_explanation=result["deterministic_explanation"],
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

    # M39: Compute and store universe coverage analysis fields (non-blocking).
    try:
        from app.services.universe_coverage import compute_universe_coverage_analysis
        result = compute_universe_coverage_analysis(snapshot.id, db)
        snapshot.coverage_analysis_json = result["coverage_analysis"]
        snapshot.symbol_quality_json = result["symbol_quality"]
        snapshot.universe_delta_json = result["universe_delta"]
        snapshot.universe_quality_summary_json = result["universe_quality_summary"]
        db.commit()
        db.refresh(snapshot)
    except Exception:
        pass

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
# M39: GET /api/universe-snapshots/{snapshot_id}/coverage-analysis
# NOTE: registered BEFORE the detail route so the literal "/coverage-analysis"
# segment is matched before any {snapshot_id} handler.
# ---------------------------------------------------------------------------

@router.get(
    "/universe-snapshots/{snapshot_id}/coverage-analysis",
)
def get_universe_coverage_analysis(
    snapshot_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Return universe coverage analysis for a universe snapshot.

    Always recomputes the delta (for freshness).
    Uses stored fields for other sections if available, or recomputes.
    Returns 404 if the snapshot does not exist.
    """
    from datetime import timezone as _tz
    from app.schemas.universe_coverage import (
        UniverseCoverageAnalysisRead,
        UniverseCoverageAnalysisResponse,
        UniverseDeltaRead,
        UniverseMetadataBreakdownRead,
        UniverseQualitySummaryRead,
        UniverseSymbolQualityRead,
    )
    from app.services.universe_coverage import (
        compute_metadata_breakdown,
        compute_symbol_quality,
        compute_universe_coverage_analysis,
        compute_universe_delta,
        compute_universe_quality_summary,
    )

    snapshot = (
        db.query(UniverseSnapshot)
        .filter(UniverseSnapshot.id == snapshot_id)
        .first()
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Universe snapshot not found")

    warnings: list[str] = []

    # Always recompute delta and run linkage for freshness.
    delta_data = compute_universe_delta(snapshot, db)

    from app.services.universe_coverage import compute_run_linkage
    run_link_data = compute_run_linkage(snapshot, db)

    # Use stored fields for other sections if available, else recompute.
    sym_data = snapshot.symbol_quality_json
    summary_data = snapshot.universe_quality_summary_json

    if sym_data is None:
        try:
            sym_data = compute_symbol_quality(snapshot.symbols_json or [])
        except Exception as exc:
            warnings.append(f"Symbol quality computation failed: {exc}")
            sym_data = []

    meta_data: dict | None = None
    try:
        meta_data = compute_metadata_breakdown(snapshot)
    except Exception as exc:
        warnings.append(f"Metadata breakdown computation failed: {exc}")
        meta_data = {
            "has_symbol_metadata": False,
            "metadata_coverage_rate": 0.0,
            "missing_metadata_symbols": len(snapshot.symbols_json or []),
            "by_sector": {},
            "by_country": {},
            "by_exchange": {},
            "by_liquidity_bucket": {},
            "warnings": [str(exc)],
        }

    if summary_data is None:
        try:
            summary_data = compute_universe_quality_summary(
                snapshot.symbols_json or [], sym_data, delta_data, meta_data
            )
        except Exception as exc:
            warnings.append(f"Quality summary computation failed: {exc}")
            summary_data = {
                "symbol_count": snapshot.symbol_count,
                "unique_symbol_count": snapshot.symbol_count,
                "duplicate_symbol_count": 0,
                "invalid_symbol_count": 0,
                "clean_symbol_count": snapshot.symbol_count,
                "review_symbol_count": 0,
                "weak_symbol_count": 0,
                "coverage_status": "unknown",
                "suggested_checks": [],
            }

    # Always merge fresh run linkage into coverage_analysis for freshness.
    cov_data = {**(snapshot.coverage_analysis_json or {}), **summary_data, **run_link_data}

    now = datetime.now(_tz.utc)

    return UniverseCoverageAnalysisResponse(
        snapshot_id=str(snapshot.id),
        strategy_id=str(snapshot.strategy_id),
        label=snapshot.label,
        universe_hash=snapshot.universe_hash,
        symbol_count=snapshot.symbol_count,
        generated_at=now,
        coverage_analysis=UniverseCoverageAnalysisRead.model_validate(cov_data),
        symbol_quality=[
            UniverseSymbolQualityRead.model_validate(s) for s in (sym_data or [])
        ],
        metadata_breakdown=UniverseMetadataBreakdownRead.model_validate(meta_data),
        universe_delta=UniverseDeltaRead.model_validate(delta_data),
        quality_summary=UniverseQualitySummaryRead.model_validate(summary_data),
        warnings=warnings,
    )


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

    # M38: Compute and store signal quality drilldown fields (non-blocking).
    try:
        from app.services.signal_quality_drilldown import compute_signal_quality_drilldown
        drilldown = compute_signal_quality_drilldown(snapshot)
        snapshot.signal_distribution_json = drilldown["signal_distribution"]
        snapshot.symbol_quality_json = drilldown["symbol_quality"]
        snapshot.signal_row_quality_json = drilldown["row_quality"]
        snapshot.signal_quality_summary_json = drilldown["quality_summary"]
        db.flush()
        db.commit()
        db.refresh(snapshot)
    except Exception:
        pass

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
# M38: GET /api/signal-snapshots/{snapshot_id}/quality-drilldown
# NOTE: registered BEFORE the detail route so the literal "/quality-drilldown"
# segment is matched before any {snapshot_id} handler.
# ---------------------------------------------------------------------------

@router.get(
    "/signal-snapshots/{snapshot_id}/quality-drilldown",
    response_model=SignalQualityDrilldownResponse,
)
def get_signal_quality_drilldown(
    snapshot_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> SignalQualityDrilldownResponse:
    """Return signal quality drilldown for a signal snapshot.

    Uses stored drilldown JSON fields if available; computes on-the-fly otherwise.
    Returns 404 if the snapshot does not exist.
    """
    from datetime import timezone as _tz

    snapshot = (
        db.query(SignalSnapshot)
        .filter(SignalSnapshot.id == snapshot_id)
        .first()
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Signal snapshot not found")

    warnings: list[str] = []

    # Prefer stored fields; compute on the fly if null.
    dist_data = snapshot.signal_distribution_json
    sym_data = snapshot.symbol_quality_json
    row_data = snapshot.signal_row_quality_json
    summary_data = snapshot.signal_quality_summary_json

    if dist_data is None or sym_data is None or row_data is None or summary_data is None:
        if snapshot.rows_json:
            try:
                from app.services.signal_quality_drilldown import compute_signal_quality_drilldown
                drilldown = compute_signal_quality_drilldown(snapshot)
                dist_data = drilldown["signal_distribution"]
                sym_data = drilldown["symbol_quality"]
                row_data = drilldown["row_quality"]
                summary_data = drilldown["quality_summary"]
            except Exception as exc:
                warnings.append(f"Drilldown computation failed: {exc}")
        else:
            warnings.append("No rows_json available; drilldown data is empty")

    # Build timestamp coverage from stored or compute.
    ts_cov_data: dict = {}
    if snapshot.rows_json:
        try:
            from app.services.signal_quality_drilldown import compute_timestamp_coverage
            ts_cov_data = compute_timestamp_coverage(snapshot.rows_json)
        except Exception:
            ts_cov_data = {}

    # Fall back to empty structures.
    if dist_data is None:
        dist_data = {
            "signal_column": "signal",
            "value_count": 0,
            "missing_count": 0,
            "non_numeric_count": 0,
            "mean_value": None,
            "median_value": None,
            "min_value": None,
            "max_value": None,
            "stddev_value": None,
            "zero_count": 0,
            "positive_count": 0,
            "negative_count": 0,
            "unique_value_count": 0,
            "outlier_count": 0,
            "extreme_positive_count": 0,
            "extreme_negative_count": 0,
            "distribution_status": "unusable",
            "issues": ["No data available"],
        }
    if sym_data is None:
        sym_data = []
    if row_data is None:
        row_data = {
            "missing_signal_rows": [],
            "non_numeric_signal_rows": [],
            "duplicate_symbol_timestamp_rows": [],
            "outlier_signal_rows": [],
            "invalid_timestamp_rows": [],
        }
    if summary_data is None:
        summary_data = {
            "total_rows": snapshot.row_count,
            "symbol_count": snapshot.symbol_count,
            "signal_value_count": 0,
            "missing_signal_count": 0,
            "non_numeric_signal_count": 0,
            "outlier_count": 0,
            "duplicate_symbol_timestamp_count": 0,
            "invalid_timestamp_count": 0,
            "clean_symbol_count": 0,
            "review_symbol_count": 0,
            "weak_symbol_count": 0,
            "unusable_symbol_count": 0,
            "worst_symbols": [],
            "suggested_checks": [],
        }
    if not ts_cov_data:
        ts_cov_data = {
            "total_timestamp_count": 0,
            "duplicate_symbol_timestamp_count": 0,
            "invalid_timestamp_count": 0,
            "min_timestamp": snapshot.min_timestamp,
            "max_timestamp": snapshot.max_timestamp,
            "symbols_with_gaps_count": None,
            "timestamp_status": "clean",
        }

    now = datetime.now(_tz.utc)

    return SignalQualityDrilldownResponse(
        snapshot_id=str(snapshot.id),
        strategy_id=str(snapshot.strategy_id),
        label=snapshot.label,
        signal_name=snapshot.signal_name,
        quality_score=snapshot.quality_score,
        row_count=snapshot.row_count,
        symbol_count=snapshot.symbol_count,
        generated_at=now,
        signal_distribution=SignalDistributionRead.model_validate(dist_data),
        symbol_quality=[SymbolSignalQualityRead.model_validate(s) for s in sym_data],
        timestamp_coverage=SignalTimestampCoverageRead.model_validate(ts_cov_data),
        row_quality=SignalRowQualitySamplesRead(
            missing_signal_rows=[
                SignalRowQualitySampleRead.model_validate(r)
                for r in row_data.get("missing_signal_rows", [])
            ],
            non_numeric_signal_rows=[
                SignalRowQualitySampleRead.model_validate(r)
                for r in row_data.get("non_numeric_signal_rows", [])
            ],
            duplicate_symbol_timestamp_rows=[
                SignalRowQualitySampleRead.model_validate(r)
                for r in row_data.get("duplicate_symbol_timestamp_rows", [])
            ],
            outlier_signal_rows=[
                SignalRowQualitySampleRead.model_validate(r)
                for r in row_data.get("outlier_signal_rows", [])
            ],
            invalid_timestamp_rows=[
                SignalRowQualitySampleRead.model_validate(r)
                for r in row_data.get("invalid_timestamp_rows", [])
            ],
        ),
        quality_summary=SignalQualitySummaryRead.model_validate(summary_data),
        warnings=warnings,
    )


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


# ---------------------------------------------------------------------------
# M30: GET /api/strategies/{strategy_id}/evidence-trends
# ---------------------------------------------------------------------------


@router.get(
    "/strategies/{strategy_id}/evidence-trends",
    response_model=StrategyEvidenceTrendsResponse,
)
def get_strategy_evidence_trends_endpoint(
    strategy_id: uuid.UUID,
    limit_per_series: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> StrategyEvidenceTrendsResponse:
    """Return longitudinal evidence trend data for a strategy.

    Covers four series: reliability score, data health, backtest trust,
    and signal quality.  No timeline event is created — read-only.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    try:
        result = _get_evidence_trends(strategy_id, db, limit_per_series=limit_per_series)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    def _point(p: TrendPointData) -> TrendPoint:
        return TrendPoint(
            id=p.id,
            label=p.label,
            value=p.value,
            status=p.status,
            timestamp=p.timestamp,
        )

    def _trend(t: TrendSummaryData) -> TrendSummary:
        return TrendSummary(
            points=[_point(p) for p in t.points],
            latest_value=t.latest_value,
            previous_value=t.previous_value,
            delta=t.delta,
            direction=t.direction,
            point_count=t.point_count,
            min_value=t.min_value,
            max_value=t.max_value,
            average_value=t.average_value,
            latest_label=t.latest_label,
            latest_at=t.latest_at,
            deterministic_summary=t.deterministic_summary,
        )

    cov = None
    if result.coverage_current:
        cov = EvidenceCoverageCurrentSummary(
            evidence_coverage_score=result.coverage_current.evidence_coverage_score,
            missing_count=result.coverage_current.missing_count,
            review_count=result.coverage_current.review_count,
            complete_count=result.coverage_current.complete_count,
        )

    return StrategyEvidenceTrendsResponse(
        strategy_id=result.strategy_id,
        strategy_name=result.strategy_name,
        generated_at=result.generated_at,
        reliability_trend=_trend(result.reliability_trend),
        data_health_trend=_trend(result.data_health_trend),
        backtest_trust_trend=_trend(result.backtest_trust_trend),
        signal_quality_trend=_trend(result.signal_quality_trend),
        coverage_current=cov,
        overall_summary=result.overall_summary,
        suggested_checks=result.suggested_checks,
    )


# ---------------------------------------------------------------------------
# M31: GET /api/strategies/{strategy_id}/export
# ---------------------------------------------------------------------------


@router.get(
    "/strategies/{strategy_id}/export",
    response_model=StrategyExportResponse,
)
def export_strategy_evidence(
    strategy_id: uuid.UUID,
    format: str = Query(default="json", description="Export format: json or markdown"),
    include_raw_json: bool = Query(default=False),
    limit_recent_runs: int = Query(default=10, ge=1, le=50),
    limit_timeline_events: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> StrategyExportResponse:
    """Return a full deterministic evidence export for a strategy.

    Supports ``format=json`` (default) and ``format=markdown``.
    Set ``include_raw_json=true`` to include the full raw evidence dict.
    No side effects: this endpoint does not write to the database.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if format not in ("json", "markdown"):
        raise HTTPException(status_code=400, detail="format must be 'json' or 'markdown'")
    try:
        result: StrategyExportData = generate_strategy_export(
            strategy_id,
            db,
            format=format,
            include_raw_json=include_raw_json,
            limit_recent_runs=limit_recent_runs,
            limit_timeline_events=limit_timeline_events,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StrategyExportResponse(
        format=result.format,
        filename=result.metadata.filename,
        metadata=StrategyExportMetadata(
            export_id=result.metadata.export_id,
            strategy_id=result.metadata.strategy_id,
            strategy_name=result.metadata.strategy_name,
            strategy_slug=result.metadata.strategy_slug,
            generated_at=result.metadata.generated_at,
            format=result.metadata.format,
            filename=result.metadata.filename,
            milestone=result.metadata.milestone,
            note=result.metadata.note,
        ),
        sections=[
            StrategyExportSection(
                section_key=s.section_key,
                title=s.title,
                summary=s.summary,
                severity=s.severity,
                evidence_json=s.evidence_json,
            )
            for s in result.sections
        ],
        content=result.content,
        raw_evidence=result.raw_evidence,
    )


# ---------------------------------------------------------------------------
# M35: GET /api/strategies/{strategy_id}/version-lineage
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/version-lineage",
    response_model=StrategyVersionLineageResponse,
)
def get_strategy_version_lineage_endpoint(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StrategyVersionLineageResponse:
    """Return full version lineage for a strategy, including per-version evidence
    coverage scores, transitions between versions, and summary statistics."""
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    try:
        result: StrategyVersionLineageData = get_strategy_version_lineage(strategy_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    def _version_schema(v: StrategyVersionLineageItemData) -> StrategyVersionLineageItem:
        return StrategyVersionLineageItem(
            version_id=v.version_id,
            version_label=v.version_label,
            git_commit=v.git_commit,
            branch_name=v.branch_name,
            code_path=v.code_path,
            signal_name=v.signal_name,
            signal_description=v.signal_description,
            created_at=v.created_at,
            updated_at=v.updated_at,
            run_count=v.run_count,
            backtest_run_count=v.backtest_run_count,
            research_run_count=v.research_run_count,
            paper_run_count=v.paper_run_count,
            live_run_count=v.live_run_count,
            config_snapshot_count=v.config_snapshot_count,
            universe_snapshot_count=v.universe_snapshot_count,
            signal_snapshot_count=v.signal_snapshot_count,
            dataset_linked_run_count=v.dataset_linked_run_count,
            backtest_audit_count=v.backtest_audit_count,
            latest_run_at=v.latest_run_at,
            latest_config_snapshot_label=v.latest_config_snapshot_label,
            latest_universe_snapshot_label=v.latest_universe_snapshot_label,
            latest_signal_snapshot_label=v.latest_signal_snapshot_label,
            latest_backtest_trust_score=v.latest_backtest_trust_score,
            latest_data_health_score=v.latest_data_health_score,
            latest_signal_quality_score=v.latest_signal_quality_score,
            has_config=v.has_config,
            has_universe=v.has_universe,
            has_signal=v.has_signal,
            has_runs=v.has_runs,
            has_dataset_linked_runs=v.has_dataset_linked_runs,
            has_backtest_audit=v.has_backtest_audit,
            version_evidence_score=v.version_evidence_score,
            lineage_status=v.lineage_status,
            suggested_checks=v.suggested_checks,
        )

    def _transition_schema(t: StrategyVersionTransitionData) -> StrategyVersionTransition:
        return StrategyVersionTransition(
            from_version_label=t.from_version_label,
            to_version_label=t.to_version_label,
            created_at_delta_days=t.created_at_delta_days,
            git_commit_changed=t.git_commit_changed,
            branch_changed=t.branch_changed,
            signal_name_changed=t.signal_name_changed,
            config_hash_changed=t.config_hash_changed,
            universe_hash_changed=t.universe_hash_changed,
            signal_hash_changed=t.signal_hash_changed,
        )

    s = result.summary
    return StrategyVersionLineageResponse(
        summary=StrategyVersionLineageSummary(
            strategy_id=s.strategy_id,
            strategy_name=s.strategy_name,
            version_count=s.version_count,
            latest_version_label=s.latest_version_label,
            most_instrumented_version_id=s.most_instrumented_version_id,
            least_instrumented_version_id=s.least_instrumented_version_id,
            average_version_evidence_score=s.average_version_evidence_score,
            versions_missing_config=s.versions_missing_config,
            versions_missing_signal=s.versions_missing_signal,
            versions_missing_universe=s.versions_missing_universe,
            versions_without_runs=s.versions_without_runs,
            deterministic_summary=s.deterministic_summary,
            generated_at=s.generated_at,
        ),
        versions=[_version_schema(v) for v in result.versions],
        transitions=[_transition_schema(t) for t in result.transitions],
    )


# ---------------------------------------------------------------------------
# M41: GET /api/strategies/{strategy_id}/assumption-health
# ---------------------------------------------------------------------------


@router.get(
    "/strategies/{strategy_id}/assumption-health",
    response_model=StrategyAssumptionHealthResponse,
)
def get_strategy_assumption_health(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StrategyAssumptionHealthResponse:
    """Return a deterministic assumption health scorecard for a strategy.

    Evaluates transaction costs, slippage, fill realism, borrow/shorting,
    liquidity/capacity, risk controls, and data evidence linkage.
    Computed on read — not persisted.  No AI, no live market data.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    try:
        result = compute_assumption_health(strategy_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Build category scorecards
    cats = [
        AssumptionCategoryScorecard(
            category_key=c["category_key"],
            title=c["title"],
            status=c["status"],
            score=c["score"],
            evidence_count=c["evidence_count"],
            positive_evidence=c["positive_evidence"],
            review_items=c["review_items"],
            weakening_changes=c["weakening_changes"],
            suggested_checks=c["suggested_checks"],
        )
        for c in result["category_scorecards"]
    ]

    # Config diff summary (may have 'warning' key for <2 snapshots)
    cds_raw = result.get("latest_config_diff_summary") or {}
    config_diff_summary = ConfigDiffAssumptionSummary(
        snapshot_a_label=cds_raw.get("snapshot_a_label"),
        snapshot_b_label=cds_raw.get("snapshot_b_label"),
        total_changes=cds_raw.get("total_changes", 0),
        positive_change_count=cds_raw.get("positive_change_count", 0),
        weakening_change_count=cds_raw.get("weakening_change_count", 0),
        review_change_count=cds_raw.get("review_change_count", 0),
        key_assumption_changes=cds_raw.get("key_assumption_changes", []),
        warning=cds_raw.get("warning"),
    )

    # Backtest audit summary (optional)
    bas_raw = result.get("latest_backtest_audit_summary")
    backtest_audit_summary = None
    if bas_raw:
        backtest_audit_summary = BacktestAuditAssumptionSummary(
            backtest_audit_id=bas_raw["backtest_audit_id"],
            trust_score=bas_raw["trust_score"],
            overall_status=bas_raw["overall_status"],
            cost_fragility_level=bas_raw.get("cost_fragility_level"),
            fill_realism_level=bas_raw.get("fill_realism_level"),
            largest_penalty_category=bas_raw.get("largest_penalty_category"),
            top_improvement_checks=bas_raw.get("top_improvement_checks", []),
        )

    return StrategyAssumptionHealthResponse(
        strategy_id=result["strategy_id"],
        strategy_name=result["strategy_name"],
        status=result["status"],
        overall_assumption_score=result["overall_assumption_score"],
        generated_at=result["generated_at"],
        category_scorecards=cats,
        latest_config_diff_summary=config_diff_summary,
        latest_backtest_audit_summary=backtest_audit_summary,
        key_assumption_changes=result.get("key_assumption_changes", []),
        weakening_change_count=result.get("weakening_change_count", 0),
        positive_change_count=result.get("positive_change_count", 0),
        review_change_count=result.get("review_change_count", 0),
        suggested_checks=result.get("suggested_checks", []),
        deterministic_summary=result["deterministic_summary"],
    )


# ---------------------------------------------------------------------------
# M47: GET /api/strategies/{strategy_id}/drift
# ---------------------------------------------------------------------------


@router.get(
    "/strategies/{strategy_id}/drift",
    response_model=StrategyDriftResponse,
)
def get_strategy_drift(
    strategy_id: uuid.UUID,
    mode: str = Query(
        default="latest_stage_pair",
        description="latest_stage_pair | selected_runs | full_stage_path",
    ),
    baseline_run_id: uuid.UUID | None = Query(default=None),
    comparison_run_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> StrategyDriftResponse:
    """Return drift analysis between two strategy runs.

    Deterministic — no AI, no causal claims, no investment advice.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    valid_modes = ("latest_stage_pair", "selected_runs", "full_stage_path")
    if mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {mode!r}")

    try:
        result: StrategyDriftData = compute_strategy_drift(
            strategy_id,
            db,
            mode=mode,
            baseline_run_id=baseline_run_id,
            comparison_run_id=comparison_run_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    def _run_schema(r: StrategyDriftRunSummaryData | None) -> StrategyDriftRunSummary | None:
        if r is None:
            return None
        return StrategyDriftRunSummary(
            run_id=r.run_id,
            run_name=r.run_name,
            run_type=r.run_type,
            status=r.status,
            created_at=r.created_at,
            completed_at=r.completed_at,
            metrics_json=r.metrics_json,
            assumptions_json=r.assumptions_json,
            strategy_version_label=r.strategy_version_label,
            dataset_health=r.dataset_health,
            signal_quality=r.signal_quality,
            universe_symbol_count=r.universe_symbol_count,
            backtest_trust=r.backtest_trust,
            run_health_label=r.run_health_label,
        )

    return StrategyDriftResponse(
        strategy_id=result.strategy_id,
        strategy_name=result.strategy_name,
        mode=result.mode,
        generated_at=result.generated_at,
        drift_score=result.drift_score,
        drift_status=result.drift_status,
        baseline_run=_run_schema(result.baseline_run),
        comparison_run=_run_schema(result.comparison_run),
        stage_path=result.stage_path,
        metric_drifts=[
            MetricDriftItem(
                metric=m.metric,
                baseline_value=m.baseline_value,
                comparison_value=m.comparison_value,
                absolute_delta=m.absolute_delta,
                percent_delta=m.percent_delta,
                direction=m.direction,
                severity=m.severity,
            )
            for m in result.metric_drifts
        ],
        evidence_drifts=[
            EvidenceDriftItem(
                evidence_type=e.evidence_type,
                baseline_value=e.baseline_value,
                comparison_value=e.comparison_value,
                delta=e.delta,
                severity=e.severity,
                explanation=e.explanation,
            )
            for e in result.evidence_drifts
        ],
        assumption_drifts=[
            AssumptionDriftItem(
                key_path=a.key_path,
                old_value=a.old_value,
                new_value=a.new_value,
                change_type=a.change_type,
                impact_level=a.impact_level,
                suggested_check=a.suggested_check,
            )
            for a in result.assumption_drifts
        ],
        trust_drifts=[
            TrustDriftItem(
                dimension=t.dimension,
                baseline_value=t.baseline_value,
                comparison_value=t.comparison_value,
                delta=t.delta,
                severity=t.severity,
                explanation=t.explanation,
            )
            for t in result.trust_drifts
        ],
        highlighted_drifts=result.highlighted_drifts,
        suggested_checks=result.suggested_checks,
        deterministic_summary=result.deterministic_summary,
    )


# ---------------------------------------------------------------------------
# M48: GET /api/strategies/{strategy_id}/freshness
# ---------------------------------------------------------------------------

from app.schemas.evidence_freshness import (  # noqa: E402
    EvidenceFreshnessItem,
    StrategyEvidenceFreshnessResponse,
)
from app.services.evidence_freshness import (  # noqa: E402
    EvidenceFreshnessItemData,
    StrategyEvidenceFreshnessData,
    compute_evidence_freshness,
)


@router.get(
    "/strategies/{strategy_id}/freshness",
    response_model=StrategyEvidenceFreshnessResponse,
)
def get_strategy_freshness(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StrategyEvidenceFreshnessResponse:
    """Return deterministic evidence freshness scorecard for a strategy.

    Checks 10 evidence types and returns freshness status, counts, and
    suggested refresh actions. Read-only — no AuditTimelineEvent created.
    Language is hedged: no investment advice, no trading recommendations.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    try:
        result = compute_evidence_freshness(strategy_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return StrategyEvidenceFreshnessResponse(
        strategy_id=result.strategy_id,
        strategy_name=result.strategy_name,
        generated_at=result.generated_at,
        overall_freshness_score=result.overall_freshness_score,
        freshness_status=result.freshness_status,
        stale_count=result.stale_count,
        missing_count=result.missing_count,
        aging_count=result.aging_count,
        fresh_count=result.fresh_count,
        evidence_items=[
            EvidenceFreshnessItem(
                evidence_type=i.evidence_type,
                label=i.label,
                latest_at=i.latest_at,
                days_since_latest=i.days_since_latest,
                count=i.count,
                status=i.status,
                threshold_days=i.threshold_days,
                severity=i.severity,
                summary=i.summary,
                suggested_check=i.suggested_check,
                latest_object_id=i.latest_object_id,
                latest_object_label=i.latest_object_label,
            )
            for i in result.evidence_items
        ],
        oldest_evidence_type=result.oldest_evidence_type,
        freshest_evidence_type=result.freshest_evidence_type,
        suggested_refresh_order=result.suggested_refresh_order,
        deterministic_summary=result.deterministic_summary,
    )


# ---------------------------------------------------------------------------
# M49: GET /api/strategies/{strategy_id}/readiness
# ---------------------------------------------------------------------------


@router.get(
    "/strategies/{strategy_id}/readiness",
    response_model=StrategyReadinessResponse,
    tags=["strategies"],
)
def get_strategy_readiness(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StrategyReadinessResponse:
    """Return a multi-dimensional readiness scorecard for a strategy.

    Deterministic — no AI, no live market data.
    Read-only — no AuditTimelineEvent created.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    try:
        result = compute_strategy_readiness(strategy_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return StrategyReadinessResponse(
        strategy_id=result.strategy_id,
        strategy_name=result.strategy_name,
        generated_at=result.generated_at,
        readiness_score=result.readiness_score,
        readiness_verdict=result.readiness_verdict,
        verdict_label=result.verdict_label,
        verdict_summary=result.verdict_summary,
        deterministic_summary=result.deterministic_summary,
        dimension_scorecards=[
            StrategyReadinessDimension(
                dimension_key=d.dimension_key,
                title=d.title,
                score=d.score,
                status=d.status,
                evidence_summary=d.evidence_summary,
                blockers=d.blockers,
                warnings=d.warnings,
                suggested_actions=d.suggested_actions,
            )
            for d in result.dimension_scorecards
        ],
        blockers=result.blockers,
        review_items=result.review_items,
        suggested_next_actions=result.suggested_next_actions,
        progression_path=StrategyProgressionPath(
            current_stage=result.progression_path.current_stage,
            next_recommended_stage=result.progression_path.next_recommended_stage,
            required_before_next_stage=result.progression_path.required_before_next_stage,
        ),
    )


# ---------------------------------------------------------------------------
# M50: GET /api/strategies/{strategy_id}/shadow-monitor
# ---------------------------------------------------------------------------

from app.schemas.shadow_production import (  # noqa: E402
    ShadowRunSummary,
    ShadowMetricComparison,
    ShadowEvidenceComparison,
    ShadowAssumptionChange,
    ShadowTrustComparison,
    ShadowProductionCheck,
    StrategyShadowMonitorResponse,
)
from app.services.shadow_production import (  # noqa: E402
    compute_shadow_production_monitor,
    StrategyShadowMonitorData,
)


@router.get(
    "/strategies/{strategy_id}/shadow-monitor",
    response_model=StrategyShadowMonitorResponse,
    tags=["strategies"],
)
def get_shadow_monitor(
    strategy_id: uuid.UUID,
    mode: str = Query(default="latest"),
    baseline_run_id: uuid.UUID | None = Query(default=None),
    shadow_run_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> StrategyShadowMonitorResponse:
    """Return a shadow production monitor for a strategy.

    Compares a baseline (research/backtest) run against a shadow (paper/live)
    run to assess shadow stability.

    Deterministic — no AI, no live market data.
    Read-only — no AuditTimelineEvent created.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    if mode not in ("latest", "selected"):
        raise HTTPException(status_code=400, detail="mode must be 'latest' or 'selected'")

    try:
        result = compute_shadow_production_monitor(
            strategy_id,
            db,
            mode=mode,
            baseline_run_id=baseline_run_id,
            shadow_run_id=shadow_run_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    def _run_schema(r: StrategyShadowMonitorData | None) -> ShadowRunSummary | None:
        if r is None:
            return None
        return ShadowRunSummary(
            run_id=r.run_id,
            run_name=r.run_name,
            run_type=r.run_type,
            status=r.status,
            created_at=r.created_at,
            completed_at=r.completed_at,
            strategy_version_label=r.strategy_version_label,
            dataset_health=r.dataset_health,
            signal_quality=r.signal_quality,
            backtest_trust=r.backtest_trust,
            universe_symbol_count=r.universe_symbol_count,
            metrics_json=r.metrics_json,
            assumptions_json=r.assumptions_json,
            run_health_label=r.run_health_label,
        )

    return StrategyShadowMonitorResponse(
        strategy_id=result.strategy_id,
        strategy_name=result.strategy_name,
        generated_at=result.generated_at,
        monitor_status=result.monitor_status,
        shadow_stability_score=result.shadow_stability_score,
        baseline_run=_run_schema(result.baseline_run),
        shadow_run=_run_schema(result.shadow_run),
        metric_comparisons=[
            ShadowMetricComparison(
                metric_key=m.metric,
                direction=m.direction,
                severity=m.severity,
                explanation=m.direction.replace("_", " "),
                baseline_value=m.baseline_value,
                comparison_value=m.comparison_value,
                absolute_delta=m.absolute_delta,
                percent_delta=m.percent_delta,
            )
            for m in result.metric_comparisons
        ],
        evidence_comparisons=[
            ShadowEvidenceComparison(
                evidence_type=e.evidence_type,
                severity=e.severity,
                explanation=e.explanation,
                baseline_value=e.baseline_value,
                comparison_value=e.comparison_value,
                delta=e.delta,
            )
            for e in result.evidence_comparisons
        ],
        assumption_changes=[
            ShadowAssumptionChange(
                key_path=a.key_path,
                change_type=a.change_type,
                impact_level=a.impact_level,
                old_value=a.old_value,
                new_value=a.new_value,
                impact_reason=None,
                suggested_check=a.suggested_check,
            )
            for a in result.assumption_changes
        ],
        trust_comparison=[
            ShadowTrustComparison(
                dimension=t.dimension,
                severity=t.severity,
                explanation=t.explanation,
                baseline_value=t.baseline_value,
                comparison_value=t.comparison_value,
                delta=t.delta,
            )
            for t in result.trust_comparison
        ],
        production_checks=[
            ShadowProductionCheck(
                check_key=c.check_key,
                title=c.title,
                passed=c.passed,
                severity=c.severity,
                evidence=c.evidence,
                suggested_action=c.suggested_action,
            )
            for c in result.production_checks
        ],
        highlighted_findings=result.highlighted_findings,
        blockers=result.blockers,
        suggested_actions=result.suggested_actions,
        deterministic_summary=result.deterministic_summary,
    )


# ---------------------------------------------------------------------------
# M51 — Promotion Gates
# ---------------------------------------------------------------------------


@router.get(
    "/strategies/{strategy_id}/promotion-gates",
    response_model=StrategyPromotionGateResponse,
)
def get_promotion_gates(
    strategy_id: uuid.UUID,
    target_stage: str = Query(
        ...,
        description=(
            "backtest_review | paper_candidate | "
            "shadow_production | production_candidate"
        ),
    ),
    db: Session = Depends(get_db),
):
    """Evaluate deterministic promotion gate checks for a strategy.

    Not trading approval — deterministic evidence gate result only.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    try:
        result = evaluate_promotion_gates(strategy_id, target_stage, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return StrategyPromotionGateResponse(
        strategy_id=result.strategy_id,
        strategy_name=result.strategy_name,
        generated_at=result.generated_at,
        current_stage=result.current_stage,
        target_stage=result.target_stage,
        stage_path=result.stage_path,
        promotion_verdict=result.promotion_verdict,
        gate_score=result.gate_score,
        gate_checks=[
            PromotionGateCheck(
                gate_key=c.gate_key,
                title=c.title,
                category=c.category,
                required=c.required,
                passed=c.passed,
                status=c.status,
                severity=c.severity,
                observed_value=c.observed_value,
                required_value=c.required_value,
                evidence_summary=c.evidence_summary,
                suggested_action=c.suggested_action,
            )
            for c in result.gate_checks
        ],
        required_pass_count=result.required_pass_count,
        required_fail_count=result.required_fail_count,
        recommended_pass_count=result.recommended_pass_count,
        recommended_fail_count=result.recommended_fail_count,
        blocker_count=result.blocker_count,
        review_count=result.review_count,
        blockers=result.blockers,
        warnings=result.warnings,
        suggested_actions=result.suggested_actions,
        deterministic_summary=result.deterministic_summary,
        note=result.note,
    )


# ---------------------------------------------------------------------------
# M52 — Evidence Graph
# ---------------------------------------------------------------------------

from app.schemas.evidence_graph import (  # noqa: E402
    EvidenceGraphNode,
    EvidenceGraphEdge,
    EvidenceBlastRadius,
    EvidenceGraphSummary,
    StrategyEvidenceGraphResponse,
)
from app.services.evidence_graph import (  # noqa: E402
    build_strategy_evidence_graph,
    StrategyEvidenceGraphData,
)


@router.get(
    "/strategies/{strategy_id}/evidence-graph",
    response_model=StrategyEvidenceGraphResponse,
)
def get_evidence_graph(
    strategy_id: uuid.UUID,
    focus_node_id: str | None = Query(default=None),
    focus_node_type: str | None = Query(default=None),
    include_timeline: bool = Query(default=True),
    include_computed: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """Build deterministic evidence graph for a strategy.

    Not investment advice — deterministic evidence graph only.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    try:
        result = build_strategy_evidence_graph(
            strategy_id,
            db,
            focus_node_id=focus_node_id,
            focus_node_type=focus_node_type,
            include_timeline=include_timeline,
            include_computed=include_computed,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    def _ns(n) -> EvidenceGraphNode:
        return EvidenceGraphNode(
            node_id=n.node_id,
            node_type=n.node_type,
            label=n.label,
            subtitle=n.subtitle,
            status=n.status,
            severity=n.severity,
            created_at=n.created_at,
            updated_at=n.updated_at,
            score=n.score,
            metadata_json=n.metadata_json,
            route_hint=n.route_hint,
        )

    def _es(e) -> EvidenceGraphEdge:
        return EvidenceGraphEdge(
            edge_id=e.edge_id,
            source_node_id=e.source_node_id,
            target_node_id=e.target_node_id,
            relationship=e.relationship,
            label=e.label,
            metadata_json=e.metadata_json,
        )

    br = None
    if result.blast_radius:
        b = result.blast_radius
        br = EvidenceBlastRadius(
            focus_node_id=b.focus_node_id,
            focus_node_type=b.focus_node_type,
            upstream_count=b.upstream_count,
            downstream_count=b.downstream_count,
            affected_run_count=b.affected_run_count,
            affected_report_count=b.affected_report_count,
            affected_alert_count=b.affected_alert_count,
            affected_audit_count=b.affected_audit_count,
            affected_readiness=b.affected_readiness,
            affected_shadow_monitor=b.affected_shadow_monitor,
            affected_promotion_gates=b.affected_promotion_gates,
            affected_nodes=[_ns(n) for n in b.affected_nodes],
            blast_radius_severity=b.blast_radius_severity,
        )

    s = result.summary
    return StrategyEvidenceGraphResponse(
        summary=EvidenceGraphSummary(
            strategy_id=s.strategy_id,
            strategy_name=s.strategy_name,
            generated_at=s.generated_at,
            node_count=s.node_count,
            edge_count=s.edge_count,
            weak_node_count=s.weak_node_count,
            missing_node_count=s.missing_node_count,
            high_critical_alert_node_count=s.high_critical_alert_node_count,
            connected_run_count=s.connected_run_count,
            orphan_evidence_count=s.orphan_evidence_count,
            graph_status=s.graph_status,
            deterministic_summary=s.deterministic_summary,
            suggested_checks=s.suggested_checks,
        ),
        nodes=[_ns(n) for n in result.nodes],
        edges=[_es(e) for e in result.edges],
        blast_radius=br,
    )


# ---------------------------------------------------------------------------
# M58 — Run Replay Pack
# ---------------------------------------------------------------------------

from app.schemas.run_replay import (  # noqa: E402
    RunReplayMetadata,
    RunReplayMissingEvidence,
    RunReplayResponse,
    RunReplaySection,
)
from app.services.run_replay import generate_run_replay_pack  # noqa: E402


@router.get(
    "/strategies/{strategy_id}/runs/{run_id}/replay-pack",
    response_model=RunReplayResponse,
)
def get_run_replay_pack(
    strategy_id: uuid.UUID,
    run_id: uuid.UUID,
    format: str = Query(default="json"),
    include_raw_json: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Generate a deterministic run replay pack for a single strategy run.

    Read-only — no DB writes, no AuditTimelineEvent created.
    Not investment advice.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    try:
        data = generate_run_replay_pack(
            db,
            strategy_id,
            run_id,
            format=format,
            include_raw_json=include_raw_json,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    return RunReplayResponse(
        metadata=RunReplayMetadata(
            replay_id=data.replay_id,
            generated_at=data.generated_at,
            format=data.format,
            strategy_id=data.strategy_id,
            run_id=data.run_id,
            filename=data.filename,
            deterministic_note=data.deterministic_note,
            no_execution_replay_note=data.no_execution_replay_note,
        ),
        replay_status=data.replay_status,
        replay_completeness_score=data.replay_completeness_score,
        sections=[
            RunReplaySection(
                section_key=s.section_key,
                title=s.title,
                summary=s.summary,
                severity=s.severity,
                evidence_json=s.evidence_json,
            )
            for s in data.sections
        ],
        missing_evidence=[
            RunReplayMissingEvidence(
                evidence_type=m.evidence_type,
                severity=m.severity,
                suggested_action=m.suggested_action,
            )
            for m in data.missing_evidence
        ],
        suggested_review_checks=data.suggested_review_checks,
        content=data.content,
        raw_evidence=data.raw_evidence,
    )


# ---------------------------------------------------------------------------
# M61: GET /api/strategies/{strategy_id}/robustness
# ---------------------------------------------------------------------------

from app.schemas.strategy_robustness import (  # noqa: E402
    RobustnessDimensionScorecard,
    RobustnessFragilitySignal,
    StrategyRobustnessResponse,
)
from app.services.strategy_robustness import (  # noqa: E402
    RobustnessFragilitySignalData,
    compute_strategy_robustness,
)


# M62: GET /api/strategies/{strategy_id}/progression-freeze
# ---------------------------------------------------------------------------

from app.schemas.progression_freeze import (  # noqa: E402
    ProgressionFreezeReason,
    ProgressionUnfreezeRequirement,
    ProgressionSubsystemStatus,
    ProgressionStageContext,
    StrategyProgressionFreezeResponse,
)
from app.services.progression_freeze import (  # noqa: E402
    compute_progression_freeze_recommendation,
    VALID_TARGET_STAGES,
)


@router.get(
    "/strategies/{strategy_id}/progression-freeze",
    response_model=StrategyProgressionFreezeResponse,
    tags=["strategies"],
)
def get_strategy_progression_freeze(
    strategy_id: uuid.UUID,
    target_stage: str | None = None,
    db: Session = Depends(get_db),
) -> StrategyProgressionFreezeResponse:
    """Return a deterministic progression freeze recommendation for a strategy.

    Deterministic — no AI, no live market data.
    Read-only — no AuditTimelineEvent created.
    Not investment advice or trading approval.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    if target_stage is not None and target_stage not in VALID_TARGET_STAGES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid target_stage '{target_stage}'. "
                f"Must be one of: {', '.join(VALID_TARGET_STAGES)}"
            ),
        )

    result = compute_progression_freeze_recommendation(db, strategy_id, target_stage)

    return StrategyProgressionFreezeResponse(
        strategy_id=result.strategy_id,
        strategy_name=result.strategy_name,
        generated_at=result.generated_at,
        target_stage=result.target_stage,
        current_stage=result.current_stage,
        recommendation=result.recommendation,
        recommendation_label=result.recommendation_label,
        freeze_risk_score=result.freeze_risk_score,
        deterministic_summary=result.deterministic_summary,
        freeze_reasons=[
            ProgressionFreezeReason(
                reason_key=r.reason_key,
                title=r.title,
                category=r.category,
                severity=r.severity,
                status=r.status,
                evidence_summary=r.evidence_summary,
                source_label=r.source_label,
                source_id=r.source_id,
                suggested_resolution=r.suggested_resolution,
                required_to_unfreeze=r.required_to_unfreeze,
            )
            for r in result.freeze_reasons
        ],
        unfreeze_requirements=[
            ProgressionUnfreezeRequirement(
                requirement_key=u.requirement_key,
                title=u.title,
                priority=u.priority,
                required=u.required,
                current_status=u.current_status,
                target_status=u.target_status,
                suggested_action=u.suggested_action,
                endpoint_hint=u.endpoint_hint,
            )
            for u in result.unfreeze_requirements
        ],
        blocking_reason_count=result.blocking_reason_count,
        review_reason_count=result.review_reason_count,
        watch_reason_count=result.watch_reason_count,
        missing_evidence_count=result.missing_evidence_count,
        subsystem_statuses=[
            ProgressionSubsystemStatus(
                subsystem=s.subsystem,
                status=s.status,
                summary=s.summary,
                score=s.score,
            )
            for s in result.subsystem_statuses
        ],
        stage_context=ProgressionStageContext(
            current_stage=result.stage_context.current_stage,
            target_stage=result.stage_context.target_stage,
            next_recommended_stage=result.stage_context.next_recommended_stage,
            stage_path=result.stage_context.stage_path,
        ),
        note=result.note,
    )


@router.get(
    "/strategies/{strategy_id}/robustness",
    response_model=StrategyRobustnessResponse,
    tags=["strategies"],
)
def get_strategy_robustness(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StrategyRobustnessResponse:
    """Return a multi-dimensional robustness score for a strategy.

    Deterministic — no AI, no live market data.
    Read-only — no AuditTimelineEvent created.
    Not investment advice.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    result = compute_strategy_robustness(db, strategy_id)

    return StrategyRobustnessResponse(
        strategy_id=result.strategy_id,
        strategy_name=result.strategy_name,
        generated_at=result.generated_at,
        robustness_score=result.robustness_score,
        robustness_status=result.robustness_status,
        robustness_verdict=result.robustness_verdict,
        verdict_label=result.verdict_label,
        deterministic_summary=result.deterministic_summary,
        dimension_scorecards=[
            RobustnessDimensionScorecard(
                dimension_key=d.dimension_key,
                title=d.title,
                score=d.score,
                status=d.status,
                evidence_count=d.evidence_count,
                fragility_signals=[
                    s.title if isinstance(s, RobustnessFragilitySignalData) else str(s)
                    for s in d.fragility_signals
                ],
                positive_evidence=d.positive_evidence,
                review_items=d.review_items,
                suggested_actions=d.suggested_actions,
                source_refs_json=d.source_refs_json,
            )
            for d in result.dimension_scorecards
        ],
        fragility_signals=[
            RobustnessFragilitySignal(
                signal_key=s.signal_key,
                title=s.title,
                severity=s.severity,
                evidence_summary=s.evidence_summary,
                suggested_action=s.suggested_action,
                source_dimension=s.source_dimension,
            )
            for s in result.fragility_signals
        ],
        top_review_drivers=result.top_review_drivers,
        suggested_actions=result.suggested_actions,
        evidence_gaps=result.evidence_gaps,
        robustness_vs_readiness_note=result.robustness_vs_readiness_note,
    )


# ---------------------------------------------------------------------------
# M63: GET /api/strategies/{strategy_id}/research-audit-trail
# ---------------------------------------------------------------------------

from app.schemas.research_audit_trail import (  # noqa: E402
    ResearchAuditDownstreamContext,
    ResearchAuditEvent,
    ResearchAuditLinkedObject,
    ResearchAuditStatusTransition,
    ResearchAuditTrailResponse,
)
from app.services.research_audit_trail import (  # noqa: E402
    get_strategy_research_audit_trail,
)


@router.get(
    "/strategies/{strategy_id}/research-audit-trail",
    response_model=ResearchAuditTrailResponse,
    tags=["strategies"],
)
def get_strategy_research_audit_trail_endpoint(
    strategy_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    include_context: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> ResearchAuditTrailResponse:
    """Return a richly-enriched research audit trail for a strategy.

    Deterministic — no AI, no live market data.
    Read-only — no AuditTimelineEvent created.
    Not investment advice.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    try:
        result = get_strategy_research_audit_trail(
            db,
            strategy_id,
            limit=limit,
            offset=offset,
            category=category,
            severity=severity,
            include_context=include_context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    def _linked(obj) -> ResearchAuditLinkedObject | None:
        if obj is None:
            return None
        return ResearchAuditLinkedObject(
            object_type=obj.object_type,
            object_id=obj.object_id,
            label=obj.label,
            route_hint=obj.route_hint,
        )

    def _transition(obj) -> ResearchAuditStatusTransition | None:
        if obj is None:
            return None
        return ResearchAuditStatusTransition(
            previous_status=obj.previous_status,
            new_status=obj.new_status,
            status_type=obj.status_type,
            transition_label=obj.transition_label,
        )

    def _downstream(obj) -> ResearchAuditDownstreamContext | None:
        if obj is None:
            return None
        return ResearchAuditDownstreamContext(
            impacted_artifact_count=obj.impacted_artifact_count,
            recommended_rechecks=list(obj.recommended_rechecks),
            affected_readiness=obj.affected_readiness,
            affected_promotion_gates=obj.affected_promotion_gates,
            affected_review_cases=obj.affected_review_cases,
            affected_freeze_recommendation=obj.affected_freeze_recommendation,
        )

    return ResearchAuditTrailResponse(
        strategy_id=result.strategy_id,
        strategy_name=result.strategy_name,
        generated_at=result.generated_at,
        total_events=result.total_events,
        returned_count=result.returned_count,
        category_counts=result.category_counts,
        importance_counts=result.importance_counts,
        phase_counts=result.phase_counts,
        high_importance_count=result.high_importance_count,
        latest_event_at=result.latest_event_at,
        latest_governance_event_at=result.latest_governance_event_at,
        latest_evidence_event_at=result.latest_evidence_event_at,
        unresolved_review_case_count=result.unresolved_review_case_count,
        open_alert_count=result.open_alert_count,
        latest_freeze_recommendation=result.latest_freeze_recommendation,
        deterministic_summary=result.deterministic_summary,
        suggested_checks=list(result.suggested_checks),
        events=[
            ResearchAuditEvent(
                event_id=e.event_id,
                event_time=e.event_time,
                event_type=e.event_type,
                title=e.title,
                description=e.description,
                severity=e.severity,
                source_type=e.source_type,
                source_id=e.source_id,
                category=e.category,
                importance=e.importance,
                research_phase=e.research_phase,
                linked_object=_linked(e.linked_object),
                downstream_context=_downstream(e.downstream_context),
                status_transition=_transition(e.status_transition),
                evidence_summary_json=e.evidence_summary_json,
                suggested_action=e.suggested_action,
            )
            for e in result.events
        ],
    )


# ---------------------------------------------------------------------------
# M64 — Strategy Reliability Command Center
# ---------------------------------------------------------------------------

from app.schemas.reliability_command_center import (  # noqa: E402
    CommandCenterSubsystemStatus,
    CommandCenterBlocker,
    CommandCenterAction,
    CommandCenterGovernanceSummary,
    CommandCenterEvidenceSummary,
    CommandCenterWorkflowSummary,
    StrategyReliabilityCommandCenterResponse,
)
from app.services.reliability_command_center import (  # noqa: E402
    get_strategy_reliability_command_center,
)


@router.get(
    "/strategies/{strategy_id}/command-center",
    response_model=StrategyReliabilityCommandCenterResponse,
    tags=["strategies"],
)
def get_strategy_reliability_command_center_endpoint(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Return the Reliability Command Center for a strategy.

    Aggregates all reliability sub-systems into a single governance view.
    Read-only, deterministic.  Not investment advice or trading authorisation.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    try:
        result = get_strategy_reliability_command_center(db, strategy_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    def _subsystem(s) -> CommandCenterSubsystemStatus:
        return CommandCenterSubsystemStatus(
            subsystem_key=s.subsystem_key,
            title=s.title,
            status=s.status,
            score=s.score,
            severity=s.severity,
            summary=s.summary,
            top_issue=s.top_issue,
            suggested_action=s.suggested_action,
            route_hint=s.route_hint,
            source_json=s.source_json,
        )

    def _blocker(b) -> CommandCenterBlocker:
        return CommandCenterBlocker(
            blocker_key=b.blocker_key,
            title=b.title,
            category=b.category,
            severity=b.severity,
            evidence_summary=b.evidence_summary,
            source_subsystem=b.source_subsystem,
            required_before_progression=b.required_before_progression,
            suggested_resolution=b.suggested_resolution,
        )

    def _action(a) -> CommandCenterAction:
        return CommandCenterAction(
            action_key=a.action_key,
            title=a.title,
            priority=a.priority,
            action_type=a.action_type,
            reason=a.reason,
            endpoint_hint=a.endpoint_hint,
            route_hint=a.route_hint,
            depends_on=list(a.depends_on),
        )

    gs = result.governance_summary
    es = result.evidence_summary
    ws = result.workflow_summary

    return StrategyReliabilityCommandCenterResponse(
        strategy_id=result.strategy_id,
        strategy_name=result.strategy_name,
        generated_at=result.generated_at,
        command_status=result.command_status,
        command_score=result.command_score,
        deterministic_summary=result.deterministic_summary,
        subsystem_statuses=[_subsystem(s) for s in result.subsystem_statuses],
        top_blockers=[_blocker(b) for b in result.top_blockers],
        action_queue=[_action(a) for a in result.action_queue],
        governance_summary=CommandCenterGovernanceSummary(
            open_review_case_count=gs.open_review_case_count,
            acknowledged_review_case_count=gs.acknowledged_review_case_count,
            high_critical_alert_count=gs.high_critical_alert_count,
            latest_regression_status=gs.latest_regression_status,
            latest_policy_status=gs.latest_policy_status,
            latest_sla_status=gs.latest_sla_status,
            latest_freeze_recommendation=gs.latest_freeze_recommendation,
            promotion_gate_paper_verdict=gs.promotion_gate_paper_verdict,
            promotion_gate_production_verdict=gs.promotion_gate_production_verdict,
        ),
        evidence_summary=CommandCenterEvidenceSummary(
            freshness_status=es.freshness_status,
            coverage_score=es.coverage_score,
            missing_evidence_count=es.missing_evidence_count,
            stale_evidence_count=es.stale_evidence_count,
            graph_status=es.graph_status,
            replay_pack_recommended=es.replay_pack_recommended,
            latest_run_id=es.latest_run_id,
            latest_run_label=es.latest_run_label,
        ),
        workflow_summary=CommandCenterWorkflowSummary(
            current_stage=ws.current_stage,
            next_recommended_stage=ws.next_recommended_stage,
            stage_path=list(ws.stage_path),
            active_experiment_count=ws.active_experiment_count,
            latest_experiment_analysis_status=ws.latest_experiment_analysis_status,
            latest_sweep_status=ws.latest_sweep_status,
            latest_audit_event_at=ws.latest_audit_event_at,
        ),
        note=result.note,
    )
