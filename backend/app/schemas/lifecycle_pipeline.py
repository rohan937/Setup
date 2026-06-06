"""M104 Lifecycle pipeline summary schemas (read-only)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LifecycleStageCount(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    count: int
    blocked_count: int


class LifecyclePipelineSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    generated_at: datetime
    total_strategies: int
    stages: list[LifecycleStageCount]
    blocked_total: int
    disclaimer: str
