"""Pydantic schemas for M38 signal quality drill-down."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SignalDistributionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signal_column: str
    value_count: int
    missing_count: int
    non_numeric_count: int
    mean_value: float | None
    median_value: float | None
    min_value: float | None
    max_value: float | None
    stddev_value: float | None
    zero_count: int
    positive_count: int
    negative_count: int
    unique_value_count: int
    outlier_count: int
    extreme_positive_count: int
    extreme_negative_count: int
    distribution_status: str
    issues: list[str]


class SymbolSignalQualityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    row_count: int
    signal_value_count: int
    missing_signal_count: int
    missing_rate: float
    non_numeric_count: int
    min_timestamp: str | None
    max_timestamp: str | None
    mean_value: float | None
    stddev_value: float | None
    outlier_count: int
    duplicate_timestamp_count: int
    quality_status: str
    issues: list[str]


class SignalTimestampCoverageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_timestamp_count: int
    duplicate_symbol_timestamp_count: int
    invalid_timestamp_count: int
    min_timestamp: str | None
    max_timestamp: str | None
    symbols_with_gaps_count: int | None
    timestamp_status: str


class SignalRowQualitySampleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_index: int
    issue_type: str
    severity: str
    symbol: str | None
    timestamp: str | None
    signal_value: str | None
    evidence_json: dict[str, Any]
    summary: str


class SignalRowQualitySamplesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    missing_signal_rows: list[SignalRowQualitySampleRead] = []
    non_numeric_signal_rows: list[SignalRowQualitySampleRead] = []
    duplicate_symbol_timestamp_rows: list[SignalRowQualitySampleRead] = []
    outlier_signal_rows: list[SignalRowQualitySampleRead] = []
    invalid_timestamp_rows: list[SignalRowQualitySampleRead] = []


class SignalQualitySummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_rows: int
    symbol_count: int
    signal_value_count: int
    missing_signal_count: int
    non_numeric_signal_count: int
    outlier_count: int
    duplicate_symbol_timestamp_count: int
    invalid_timestamp_count: int
    clean_symbol_count: int
    review_symbol_count: int
    weak_symbol_count: int
    unusable_symbol_count: int
    worst_symbols: list[str]
    suggested_checks: list[str]


class SignalQualityDrilldownResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    snapshot_id: str
    strategy_id: str
    label: str
    signal_name: str | None
    quality_score: int | None
    row_count: int
    symbol_count: int
    generated_at: datetime
    signal_distribution: SignalDistributionRead
    symbol_quality: list[SymbolSignalQualityRead]
    timestamp_coverage: SignalTimestampCoverageRead
    row_quality: SignalRowQualitySamplesRead
    quality_summary: SignalQualitySummaryRead
    warnings: list[str] = []
