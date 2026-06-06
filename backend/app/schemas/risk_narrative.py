from pydantic import BaseModel, ConfigDict
from datetime import datetime
import uuid

class NarrativeStrengthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    label: str
    evidence: str

class NarrativeRiskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    label: str
    severity: str  # low | medium | high | critical
    evidence: str
    recommended_action: str | None = None

class RiskNarrativeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    strategy_id: uuid.UUID
    strategy_name: str
    target_stage: str
    headline: str
    narrative: str
    verdict: str  # ready | review | blocked | insufficient_data
    confidence: str  # high | medium | low
    primary_strengths: list[NarrativeStrengthOut]
    primary_risks: list[NarrativeRiskOut]
    recommended_next_actions: list[str]
    source_scores: dict[str, float | None]
    disclaimer: str
    generated_at: datetime

class RiskNarrativeReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    strategy_id: uuid.UUID
    format: str
    content: str
    generated_at: datetime
