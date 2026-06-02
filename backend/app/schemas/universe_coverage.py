"""Pydantic schemas for M39 universe coverage analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UniverseSymbolQualityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    normalized_symbol: str
    quality_status: str
    is_duplicate: bool
    has_invalid_format: bool
    format_issues: list[str]
    issues: list[str]


class UniverseMetadataBreakdownRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    has_symbol_metadata: bool
    metadata_coverage_rate: float
    missing_metadata_symbols: int
    by_sector: dict[str, int]
    by_country: dict[str, int]
    by_exchange: dict[str, int]
    by_liquidity_bucket: dict[str, int]
    warnings: list[str]


class UniverseDeltaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    has_previous: bool
    previous_snapshot_id: Optional[str]
    previous_label: Optional[str]
    delta_status: Optional[str]
    added_symbols: list[str]
    removed_symbols: list[str]
    common_symbols_count: int
    added_count: int
    removed_count: int
    overlap_ratio: Optional[float]
    jaccard_similarity: Optional[float]
    churn_rate: Optional[float]


class UniverseQualitySummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol_count: int
    unique_symbol_count: int
    duplicate_symbol_count: int
    invalid_symbol_count: int
    clean_symbol_count: int
    review_symbol_count: int
    weak_symbol_count: int
    coverage_status: str
    suggested_checks: list[str]


class UniverseCoverageAnalysisRead(UniverseQualitySummaryRead):
    model_config = ConfigDict(from_attributes=True)

    linked_run_count: int
    is_used_by_runs: bool
    linkage_status: str
    version_label: Optional[str]


class UniverseCoverageAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    snapshot_id: str
    strategy_id: str
    label: str
    universe_hash: str
    symbol_count: int
    generated_at: datetime
    coverage_analysis: UniverseCoverageAnalysisRead
    symbol_quality: list[UniverseSymbolQualityRead]
    metadata_breakdown: UniverseMetadataBreakdownRead
    universe_delta: UniverseDeltaRead
    quality_summary: UniverseQualitySummaryRead
    warnings: list[str]
