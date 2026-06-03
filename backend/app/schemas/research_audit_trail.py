"""M63: Pydantic schemas for Research Audit Trail v2."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ResearchAuditLinkedObject(BaseModel):
    object_type: str
    object_id: str
    label: str
    route_hint: str | None = None


class ResearchAuditStatusTransition(BaseModel):
    previous_status: str | None = None
    new_status: str | None = None
    status_type: str | None = None
    transition_label: str | None = None


class ResearchAuditDownstreamContext(BaseModel):
    impacted_artifact_count: int = 0
    recommended_rechecks: list[str] = []
    affected_readiness: bool = False
    affected_promotion_gates: bool = False
    affected_review_cases: bool = False
    affected_freeze_recommendation: bool = False


class ResearchAuditEvent(BaseModel):
    event_id: str
    event_time: datetime
    event_type: str
    title: str
    description: str | None = None
    severity: str
    source_type: str | None = None
    source_id: str | None = None
    category: str
    importance: str
    research_phase: str
    linked_object: ResearchAuditLinkedObject | None = None
    downstream_context: ResearchAuditDownstreamContext | None = None
    status_transition: ResearchAuditStatusTransition | None = None
    evidence_summary_json: dict[str, Any] = {}
    suggested_action: str | None = None


class ResearchAuditTrailResponse(BaseModel):
    strategy_id: str
    strategy_name: str
    generated_at: datetime
    total_events: int
    returned_count: int
    category_counts: dict[str, int] = {}
    importance_counts: dict[str, int] = {}
    phase_counts: dict[str, int] = {}
    high_importance_count: int = 0
    latest_event_at: datetime | None = None
    latest_governance_event_at: datetime | None = None
    latest_evidence_event_at: datetime | None = None
    unresolved_review_case_count: int = 0
    open_alert_count: int = 0
    latest_freeze_recommendation: str | None = None
    deterministic_summary: str
    suggested_checks: list[str] = []
    events: list[ResearchAuditEvent] = []
