"""Pydantic schemas for M31 strategy evidence export."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class StrategyExportSection(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    section_key: str
    title: str
    summary: str
    severity: Optional[str] = None
    evidence_json: Optional[Any] = None  # dict or list (reports section returns a list)


class StrategyExportMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    export_id: str
    strategy_id: uuid.UUID
    strategy_name: str
    strategy_slug: str
    generated_at: datetime
    format: str
    filename: str
    milestone: str
    note: str


class StrategyExportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    format: str
    filename: str
    metadata: StrategyExportMetadata
    sections: list[StrategyExportSection]
    content: Optional[str] = None
    raw_evidence: Optional[Any] = None
