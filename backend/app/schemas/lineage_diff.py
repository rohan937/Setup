from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Any

class LineageDiffItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    label: str
    base_value: Any
    comparison_value: Any
    delta: Any
    status: str  # improved | worsened | changed | unchanged | missing | introduced | resolved
    explanation: str

class LineageDiffSection(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    title: str
    status: str  # improved | worse | changed | unchanged | missing
    items: list[LineageDiffItem]

class LineageDiffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    strategy_id: str
    base_version: str
    comparison_version: str
    verdict: str  # improved | mixed | worse | unchanged | insufficient_data
    trust_delta: float | None
    primary_change: str | None
    primary_risk: str | None
    summary: str
    sections: list[LineageDiffSection]
    metric_deltas: list[LineageDiffItem]
    blockers_introduced: list[LineageDiffItem]
    blockers_resolved: list[LineageDiffItem]
    suggested_actions: list[str]
    generated_at: str
    disclaimer: str

class LineageDiffReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    strategy_id: str
    base_version: str
    comparison_version: str
    format: str
    content: str
    generated_at: str

class ComparableVersionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    version_id: str
    version_label: str
    created_at: str
    git_commit: str | None

class ComparableVersionsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    strategy_id: str
    versions: list[ComparableVersionItem]
    comparable: bool  # True if len(versions) >= 2
