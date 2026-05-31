from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------

class StrategyCreate(BaseModel):
    """Request body for POST /api/strategies."""

    project_id: uuid.UUID
    name: Annotated[str, StringConstraints(min_length=1, max_length=255, strip_whitespace=True)]
    slug: str | None = Field(default=None, max_length=100)
    description: str | None = None
    # See constants.AssetClass for valid values.  Defaults to equity.
    asset_class: str = "equity"
    # See constants.StrategyStatus for valid values.  Defaults to active.
    status: str = "active"


class StrategyVersionCreate(BaseModel):
    """Request body for POST /api/strategies/{strategy_id}/versions (M15)."""

    version_label: Annotated[str, StringConstraints(min_length=1, max_length=100, strip_whitespace=True)]
    git_commit: str | None = Field(default=None, max_length=255)
    branch_name: str | None = Field(default=None, max_length=255)
    code_path: str | None = Field(default=None, max_length=512)
    signal_name: str | None = Field(default=None, max_length=255)
    signal_description: str | None = None


class StrategyConfigSnapshotCreate(BaseModel):
    """Request body for POST /api/strategies/{strategy_id}/config-snapshots (M15)."""

    strategy_version_id: uuid.UUID | None = None
    label: Annotated[str, StringConstraints(min_length=1, max_length=255, strip_whitespace=True)]
    source_type: str = "manual_json"
    source_filename: str | None = Field(default=None, max_length=512)
    # Must be a JSON object (not array/scalar); validated in route.
    config_json: dict[str, Any]


class StrategyRunCreate(BaseModel):
    """Request body for POST /api/strategies/{strategy_id}/runs."""

    strategy_version_id: uuid.UUID | None = None
    # M7: optional link to a QuantFidelity dataset snapshot (must be in the same project).
    dataset_snapshot_id: uuid.UUID | None = None
    run_name: Annotated[str, StringConstraints(min_length=1, max_length=255, strip_whitespace=True)]
    # See constants.RunType for valid values.  Required.
    run_type: str
    # See constants.RunStatus for valid values.  Defaults to completed.
    status: str = "completed"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    # Each JSON field must be a dict (object) if provided, not an array or scalar.
    params_json: dict | None = None
    assumptions_json: dict | None = None
    metrics_json: dict | None = None
    universe_name: str | None = Field(default=None, max_length=255)
    # Free-text label retained alongside dataset_snapshot_id for unlinked runs.
    dataset_version: str | None = Field(default=None, max_length=255)
    notes: str | None = None


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

class DataEvidenceSummary(BaseModel):
    """Lightweight data health evidence embedded in strategy run responses (M7).

    Computed from a linked DatasetSnapshot and its quality issues.
    Never embeds raw rows or full issue lists.
    """

    id: uuid.UUID                 # snapshot id
    dataset_id: uuid.UUID
    dataset_name: str
    snapshot_label: str           # version_label
    health_score: int
    row_count: int
    column_count: int
    symbol_count: int
    min_timestamp: str | None
    max_timestamp: str | None
    issue_count: int
    worst_severity: str | None    # None when issue_count == 0


class StrategyVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    version_label: str
    git_commit: str | None
    branch_name: str | None
    code_path: str | None
    signal_name: str | None
    signal_description: str | None
    created_at: datetime
    updated_at: datetime
    # M15: config snapshot count for this version (populated by route if requested)
    config_snapshot_count: int = 0


class StrategyConfigSnapshotRead(BaseModel):
    """Config snapshot summary — no config_json blob (used in list responses)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version_id: uuid.UUID | None
    label: str
    source_type: str
    source_filename: str | None
    config_hash: str
    param_count: int
    assumption_count: int
    created_at: datetime
    updated_at: datetime


class StrategyConfigSnapshotDetail(StrategyConfigSnapshotRead):
    """Full config snapshot including the config_json payload."""

    config_json: dict[str, Any]


class ConfigKeyChangeOut(BaseModel):
    key: str
    old_value: Any = None
    new_value: Any = None
    change_type: str  # "added" | "removed" | "changed"


class ConfigComparisonSectionOut(BaseModel):
    added: list[ConfigKeyChangeOut] = []
    removed: list[ConfigKeyChangeOut] = []
    changed: list[ConfigKeyChangeOut] = []
    total_changes: int = 0


class ConfigComparisonResponse(BaseModel):
    snapshot_a_id: uuid.UUID
    snapshot_b_id: uuid.UUID
    snapshot_a_label: str
    snapshot_b_label: str
    is_same_config: bool
    top_level: ConfigComparisonSectionOut
    params: ConfigComparisonSectionOut
    assumptions: ConfigComparisonSectionOut
    highlighted_changes: list[str]
    total_changes: int


class StrategyRunOut(BaseModel):
    """Strategy run response — built manually in route handlers (not from_attributes).

    dataset_snapshot is populated only when the run has a linked snapshot
    and the route eagerly loads StrategyRun.snapshot → dataset + issues.
    """

    id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version_id: uuid.UUID | None
    # M7: nullable FK to a linked dataset snapshot.
    dataset_snapshot_id: uuid.UUID | None = None
    run_name: str
    run_type: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    params_json: dict | None
    assumptions_json: dict | None
    metrics_json: dict | None
    universe_name: str | None
    dataset_version: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    # M7: data evidence summary — None when no snapshot is linked.
    dataset_snapshot: DataEvidenceSummary | None = None


class StrategyListItemOut(BaseModel):
    """Strategy summary row used in the list endpoint."""

    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    name: str
    slug: str
    description: str | None
    asset_class: str
    status: str
    run_count: int
    latest_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StrategyDetailOut(StrategyListItemOut):
    """Full strategy detail with versions, runs, and recent config snapshots (M15)."""

    versions: list[StrategyVersionOut] = []
    runs: list[StrategyRunOut] = []
    config_snapshots: list[StrategyConfigSnapshotRead] = []


# Keep the plain StrategyOut for any internal callers that still use it.
class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    asset_class: str
    status: str
    created_at: datetime
    updated_at: datetime
