"""Pydantic schemas for M53 strategy regression tests."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class StrategyRegressionTestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    name: str
    test_key: str
    test_type: str
    metric_key: str | None = None
    operator: str
    threshold_value: float | None = None
    threshold_json: Any | None = None
    severity: str
    is_required: bool
    is_enabled: bool
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class StrategyRegressionTestRunRequest(BaseModel):
    mode: str = "latest_vs_previous"
    baseline_run_id: uuid.UUID | None = None
    comparison_run_id: uuid.UUID | None = None
    suite_label: str | None = None


class StrategyRegressionTestResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    test_run_id: uuid.UUID
    regression_test_id: uuid.UUID | None = None
    test_key: str
    title: str
    status: str
    severity: str
    is_required: bool
    observed_value: str | None = None
    expected_value: str | None = None
    baseline_value: str | None = None
    comparison_value: str | None = None
    evidence_json: Any | None = None
    suggested_action: str | None = None
    created_at: datetime


class StrategyRegressionTestRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    suite_label: str | None = None
    mode: str
    baseline_run_id: uuid.UUID | None = None
    comparison_run_id: uuid.UUID | None = None
    overall_status: str
    passed_count: int
    failed_count: int
    warning_count: int
    skipped_count: int
    required_failed_count: int
    result_json: Any | None = None
    deterministic_summary: str | None = None
    created_at: datetime
    updated_at: datetime
    results: list[StrategyRegressionTestResultRead] = []


class StrategyRegressionTestRunListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[StrategyRegressionTestRunRead]
    total: int
    limit: int
    offset: int
