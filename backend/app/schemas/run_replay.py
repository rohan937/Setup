"""Pydantic schemas for M58 Run Replay Pack."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class RunReplaySection(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    section_key: str
    title: str
    summary: str
    severity: Optional[str] = None
    evidence_json: dict = {}


class RunReplayMissingEvidence(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_type: str
    severity: str
    suggested_action: str


class RunReplayMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    replay_id: str
    generated_at: datetime
    format: str
    strategy_id: str
    run_id: str
    filename: str
    deterministic_note: str
    no_execution_replay_note: str


class RunReplayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metadata: RunReplayMetadata
    replay_status: str
    replay_completeness_score: float
    sections: list[RunReplaySection]
    missing_evidence: list[RunReplayMissingEvidence]
    suggested_review_checks: list[str]
    content: Optional[str] = None
    raw_evidence: Optional[Any] = None
