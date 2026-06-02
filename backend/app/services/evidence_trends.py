"""Evidence Trends service (M30).

Computes longitudinal trends for the four key evidence series:
  - Reliability score (overall_score from StrategyReliabilityScore)
  - Data health (health_score from DatasetSnapshot via StrategyRun)
  - Backtest trust (trust_score from BacktestAudit via StrategyRun)
  - Signal quality (quality_score from SignalSnapshot)

No timeline events are created; this is a read-only service.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.backtest_audit import BacktestAudit
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.signal_snapshot import SignalSnapshot
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.models.strategy_run import StrategyRun


# ---------------------------------------------------------------------------
# Severity ordering (mirrors strategy_run_history.py)
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_ts(dt: datetime | None) -> datetime | None:
    """Ensure datetime is timezone-aware (UTC).  Returns None if dt is None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TrendPointData:
    id: uuid.UUID
    label: str
    value: float | None
    status: str | None
    timestamp: datetime
    metadata_json: dict | None = field(default=None)


@dataclass
class TrendSummaryData:
    points: list  # list of TrendPointData, chronological ascending
    latest_value: float | None
    previous_value: float | None
    delta: float | None
    direction: str  # "improving" | "deteriorating" | "flat" | "insufficient_history"
    point_count: int
    min_value: float | None
    max_value: float | None
    average_value: float | None
    latest_label: str | None
    latest_at: datetime | None
    deterministic_summary: str


@dataclass
class EvidenceCoverageCurrentData:
    evidence_coverage_score: float
    missing_count: int
    review_count: int
    complete_count: int


@dataclass
class StrategyEvidenceTrendsData:
    strategy_id: uuid.UUID
    strategy_name: str
    generated_at: datetime
    reliability_trend: TrendSummaryData
    data_health_trend: TrendSummaryData
    backtest_trust_trend: TrendSummaryData
    signal_quality_trend: TrendSummaryData
    coverage_current: EvidenceCoverageCurrentData | None
    overall_summary: str
    suggested_checks: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core trend computation
# ---------------------------------------------------------------------------


def _compute_trend_summary(series_name: str, points: list[TrendPointData]) -> TrendSummaryData:
    """Given a list of TrendPointData (in any order), sort chronologically,
    compute stats and direction.
    """
    _min_ts = datetime.min.replace(tzinfo=timezone.utc)
    points_sorted = sorted(
        points,
        key=lambda p: _normalize_ts(p.timestamp) or _min_ts,
    )
    numeric = [(p.value, p.timestamp) for p in points_sorted if p.value is not None]
    point_count = len(numeric)

    if point_count == 0:
        return TrendSummaryData(
            points=points_sorted,
            latest_value=None,
            previous_value=None,
            delta=None,
            direction="insufficient_history",
            point_count=0,
            min_value=None,
            max_value=None,
            average_value=None,
            latest_label=None,
            latest_at=None,
            deterministic_summary=(
                f"No {series_name} data exists. Log evidence to see trend."
            ),
        )

    if point_count == 1:
        val, _ts = numeric[0]
        latest_label = points_sorted[-1].label if points_sorted else None
        latest_at = _normalize_ts(points_sorted[-1].timestamp) if points_sorted else None
        return TrendSummaryData(
            points=points_sorted,
            latest_value=val,
            previous_value=None,
            delta=None,
            direction="insufficient_history",
            point_count=1,
            min_value=val,
            max_value=val,
            average_value=val,
            latest_label=latest_label,
            latest_at=latest_at,
            deterministic_summary=(
                f"Only 1 {series_name} data point exists. "
                f"At least 2 are needed to show trend direction."
            ),
        )

    latest_val = numeric[-1][0]
    previous_val = numeric[-2][0]
    delta = latest_val - previous_val

    DIRECTION_THRESHOLD = 2.0
    if delta > DIRECTION_THRESHOLD:
        direction = "improving"
    elif delta < -DIRECTION_THRESHOLD:
        direction = "deteriorating"
    else:
        direction = "flat"

    values = [v for v, _ in numeric]
    min_v = min(values)
    max_v = max(values)
    avg_v = round(sum(values) / len(values), 1)
    latest_label = points_sorted[-1].label if points_sorted else None
    latest_at = _normalize_ts(points_sorted[-1].timestamp) if points_sorted else None

    if direction == "improving":
        summary = (
            f"{series_name} improved from {previous_val:.0f} to {latest_val:.0f} "
            f"(+{delta:.0f}) across {point_count} data point(s)."
        )
    elif direction == "deteriorating":
        summary = (
            f"{series_name} deteriorated from {previous_val:.0f} to {latest_val:.0f} "
            f"({delta:.0f}) across {point_count} data point(s)."
        )
    else:
        summary = (
            f"{series_name} is stable near {latest_val:.0f} across {point_count} "
            f"data point(s). Delta: {delta:+.0f}."
        )

    return TrendSummaryData(
        points=points_sorted,
        latest_value=latest_val,
        previous_value=previous_val,
        delta=round(delta, 1),
        direction=direction,
        point_count=point_count,
        min_value=round(min_v, 1),
        max_value=round(max_v, 1),
        average_value=avg_v,
        latest_label=latest_label,
        latest_at=latest_at,
        deterministic_summary=summary,
    )


# ---------------------------------------------------------------------------
# Series-specific loaders
# ---------------------------------------------------------------------------


def _reliability_trend(strategy_id: uuid.UUID, db: Session, limit: int) -> TrendSummaryData:
    scores = (
        db.query(StrategyReliabilityScore)
        .filter(StrategyReliabilityScore.strategy_id == strategy_id)
        .order_by(StrategyReliabilityScore.generated_at.asc())
        .limit(limit)
        .all()
    )
    points = [
        TrendPointData(
            id=s.id,
            label=f"Score {i + 1}",
            value=s.overall_score,
            status=s.status,
            timestamp=s.generated_at,
        )
        for i, s in enumerate(scores)
    ]
    return _compute_trend_summary("Reliability score", points)


def _data_health_trend(strategy_id: uuid.UUID, db: Session, limit: int) -> TrendSummaryData:
    rows = (
        db.query(DatasetSnapshot, Dataset.name)
        .join(StrategyRun, StrategyRun.dataset_snapshot_id == DatasetSnapshot.id)
        .join(Dataset, DatasetSnapshot.dataset_id == Dataset.id)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(DatasetSnapshot.created_at.asc())
        .limit(limit)
        .all()
    )
    points = [
        TrendPointData(
            id=snap.id,
            label=f"{ds_name} v{snap.version_label}",
            value=float(snap.health_score) if snap.health_score is not None else None,
            status=None,
            timestamp=snap.created_at,
        )
        for snap, ds_name in rows
    ]
    return _compute_trend_summary("Data health", points)


def _backtest_trust_trend(strategy_id: uuid.UUID, db: Session, limit: int) -> TrendSummaryData:
    rows = (
        db.query(BacktestAudit)
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(BacktestAudit.created_at.asc())
        .limit(limit)
        .all()
    )
    points = [
        TrendPointData(
            id=a.id,
            label=f"Audit {i + 1}",
            value=float(a.trust_score),
            status=a.overall_status,
            timestamp=a.created_at,
        )
        for i, a in enumerate(rows)
    ]
    return _compute_trend_summary("Backtest trust", points)


def _signal_quality_trend(strategy_id: uuid.UUID, db: Session, limit: int) -> TrendSummaryData:
    rows = (
        db.query(SignalSnapshot)
        .filter(SignalSnapshot.strategy_id == strategy_id)
        .order_by(SignalSnapshot.created_at.asc())
        .limit(limit)
        .all()
    )
    points = [
        TrendPointData(
            id=s.id,
            label=s.label or f"Signal {i + 1}",
            value=float(s.quality_score) if s.quality_score is not None else None,
            status=None,
            timestamp=s.created_at,
        )
        for i, s in enumerate(rows)
    ]
    return _compute_trend_summary("Signal quality", points)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_strategy_evidence_trends(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    limit_per_series: int = 20,
) -> StrategyEvidenceTrendsData:
    """Return evidence trend data for the four key series for a strategy.

    Raises ValueError if the strategy does not exist.
    """
    from app.models.strategy import Strategy  # deferred to avoid circular imports

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    now = datetime.now(timezone.utc)

    rel = _reliability_trend(strategy_id, db, limit_per_series)
    data = _data_health_trend(strategy_id, db, limit_per_series)
    bt = _backtest_trust_trend(strategy_id, db, limit_per_series)
    sig = _signal_quality_trend(strategy_id, db, limit_per_series)

    # Coverage current snapshot (from evidence_coverage service)
    coverage_current: EvidenceCoverageCurrentData | None = None
    try:
        from app.services.evidence_coverage import _compute_row

        cov = _compute_row(strategy, db)
        coverage_current = EvidenceCoverageCurrentData(
            evidence_coverage_score=cov.evidence_coverage_score,
            missing_count=cov.missing_count,
            review_count=cov.review_count,
            complete_count=cov.complete_count,
        )
    except Exception:
        pass

    # Overall summary
    improving_count = sum(1 for t in [rel, data, bt, sig] if t.direction == "improving")
    deteriorating_count = sum(
        1 for t in [rel, data, bt, sig] if t.direction == "deteriorating"
    )
    if deteriorating_count > 0:
        overall = (
            f"{deteriorating_count} evidence series is/are deteriorating. Review required."
        )
    elif improving_count > 0:
        overall = f"{improving_count} evidence series is/are improving."
    else:
        overall = "Evidence trends are stable or have insufficient history."

    # Suggested checks for series with no history
    checks: list[str] = []
    if rel.direction == "insufficient_history":
        checks.append(
            "Compute at least two reliability scores to see reliability trend."
        )
    if data.direction == "insufficient_history":
        checks.append(
            "Link strategy runs to dataset snapshots to see data health trend."
        )
    if bt.direction == "insufficient_history":
        checks.append(
            "Run backtest audits on strategy runs to see trust trend."
        )
    if sig.direction == "insufficient_history":
        checks.append(
            "Log signal snapshots to see signal quality trend."
        )

    return StrategyEvidenceTrendsData(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        generated_at=now,
        reliability_trend=rel,
        data_health_trend=data,
        backtest_trust_trend=bt,
        signal_quality_trend=sig,
        coverage_current=coverage_current,
        overall_summary=overall,
        suggested_checks=checks,
    )
