"""Admin routes — M45 System Health, M46 Demo Seed.

GET  /api/admin/system-health  — full system health snapshot (read-only).
POST /api/admin/seed-demo      — seed / reset demo data.
GET  /api/admin/demo-status    — describe current demo data state.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.system_health import (
    SystemApiKeyHealth,
    SystemEntityCounts,
    SystemEvidenceActivity,
    SystemHealthResponse,
    SystemIngestionHealth,
    SystemOperationalActivityItem,
    SystemProjectHealthRollup,
    SystemStrategyHealthRollup,
)
from app.schemas.demo_seed import DemoSeedRequest, DemoSeedResponse, DemoStatusResponse
from app.schemas.deployment_readiness import (
    DeploymentReadinessCheck,
    DeploymentReadinessCategory,
    DeploymentReadinessResponse,
)

router = APIRouter(tags=["admin"])


@router.get("/admin/system-health", response_model=SystemHealthResponse)
def get_system_health_endpoint(db: Session = Depends(get_db)) -> SystemHealthResponse:
    """Return a comprehensive system health snapshot.

    Read-only — no database writes occur.
    """
    from app.services.system_health import get_system_health

    r = get_system_health(db)

    entity_counts = SystemEntityCounts(
        organization_count=r.get("organization_count", 0),
        project_count=r.get("project_count", 0),
        strategy_count=r.get("strategy_count", 0),
        active_strategy_count=r.get("active_strategy_count", 0),
        archived_strategy_count=r.get("archived_strategy_count", 0),
        run_count=r.get("run_count", 0),
        dataset_count=r.get("dataset_count", 0),
        dataset_snapshot_count=r.get("dataset_snapshot_count", 0),
        signal_snapshot_count=r.get("signal_snapshot_count", 0),
        universe_snapshot_count=r.get("universe_snapshot_count", 0),
        config_snapshot_count=r.get("config_snapshot_count", 0),
        backtest_audit_count=r.get("backtest_audit_count", 0),
        alert_count=r.get("alert_count", 0),
        open_alert_count=r.get("open_alert_count", 0),
        high_critical_alert_count=r.get("high_critical_alert_count", 0),
        report_count=r.get("report_count", 0),
        timeline_event_count=r.get("timeline_event_count", 0),
        api_key_count=r.get("api_key_count", 0),
        active_api_key_count=r.get("active_api_key_count", 0),
        revoked_api_key_count=r.get("revoked_api_key_count", 0),
        ingestion_batch_count=r.get("ingestion_batch_count", 0),
        failed_ingestion_batch_count=r.get("failed_ingestion_batch_count", 0),
        completed_ingestion_batch_count=r.get("completed_ingestion_batch_count", 0),
    )

    ingestion_health = SystemIngestionHealth(
        total_batches=r.get("ingestion_total_batches", 0),
        completed_batches=r.get("ingestion_completed_batches", 0),
        failed_batches=r.get("ingestion_failed_batches", 0),
        recent_failed_batches_count=r.get("ingestion_recent_failed_batches", 0),
        failure_rate=r.get("ingestion_failure_rate", 0.0),
        latest_batch_at=r.get("ingestion_latest_batch_at"),
        latest_failed_batch_at=r.get("ingestion_latest_failed_batch_at"),
        ingestion_status=r.get("ingestion_status", "no_batches"),
    )

    api_key_health = SystemApiKeyHealth(
        active_api_keys=r.get("api_key_active_count", 0),
        revoked_api_keys=r.get("api_key_revoked_count", 0),
        keys_used_last_7d=r.get("api_keys_used_last_7d", 0),
        keys_never_used=r.get("api_keys_never_used", 0),
        stale_keys_count=r.get("api_key_stale_count", 0),
        api_key_status=r.get("api_key_status", "healthy"),
    )

    evidence_activity = SystemEvidenceActivity(
        events_last_24h=r.get("evidence_events_last_24h", 0),
        events_last_7d=r.get("evidence_events_last_7d", 0),
        events_last_30d=r.get("evidence_events_last_30d", 0),
        latest_event_at=r.get("evidence_latest_event_at"),
        activity_status=r.get("evidence_activity_status", "no_activity"),
    )

    project_health_rollup = SystemProjectHealthRollup(
        project_count_by_health_status=r.get("project_count_by_health_status", {}),
        projects_requiring_review=r.get("projects_requiring_review", []),
        healthiest_projects=[],
    )

    strategy_health_rollup = SystemStrategyHealthRollup(
        strategy_count_by_health_status=r.get("strategy_count_by_health_status", {}),
        strategies_requiring_review=r.get("strategies_requiring_review", []),
        most_active_strategies=[],
    )

    recent_activity = [
        SystemOperationalActivityItem(
            item_type=item.get("item_type", ""),
            title=item.get("title", ""),
            timestamp=item.get("timestamp"),
            detail=item.get("detail"),
        )
        for item in r.get("recent_activity", [])
    ]

    return SystemHealthResponse(
        generated_at=r["generated_at"],
        environment=r.get("environment", "local"),
        db_type=r.get("db_type", "unknown"),
        note=r.get("note", ""),
        system_status=r.get("system_status", "unknown"),
        system_score=r.get("system_score"),
        entity_counts=entity_counts,
        ingestion_health=ingestion_health,
        api_key_health=api_key_health,
        evidence_activity=evidence_activity,
        project_health_rollup=project_health_rollup,
        strategy_health_rollup=strategy_health_rollup,
        recent_activity=recent_activity,
        suggested_operational_checks=r.get("suggested_operational_checks", []),
    )


# ---------------------------------------------------------------------------
# M46: Demo seed endpoints
# ---------------------------------------------------------------------------


@router.post("/admin/seed-demo", response_model=DemoSeedResponse)
def seed_demo_endpoint(
    payload: DemoSeedRequest,
    db: Session = Depends(get_db),
) -> DemoSeedResponse:
    """Seed (or reset) the demo dataset.

    POST with mode="extend" (default) to create missing records.
    POST with mode="reset_demo_only" and confirm_reset=true to wipe and reseed.
    """
    from app.services.demo_seed import seed_demo_data

    try:
        result = seed_demo_data(
            db,
            mode=payload.mode,
            confirm_reset=payload.confirm_reset,
            include_reports=payload.include_reports,
            include_alerts=payload.include_alerts,
            include_backtest_audits=payload.include_backtest_audits,
        )
        return DemoSeedResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Demo seed failed: {str(exc)[:200]}",
        )


@router.get("/admin/demo-status", response_model=DemoStatusResponse)
def demo_status_endpoint(db: Session = Depends(get_db)) -> DemoStatusResponse:
    """Return the current state of the demo dataset (read-only)."""
    from app.services.demo_seed import get_demo_status

    result = get_demo_status(db)
    return DemoStatusResponse(**result)


# ---------------------------------------------------------------------------
# M65: Deployment Readiness Checklist
# ---------------------------------------------------------------------------


@router.get("/admin/deployment-readiness", response_model=DeploymentReadinessResponse)
def deployment_readiness_endpoint(
    db: Session = Depends(get_db),
) -> DeploymentReadinessResponse:
    """Return a structured deployment readiness checklist.

    Read-only — no database writes occur. Inspects repository structure,
    configuration files, and service availability to produce a scored
    checklist across seven categories.
    """
    from app.services.deployment_readiness import get_deployment_readiness

    data = get_deployment_readiness(db)

    categories = [
        DeploymentReadinessCategory(
            category_key=cat.category_key,
            title=cat.title,
            status=cat.status,
            pass_count=cat.pass_count,
            warning_count=cat.warning_count,
            fail_count=cat.fail_count,
            manual_count=cat.manual_count,
            checks=[
                DeploymentReadinessCheck(
                    check_key=c.check_key,
                    title=c.title,
                    category=c.category,
                    status=c.status,
                    severity=c.severity,
                    observed_value=c.observed_value,
                    expected_value=c.expected_value,
                    explanation=c.explanation,
                    suggested_action=c.suggested_action,
                )
                for c in cat.checks
            ],
        )
        for cat in data.categories
    ]

    return DeploymentReadinessResponse(
        generated_at=data.generated_at,
        overall_status=data.overall_status,
        readiness_score=data.readiness_score,
        pass_count=data.pass_count,
        warning_count=data.warning_count,
        fail_count=data.fail_count,
        manual_count=data.manual_count,
        blocker_count=data.blocker_count,
        categories=categories,
        blockers=data.blockers,
        warnings=data.warnings,
        suggested_next_steps=data.suggested_next_steps,
        deterministic_summary=data.deterministic_summary,
    )
