"""Pydantic schemas for the Alerts Engine (M11 + M85 lifecycle)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

from app.services.alert_catalog import DISCLAIMER


class AlertRead(BaseModel):
    """Full alert record — returned from GET endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    rule_type: str
    status: str
    severity: str
    title: str
    description: str | None
    source_type: str | None
    source_id: str | None
    strategy_id: uuid.UUID | None
    triggered_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    snoozed_until: datetime | None
    metadata_json: dict | None
    # M85 additions
    recommended_fix: str | None = None
    owner_user_id: str | None = None
    disclaimer: str = DISCLAIMER
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence_type(self) -> str | None:
        """Alias of ``source_type`` for the M85 evidence-centric UI."""
        return self.source_type

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence_id(self) -> str | None:
        """Alias of ``source_id`` for the M85 evidence-centric UI."""
        return self.source_id


class AlertListResponse(BaseModel):
    """Paginated list of alerts."""

    items: list[AlertRead]
    total: int
    limit: int
    offset: int


class AlertGenerateResponse(BaseModel):
    """Summary returned after running the alert-generation service."""

    alerts_created: int
    alerts_skipped_duplicate: int
    alerts_auto_resolved: int = 0
    total_alerts_open: int


# ---------------------------------------------------------------------------
# Alert history
# ---------------------------------------------------------------------------

class AlertHistoryRead(BaseModel):
    """A single audit-log entry for a lifecycle action on an alert."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alert_id: uuid.UUID
    actor_user_id: str | None
    action: str
    note: str | None
    created_at: datetime


class AlertHistoryListResponse(BaseModel):
    items: list[AlertHistoryRead]


# ---------------------------------------------------------------------------
# Alert rules
# ---------------------------------------------------------------------------

class AlertRuleRead(BaseModel):
    """Alert rule exposed with M85 field naming (rule_key / enabled / threshold_json)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    rule_key: str
    enabled: bool
    severity: str | None
    threshold: int | None = None
    threshold_json: dict | None
    strategy_id: str | None
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _map_aliases(cls, data):
        """Map ORM column names (rule_type/is_active/config_json) to M85 names."""
        if isinstance(data, dict):
            return data
        # ORM object — build a dict with the renamed keys.
        return {
            "id": getattr(data, "id", None),
            "organization_id": getattr(data, "organization_id", None),
            "rule_key": getattr(data, "rule_type", None),
            "enabled": getattr(data, "is_active", None),
            "severity": getattr(data, "severity", None),
            "threshold": getattr(data, "threshold", None),
            "threshold_json": getattr(data, "config_json", None),
            "strategy_id": getattr(data, "strategy_id", None),
            "name": getattr(data, "name", None),
            "description": getattr(data, "description", None),
            "created_at": getattr(data, "created_at", None),
            "updated_at": getattr(data, "updated_at", None),
        }


class AlertRuleListResponse(BaseModel):
    items: list[AlertRuleRead]


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class AlertUpdateRequest(BaseModel):
    """Partial update — status, owner assignment, and/or a free-text note."""

    status: str | None = None
    owner_user_id: str | None = None
    note: str | None = None


class AlertAcknowledgeRequest(BaseModel):
    note: str | None = None


class AlertResolveRequest(BaseModel):
    note: str | None = None


class AlertSnoozeRequest(BaseModel):
    hours: int | None = 24
    snoozed_until: datetime | None = None
    note: str | None = None


class AlertRuleUpdateRequest(BaseModel):
    enabled: bool | None = None
    severity: str | None = None
    threshold_json: dict | None = None
    name: str | None = None
    description: str | None = None


# ---------------------------------------------------------------------------
# Strategy / org summaries
# ---------------------------------------------------------------------------

class StrategyAlertSummaryResponse(BaseModel):
    """Status/severity breakdown of alerts for a single strategy."""

    open: int
    acknowledged: int
    snoozed: int
    resolved: int
    by_severity: dict[str, int]
    blocking_promotion: int


class AlertSeveritySummaryResponse(BaseModel):
    """Org-level severity/status summary of alerts."""

    open: int
    acknowledged: int
    snoozed: int
    resolved: int
    by_severity: dict[str, int]
