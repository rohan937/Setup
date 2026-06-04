"""Pydantic schemas for M46 demo seed endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class DemoSeedRequest(BaseModel):
    """Request body for POST /api/admin/seed-demo."""

    mode: str = "extend"
    confirm_reset: bool = False
    include_reports: bool = True
    include_alerts: bool = True
    include_backtest_audits: bool = True


class DemoSeedResponse(BaseModel):
    """Response body for POST /api/admin/seed-demo."""

    mode: str
    summary: str
    organization_id: Optional[str] = None
    project_id: Optional[str] = None
    strategy_ids: list[str] = []
    created_counts: dict = {}
    reused_counts: dict = {}
    reset_counts: dict = {}
    generated_artifacts: list[str] = []
    warnings: list[str] = []


class DemoStatusResponse(BaseModel):
    """Response body for GET /api/admin/demo-status."""

    demo_org_exists: bool
    demo_project_exists: bool
    strategy_count: int
    demo_strategy_names: list[str] = []
    last_seeded_at: Optional[datetime] = None
    summary: str


class AdvancedDemoSeedResponse(BaseModel):
    """Response body for POST /api/admin/demo/advanced-strategy (M78)."""

    status: str  # created | refreshed
    strategy_id: str
    strategy_name: str
    strategy_slug: str
    organization_id: str
    project_id: str
    counts: dict = {}
    total_artifacts: int
    summary: str
    disclaimer: str
