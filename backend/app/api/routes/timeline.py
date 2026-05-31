"""Audit timeline endpoints (M10):

  GET /api/timeline              — filtered, paginated event stream
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.audit_timeline_event import AuditTimelineEvent
from app.schemas.timeline import TimelineEventOut, TimelineListResponse

router = APIRouter(tags=["timeline"])


@router.get("/timeline", response_model=TimelineListResponse)
def list_timeline_events(
    project_id: uuid.UUID | None = Query(default=None, description="Filter by project"),
    strategy_id: uuid.UUID | None = Query(default=None, description="Filter by strategy"),
    event_type: str | None = Query(default=None, description="Filter by event_type (e.g. strategy_created)"),
    severity: str | None = Query(default=None, description="Filter by severity (info/low/medium/high/critical)"),
    source_type: str | None = Query(
        default=None,
        description="Filter by source_type (strategy/strategy_run/dataset_snapshot/backtest_audit)",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> TimelineListResponse:
    """Return audit timeline events newest-first with optional filtering and pagination.

    All filters are AND-combined.  ``total`` reflects the full untruncated count
    matching the filters so the caller can implement paging.
    """
    q = db.query(AuditTimelineEvent)

    if project_id is not None:
        q = q.filter(AuditTimelineEvent.project_id == project_id)
    if strategy_id is not None:
        q = q.filter(AuditTimelineEvent.strategy_id == strategy_id)
    if event_type is not None:
        q = q.filter(AuditTimelineEvent.event_type == event_type)
    if severity is not None:
        q = q.filter(AuditTimelineEvent.severity == severity)
    if source_type is not None:
        q = q.filter(AuditTimelineEvent.source_type == source_type)

    total: int = q.count()
    items = (
        q.order_by(AuditTimelineEvent.event_time.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return TimelineListResponse(
        items=[TimelineEventOut.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )
