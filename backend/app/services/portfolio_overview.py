"""Portfolio Overview service (M32).

Aggregates strategy-level health, coverage, reliability, and trend data
across a project or organization into a single portfolio snapshot.

Deterministic — no AI, no live market data, no external calls.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Health status priority (lower = more urgent)
# ---------------------------------------------------------------------------

HEALTH_STATUS_ORDER = {
    "critical": 0,
    "review": 1,
    "watch": 2,
    "insufficient_evidence": 3,
    "healthy": 4,
}


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class PortfolioTrendFlagsData:
    reliability_deteriorating: bool
    data_health_deteriorating: bool
    backtest_trust_deteriorating: bool
    signal_quality_deteriorating: bool


@dataclass
class PortfolioStrategyItemData:
    strategy_id: uuid.UUID
    name: str
    slug: str
    asset_class: str
    status: str
    health_score: float | None
    health_status: str
    primary_concern: str
    reliability_score: float | None
    reliability_status: str | None
    evidence_coverage_score: float
    open_alert_count: int
    high_critical_alert_count: int
    latest_run_at: datetime | None
    days_since_latest_run: int | None
    trend_flags: PortfolioTrendFlagsData
    missing_evidence_count: int
    review_reason: str | None


@dataclass
class PortfolioRecentActivityItemData:
    strategy_name: str
    event_type: str
    description: str
    timestamp: datetime


@dataclass
class PortfolioOverviewData:
    generated_at: datetime
    strategy_count: int
    active_strategy_count: int
    archived_strategy_count: int
    average_health_score: float | None
    average_reliability_score: float | None
    average_evidence_coverage_score: float | None
    open_alert_count: int
    high_critical_alert_count: int
    strategies_by_health_status: dict
    strategies_by_reliability_status: dict
    strategies_by_asset_class: dict
    all_items: list
    top_review_strategies: list
    most_under_instrumented_strategies: list
    strongest_evidence_strategies: list
    deteriorating_trend_strategies: list
    recent_activity: list
    suggested_next_steps: list
    deterministic_summary: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _quick_trend_flags(strategy_id: uuid.UUID, db: Session) -> PortfolioTrendFlagsData:
    """Check if any evidence trends are deteriorating by comparing last 2 data points.

    Uses threshold of 2.0 points (same as evidence_trends.py).
    """
    THRESHOLD = 2.0

    def _is_deteriorating(values: list) -> bool:
        valid = [v for v in values if v is not None]
        if len(valid) < 2:
            return False
        return (valid[-1] - valid[-2]) < -THRESHOLD

    from app.models.strategy_reliability_score import StrategyReliabilityScore
    from app.models.backtest_audit import BacktestAudit
    from app.models.dataset_snapshot import DatasetSnapshot
    from app.models.signal_snapshot import SignalSnapshot
    from app.models.strategy_run import StrategyRun

    rel_rows = (
        db.query(StrategyReliabilityScore.overall_score)
        .filter(
            StrategyReliabilityScore.strategy_id == strategy_id,
            StrategyReliabilityScore.overall_score.isnot(None),
        )
        .order_by(StrategyReliabilityScore.generated_at.desc())
        .limit(2)
        .all()
    )
    rel = [row[0] for row in rel_rows]
    rel.reverse()

    data_rows = (
        db.query(DatasetSnapshot.health_score)
        .join(StrategyRun, StrategyRun.dataset_snapshot_id == DatasetSnapshot.id)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(DatasetSnapshot.created_at.desc())
        .limit(2)
        .all()
    )
    data = [row[0] for row in data_rows]
    data.reverse()

    bt_rows = (
        db.query(BacktestAudit.trust_score)
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(BacktestAudit.created_at.desc())
        .limit(2)
        .all()
    )
    bt = [row[0] for row in bt_rows]
    bt.reverse()

    sig_rows = (
        db.query(SignalSnapshot.quality_score)
        .filter(SignalSnapshot.strategy_id == strategy_id)
        .order_by(SignalSnapshot.created_at.desc())
        .limit(2)
        .all()
    )
    sig = [row[0] for row in sig_rows]
    sig.reverse()

    return PortfolioTrendFlagsData(
        reliability_deteriorating=_is_deteriorating(rel),
        data_health_deteriorating=_is_deteriorating(data),
        backtest_trust_deteriorating=_is_deteriorating(bt),
        signal_quality_deteriorating=_is_deteriorating(sig),
    )


def _build_portfolio_item(
    strategy,
    health,
    cov_row,
    db: Session,
) -> PortfolioStrategyItemData:
    trend_flags = _quick_trend_flags(strategy.id, db)

    review_reason: str | None = None
    if health.health_status == "critical":
        review_reason = "Critical health state"
    elif health.high_critical_alert_count > 0:
        review_reason = "High/critical alerts open"
    elif health.health_status == "review":
        review_reason = health.primary_concern
    elif health.health_status == "watch":
        review_reason = "Watch state"

    return PortfolioStrategyItemData(
        strategy_id=strategy.id,
        name=strategy.name,
        slug=strategy.slug,
        asset_class=strategy.asset_class,
        status=strategy.status,
        health_score=health.health_score,
        health_status=health.health_status,
        primary_concern=health.primary_concern,
        reliability_score=health.latest_reliability_score,
        reliability_status=health.reliability_status,
        evidence_coverage_score=cov_row.evidence_coverage_score,
        open_alert_count=health.open_alert_count,
        high_critical_alert_count=health.high_critical_alert_count,
        latest_run_at=health.latest_run_at,
        days_since_latest_run=health.days_since_latest_run,
        trend_flags=trend_flags,
        missing_evidence_count=cov_row.missing_count,
        review_reason=review_reason,
    )


# ---------------------------------------------------------------------------
# Main service function
# ---------------------------------------------------------------------------


def get_portfolio_overview(
    db: Session,
    *,
    project_id=None,
    organization_id=None,
    include_archived: bool = False,
    limit_per_section: int = 5,
) -> PortfolioOverviewData:
    from app.models.strategy import Strategy
    from app.models.project import Project
    from app.services.strategy_health import compute_strategy_health
    from app.services.evidence_coverage import _compute_row

    now = datetime.now(timezone.utc)

    q = db.query(Strategy)
    if not include_archived:
        q = q.filter(Strategy.status != "archived")
    if project_id is not None:
        q = q.filter(Strategy.project_id == project_id)
    if organization_id is not None:
        q = q.join(Project, Strategy.project_id == Project.id).filter(
            Project.organization_id == organization_id
        )
    strategies = q.order_by(Strategy.name).all()
    total_count = len(strategies)

    archived_count = len(
        db.query(Strategy).filter(Strategy.status == "archived").all()
    )
    active_count = sum(1 for s in strategies if s.status != "archived")

    items: list[PortfolioStrategyItemData] = []
    for s in strategies:
        try:
            health = compute_strategy_health(s.id, db)
            cov_row = _compute_row(s, db)
            item = _build_portfolio_item(s, health, cov_row, db)
            items.append(item)
        except Exception:
            pass

    # ----- Aggregate stats -----
    health_scores = [i.health_score for i in items if i.health_score is not None]
    rel_scores = [i.reliability_score for i in items if i.reliability_score is not None]
    cov_scores = [i.evidence_coverage_score for i in items]

    avg_health = round(sum(health_scores) / len(health_scores), 1) if health_scores else None
    avg_rel = round(sum(rel_scores) / len(rel_scores), 1) if rel_scores else None
    avg_cov = round(sum(cov_scores) / len(cov_scores), 1) if cov_scores else None

    total_alerts = sum(i.open_alert_count for i in items)
    total_hc = sum(i.high_critical_alert_count for i in items)

    status_counts: dict = {}
    for i in items:
        status_counts[i.health_status] = status_counts.get(i.health_status, 0) + 1

    rel_status_counts: dict = {}
    for i in items:
        rs = i.reliability_status or "no_score"
        rel_status_counts[rs] = rel_status_counts.get(rs, 0) + 1

    asset_counts: dict = {}
    for i in items:
        asset_counts[i.asset_class] = asset_counts.get(i.asset_class, 0) + 1

    # ----- Rankings -----
    def _health_sort_key(i: PortfolioStrategyItemData):
        return (
            HEALTH_STATUS_ORDER.get(i.health_status, 99),
            -i.high_critical_alert_count,
            i.health_score or 0.0,
            i.name,
        )

    review_items = sorted(
        [
            i
            for i in items
            if i.health_status in ("critical", "review", "watch", "insufficient_evidence")
        ],
        key=_health_sort_key,
    )
    under_instr = sorted(
        items,
        key=lambda i: (i.evidence_coverage_score, -i.missing_evidence_count, i.name),
    )
    strongest = sorted(
        [i for i in items if i.high_critical_alert_count == 0],
        key=lambda i: (-i.evidence_coverage_score, -(i.reliability_score or 0), i.name),
    )
    deteriorating = sorted(
        [
            i
            for i in items
            if any(
                [
                    i.trend_flags.reliability_deteriorating,
                    i.trend_flags.data_health_deteriorating,
                    i.trend_flags.backtest_trust_deteriorating,
                    i.trend_flags.signal_quality_deteriorating,
                ]
            )
        ],
        key=lambda i: -(
            sum(
                [
                    i.trend_flags.reliability_deteriorating,
                    i.trend_flags.data_health_deteriorating,
                    i.trend_flags.backtest_trust_deteriorating,
                    i.trend_flags.signal_quality_deteriorating,
                ]
            )
        ),
    )

    # ----- Suggested next steps -----
    checks: list[str] = []
    crit_count = status_counts.get("critical", 0)
    rev_count = status_counts.get("review", 0)
    if crit_count > 0:
        checks.append(f"Resolve critical health issues for {crit_count} strategy(ies).")
    if total_hc > 0:
        checks.append(f"Address {total_hc} open high/critical alert(s).")
    if len(deteriorating) > 0:
        checks.append(
            f"Investigate deteriorating evidence trends in {len(deteriorating)} strategy(ies)."
        )
    if under_instr and under_instr[0].evidence_coverage_score < 30:
        checks.append("Improve evidence coverage for under-instrumented strategies.")

    # ----- Deterministic summary -----
    if crit_count > 0:
        summary = (
            f"Portfolio has {crit_count} critical and {rev_count} review strategy(ies). "
            "Immediate review required."
        )
    elif rev_count > 0:
        summary = (
            f"Portfolio has {rev_count} strategy(ies) requiring review. "
            f"Average health score: {avg_health or 'N/A'}."
        )
    else:
        summary = (
            f"Portfolio of {total_count} strategies. "
            f"Average health: {avg_health or 'N/A'}/100. "
            f"Average coverage: {avg_cov or 'N/A'}/100."
        )

    return PortfolioOverviewData(
        generated_at=now,
        strategy_count=total_count,
        active_strategy_count=active_count,
        archived_strategy_count=archived_count,
        average_health_score=avg_health,
        average_reliability_score=avg_rel,
        average_evidence_coverage_score=avg_cov,
        open_alert_count=total_alerts,
        high_critical_alert_count=total_hc,
        strategies_by_health_status=status_counts,
        strategies_by_reliability_status=rel_status_counts,
        strategies_by_asset_class=asset_counts,
        all_items=items,
        top_review_strategies=review_items[:limit_per_section],
        most_under_instrumented_strategies=under_instr[:limit_per_section],
        strongest_evidence_strategies=strongest[:limit_per_section],
        deteriorating_trend_strategies=deteriorating[:limit_per_section],
        recent_activity=[],
        suggested_next_steps=checks,
        deterministic_summary=summary,
    )
