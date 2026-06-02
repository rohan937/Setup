"""Pydantic schemas for M55 research review cases."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


def _uuid_to_str(v: Any) -> str:
    if v is None:
        return v  # type: ignore[return-value]
    return str(v)


class ResearchReviewCaseEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    event_type: str
    title: str
    description: str | None
    metadata_json: dict[str, Any] | None
    created_at: datetime

    @field_validator("id", "case_id", mode="before")
    @classmethod
    def coerce_id(cls, v: Any) -> str:
        return str(v)


class ResearchReviewCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_id: str

    @field_validator("id", "strategy_id", mode="before")
    @classmethod
    def coerce_ids(cls, v: Any) -> str:
        return str(v)
    title: str
    case_key: str
    status: str
    severity: str
    category: str
    summary: str | None
    deterministic_summary: str | None
    evidence_json: dict[str, Any] | None
    suggested_actions_json: list[str] | None
    linked_alert_ids_json: list[str] | None
    linked_regression_run_ids_json: list[str] | None
    linked_policy_evaluation_ids_json: list[str] | None
    linked_backtest_audit_ids_json: list[str] | None
    linked_run_ids_json: list[str] | None
    linked_snapshot_ids_json: list[str] | None
    opened_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    events: list[ResearchReviewCaseEventRead] = []


class ResearchReviewCaseGenerateResponse(BaseModel):
    strategy_id: str
    generated_count: int
    refreshed_count: int
    total_open: int
    cases: list[ResearchReviewCaseRead]


class ResearchReviewCaseListResponse(BaseModel):
    items: list[ResearchReviewCaseRead]
    total: int
