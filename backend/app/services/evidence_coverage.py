"""Evidence Coverage Matrix service (M21).

For every non-archived strategy, computes coverage across 11 evidence layers.
Deterministic — no AI, no live market data, no external calls.

Evidence columns:
  strategy_runs, backtest_runs, dataset_evidence, backtest_audits,
  config_snapshots, universe_snapshots, signal_snapshots, alerts,
  reports, reliability_scores, timeline_events

Cell status values:
  complete  – evidence is present and meets quality threshold
  partial   – evidence exists but is incomplete (e.g. only 1 run, or insufficient_evidence score)
  review    – evidence exists but has quality concerns (e.g. low trust score, open high alert)
  missing   – no evidence found

Coverage score (0–100):
  Average of status weights across 11 columns × 100
  complete=1.0, partial=0.6, review=0.4, missing=0.0
"""
from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.backtest_audit import BacktestAudit
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.report import Report
from app.models.signal_snapshot import SignalSnapshot
from app.models.strategy import Strategy
from app.models.strategy_config_snapshot import StrategyConfigSnapshot
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.models.strategy_run import StrategyRun
from app.models.universe_snapshot import UniverseSnapshot


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STATUS_WEIGHTS: dict[str, float] = {
    "complete": 1.0,
    "partial": 0.6,
    "review": 0.4,
    "missing": 0.0,
}

_COVERAGE_COLUMNS = [
    "strategy_runs",
    "backtest_runs",
    "dataset_evidence",
    "backtest_audits",
    "config_snapshots",
    "universe_snapshots",
    "signal_snapshots",
    "alerts",
    "reports",
    "reliability_scores",
    "timeline_events",
]

# Human-readable column labels (used in most_common_missing_evidence)
_COLUMN_LABELS: dict[str, str] = {
    "strategy_runs": "Strategy Runs",
    "backtest_runs": "Backtest Runs",
    "dataset_evidence": "Dataset Evidence",
    "backtest_audits": "Backtest Audits",
    "config_snapshots": "Config Snapshots",
    "universe_snapshots": "Universe Snapshots",
    "signal_snapshots": "Signal Snapshots",
    "alerts": "Alerts (open high/critical)",
    "reports": "Reliability Reports",
    "reliability_scores": "Reliability Scores",
    "timeline_events": "Timeline Events",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class EvidenceCellData:
    status: str          # "complete", "partial", "review", "missing"
    count: int
    latest_at: datetime | None
    summary: str
    suggested_check: str | None


@dataclass
class StrategyEvidenceCoverageRowData:
    strategy_id: uuid.UUID
    name: str
    slug: str
    asset_class: str
    status: str
    evidence_coverage_score: float
    missing_count: int
    review_count: int
    partial_count: int
    complete_count: int
    strategy_runs: EvidenceCellData
    backtest_runs: EvidenceCellData
    dataset_evidence: EvidenceCellData
    backtest_audits: EvidenceCellData
    config_snapshots: EvidenceCellData
    universe_snapshots: EvidenceCellData
    signal_snapshots: EvidenceCellData
    alerts: EvidenceCellData
    reports: EvidenceCellData
    reliability_scores: EvidenceCellData
    timeline_events: EvidenceCellData
    suggested_next_steps: list[str] = field(default_factory=list)


@dataclass
class EvidenceCoverageSummaryData:
    strategy_count: int
    average_coverage_score: float
    complete_cell_count: int
    partial_cell_count: int
    review_cell_count: int
    missing_cell_count: int
    most_common_missing_evidence: list[str] = field(default_factory=list)


@dataclass
class EvidenceCoverageMatrixData:
    items: list[StrategyEvidenceCoverageRowData]
    total: int
    limit: int
    offset: int
    generated_at: datetime
    summary: EvidenceCoverageSummaryData


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _coverage_score(cells: list[EvidenceCellData]) -> float:
    """Average of per-cell status weights × 100.  Returns 0.0 for empty list."""
    if not cells:
        return 0.0
    total = sum(_STATUS_WEIGHTS.get(c.status, 0.0) for c in cells)
    return round((total / len(cells)) * 100, 1)


def _compute_row(strategy: Strategy, db: Session) -> StrategyEvidenceCoverageRowData:
    """Build a full coverage row for one strategy from existing DB evidence."""
    sid = strategy.id

    # ── A. strategy_runs ──────────────────────────────────────────────────────
    run_type_rows = (
        db.query(StrategyRun.run_type, func.count(StrategyRun.id))
        .filter(StrategyRun.strategy_id == sid)
        .group_by(StrategyRun.run_type)
        .all()
    )
    run_type_map: dict[str, int] = {r[0]: r[1] for r in run_type_rows}
    total_runs = sum(run_type_map.values())
    latest_run_at = (
        db.query(func.max(StrategyRun.created_at))
        .filter(StrategyRun.strategy_id == sid)
        .scalar()
    )

    if total_runs >= 2:
        runs_status, runs_check = "complete", None
        runs_summary = f"{total_runs} run(s) logged"
    elif total_runs == 1:
        runs_status = "partial"
        runs_summary = "1 run logged"
        runs_check = "Log at least one more run to reach complete coverage"
    else:
        runs_status = "missing"
        runs_summary = "No runs logged"
        runs_check = "Log at least two strategy runs (backtest or paper)"

    runs_cell = EvidenceCellData(
        status=runs_status, count=total_runs, latest_at=latest_run_at,
        summary=runs_summary, suggested_check=runs_check,
    )

    # ── B. backtest_runs ──────────────────────────────────────────────────────
    backtest_count = run_type_map.get("backtest", 0)
    latest_bt_at = (
        db.query(func.max(StrategyRun.created_at))
        .filter(StrategyRun.strategy_id == sid, StrategyRun.run_type == "backtest")
        .scalar()
    )

    if backtest_count >= 1:
        bt_status, bt_check = "complete", None
        bt_summary = f"{backtest_count} backtest run(s)"
    else:
        bt_status = "missing"
        bt_summary = "No backtest runs logged"
        bt_check = "Log at least one backtest run"

    bt_cell = EvidenceCellData(
        status=bt_status, count=backtest_count, latest_at=latest_bt_at,
        summary=bt_summary, suggested_check=bt_check,
    )

    # ── C. dataset_evidence ───────────────────────────────────────────────────
    dataset_linked: int = (
        db.query(func.count(StrategyRun.id))
        .filter(
            StrategyRun.strategy_id == sid,
            StrategyRun.dataset_snapshot_id.isnot(None),
        )
        .scalar()
    ) or 0

    if dataset_linked > 0:
        health_rows = (
            db.query(DatasetSnapshot.health_score)
            .join(StrategyRun, StrategyRun.dataset_snapshot_id == DatasetSnapshot.id)
            .filter(StrategyRun.strategy_id == sid)
            .all()
        )
        health_list = [int(r[0]) for r in health_rows if r[0] is not None]
        min_health = min(health_list) if health_list else None
        latest_ds_at = (
            db.query(func.max(DatasetSnapshot.created_at))
            .join(StrategyRun, StrategyRun.dataset_snapshot_id == DatasetSnapshot.id)
            .filter(StrategyRun.strategy_id == sid)
            .scalar()
        )
        if min_health is not None and min_health >= 75:
            ds_status = "complete"
            ds_summary = (
                f"{dataset_linked} run(s) with dataset evidence"
                f" (min health {min_health})"
            )
            ds_check = None
        else:
            ds_status = "review"
            h_str = str(min_health) if min_health is not None else "—"
            ds_summary = (
                f"{dataset_linked} run(s) with dataset evidence"
                f" (min health {h_str}, below 75)"
            )
            ds_check = "Investigate dataset snapshots with health score below 75"
    else:
        latest_ds_at = None
        ds_status = "missing"
        ds_summary = "No runs linked to dataset snapshots"
        ds_check = "Link at least one run to a dataset snapshot"

    ds_cell = EvidenceCellData(
        status=ds_status, count=dataset_linked, latest_at=latest_ds_at,
        summary=ds_summary, suggested_check=ds_check,
    )

    # ── D. backtest_audits ────────────────────────────────────────────────────
    audit_count: int = (
        db.query(func.count(BacktestAudit.id))
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .filter(StrategyRun.strategy_id == sid)
        .scalar()
    ) or 0
    latest_audit_at = (
        db.query(func.max(BacktestAudit.created_at))
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .filter(StrategyRun.strategy_id == sid)
        .scalar()
    )

    if audit_count > 0:
        trust_rows = (
            db.query(BacktestAudit.trust_score)
            .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
            .filter(StrategyRun.strategy_id == sid)
            .all()
        )
        trust_list = [int(r[0]) for r in trust_rows if r[0] is not None]
        avg_trust = round(sum(trust_list) / len(trust_list)) if trust_list else None
        has_high = any(t >= 75 for t in trust_list)
        t_str = str(avg_trust) if avg_trust is not None else "—"

        if has_high:
            audit_status = "complete"
            audit_summary = f"{audit_count} audit(s), avg trust {t_str}"
            audit_check = None
        else:
            audit_status = "review"
            audit_summary = f"{audit_count} audit(s), avg trust {t_str} (below 75)"
            audit_check = "Investigate backtest audits with trust score below 75"
    else:
        audit_status = "missing"
        audit_summary = "No backtest audits computed"
        audit_check = "Run a backtest audit to assess trust quality"

    audit_cell = EvidenceCellData(
        status=audit_status, count=audit_count, latest_at=latest_audit_at,
        summary=audit_summary, suggested_check=audit_check,
    )

    # ── E. config_snapshots ───────────────────────────────────────────────────
    config_count: int = (
        db.query(func.count(StrategyConfigSnapshot.id))
        .filter(StrategyConfigSnapshot.strategy_id == sid)
        .scalar()
    ) or 0
    latest_config_at = (
        db.query(func.max(StrategyConfigSnapshot.created_at))
        .filter(StrategyConfigSnapshot.strategy_id == sid)
        .scalar()
    )

    if config_count >= 1:
        config_status, config_check = "complete", None
        config_summary = f"{config_count} config snapshot(s)"
    else:
        config_status = "missing"
        config_summary = "No config snapshots logged"
        config_check = "Log at least one config snapshot to capture strategy parameters"

    config_cell = EvidenceCellData(
        status=config_status, count=config_count, latest_at=latest_config_at,
        summary=config_summary, suggested_check=config_check,
    )

    # ── F. universe_snapshots ─────────────────────────────────────────────────
    uni_count: int = (
        db.query(func.count(UniverseSnapshot.id))
        .filter(UniverseSnapshot.strategy_id == sid)
        .scalar()
    ) or 0
    latest_uni_at = (
        db.query(func.max(UniverseSnapshot.created_at))
        .filter(UniverseSnapshot.strategy_id == sid)
        .scalar()
    )

    if uni_count >= 1:
        uni_status, uni_check = "complete", None
        uni_summary = f"{uni_count} universe snapshot(s)"
    else:
        uni_status = "missing"
        uni_summary = "No universe snapshots logged"
        uni_check = (
            "Log at least one universe snapshot to capture the strategy's trading universe"
        )

    uni_cell = EvidenceCellData(
        status=uni_status, count=uni_count, latest_at=latest_uni_at,
        summary=uni_summary, suggested_check=uni_check,
    )

    # ── G. signal_snapshots ───────────────────────────────────────────────────
    sig_count: int = (
        db.query(func.count(SignalSnapshot.id))
        .filter(SignalSnapshot.strategy_id == sid)
        .scalar()
    ) or 0
    latest_sig_at = (
        db.query(func.max(SignalSnapshot.created_at))
        .filter(SignalSnapshot.strategy_id == sid)
        .scalar()
    )

    if sig_count > 0:
        avg_q_row = (
            db.query(func.avg(SignalSnapshot.quality_score))
            .filter(SignalSnapshot.strategy_id == sid)
            .scalar()
        )
        avg_quality = float(avg_q_row) if avg_q_row is not None else None
        q_str = f"{avg_quality:.0f}" if avg_quality is not None else "—"

        if avg_quality is not None and avg_quality >= 75:
            sig_status = "complete"
            sig_summary = f"{sig_count} signal snapshot(s), avg quality {q_str}"
            sig_check = None
        else:
            sig_status = "review"
            sig_summary = f"{sig_count} signal snapshot(s), avg quality {q_str} (below 75)"
            sig_check = "Investigate signal snapshots with quality score below 75"
    else:
        sig_status = "missing"
        sig_summary = "No signal snapshots logged"
        sig_check = (
            "Log at least one signal snapshot to capture signal quality evidence"
        )

    sig_cell = EvidenceCellData(
        status=sig_status, count=sig_count, latest_at=latest_sig_at,
        summary=sig_summary, suggested_check=sig_check,
    )

    # ── H. alerts ─────────────────────────────────────────────────────────────
    # Alert.strategy_id is String(36) — use str(sid)
    open_sev_rows = (
        db.query(Alert.severity)
        .filter(
            Alert.strategy_id == str(sid),
            Alert.status.in_(["open", "acknowledged", "snoozed"]),
        )
        .all()
    )
    open_alert_count: int = (
        db.query(func.count(Alert.id))
        .filter(
            Alert.strategy_id == str(sid),
            Alert.status.in_(["open", "acknowledged", "snoozed"]),
        )
        .scalar()
    ) or 0
    latest_alert_at = (
        db.query(func.max(Alert.triggered_at))
        .filter(Alert.strategy_id == str(sid))
        .scalar()
    )

    severities = [r[0] for r in open_sev_rows]
    has_high_critical = any(s in ("high", "critical") for s in severities)
    has_any_open = open_alert_count > 0

    if has_high_critical:
        alert_status = "review"
        alert_summary = (
            f"{open_alert_count} open alert(s) including high/critical severity"
        )
        alert_check = (
            "Resolve open high/critical alerts before computing reliability score"
        )
    elif has_any_open:
        alert_status = "partial"
        alert_summary = f"{open_alert_count} open low/medium alert(s)"
        alert_check = "Review and resolve open alerts"
    else:
        alert_status = "complete"
        alert_summary = "No open high/critical alerts"
        alert_check = None

    alert_cell = EvidenceCellData(
        status=alert_status, count=open_alert_count, latest_at=latest_alert_at,
        summary=alert_summary, suggested_check=alert_check,
    )

    # ── I. reports ────────────────────────────────────────────────────────────
    # Report.strategy_id is Uuid(as_uuid=True) — direct compare
    report_count: int = (
        db.query(func.count(Report.id))
        .filter(Report.strategy_id == sid)
        .scalar()
    ) or 0
    latest_report_at = (
        db.query(func.max(Report.generated_at))
        .filter(Report.strategy_id == sid)
        .scalar()
    )
    reliability_report_count: int = (
        db.query(func.count(Report.id))
        .filter(
            Report.strategy_id == sid,
            Report.report_type == "strategy_reliability",
        )
        .scalar()
    ) or 0

    if reliability_report_count >= 1:
        report_status = "complete"
        report_summary = (
            f"{report_count} report(s), including strategy reliability report"
        )
        report_check = None
    elif report_count >= 1:
        report_status = "partial"
        report_summary = f"{report_count} report(s) (no strategy reliability report)"
        report_check = (
            "Generate a strategy reliability report for complete report coverage"
        )
    else:
        report_status = "missing"
        report_summary = "No reports generated"
        report_check = "Generate at least one strategy reliability report"

    report_cell = EvidenceCellData(
        status=report_status, count=report_count, latest_at=latest_report_at,
        summary=report_summary, suggested_check=report_check,
    )

    # ── J. reliability_scores ─────────────────────────────────────────────────
    # StrategyReliabilityScore.strategy_id is Uuid(as_uuid=True) — direct compare
    score_count: int = (
        db.query(func.count(StrategyReliabilityScore.id))
        .filter(StrategyReliabilityScore.strategy_id == sid)
        .scalar()
    ) or 0
    latest_score = (
        db.query(StrategyReliabilityScore)
        .filter(StrategyReliabilityScore.strategy_id == sid)
        .order_by(StrategyReliabilityScore.generated_at.desc())
        .first()
    )

    if latest_score is None:
        rel_status = "missing"
        rel_summary = "No reliability score computed"
        rel_check = "Compute a reliability score to assess overall evidence quality"
        latest_rel_at: datetime | None = None
    elif latest_score.status == "insufficient_evidence":
        rel_status = "partial"
        rel_summary = "Reliability score computed: insufficient evidence"
        rel_check = "Log more evidence to enable a complete reliability score"
        latest_rel_at = latest_score.generated_at
    elif latest_score.status in ("weak", "review"):
        rel_status = "review"
        s_str = (
            f"{latest_score.overall_score:.1f}"
            if latest_score.overall_score is not None
            else "—"
        )
        rel_summary = f"Reliability score: {s_str}/100 ({latest_score.status})"
        rel_check = "Review and address items flagged in the reliability score"
        latest_rel_at = latest_score.generated_at
    else:
        rel_status = "complete"
        s_str = (
            f"{latest_score.overall_score:.1f}"
            if latest_score.overall_score is not None
            else "—"
        )
        rel_summary = f"Reliability score: {s_str}/100 ({latest_score.status})"
        rel_check = None
        latest_rel_at = latest_score.generated_at

    rel_cell = EvidenceCellData(
        status=rel_status, count=score_count, latest_at=latest_rel_at,
        summary=rel_summary, suggested_check=rel_check,
    )

    # ── K. timeline_events ────────────────────────────────────────────────────
    # AuditTimelineEvent.strategy_id is Uuid(as_uuid=True) — direct compare
    timeline_count: int = (
        db.query(func.count(AuditTimelineEvent.id))
        .filter(AuditTimelineEvent.strategy_id == sid)
        .scalar()
    ) or 0
    latest_tl_at = (
        db.query(func.max(AuditTimelineEvent.created_at))
        .filter(AuditTimelineEvent.strategy_id == sid)
        .scalar()
    )

    if timeline_count >= 3:
        tl_status, tl_check = "complete", None
        tl_summary = f"{timeline_count} timeline event(s)"
    elif timeline_count >= 1:
        tl_status = "partial"
        tl_summary = f"{timeline_count} timeline event(s)"
        tl_check = "Log more evidence to increase timeline activity"
    else:
        tl_status = "missing"
        tl_summary = "No timeline events"
        tl_check = (
            "Timeline events are created automatically when evidence is logged"
        )

    tl_cell = EvidenceCellData(
        status=tl_status, count=timeline_count, latest_at=latest_tl_at,
        summary=tl_summary, suggested_check=tl_check,
    )

    # ── Coverage score & counts ───────────────────────────────────────────────
    all_cells: list[EvidenceCellData] = [
        runs_cell, bt_cell, ds_cell, audit_cell, config_cell, uni_cell,
        sig_cell, alert_cell, report_cell, rel_cell, tl_cell,
    ]
    coverage_score = _coverage_score(all_cells)
    missing_count = sum(1 for c in all_cells if c.status == "missing")
    review_count = sum(1 for c in all_cells if c.status == "review")
    partial_count = sum(1 for c in all_cells if c.status == "partial")
    complete_count = sum(1 for c in all_cells if c.status == "complete")

    # Suggested next steps: checks from non-complete cells (missing first, then review, partial)
    steps: list[str] = []
    for c in all_cells:
        if c.status == "missing" and c.suggested_check:
            steps.append(c.suggested_check)
    for c in all_cells:
        if c.status == "review" and c.suggested_check:
            steps.append(c.suggested_check)
    for c in all_cells:
        if c.status == "partial" and c.suggested_check:
            steps.append(c.suggested_check)

    return StrategyEvidenceCoverageRowData(
        strategy_id=sid,
        name=strategy.name,
        slug=strategy.slug,
        asset_class=strategy.asset_class,
        status=strategy.status,
        evidence_coverage_score=coverage_score,
        missing_count=missing_count,
        review_count=review_count,
        partial_count=partial_count,
        complete_count=complete_count,
        strategy_runs=runs_cell,
        backtest_runs=bt_cell,
        dataset_evidence=ds_cell,
        backtest_audits=audit_cell,
        config_snapshots=config_cell,
        universe_snapshots=uni_cell,
        signal_snapshots=sig_cell,
        alerts=alert_cell,
        reports=report_cell,
        reliability_scores=rel_cell,
        timeline_events=tl_cell,
        suggested_next_steps=steps,
    )


def _build_summary(
    all_rows: list[StrategyEvidenceCoverageRowData],
    page_rows: list[StrategyEvidenceCoverageRowData],
) -> EvidenceCoverageSummaryData:
    """Build aggregate summary over ALL matched rows (not just the page)."""
    strategy_count = len(all_rows)
    if not all_rows:
        return EvidenceCoverageSummaryData(
            strategy_count=0,
            average_coverage_score=0.0,
            complete_cell_count=0,
            partial_cell_count=0,
            review_cell_count=0,
            missing_cell_count=0,
            most_common_missing_evidence=[],
        )

    scores = [r.evidence_coverage_score for r in all_rows]
    avg_score = round(sum(scores) / len(scores), 1)

    complete_count = sum(r.complete_count for r in all_rows)
    partial_count = sum(r.partial_count for r in all_rows)
    review_count = sum(r.review_count for r in all_rows)
    missing_count = sum(r.missing_count for r in all_rows)

    # Count which evidence columns are most frequently missing/review across all rows
    col_names = [
        "strategy_runs", "backtest_runs", "dataset_evidence", "backtest_audits",
        "config_snapshots", "universe_snapshots", "signal_snapshots",
        "alerts", "reports", "reliability_scores", "timeline_events",
    ]
    miss_counter: Counter[str] = Counter()
    for row in all_rows:
        for col in col_names:
            cell: EvidenceCellData = getattr(row, col)
            if cell.status in ("missing", "review"):
                miss_counter[_COLUMN_LABELS.get(col, col)] += 1

    most_common = [label for label, _ in miss_counter.most_common(5)]

    return EvidenceCoverageSummaryData(
        strategy_count=strategy_count,
        average_coverage_score=avg_score,
        complete_cell_count=complete_count,
        partial_cell_count=partial_count,
        review_cell_count=review_count,
        missing_cell_count=missing_count,
        most_common_missing_evidence=most_common,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_evidence_coverage_matrix(
    db: Session,
    *,
    include_archived: bool = False,
    asset_class: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> EvidenceCoverageMatrixData:
    """Return evidence coverage rows for all strategies matching the filters.

    Parameters
    ----------
    db:
        Open SQLAlchemy session.
    include_archived:
        When False (default), archived strategies are excluded.
    asset_class:
        Optional filter by asset_class string (exact match).
    status:
        Optional filter by strategy status string (exact match).
    limit:
        Page size (1–500, default 100).
    offset:
        Page offset (default 0).

    Returns
    -------
    EvidenceCoverageMatrixData with paginated items plus aggregate summary
    computed over *all* matched strategies (not just the page).
    """
    q = db.query(Strategy).order_by(Strategy.name)

    if not include_archived:
        q = q.filter(Strategy.status != "archived")

    if asset_class is not None:
        q = q.filter(Strategy.asset_class == asset_class)

    if status is not None:
        q = q.filter(Strategy.status == status)

    all_strategies: list[Strategy] = q.all()
    total = len(all_strategies)

    # Compute coverage for every matched strategy (for accurate summary stats)
    all_rows = [_compute_row(s, db) for s in all_strategies]

    # Paginate
    page_rows = all_rows[offset: offset + limit]

    summary = _build_summary(all_rows, page_rows)

    return EvidenceCoverageMatrixData(
        items=page_rows,
        total=total,
        limit=limit,
        offset=offset,
        generated_at=datetime.now(timezone.utc),
        summary=summary,
    )
