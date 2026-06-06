"""Alerts Engine API endpoints (M11 + M85 lifecycle).

M11:
  POST  /api/alerts/generate             — trigger alert generation for the org
  GET   /api/alerts                      — list alerts (filterable, paginated)
  GET   /api/alerts/{alert_id}           — fetch a single alert
  PATCH /api/alerts/{alert_id}           — update alert status/owner/note

M85:
  POST  /api/strategies/{id}/alerts/generate   — generate for one strategy
  GET   /api/strategies/{id}/alerts            — list a strategy's alerts
  GET   /api/strategies/{id}/alerts/summary    — strategy alert summary
  POST  /api/alerts/{id}/acknowledge
  POST  /api/alerts/{id}/resolve
  POST  /api/alerts/{id}/snooze
  GET   /api/alerts/{id}/history
  GET   /api/alerts/rules
  PATCH /api/alerts/rules/{rule_id}
  GET   /api/alerts/summary
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_optional_current_user
from app.core.constants import AlertAction, AlertStatus
from app.core.rbac import (
    require_verified_email,
    require_workspace_admin,
    require_workspace_write_access,
)
from app.db.session import get_db
from app.models.alert import Alert
from app.models.alert_history import AlertHistory
from app.models.alert_rule import AlertRule
from app.models.organization import Organization
from app.schemas.alerts import (
    AlertAcknowledgeRequest,
    AlertGenerateResponse,
    AlertHistoryListResponse,
    AlertHistoryRead,
    AlertListResponse,
    AlertRead,
    AlertResolveRequest,
    AlertRuleListResponse,
    AlertRuleRead,
    AlertRuleUpdateRequest,
    AlertSeveritySummaryResponse,
    AlertSnoozeRequest,
    AlertUpdateRequest,
    StrategyAlertSummaryResponse,
)
from app.services.alerts import (
    generate_alerts,
    generate_alerts_for_strategy,
    get_strategy_alert_summary,
    record_alert_history,
)

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


def _actor_id(current) -> str | None:
    return str(current.id) if current is not None else None


def _load_alert(db: Session, alert_id: uuid.UUID) -> Alert:
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return alert


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

@router.post("/alerts/generate", response_model=AlertGenerateResponse)
def trigger_alert_generation(
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_write_access),
    _verified=Depends(require_verified_email),
) -> AlertGenerateResponse:
    """Run the deterministic alert-generation service and return a summary."""
    org = _get_default_org(db)
    if org is None:
        raise HTTPException(status_code=404, detail="No organisation found.")

    org_id = str(org.id)
    result = generate_alerts(db, org_id)
    db.commit()

    return AlertGenerateResponse(
        alerts_created=result.alerts_created,
        alerts_skipped_duplicate=result.alerts_skipped_duplicate,
        alerts_auto_resolved=result.alerts_auto_resolved,
        total_alerts_open=result.total_alerts_open,
    )


@router.post(
    "/strategies/{strategy_id}/alerts/generate", response_model=AlertGenerateResponse
)
def trigger_strategy_alert_generation(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_write_access),
    _verified=Depends(require_verified_email),
) -> AlertGenerateResponse:
    """Generate alerts scoped to a single strategy (auto-resolve scoped too)."""
    counts = generate_alerts_for_strategy(db, str(strategy_id))
    db.commit()
    return AlertGenerateResponse(
        alerts_created=counts["alerts_created"],
        alerts_skipped_duplicate=counts["alerts_skipped_duplicate"],
        alerts_auto_resolved=counts["alerts_auto_resolved"],
        total_alerts_open=counts["total_alerts_open"],
    )


# ---------------------------------------------------------------------------
# Strategy-scoped reads
# ---------------------------------------------------------------------------

@router.get("/strategies/{strategy_id}/alerts", response_model=AlertListResponse)
def list_strategy_alerts(
    strategy_id: uuid.UUID,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> AlertListResponse:
    """List alerts for a single strategy, optionally filtered by status."""
    q = db.query(Alert).filter(Alert.strategy_id == str(strategy_id))
    if status is not None:
        q = q.filter(Alert.status == status)
    total = q.count()
    items = q.order_by(Alert.triggered_at.desc()).offset(offset).limit(limit).all()
    return AlertListResponse(
        items=[AlertRead.model_validate(a) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/strategies/{strategy_id}/alerts/summary",
    response_model=StrategyAlertSummaryResponse,
)
def strategy_alert_summary(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StrategyAlertSummaryResponse:
    """Return the status/severity breakdown of a strategy's alerts."""
    summary = get_strategy_alert_summary(db, str(strategy_id))
    return StrategyAlertSummaryResponse(**summary)


# ---------------------------------------------------------------------------
# Org-level reads
# ---------------------------------------------------------------------------

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
    items = q.order_by(Alert.triggered_at.desc()).offset(offset).limit(limit).all()
    return AlertListResponse(
        items=[AlertRead.model_validate(a) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/alerts/summary", response_model=AlertSeveritySummaryResponse)
def alert_summary(
    db: Session = Depends(get_db),
) -> AlertSeveritySummaryResponse:
    """Org-level severity/status summary for the default org's alerts."""
    org = _get_default_org(db)
    counts = {"open": 0, "acknowledged": 0, "snoozed": 0, "resolved": 0}
    by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    if org is not None:
        alerts = db.query(Alert).filter(Alert.organization_id == str(org.id)).all()
        for a in alerts:
            st = str(a.status)
            if st in counts:
                counts[st] += 1
            if st == str(AlertStatus.open) and str(a.severity) in by_severity:
                by_severity[str(a.severity)] += 1
    return AlertSeveritySummaryResponse(
        open=counts["open"],
        acknowledged=counts["acknowledged"],
        snoozed=counts["snoozed"],
        resolved=counts["resolved"],
        by_severity=by_severity,
    )


# ---------------------------------------------------------------------------
# Alert rules
# ---------------------------------------------------------------------------

@router.get("/alerts/rules", response_model=AlertRuleListResponse)
def list_alert_rules(
    db: Session = Depends(get_db),
) -> AlertRuleListResponse:
    """List alert rules for the caller's (default) org."""
    org = _get_default_org(db)
    q = db.query(AlertRule)
    if org is not None:
        q = q.filter(AlertRule.organization_id == str(org.id))
    rules = q.order_by(AlertRule.created_at.asc()).all()
    return AlertRuleListResponse(items=[AlertRuleRead.model_validate(r) for r in rules])


@router.patch("/alerts/rules/{rule_id}", response_model=AlertRuleRead)
def update_alert_rule(
    rule_id: uuid.UUID,
    body: AlertRuleUpdateRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_workspace_admin),
    _verified=Depends(require_verified_email),
) -> AlertRuleRead:
    """Update an alert rule's enabled/severity/threshold_json/name/description."""
    rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Alert rule not found.")

    if body.enabled is not None:
        rule.is_active = body.enabled
    if body.severity is not None:
        rule.severity = body.severity
    if body.threshold_json is not None:
        rule.config_json = body.threshold_json
    if body.name is not None:
        rule.name = body.name
    if body.description is not None:
        rule.description = body.description

    db.commit()
    db.refresh(rule)
    return AlertRuleRead.model_validate(rule)


# ---------------------------------------------------------------------------
# Single alert reads
# ---------------------------------------------------------------------------

@router.get("/alerts/{alert_id}", response_model=AlertRead)
def get_alert(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> AlertRead:
    """Fetch a single alert by id."""
    alert = _load_alert(db, alert_id)
    return AlertRead.model_validate(alert)


@router.get("/alerts/{alert_id}/history", response_model=AlertHistoryListResponse)
def get_alert_history(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> AlertHistoryListResponse:
    """Return the audit log for an alert, oldest first."""
    _load_alert(db, alert_id)
    rows = (
        db.query(AlertHistory)
        .filter(AlertHistory.alert_id == str(alert_id))
        .order_by(AlertHistory.created_at.asc())
        .all()
    )
    return AlertHistoryListResponse(items=[AlertHistoryRead.model_validate(r) for r in rows])


# ---------------------------------------------------------------------------
# Lifecycle mutations
# ---------------------------------------------------------------------------

@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertRead)
def acknowledge_alert(
    alert_id: uuid.UUID,
    body: AlertAcknowledgeRequest,
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_write_access),
    _verified=Depends(require_verified_email),
    current=Depends(get_optional_current_user),
) -> AlertRead:
    """Acknowledge an alert."""
    alert = _load_alert(db, alert_id)
    now = datetime.now(timezone.utc)
    alert.status = str(AlertStatus.acknowledged)
    if alert.acknowledged_at is None:
        alert.acknowledged_at = now
    record_alert_history(
        db, str(alert.id), _actor_id(current), str(AlertAction.acknowledged), body.note
    )
    db.commit()
    db.refresh(alert)
    return AlertRead.model_validate(alert)


@router.post("/alerts/{alert_id}/resolve", response_model=AlertRead)
def resolve_alert(
    alert_id: uuid.UUID,
    body: AlertResolveRequest,
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_write_access),
    _verified=Depends(require_verified_email),
    current=Depends(get_optional_current_user),
) -> AlertRead:
    """Resolve an alert."""
    alert = _load_alert(db, alert_id)
    now = datetime.now(timezone.utc)
    alert.status = str(AlertStatus.resolved)
    alert.resolved_at = now
    record_alert_history(
        db, str(alert.id), _actor_id(current), str(AlertAction.resolved), body.note
    )
    db.commit()
    db.refresh(alert)
    return AlertRead.model_validate(alert)


@router.post("/alerts/{alert_id}/snooze", response_model=AlertRead)
def snooze_alert(
    alert_id: uuid.UUID,
    body: AlertSnoozeRequest,
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_write_access),
    _verified=Depends(require_verified_email),
    current=Depends(get_optional_current_user),
) -> AlertRead:
    """Snooze an alert until an explicit time or for N hours (default 24)."""
    alert = _load_alert(db, alert_id)
    now = datetime.now(timezone.utc)
    if body.snoozed_until is not None:
        snoozed_until = body.snoozed_until
    else:
        snoozed_until = now + timedelta(hours=body.hours or 24)
    alert.status = str(AlertStatus.snoozed)
    alert.snoozed_until = snoozed_until
    record_alert_history(
        db, str(alert.id), _actor_id(current), str(AlertAction.snoozed), body.note
    )
    db.commit()
    db.refresh(alert)
    return AlertRead.model_validate(alert)


@router.patch("/alerts/{alert_id}", response_model=AlertRead)
def update_alert_status(
    alert_id: uuid.UUID,
    body: AlertUpdateRequest,
    db: Session = Depends(get_db),
    _member=Depends(require_workspace_write_access),
    _verified=Depends(require_verified_email),
    current=Depends(get_optional_current_user),
) -> AlertRead:
    """Update an alert's status and/or owner, with an optional note.

    Status → matching timestamp + a history row using the corresponding action.
    Owner-only / note-only updates record a 'note' history row.
    """
    alert = _load_alert(db, alert_id)
    now = datetime.now(timezone.utc)
    actor = _actor_id(current)

    _status_action = {
        str(AlertStatus.open): str(AlertAction.reopened),
        str(AlertStatus.acknowledged): str(AlertAction.acknowledged),
        str(AlertStatus.snoozed): str(AlertAction.snoozed),
        str(AlertStatus.resolved): str(AlertAction.resolved),
        str(AlertStatus.dismissed): str(AlertAction.dismissed),
    }

    status_changed = False
    if body.status is not None:
        if body.status not in _VALID_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{body.status}'. Must be one of: {sorted(_VALID_STATUSES)}",
            )
        alert.status = body.status
        if body.status == str(AlertStatus.acknowledged) and alert.acknowledged_at is None:
            alert.acknowledged_at = now
        elif body.status == str(AlertStatus.resolved):
            alert.resolved_at = now
        record_alert_history(
            db, str(alert.id), actor, _status_action[body.status], body.note
        )
        status_changed = True

    if body.owner_user_id is not None:
        alert.owner_user_id = body.owner_user_id

    # Owner-only or note-only update → record a note entry.
    if not status_changed and (body.owner_user_id is not None or body.note is not None):
        record_alert_history(db, str(alert.id), actor, str(AlertAction.note), body.note)

    db.commit()
    db.refresh(alert)
    return AlertRead.model_validate(alert)
