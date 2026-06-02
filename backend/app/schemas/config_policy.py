"""Pydantic schemas for M54 config policy engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class StrategyConfigPolicyCreate(BaseModel):
    name: str
    description: str | None = None
    is_active: bool = True
    policy_json: dict[str, Any]


class StrategyConfigPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_id: str
    name: str
    description: str | None
    is_active: bool
    policy_json: dict[str, Any]
    rule_count: int = 0
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_with_count(cls, obj: Any) -> "StrategyConfigPolicyRead":
        rules = obj.policy_json.get("rules", []) if obj.policy_json else []
        return cls(
            id=str(obj.id),
            strategy_id=str(obj.strategy_id),
            name=obj.name,
            description=obj.description,
            is_active=obj.is_active,
            policy_json=obj.policy_json,
            rule_count=len(rules),
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class ConfigPolicyEvaluationRequest(BaseModel):
    config_snapshot_id: str | None = None


class ConfigPolicyResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    evaluation_id: str
    rule_key: str
    title: str
    status: str
    severity: str
    is_required: bool
    observed_value: str | None
    expected_value: str | None
    key_path: str | None
    evidence_json: dict[str, Any] | None
    suggested_action: str | None
    created_at: datetime


class ConfigPolicyEvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_id: str
    policy_id: str
    config_snapshot_id: str | None
    overall_status: str
    passed_count: int
    warning_count: int
    failed_count: int
    skipped_count: int
    critical_failed_count: int
    result_json: Any | None
    deterministic_summary: str | None
    created_at: datetime
    results: list[ConfigPolicyResultRead] = []


class ConfigPolicyEvaluationListResponse(BaseModel):
    items: list[ConfigPolicyEvaluationRead]
    total: int
