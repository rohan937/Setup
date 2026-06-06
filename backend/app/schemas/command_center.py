"""Pydantic schemas for M106 Research Command Center.

Read-only workspace-triage aggregation response. Mirrors the dict shape built by
:func:`app.services.command_center.build_command_center`.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CommandCenterWorkspaceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_count: int
    healthy_count: int
    review_count: int
    blocked_count: int
    open_alert_count: int
    high_critical_alert_count: int
    pending_action_count: int
    pending_review_count: int
    production_ready_count: int


class CommandCenterAction(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: str
    strategy_name: str | None = None
    title: str | None = None
    severity: str | None = None
    category: str | None = None
    recommended_action: str | None = None
    target_tab: str | None = None


class CommandCenterAttentionStrategy(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: str
    name: str | None = None
    slug: str | None = None
    lifecycle_stage: str | None = None
    health_classification: str | None = None
    reliability_score: float | None = None
    primary_concern: str | None = None
    top_blocker_title: str | None = None
    open_alert_count: int


class CommandCenterPendingReview(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_id: str
    strategy_id: str
    strategy_name: str | None = None
    target_stage: str | None = None
    status: str | None = None
    reviewer_user_id: str | None = None


class CommandCenterAlert(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None = None
    severity: str | None = None
    strategy_id: str | None = None
    rule_type: str | None = None


class CommandCenterLifecycleStage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    count: int
    blocked_count: int


class CommandCenterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_summary: CommandCenterWorkspaceSummary
    lifecycle_summary: list[CommandCenterLifecycleStage]
    top_actions: list[CommandCenterAction]
    strategies_needing_attention: list[CommandCenterAttentionStrategy]
    pending_reviews: list[CommandCenterPendingReview]
    top_alerts: list[CommandCenterAlert]
    generated_at: datetime
    disclaimer: str
