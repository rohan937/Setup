"""Evidence SLA Monitor service (M56).

Deterministic — no AI, no live market data, no external calls.
Evaluates evidence freshness, quality, and coverage against configurable SLA rules.
Creates an AuditTimelineEvent when an evaluation is performed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.evidence_sla import EvidenceSLAPolicy, EvidenceSLAEvaluation, EvidenceSLAResult
from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.signal_snapshot import SignalSnapshot
from app.models.backtest_audit import BacktestAudit
from app.models.alert import Alert
from app.models.audit_timeline_event import AuditTimelineEvent
from app.core.constants import EventType

# Try importing existing services
try:
    from app.services.evidence_freshness import compute_evidence_freshness
except Exception:
    compute_evidence_freshness = None  # type: ignore[assignment]

try:
    from app.services.strategy_readiness import compute_strategy_readiness
except Exception:
    compute_strategy_readiness = None  # type: ignore[assignment]

try:
    from app.services.evidence_coverage import _compute_row
except Exception:
    _compute_row = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Default SLA Rules
# ---------------------------------------------------------------------------

DEFAULT_SLA_RULES: list[dict[str, Any]] = [
    # --- Freshness rules ---
    {
        "rule_key": "strategy_runs_freshness",
        "title": "Strategy runs must be logged within 30 days",
        "evidence_type": "strategy_runs",
        "rule_type": "freshness_max_days",
        "max_days": 30,
        "severity": "medium",
        "is_required": True,
    },
    {
        "rule_key": "dataset_snapshot_freshness",
        "title": "Dataset snapshot must be refreshed within 45 days",
        "evidence_type": "dataset_snapshots",
        "rule_type": "freshness_max_days",
        "max_days": 45,
        "severity": "medium",
        "is_required": True,
    },
    {
        "rule_key": "signal_snapshot_freshness",
        "title": "Signal snapshot must be refreshed within 30 days",
        "evidence_type": "signal_snapshots",
        "rule_type": "freshness_max_days",
        "max_days": 30,
        "severity": "high",
        "is_required": True,
    },
    {
        "rule_key": "universe_snapshot_freshness",
        "title": "Universe snapshot should be refreshed within 90 days",
        "evidence_type": "universe_snapshots",
        "rule_type": "freshness_max_days",
        "max_days": 90,
        "severity": "low",
        "is_required": False,
    },
    {
        "rule_key": "config_snapshot_freshness",
        "title": "Config snapshot should be refreshed within 90 days",
        "evidence_type": "config_snapshots",
        "rule_type": "freshness_max_days",
        "max_days": 90,
        "severity": "low",
        "is_required": False,
    },
    {
        "rule_key": "backtest_audit_freshness",
        "title": "Backtest audit must be refreshed within 45 days",
        "evidence_type": "backtest_audits",
        "rule_type": "freshness_max_days",
        "max_days": 45,
        "severity": "high",
        "is_required": True,
    },
    {
        "rule_key": "reliability_score_freshness",
        "title": "Reliability score must be recomputed within 30 days",
        "evidence_type": "reliability_scores",
        "rule_type": "freshness_max_days",
        "max_days": 30,
        "severity": "medium",
        "is_required": True,
    },
    {
        "rule_key": "report_freshness",
        "title": "Strategy report should be generated within 90 days",
        "evidence_type": "reports",
        "rule_type": "freshness_max_days",
        "max_days": 90,
        "severity": "low",
        "is_required": False,
    },
    # --- Quality / score minimum rules ---
    {
        "rule_key": "dataset_health_minimum",
        "title": "Dataset health must stay above 75",
        "evidence_type": "dataset_snapshots",
        "rule_type": "score_minimum",
        "min_score": 75,
        "severity": "high",
        "is_required": True,
    },
    {
        "rule_key": "signal_quality_minimum",
        "title": "Signal quality must stay above 75",
        "evidence_type": "signal_snapshots",
        "rule_type": "score_minimum",
        "min_score": 75,
        "severity": "high",
        "is_required": True,
    },
    {
        "rule_key": "backtest_trust_minimum",
        "title": "Backtest trust must stay above 70",
        "evidence_type": "backtest_audits",
        "rule_type": "score_minimum",
        "min_score": 70,
        "severity": "high",
        "is_required": True,
    },
    {
        "rule_key": "evidence_coverage_minimum",
        "title": "Evidence coverage must stay above 70",
        "evidence_type": "evidence_coverage",
        "rule_type": "score_minimum",
        "min_score": 70,
        "severity": "medium",
        "is_required": True,
    },
    # --- Status / readiness rules ---
    {
        "rule_key": "readiness_not_blocked",
        "title": "Strategy readiness must not be blocked or under-instrumented",
        "evidence_type": "readiness",
        "rule_type": "status_not_in",
        "blocked_statuses": ["blocked", "under_instrumented"],
        "severity": "high",
        "is_required": True,
    },
    {
        "rule_key": "freshness_not_stale",
        "title": "Overall evidence freshness must not be stale",
        "evidence_type": "freshness",
        "rule_type": "status_not_in",
        "blocked_statuses": ["stale", "missing_evidence"],
        "severity": "medium",
        "is_required": True,
    },
    # --- Alert rule ---
    {
        "rule_key": "no_high_critical_alerts",
        "title": "No high or critical alerts should remain open",
        "evidence_type": "alerts",
        "rule_type": "no_open_high_critical_alerts",
        "severity": "high",
        "is_required": True,
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_latest_freshness_item(freshness_data: Any, evidence_type: str) -> Any | None:
    """Find freshness item matching evidence_type from freshness_data."""
    if freshness_data is None:
        return None
    items = getattr(freshness_data, "evidence_items", None)
    if not items:
        return None
    for item in items:
        et = getattr(item, "evidence_type", None)
        if et == evidence_type:
            return item
    return None


def _eval_sla_rule(
    rule: dict,
    db: Session,
    strategy_id: str,
    freshness_data: Any,
    readiness_data: Any,
    coverage_data: Any,
) -> dict[str, Any]:
    """Evaluate one SLA rule against gathered evidence. Returns a result dict."""
    rule_key = rule["rule_key"]
    title = rule["title"]
    evidence_type = rule.get("evidence_type")
    rule_type = rule.get("rule_type", "freshness_max_days")
    severity = rule.get("severity", "medium")
    is_required = rule.get("is_required", True)
    now = datetime.now(timezone.utc)

    status = "skipped"
    observed_value: str | None = None
    expected_value: str | None = None
    days_since_latest: float | None = None
    latest_at: datetime | None = None
    evidence_json: dict = {}
    suggested_action: str | None = None

    if rule_type == "freshness_max_days":
        max_days = rule.get("max_days", 30)
        expected_value = f"<= {max_days} days"
        item = _get_latest_freshness_item(freshness_data, evidence_type)

        if item is None or getattr(item, "days_since_latest", None) is None:
            if is_required:
                status = "violated"
                suggested_action = f"Log {evidence_type} evidence to meet the {max_days}-day SLA."
            else:
                status = "skipped"
            observed_value = "no evidence"
        else:
            dsl = float(getattr(item, "days_since_latest", 0))
            days_since_latest = dsl
            latest_at = getattr(item, "latest_at", None)
            observed_value = f"{dsl:.0f} days"

            if dsl > max_days:
                status = "violated"
                if is_required:
                    suggested_action = (
                        f"Update {evidence_type} to meet the {max_days}-day SLA. "
                        f"Last update was {dsl:.0f} days ago."
                    )
            elif dsl > max_days * 0.75:
                status = "warning"
                suggested_action = (
                    f"Consider refreshing {evidence_type} soon. "
                    f"Approaching the {max_days}-day SLA threshold ({dsl:.0f} days elapsed)."
                )
            else:
                status = "passed"

    elif rule_type == "score_minimum":
        min_score = rule.get("min_score", 70)
        expected_value = f">= {min_score}"
        score: float | None = None

        try:
            sid = uuid.UUID(str(strategy_id))
            if evidence_type == "dataset_snapshots":
                run = (
                    db.query(StrategyRun)
                    .filter(StrategyRun.strategy_id == sid)
                    .order_by(StrategyRun.created_at.desc())
                    .first()
                )
                if run and run.dataset_snapshot_id:
                    snap = db.query(DatasetSnapshot).filter(
                        DatasetSnapshot.id == run.dataset_snapshot_id
                    ).first()
                    if snap:
                        score = snap.health_score

            elif evidence_type == "signal_snapshots":
                sig = (
                    db.query(SignalSnapshot)
                    .filter(SignalSnapshot.strategy_id == sid)
                    .order_by(SignalSnapshot.created_at.desc())
                    .first()
                )
                if sig:
                    score = sig.quality_score

            elif evidence_type == "backtest_audits":
                run = (
                    db.query(StrategyRun)
                    .filter(
                        StrategyRun.strategy_id == sid,
                        StrategyRun.run_type == "backtest",
                    )
                    .order_by(StrategyRun.created_at.desc())
                    .first()
                )
                if run:
                    audit = (
                        db.query(BacktestAudit)
                        .filter(BacktestAudit.strategy_run_id == run.id)
                        .order_by(BacktestAudit.created_at.desc())
                        .first()
                    )
                    if audit:
                        score = audit.trust_score

            elif evidence_type == "evidence_coverage":
                if coverage_data is not None:
                    score = getattr(coverage_data, "evidence_coverage_score", None)

        except Exception:
            score = None

        if score is None:
            if is_required:
                status = "violated"
                suggested_action = f"Ensure {evidence_type} evidence is available and scored above {min_score}."
            else:
                status = "skipped"
            observed_value = "no data"
        else:
            observed_value = f"{score:.1f}"
            if score < min_score:
                status = "violated"
                if is_required:
                    suggested_action = (
                        f"Improve {evidence_type} score to meet the minimum of {min_score}. "
                        f"Current score: {score:.1f}."
                    )
            elif score < min_score * 1.1:
                status = "warning"
                suggested_action = (
                    f"Monitor {evidence_type} score closely. "
                    f"Current {score:.1f} is approaching minimum threshold of {min_score}."
                )
            else:
                status = "passed"

    elif rule_type == "status_not_in":
        blocked_statuses = rule.get("blocked_statuses", [])
        expected_value = f"not in {blocked_statuses}"
        current_status: str | None = None

        if evidence_type == "readiness":
            if readiness_data is not None:
                if isinstance(readiness_data, dict):
                    current_status = readiness_data.get("readiness_verdict")
                else:
                    current_status = getattr(readiness_data, "readiness_verdict", None)

        elif evidence_type == "freshness":
            if freshness_data is not None:
                if isinstance(freshness_data, dict):
                    current_status = freshness_data.get("freshness_status")
                else:
                    current_status = getattr(freshness_data, "freshness_status", None)

        if current_status is None:
            status = "skipped"
            observed_value = "no data"
        elif current_status in blocked_statuses:
            status = "violated"
            observed_value = current_status
            if is_required:
                suggested_action = (
                    f"Resolve {evidence_type} status '{current_status}' before progressing. "
                    f"Status must not be in: {blocked_statuses}."
                )
        else:
            status = "passed"
            observed_value = current_status

    elif rule_type == "no_open_high_critical_alerts":
        expected_value = "0"
        try:
            count = (
                db.query(Alert)
                .filter(
                    Alert.strategy_id == str(strategy_id),
                    Alert.status == "open",
                    Alert.severity.in_(["high", "critical"]),
                )
                .count()
            )
            observed_value = f"{count} open"
            if count > 0:
                status = "violated"
                if is_required:
                    suggested_action = (
                        f"Review and resolve {count} open high or critical alert(s) for this strategy."
                    )
            else:
                status = "passed"
                observed_value = "0 open"
        except Exception:
            status = "skipped"
            observed_value = "query error"

    elif rule_type == "latest_evidence_required":
        item = _get_latest_freshness_item(freshness_data, evidence_type)
        count = getattr(item, "count", 0) if item else 0
        if count == 0:
            status = "violated"
            observed_value = "0"
            if is_required:
                suggested_action = f"Log at least one {evidence_type} entry."
        else:
            status = "passed"
            observed_value = str(count)
        expected_value = ">= 1"

    return {
        "rule_key": rule_key,
        "title": title,
        "evidence_type": evidence_type,
        "status": status,
        "severity": severity,
        "is_required": is_required,
        "observed_value": observed_value,
        "expected_value": expected_value,
        "days_since_latest": days_since_latest,
        "latest_at": latest_at,
        "evidence_json": evidence_json,
        "suggested_action": suggested_action,
        "created_at": now,
    }


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

def create_default_evidence_sla_policy(db: Session, strategy_id: str) -> EvidenceSLAPolicy:
    """Create (or return existing) the default QuantFidelity Evidence SLA policy."""
    default_name = "QuantFidelity Default Evidence SLA"

    existing = (
        db.query(EvidenceSLAPolicy)
        .filter(
            EvidenceSLAPolicy.strategy_id == uuid.UUID(strategy_id),
            EvidenceSLAPolicy.name == default_name,
        )
        .first()
    )
    if existing:
        return existing

    policy = EvidenceSLAPolicy(
        strategy_id=uuid.UUID(strategy_id),
        name=default_name,
        description=(
            "Default set of evidence SLA rules for QuantFidelity strategies. "
            "Checks freshness, quality scores, readiness, and open alerts."
        ),
        is_active=True,
        policy_json={"rules": DEFAULT_SLA_RULES},
    )
    db.add(policy)
    db.flush()
    return policy


def create_evidence_sla_policy(db: Session, strategy_id: str, payload: dict) -> EvidenceSLAPolicy:
    """Create a new custom SLA policy for a strategy."""
    policy = EvidenceSLAPolicy(
        strategy_id=uuid.UUID(strategy_id),
        name=payload["name"],
        description=payload.get("description"),
        is_active=payload.get("is_active", True),
        policy_json=payload["policy_json"],
    )
    db.add(policy)
    db.flush()
    return policy


def get_evidence_sla_policies(db: Session, strategy_id: str) -> list[EvidenceSLAPolicy]:
    """Return all policies for a strategy, newest first."""
    return (
        db.query(EvidenceSLAPolicy)
        .filter(EvidenceSLAPolicy.strategy_id == uuid.UUID(strategy_id))
        .order_by(EvidenceSLAPolicy.created_at.desc())
        .all()
    )


def evaluate_evidence_sla_policy(
    db: Session,
    strategy_id: str,
    policy_id: str,
) -> EvidenceSLAEvaluation:
    """Evaluate an SLA policy for a strategy.

    Persists evaluation + per-rule results + AuditTimelineEvent.
    """
    now = datetime.now(timezone.utc)

    # Load policy
    policy = (
        db.query(EvidenceSLAPolicy)
        .filter(
            EvidenceSLAPolicy.id == uuid.UUID(policy_id),
            EvidenceSLAPolicy.strategy_id == uuid.UUID(strategy_id),
        )
        .first()
    )
    if not policy:
        # Return an insufficient_evidence evaluation
        strategy = db.query(Strategy).filter(Strategy.id == uuid.UUID(strategy_id)).first()
        evaluation = EvidenceSLAEvaluation(
            strategy_id=uuid.UUID(strategy_id),
            policy_id=uuid.UUID(policy_id),
            overall_status="insufficient_evidence",
            passed_count=0,
            warning_count=0,
            violated_count=0,
            skipped_count=0,
            critical_violation_count=0,
            result_json=None,
            deterministic_summary="Policy not found for strategy.",
            created_at=now,
        )
        db.add(evaluation)
        db.flush()
        if strategy:
            _create_sla_timeline_event(db=db, strategy=strategy, evaluation=evaluation, now=now)
        return evaluation

    # Load strategy (for timeline event)
    strategy = db.query(Strategy).filter(Strategy.id == uuid.UUID(strategy_id)).first()

    # Gather evidence data
    freshness_data = None
    readiness_data = None
    coverage_data = None

    if compute_evidence_freshness is not None:
        try:
            freshness_data = compute_evidence_freshness(uuid.UUID(strategy_id), db)
        except Exception:
            freshness_data = None

    if compute_strategy_readiness is not None:
        try:
            readiness_data = compute_strategy_readiness(uuid.UUID(strategy_id), db)
        except Exception:
            readiness_data = None

    if _compute_row is not None and strategy is not None:
        try:
            coverage_data = _compute_row(strategy, db)
        except Exception:
            coverage_data = None

    # Evaluate rules
    rules = policy.policy_json.get("rules", []) if policy.policy_json else []

    if not rules:
        evaluation = EvidenceSLAEvaluation(
            strategy_id=uuid.UUID(strategy_id),
            policy_id=policy.id,
            overall_status="insufficient_evidence",
            passed_count=0,
            warning_count=0,
            violated_count=0,
            skipped_count=0,
            critical_violation_count=0,
            result_json=[],
            deterministic_summary="Insufficient evidence: no rules defined in policy.",
            created_at=now,
        )
        db.add(evaluation)
        db.flush()
        if strategy:
            _create_sla_timeline_event(db=db, strategy=strategy, evaluation=evaluation, now=now)
        return evaluation

    rule_results: list[dict[str, Any]] = []
    for rule in rules:
        result = _eval_sla_rule(rule, db, strategy_id, freshness_data, readiness_data, coverage_data)
        rule_results.append(result)

    # Compute counts
    passed_count = sum(1 for r in rule_results if r["status"] == "passed")
    warning_count = sum(1 for r in rule_results if r["status"] == "warning")
    violated_count = sum(1 for r in rule_results if r["status"] == "violated")
    skipped_count = sum(1 for r in rule_results if r["status"] == "skipped")
    critical_violation_count = sum(
        1 for r in rule_results
        if r["status"] == "violated" and r["severity"] in ("high", "critical")
    )

    # Compute overall_status
    non_skipped = [r for r in rule_results if r["status"] != "skipped"]
    if not non_skipped:
        overall_status = "insufficient_evidence"
    elif any(r["status"] == "violated" and r["is_required"] for r in rule_results):
        overall_status = "violated"
    elif any(r["status"] in ("violated", "warning") for r in rule_results):
        overall_status = "warning"
    else:
        overall_status = "passed"

    # Build deterministic summary
    violated_titles = [r["title"] for r in rule_results if r["status"] == "violated"]
    summary_parts = [
        f"SLA evaluation: {passed_count} passed, {violated_count} violated, {warning_count} warnings."
    ]
    if violated_titles:
        joined = " ".join(f"{t}." for t in violated_titles[:3])
        summary_parts.append(joined)
    deterministic_summary = " ".join(summary_parts)

    # Persist evaluation
    evaluation = EvidenceSLAEvaluation(
        strategy_id=uuid.UUID(strategy_id),
        policy_id=policy.id,
        overall_status=overall_status,
        passed_count=passed_count,
        warning_count=warning_count,
        violated_count=violated_count,
        skipped_count=skipped_count,
        critical_violation_count=critical_violation_count,
        result_json=[
            {k: str(v) if isinstance(v, (datetime, uuid.UUID)) else v
             for k, v in r.items() if k != "created_at"}
            for r in rule_results
        ],
        deterministic_summary=deterministic_summary,
        created_at=now,
    )
    db.add(evaluation)
    db.flush()

    # Persist per-rule results
    for r in rule_results:
        result_row = EvidenceSLAResult(
            evaluation_id=evaluation.id,
            rule_key=r["rule_key"],
            title=r["title"],
            evidence_type=r.get("evidence_type"),
            status=r["status"],
            severity=r["severity"],
            is_required=r["is_required"],
            observed_value=r.get("observed_value"),
            expected_value=r.get("expected_value"),
            days_since_latest=r.get("days_since_latest"),
            latest_at=r.get("latest_at"),
            evidence_json=r.get("evidence_json"),
            suggested_action=r.get("suggested_action"),
            created_at=r.get("created_at", now),
        )
        db.add(result_row)
    db.flush()

    # AuditTimelineEvent
    if strategy:
        _create_sla_timeline_event(db=db, strategy=strategy, evaluation=evaluation, now=now)

    return evaluation


def _create_sla_timeline_event(
    db: Session,
    strategy: Any,
    evaluation: EvidenceSLAEvaluation,
    now: datetime,
) -> None:
    """Persist an AuditTimelineEvent for an SLA evaluation."""
    from app.core.constants import Severity

    if evaluation.overall_status == "passed":
        sev = Severity.info
    elif evaluation.overall_status == "warning":
        sev = Severity.medium
    elif evaluation.overall_status == "violated":
        sev = Severity.high
    else:
        sev = Severity.info

    event = AuditTimelineEvent(
        organization_id=strategy.project.organization_id,
        project_id=strategy.project_id,
        strategy_id=strategy.id,
        event_type=EventType.evidence_sla_evaluated,
        title="Evidence SLA evaluated",
        description=evaluation.deterministic_summary,
        source_type="evidence_sla",
        source_id=str(evaluation.id),
        severity=sev,
        event_time=now,
        metadata_json={
            "overall_status": evaluation.overall_status,
            "violated_count": evaluation.violated_count,
            "policy_id": str(evaluation.policy_id),
        },
    )
    db.add(event)
    db.flush()


def get_evidence_sla_evaluations(
    db: Session,
    strategy_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[EvidenceSLAEvaluation]:
    """Return evaluations for a strategy, newest first."""
    return (
        db.query(EvidenceSLAEvaluation)
        .filter(EvidenceSLAEvaluation.strategy_id == uuid.UUID(strategy_id))
        .order_by(EvidenceSLAEvaluation.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_evidence_sla_evaluation(
    db: Session,
    evaluation_id: str,
) -> EvidenceSLAEvaluation | None:
    """Return a single evaluation with its results eagerly loaded."""
    from sqlalchemy.orm import joinedload

    return (
        db.query(EvidenceSLAEvaluation)
        .options(joinedload(EvidenceSLAEvaluation.results))
        .filter(EvidenceSLAEvaluation.id == uuid.UUID(evaluation_id))
        .first()
    )
