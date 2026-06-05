"""Alerts Engine API endpoints (M11):

  POST /api/alerts/generate             — trigger alert generation for the org
  GET  /api/alerts                      — list alerts (filterable, paginated)
  GET  /api/alerts/{alert_id}           — fetch a single alert
  PATCH /api/alerts/{alert_id}          — update alert status
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.constants import AlertStatus
from app.core.rbac import require_workspace_write_access
from app.db.session import get_db
from app.models.alert import Alert
from app.models.organization import Organization
from app.models.strategy import Strategy
from app.models.project import Project
from app.schemas.alerts import (
    AlertGenerateResponse,
    AlertListResponse,
    AlertRead,
    AlertUpdateRequest,
)
from app.services.alerts import generate_alerts

router = APIRouter(tags=["alerts"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_STATUSES = {str(s) for s in AlertStatus}


def _get_default_org(db: Session) -> Organization | None:
    """Return the first organisation found (single-org assumption for M11)."""
    return db.query(Organization).first()


def _get_total_open(db: Session, org_id: str) -> int:
    return (
        db.query(Alert)
        .filter(Alert.organization_id == org_id, Alert.status == str(AlertStatus.open))
        .count()
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/alerts/generate", response_model=AlertGenerateResponse)
def trigger_alert_generation(
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_write_access),
) -> AlertGenerateResponse:
    """Run the deterministic alert-generation service and return a summary.

    Idempotent: duplicate detection prevents re-creating open alerts for the
    same evidence source.
    """
    org = _get_default_org(db)
    if org is None:
        raise HTTPException(status_code=404, detail="No organisation found.")

    org_id = str(org.id)
    result = generate_alerts(db, org_id)
    db.commit()

    total_open = _get_total_open(db, org_id)
    return AlertGenerateResponse(
        alerts_created=result.alerts_created,
        alerts_skipped_duplicate=result.alerts_skipped_duplicate,
        total_alerts_open=total_open,
    )


@router.get("/alerts", response_model=AlertListResponse)
def list_alerts(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    rule_type: str | None = Query(default=None),
    strategy_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> AlertListResponse:
    """Return a paginated, filterable list of alerts."""
    q = db.query(Alert)

    if status is not None:
        q = q.filter(Alert.status == status)
    if severity is not None:
        q = q.filter(Alert.severity == severity)
    if rule_type is not None:
        q = q.filter(Alert.rule_type == rule_type)
    if strategy_id is not None:
        q = q.filter(Alert.strategy_id == str(strategy_id))

    total: int = q.count()
    items = (
        q.order_by(Alert.triggered_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return AlertListResponse(
        items=[AlertRead.model_validate(a) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/alerts/{alert_id}", response_model=AlertRead)
def get_alert(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> AlertRead:
    """Fetch a single alert by id."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return AlertRead.model_validate(alert)


@router.patch("/alerts/{alert_id}", response_model=AlertRead)
def update_alert_status(
    alert_id: uuid.UUID,
    body: AlertUpdateRequest,
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_write_access),
) -> AlertRead:
    """Update the status of an alert (open → acknowledged / resolved / snoozed).

    Side-effects on timestamps:
    - Transition to acknowledged → sets acknowledged_at
    - Transition to resolved → sets resolved_at
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")

    new_status = body.status
    if new_status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{new_status}'. Must be one of: {sorted(_VALID_STATUSES)}",
        )

    now = datetime.now(timezone.utc)
    alert.status = new_status
    if new_status == str(AlertStatus.acknowledged) and alert.acknowledged_at is None:
        alert.acknowledged_at = now
    elif new_status == str(AlertStatus.resolved) and alert.resolved_at is None:
        alert.resolved_at = now

    db.commit()
    db.refresh(alert)
    return AlertRead.model_validate(alert)
