"""Pydantic schemas for strategy health snapshots (M27).

GET /api/strategies/health          → StrategyHealthListResponse
GET /api/strategies/{id}/health     → StrategyHealthRead
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StrategyHealthRead(BaseModel):
    strategy_id: uuid.UUID
    strategy_name: str
    asset_class: str
    status: str
    health_score: float | None
    health_status: str
    primary_concern: str
    latest_run_at: datetime | None
    days_since_latest_run: int | None
    latest_reliability_score: float | None
    reliability_status: str | None
    evidence_coverage_score: float
    open_alert_count: int
    high_critical_alert_count: int
    latest_ingestion_status: str | None
    latest_ingestion_at: datetime | None
    latest_backtest_trust_score: float | None
    latest_data_health_score: float | None
    latest_signal_quality_score: float | None
    latest_report_score: float | None
    missing_evidence: list[str]
    suggested_checks: list[str]
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StrategyHealthListResponse(BaseModel):
    items: list[StrategyHealthRead]
    total: int
    limit: int
    offset: int
    generated_at: datetime
