from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

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


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

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


class StrategyRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version_id: uuid.UUID | None
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
    """Full strategy detail with versions and recent runs."""

    versions: list[StrategyVersionOut] = []
    runs: list[StrategyRunOut] = []


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
