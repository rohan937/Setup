"""Pydantic schemas for M14: Reliability Reports."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ReportSectionRead(BaseModel):
    """One section of a reliability report."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    report_id: uuid.UUID
    section_key: str
    title: str
    summary: str
    severity: str | None = None
    order_index: int
    evidence_json: dict[str, Any] | None = None
    created_at: datetime


class ReportRead(BaseModel):
    """Core report fields — no sections list.

    Used as list-view representation.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID | None = None
    strategy_id: uuid.UUID | None = None
    report_type: str
    title: str
    status: str
    summary: str
    generated_at: datetime
    source_type: str | None = None
    source_id: str | None = None
    score: int | None = None
    report_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class ReportDetail(ReportRead):
    """Full report with all sections — returned by POST and GET single-report."""

    sections: list[ReportSectionRead]


class ReportListResponse(BaseModel):
    """Paginated list of reports."""

    items: list[ReportRead]
    total: int
    limit: int
    offset: int
