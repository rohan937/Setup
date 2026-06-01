"""M18: Deterministic per-strategy reliability scoring service.

Aggregates all evidence collected so far (runs, dataset snapshots, backtest
audits, config/universe/signal snapshots, open alerts, reports) into a single
reliability score.  No AI, no live data, no external calls.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.constants import ReliabilityScoreStatus
from app.models.alert import Alert
from app.models.backtest_audit import BacktestAudit
from app.models.data_quality_issue import DataQualityIssue
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.report import Report
from app.models.strategy_config_snapshot import StrategyConfigSnapshot
from app.models.strategy_run import StrategyRun
from app.models.strategy_version import StrategyVersion
from app.models.universe_snapshot import UniverseSnapshot
from app.models.signal_snapshot import SignalSnapshot

# ---------------------------------------------------------------------------
# Weight map for overall score computation
# ---------------------------------------------------------------------------

WEIGHTS: dict[str, float] = {
    "backtest_trust_score": 0.25,
    "data_evidence_score": 0.20,
    "signal_evidence_score": 0.15,
    "universe_evidence_score": 0.10,
    "config_evidence_score": 0.10,
    "strategy_activity_score": 0.10,
    "alert_penalty_score": 0.10,
}


# ---------------------------------------------------------------------------
# Component scoring functions
# ---------------------------------------------------------------------------


def _score_activity(runs: list[StrategyRun]) -> float:
    """Score based on number and diversity of strategy runs. Never None."""
    n = len(runs)
    if n == 0:
        base = 30.0
    elif n == 1:
        base = 55.0
    else:
        base = 75.0

    # Bonus: if run types include backtest AND at least one of (paper/live/research)
    run_types = {r.run_type for r in runs}
    has_backtest = "backtest" in run_types
    has_other = bool(run_types & {"paper", "live", "research"})
    if has_backtest and has_other:
        base = min(base + 10.0, 100.0)

    return base


def _score_data_evidence(
    runs: list[StrategyRun], db: Session
) -> float | None:
    """Score based on linked dataset snapshot health. None when no linked snapshots."""
    # Get run IDs that have dataset_snapshot_id set
    snapshot_ids = [
        r.dataset_snapshot_id
        for r in runs
        if r.dataset_snapshot_id is not None
    ]
    if not snapshot_ids:
        return None

    snapshots = (
        db.query(DatasetSnapshot)
        .filter(DatasetSnapshot.id.in_(snapshot_ids))
        .all()
    )
    if not snapshots:
        return None

    # Average health score
    avg_health = sum(s.health_score for s in snapshots) / len(snapshots)
    result = avg_health

    # Cap at 60 if any snapshot health < 50
    if any(s.health_score < 50 for s in snapshots):
        result = min(result, 60.0)

    # Cap at 70 if any snapshot has critical quality issues
    snap_ids = [s.id for s in snapshots]
    critical_count = (
        db.query(DataQualityIssue)
        .filter(
            DataQualityIssue.snapshot_id.in_(snap_ids),
            DataQualityIssue.severity == "critical",
        )
        .count()
    )
    if critical_count > 0:
        result = min(result, 70.0)

    return round(result, 1)


def _score_backtest_trust(
    runs: list[StrategyRun], db: Session
) -> float | None:
    """Score based on backtest audit trust scores. None when no audits exist."""
    run_ids = [r.id for r in runs]
    if not run_ids:
        return None

    audits = (
        db.query(BacktestAudit)
        .filter(BacktestAudit.strategy_run_id.in_(run_ids))
        .all()
    )
    if not audits:
        return None

    avg_trust = sum(a.trust_score for a in audits) / len(audits)
    result = avg_trust

    # Cap at 65 if any audit has weak or unreliable status
    if any(a.overall_status in ("weak", "unreliable") for a in audits):
        result = min(result, 65.0)

    return round(result, 1)


def _score_config_evidence(
    strategy_id: uuid.UUID,
    versions: list[StrategyVersion],
    db: Session,
) -> float:
    """Score based on config snapshot availability. Never None."""
    if not versions:
        return 40.0

    # Count config snapshots for this strategy
    config_snapshots = (
        db.query(StrategyConfigSnapshot)
        .filter(StrategyConfigSnapshot.strategy_id == strategy_id)
        .all()
    )
    if not config_snapshots:
        return 60.0
    if len(config_snapshots) >= 2:
        return 90.0
    return 85.0


def _score_universe_evidence(
    runs: list[StrategyRun],
    universe_snapshots: list[UniverseSnapshot],
    db: Session,
) -> float | None:
    """Score based on universe snapshot availability. None when no snapshots."""
    if not universe_snapshots:
        return None

    n = len(universe_snapshots)
    if n == 1:
        base = 75.0
    else:
        base = 85.0

    # Bonus if any run has a universe_snapshot_id set
    has_linked_run = any(r.universe_snapshot_id is not None for r in runs)
    if has_linked_run:
        base = min(base + 10.0, 100.0)

    return base


def _score_signal_evidence(
    runs: list[StrategyRun],
    signal_snapshots: list[SignalSnapshot],
    db: Session,
) -> float | None:
    """Score based on signal snapshot quality. None when no snapshots."""
    if not signal_snapshots:
        return None

    # Average quality_score (0–100 integer) across all signal snapshots
    avg_quality = sum(s.quality_score for s in signal_snapshots) / len(signal_snapshots)
    result = float(avg_quality)

    # Cap at 75 if any quality < 70
    if any(s.quality_score < 70 for s in signal_snapshots):
        result = min(result, 75.0)

    # Slight boost if any run links a signal snapshot
    has_linked_run = any(r.signal_snapshot_id is not None for r in runs)
    if has_linked_run:
        result = min(result + 5.0, 100.0)

    return round(result, 1)


def _score_alert_penalty(strategy_id: uuid.UUID, db: Session) -> float:
    """Score penalized by open alerts. Never None."""
    # Load all open alerts for this strategy
    open_alerts = (
        db.query(Alert)
        .filter(
            Alert.strategy_id == str(strategy_id),
            Alert.status == "open",
        )
        .all()
    )

    score = 100.0
    for alert in open_alerts:
        sev = alert.severity
        if sev == "low":
            score -= 5.0
        elif sev == "medium":
            score -= 10.0
        elif sev == "high":
            score -= 20.0
        elif sev == "critical":
            score -= 30.0

    return max(score, 0.0)


def _score_report_coverage(strategy_id: uuid.UUID, db: Session) -> float | None:
    """Score based on report existence and recency. None when no reports."""
    reports = (
        db.query(Report)
        .filter(
            Report.strategy_id == strategy_id,
            Report.report_type == "strategy_reliability",
        )
        .order_by(Report.generated_at.desc())
        .all()
    )
    if not reports:
        return None

    latest = reports[0]
    now = datetime.now(timezone.utc)
    generated = latest.generated_at
    # Make timezone-aware if needed
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)

    age = now - generated
    if age <= timedelta(days=30):
        return 90.0
    return 80.0


# ---------------------------------------------------------------------------
# Status from score
# ---------------------------------------------------------------------------


def _status_from_score(score: float | None) -> str:
    """Deterministic status from overall score."""
    if score is None:
        return ReliabilityScoreStatus.insufficient_evidence
    if score >= 90:
        return ReliabilityScoreStatus.excellent
    if score >= 75:
        return ReliabilityScoreStatus.good
    if score >= 55:
        return ReliabilityScoreStatus.review
    return ReliabilityScoreStatus.weak


# ---------------------------------------------------------------------------
# Main computation function
# ---------------------------------------------------------------------------


def compute_reliability_score(strategy_id: str, db: Session) -> dict:
    """Compute and return all score components as a dict ready for ORM insertion.

    Loads all evidence for the strategy (runs, snapshots, audits, alerts, reports)
    and computes a deterministic per-component + overall reliability score.
    No AI, no live data, no external calls.
    """
    strategy_uuid = uuid.UUID(strategy_id)
    now = datetime.now(timezone.utc)

    # Load data
    runs: list[StrategyRun] = (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_uuid)
        .all()
    )
    versions: list[StrategyVersion] = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_uuid)
        .all()
    )
    universe_snapshots: list[UniverseSnapshot] = (
        db.query(UniverseSnapshot)
        .filter(UniverseSnapshot.strategy_id == strategy_uuid)
        .all()
    )
    signal_snapshots: list[SignalSnapshot] = (
        db.query(SignalSnapshot)
        .filter(SignalSnapshot.strategy_id == strategy_uuid)
        .all()
    )

    # Compute components
    missing_evidence: list[str] = []

    activity_score = _score_activity(runs)

    data_score = _score_data_evidence(runs, db)
    if data_score is None:
        missing_evidence.append("No dataset snapshots linked to any strategy run.")

    backtest_score = _score_backtest_trust(runs, db)
    if backtest_score is None:
        missing_evidence.append("No backtest audits found for any strategy run.")

    config_score = _score_config_evidence(strategy_uuid, versions, db)

    universe_score = _score_universe_evidence(runs, universe_snapshots, db)
    if universe_score is None:
        missing_evidence.append("No universe snapshots found for this strategy.")

    signal_score = _score_signal_evidence(runs, signal_snapshots, db)
    if signal_score is None:
        missing_evidence.append("No signal snapshots found for this strategy.")

    alert_score = _score_alert_penalty(strategy_uuid, db)

    report_score = _score_report_coverage(strategy_uuid, db)
    if report_score is None:
        missing_evidence.append("No strategy_reliability report generated yet.")

    # Build component map
    components: dict[str, float | None] = {
        "strategy_activity_score": activity_score,
        "data_evidence_score": data_score,
        "backtest_trust_score": backtest_score,
        "config_evidence_score": config_score,
        "universe_evidence_score": universe_score,
        "signal_evidence_score": signal_score,
        "alert_penalty_score": alert_score,
        "report_coverage_score": report_score,
    }

    # Compute weighted overall score
    available_weight_sum = 0.0
    weighted_sum = 0.0
    non_null_count = 0
    for key, weight in WEIGHTS.items():
        val = components.get(key)
        if val is not None:
            weighted_sum += weight * val
            available_weight_sum += weight
            non_null_count += 1

    if non_null_count < 3 or available_weight_sum == 0:
        overall_score: float | None = None
        status = ReliabilityScoreStatus.insufficient_evidence
    else:
        overall_score = round(weighted_sum / available_weight_sum, 1)
        status = _status_from_score(overall_score)

    # Suggested checks
    suggested_checks: list[str] = []
    if len(runs) == 0:
        suggested_checks.append("Log at least two strategy runs.")
    elif len(runs) == 1:
        suggested_checks.append("Log at least one more strategy run to improve evidence.")
    if data_score is None:
        suggested_checks.append("Link dataset snapshots to strategy runs.")
    if backtest_score is None:
        suggested_checks.append("Run a Backtest Reality Check.")
    if universe_score is None:
        suggested_checks.append("Log universe snapshots for this strategy.")
    if signal_score is None:
        suggested_checks.append("Log signal snapshots to inspect signal coverage.")
    if alert_score < 80:
        suggested_checks.append("Resolve open alerts for this strategy.")
    if report_score is None:
        suggested_checks.append("Generate a reliability report for this strategy.")
    if backtest_score is not None and backtest_score < 70:
        suggested_checks.append("Investigate low-trust backtest audits.")

    # Evidence counts for transparency
    evidence_counts = {
        "run_count": len(runs),
        "version_count": len(versions),
        "universe_snapshot_count": len(universe_snapshots),
        "signal_snapshot_count": len(signal_snapshots),
        "linked_dataset_snapshot_count": sum(
            1 for r in runs if r.dataset_snapshot_id is not None
        ),
    }

    # Component summaries (brief text description of each score)
    component_summaries: dict[str, str] = {}
    for key, val in components.items():
        if val is not None:
            component_summaries[key] = f"{val:.1f}"
        else:
            component_summaries[key] = "N/A"

    return {
        "strategy_id": strategy_uuid,
        "overall_score": overall_score,
        "status": str(status),
        "strategy_activity_score": activity_score,
        "data_evidence_score": data_score,
        "backtest_trust_score": backtest_score,
        "config_evidence_score": config_score,
        "universe_evidence_score": universe_score,
        "signal_evidence_score": signal_score,
        "alert_penalty_score": alert_score,
        "report_coverage_score": report_score,
        "evidence_counts_json": evidence_counts,
        "component_summaries_json": component_summaries,
        "missing_evidence_json": missing_evidence if missing_evidence else None,
        "suggested_checks_json": suggested_checks if suggested_checks else None,
        "generated_at": now,
    }
