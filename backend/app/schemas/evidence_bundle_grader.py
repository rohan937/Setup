from pydantic import BaseModel, ConfigDict
from datetime import datetime

class BundleIncludedItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    label: str
    status: str  # present | partial | absent
    quality: str  # good | fair | weak | missing
    details: str

class BundleMissingItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    label: str
    severity: str  # low | medium | high
    why_it_matters: str

class BundleGradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    quality_score: float
    letter_grade: str
    verdict: str  # excellent | good | usable | weak | invalid
    stage_sufficiency: dict[str, str]
    sufficient_for: list[str]
    not_sufficient_for: list[str]
    included: list[BundleIncludedItem]
    missing: list[BundleMissingItem]
    warnings: list[str]
    recommended_fixes: list[str]
    generated_at: datetime
    disclaimer: str

class BundleGradeReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    format: str
    content: str
    generated_at: datetime
