from pydantic import BaseModel, ConfigDict
from datetime import datetime
import uuid

class ScoreDriverItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    label: str
    points: float
    direction: str  # positive | negative | neutral
    category: str
    evidence_type: str | None = None
    evidence_id: str | None = None
    explanation: str
    recommended_action: str | None = None

class ScoreCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    score_key: str
    label: str
    score: float | None
    max_score: float
    verdict: str
    primary_positive: str | None
    primary_drag: str | None
    items: list[ScoreDriverItemOut]
    formula_note: str
    generated_at: datetime

class StrategyScoreExplanationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    strategy_id: uuid.UUID
    strategy_name: str
    overall_summary: str
    scorecards: list[ScoreCardOut]
    disclaimer: str
    generated_at: datetime

class ScoreExplainReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    strategy_id: uuid.UUID
    format: str
    content: str
    generated_at: datetime
