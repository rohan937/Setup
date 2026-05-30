"""GET /api/timeline — list audit timeline events, newest first."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.audit_timeline_event import AuditTimelineEvent
from app.schemas.timeline import TimelineEventOut

router = APIRouter(tags=["timeline"])


@router.get("/timeline", response_model=list[TimelineEventOut])
def list_timeline_events(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[AuditTimelineEvent]:
    return (
        db.query(AuditTimelineEvent)
        .order_by(AuditTimelineEvent.event_time.desc())
        .limit(limit)
        .all()
    )
