"""M65A Strategy Reliability Snapshot Cache service.

Builds and persists cached snapshots of the reliability command center.
Snapshots are append-only — refreshed on demand or when source data changes.
Not investment advice or trading authorisation.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.models.reliability_snapshot import StrategyReliabilitySnapshot
from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun
from app.models.dataset_snapshot import DatasetSnapshot  # noqa: F401 — kept for future use
from app.models.signal_snapshot import SignalSnapshot  # noqa: F401
from app.models.strategy_config_snapshot import StrategyConfigSnapshot  # noqa: F401
from app.models.backtest_audit import BacktestAudit
from app.models.alert import Alert
from app.models.review_case import ResearchReviewCase
from app.models.audit_timeline_event import AuditTimelineEvent
from app.core.constants import EventType

try:
    from app.services.reliability_command_center import get_strategy_reliability_command_center
except ImportError:
    get_strategy_reliability_command_center = None  # type: ignore[assignment]

STALE_AFTER_HOURS = 24


# ---------------------------------------------------------------------------
# Source hash
# ---------------------------------------------------------------------------

def _compute_source_hash(db: Session, strategy_id: str) -> str:
    """Compute a short hash summarising the latest timestamps for a strategy.

    Any change in the underlying data will produce a different hash, causing
    the caller to create a fresh snapshot rather than reuse the existing one.
    """
    sid = str(strategy_id)
    parts: dict[str, str | None] = {}

    try:
        run = (
            db.query(StrategyRun.created_at)
            .filter(StrategyRun.strategy_id == sid)
            .order_by(StrategyRun.created_at.desc())
            .first()
        )
        parts["latest_run"] = run[0].isoformat() if run and run[0] else None
    except Exception:
        parts["latest_run"] = None

    try:
        audit = (
            db.query(BacktestAudit.created_at)
            .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
            .filter(StrategyRun.strategy_id == sid)
            .order_by(BacktestAudit.created_at.desc())
            .first()
        )
        parts["latest_audit"] = audit[0].isoformat() if audit and audit[0] else None
    except Exception:
        parts["latest_audit"] = None

    try:
        alert = (
            db.query(Alert.triggered_at)
            .filter(Alert.strategy_id == sid)
            .order_by(Alert.triggered_at.desc())
            .first()
        )
        parts["latest_alert"] = alert[0].isoformat() if alert and alert[0] else None
    except Exception:
        parts["latest_alert"] = None

    try:
        case = (
            db.query(ResearchReviewCase.updated_at)
            .filter(ResearchReviewCase.strategy_id == sid)
            .order_by(ResearchReviewCase.updated_at.desc())
            .first()
        )
        parts["latest_review_case"] = case[0].isoformat() if case and case[0] else None
    except Exception:
        parts["latest_review_case"] = None

    try:
        evt = (
            db.query(AuditTimelineEvent.event_time)
            .filter(
                AuditTimelineEvent.strategy_id == uuid.UUID(sid),
                AuditTimelineEvent.event_type != EventType.reliability_snapshot_refreshed,
            )
            .order_by(AuditTimelineEvent.event_time.desc())
            .first()
        )
        parts["latest_event"] = evt[0].isoformat() if evt and evt[0] else None
    except Exception:
        parts["latest_event"] = None

    payload = json.dumps(dict(sorted(parts.items())), sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return digest[:16]


# ---------------------------------------------------------------------------
# Staleness check
# ---------------------------------------------------------------------------

def is_snapshot_stale(
    db: Session,
    snapshot: StrategyReliabilitySnapshot,
) -> tuple[bool, list[str]]:
    """Return (is_stale, reasons) for the given snapshot.

    SQLite stores naive datetimes; all comparisons normalise to UTC.
    """
    reasons: list[str] = []
    sid = str(snapshot.strategy_id)

    # Normalise snapshot timestamps to UTC-aware for safe comparison.
    gen_at = snapshot.generated_at
    if gen_at.tzinfo is None:
        gen_at = gen_at.replace(tzinfo=timezone.utc)

    stale_after = snapshot.stale_after
    if stale_after.tzinfo is None:
        stale_after = stale_after.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)

    try:
        if now > stale_after:
            reasons.append("Snapshot older than 24 hours")
    except Exception:
        pass

    try:
        evt = (
            db.query(AuditTimelineEvent.event_time)
            .filter(
                AuditTimelineEvent.strategy_id == uuid.UUID(sid),
                AuditTimelineEvent.event_type != EventType.reliability_snapshot_refreshed,
            )
            .order_by(AuditTimelineEvent.event_time.desc())
            .first()
        )
        if evt and evt[0]:
            latest = evt[0]
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
            if latest > gen_at:
                reasons.append("New timeline events since snapshot")
    except Exception:
        pass

    try:
        run = (
            db.query(StrategyRun.created_at)
            .filter(StrategyRun.strategy_id == sid)
            .order_by(StrategyRun.created_at.desc())
            .first()
        )
        if run and run[0]:
            latest = run[0]
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
            if latest > gen_at:
                reasons.append("New run since snapshot")
    except Exception:
        pass

    try:
        alert = (
            db.query(Alert.triggered_at)
            .filter(Alert.strategy_id == sid)
            .order_by(Alert.triggered_at.desc())
            .first()
        )
        if alert and alert[0]:
            latest = alert[0]
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
            if latest > gen_at:
                reasons.append("New or updated alert since snapshot")
    except Exception:
        pass

    try:
        case = (
            db.query(ResearchReviewCase.updated_at)
            .filter(ResearchReviewCase.strategy_id == sid)
            .order_by(ResearchReviewCase.updated_at.desc())
            .first()
        )
        if case and case[0]:
            latest = case[0]
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
            if latest > gen_at:
                reasons.append("Review case updated since snapshot")
    except Exception:
        pass

    return bool(reasons), reasons


# ---------------------------------------------------------------------------
# Subsystem extraction helpers
# ---------------------------------------------------------------------------

def _find_subsystem(subsystems: list, key: str):
    """Return the first subsystem whose subsystem_key matches *key*."""
    for s in subsystems:
        if getattr(s, "subsystem_key", None) == key:
            return s
    return None


def _serialize_blockers(blockers: list, limit: int = 5) -> list[dict]:
    result = []
    for b in blockers[:limit]:
        result.append({
            "blocker_key": getattr(b, "blocker_key", None),
            "title": getattr(b, "title", None),
            "severity": getattr(b, "severity", None),
        })
    return result


def _serialize_actions(actions: list, limit: int = 8) -> list[dict]:
    result = []
    for a in actions[:limit]:
        result.append({
            "action_key": getattr(a, "action_key", None),
            "title": getattr(a, "title", None),
            "priority": getattr(a, "priority", None),
        })
    return result


def _serialize_subsystems(subsystems: list) -> list[dict]:
    result = []
    for s in subsystems:
        result.append({
            "subsystem_key": getattr(s, "subsystem_key", None),
            "title": getattr(s, "title", None),
            "status": getattr(s, "status", None),
            "score": getattr(s, "score", None),
            "severity": getattr(s, "severity", None),
            "summary": getattr(s, "summary", None),
        })
    return result


# ---------------------------------------------------------------------------
# Core refresh function
# ---------------------------------------------------------------------------

def refresh_strategy_reliability_snapshot(
    db: Session,
    strategy_id: str,
    force: bool = False,
) -> StrategyReliabilitySnapshot:
    """Build (or reuse) a reliability snapshot for *strategy_id*.

    If *force* is False and an existing snapshot has the same source hash and
    is not stale, the existing snapshot is returned without creating a new one.
    """
    strategy = db.query(Strategy).filter(Strategy.id == uuid.UUID(strategy_id)).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id!r} not found")

    source_hash = _compute_source_hash(db, strategy_id)

    if not force:
        existing = (
            db.query(StrategyReliabilitySnapshot)
            .filter(StrategyReliabilitySnapshot.strategy_id == str(strategy_id))
            .order_by(StrategyReliabilitySnapshot.created_at.desc())
            .first()
        )
        if existing is not None and existing.source_hash == source_hash:
            is_stale, _ = is_snapshot_stale(db, existing)
            if not is_stale:
                return existing

    # --- Call command center ---
    cc_result = None
    snapshot_status = "fresh"

    if get_strategy_reliability_command_center is not None:
        try:
            cc_result = get_strategy_reliability_command_center(db, uuid.UUID(strategy_id))
        except Exception:
            snapshot_status = "error"
    else:
        snapshot_status = "error"

    now = datetime.now(timezone.utc)

    # --- Extract fields from cc_result ---
    command_status = None
    command_score = None
    readiness_verdict = None
    readiness_score = None
    robustness_verdict = None
    robustness_score = None
    freeze_recommendation = None
    freeze_risk_score = None
    freshness_status = None
    freshness_score = None
    drift_status = None
    drift_score = None
    shadow_status = None
    shadow_score = None
    open_review_case_count = 0
    high_critical_alert_count = 0
    latest_regression_status = None
    latest_config_policy_status = None
    latest_sla_status = None
    top_blockers_json: list = []
    action_queue_json: list = []
    subsystem_statuses_json: list = []
    summary_json: dict | None = None
    deterministic_summary = None

    if cc_result is not None:
        command_status = getattr(cc_result, "command_status", None)
        command_score = getattr(cc_result, "command_score", None)
        deterministic_summary = getattr(cc_result, "deterministic_summary", None)

        subsystems = getattr(cc_result, "subsystem_statuses", []) or []
        subsystem_statuses_json = _serialize_subsystems(subsystems)

        # Readiness
        readiness_sub = _find_subsystem(subsystems, "readiness")
        if readiness_sub is not None:
            readiness_score = getattr(readiness_sub, "score", None)
            readiness_verdict = getattr(readiness_sub, "status", None)

        # Robustness
        robustness_sub = _find_subsystem(subsystems, "robustness")
        if robustness_sub is not None:
            robustness_score = getattr(robustness_sub, "score", None)
            robustness_verdict = getattr(robustness_sub, "status", None)

        # Progression freeze — freeze_risk = 100 - score
        freeze_sub = _find_subsystem(subsystems, "progression_freeze")
        if freeze_sub is not None:
            raw_score = getattr(freeze_sub, "score", None)
            freeze_recommendation = getattr(freeze_sub, "status", None)
            freeze_risk_score = (100.0 - raw_score) if raw_score is not None else None

        # Evidence freshness
        freshness_sub = _find_subsystem(subsystems, "evidence_freshness")
        if freshness_sub is not None:
            freshness_score = getattr(freshness_sub, "score", None)
            freshness_status = getattr(freshness_sub, "status", None)

        # Drift
        drift_sub = _find_subsystem(subsystems, "drift")
        if drift_sub is not None:
            drift_score = getattr(drift_sub, "score", None)
            drift_status = getattr(drift_sub, "status", None)

        # Shadow monitor
        shadow_sub = _find_subsystem(subsystems, "shadow_monitor")
        if shadow_sub is not None:
            shadow_score = getattr(shadow_sub, "score", None)
            shadow_status = getattr(shadow_sub, "status", None)

        # Governance summary
        gov = getattr(cc_result, "governance_summary", None)
        if gov is not None:
            open_review_case_count = getattr(gov, "open_review_case_count", 0) or 0
            high_critical_alert_count = getattr(gov, "high_critical_alert_count", 0) or 0
            latest_regression_status = getattr(gov, "latest_regression_status", None)
            latest_config_policy_status = getattr(gov, "latest_policy_status", None)
            latest_sla_status = getattr(gov, "latest_sla_status", None)

        # Top blockers / action queue
        blockers = getattr(cc_result, "top_blockers", []) or []
        top_blockers_json = _serialize_blockers(blockers)

        actions = getattr(cc_result, "action_queue", []) or []
        action_queue_json = _serialize_actions(actions)

        # Summary JSON — assemble from sub-summaries
        try:
            ev = getattr(cc_result, "evidence_summary", None)
            wf = getattr(cc_result, "workflow_summary", None)
            summary_json = {
                "governance": {
                    "open_review_case_count": open_review_case_count,
                    "high_critical_alert_count": high_critical_alert_count,
                    "latest_regression_status": latest_regression_status,
                    "latest_config_policy_status": latest_config_policy_status,
                    "latest_sla_status": latest_sla_status,
                } if gov is not None else None,
                "evidence": {
                    "freshness_status": getattr(ev, "freshness_status", None),
                    "coverage_score": getattr(ev, "coverage_score", None),
                    "missing_evidence_count": getattr(ev, "missing_evidence_count", None),
                    "stale_evidence_count": getattr(ev, "stale_evidence_count", None),
                } if ev is not None else None,
                "workflow": {
                    "current_stage": getattr(wf, "current_stage", None),
                    "next_recommended_stage": getattr(wf, "next_recommended_stage", None),
                    "active_experiment_count": getattr(wf, "active_experiment_count", None),
                } if wf is not None else None,
            }
        except Exception:
            summary_json = None

    # --- Create snapshot ---
    snapshot = StrategyReliabilitySnapshot(
        strategy_id=str(strategy_id),
        snapshot_status=snapshot_status,
        command_status=command_status,
        command_score=command_score,
        readiness_verdict=readiness_verdict,
        readiness_score=readiness_score,
        robustness_verdict=robustness_verdict,
        robustness_score=robustness_score,
        freeze_recommendation=freeze_recommendation,
        freeze_risk_score=freeze_risk_score,
        freshness_status=freshness_status,
        freshness_score=freshness_score,
        drift_status=drift_status,
        drift_score=drift_score,
        shadow_status=shadow_status,
        shadow_score=shadow_score,
        open_review_case_count=open_review_case_count,
        high_critical_alert_count=high_critical_alert_count,
        latest_regression_status=latest_regression_status,
        latest_config_policy_status=latest_config_policy_status,
        latest_sla_status=latest_sla_status,
        top_blockers_json=top_blockers_json,
        action_queue_json=action_queue_json,
        subsystem_statuses_json=subsystem_statuses_json,
        summary_json=summary_json,
        deterministic_summary=deterministic_summary,
        source_hash=source_hash,
        generated_at=now,
        stale_after=now + timedelta(hours=STALE_AFTER_HOURS),
        created_at=now,
    )
    db.add(snapshot)
    db.flush()

    # --- Audit timeline event ---
    try:
        event = AuditTimelineEvent(
            organization_id=strategy.project.organization_id
            if hasattr(strategy, "project") and strategy.project is not None
            else _get_org_id_for_strategy(db, strategy),
            project_id=strategy.project_id,
            strategy_id=strategy.id,
            event_type=EventType.reliability_snapshot_refreshed,
            source_type="reliability_snapshot",
            source_id=str(snapshot.id),
            title="Reliability snapshot refreshed",
            severity="info",
            event_time=now,
            metadata_json={
                "command_status": command_status,
                "command_score": command_score,
                "force": force,
            },
        )
        db.add(event)
        db.flush()
    except Exception:
        pass

    return snapshot


def _get_org_id_for_strategy(db: Session, strategy: Strategy) -> uuid.UUID:
    """Resolve the organisation ID for a strategy via its project."""
    from app.models.project import Project

    project = db.query(Project).filter(Project.id == strategy.project_id).first()
    if project is None:
        raise ValueError("Project not found for strategy")
    return project.organization_id


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_latest_strategy_reliability_snapshot(
    db: Session,
    strategy_id: str,
) -> StrategyReliabilitySnapshot | None:
    """Return the most recently created snapshot for *strategy_id*, or None."""
    return (
        db.query(StrategyReliabilitySnapshot)
        .filter(StrategyReliabilitySnapshot.strategy_id == str(strategy_id))
        .order_by(StrategyReliabilitySnapshot.created_at.desc())
        .first()
    )


def get_strategy_reliability_snapshot_history(
    db: Session,
    strategy_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[StrategyReliabilitySnapshot]:
    """Return snapshots for *strategy_id*, newest first."""
    return (
        db.query(StrategyReliabilitySnapshot)
        .filter(StrategyReliabilitySnapshot.strategy_id == str(strategy_id))
        .order_by(StrategyReliabilitySnapshot.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
