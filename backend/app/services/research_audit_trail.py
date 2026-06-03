"""M63: Research Audit Trail v2 service.

Read-only service — no new database tables, no AuditTimelineEvent written.
Uses existing AuditTimelineEvent data to produce a richly-enriched,
deterministic audit trail for a strategy's research lifecycle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.models.strategy import Strategy
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.alert import Alert
from app.models.review_case import ResearchReviewCase

try:
    from app.services.change_impact import analyze_strategy_change_impact
    _CHANGE_IMPACT_AVAILABLE = True
except Exception:
    _CHANGE_IMPACT_AVAILABLE = False

try:
    from app.services.evidence_graph import build_strategy_evidence_graph
    _EVIDENCE_GRAPH_AVAILABLE = True
except Exception:
    _EVIDENCE_GRAPH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AuditLinkedObjectData:
    object_type: str
    object_id: str
    label: str
    route_hint: str | None = None


@dataclass
class AuditStatusTransitionData:
    previous_status: str | None
    new_status: str | None
    status_type: str | None
    transition_label: str | None


@dataclass
class AuditDownstreamContextData:
    impacted_artifact_count: int = 0
    recommended_rechecks: list = field(default_factory=list)  # capped at 5 str
    affected_readiness: bool = False
    affected_promotion_gates: bool = False
    affected_review_cases: bool = False
    affected_freeze_recommendation: bool = False


@dataclass
class ResearchAuditEventData:
    event_id: str
    event_time: datetime
    event_type: str
    title: str
    description: str | None
    severity: str
    source_type: str | None
    source_id: str | None
    category: str
    importance: str
    research_phase: str
    linked_object: AuditLinkedObjectData | None
    downstream_context: AuditDownstreamContextData | None
    status_transition: AuditStatusTransitionData | None
    evidence_summary_json: dict
    suggested_action: str | None


@dataclass
class ResearchAuditTrailData:
    strategy_id: str
    strategy_name: str
    generated_at: datetime
    total_events: int
    returned_count: int
    category_counts: dict
    importance_counts: dict
    phase_counts: dict
    high_importance_count: int
    latest_event_at: datetime | None
    latest_governance_event_at: datetime | None
    latest_evidence_event_at: datetime | None
    unresolved_review_case_count: int
    open_alert_count: int
    latest_freeze_recommendation: str | None
    deterministic_summary: str
    suggested_checks: list
    events: list  # list[ResearchAuditEventData]


# ---------------------------------------------------------------------------
# Category / phase / importance mapping constants
# ---------------------------------------------------------------------------

EVENT_CATEGORY_MAP: dict[str, str] = {
    # Setup/creation
    "strategy_created": "setup",
    "strategy_version_created": "config",
    # Run
    "strategy_run_logged": "run",
    "run_logged": "run",
    # Data
    "dataset_snapshot_created": "data",
    "dataset_snapshot_uploaded": "data",
    "dataset_uploaded": "data",
    "data_quality_issue_created": "data",
    "data_issue_detected": "data",
    "dataset_comparison_created": "data",
    "dataset_snapshot_ingested": "data",
    "data_quality_computed": "data",
    # Signal
    "signal_snapshot_created": "signal",
    "signal_snapshot_logged": "signal",
    # Universe
    "universe_snapshot_created": "universe",
    "universe_snapshot_logged": "universe",
    # Config
    "config_snapshot_created": "config",
    "strategy_config_snapshot_logged": "config",
    "config_snapshot_logged": "config",
    # Backtest
    "backtest_run_logged": "backtest",
    "backtest_audited": "backtest",
    "backtest_audit_computed": "backtest",
    "backtest_reality_check": "backtest",
    # Reliability
    "reliability_diagnosed": "reliability",
    "reliability_score_computed": "reliability",
    "reliability_score_generated": "reliability",
    "reliability_scored": "reliability",
    "strategy_reliability_scored": "reliability",
    # Alerts
    "alert_raised": "alert",
    "alert_generated": "alert",
    "alert_status_changed": "alert",
    "alert_created": "alert",
    "alerts_generated": "alert",
    "alert_acknowledged": "alert",
    "alert_resolved": "alert",
    "alert_triggered": "alert",
    "alert_dismissed": "alert",
    "live_run_started": "run",
    "live_run_completed": "run",
    # Reports
    "report_generated": "report",
    "report_created": "report",
    # Ingestion
    "evidence_bundle_ingested": "ingestion",
    # Regression
    "regression_tests_run": "regression",
    # Policy
    "config_policy_evaluated": "policy",
    # SLA
    "evidence_sla_evaluated": "sla",
    # Review cases
    "research_review_cases_generated": "review_case",
    "research_review_case_acknowledged": "review_case",
    "research_review_case_resolved": "review_case",
    # Experiment
    "strategy_experiment_created": "experiment",
    "strategy_experiment_run_added": "experiment",
    "strategy_experiment_analyzed": "experiment",
    "strategy_sweep_analyzed": "experiment",
    # Change impact
    "strategy_change_impact_analyzed": "config",
    # System/demo
    "demo_seeded": "system",
    "api_key_created": "system",
    "api_key_revoked": "system",
}

# Source-type based fallback mapping
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
    "strategy": "setup",
    "strategy_version": "config",
    "regression_test_run": "regression",
    "config_policy_evaluation": "policy",
    "evidence_sla": "sla",
    "review_case": "review_case",
    "experiment": "experiment",
}

EVIDENCE_CATEGORIES = {
    "data", "signal", "universe", "config", "run", "backtest", "reliability", "ingestion"
}
GOVERNANCE_CATEGORIES = {
    "regression", "policy", "sla", "review_case", "promotion", "freeze", "alert"
}

PHASE_MAP: dict[str, str] = {
    "setup": "setup",
    "config": "evidence_logging",
    "run": "evidence_logging",
    "data": "evidence_logging",
    "signal": "evidence_logging",
    "universe": "evidence_logging",
    "backtest": "backtest_review",
    "reliability": "quality_review",
    "alert": "quality_review",
    "regression": "progression_review",
    "policy": "progression_review",
    "sla": "progression_review",
    "review_case": "governance_review",
    "promotion": "governance_review",
    "freeze": "governance_review",
    "report": "reporting",
    "experiment": "evidence_logging",
    "ingestion": "evidence_logging",
    "system": "setup",
    "other": "unknown",
}

IMPORTANCE_MAP: dict[str, str] = {
    "critical": "critical",
    "error": "high",
    "high": "high",
    "warning": "medium",
    "info": "low",
    "low": "low",
}

ROUTE_HINTS: dict[str, str] = {
    "run": "/strategies/{strategy_id}#run-history",
    "data": "/strategies/{strategy_id}#data-health",
    "signal": "/strategies/{strategy_id}#signal-evidence",
    "universe": "/strategies/{strategy_id}#universe-evidence",
    "config": "/strategies/{strategy_id}#config-snapshots",
    "setup": "/strategies/{strategy_id}",
    "backtest": "/backtests/audits",
    "reliability": "/strategies/{strategy_id}#reliability",
    "regression": "/strategies/{strategy_id}#regression-tests",
    "policy": "/strategies/{strategy_id}#config-policy",
    "sla": "/strategies/{strategy_id}#evidence-sla",
    "review_case": "/strategies/{strategy_id}#review-cases",
    "experiment": "/strategies/{strategy_id}#experiments",
    "report": "/reports",
    "alert": "/alerts",
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _get_category(event_type: str | None, source_type: str | None) -> str:
    """Determine audit category from event_type first, then source_type."""
    if event_type is not None:
        cat = EVENT_CATEGORY_MAP.get(event_type)
        if cat is not None:
            return cat
    if source_type is not None:
        cat = SOURCE_TYPE_CATEGORY_MAP.get(source_type)
        if cat is not None:
            return cat
    return "other"


def _get_importance(event: AuditTimelineEvent, category: str) -> str:
    """Compute importance from severity with governance boosts."""
    severity = (event.severity or "info").lower()
    base = IMPORTANCE_MAP.get(severity, "low")

    # Boost governance events
    if category in GOVERNANCE_CATEGORIES:
        if base == "low":
            base = "medium"
        if severity in ("critical", "error"):
            base = "critical"
        elif base == "medium":
            base = "high"

    # Boost regression failures
    if category == "regression" and severity in ("error", "warning"):
        if base not in ("critical", "high"):
            base = "high"

    return base


def _get_research_phase(category: str) -> str:
    """Map category to research lifecycle phase."""
    return PHASE_MAP.get(category, "unknown")


def _extract_status_transition(
    event: AuditTimelineEvent, category: str
) -> AuditStatusTransitionData | None:
    """Extract status transition data from event metadata, if applicable."""
    meta = event.metadata_json or {}
    et = event.event_type or ""

    if et == "regression_tests_run":
        new_status = meta.get("overall_status")
        if new_status:
            return AuditStatusTransitionData(
                previous_status=None,
                new_status=new_status,
                status_type="regression_status",
                transition_label=f"Regression status: {new_status}",
            )

    elif et == "config_policy_evaluated":
        new_status = meta.get("overall_status")
        if new_status:
            return AuditStatusTransitionData(
                previous_status=None,
                new_status=new_status,
                status_type="policy_status",
                transition_label=f"Policy evaluation: {new_status}",
            )

    elif et == "evidence_sla_evaluated":
        new_status = meta.get("overall_status")
        if new_status:
            return AuditStatusTransitionData(
                previous_status=None,
                new_status=new_status,
                status_type="sla_status",
                transition_label=f"SLA status: {new_status}",
            )

    elif et == "research_review_cases_generated":
        case_count = meta.get("case_count", 1)
        return AuditStatusTransitionData(
            previous_status=None,
            new_status="open",
            status_type="review_case_status",
            transition_label=f"Review case(s) opened ({case_count})",
        )

    elif et == "research_review_case_acknowledged":
        return AuditStatusTransitionData(
            previous_status="open",
            new_status="acknowledged",
            status_type="review_case_status",
            transition_label="Review case acknowledged",
        )

    elif et == "research_review_case_resolved":
        return AuditStatusTransitionData(
            previous_status=None,
            new_status="resolved",
            status_type="review_case_status",
            transition_label="Review case resolved",
        )

    elif et == "strategy_experiment_analyzed":
        new_status = meta.get("overall_status")
        if new_status:
            return AuditStatusTransitionData(
                previous_status=None,
                new_status=new_status,
                status_type="experiment_status",
                transition_label=f"Experiment analysis: {new_status}",
            )

    elif et == "alert_status_changed":
        old_status = meta.get("previous_status")
        new_status = meta.get("new_status")
        if new_status:
            return AuditStatusTransitionData(
                previous_status=old_status,
                new_status=new_status,
                status_type="alert_status",
                transition_label=f"Alert status changed to {new_status}",
            )

    return None


def _build_linked_object(
    event: AuditTimelineEvent, category: str, strategy_id: str
) -> AuditLinkedObjectData | None:
    """Build linked object reference from source_type/source_id."""
    source_id = event.source_id
    if not source_id:
        return None

    source_type = event.source_type or category
    short_id = source_id[:8] if len(source_id) >= 8 else source_id

    # Human-readable label
    label_map = {
        "strategy_run": "Strategy Run",
        "dataset_snapshot": "Dataset Snapshot",
        "backtest_audit": "Backtest Audit",
        "strategy_config_snapshot": "Config Snapshot",
        "universe_snapshot": "Universe Snapshot",
        "signal_snapshot": "Signal Snapshot",
        "strategy_reliability_score": "Reliability Score",
        "report": "Report",
        "alert": "Alert",
        "sdk_ingestion_batch": "SDK Ingestion",
        "strategy": "Strategy",
        "strategy_version": "Strategy Version",
        "regression_test_run": "Regression Test Run",
        "config_policy_evaluation": "Policy Evaluation",
        "evidence_sla": "Evidence SLA",
        "review_case": "Review Case",
        "experiment": "Experiment",
    }
    label_base = label_map.get(source_type, source_type.replace("_", " ").title())
    label = f"{label_base} {short_id}"

    # Route hint
    route_template = ROUTE_HINTS.get(category)
    route_hint = route_template.replace("{strategy_id}", strategy_id) if route_template else None

    return AuditLinkedObjectData(
        object_type=source_type,
        object_id=source_id,
        label=label,
        route_hint=route_hint,
    )


def _build_downstream_context(
    db: Session,
    event: AuditTimelineEvent,
    category: str,
    strategy_id_obj,
    include_context: bool,
) -> AuditDownstreamContextData | None:
    """Build downstream impact context for evidence category events."""
    if not include_context:
        return None

    # Only compute for evidence categories and if change impact is available
    if category not in EVIDENCE_CATEGORIES:
        return None

    if not _CHANGE_IMPACT_AVAILABLE or not event.source_id:
        return None

    try:
        result = analyze_strategy_change_impact(
            db,
            strategy_id_obj,
            focus_node_id=event.source_id,
            focus_node_type=category,
            mode="focus_node",
        )
        if not isinstance(result, dict):
            return AuditDownstreamContextData(impacted_artifact_count=0)

        impacted = result.get("impacted_artifacts", [])
        rechecks_raw = result.get("recommended_rechecks", [])
        rechecks = []
        for r in rechecks_raw[:5]:
            if isinstance(r, dict):
                rechecks.append(r.get("title", str(r)))
            else:
                rechecks.append(str(r))

        readiness_impacts = result.get("readiness_impacts", {})
        impact_level = ""
        if isinstance(readiness_impacts, dict):
            impact_level = readiness_impacts.get("impact_level", "")

        return AuditDownstreamContextData(
            impacted_artifact_count=len(impacted) if isinstance(impacted, list) else 0,
            recommended_rechecks=rechecks,
            affected_readiness=impact_level not in ("none", "", None),
            affected_promotion_gates=bool(result.get("affected_promotion_gates", False)),
            affected_review_cases=bool(result.get("affected_review_cases", False)),
            affected_freeze_recommendation=bool(result.get("affected_freeze_recommendation", False)),
        )
    except Exception:
        return AuditDownstreamContextData(impacted_artifact_count=0)


def _build_suggested_action(
    event: AuditTimelineEvent,
    category: str,
    status_transition: AuditStatusTransitionData | None,
) -> str | None:
    """Return a deterministic suggested action based on event context."""
    new_status = status_transition.new_status if status_transition else None

    if category == "regression":
        if new_status in ("failed", "warning"):
            return "Run Regression Test Suite again after resolving failed checks."
        return None

    if category == "policy":
        if new_status == "failed":
            return "Fix config policy violations before progressing."
        return None

    if category == "sla":
        if new_status in ("violated", "warning"):
            return "Refresh stale evidence to resolve SLA violations."
        return None

    if category == "review_case":
        if new_status == "open":
            return "Review and acknowledge open research review cases."
        return None

    if category == "data":
        return "Inspect dataset quality drill-down if evidence was recently updated."

    if category == "signal":
        return "Inspect signal quality drill-down after signal snapshot updates."

    if category == "config":
        return "Re-evaluate config policy and assumption health after config changes."

    if category == "run":
        return "Run Backtest Reality Check for new strategy runs."

    if category == "backtest":
        return "Review Backtest audit findings and re-evaluate promotion gates."

    if category == "reliability":
        return "Refresh readiness scorecard and promotion gates after reliability score update."

    return None


def _sanitize_metadata(metadata_json: dict | None) -> dict:
    """Return a copy of metadata with sensitive keys stripped."""
    if not metadata_json:
        return {}
    forbidden_keys = {"api_key", "secret", "password", "token", "credential", "access_key"}
    return {
        k: v
        for k, v in metadata_json.items()
        if not any(fk in k.lower() for fk in forbidden_keys)
    }


def _enrich_event(
    db: Session,
    event: AuditTimelineEvent,
    strategy_id_obj,
    strategy_id_str: str,
    include_context: bool,
) -> ResearchAuditEventData:
    """Enrich a single AuditTimelineEvent into ResearchAuditEventData."""
    category = _get_category(event.event_type, event.source_type)
    importance = _get_importance(event, category)
    research_phase = _get_research_phase(category)
    status_transition = _extract_status_transition(event, category)
    linked_object = _build_linked_object(event, category, strategy_id_str)
    downstream_context = _build_downstream_context(
        db, event, category, strategy_id_obj, include_context
    )
    suggested_action = _build_suggested_action(event, category, status_transition)

    evidence_summary_json = {
        "event_type": event.event_type,
        "source_type": event.source_type,
        "source_id": event.source_id,
        "metadata": _sanitize_metadata(event.metadata_json),
    }

    return ResearchAuditEventData(
        event_id=str(event.id),
        event_time=event.event_time,
        event_type=event.event_type,
        title=event.title,
        description=event.description,
        severity=event.severity,
        source_type=event.source_type,
        source_id=event.source_id,
        category=category,
        importance=importance,
        research_phase=research_phase,
        linked_object=linked_object,
        downstream_context=downstream_context,
        status_transition=status_transition,
        evidence_summary_json=evidence_summary_json,
        suggested_action=suggested_action,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def get_strategy_research_audit_trail(
    db: Session,
    strategy_id,
    *,
    limit: int = 100,
    offset: int = 0,
    category: str | None = None,
    severity: str | None = None,
    include_context: bool = True,
) -> ResearchAuditTrailData:
    """Build a research audit trail for a strategy.

    Read-only — no AuditTimelineEvent is created.
    Deterministic — no AI, no live market data.
    Not investment advice.
    """
    import uuid as _uuid

    # Normalise strategy_id to a UUID object and string
    if isinstance(strategy_id, str):
        strategy_id_obj = _uuid.UUID(strategy_id)
    else:
        strategy_id_obj = strategy_id
    strategy_id_str = str(strategy_id_obj)

    # 1. Load strategy
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id_obj).first()
    if strategy is None:
        raise ValueError(f"Strategy not found: {strategy_id_str}")

    strategy_name = strategy.name

    # 2. Build base query — newest first
    base_q = (
        db.query(AuditTimelineEvent)
        .filter(AuditTimelineEvent.strategy_id == strategy_id_obj)
        .order_by(desc(AuditTimelineEvent.event_time))
    )

    # Apply severity filter at DB level if provided
    if severity:
        base_q = base_q.filter(AuditTimelineEvent.severity == severity)

    # 3. Get total count before limit/offset (and before in-memory category filter)
    total_events = base_q.count()

    # 4. For category filter: fetch a larger set and filter in memory, then slice
    if category is not None:
        # Build reverse lookup: which event_types map to this category?
        matching_event_types = {
            et for et, cat in EVENT_CATEGORY_MAP.items() if cat == category
        }
        matching_source_types = {
            st for st, cat in SOURCE_TYPE_CATEGORY_MAP.items() if cat == category
        }

        # Fetch more rows to account for filtering loss
        fetch_limit = min((limit + offset) * 4 + 100, 1000)
        raw_events = base_q.limit(fetch_limit).all()

        filtered_events = []
        for ev in raw_events:
            ev_cat = _get_category(ev.event_type, ev.source_type)
            if ev_cat == category:
                filtered_events.append(ev)

        total_events = len(filtered_events)
        page_events = filtered_events[offset: offset + limit]
    else:
        page_events = base_q.offset(offset).limit(limit).all()

    # 5. Enrich events
    enriched: list[ResearchAuditEventData] = []
    for ev in page_events:
        try:
            enriched.append(
                _enrich_event(db, ev, strategy_id_obj, strategy_id_str, include_context)
            )
        except Exception:
            pass

    # 6. Compute summary statistics from enriched events
    category_counts: dict[str, int] = {}
    importance_counts: dict[str, int] = {}
    phase_counts: dict[str, int] = {}
    latest_event_at: datetime | None = None
    latest_governance_event_at: datetime | None = None
    latest_evidence_event_at: datetime | None = None

    for e in enriched:
        category_counts[e.category] = category_counts.get(e.category, 0) + 1
        importance_counts[e.importance] = importance_counts.get(e.importance, 0) + 1
        phase_counts[e.research_phase] = phase_counts.get(e.research_phase, 0) + 1

        if latest_event_at is None or e.event_time > latest_event_at:
            latest_event_at = e.event_time

        if e.category in GOVERNANCE_CATEGORIES:
            if latest_governance_event_at is None or e.event_time > latest_governance_event_at:
                latest_governance_event_at = e.event_time

        if e.category in EVIDENCE_CATEGORIES:
            if latest_evidence_event_at is None or e.event_time > latest_evidence_event_at:
                latest_evidence_event_at = e.event_time

    high_importance_count = (
        importance_counts.get("high", 0) + importance_counts.get("critical", 0)
    )

    # 7. Open alert count
    try:
        open_alert_count = (
            db.query(Alert)
            .filter(
                Alert.strategy_id == strategy_id_str,
                Alert.status == "open",
            )
            .count()
        )
    except Exception:
        open_alert_count = 0

    # 8. Unresolved review case count
    try:
        unresolved_review_case_count = (
            db.query(ResearchReviewCase)
            .filter(
                ResearchReviewCase.strategy_id == strategy_id_str,
                ResearchReviewCase.status == "open",
            )
            .count()
        )
    except Exception:
        unresolved_review_case_count = 0

    # 9. Latest freeze recommendation from metadata
    latest_freeze_recommendation: str | None = None
    try:
        freeze_events = (
            db.query(AuditTimelineEvent)
            .filter(
                AuditTimelineEvent.strategy_id == strategy_id_obj,
                AuditTimelineEvent.event_type.in_([
                    "progression_freeze_evaluated",
                    "strategy_freeze_evaluated",
                ]),
            )
            .order_by(desc(AuditTimelineEvent.event_time))
            .limit(1)
            .all()
        )
        if freeze_events:
            fe_meta = freeze_events[0].metadata_json or {}
            latest_freeze_recommendation = fe_meta.get("recommendation")
    except Exception:
        pass

    # 10. Deterministic summary
    deterministic_summary = _build_deterministic_summary(
        strategy_name=strategy_name,
        total_events=total_events,
        category_counts=category_counts,
        high_importance_count=high_importance_count,
        open_alert_count=open_alert_count,
        unresolved_review_case_count=unresolved_review_case_count,
    )

    # 11. Suggested checks (deterministic)
    suggested_checks = _build_suggested_checks(
        category_counts=category_counts,
        importance_counts=importance_counts,
        open_alert_count=open_alert_count,
        unresolved_review_case_count=unresolved_review_case_count,
    )

    return ResearchAuditTrailData(
        strategy_id=strategy_id_str,
        strategy_name=strategy_name,
        generated_at=datetime.now(timezone.utc),
        total_events=total_events,
        returned_count=len(enriched),
        category_counts=category_counts,
        importance_counts=importance_counts,
        phase_counts=phase_counts,
        high_importance_count=high_importance_count,
        latest_event_at=latest_event_at,
        latest_governance_event_at=latest_governance_event_at,
        latest_evidence_event_at=latest_evidence_event_at,
        unresolved_review_case_count=unresolved_review_case_count,
        open_alert_count=open_alert_count,
        latest_freeze_recommendation=latest_freeze_recommendation,
        deterministic_summary=deterministic_summary,
        suggested_checks=suggested_checks,
        events=enriched,
    )


# ---------------------------------------------------------------------------
# Summary builders
# ---------------------------------------------------------------------------

def _build_deterministic_summary(
    *,
    strategy_name: str,
    total_events: int,
    category_counts: dict,
    high_importance_count: int,
    open_alert_count: int,
    unresolved_review_case_count: int,
) -> str:
    """Build a deterministic, human-readable audit trail summary.

    Language policy:
    - No AI language ("prediction", "AI-generated", etc.)
    - No investment advice ("buy", "sell", "profitable", etc.)
    - No alarming language ("incident", "breach", "strategy failed", "do not trade")
    """
    parts = [
        f"Audit trail for '{strategy_name}': {total_events} total recorded event(s).",
    ]

    if total_events == 0:
        parts.append("No timeline events found for this strategy.")
        return " ".join(parts)

    if high_importance_count > 0:
        parts.append(
            f"{high_importance_count} event(s) are classified as high or critical importance."
        )

    # Summarise category distribution
    dominant_cats = sorted(category_counts.items(), key=lambda x: -x[1])[:3]
    if dominant_cats:
        cat_summary = ", ".join(f"{cat} ({cnt})" for cat, cnt in dominant_cats)
        parts.append(f"Top categories: {cat_summary}.")

    if open_alert_count > 0:
        parts.append(f"{open_alert_count} open alert(s) require attention.")

    if unresolved_review_case_count > 0:
        parts.append(
            f"{unresolved_review_case_count} research review case(s) are pending resolution."
        )

    return " ".join(parts)


def _build_suggested_checks(
    *,
    category_counts: dict,
    importance_counts: dict,
    open_alert_count: int,
    unresolved_review_case_count: int,
) -> list[str]:
    """Return a deterministic list of suggested checks based on audit trail content."""
    checks: list[str] = []

    if open_alert_count > 0:
        checks.append("Review open alerts and determine whether evidence refresh is required.")

    if unresolved_review_case_count > 0:
        checks.append("Acknowledge and resolve pending research review cases.")

    if category_counts.get("regression", 0) > 0:
        checks.append("Inspect regression test history for any failed or warning runs.")

    if category_counts.get("policy", 0) > 0:
        checks.append("Verify config policy evaluation results and address any violations.")

    if category_counts.get("sla", 0) > 0:
        checks.append("Check evidence SLA evaluations and refresh any stale evidence types.")

    if category_counts.get("backtest", 0) > 0:
        checks.append(
            "Review backtest audit findings before progressing to later research stages."
        )

    if category_counts.get("reliability", 0) > 0:
        checks.append("Confirm reliability scores are current and readiness scorecard is up to date.")

    if importance_counts.get("critical", 0) > 0:
        checks.append("Address all critical-importance events before progressing.")

    return checks
