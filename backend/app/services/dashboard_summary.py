"""Dashboard summary aggregation service (M9).

Queries all M3–M8 tables and produces a single ``DashboardSummary`` object.

Design rules:
  - All scores are null when no evidence exists — never fake a score of 100.
  - overall_reliability_score = simple average of available (non-null) dimension scores.
  - strategy_activity_score is computed deterministically from strategy/run counts.
  - No AI, no live market data, no external calls.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.backtest_audit import BacktestAudit
from app.models.backtest_issue import BacktestIssue
from app.models.data_quality_issue import DataQualityIssue
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun
from app.schemas.dashboard import (
    DashboardCounts,
    DashboardScores,
    DashboardSummary,
    RecentEvidenceItem,
)

_RECENT_N = 5   # how many recent items to return per evidence type
_MAX_STRATEGY_RUNS_FOR_FULL_ACTIVITY = 10  # 10+ runs → activity score 100


# ---------------------------------------------------------------------------
# Score helpers
# ---------------------------------------------------------------------------

def _strategy_activity_score(total_strategies: int, total_runs: int) -> float | None:
    """Deterministic activity score based on strategy + run counts.

    Returns None if there are no strategies (not yet instrumented).

    Formula (v1 — simple, deterministic):
      - 0 strategies → None
      - 1+ strategies, 0 runs → 20
      - 1+ strategies, 1–2 runs → 40
      - 1+ strategies, 3–5 runs → 60
      - 1+ strategies, 6–9 runs → 80
      - 10+ runs → 100
    """
    if total_strategies == 0:
        return None
    if total_runs == 0:
        return 20.0
    if total_runs <= 2:
        return 40.0
    if total_runs <= 5:
        return 60.0
    if total_runs <= 9:
        return 80.0
    return 100.0


def _overall_reliability_score(
    data_health: float | None,
    backtest_trust: float | None,
    strategy_activity: float | None,
) -> float | None:
    """Weighted average of available (non-null) dimension scores.

    Returns None only when ALL dimensions are null.
    """
    available = [s for s in (data_health, backtest_trust, strategy_activity) if s is not None]
    if not available:
        return None
    return round(sum(available) / len(available), 1)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_dashboard_summary(db: Session) -> DashboardSummary:
    """Aggregate all M3–M8 evidence into a single DashboardSummary.

    All queries run synchronously in the caller's SQLAlchemy session.
    """
    now = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # A. Strategy counts
    # ------------------------------------------------------------------
    total_strategies: int = db.query(func.count(Strategy.id)).scalar() or 0

    active_strategies: int = (
        db.query(func.count(Strategy.id))
        .filter(Strategy.status == "active")
        .scalar()
        or 0
    )
    archived_strategies: int = (
        db.query(func.count(Strategy.id))
        .filter(Strategy.status == "archived")
        .scalar()
        or 0
    )

    # Strategies grouped by asset_class.
    asset_class_rows = (
        db.query(Strategy.asset_class, func.count(Strategy.id))
        .group_by(Strategy.asset_class)
        .all()
    )
    strategies_by_asset_class: dict[str, int] = {
        row[0]: row[1] for row in asset_class_rows
    }

    # ------------------------------------------------------------------
    # B. Run counts
    # ------------------------------------------------------------------
    total_runs: int = db.query(func.count(StrategyRun.id)).scalar() or 0

    run_type_rows = (
        db.query(StrategyRun.run_type, func.count(StrategyRun.id))
        .group_by(StrategyRun.run_type)
        .all()
    )
    runs_by_type: dict[str, int] = {row[0]: row[1] for row in run_type_rows}

    latest_run_at: datetime | None = db.query(
        func.max(StrategyRun.created_at)
    ).scalar()

    # ------------------------------------------------------------------
    # C. Data health summary
    # ------------------------------------------------------------------
    total_datasets: int = db.query(func.count(Dataset.id)).scalar() or 0
    total_dataset_snapshots: int = (
        db.query(func.count(DatasetSnapshot.id)).scalar() or 0
    )

    # Snapshots that have at least one quality issue.
    snapshots_with_issues: int = (
        db.query(func.count(func.distinct(DataQualityIssue.snapshot_id))).scalar() or 0
    )

    total_data_quality_issues: int = (
        db.query(func.count(DataQualityIssue.id)).scalar() or 0
    )

    data_issue_sev_rows = (
        db.query(DataQualityIssue.severity, func.count(DataQualityIssue.id))
        .group_by(DataQualityIssue.severity)
        .all()
    )
    data_issues_by_severity: dict[str, int] = {
        row[0]: row[1] for row in data_issue_sev_rows
    }

    # Average and lowest health scores.
    avg_data_health: float | None = None
    lowest_data_health: int | None = None
    if total_dataset_snapshots > 0:
        avg_result = db.query(func.avg(DatasetSnapshot.health_score)).scalar()
        avg_data_health = round(float(avg_result), 1) if avg_result is not None else None
        min_result = db.query(func.min(DatasetSnapshot.health_score)).scalar()
        lowest_data_health = int(min_result) if min_result is not None else None

    # ------------------------------------------------------------------
    # D. Backtest audit summary
    # ------------------------------------------------------------------
    total_backtest_audits: int = (
        db.query(func.count(BacktestAudit.id)).scalar() or 0
    )

    total_backtest_issues: int = (
        db.query(func.count(BacktestIssue.id)).scalar() or 0
    )

    backtest_issue_sev_rows = (
        db.query(BacktestIssue.severity, func.count(BacktestIssue.id))
        .group_by(BacktestIssue.severity)
        .all()
    )
    backtest_issues_by_severity: dict[str, int] = {
        row[0]: row[1] for row in backtest_issue_sev_rows
    }

    audit_status_rows = (
        db.query(BacktestAudit.overall_status, func.count(BacktestAudit.id))
        .group_by(BacktestAudit.overall_status)
        .all()
    )
    audits_by_status: dict[str, int] = {
        row[0]: row[1] for row in audit_status_rows
    }

    # Average and lowest trust scores.
    avg_backtest_trust: float | None = None
    lowest_backtest_trust: int | None = None
    if total_backtest_audits > 0:
        avg_bt = db.query(func.avg(BacktestAudit.trust_score)).scalar()
        avg_backtest_trust = round(float(avg_bt), 1) if avg_bt is not None else None
        min_bt = db.query(func.min(BacktestAudit.trust_score)).scalar()
        lowest_backtest_trust = int(min_bt) if min_bt is not None else None

    # ------------------------------------------------------------------
    # E. Reliability scores
    # ------------------------------------------------------------------
    activity_score = _strategy_activity_score(total_strategies, total_runs)
    overall_score = _overall_reliability_score(
        avg_data_health, avg_backtest_trust, activity_score
    )

    # ------------------------------------------------------------------
    # F. Recent evidence (most recent N items each)
    # ------------------------------------------------------------------

    # Recent strategy runs — join to get strategy name.
    recent_run_rows = (
        db.query(StrategyRun, Strategy.name)
        .join(Strategy, StrategyRun.strategy_id == Strategy.id)
        .order_by(StrategyRun.created_at.desc())
        .limit(_RECENT_N)
        .all()
    )
    recent_runs: list[RecentEvidenceItem] = [
        RecentEvidenceItem(
            id=run.id,
            item_type="run",
            title=run.run_name,
            strategy_name=strategy_name,
            score=None,
            status=f"{run.run_type} · {run.status}",
            timestamp=run.created_at,
        )
        for run, strategy_name in recent_run_rows
    ]

    # Recent dataset snapshots — join to dataset for the name.
    recent_snap_rows = (
        db.query(DatasetSnapshot, Dataset.name)
        .join(Dataset, DatasetSnapshot.dataset_id == Dataset.id)
        .order_by(DatasetSnapshot.created_at.desc())
        .limit(_RECENT_N)
        .all()
    )
    recent_snapshots: list[RecentEvidenceItem] = [
        RecentEvidenceItem(
            id=snap.id,
            item_type="snapshot",
            title=f"{dataset_name} · {snap.version_label}",
            strategy_name=None,
            score=float(snap.health_score),
            status="healthy" if snap.health_score >= 90 else (
                "warning" if snap.health_score >= 60 else "degraded"
            ),
            timestamp=snap.created_at,
        )
        for snap, dataset_name in recent_snap_rows
    ]

    # Recent backtest audits — join to strategy_run + strategy.
    recent_audit_rows = (
        db.query(BacktestAudit, StrategyRun.run_name, Strategy.name)
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .join(Strategy, StrategyRun.strategy_id == Strategy.id)
        .order_by(BacktestAudit.created_at.desc())
        .limit(_RECENT_N)
        .all()
    )
    recent_audits: list[RecentEvidenceItem] = [
        RecentEvidenceItem(
            id=audit.id,
            item_type="audit",
            title=run_name,
            strategy_name=strategy_name,
            score=float(audit.trust_score),
            status=audit.overall_status,
            timestamp=audit.created_at,
        )
        for audit, run_name, strategy_name in recent_audit_rows
    ]

    # Recent timeline events.
    recent_event_rows = (
        db.query(AuditTimelineEvent)
        .order_by(AuditTimelineEvent.created_at.desc())
        .limit(_RECENT_N)
        .all()
    )
    recent_timeline_events: list[RecentEvidenceItem] = [
        RecentEvidenceItem(
            id=event.id,
            item_type="timeline_event",
            title=event.title,
            strategy_name=None,
            score=None,
            status=event.event_type,
            timestamp=event.created_at,
        )
        for event in recent_event_rows
    ]

    # ------------------------------------------------------------------
    # Assemble and return
    # ------------------------------------------------------------------
    counts = DashboardCounts(
        total_strategies=total_strategies,
        active_strategies=active_strategies,
        archived_strategies=archived_strategies,
        strategies_by_asset_class=strategies_by_asset_class,
        total_runs=total_runs,
        backtest_run_count=runs_by_type.get("backtest", 0),
        research_run_count=runs_by_type.get("research", 0),
        paper_run_count=runs_by_type.get("paper", 0),
        live_run_count=runs_by_type.get("live", 0),
        latest_run_at=latest_run_at,
        total_datasets=total_datasets,
        total_dataset_snapshots=total_dataset_snapshots,
        snapshots_with_issues=snapshots_with_issues,
        total_data_quality_issues=total_data_quality_issues,
        data_issues_by_severity=data_issues_by_severity,
        total_backtest_audits=total_backtest_audits,
        total_backtest_issues=total_backtest_issues,
        backtest_issues_by_severity=backtest_issues_by_severity,
        audits_by_status=audits_by_status,
    )

    scores = DashboardScores(
        data_health_score=avg_data_health,
        lowest_data_health_score=lowest_data_health,
        backtest_trust_score=avg_backtest_trust,
        lowest_backtest_trust_score=lowest_backtest_trust,
        strategy_activity_score=activity_score,
        overall_reliability_score=overall_score,
    )

    return DashboardSummary(
        generated_at=now,
        counts=counts,
        scores=scores,
        recent_runs=recent_runs,
        recent_snapshots=recent_snapshots,
        recent_audits=recent_audits,
        recent_timeline_events=recent_timeline_events,
    )
