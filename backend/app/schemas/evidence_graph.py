"""Pydantic schemas for Evidence Graph (M52).

GET /api/strategies/{strategy_id}/evidence-graph → StrategyEvidenceGraphResponse
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EvidenceGraphNode(BaseModel):
    node_id: str
    node_type: str
    label: str
    subtitle: Optional[str] = None
    status: str
    severity: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    score: Optional[float] = None
    metadata_json: dict
    route_hint: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class EvidenceGraphEdge(BaseModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    relationship: str
    label: str
    metadata_json: dict

    model_config = ConfigDict(from_attributes=True)


class EvidenceBlastRadius(BaseModel):
    focus_node_id: str
    focus_node_type: str
    blast_radius_severity: str
    upstream_count: int
    downstream_count: int
    affected_run_count: int
    affected_report_count: int
    affected_alert_count: int
    affected_audit_count: int
    affected_readiness: bool
    affected_shadow_monitor: bool
    affected_promotion_gates: bool
    affected_nodes: list[EvidenceGraphNode]

    model_config = ConfigDict(from_attributes=True)


class EvidenceGraphSummary(BaseModel):
    strategy_id: uuid.UUID
    strategy_name: str
    generated_at: datetime
    node_count: int
    edge_count: int
    weak_node_count: int
    missing_node_count: int
    high_critical_alert_node_count: int
    connected_run_count: int
    orphan_evidence_count: int
    graph_status: str
    deterministic_summary: str
    suggested_checks: list[str]

    model_config = ConfigDict(from_attributes=True)


class StrategyEvidenceGraphResponse(BaseModel):
    summary: EvidenceGraphSummary
    nodes: list[EvidenceGraphNode]
    edges: list[EvidenceGraphEdge]
    blast_radius: Optional[EvidenceBlastRadius] = None

    model_config = ConfigDict(from_attributes=True)
