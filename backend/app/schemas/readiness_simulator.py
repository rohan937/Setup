from pydantic import BaseModel, ConfigDict
from datetime import datetime
import uuid

class RecommendedActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    title: str
    category: str
    impact_points: int
    effort: str  # low | medium | high
    status: str  # not_started | done
    why_it_matters: str
    cta_label: str
    cta_target: str

class ReadinessSimulatorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    strategy_id: uuid.UUID
    strategy_name: str
    current_stage: str
    target_stage: str
    current_readiness_score: float | None
    projected_readiness_score: float | None
    current_verdict: str
    projected_verdict: str
    estimated_delta: float
    current_blockers: list[str]
    remaining_blockers: list[str]
    recommended_actions: list[RecommendedActionOut]
    simulated_completed_actions: list[str]
    warnings: list[str]
    generated_at: datetime
    disclaimer: str

class ReadinessSimulateRequest(BaseModel):
    target_stage: str | None = None
    completed_actions: list[str] = []

class RecommendedActionsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    strategy_id: uuid.UUID
    target_stage: str
    recommended_actions: list[RecommendedActionOut]
    generated_at: datetime
