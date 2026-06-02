"""Project health snapshot service (M28).

Deterministic — no AI, no live market data, no external calls.
Aggregates per-strategy health snapshots into a project-level health summary.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class ProjectHealthSnapshot:
    project_id: uuid.UUID
    project_name: str
    organization_id: uuid.UUID
    health_score: float | None
    health_status: str  # healthy/watch/review/critical/insufficient_evidence
    strategy_count: int
    healthy_strategy_count: int
    watch_strategy_count: int
    review_strategy_count: int
    critical_strategy_count: int
    insufficient_evidence_strategy_count: int
    average_strategy_health_score: float | None
    average_reliability_score: float | None
    average_evidence_coverage_score: float | None
    open_alert_count: int
    high_critical_alert_count: int
    recent_failed_ingestion_count: int
    latest_activity_at: datetime | None
    primary_concern: str
    suggested_checks: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_project_status(
    critical_cnt: int,
    review_cnt: int,
    watch_cnt: int,
    healthy_cnt: int,
    insuff_cnt: int,
    total: int,
    health_score: float | None,
    project_critical_alerts: int,
) -> str:
    if total == 0:
        return "insufficient_evidence"
    if project_critical_alerts > 0 or critical_cnt > 0:
        return "critical"
    most_insuff = insuff_cnt > total / 2
    if most_insuff and healthy_cnt == 0:
        return "insufficient_evidence"
    if review_cnt > 0 or (health_score is not None and health_score < 60):
        return "review"
    if watch_cnt > 0 or (health_score is not None and 60 <= health_score < 75):
        return "watch"
    if healthy_cnt > 0 and health_score is not None and health_score >= 75:
        return "healthy"
    if health_score is None:
        return "insufficient_evidence"
    return "watch"


def _project_primary_concern(
    status: str,
    critical_cnt: int,
    review_cnt: int,
    critical_alerts: int,
    high_alerts: int,
    strategy_count: int,
    recent_failed: int,
) -> str:
    if status == "insufficient_evidence":
        return "Insufficient evidence across project strategies"
    if status == "critical":
        if critical_alerts > 0:
            return "Critical-severity alerts are open for project strategies"
        if critical_cnt > 0:
            return f"{critical_cnt} strategy(ies) in critical health state"
    if status == "review":
        if high_alerts > 0:
            return "High-severity alerts are open for project strategies"
        if review_cnt > 0:
            return f"{review_cnt} strategy(ies) require health review"
    if status == "watch":
        if recent_failed > 0:
            return f"{recent_failed} failed ingestion batch(es) in last 7 days"
        return "Some strategies are in watch state"
    return "Project strategies are in good health"


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_project_health(project_id: uuid.UUID, db: Session) -> ProjectHealthSnapshot:
    """Compute a ProjectHealthSnapshot for the given project."""
    from app.models.alert import Alert
    from app.models.project import Project
    from app.models.sdk_ingestion_batch import SdkIngestionBatch
    from app.models.strategy import Strategy
    from app.models.strategy_run import StrategyRun
    from app.services.strategy_health import compute_strategy_health

    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    now = datetime.now(timezone.utc)
    strategies = db.query(Strategy).filter(Strategy.project_id == project_id).all()
    strategy_count = len(strategies)

    # Compute health for each strategy
    health_snaps = []
    for s in strategies:
        try:
            health_snaps.append(compute_strategy_health(s.id, db))
        except Exception:
            pass

    # Count status distributions
    status_counts: dict[str, int] = {
        "healthy": 0,
        "watch": 0,
        "review": 0,
        "critical": 0,
        "insufficient_evidence": 0,
    }
    for snap in health_snaps:
        key = snap.health_status
        status_counts[key] = status_counts.get(key, 0) + 1

    scored = [s.health_score for s in health_snaps if s.health_score is not None]
    avg_health = round(sum(scored) / len(scored), 1) if scored else None

    rel_scores = [s.latest_reliability_score for s in health_snaps if s.latest_reliability_score is not None]
    avg_rel = round(sum(rel_scores) / len(rel_scores), 1) if rel_scores else None

    cov_scores = [s.evidence_coverage_score for s in health_snaps]
    avg_cov = round(sum(cov_scores) / len(cov_scores), 1) if cov_scores else None

    # Project-level alerts (aggregate across all strategy String IDs)
    strategy_id_strs = [str(s.id) for s in strategies]
    alert_sevs: list[str] = []
    if strategy_id_strs:
        rows = (
            db.query(Alert.severity)
            .filter(
                Alert.strategy_id.in_(strategy_id_strs),
                Alert.status.in_(["open", "acknowledged", "snoozed"]),
            )
            .all()
        )
        alert_sevs = [r[0] for r in rows]

    open_alert_count = len(alert_sevs)
    critical_alerts = sum(1 for s in alert_sevs if s == "critical")
    high_alerts = sum(1 for s in alert_sevs if s == "high")
    medium_alerts = sum(1 for s in alert_sevs if s == "medium")
    low_alerts = sum(1 for s in alert_sevs if s == "low")
    high_crit_count = critical_alerts + high_alerts

    # Recent failed ingestion batches (last 7 days)
    recent_failed = 0
    if strategies:
        cutoff = now - timedelta(days=7)
        strategy_uuids = [s.id for s in strategies]
        recent_failed = (
            db.query(func.count(SdkIngestionBatch.id))
            .filter(
                SdkIngestionBatch.strategy_id.in_(strategy_uuids),
                SdkIngestionBatch.status == "failed",
            )
            .scalar()
        ) or 0

    # Latest activity (most recent run)
    latest_at: datetime | None = None
    if strategies:
        strategy_uuids = [s.id for s in strategies]
        latest_run_at = (
            db.query(func.max(StrategyRun.created_at))
            .filter(StrategyRun.strategy_id.in_(strategy_uuids))
            .scalar()
        )
        if latest_run_at:
            if latest_run_at.tzinfo is None:
                latest_run_at = latest_run_at.replace(tzinfo=timezone.utc)
            latest_at = latest_run_at

    # Compute health score
    health_score: float | None = None
    if avg_health is not None:
        score = avg_health
        score -= critical_alerts * 20
        score -= high_alerts * 10
        score -= medium_alerts * 4
        score -= low_alerts * 2
        if recent_failed > 0:
            score -= min(recent_failed * 5, 15)
        health_score = max(0.0, round(score, 1))

    health_status = _compute_project_status(
        status_counts["critical"],
        status_counts["review"],
        status_counts["watch"],
        status_counts["healthy"],
        status_counts["insufficient_evidence"],
        strategy_count,
        health_score,
        critical_alerts,
    )

    primary_concern = _project_primary_concern(
        health_status,
        status_counts["critical"],
        status_counts["review"],
        critical_alerts,
        high_alerts,
        strategy_count,
        recent_failed,
    )

    suggested: list[str] = []
    if status_counts["critical"] > 0:
        suggested.append("Resolve critical strategy health issues first")
    if critical_alerts > 0:
        suggested.append("Resolve open critical alerts")
    if recent_failed > 0:
        suggested.append("Investigate recent ingestion failures")
    if avg_rel is None:
        suggested.append("Compute reliability scores for project strategies")

    return ProjectHealthSnapshot(
        project_id=project_id,
        project_name=project.name,
        organization_id=project.organization_id,
        health_score=health_score,
        health_status=health_status,
        strategy_count=strategy_count,
        healthy_strategy_count=status_counts["healthy"],
        watch_strategy_count=status_counts["watch"],
        review_strategy_count=status_counts["review"],
        critical_strategy_count=status_counts["critical"],
        insufficient_evidence_strategy_count=status_counts["insufficient_evidence"],
        average_strategy_health_score=avg_health,
        average_reliability_score=avg_rel,
        average_evidence_coverage_score=avg_cov,
        open_alert_count=open_alert_count,
        high_critical_alert_count=high_crit_count,
        recent_failed_ingestion_count=recent_failed,
        latest_activity_at=latest_at,
        primary_concern=primary_concern,
        suggested_checks=suggested,
        generated_at=now,
    )


def get_projects_health(
    db: Session,
    *,
    organization_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[ProjectHealthSnapshot], int]:
    """Return paginated project health snapshots with optional filters."""
    from app.models.project import Project

    q = db.query(Project)
    if organization_id:
        q = q.filter(Project.organization_id == organization_id)
    q = q.order_by(Project.name)
    all_projects = q.all()
    total = len(all_projects)
    page = all_projects[offset : offset + limit]

    snaps: list[ProjectHealthSnapshot] = []
    for p in page:
        try:
            snap = compute_project_health(p.id, db)
            if status and snap.health_status != status:
                continue
            snaps.append(snap)
        except Exception:
            pass
    return snaps, total
