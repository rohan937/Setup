"""Pydantic schemas for deterministic run comparison responses.

No AI, no causal inference — strictly structured diffs of logged run data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class FieldChange(BaseModel):
    """A single field that changed between two runs."""

    field: str
    # old_value / new_value are None for added / removed fields respectively.
    old_value: Any
    new_value: Any
    # "added" | "removed" | "changed"
    change_type: str
    # Numeric delta (new - old) when both values are numeric; None otherwise.
    delta: float | None = None
    # Percent change relative to old value; None when old_value == 0 or non-numeric.
    pct_delta: float | None = None


class ComparisonSection(BaseModel):
    """Comparison results for one section (params, assumptions, metrics, metadata)."""

    added: list[FieldChange] = []
    removed: list[FieldChange] = []
    changed: list[FieldChange] = []
    unchanged_count: int = 0
    total_changes: int = 0


class RunComparisonResponse(BaseModel):
    """Full deterministic comparison between two strategy runs.

    This is a read-only analysis — no audit event is created.
    """

    strategy_id: str
    run_a_id: str
    run_b_id: str
    run_a_name: str
    run_b_name: str
    run_a_created_at: datetime
    run_b_created_at: datetime
    # True when run_a_id == run_b_id (comparing a run to itself).
    is_same_run: bool
    metadata: ComparisonSection
    params: ComparisonSection
    assumptions: ComparisonSection
    metrics: ComparisonSection
    # Human-readable sentences for the most important individual changes.
    highlighted_changes: list[str]
    # Plain-language summary. Hedged — no causal claims.
    deterministic_explanation: str
    # Warnings about potentially misleading comparisons (e.g. different run_type).
    warnings: list[str]
    total_changes: int
