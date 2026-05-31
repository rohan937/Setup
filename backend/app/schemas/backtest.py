"""Pydantic schemas for M8: Backtest Reality Check."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BacktestIssueRead(BaseModel):
    """One detected realism concern."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    issue_type: str
    severity: str
    title: str
    description: str
    evidence_json: dict | None = None
    suggested_check: str | None = None
    created_at: datetime


class BacktestAuditRead(BaseModel):
    """Core audit fields — no issues list.

    Used as a base for ``BacktestAuditDetail`` and ``BacktestAuditListItem``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_run_id: uuid.UUID
    trust_score: int
    lookahead_risk_score: int
    cost_realism_score: int
    fill_realism_score: int
    liquidity_realism_score: int
    borrow_realism_score: int
    data_quality_score: int
    overall_status: str
    summary: str
    created_at: datetime
    updated_at: datetime


class BacktestAuditDetail(BacktestAuditRead):
    """Full audit with all issues — returned by POST and GET single-audit."""

    issues: list[BacktestIssueRead]


class BacktestAuditListItem(BacktestAuditRead):
    """Audit enriched with run/strategy context for the global list view."""

    strategy_id: uuid.UUID
    strategy_name: str
    run_name: str
    run_type: str
    issue_count: int
    # Top 3 issues ordered by severity (most severe first).
    top_issues: list[BacktestIssueRead]
