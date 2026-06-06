"""Dashboard endpoint (M9):

  GET /api/dashboard/summary — aggregated reliability summary.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.command_center import CommandCenterResponse
from app.schemas.dashboard import DashboardSummary
from app.services.command_center import build_command_center
from app.services.dashboard_summary import build_dashboard_summary

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db)) -> DashboardSummary:
    """Return a fully aggregated reliability dashboard summary.

    Aggregates strategy, run, dataset, backtest-audit, and timeline evidence
    from M3–M8 into a single response.  All scores are null when no evidence
    exists — no fake scores are ever returned.

    Read-only.  No events are created.
    """
    return build_dashboard_summary(db)


@router.get("/command-center", response_model=CommandCenterResponse, tags=["dashboard"])
def get_command_center(db: Session = Depends(get_db)) -> CommandCenterResponse:
    """Read-only workspace triage aggregation (M106 Research Command Center).

    Composes the portfolio reliability summary, lifecycle stage summary, active
    strategy reviews, and open alerts into a single Home-page payload — collapsing
    the previous per-strategy N+1 fan-out into one call.

    Read-only.  No DB mutation, no events, no new business logic.
    """
    data = build_command_center(db)
    return CommandCenterResponse.model_validate(data)
