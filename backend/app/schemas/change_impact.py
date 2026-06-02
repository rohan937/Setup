"""Pydantic schemas for M57 Strategy Change Impact Analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ChangeImpactFocusNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: str
    node_type: str
    label: str
    created_at: Optional[datetime] = None
    score: Optional[float] = None
    status: str = "unknown"
    route_hint: str = ""
    metadata_json: dict[str, Any] = {}


class ImpactedArtifact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    artifact_id: str
    artifact_type: str
    label: str
    relationship: str
    impact_level: str  # critical / high / medium / low / none
    reason: str
    current_status: str = "unknown"
    current_score: Optional[float] = None
    route_hint: str = ""
    suggested_recheck: str = ""


class RecommendedRecheck(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recheck_key: str
    title: str
    priority: str  # critical / high / medium / low
    reason: str
    endpoint_hint: str = ""
    depends_on: list[str] = []
    status: str = "pending"


class AssumptionImpactSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    has_assumption_change: bool = False
    positive_change_count: int = 0
    weakening_change_count: int = 0
    review_change_count: int = 0
    key_changes: list[dict[str, Any]] = []
    impact_level: str = "none"
    suggested_checks: list[str] = []


class QualityImpactSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quality_impact_count: int = 0
    degraded_quality_count: int = 0
    missing_quality_count: int = 0
    key_quality_findings: list[str] = []


class ReadinessImpactSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    readiness_verdict: Optional[str] = None
    promotion_risk_count: int = 0
    failed_regression_count: int = 0
    failed_policy_count: int = 0
    sla_violation_count: int = 0
    open_review_case_count: int = 0
    impact_level: str = "none"
    suggested_checks: list[str] = []


class GraphBlastRadiusSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    focus_node_id: str
    focus_node_type: str
    upstream_count: int = 0
    downstream_count: int = 0
    affected_run_count: int = 0
    affected_report_count: int = 0
    affected_alert_count: int = 0
    affected_audit_count: int = 0
    affected_readiness: bool = False
    affected_shadow_monitor: bool = False
    affected_promotion_gates: bool = False
    blast_radius_severity: str = "low"


class StrategyChangeImpactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: str
    strategy_name: str
    generated_at: str  # ISO 8601
    mode: str

    focus_node: Optional[ChangeImpactFocusNode] = None
    impact_score: float  # 0–100; higher = less impact
    impact_status: str   # no_change_detected / low / medium / high / requires_review

    assumption_impacts: AssumptionImpactSummary
    quality_impacts: QualityImpactSummary
    readiness_impacts: ReadinessImpactSummary
    graph_blast_radius: Optional[GraphBlastRadiusSummary] = None

    impacted_artifacts: list[ImpactedArtifact] = []
    recommended_rechecks: list[RecommendedRecheck] = []
    suggested_actions: list[str] = []
    deterministic_summary: str
