"""M65 Deployment Readiness — Pydantic response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DeploymentReadinessCheck(BaseModel):
    check_key: str
    title: str
    category: str
    status: str  # pass/warning/fail/manual/not_applicable
    severity: str  # info/low/medium/high/critical
    observed_value: str | None = None
    expected_value: str | None = None
    explanation: str = ""
    suggested_action: str | None = None


class DeploymentReadinessCategory(BaseModel):
    category_key: str
    title: str
    status: str  # pass/warning/fail/manual
    pass_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    manual_count: int = 0
    checks: list[DeploymentReadinessCheck] = []


class DeploymentReadinessResponse(BaseModel):
    generated_at: datetime
    overall_status: str  # local_demo_ready/deployment_prep_ready/needs_review/blocked
    readiness_score: float
    pass_count: int
    warning_count: int
    fail_count: int
    manual_count: int
    blocker_count: int
    categories: list[DeploymentReadinessCategory] = []
    blockers: list[str] = []
    warnings: list[str] = []
    suggested_next_steps: list[str] = []
    deterministic_summary: str
