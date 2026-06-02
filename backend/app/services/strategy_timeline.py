"""Strategy timeline drilldown service (M29).

Provides enriched, per-strategy timeline events with evidence_category,
source_label, and linked_url_hint fields.
"""
from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.audit_timeline_event import AuditTimelineEvent


# ---------------------------------------------------------------------------
# Category mappings
# ---------------------------------------------------------------------------

EVIDENCE_CATEGORY_MAP: dict[str, str] = {
    "strategy_run_logged": "run",
    "strategy_created": "config",
    "strategy_version_created": "config",
    "strategy_config_snapshot_logged": "config",
    "universe_snapshot_logged": "universe",
    "signal_snapshot_logged": "signal",
    "backtest_audit_computed": "backtest",
    "data_quality_computed": "data",
    "dataset_snapshot_ingested": "data",
    "strategy_reliability_scored": "reliability",
    "report_generated": "report",
    "api_key_created": "other",
    "api_key_revoked": "other",
    "evidence_bundle_ingested": "ingestion",
    "alert_triggered": "alert",
    "alert_resolved": "alert",
    "alert_dismissed": "alert",
}

SOURCE_TYPE_CATEGORY_MAP: dict[str, str] = {
    "strategy_run": "run",
    "dataset_snapshot": "data",
    "backtest_audit": "backtest",
    "strategy_config_snapshot": "config",
    "universe_snapshot": "universe",
    "signal_snapshot": "signal",
    "strategy_reliability_score": "reliability",
    "report": "report",
    "alert": "alert",
    "sdk_ingestion_batch": "ingestion",
    "strategy": "config",
    "strategy_version": "config",
}


def _get_evidence_category(event_type: str | None, source_type: str | None) -> str:
    """Determine evidence category from event_type or source_type."""
    if event_type is not None and event_type in EVIDENCE_CATEGORY_MAP:
        return EVIDENCE_CATEGORY_MAP[event_type]
    if source_type is not None and source_type in SOURCE_TYPE_CATEGORY_MAP:
        return SOURCE_TYPE_CATEGORY_MAP[source_type]
    return "other"


def _get_source_label(event: AuditTimelineEvent) -> str:
    """Human-readable label based on source_type and event_type."""
    source_type = event.source_type or ""
    event_type = event.event_type or ""

    if source_type == "strategy_run":
        return "Strategy Run"
    elif source_type == "dataset_snapshot":
        return "Dataset Snapshot"
    elif source_type == "backtest_audit":
        return "Backtest Audit"
    elif source_type == "strategy_config_snapshot":
        return "Config Snapshot"
    elif source_type == "universe_snapshot":
        return "Universe Snapshot"
    elif source_type == "signal_snapshot":
        return "Signal Snapshot"
    elif source_type == "strategy_reliability_score":
        return "Reliability Score"
    elif source_type == "report":
        return "Report"
    elif source_type == "alert":
        return "Alert"
    elif source_type == "sdk_ingestion_batch":
        return "SDK Ingestion"
    elif source_type == "strategy":
        return "Strategy"
    elif source_type == "strategy_version":
        return "Strategy Version"
    elif event_type == "strategy_run_logged":
        return "Strategy Run"
    elif event_type == "strategy_created":
        return "Strategy"
    elif event_type == "strategy_version_created":
        return "Version"
    elif event_type == "evidence_bundle_ingested":
        return "Evidence Bundle"
    elif event_type == "api_key_created":
        return "API Key"
    elif event_type == "api_key_revoked":
        return "API Key"
    else:
        return source_type.replace("_", " ").title() if source_type else "Event"


def _get_linked_url_hint(event: AuditTimelineEvent, strategy_id: uuid.UUID) -> str | None:
    """Frontend path hint for navigating to the source object."""
    source_type = event.source_type or ""
    source_id = event.source_id

    base = f"/strategies/{strategy_id}"

    if source_type == "strategy_run" and source_id:
        return f"{base}/runs/{source_id}"
    elif source_type == "dataset_snapshot" and source_id:
        return f"/dataset-snapshots/{source_id}"
    elif source_type == "backtest_audit" and source_id:
        return f"{base}/audits/{source_id}"
    elif source_type == "strategy_config_snapshot" and source_id:
        return f"{base}/config-snapshots/{source_id}"
    elif source_type == "universe_snapshot" and source_id:
        return f"{base}/universe-snapshots/{source_id}"
    elif source_type == "signal_snapshot" and source_id:
        return f"{base}/signal-snapshots/{source_id}"
    elif source_type == "strategy_reliability_score" and source_id:
        return f"{base}/reliability-score"
    elif source_type == "report" and source_id:
        return f"/reports/{source_id}"
    elif source_type == "alert" and source_id:
        return f"/alerts/{source_id}"
    elif source_type == "sdk_ingestion_batch" and source_id:
        return f"/ingestion/{source_id}"
    elif source_type == "strategy":
        return base
    elif source_type == "strategy_version" and source_id:
        return f"{base}/versions/{source_id}"
    else:
        return None


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StrategyTimelineDrilldownItem:
    event_id: uuid.UUID
    event_type: str
    title: str
    description: str | None
    severity: str
    event_time: datetime
    created_at: datetime
    source_type: str | None
    source_id: str | None
    evidence_category: str
    source_label: str
    linked_url_hint: str | None


@dataclass
class StrategyTimelineDrilldownSummaryData:
    total_events: int
    event_type_counts: dict
    source_type_counts: dict
    latest_event_at: datetime | None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_strategy_timeline_drilldown(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    limit: int = 100,
    offset: int = 0,
    event_type: str | None = None,
    source_type: str | None = None,
) -> tuple[list[StrategyTimelineDrilldownItem], StrategyTimelineDrilldownSummaryData]:
    """Return enriched timeline events for a strategy with optional filtering.

    Returns a paginated page and a summary with counts.
    """
    q = (
        db.query(AuditTimelineEvent)
        .filter(AuditTimelineEvent.strategy_id == strategy_id)
    )

    if event_type is not None:
        q = q.filter(AuditTimelineEvent.event_type == event_type)
    if source_type is not None:
        q = q.filter(AuditTimelineEvent.source_type == source_type)

    # Compute summary across ALL matching events (before pagination)
    all_events = q.order_by(AuditTimelineEvent.event_time.desc()).all()
    total_events = len(all_events)

    event_type_counts: Counter = Counter()
    source_type_counts: Counter = Counter()
    latest_event_at: datetime | None = None

    for ev in all_events:
        if ev.event_type:
            event_type_counts[ev.event_type] += 1
        if ev.source_type:
            source_type_counts[ev.source_type] += 1
        if latest_event_at is None or (ev.event_time is not None and ev.event_time > latest_event_at):
            latest_event_at = ev.event_time

    summary = StrategyTimelineDrilldownSummaryData(
        total_events=total_events,
        event_type_counts=dict(event_type_counts),
        source_type_counts=dict(source_type_counts),
        latest_event_at=latest_event_at,
    )

    # Paginate
    page_events = all_events[offset : offset + limit]

    items = [
        StrategyTimelineDrilldownItem(
            event_id=ev.id,
            event_type=ev.event_type,
            title=ev.title,
            description=ev.description,
            severity=ev.severity,
            event_time=ev.event_time,
            created_at=ev.created_at,
            source_type=ev.source_type,
            source_id=ev.source_id,
            evidence_category=_get_evidence_category(ev.event_type, ev.source_type),
            source_label=_get_source_label(ev),
            linked_url_hint=_get_linked_url_hint(ev, strategy_id),
        )
        for ev in page_events
    ]

    return items, summary
