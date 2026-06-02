"""Pydantic schemas for Strategy Comparison Report (M44)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StrategyComparisonReportRequest(BaseModel):
    strategy_ids: list[str]
    format: str = "json"
    include_raw_json: bool = False


class StrategyComparisonReportMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: str
    generated_at: datetime
    format: str
    note: str
    strategy_count: int
    strategy_ids: list[str]


class StrategyComparisonReportSection(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    section_key: str
    title: str
    summary: str
    severity: str | None = None
    evidence_json: dict[str, Any] | None = None


class StrategyComparisonReportStrategySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: UUID
    name: str
    asset_class: str
    status: str
    health_status: str | None = None
    health_score: float | None = None
    primary_concern: str | None = None
    reliability_score: float | None = None
    reliability_status: str | None = None
    evidence_coverage_score: float | None = None
    assumption_status: str | None = None
    assumption_score: float | None = None
    weakening_change_count: int = 0
    positive_change_count: int = 0
    open_alert_count: int = 0
    high_critical_alert_count: int = 0
    reliability_trend: str | None = None
    data_health_trend: str | None = None
    backtest_trust_trend: str | None = None
    signal_quality_trend: str | None = None
    suggested_checks: list[str] = []


class StrategyComparisonReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    format: str
    filename: str
    metadata: StrategyComparisonReportMetadata
    sections: list[StrategyComparisonReportSection]
    strategy_summaries: list[StrategyComparisonReportStrategySummary]
    rankings: dict[str, Any]
    suggested_review_agenda: list[str]
    content: str | None = None
    raw_evidence: dict[str, Any] | None = None
