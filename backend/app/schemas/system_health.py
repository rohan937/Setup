"""Pydantic schemas for System Health — M45."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SystemEntityCounts(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_count: int
    project_count: int
    strategy_count: int
    active_strategy_count: int
    archived_strategy_count: int
    run_count: int
    dataset_count: int
    dataset_snapshot_count: int
    signal_snapshot_count: int
    universe_snapshot_count: int
    config_snapshot_count: int
    backtest_audit_count: int
    alert_count: int
    open_alert_count: int
    high_critical_alert_count: int
    report_count: int
    timeline_event_count: int
    api_key_count: int
    active_api_key_count: int
    revoked_api_key_count: int
    ingestion_batch_count: int
    failed_ingestion_batch_count: int
    completed_ingestion_batch_count: int


class SystemIngestionHealth(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_batches: int
    completed_batches: int
    failed_batches: int
    recent_failed_batches_count: int
    failure_rate: float
    latest_batch_at: datetime | None
    latest_failed_batch_at: datetime | None
    ingestion_status: str


class SystemApiKeyHealth(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    active_api_keys: int
    revoked_api_keys: int
    keys_used_last_7d: int
    keys_never_used: int
    stale_keys_count: int
    api_key_status: str


class SystemEvidenceActivity(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    events_last_24h: int
    events_last_7d: int
    events_last_30d: int
    latest_event_at: datetime | None
    activity_status: str


class SystemProjectHealthRollup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_count_by_health_status: dict[str, int]
    projects_requiring_review: list[dict]
    healthiest_projects: list[dict]


class SystemStrategyHealthRollup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_count_by_health_status: dict[str, int]
    strategies_requiring_review: list[dict]
    most_active_strategies: list[dict]


class SystemOperationalActivityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_type: str
    title: str
    timestamp: datetime | None
    detail: str | None


class SystemHealthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    generated_at: datetime
    environment: str
    db_type: str
    note: str
    system_status: str
    system_score: float | None
    entity_counts: SystemEntityCounts
    ingestion_health: SystemIngestionHealth
    api_key_health: SystemApiKeyHealth
    evidence_activity: SystemEvidenceActivity
    project_health_rollup: SystemProjectHealthRollup
    strategy_health_rollup: SystemStrategyHealthRollup
    recent_activity: list[SystemOperationalActivityItem]
    suggested_operational_checks: list[str]
