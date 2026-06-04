"""Pydantic schemas for the M74 Strategy Action Queue."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ActionItem(BaseModel):
    """A single prioritized, deterministic next-action for a strategy."""

    id: str
    strategy_id: str
    title: str
    description: str
    why_it_matters: str
    severity: str          # critical | high | medium | low | info
    priority_rank: int
    status: str            # pending | done | blocked | optional
    category: str          # evidence | readiness | governance | freshness | run_quality | assumptions | reporting | shadow | developer
    source: str            # readiness | freshness | promotion_gates | assumption_health | drift | run_history | reliability | review_cases | regression_tests | config_policy | sla | report | alerts
    target_tab: str | None = None      # overview | evidence | runs | governance | lineage | exports | developer
    target_panel_label: str | None = None
    action_label: str
    action_type: str       # navigate | generate_report | create_policy | create_regression_tests | create_sla | generate_review_cases | upload_bundle | link_evidence | refresh_snapshot | run_alert_check | no_action
    related_object_id: str | None = None
    related_object_type: str | None = None
    deterministic_reason: str
    created_from: list[str] = []


class ActionQueueResponse(BaseModel):
    """The full action queue for a strategy."""

    strategy_id: str
    strategy_name: str
    generated_at: datetime
    items: list[ActionItem] = []
    total_action_count: int
    completed_count: int
    pending_count: int
    blocked_count: int
    optional_count: int
    deterministic_summary: str
    disclaimer: str = (
        "Action Queue prioritizes research evidence tasks. "
        "It does not provide trading recommendations."
    )
