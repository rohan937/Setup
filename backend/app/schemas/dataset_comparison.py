"""Pydantic schemas for M12: Dataset Snapshot Comparison."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Section: Metadata
# ---------------------------------------------------------------------------

class MetadataComparison(BaseModel):
    """Scalar metadata about each snapshot."""

    snapshot_a_label: str
    snapshot_b_label: str
    row_count_a: int
    row_count_b: int
    row_count_delta: int


# ---------------------------------------------------------------------------
# Section: Schema (columns + inferred types)
# ---------------------------------------------------------------------------

class TypeChange(BaseModel):
    """A column whose inferred type differs between snapshots."""

    column: str
    type_a: str
    type_b: str


class SchemaComparison(BaseModel):
    """Column-level schema differences."""

    columns_a: list[str]
    columns_b: list[str]
    added_columns: list[str]
    removed_columns: list[str]
    type_changes: list[TypeChange]
    unchanged_columns_count: int
    total_changes: int


# ---------------------------------------------------------------------------
# Section: Symbol coverage
# ---------------------------------------------------------------------------

class SymbolCoverageComparison(BaseModel):
    """Differences in symbol coverage between snapshots."""

    symbol_count_a: int
    symbol_count_b: int
    symbol_count_delta: int
    added_symbols: list[str]
    removed_symbols: list[str]
    common_symbols_count: int
    # If the dataset has no 'symbol' column, keyed comparisons are unavailable.
    keyed_by_symbol: bool


# ---------------------------------------------------------------------------
# Section: Timestamp coverage
# ---------------------------------------------------------------------------

class TimestampCoverageComparison(BaseModel):
    """Changes in the timestamp range covered by the snapshots."""

    min_timestamp_a: str | None
    max_timestamp_a: str | None
    min_timestamp_b: str | None
    max_timestamp_b: str | None
    min_changed: bool
    max_changed: bool
    date_range_days_a: int | None
    date_range_days_b: int | None
    date_range_days_delta: int | None


# ---------------------------------------------------------------------------
# Section: Data health
# ---------------------------------------------------------------------------

class DataHealthComparison(BaseModel):
    """Changes in deterministic health scores and quality issues."""

    health_score_a: int
    health_score_b: int
    health_score_delta: int
    issue_count_a: int
    issue_count_b: int
    issue_count_delta: int
    worst_severity_a: str | None
    worst_severity_b: str | None
    issue_types_a: list[str]
    issue_types_b: list[str]
    issue_types_added: list[str]
    issue_types_removed: list[str]


# ---------------------------------------------------------------------------
# Section: Value revisions
# ---------------------------------------------------------------------------

class ValueRevisionExample(BaseModel):
    """One changed / added / removed row from the value revision analysis."""

    symbol: str | None
    timestamp: str | None
    change_type: str           # "added" | "removed" | "changed"
    old_values: dict | None    # OHLCV field values in snapshot A
    new_values: dict | None    # OHLCV field values in snapshot B
    changed_fields: list[str]  # field names that differ (for "changed" rows)
    # Numeric delta per changed OHLCV field: field → (new - old)
    field_deltas: dict[str, float]


class ValueRevisionsComparison(BaseModel):
    """Row-level revision analysis using (symbol, timestamp) keys."""

    rows_available_a: bool
    rows_available_b: bool
    keyed_comparison_available: bool  # True when both snapshots have symbol+timestamp
    added_rows_count: int
    removed_rows_count: int
    changed_rows_count: int
    examples: list[ValueRevisionExample]
    total_examples_capped: bool   # True when examples were capped to MAX_EXAMPLES
    max_examples: int             # The cap that was applied


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------

class DatasetSnapshotComparisonResponse(BaseModel):
    """Full deterministic comparison of two dataset snapshots."""

    dataset_id: uuid.UUID
    snapshot_a_id: uuid.UUID
    snapshot_b_id: uuid.UUID
    snapshot_a_label: str
    snapshot_b_label: str
    is_same_snapshot: bool
    # Short prose summary of the most important changes.
    summary: str
    # Section-by-section structured comparison.
    metadata: MetadataComparison
    schema_diff: SchemaComparison
    symbol_coverage: SymbolCoverageComparison
    timestamp_coverage: TimestampCoverageComparison
    data_health: DataHealthComparison
    value_revisions: ValueRevisionsComparison
    # Human-readable bullets for the top-N most notable changes.
    highlighted_changes: list[str]
    # Deterministic, hedged explanation paragraph.
    deterministic_explanation: str
    # Advisory warnings (e.g. different column sets make row comparison unreliable).
    warnings: list[str]
    generated_at: datetime
