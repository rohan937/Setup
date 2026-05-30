from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


class StrategyDetailOut(StrategyOut):
    versions: list[StrategyVersionOut] = []


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
