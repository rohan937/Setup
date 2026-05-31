from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------

class DatasetCreate(BaseModel):
    """Request body for POST /api/datasets."""

    project_id: uuid.UUID
    name: Annotated[
        str, StringConstraints(min_length=1, max_length=255, strip_whitespace=True)
    ]
    description: str | None = None
    # See constants.DatasetType for valid values.  Defaults to ohlcv.
    dataset_type: str = "ohlcv"
    # See constants.DatasetSourceType for valid values.  Defaults to manual.
    source_type: str = "manual"


class DatasetSnapshotCreate(BaseModel):
    """Request body for POST /api/datasets/{id}/snapshots."""

    version_label: Annotated[
        str, StringConstraints(min_length=1, max_length=100, strip_whitespace=True)
    ]
    # List of row dicts — must be a JSON array of objects.
    rows: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

class DataQualityIssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    snapshot_id: uuid.UUID
    issue_type: str
    severity: str
    field_name: str | None
    row_index: int | None
    detail: str | None
    created_at: datetime


class DatasetSnapshotRead(BaseModel):
    """Snapshot summary — no rows payload."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    version_label: str
    row_count: int
    health_score: int
    created_at: datetime
    updated_at: datetime


class DatasetSnapshotDetail(DatasetSnapshotRead):
    """Full snapshot detail including quality issues."""

    issues: list[DataQualityIssueRead] = []


class DatasetRead(BaseModel):
    """Dataset summary row — no snapshot payloads."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    dataset_type: str
    source_type: str
    snapshot_count: int = 0
    created_at: datetime
    updated_at: datetime


class DatasetDetail(DatasetRead):
    """Full dataset with snapshot metadata list (no rows)."""

    snapshots: list[DatasetSnapshotRead] = []
