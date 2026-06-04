"""M55 Research Review Cases service.

Deterministic case generation — no AI calls.  Reads evidence from previously
persisted data (readiness, freshness, drift, shadow, gates, assumptions,
regression runs, policy evaluations, backtest audits, alerts) and surfaces
structured review cases that warrant human attention.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.review_case import ResearchReviewCase, ResearchReviewCaseEvent
from app.models.strategy import Strategy
from app.models.alert import Alert
from app.models.regression import StrategyRegressionTestRun
from app.models.config_policy import StrategyConfigPolicyEvaluation
from app.models.backtest_audit import BacktestAudit
from app.models.strategy_run import StrategyRun


# ---------------------------------------------------------------------------
# Service imports (wrapped to tolerate partial install)
# ---------------------------------------------------------------------------

try:
    from app.services.strategy_readiness import compute_strategy_readiness
except ImportError:
    compute_strategy_readiness = None  # type: ignore[assignment]

try:
    from app.services.evidence_freshness import compute_evidence_freshness
except ImportError:
    compute_evidence_freshness = None  # type: ignore[assignment]

try:
    from app.services.strategy_drift import compute_strategy_drift
except ImportError:
    compute_strategy_drift = None  # type: ignore[assignment]

try:
    from app.services.shadow_production import compute_shadow_production_monitor
except ImportError:
    compute_shadow_production_monitor = None  # type: ignore[assignment]

try:
    from app.services.promotion_gates import evaluate_promotion_gates
except ImportError:
    evaluate_promotion_gates = None  # type: ignore[assignment]

try:
    from app.services.assumption_health import compute_assumption_health
except ImportError:
    compute_assumption_health = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Evidence gathering
# ---------------------------------------------------------------------------

def _to_uuid(strategy_id: str | uuid.UUID) -> uuid.UUID:
    """Convert a strategy_id to a UUID object if not already one."""
    if isinstance(strategy_id, uuid.UUID):
        return strategy_id
    return uuid.UUID(str(strategy_id))


def _strategy_id_forms(strategy_id: str | uuid.UUID) -> list[str]:
    """Both stored forms of a strategy id (36-char str and 32-char hex)."""
    try:
        u = _to_uuid(strategy_id)
        return [str(u), u.hex]
    except Exception:
        return [str(strategy_id)]


def _gather_evidence(db: Session, strategy_id: str) -> dict[str, Any]:
    """Collect all evidence needed for case generation."""
    evidence: dict[str, Any] = {}
    sid_uuid = _to_uuid(strategy_id)

    if compute_strategy_readiness is not None:
        try:
            evidence["readiness"] = compute_strategy_readiness(db, strategy_id)
        except Exception:
            evidence["readiness"] = None
    else:
        evidence["readiness"] = None

    if compute_evidence_freshness is not None:
        try:
            evidence["freshness"] = compute_evidence_freshness(db, strategy_id)
        except Exception:
            evidence["freshness"] = None
    else:
        evidence["freshness"] = None

    if compute_strategy_drift is not None:
        try:
            evidence["drift"] = compute_strategy_drift(db, strategy_id)
        except Exception:
            evidence["drift"] = None
    else:
        evidence["drift"] = None

    if compute_shadow_production_monitor is not None:
        try:
            evidence["shadow"] = compute_shadow_production_monitor(db, strategy_id)
        except Exception:
            evidence["shadow"] = None
    else:
        evidence["shadow"] = None

    if evaluate_promotion_gates is not None:
        try:
            evidence["gates_paper"] = evaluate_promotion_gates(
                db, strategy_id, "paper_candidate"
            )
        except Exception:
            evidence["gates_paper"] = None
    else:
        evidence["gates_paper"] = None

    if compute_assumption_health is not None:
        try:
            evidence["assumption"] = compute_assumption_health(db, strategy_id)
        except Exception:
            evidence["assumption"] = None
    else:
        evidence["assumption"] = None

    # Latest regression run
    try:
        evidence["latest_regression_run"] = (
            db.query(StrategyRegressionTestRun)
            .filter(StrategyRegressionTestRun.strategy_id == sid_uuid)
            .order_by(StrategyRegressionTestRun.created_at.desc())
            .first()
        )
    except Exception:
        evidence["latest_regression_run"] = None

    # Latest policy evaluation
    try:
        evidence["latest_policy_eval"] = (
            db.query(StrategyConfigPolicyEvaluation)
            .filter(StrategyConfigPolicyEvaluation.strategy_id == sid_uuid)
            .order_by(StrategyConfigPolicyEvaluation.created_at.desc())
            .first()
        )
    except Exception:
        evidence["latest_policy_eval"] = None

    # Latest backtest audit (via join to strategy_runs)
    try:
        evidence["latest_backtest_audit"] = (
            db.query(BacktestAudit)
            .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
            .filter(StrategyRun.strategy_id == sid_uuid)
            .order_by(BacktestAudit.created_at.desc())
            .first()
        )
    except Exception:
        evidence["latest_backtest_audit"] = None

    # Open alerts for strategy
    try:
        open_alerts = (
            db.query(Alert)
            .filter(
                and_(
                    Alert.strategy_id == str(strategy_id),
                    Alert.status == "open",
                )
            )
            .all()
        )
        evidence["open_alerts"] = open_alerts
        evidence["high_critical_alert_count"] = sum(
            1 for a in open_alerts if a.severity in ("high", "critical")
        )
    except Exception:
        evidence["open_alerts"] = []
        evidence["high_critical_alert_count"] = 0

    return evidence


# ---------------------------------------------------------------------------
# Upsert helper
# ---------------------------------------------------------------------------

def _upsert_case(
    db: Session,
    strategy_id: str,
    case_key: str,
    case_data: dict,
) -> tuple[ResearchReviewCase, bool]:
    """Find existing open/acknowledged case or create a new one.

    Returns (case, is_new).
    """
    now = datetime.now(timezone.utc)

    existing = (
        db.query(ResearchReviewCase)
        .filter(
            and_(
                ResearchReviewCase.strategy_id == str(strategy_id),
                ResearchReviewCase.case_key == case_key,
                ResearchReviewCase.status.in_(["open", "acknowledged"]),
            )
        )
        .first()
    )

    if existing is not None:
        # Refresh evidence and metadata
        existing.evidence_json = case_data.get("evidence_json")
        existing.suggested_actions_json = case_data.get("suggested_actions_json")
        existing.updated_at = now
        existing.linked_alert_ids_json = case_data.get("linked_alert_ids_json")
        existing.linked_regression_run_ids_json = case_data.get(
            "linked_regression_run_ids_json"
        )
        existing.linked_policy_evaluation_ids_json = case_data.get(
            "linked_policy_evaluation_ids_json"
        )
        existing.linked_backtest_audit_ids_json = case_data.get(
            "linked_backtest_audit_ids_json"
        )
        existing.linked_run_ids_json = case_data.get("linked_run_ids_json")
        existing.linked_snapshot_ids_json = case_data.get("linked_snapshot_ids_json")

        event = ResearchReviewCaseEvent(
            case_id=existing.id,
            event_type="refreshed",
            title="Review case refreshed",
            created_at=now,
        )
        db.add(event)
        db.flush()
        return existing, False

    # Create new case
    case = ResearchReviewCase(
        strategy_id=str(strategy_id),
        case_key=case_key,
        title=case_data["title"],
        status="open",
        severity=case_data["severity"],
        category=case_data["category"],
        summary=case_data.get("summary"),
        deterministic_summary=case_data.get("deterministic_summary"),
        evidence_json=case_data.get("evidence_json"),
        suggested_actions_json=case_data.get("suggested_actions_json"),
        linked_alert_ids_json=case_data.get("linked_alert_ids_json"),
        linked_regression_run_ids_json=case_data.get("linked_regression_run_ids_json"),
        linked_policy_evaluation_ids_json=case_data.get(
            "linked_policy_evaluation_ids_json"
        ),
        linked_backtest_audit_ids_json=case_data.get("linked_backtest_audit_ids_json"),
        linked_run_ids_json=case_data.get("linked_run_ids_json"),
        linked_snapshot_ids_json=case_data.get("linked_snapshot_ids_json"),
        opened_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(case)
    db.flush()

    event = ResearchReviewCaseEvent(
        case_id=case.id,
        event_type="opened",
        title="Review case opened",
        created_at=now,
    )
    db.add(event)
    db.flush()
    return case, True


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------

_MAX_CASES = 7

_FORBIDDEN_TERMS = [
    "incident",
    "breach",
    "strategy failed",
    "do not trade",
]


def _safe_summary(text: str) -> str:
    """Ensure summary text does not contain forbidden language."""
    lowered = text.lower()
    for term in _FORBIDDEN_TERMS:
        if term in lowered:
            text = text.replace(term, "[flagged]")
    return text


def generate_research_review_cases(
    db: Session, strategy_id: str
) -> list[ResearchReviewCase]:
    """Generate (or refresh) research review cases for a strategy.

    Returns the list of cases created or refreshed in this run.
    """
    strategy = db.query(Strategy).filter(Strategy.id == _to_uuid(strategy_id)).first()
    if strategy is None:
        return []

    # Ensure project relationship is loaded for organization_id
    _ = strategy.project

    evidence = _gather_evidence(db, strategy_id)

    generated_cases: list[ResearchReviewCase] = []
    new_count = 0
    refresh_count = 0

    # -----------------------------------------------------------------------
    # A. RELIABILITY
    # -----------------------------------------------------------------------
    readiness_verdict = getattr(
        evidence.get("readiness"), "readiness_verdict", None
    )
    backtest_audit = evidence.get("latest_backtest_audit")
    backtest_trust = getattr(backtest_audit, "trust_score", None) if backtest_audit else None

    reliability_trigger = (
        readiness_verdict in (
            "blocked", "requires_review_before_progression", "under_instrumented"
        )
        or (backtest_trust is not None and backtest_trust < 60)
    )

    if reliability_trigger and len(generated_cases) < _MAX_CASES:
        if readiness_verdict == "blocked":
            severity = "critical"
        elif (backtest_trust is not None and backtest_trust < 60) or readiness_verdict in (
            "requires_review_before_progression",
        ):
            severity = "high"
        else:
            severity = "medium"

        parts = []
        if readiness_verdict in ("blocked", "requires_review_before_progression", "under_instrumented"):
            parts.append(f"readiness verdict is '{readiness_verdict}'")
        if backtest_trust is not None and backtest_trust < 60:
            parts.append(f"backtest trust score is {backtest_trust}/100")

        summary = _safe_summary(
            "Strategy reliability requires attention. "
            + ("; ".join(parts) if parts else "Issues were detected in reliability evidence.")
            + "."
        )

        linked_audit_ids = (
            [str(backtest_audit.id)] if backtest_audit else None
        )

        case_data = {
            "title": "Strategy Reliability Review",
            "severity": severity,
            "category": "reliability",
            "summary": summary,
            "deterministic_summary": summary,
            "evidence_json": {
                "readiness_verdict": readiness_verdict,
                "backtest_trust_score": backtest_trust,
            },
            "suggested_actions_json": [
                "Review backtest audit findings and address flagged issues.",
                "Ensure sufficient run evidence is recorded before progression.",
                "Check reliability score history for deterioration trends.",
            ],
            "linked_backtest_audit_ids_json": linked_audit_ids,
        }
        case, is_new = _upsert_case(db, strategy_id, "reliability_review", case_data)
        generated_cases.append(case)
        if is_new:
            new_count += 1
        else:
            refresh_count += 1

    # -----------------------------------------------------------------------
    # B. EVIDENCE QUALITY
    # -----------------------------------------------------------------------
    high_critical_count = evidence.get("high_critical_alert_count", 0)
    open_alerts = evidence.get("open_alerts", [])
    critical_alerts = [a for a in open_alerts if a.severity == "critical"]

    evidence_quality_trigger = high_critical_count > 0

    if evidence_quality_trigger and len(generated_cases) < _MAX_CASES:
        severity = "high" if critical_alerts else "medium"

        summary = _safe_summary(
            f"There are {high_critical_count} high or critical severity alert(s) open for this strategy. "
            "Evidence quality requires review."
        )
        linked_alert_ids = [str(a.id) for a in open_alerts if a.severity in ("high", "critical")]

        case_data = {
            "title": "Evidence Quality Review",
            "severity": severity,
            "category": "evidence_quality",
            "summary": summary,
            "deterministic_summary": summary,
            "evidence_json": {
                "high_critical_alert_count": high_critical_count,
                "open_alert_count": len(open_alerts),
            },
            "suggested_actions_json": [
                "Review and address open high/critical severity alerts.",
                "Verify that data sources are current and complete.",
                "Re-run evidence ingestion after resolving alerts.",
            ],
            "linked_alert_ids_json": linked_alert_ids or None,
        }
        case, is_new = _upsert_case(db, strategy_id, "evidence_quality", case_data)
        generated_cases.append(case)
        if is_new:
            new_count += 1
        else:
            refresh_count += 1

    # -----------------------------------------------------------------------
    # C. FRESHNESS
    # -----------------------------------------------------------------------
    freshness_obj = evidence.get("freshness")
    freshness_status = getattr(freshness_obj, "freshness_status", None)
    stale_count = getattr(freshness_obj, "stale_count", 0) or 0
    missing_count = getattr(freshness_obj, "missing_count", 0) or 0

    freshness_trigger = (
        freshness_status in ("stale", "missing_evidence")
        and (stale_count + missing_count) >= 2
    )

    if freshness_trigger and len(generated_cases) < _MAX_CASES:
        severity = "high" if freshness_status == "missing_evidence" else "medium"

        summary = _safe_summary(
            f"Evidence freshness check indicates {stale_count} stale and "
            f"{missing_count} missing evidence item(s). "
            "Freshness status: " + str(freshness_status) + "."
        )

        case_data = {
            "title": "Evidence Freshness Review",
            "severity": severity,
            "category": "freshness",
            "summary": summary,
            "deterministic_summary": summary,
            "evidence_json": {
                "freshness_status": freshness_status,
                "stale_count": stale_count,
                "missing_count": missing_count,
            },
            "suggested_actions_json": [
                "Re-run evidence ingestion to refresh stale evidence.",
                "Check that all required evidence types have been uploaded.",
                "Verify data pipelines are running on schedule.",
            ],
        }
        case, is_new = _upsert_case(db, strategy_id, "freshness_review", case_data)
        generated_cases.append(case)
        if is_new:
            new_count += 1
        else:
            refresh_count += 1

    # -----------------------------------------------------------------------
    # D. ASSUMPTIONS
    # -----------------------------------------------------------------------
    assumption = evidence.get("assumption")
    assumption_status = assumption.get("status") if isinstance(assumption, dict) else None
    policy_eval = evidence.get("latest_policy_eval")
    policy_status = getattr(policy_eval, "overall_status", None)

    assumption_trigger = (
        assumption_status in ("weak", "review")
        or policy_status == "failed"
    )

    if assumption_trigger and len(generated_cases) < _MAX_CASES:
        if assumption_status == "weak" or (
            policy_eval and getattr(policy_eval, "critical_failed_count", 0) > 0
        ):
            severity = "high"
        else:
            severity = "medium"

        parts = []
        if assumption_status in ("weak", "review"):
            parts.append(f"assumption health status is '{assumption_status}'")
        if policy_status == "failed":
            failed = getattr(policy_eval, "failed_count", 0)
            parts.append(f"config policy evaluation has {failed} failed rule(s)")

        summary = _safe_summary(
            "Assumption guardrails require review. "
            + ("; ".join(parts) if parts else "Issues detected in assumption or config policy checks.")
            + "."
        )

        linked_policy_ids = [str(policy_eval.id)] if policy_eval else None

        case_data = {
            "title": "Assumption Guardrails Review",
            "severity": severity,
            "category": "assumptions",
            "summary": summary,
            "deterministic_summary": summary,
            "evidence_json": {
                "assumption_status": assumption_status,
                "policy_overall_status": policy_status,
                "policy_failed_count": getattr(policy_eval, "failed_count", None),
            },
            "suggested_actions_json": [
                "Review config policy evaluation results and resolve failed rules.",
                "Verify that strategy assumptions are documented and current.",
                "Re-evaluate the config policy after remediation.",
            ],
            "linked_policy_evaluation_ids_json": linked_policy_ids,
        }
        case, is_new = _upsert_case(db, strategy_id, "assumption_review", case_data)
        generated_cases.append(case)
        if is_new:
            new_count += 1
        else:
            refresh_count += 1

    # -----------------------------------------------------------------------
    # E. REGRESSION
    # -----------------------------------------------------------------------
    reg_run = evidence.get("latest_regression_run")
    reg_status = getattr(reg_run, "overall_status", None)
    req_failed = getattr(reg_run, "required_failed_count", 0) or 0
    failed = getattr(reg_run, "failed_count", 0) or 0

    regression_trigger = (
        reg_run is not None
        and reg_status in ("failed", "warning")
        and (req_failed > 0 or failed > 0)
    )

    if regression_trigger and len(generated_cases) < _MAX_CASES:
        severity = "high" if req_failed > 0 else "medium"

        summary = _safe_summary(
            f"Latest regression test run has status '{reg_status}' with "
            f"{req_failed} required failure(s) and {failed} total failure(s)."
        )

        case_data = {
            "title": "Regression Test Review",
            "severity": severity,
            "category": "regression",
            "summary": summary,
            "deterministic_summary": summary,
            "evidence_json": {
                "regression_run_status": reg_status,
                "required_failed_count": req_failed,
                "failed_count": failed,
                "passed_count": getattr(reg_run, "passed_count", None),
            },
            "suggested_actions_json": [
                "Investigate regression test failures and determine root cause.",
                "Fix underlying issues or update test expectations if appropriate.",
                "Re-run the regression test suite after remediation.",
            ],
            "linked_regression_run_ids_json": [str(reg_run.id)],
        }
        case, is_new = _upsert_case(db, strategy_id, "regression_failure", case_data)
        generated_cases.append(case)
        if is_new:
            new_count += 1
        else:
            refresh_count += 1

    # -----------------------------------------------------------------------
    # F. PROMOTION GATES
    # -----------------------------------------------------------------------
    gates_paper = evidence.get("gates_paper")
    promotion_verdict = getattr(gates_paper, "promotion_verdict", None)

    promotion_trigger = promotion_verdict in (
        "blocked", "requires_review", "insufficient_evidence"
    )

    if promotion_trigger and len(generated_cases) < _MAX_CASES:
        severity = "high" if promotion_verdict == "blocked" else "medium"

        summary = _safe_summary(
            f"Promotion gate evaluation returned verdict: '{promotion_verdict}'. "
            "This strategy is not currently ready for promotion to the next stage."
        )

        case_data = {
            "title": "Promotion Gate Review",
            "severity": severity,
            "category": "promotion",
            "summary": summary,
            "deterministic_summary": summary,
            "evidence_json": {
                "promotion_verdict": promotion_verdict,
            },
            "suggested_actions_json": [
                "Review promotion gate criteria and identify blocking factors.",
                "Gather additional evidence to satisfy gate requirements.",
                "Re-evaluate promotion gates after addressing gaps.",
            ],
        }
        case, is_new = _upsert_case(db, strategy_id, "promotion_blocked", case_data)
        generated_cases.append(case)
        if is_new:
            new_count += 1
        else:
            refresh_count += 1

    # -----------------------------------------------------------------------
    # G. SHADOW PRODUCTION
    # -----------------------------------------------------------------------
    shadow = evidence.get("shadow")
    monitor_status = getattr(shadow, "monitor_status", None)

    shadow_trigger = monitor_status in ("review", "severe")

    if shadow_trigger and len(generated_cases) < _MAX_CASES:
        severity = "critical" if monitor_status == "severe" else "medium"

        summary = _safe_summary(
            f"Shadow production monitor status is '{monitor_status}'. "
            "Review shadow run performance before live deployment."
        )

        case_data = {
            "title": "Shadow Production Review",
            "severity": severity,
            "category": "shadow",
            "summary": summary,
            "deterministic_summary": summary,
            "evidence_json": {
                "monitor_status": monitor_status,
            },
            "suggested_actions_json": [
                "Review shadow run results and identify performance discrepancies.",
                "Compare shadow vs. backtest metrics for consistency.",
                "Address monitor findings before progressing to live trading.",
            ],
        }
        case, is_new = _upsert_case(db, strategy_id, "shadow_review", case_data)
        generated_cases.append(case)
        if is_new:
            new_count += 1
        else:
            refresh_count += 1

    # -----------------------------------------------------------------------
    # AuditTimelineEvent
    # -----------------------------------------------------------------------
    if generated_cases:
        from app.models.audit_timeline_event import AuditTimelineEvent
        from app.core.constants import EventType

        now = datetime.now(timezone.utc)
        has_high_critical = any(
            c.severity in ("high", "critical") for c in generated_cases
        )

        event = AuditTimelineEvent(
            organization_id=strategy.project.organization_id,
            project_id=strategy.project_id,
            strategy_id=strategy.id,
            event_type=EventType.research_review_cases_generated,
            source_type="review_case",
            source_id=str(strategy.id),
            severity="warning" if has_high_critical else "info",
            title="Research review cases generated",
            description=f"{len(generated_cases)} review case(s) generated for strategy.",
            metadata_json={
                "strategy_id": str(strategy_id),
                "generated_count": new_count,
                "refreshed_count": refresh_count,
            },
            event_time=now,
        )
        db.add(event)
        db.flush()

    return generated_cases


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_research_review_cases(
    db: Session,
    strategy_id: str,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ResearchReviewCase]:
    """Return review cases for a strategy, optionally filtered by status."""
    # strategy_id may be stored as the 36-char str or the 32-char hex form
    # (SQLAlchemy 2.0 SQLite stores UUID PKs as hex). Match both defensively.
    q = db.query(ResearchReviewCase).filter(
        ResearchReviewCase.strategy_id.in_(_strategy_id_forms(strategy_id))
    )
    if status is not None:
        q = q.filter(ResearchReviewCase.status == status)
    q = q.order_by(ResearchReviewCase.opened_at.desc())
    return q.offset(offset).limit(limit).all()


def get_research_review_case(
    db: Session, case_id: str
) -> ResearchReviewCase | None:
    """Return a single review case by ID, eager-loading events."""
    from sqlalchemy.orm import joinedload

    try:
        case_uuid = _to_uuid(case_id)
    except Exception:
        return None

    return (
        db.query(ResearchReviewCase)
        .options(joinedload(ResearchReviewCase.events))
        .filter(ResearchReviewCase.id == case_uuid)
        .first()
    )


# ---------------------------------------------------------------------------
# Workflow transitions
# ---------------------------------------------------------------------------

def acknowledge_research_review_case(
    db: Session, case_id: str
) -> ResearchReviewCase | None:
    """Acknowledge an open review case."""
    try:
        case_uuid = _to_uuid(case_id)
    except Exception:
        return None
    case = (
        db.query(ResearchReviewCase)
        .filter(ResearchReviewCase.id == case_uuid)
        .first()
    )
    if case is None or case.status != "open":
        return None

    now = datetime.now(timezone.utc)
    case.status = "acknowledged"
    case.acknowledged_at = now
    case.updated_at = now

    event = ResearchReviewCaseEvent(
        case_id=case.id,
        event_type="acknowledged",
        title="Review case acknowledged",
        created_at=now,
    )
    db.add(event)

    from app.models.audit_timeline_event import AuditTimelineEvent
    from app.core.constants import EventType

    strategy = db.query(Strategy).filter(
        Strategy.id == _to_uuid(case.strategy_id)
    ).first()
    if strategy is not None:
        _ = strategy.project
        audit_event = AuditTimelineEvent(
            organization_id=strategy.project.organization_id,
            project_id=strategy.project_id,
            strategy_id=strategy.id,
            event_type=EventType.research_review_case_acknowledged,
            source_type="review_case",
            source_id=str(case.id),
            severity="info",
            title="Review case acknowledged",
            description=f"Review case '{case.title}' was acknowledged.",
            metadata_json={"case_id": str(case.id), "case_key": case.case_key},
            event_time=now,
        )
        db.add(audit_event)

    db.flush()
    return case


def resolve_research_review_case(
    db: Session, case_id: str
) -> ResearchReviewCase | None:
    """Resolve a review case (from any non-resolved state)."""
    try:
        case_uuid = _to_uuid(case_id)
    except Exception:
        return None
    case = (
        db.query(ResearchReviewCase)
        .filter(ResearchReviewCase.id == case_uuid)
        .first()
    )
    if case is None or case.status == "resolved":
        return None

    now = datetime.now(timezone.utc)
    case.status = "resolved"
    case.resolved_at = now
    case.updated_at = now

    event = ResearchReviewCaseEvent(
        case_id=case.id,
        event_type="resolved",
        title="Review case resolved",
        created_at=now,
    )
    db.add(event)

    from app.models.audit_timeline_event import AuditTimelineEvent
    from app.core.constants import EventType

    strategy = db.query(Strategy).filter(
        Strategy.id == _to_uuid(case.strategy_id)
    ).first()
    if strategy is not None:
        _ = strategy.project
        audit_event = AuditTimelineEvent(
            organization_id=strategy.project.organization_id,
            project_id=strategy.project_id,
            strategy_id=strategy.id,
            event_type=EventType.research_review_case_resolved,
            source_type="review_case",
            source_id=str(case.id),
            severity="info",
            title="Review case resolved",
            description=f"Review case '{case.title}' was resolved.",
            metadata_json={"case_id": str(case.id), "case_key": case.case_key},
            event_time=now,
        )
        db.add(audit_event)

    db.flush()
    return case
