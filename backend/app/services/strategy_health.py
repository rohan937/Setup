"""Strategy health snapshot service (M27).
Deterministic — no AI, no live market data, no external calls.
Uses existing evidence: reliability scores, evidence coverage, alerts, runs, ingestion batches.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.backtest_audit import BacktestAudit
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.report import Report
from app.models.sdk_ingestion_batch import SdkIngestionBatch
from app.models.signal_snapshot import SignalSnapshot
from app.models.strategy import Strategy
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.models.strategy_run import StrategyRun
from app.services.evidence_coverage import _compute_row, StrategyEvidenceCoverageRowData


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class StrategyHealthSnapshot:
    strategy_id: uuid.UUID
    strategy_name: str
    asset_class: str
    status: str
    health_score: float | None
    health_status: str  # "healthy"|"watch"|"review"|"critical"|"insufficient_evidence"
    primary_concern: str
    latest_run_at: datetime | None
    days_since_latest_run: int | None
    latest_reliability_score: float | None
    reliability_status: str | None
    evidence_coverage_score: float
    open_alert_count: int
    high_critical_alert_count: int
    latest_ingestion_status: str | None
    latest_ingestion_at: datetime | None
    latest_backtest_trust_score: float | None
    latest_data_health_score: float | None
    latest_signal_quality_score: float | None
    latest_report_score: float | None
    missing_evidence: list[str] = field(default_factory=list)
    suggested_checks: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _compute_health_score(
    reliability_score: float | None,
    reliability_status: str | None,
    coverage_score: float,
    critical_alerts: int,
    high_alerts: int,
    medium_alerts: int,
    low_alerts: int,
    days_since_run: int | None,
) -> float | None:
    """Compute a 0–100 health score from available evidence. Returns None if no base exists."""
    # Base score from reliability or coverage
    if reliability_score is not None and reliability_status not in (None, "insufficient_evidence"):
        base = reliability_score
    elif coverage_score > 0:
        base = coverage_score
    else:
        return None

    score = base
    score -= critical_alerts * 30
    score -= high_alerts * 20
    score -= medium_alerts * 8
    score -= low_alerts * 3

    # Staleness penalty
    if days_since_run is None:
        score -= 20
    elif days_since_run > 90:
        score -= 20
    elif days_since_run > 30:
        score -= 10

    return max(0.0, round(score, 1))


def _compute_health_status(
    strategy_status: str,
    reliability_status: str | None,
    reliability_score: float | None,
    coverage_score: float,
    critical_alerts: int,
    high_alerts: int,
    has_any_low_med: bool,
    days_since_run: int | None,
    latest_bt_trust: float | None,
    run_count: int,
) -> str:
    """Determine categorical health status from evidence signals."""
    # Critical
    if critical_alerts > 0:
        return "critical"
    if reliability_status == "weak" and reliability_score is not None and reliability_score < 35:
        return "critical"
    if latest_bt_trust is not None and latest_bt_trust < 40:
        return "critical"
    if strategy_status == "active" and coverage_score < 30 and run_count == 0:
        return "critical"

    # Insufficient evidence
    if reliability_status is None and coverage_score < 20 and run_count == 0:
        return "insufficient_evidence"

    # Review
    if high_alerts > 0:
        return "review"
    if reliability_status in ("weak", "review"):
        return "review"
    if strategy_status == "active" and coverage_score < 60:
        return "review"
    if strategy_status == "active" and run_count == 0:
        return "review"

    # Watch
    if has_any_low_med:
        return "watch"
    if 60 <= coverage_score < 75:
        return "watch"
    if days_since_run is not None and days_since_run > 30:
        return "watch"
    if reliability_status == "good" and coverage_score < 75:
        return "watch"

    # Healthy
    if reliability_status in ("excellent", "good") and coverage_score >= 75:
        return "healthy"

    # Default
    if reliability_status is None:
        return "insufficient_evidence"
    return "watch"


def _primary_concern(
    health_status: str,
    critical_alerts: int,
    high_alerts: int,
    has_low_med: bool,
    reliability_status: str | None,
    reliability_score: float | None,
    run_count: int,
    coverage_score: float,
    days_since_run: int | None,
    missing_evidence: list[str],
) -> str:
    if health_status == "critical":
        if critical_alerts > 0:
            return "Critical-severity alert is open"
        if reliability_score is not None and reliability_score < 35:
            return "Reliability score is critically low"
        return "Evidence coverage is critically insufficient"
    if health_status == "review":
        if high_alerts > 0:
            return "High-severity alert is open"
        if reliability_status in ("weak", "review"):
            return "Reliability score requires review"
        if run_count == 0:
            return "No strategy runs logged"
        return "Evidence coverage is below review threshold"
    if health_status == "watch":
        if has_low_med:
            return "Open low/medium-severity alerts"
        if days_since_run is not None and days_since_run > 30:
            return f"Latest run is {days_since_run} days old"
        return "Evidence coverage is below target"
    if health_status == "insufficient_evidence":
        return "Insufficient evidence to assess strategy health"
    # healthy
    return "Evidence coverage is strong"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_strategy_health(strategy_id: uuid.UUID, db: Session) -> StrategyHealthSnapshot:
    """Compute current health snapshot. No AI, no live data, no external calls."""
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    now = datetime.now(timezone.utc)

    # Evidence coverage row (reuses existing service)
    cov: StrategyEvidenceCoverageRowData = _compute_row(strategy, db)

    # Latest reliability score
    latest_score = (
        db.query(StrategyReliabilityScore)
        .filter(StrategyReliabilityScore.strategy_id == strategy_id)
        .order_by(StrategyReliabilityScore.generated_at.desc())
        .first()
    )
    reliability_score = latest_score.overall_score if latest_score else None
    reliability_status = latest_score.status if latest_score else None
    missing_evidence_list = list(latest_score.missing_evidence_json or []) if latest_score else []
    suggested_checks_list = list(latest_score.suggested_checks_json or []) if latest_score else []

    # Alerts — Alert.strategy_id is String(36)
    open_alert_rows = (
        db.query(Alert.severity)
        .filter(
            Alert.strategy_id == str(strategy_id),
            Alert.status.in_(["open", "acknowledged", "snoozed"]),
        )
        .all()
    )
    sev_list = [r[0] for r in open_alert_rows]
    critical_count = sum(1 for s in sev_list if s == "critical")
    high_count = sum(1 for s in sev_list if s == "high")
    medium_count = sum(1 for s in sev_list if s == "medium")
    low_count = sum(1 for s in sev_list if s == "low")
    open_alert_count = len(sev_list)
    high_critical_count = critical_count + high_count
    has_low_med = (medium_count + low_count) > 0

    # Latest run
    latest_run_at = _normalize_dt(cov.strategy_runs.latest_at)
    days_since_run = int((now - latest_run_at).days) if latest_run_at else None

    # Latest backtest trust
    latest_bt_row = (
        db.query(BacktestAudit.trust_score)
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(BacktestAudit.created_at.desc())
        .first()
    )
    latest_bt_trust = float(latest_bt_row[0]) if latest_bt_row else None

    # Latest data health score
    latest_ds_row = (
        db.query(DatasetSnapshot.health_score)
        .join(StrategyRun, StrategyRun.dataset_snapshot_id == DatasetSnapshot.id)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(DatasetSnapshot.created_at.desc())
        .first()
    )
    latest_data_health = float(latest_ds_row[0]) if latest_ds_row else None

    # Latest signal quality
    latest_sig_row = (
        db.query(SignalSnapshot.quality_score)
        .filter(SignalSnapshot.strategy_id == strategy_id)
        .order_by(SignalSnapshot.created_at.desc())
        .first()
    )
    latest_sig_quality = float(latest_sig_row[0]) if latest_sig_row else None

    # Latest report score
    latest_report_row = (
        db.query(Report.score)
        .filter(Report.strategy_id == strategy_id, Report.score.isnot(None))
        .order_by(Report.generated_at.desc())
        .first()
    )
    latest_report_score = float(latest_report_row[0]) if latest_report_row else None

    # Latest ingestion batch (M25)
    latest_batch = (
        db.query(SdkIngestionBatch)
        .filter(SdkIngestionBatch.strategy_id == strategy_id)
        .order_by(SdkIngestionBatch.created_at.desc())
        .first()
    )
    latest_ingest_status = latest_batch.status if latest_batch else None
    latest_ingest_at = _normalize_dt(latest_batch.created_at) if latest_batch else None

    # Compute health score and status
    run_count = cov.strategy_runs.count
    health_score = _compute_health_score(
        reliability_score, reliability_status,
        cov.evidence_coverage_score,
        critical_count, high_count, medium_count, low_count,
        days_since_run,
    )
    health_status = _compute_health_status(
        strategy.status, reliability_status, reliability_score,
        cov.evidence_coverage_score, critical_count, high_count,
        has_low_med, days_since_run, latest_bt_trust, run_count,
    )

    # Primary concern
    primary = _primary_concern(
        health_status, critical_count, high_count, has_low_med,
        reliability_status, reliability_score, run_count,
        cov.evidence_coverage_score, days_since_run, missing_evidence_list,
    )

    return StrategyHealthSnapshot(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        asset_class=strategy.asset_class,
        status=strategy.status,
        health_score=health_score,
        health_status=health_status,
        primary_concern=primary,
        latest_run_at=latest_run_at,
        days_since_latest_run=days_since_run,
        latest_reliability_score=reliability_score,
        reliability_status=reliability_status,
        evidence_coverage_score=cov.evidence_coverage_score,
        open_alert_count=open_alert_count,
        high_critical_alert_count=high_critical_count,
        latest_ingestion_status=latest_ingest_status,
        latest_ingestion_at=latest_ingest_at,
        latest_backtest_trust_score=latest_bt_trust,
        latest_data_health_score=latest_data_health,
        latest_signal_quality_score=latest_sig_quality,
        latest_report_score=latest_report_score,
        missing_evidence=missing_evidence_list,
        suggested_checks=suggested_checks_list,
        generated_at=now,
    )


def get_strategies_health(
    db: Session,
    *,
    status: str | None = None,
    asset_class: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[StrategyHealthSnapshot], int]:
    """Compute health for multiple strategies (non-archived by default). Returns (items, total)."""
    q = db.query(Strategy).filter(Strategy.status != "archived")
    if status:
        q = q.filter(Strategy.status == status)
    if asset_class:
        q = q.filter(Strategy.asset_class == asset_class)
    q = q.order_by(Strategy.name)

    all_strategies = q.all()
    total = len(all_strategies)
    page = all_strategies[offset: offset + limit]

    snapshots = []
    for s in page:
        try:
            snapshots.append(compute_strategy_health(s.id, db))
        except Exception:
            pass  # skip strategies that fail

    return snapshots, total
