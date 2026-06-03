"""Pydantic schemas for M65A strategy reliability snapshots."""

from __future__ import annotations

import uuid as _uuid_mod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class StrategyReliabilitySnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_id: str

    @field_validator("id", "strategy_id", mode="before")
    @classmethod
    def _coerce_uuid_to_str(cls, v: Any) -> str:
        if isinstance(v, _uuid_mod.UUID):
            return str(v)
        return v
    snapshot_status: str
    command_status: str | None
    command_score: float | None
    readiness_verdict: str | None
    readiness_score: float | None
    robustness_verdict: str | None
    robustness_score: float | None
    freeze_recommendation: str | None
    freeze_risk_score: float | None
    freshness_status: str | None
    freshness_score: float | None
    drift_status: str | None
    drift_score: float | None
    shadow_status: str | None
    shadow_score: float | None
    open_review_case_count: int
    high_critical_alert_count: int
    latest_regression_status: str | None
    latest_config_policy_status: str | None
    latest_sla_status: str | None
    top_blockers_json: Any | None
    action_queue_json: Any | None
    subsystem_statuses_json: Any | None
    deterministic_summary: str | None
    source_hash: str | None
    generated_at: datetime
    stale_after: datetime
    created_at: datetime
    is_stale: bool = False
    stale_reasons: list[str] = []


class StrategyReliabilitySnapshotListResponse(BaseModel):
    items: list[StrategyReliabilitySnapshotRead]
    total: int
