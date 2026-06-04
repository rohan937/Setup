"""M75 Evidence Repair + Strategy Management schemas.

Deterministic, local management actions — no AI, no external data, no trading.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Repair options
# ---------------------------------------------------------------------------

class RepairOptionItem(BaseModel):
    """A single linkable evidence object surfaced for repair."""

    id: str
    label: str
    created_at: datetime | None = None
    quality_score: int | None = None       # dataset health / signal quality
    row_count: int | None = None
    symbol_count: int | None = None
    linked_run_count: int | None = None
    recommended: bool = False              # latest / highest-quality option
    detail: str | None = None              # short human descriptor


class RunMissingLinks(BaseModel):
    """A run together with which evidence links it is missing."""

    run_id: str
    run_name: str
    run_type: str
    created_at: datetime | None = None
    missing: list[str] = []                # subset of dataset/signal/universe/version
    dataset_snapshot_id: str | None = None
    signal_snapshot_id: str | None = None
    universe_snapshot_id: str | None = None
    strategy_version_id: str | None = None


class RepairOptionsResponse(BaseModel):
    strategy_id: str
    strategy_name: str
    dataset_snapshots: list[RepairOptionItem] = []
    signal_snapshots: list[RepairOptionItem] = []
    universe_snapshots: list[RepairOptionItem] = []
    strategy_versions: list[RepairOptionItem] = []
    runs_missing_links: list[RunMissingLinks] = []


# ---------------------------------------------------------------------------
# Run link update
# ---------------------------------------------------------------------------

class RunLinkUpdateRequest(BaseModel):
    """Partial update — only provided fields are linked."""

    dataset_snapshot_id: uuid.UUID | None = None
    signal_snapshot_id: uuid.UUID | None = None
    universe_snapshot_id: uuid.UUID | None = None
    strategy_version_id: uuid.UUID | None = None


class RunLinkSummary(BaseModel):
    run_id: str
    strategy_id: str
    run_name: str
    run_type: str
    status: str
    dataset_snapshot_id: str | None = None
    signal_snapshot_id: str | None = None
    universe_snapshot_id: str | None = None
    strategy_version_id: str | None = None
    dataset_snapshot_label: str | None = None
    signal_snapshot_label: str | None = None
    universe_snapshot_label: str | None = None
    strategy_version_label: str | None = None
    linked_fields: list[str] = []          # fields changed by this request
    updated_at: datetime | None = None
    message: str = ""


# ---------------------------------------------------------------------------
# Strategy management
# ---------------------------------------------------------------------------

class StrategyUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    asset_class: str | None = None


class StrategyManagementSummary(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None = None
    asset_class: str
    status: str
    archived: bool = False
    message: str = ""
