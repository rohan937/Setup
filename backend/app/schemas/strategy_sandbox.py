from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Any
import uuid

class SandboxScores(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    reliability_score: float | None
    backtest_reality_score: float | None
    readiness_score: float | None
    promotion_verdict: str

class SandboxDeltaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    label: str
    current_value: Any
    projected_value: Any
    impact: float
    explanation: str

class SandboxResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    strategy_id: uuid.UUID
    strategy_name: str
    scenario_name: str
    target_stage: str
    current: SandboxScores
    projected: SandboxScores
    deltas: list[SandboxDeltaOut]
    new_blockers: list[str]
    resolved_blockers: list[str]
    warnings: list[str]
    suggested_actions: list[str]
    generated_at: datetime
    disclaimer: str

class SandboxScenarioRequest(BaseModel):
    scenario_name: str | None = None
    assumption_overrides: dict[str, Any] = {}
    metric_overrides: dict[str, Any] = {}
    evidence_overrides: dict[str, Any] = {}
    target_stage: str | None = None

class SandboxPresetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    name: str
    description: str
    assumption_overrides: dict[str, Any]
    metric_overrides: dict[str, Any]
    evidence_overrides: dict[str, Any]
    target_stage: str | None

class SandboxStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    strategy_id: uuid.UUID
    strategy_name: str
    current: SandboxScores
    target_stage: str
    presets: list[SandboxPresetOut]
    generated_at: datetime
    disclaimer: str
