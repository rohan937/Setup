"""M64 Pydantic schemas for Strategy Reliability Command Center."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class CommandCenterSubsystemStatus(BaseModel):
    """Status of a single reliability sub-system."""
    subsystem_key: str
    title: str
    status: str  # healthy/watch/review/blocked/missing/error
    score: Optional[float] = None
    severity: str = "info"
    summary: Optional[str] = None
    top_issue: Optional[str] = None
    suggested_action: Optional[str] = None
    route_hint: Optional[str] = None
    source_json: Optional[dict] = None

    model_config = {"from_attributes": True}


class CommandCenterBlocker(BaseModel):
    """A concrete blocker surfaced by the command center."""
    blocker_key: str
    title: str
    category: str
    severity: str
    evidence_summary: str
    source_subsystem: str
    required_before_progression: bool = False
    suggested_resolution: str = ""

    model_config = {"from_attributes": True}


class CommandCenterAction(BaseModel):
    """A recommended action surfaced by the command center."""
    action_key: str
    title: str
    priority: str  # low/medium/high/critical
    action_type: str
    reason: str
    endpoint_hint: Optional[str] = None
    route_hint: Optional[str] = None
    depends_on: list[str] = []

    model_config = {"from_attributes": True}


class CommandCenterGovernanceSummary(BaseModel):
    """Aggregated governance signal counts."""
    open_review_case_count: int = 0
    acknowledged_review_case_count: int = 0
    high_critical_alert_count: int = 0
    latest_regression_status: Optional[str] = None
    latest_policy_status: Optional[str] = None
    latest_sla_status: Optional[str] = None
    latest_freeze_recommendation: Optional[str] = None
    promotion_gate_paper_verdict: Optional[str] = None
    promotion_gate_production_verdict: Optional[str] = None

    model_config = {"from_attributes": True}


class CommandCenterEvidenceSummary(BaseModel):
    """Evidence coverage and freshness summary."""
    freshness_status: Optional[str] = None
    coverage_score: Optional[float] = None
    missing_evidence_count: int = 0
    stale_evidence_count: int = 0
    graph_status: Optional[str] = None
    replay_pack_recommended: bool = False
    latest_run_id: Optional[str] = None
    latest_run_label: Optional[str] = None

    model_config = {"from_attributes": True}


class CommandCenterWorkflowSummary(BaseModel):
    """Workflow and experiment progress summary."""
    current_stage: str = "idea"
    next_recommended_stage: str = "backtest_review"
    stage_path: list[str] = []
    active_experiment_count: int = 0
    latest_experiment_analysis_status: Optional[str] = None
    latest_sweep_status: Optional[str] = None
    latest_audit_event_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class StrategyReliabilityCommandCenterResponse(BaseModel):
    """Full Reliability Command Center response."""
    strategy_id: str
    strategy_name: str
    generated_at: datetime
    command_status: str  # clear/monitor/review/blocked/insufficient_evidence
    command_score: Optional[float]
    deterministic_summary: str
    subsystem_statuses: list[CommandCenterSubsystemStatus]
    top_blockers: list[CommandCenterBlocker]
    action_queue: list[CommandCenterAction]
    governance_summary: CommandCenterGovernanceSummary
    evidence_summary: CommandCenterEvidenceSummary
    workflow_summary: CommandCenterWorkflowSummary
    note: str

    model_config = {"from_attributes": True}
