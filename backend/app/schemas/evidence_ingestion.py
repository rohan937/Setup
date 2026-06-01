"""Pydantic schemas for the Evidence Ingestion Bundle endpoint (M22).

POST /api/strategies/{strategy_id}/evidence-bundles

Allows submitting multiple evidence sections in a single request:
  - strategy_version
  - config_snapshot
  - universe_snapshot
  - signal_snapshot
  - dataset + dataset_snapshot
  - strategy_run
  - optional actions (audit, reliability score, report, alerts)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Input: individual sections
# ---------------------------------------------------------------------------


class EvidenceBundleVersionSection(BaseModel):
    """Strategy version to create or reuse."""

    version_label: str = Field(..., min_length=1, max_length=100)
    git_commit: str | None = None
    branch_name: str | None = None
    code_path: str | None = None
    signal_name: str | None = None
    signal_description: str | None = None


class EvidenceBundleConfigSection(BaseModel):
    """Config snapshot to create."""

    strategy_version_label: str | None = None
    label: str = Field(..., min_length=1, max_length=255)
    source_type: str = "manual_json"
    source_filename: str | None = None
    config_json: dict[str, Any] = Field(..., description="Raw config dict")


class EvidenceBundleUniverseSection(BaseModel):
    """Universe snapshot to create."""

    strategy_version_label: str | None = None
    label: str = Field(..., min_length=1, max_length=255)
    source_type: str = "manual_json"
    source_filename: str | None = None
    symbols: list[str] = Field(..., min_length=1)
    metadata_json: dict[str, Any] | None = None


class EvidenceBundleSignalSection(BaseModel):
    """Signal snapshot to create."""

    strategy_version_label: str | None = None
    universe_snapshot_label: str | None = None
    label: str = Field(..., min_length=1, max_length=255)
    signal_name: str | None = None
    source_type: str = "manual_json"
    source_filename: str | None = None
    signal_column: str = "signal"
    rows: list[dict[str, Any]] = Field(..., min_length=1)
    metadata_json: dict[str, Any] | None = None


class EvidenceBundleDatasetSection(BaseModel):
    """Dataset to create or reuse (matched by name within project)."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str | None = None
    description: str | None = None
    asset_class: str = "equity"
    dataset_type: str = "equity_prices"
    source_type: str = "csv_upload"


class EvidenceBundleDatasetSnapshotSection(BaseModel):
    """Dataset snapshot to create under the dataset."""

    snapshot_label: str | None = None
    source_filename: str | None = None
    rows: list[dict[str, Any]] = Field(..., min_length=1)


class EvidenceBundleRunSection(BaseModel):
    """Strategy run to create."""

    strategy_version_label: str | None = None
    dataset_snapshot_label: str | None = None
    universe_snapshot_label: str | None = None
    signal_snapshot_label: str | None = None
    run_name: str = Field(..., min_length=1, max_length=255)
    run_type: str = "backtest"
    status: str = "completed"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    params_json: dict[str, Any] | None = None
    assumptions_json: dict[str, Any] | None = None
    metrics_json: dict[str, Any] | None = None
    universe_name: str | None = None
    dataset_version: str | None = None
    notes: str | None = None


class EvidenceBundleActions(BaseModel):
    """Post-ingestion actions to run."""

    run_backtest_audit: bool = False
    compute_reliability_score: bool = False
    generate_strategy_report: bool = False
    generate_alerts: bool = False


class EvidenceBundleRequest(BaseModel):
    """Full evidence bundle request — all sections are optional."""

    strategy_version: EvidenceBundleVersionSection | None = None
    config_snapshot: EvidenceBundleConfigSection | None = None
    universe_snapshot: EvidenceBundleUniverseSection | None = None
    signal_snapshot: EvidenceBundleSignalSection | None = None
    dataset: EvidenceBundleDatasetSection | None = None
    dataset_snapshot: EvidenceBundleDatasetSnapshotSection | None = None
    strategy_run: EvidenceBundleRunSection | None = None
    actions: EvidenceBundleActions | None = None


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class EvidenceBundleObjectRef(BaseModel):
    """Reference to a created or reused object."""

    id: uuid.UUID
    name: str
    type: str
    status: str  # "created" | "reused"

    model_config = {"from_attributes": True}


class EvidenceBundleResponse(BaseModel):
    """Response for POST /api/strategies/{strategy_id}/evidence-bundles."""

    strategy_id: uuid.UUID
    created_count: int
    reused_count: int
    actions_run: list[str]
    objects: dict[str, EvidenceBundleObjectRef | None]
    alerts_generated: int = 0
    warnings: list[str]
    summary: str
    timeline_events_created: int
    generated_at: datetime

    model_config = {"from_attributes": True}
