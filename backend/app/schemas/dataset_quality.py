"""Pydantic schemas for M37 dataset quality drill-down."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ColumnQualityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    column_name: str
    inferred_type: str
    non_null_count: int
    null_count: int
    null_rate: float
    unique_count: int
    duplicate_value_count: int
    numeric_count: int
    string_count: int
    boolean_count: int
    timestamp_parseable_count: int
    invalid_timestamp_count: int
    min_value: float | None
    max_value: float | None
    mean_value: float | None
    stddev_value: float | None
    zero_count: int
    negative_count: int
    outlier_count: int
    sample_values: list[str]
    quality_status: str
    issues: list[str]


class RowQualitySampleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_index: int
    issue_type: str
    severity: str
    evidence_json: dict[str, Any]
    summary: str


class RowQualitySamplesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    duplicate_rows: list[RowQualitySampleRead] = []
    duplicate_symbol_timestamp: list[RowQualitySampleRead] = []
    invalid_timestamp_rows: list[RowQualitySampleRead] = []
    invalid_ohlc_rows: list[RowQualitySampleRead] = []
    suspicious_return_rows: list[RowQualitySampleRead] = []
    missing_value_rows: list[RowQualitySampleRead] = []
    outlier_rows: list[RowQualitySampleRead] = []


class DatasetQualitySummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_rows: int
    total_columns: int
    clean_column_count: int
    review_column_count: int
    weak_column_count: int
    unusable_column_count: int
    total_missing_values: int
    total_outliers: int
    total_invalid_timestamps: int
    total_duplicate_rows: int
    total_duplicate_symbol_timestamps: int
    worst_columns: list[str]
    suggested_checks: list[str]


class DatasetQualityDrilldownResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    snapshot_id: uuid.UUID
    dataset_id: uuid.UUID
    dataset_name: str
    snapshot_label: str
    health_score: int
    row_count: int
    column_count: int
    column_quality: list[ColumnQualityRead]
    row_quality: RowQualitySamplesRead
    quality_summary: DatasetQualitySummaryRead
    generated_at: datetime
    warnings: list[str] = []
