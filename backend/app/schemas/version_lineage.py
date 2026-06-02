"""Pydantic schemas for M35 version lineage endpoint."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class StrategyVersionLineageItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_id: uuid.UUID
    version_label: str
    git_commit: Optional[str] = None
    branch_name: Optional[str] = None
    code_path: Optional[str] = None
    signal_name: Optional[str] = None
    signal_description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    run_count: int
    backtest_run_count: int
    research_run_count: int
    paper_run_count: int
    live_run_count: int
    config_snapshot_count: int
    universe_snapshot_count: int
    signal_snapshot_count: int
    dataset_linked_run_count: int
    backtest_audit_count: int
    latest_run_at: Optional[datetime] = None
    latest_config_snapshot_label: Optional[str] = None
    latest_universe_snapshot_label: Optional[str] = None
    latest_signal_snapshot_label: Optional[str] = None
    latest_backtest_trust_score: Optional[float] = None
    latest_data_health_score: Optional[float] = None
    latest_signal_quality_score: Optional[float] = None
    has_config: bool
    has_universe: bool
    has_signal: bool
    has_runs: bool
    has_dataset_linked_runs: bool
    has_backtest_audit: bool
    version_evidence_score: float
    lineage_status: str
    suggested_checks: List[str] = []


class StrategyVersionTransition(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_version_label: str
    to_version_label: str
    created_at_delta_days: int
    git_commit_changed: bool
    branch_changed: bool
    signal_name_changed: bool
    config_hash_changed: Optional[bool] = None
    universe_hash_changed: Optional[bool] = None
    signal_hash_changed: Optional[bool] = None


class StrategyVersionLineageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    version_count: int
    latest_version_label: Optional[str] = None
    most_instrumented_version_id: Optional[uuid.UUID] = None
    least_instrumented_version_id: Optional[uuid.UUID] = None
    average_version_evidence_score: Optional[float] = None
    versions_missing_config: int
    versions_missing_signal: int
    versions_missing_universe: int
    versions_without_runs: int
    deterministic_summary: str
    generated_at: datetime


class StrategyVersionLineageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary: StrategyVersionLineageSummary
    versions: List[StrategyVersionLineageItem]
    transitions: List[StrategyVersionTransition]
