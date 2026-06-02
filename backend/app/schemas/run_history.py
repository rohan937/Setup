"""Pydantic schemas for M29 run history and timeline drilldown endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class StrategyVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_id: uuid.UUID
    version_label: Optional[str] = None
    git_commit: Optional[str] = None
    branch_name: Optional[str] = None
    signal_name: Optional[str] = None


class DatasetEvidence(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_snapshot_id: uuid.UUID
    dataset_name: str
    snapshot_label: str
    health_score: int
    issue_count: int
    worst_severity: Optional[str] = None


class UniverseEvidence(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    universe_snapshot_id: uuid.UUID
    label: str
    symbol_count: int
    universe_hash: str


class SignalEvidence(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signal_snapshot_id: uuid.UUID
    label: str
    signal_name: Optional[str] = None
    quality_score: int
    missing_signal_count: int
    symbol_count: int
    mean_value: Optional[float] = None
    stddev_value: Optional[float] = None


class BacktestAuditSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audit_id: uuid.UUID
    trust_score: int
    overall_status: str
    issue_count: int
    high_critical_issue_count: int
    cost_fragility_level: Optional[str] = None
    fill_realism_level: Optional[str] = None


class StrategyRunHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: uuid.UUID
    run_name: str
    run_type: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    params_json: Optional[dict] = None
    assumptions_json: Optional[dict] = None
    metrics_json: Optional[dict] = None
    notes: Optional[str] = None
    strategy_version: Optional[StrategyVersionSummary] = None
    dataset_evidence: Optional[DatasetEvidence] = None
    universe_evidence: Optional[UniverseEvidence] = None
    signal_evidence: Optional[SignalEvidence] = None
    backtest_audit: Optional[BacktestAuditSummarySchema] = None
    has_dataset_evidence: bool
    has_universe_evidence: bool
    has_signal_evidence: bool
    has_backtest_audit: bool
    has_strategy_version: bool
    run_health_label: str


class StrategyRunHistorySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_runs: int
    strong_count: int
    usable_count: int
    review_count: int
    weak_count: int
    insufficient_evidence_count: int
    runs_missing_dataset: int
    runs_missing_signal: int
    runs_missing_universe: int
    runs_missing_audit: int
    latest_run_at: Optional[datetime] = None


class StrategyRunHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[StrategyRunHistoryItem]
    total: int
    limit: int
    offset: int
    summary: StrategyRunHistorySummary


class StrategyTimelineDrilldownItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: uuid.UUID
    event_type: str
    title: str
    description: Optional[str] = None
    severity: str
    event_time: datetime
    created_at: datetime
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    evidence_category: str
    source_label: str
    linked_url_hint: Optional[str] = None


class StrategyTimelineDrilldownSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_events: int
    event_type_counts: dict
    source_type_counts: dict
    latest_event_at: Optional[datetime] = None


class StrategyTimelineDrilldownResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[StrategyTimelineDrilldownItem]
    total: int
    limit: int
    offset: int
    summary: StrategyTimelineDrilldownSummary
