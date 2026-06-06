"""Pydantic schemas for evidence verification (M92)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EvidenceVerificationCheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    title: str
    status: str  # pass | warning | fail | missing
    severity: str  # low | medium | high | critical
    evidence_type: str
    evidence_id: str | None
    explanation: str
    recommended_fix: str | None


class EvidenceVerificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    verification_score: float
    verdict: str
    chain_status: str
    root_hash: str | None
    generated_at: datetime
    checks: list[EvidenceVerificationCheckOut]
    tamper_warnings: list[str]
    time_consistency_warnings: list[str]
    link_consistency_warnings: list[str]
    suggested_actions: list[str]
    disclaimer: str


class EvidenceVerificationReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: uuid.UUID
    strategy_name: str
    format: str
    content: str
    generated_at: datetime
