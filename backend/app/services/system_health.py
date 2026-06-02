"""System Health aggregation service (M45).

Queries all major tables and produces a single system-wide health snapshot.

Design rules:
  - Read-only — no writes, no AuditTimelineEvent creation.
  - All counts default to 0 on error (never raise).
  - All scores are null when insufficient data.
  - No AI, no live market data, no external calls.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_ts(dt: datetime | None) -> datetime | None:
    """Return datetime with UTC tzinfo, or None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def get_system_health(db: Session) -> dict:  # noqa: C901
    """Aggregate system-wide health and return a flat dict."""

    now = datetime.now(timezone.utc)

    # -----------------------------------------------------------------------
    # 1. Org + Project counts
    # -----------------------------------------------------------------------
    org_count = 0
    project_count = 0
    try:
        from app.models.organization import Organization
        from app.models.project import Project
        org_count = db.query(Organization).count() or 0
        project_count = db.query(Project).count() or 0
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # 2. Strategy counts
    # -----------------------------------------------------------------------
    strategy_count = 0
    active_strategy_count = 0
    archived_strategy_count = 0
    try:
        from app.models.strategy import Strategy
        strategy_count = db.query(Strategy).count() or 0
        active_strategy_count = db.query(Strategy).filter(Strategy.status != "archived").count() or 0
        archived_strategy_count = db.query(Strategy).filter(Strategy.status == "archived").count() or 0
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # 3. StrategyRun count
    # -----------------------------------------------------------------------
    run_count = 0
    try:
        from app.models.strategy_run import StrategyRun
        run_count = db.query(StrategyRun).count() or 0
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # 4. Dataset count
    # -----------------------------------------------------------------------
    dataset_count = 0
    try:
        from app.models.dataset import Dataset
        dataset_count = db.query(Dataset).count() or 0
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # 5. DatasetSnapshot count
    # -----------------------------------------------------------------------
    dataset_snapshot_count = 0
    try:
        from app.models.dataset_snapshot import DatasetSnapshot
        dataset_snapshot_count = db.query(DatasetSnapshot).count() or 0
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # 6. SignalSnapshot count
    # -----------------------------------------------------------------------
    signal_snapshot_count = 0
    try:
        from app.models.signal_snapshot import SignalSnapshot
        signal_snapshot_count = db.query(SignalSnapshot).count() or 0
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # 7. UniverseSnapshot count
    # -----------------------------------------------------------------------
    universe_snapshot_count = 0
    try:
        from app.models.universe_snapshot import UniverseSnapshot
        universe_snapshot_count = db.query(UniverseSnapshot).count() or 0
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # 8. StrategyConfigSnapshot count
    # -----------------------------------------------------------------------
    config_snapshot_count = 0
    try:
        from app.models.strategy_config_snapshot import StrategyConfigSnapshot
        config_snapshot_count = db.query(StrategyConfigSnapshot).count() or 0
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # 9. BacktestAudit count
    # -----------------------------------------------------------------------
    backtest_audit_count = 0
    try:
        from app.models.backtest_audit import BacktestAudit
        backtest_audit_count = db.query(BacktestAudit).count() or 0
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # 10. Alert counts
    # -----------------------------------------------------------------------
    alert_count = 0
    open_alert_count = 0
    high_critical_alert_count = 0
    try:
        from app.models.alert import Alert
        alert_count = db.query(Alert).count() or 0
        open_alert_count = (
            db.query(Alert)
            .filter(Alert.status.in_(["open", "acknowledged", "snoozed"]))
            .count() or 0
        )
        high_critical_alert_count = (
            db.query(Alert)
            .filter(
                Alert.severity.in_(["high", "critical"]),
                Alert.status == "open",
            )
            .count() or 0
        )
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # 11. Report count
    # -----------------------------------------------------------------------
    report_count = 0
    try:
        from app.models.report import Report
        report_count = db.query(Report).count() or 0
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # 12. AuditTimelineEvent count
    # -----------------------------------------------------------------------
    timeline_event_count = 0
    try:
        from app.models.audit_timeline_event import AuditTimelineEvent
        timeline_event_count = db.query(AuditTimelineEvent).count() or 0
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # 13. ApiKey counts
    # -----------------------------------------------------------------------
    api_key_count = 0
    active_api_key_count = 0
    revoked_api_key_count = 0
    try:
        from app.models.api_key import ApiKey
        api_key_count = db.query(ApiKey).count() or 0
        active_api_key_count = db.query(ApiKey).filter(ApiKey.status == "active").count() or 0
        revoked_api_key_count = db.query(ApiKey).filter(ApiKey.status == "revoked").count() or 0
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # 14. SdkIngestionBatch stats
    # -----------------------------------------------------------------------
    ingestion_total = 0
    ingestion_completed = 0
    ingestion_failed = 0
    ingestion_recent_failed = 0
    latest_batch_at: datetime | None = None
    latest_failed_batch_at: datetime | None = None
    try:
        from app.models.sdk_ingestion_batch import SdkIngestionBatch
        ingestion_total = db.query(SdkIngestionBatch).count() or 0
        ingestion_completed = (
            db.query(SdkIngestionBatch)
            .filter(SdkIngestionBatch.status == "completed")
            .count() or 0
        )
        ingestion_failed = (
            db.query(SdkIngestionBatch)
            .filter(SdkIngestionBatch.status == "failed")
            .count() or 0
        )
        cutoff_7d = now - timedelta(days=7)
        ingestion_recent_failed = (
            db.query(SdkIngestionBatch)
            .filter(
                SdkIngestionBatch.status == "failed",
                SdkIngestionBatch.created_at >= cutoff_7d,
            )
            .count() or 0
        )
        latest_row = (
            db.query(SdkIngestionBatch)
            .order_by(SdkIngestionBatch.created_at.desc())
            .first()
        )
        if latest_row is not None:
            latest_batch_at = _normalize_ts(latest_row.created_at)
        failed_row = (
            db.query(SdkIngestionBatch)
            .filter(SdkIngestionBatch.status == "failed")
            .order_by(SdkIngestionBatch.created_at.desc())
            .first()
        )
        if failed_row is not None:
            latest_failed_batch_at = _normalize_ts(failed_row.created_at)
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # 15. API key health metrics
    # -----------------------------------------------------------------------
    keys_used_last_7d = 0
    keys_never_used = 0
    stale_keys_count = 0
    try:
        from app.models.api_key import ApiKey
        cutoff_7d = now - timedelta(days=7)
        cutoff_90d = now - timedelta(days=90)
        keys_used_last_7d = (
            db.query(ApiKey)
            .filter(ApiKey.last_used_at >= cutoff_7d)
            .count() or 0
        )
        keys_never_used = (
            db.query(ApiKey)
            .filter(ApiKey.status == "active", ApiKey.last_used_at.is_(None))
            .count() or 0
        )
        stale_keys_count = (
            db.query(ApiKey)
            .filter(
                ApiKey.status == "active",
                (ApiKey.last_used_at.is_(None)) | (ApiKey.last_used_at <= cutoff_90d),
            )
            .count() or 0
        )
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # 16. Evidence activity (AuditTimelineEvent)
    # -----------------------------------------------------------------------
    events_last_24h = 0
    events_last_7d = 0
    events_last_30d = 0
    latest_event_at: datetime | None = None
    try:
        from app.models.audit_timeline_event import AuditTimelineEvent
        cutoff_24h = now - timedelta(hours=24)
        cutoff_7d = now - timedelta(days=7)
        cutoff_30d = now - timedelta(days=30)
        events_last_24h = (
            db.query(AuditTimelineEvent)
            .filter(AuditTimelineEvent.event_time >= cutoff_24h)
            .count() or 0
        )
        events_last_7d = (
            db.query(AuditTimelineEvent)
            .filter(AuditTimelineEvent.event_time >= cutoff_7d)
            .count() or 0
        )
        events_last_30d = (
            db.query(AuditTimelineEvent)
            .filter(AuditTimelineEvent.event_time >= cutoff_30d)
            .count() or 0
        )
        latest_event_row = (
            db.query(AuditTimelineEvent)
            .order_by(AuditTimelineEvent.event_time.desc())
            .first()
        )
        if latest_event_row is not None:
            latest_event_at = _normalize_ts(latest_event_row.event_time)
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # Derived statuses
    # -----------------------------------------------------------------------

    # Ingestion status
    if ingestion_total == 0:
        ingestion_status = "no_batches"
    else:
        failure_rate = ingestion_failed / ingestion_total
        if failure_rate > 0.10 or ingestion_recent_failed >= 3:
            ingestion_status = "degraded"
        elif failure_rate > 0:
            ingestion_status = "watch"
        else:
            ingestion_status = "healthy"

    # API key status
    if stale_keys_count > 0:
        api_key_status = "review"
    elif (
        keys_never_used > active_api_key_count * 0.5
        and active_api_key_count > 2
    ):
        api_key_status = "watch"
    else:
        api_key_status = "healthy"

    # Evidence activity status
    if latest_event_at is None:
        activity_status = "no_activity"
    else:
        days_since = (now - latest_event_at).days
        if days_since <= 7:
            activity_status = "active"
        elif days_since <= 30:
            activity_status = "quiet"
        else:
            activity_status = "stale"

    # -----------------------------------------------------------------------
    # Strategy health rollup (via portfolio_overview)
    # -----------------------------------------------------------------------
    status_counts: dict = {}
    requiring_review: list = []
    try:
        from app.services.portfolio_overview import get_portfolio_overview
        po, _ = get_portfolio_overview(db, limit_per_section=5)
        status_counts = po.strategies_by_health_status
        requiring_review = [
            {
                "id": str(item.strategy_id),
                "name": item.name,
                "status": item.health_status,
            }
            for item in po.top_review_strategies[:5]
        ]
    except Exception:
        status_counts = {}
        requiring_review = []

    # -----------------------------------------------------------------------
    # Project health rollup
    # -----------------------------------------------------------------------
    proj_status_counts: dict = {}
    proj_requiring_review: list = []
    try:
        from app.services.project_health import get_projects_health
        projects, _total = get_projects_health(db, limit=20)
        proj_status_counts = {}
        for p in projects:
            proj_status_counts[p.health_status] = proj_status_counts.get(p.health_status, 0) + 1
        proj_requiring_review = [
            {"id": str(p.project_id), "name": p.project_name, "status": p.health_status}
            for p in projects
            if p.health_status in ("critical", "review")
        ][:5]
    except Exception:
        proj_status_counts = {}
        proj_requiring_review = []

    # -----------------------------------------------------------------------
    # Recent activity (top 10 combined from batches + timeline events)
    # -----------------------------------------------------------------------
    recent_activity: list = []
    try:
        from app.models.sdk_ingestion_batch import SdkIngestionBatch
        batches = (
            db.query(SdkIngestionBatch)
            .order_by(SdkIngestionBatch.created_at.desc())
            .limit(5)
            .all()
        )
        for b in batches:
            recent_activity.append({
                "item_type": "ingestion_batch",
                "title": f"Ingestion {b.status}",
                "timestamp": _normalize_ts(b.created_at),
                "detail": b.status,
            })
    except Exception:
        pass

    try:
        from app.models.audit_timeline_event import AuditTimelineEvent
        events = (
            db.query(AuditTimelineEvent)
            .order_by(AuditTimelineEvent.event_time.desc())
            .limit(5)
            .all()
        )
        for e in events:
            recent_activity.append({
                "item_type": "timeline_event",
                "title": e.title or e.event_type,
                "timestamp": _normalize_ts(e.event_time),
                "detail": e.event_type,
            })
    except Exception:
        pass

    recent_activity.sort(
        key=lambda x: _normalize_ts(x["timestamp"]) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    recent_activity = recent_activity[:10]

    # -----------------------------------------------------------------------
    # System score
    # -----------------------------------------------------------------------
    score = 100.0
    if ingestion_status == "degraded":
        score -= 25
    elif ingestion_status == "watch":
        score -= 10

    score -= min(high_critical_alert_count * 5, 25)

    if api_key_status == "review":
        score -= 10
    elif api_key_status == "watch":
        score -= 5

    if activity_status in ("stale", "no_activity"):
        score -= 15
    elif activity_status == "quiet":
        score -= 8

    insuff = status_counts.get("insufficient_evidence", 0)
    score -= min(insuff * 3, 25)

    score = max(0.0, round(score, 1))

    # -----------------------------------------------------------------------
    # System status
    # -----------------------------------------------------------------------
    hc = high_critical_alert_count
    failed_batches = ingestion_failed
    stale_keys = stale_keys_count

    if ingestion_status == "degraded" or (hc > 0 and status_counts.get("critical", 0) > 0):
        system_status = "degraded"
    elif (
        failed_batches > 0
        or stale_keys > 0
        or status_counts.get("review", 0) > 3
    ):
        system_status = "review"
    elif open_alert_count > 0 or activity_status in ("quiet", "stale"):
        system_status = "watch"
    else:
        system_status = "healthy"

    # -----------------------------------------------------------------------
    # Suggested checks
    # -----------------------------------------------------------------------
    checks: list[str] = []
    if failed_batches > 0:
        checks.append("Review failed SDK ingestion batches.")
    if stale_keys > 0:
        checks.append("Revoke or rotate stale API keys.")
    if activity_status in ("stale", "no_activity"):
        checks.append("Generate alerts for strategies with stale evidence.")
    if insuff > 0:
        checks.append("Improve evidence coverage for under-instrumented strategies.")
    if not checks:
        checks.append("System appears healthy. Run evidence coverage matrix before demos.")

    # -----------------------------------------------------------------------
    # Environment info
    # -----------------------------------------------------------------------
    env_name = "local"
    db_type = "unknown"
    try:
        from app.core.config import get_settings
        settings = get_settings()
        env_name = getattr(settings, "environment", "local")
        db_url = getattr(settings, "database_url", "")
        db_url_str = str(db_url).lower()
        if "sqlite" in db_url_str:
            db_type = "sqlite"
        elif "postgresql" in db_url_str:
            db_type = "postgresql"
        else:
            db_type = "unknown"
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # Return flat dict
    # -----------------------------------------------------------------------
    return {
        "generated_at": now,
        "environment": env_name,
        "db_type": db_type,
        "note": "M45 system health snapshot — deterministic, read-only.",
        "system_status": system_status,
        "system_score": score,
        # Entity counts
        "organization_count": org_count,
        "project_count": project_count,
        "strategy_count": strategy_count,
        "active_strategy_count": active_strategy_count,
        "archived_strategy_count": archived_strategy_count,
        "run_count": run_count,
        "dataset_count": dataset_count,
        "dataset_snapshot_count": dataset_snapshot_count,
        "signal_snapshot_count": signal_snapshot_count,
        "universe_snapshot_count": universe_snapshot_count,
        "config_snapshot_count": config_snapshot_count,
        "backtest_audit_count": backtest_audit_count,
        "alert_count": alert_count,
        "open_alert_count": open_alert_count,
        "high_critical_alert_count": high_critical_alert_count,
        "report_count": report_count,
        "timeline_event_count": timeline_event_count,
        "api_key_count": api_key_count,
        "active_api_key_count": active_api_key_count,
        "revoked_api_key_count": revoked_api_key_count,
        "ingestion_batch_count": ingestion_total,
        "failed_ingestion_batch_count": ingestion_failed,
        "completed_ingestion_batch_count": ingestion_completed,
        # Ingestion health
        "ingestion_total_batches": ingestion_total,
        "ingestion_completed_batches": ingestion_completed,
        "ingestion_failed_batches": ingestion_failed,
        "ingestion_recent_failed_batches": ingestion_recent_failed,
        "ingestion_failure_rate": (ingestion_failed / ingestion_total) if ingestion_total > 0 else 0.0,
        "ingestion_latest_batch_at": latest_batch_at,
        "ingestion_latest_failed_batch_at": latest_failed_batch_at,
        "ingestion_status": ingestion_status,
        # API key health
        "api_key_active_count": active_api_key_count,
        "api_key_revoked_count": revoked_api_key_count,
        "api_keys_used_last_7d": keys_used_last_7d,
        "api_keys_never_used": keys_never_used,
        "api_key_stale_count": stale_keys_count,
        "api_key_status": api_key_status,
        # Evidence activity
        "evidence_events_last_24h": events_last_24h,
        "evidence_events_last_7d": events_last_7d,
        "evidence_events_last_30d": events_last_30d,
        "evidence_latest_event_at": latest_event_at,
        "evidence_activity_status": activity_status,
        # Rollups
        "strategy_count_by_health_status": status_counts,
        "strategies_requiring_review": requiring_review,
        "project_count_by_health_status": proj_status_counts,
        "projects_requiring_review": proj_requiring_review,
        # Recent activity
        "recent_activity": recent_activity,
        # Suggested checks
        "suggested_operational_checks": checks,
    }
