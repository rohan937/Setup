"""M62: Strategy Progression Freeze Recommendations service.

Deterministic, read-only. No AuditTimelineEvent created.
Not investment advice or trading approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun
from app.models.backtest_audit import BacktestAudit
from app.models.alert import Alert

# ---------------------------------------------------------------------------
# Try-import optional services (gracefully degrade if not available)
# ---------------------------------------------------------------------------

try:
    from app.services.strategy_readiness import compute_strategy_readiness
except ImportError:
    compute_strategy_readiness = None  # type: ignore[assignment]

try:
    from app.services.strategy_robustness import compute_strategy_robustness
except ImportError:
    compute_strategy_robustness = None  # type: ignore[assignment]

try:
    from app.services.promotion_gates import evaluate_promotion_gates
except ImportError:
    evaluate_promotion_gates = None  # type: ignore[assignment]

try:
    from app.services.strategy_drift import compute_strategy_drift
except ImportError:
    compute_strategy_drift = None  # type: ignore[assignment]

try:
    from app.services.shadow_production import compute_shadow_production_monitor
except ImportError:
    compute_shadow_production_monitor = None  # type: ignore[assignment]

try:
    from app.services.evidence_freshness import compute_evidence_freshness
except ImportError:
    compute_evidence_freshness = None  # type: ignore[assignment]

try:
    from app.services.assumption_health import compute_assumption_health
except ImportError:
    compute_assumption_health = None  # type: ignore[assignment]

try:
    from app.services.regression_tests import get_regression_test_runs
except ImportError:
    get_regression_test_runs = None  # type: ignore[assignment]

try:
    from app.services.config_policies import get_config_policy_evaluations
except ImportError:
    get_config_policy_evaluations = None  # type: ignore[assignment]

try:
    from app.services.evidence_sla import get_evidence_sla_evaluations
except ImportError:
    get_evidence_sla_evaluations = None  # type: ignore[assignment]

try:
    from app.services.review_cases import get_research_review_cases
except ImportError:
    get_research_review_cases = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_TARGET_STAGES = [
    "backtest_review",
    "paper_candidate",
    "shadow_production",
    "production_candidate",
]

STAGE_PATH = [
    "idea",
    "research",
    "backtest_review",
    "paper_candidate",
    "shadow_production",
    "production_candidate",
]

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FreezeReasonData:
    reason_key: str
    title: str
    category: str
    severity: str  # low/medium/high/critical
    status: str  # blocker/review/watch/missing
    evidence_summary: str
    source_label: str
    source_id: str | None = None
    suggested_resolution: str = ""
    required_to_unfreeze: bool = False


@dataclass
class UnfreezeRequirementData:
    requirement_key: str
    title: str
    priority: str  # low/medium/high/critical
    required: bool
    current_status: str
    target_status: str
    suggested_action: str
    endpoint_hint: str | None = None


@dataclass
class SubsystemStatusData:
    subsystem: str
    status: str  # ok/watch/review/blocked/fragile/missing/unavailable
    summary: str | None = None
    score: float | None = None


@dataclass
class StageContextData:
    current_stage: str
    target_stage: str
    next_recommended_stage: str
    stage_path: list = field(default_factory=list)


@dataclass
class ProgressionFreezeData:
    strategy_id: str
    strategy_name: str
    generated_at: datetime
    target_stage: str
    current_stage: str
    recommendation: str  # continue_progression/monitor_before_progression/pause_progression/freeze_progression/insufficient_evidence
    recommendation_label: str
    freeze_risk_score: float
    deterministic_summary: str
    freeze_reasons: list  # list[FreezeReasonData]
    unfreeze_requirements: list  # list[UnfreezeRequirementData]
    blocking_reason_count: int
    review_reason_count: int
    watch_reason_count: int
    missing_evidence_count: int
    subsystem_statuses: list  # list[SubsystemStatusData]
    stage_context: StageContextData
    note: str


# ---------------------------------------------------------------------------
# Helper: infer current stage
# ---------------------------------------------------------------------------


def _infer_current_stage(db: Session, strategy_id) -> str:
    """Infer the current stage of a strategy based on its latest run."""
    try:
        run = (
            db.query(StrategyRun)
            .filter(StrategyRun.strategy_id == strategy_id)
            .order_by(
                StrategyRun.completed_at.desc().nullslast(),
                StrategyRun.created_at.desc(),
            )
            .first()
        )
        if run is None:
            return "idea"
        run_type_map = {
            "research": "research",
            "backtest": "backtest_review",
            "paper": "paper_candidate",
            "live": "shadow_production",
        }
        return run_type_map.get(run.run_type, "research")
    except Exception:
        return "idea"


# ---------------------------------------------------------------------------
# Helper: infer target stage
# ---------------------------------------------------------------------------


def _infer_target_stage(current_stage: str) -> str:
    """Return the next logical stage from the current one."""
    progression = {
        "idea": "backtest_review",
        "research": "backtest_review",
        "backtest_review": "paper_candidate",
        "paper_candidate": "shadow_production",
        "shadow_production": "production_candidate",
        "production_candidate": "production_candidate",
    }
    return progression.get(current_stage, "backtest_review")


# ---------------------------------------------------------------------------
# Helper: gather subsystem data
# ---------------------------------------------------------------------------


def _gather_subsystem_data(db: Session, strategy_id, target_stage: str) -> dict:
    """Collect data from all subsystems. Each is wrapped in try/except."""
    data: dict = {}

    # Readiness
    try:
        if compute_strategy_readiness is not None:
            data["readiness"] = compute_strategy_readiness(db, strategy_id)
        else:
            data["readiness"] = None
    except Exception:
        data["readiness"] = None

    # Robustness
    try:
        if compute_strategy_robustness is not None:
            data["robustness"] = compute_strategy_robustness(db, strategy_id)
        else:
            data["robustness"] = None
    except Exception:
        data["robustness"] = None

    # Promotion gates
    try:
        if evaluate_promotion_gates is not None:
            data["gates"] = evaluate_promotion_gates(db, strategy_id, target_stage)
        else:
            data["gates"] = None
    except Exception:
        data["gates"] = None

    # Drift
    try:
        if compute_strategy_drift is not None:
            data["drift"] = compute_strategy_drift(db, strategy_id)
        else:
            data["drift"] = None
    except Exception:
        data["drift"] = None

    # Shadow monitor
    try:
        if compute_shadow_production_monitor is not None:
            data["shadow"] = compute_shadow_production_monitor(db, strategy_id)
        else:
            data["shadow"] = None
    except Exception:
        data["shadow"] = None

    # Evidence freshness
    try:
        if compute_evidence_freshness is not None:
            data["freshness"] = compute_evidence_freshness(db, strategy_id)
        else:
            data["freshness"] = None
    except Exception:
        data["freshness"] = None

    # Assumption health (returns dict)
    try:
        if compute_assumption_health is not None:
            data["assumption"] = compute_assumption_health(db, strategy_id)
        else:
            data["assumption"] = None
    except Exception:
        data["assumption"] = None

    # Regression tests
    try:
        if get_regression_test_runs is not None:
            runs = get_regression_test_runs(strategy_id, db, limit=1)
            data["regression"] = runs[0] if runs else None
        else:
            data["regression"] = None
    except Exception:
        data["regression"] = None

    # Config policy
    try:
        if get_config_policy_evaluations is not None:
            evals = get_config_policy_evaluations(db, strategy_id, limit=1)
            data["policy"] = evals[0] if evals else None
        else:
            data["policy"] = None
    except Exception:
        data["policy"] = None

    # Evidence SLA
    try:
        if get_evidence_sla_evaluations is not None:
            sla_evals = get_evidence_sla_evaluations(db, strategy_id, limit=1)
            data["sla"] = sla_evals[0] if sla_evals else None
        else:
            data["sla"] = None
    except Exception:
        data["sla"] = None

    # Review cases
    try:
        if get_research_review_cases is not None:
            data["review_cases"] = get_research_review_cases(
                db, strategy_id, status="open"
            ) or []
        else:
            data["review_cases"] = []
    except Exception:
        data["review_cases"] = []

    # Alerts
    try:
        alerts = (
            db.query(Alert)
            .filter(
                Alert.strategy_id == str(strategy_id),
                Alert.status == "open",
            )
            .order_by(Alert.severity.desc())
            .all()
        )
        data["alerts"] = alerts
    except Exception:
        data["alerts"] = []

    # Backtest trust
    try:
        audit = (
            db.query(BacktestAudit)
            .join(StrategyRun, StrategyRun.id == BacktestAudit.strategy_run_id)
            .filter(StrategyRun.strategy_id == str(strategy_id))
            .order_by(BacktestAudit.created_at.desc())
            .first()
        )
        data["backtest_trust"] = audit
    except Exception:
        data["backtest_trust"] = None

    return data


# ---------------------------------------------------------------------------
# Helper: build freeze reasons
# ---------------------------------------------------------------------------


def _build_freeze_reasons(subsystem_data: dict, target_stage: str) -> list[FreezeReasonData]:
    """Evaluate all subsystems and produce FreezeReasonData entries."""
    reasons: list[FreezeReasonData] = []

    # 1. Readiness
    readiness = subsystem_data.get("readiness")
    readiness_verdict = getattr(readiness, "readiness_verdict", None)
    if readiness_verdict == "blocked":
        reasons.append(FreezeReasonData(
            reason_key="readiness_blocked",
            title="Strategy readiness is blocked",
            category="readiness",
            severity="critical",
            status="blocker",
            evidence_summary="Readiness check returned 'blocked' verdict.",
            source_label="Strategy Readiness",
            suggested_resolution="Resolve all readiness blockers before progressing.",
            required_to_unfreeze=True,
        ))
    elif readiness_verdict == "requires_review_before_progression":
        reasons.append(FreezeReasonData(
            reason_key="readiness_requires_review",
            title="Strategy readiness requires review before progression",
            category="readiness",
            severity="high",
            status="review",
            evidence_summary="Readiness check requires manual review before advancing.",
            source_label="Strategy Readiness",
            suggested_resolution="Complete readiness review and address flagged items.",
        ))
    elif readiness_verdict == "under_instrumented":
        reasons.append(FreezeReasonData(
            reason_key="readiness_under_instrumented",
            title="Strategy is under-instrumented for readiness assessment",
            category="readiness",
            severity="medium",
            status="review",
            evidence_summary="Insufficient instrumentation to confirm readiness.",
            source_label="Strategy Readiness",
            suggested_resolution="Add monitoring and evidence collection for readiness checks.",
        ))
    elif readiness_verdict is None:
        reasons.append(FreezeReasonData(
            reason_key="readiness_missing",
            title="Readiness data unavailable",
            category="readiness",
            severity="low",
            status="missing",
            evidence_summary="No readiness assessment has been run.",
            source_label="Strategy Readiness",
            suggested_resolution="Run a readiness assessment.",
        ))

    # 2. Robustness
    robustness = subsystem_data.get("robustness")
    robustness_verdict = getattr(robustness, "robustness_verdict", None)
    if robustness_verdict == "fragile_under_variation":
        reasons.append(FreezeReasonData(
            reason_key="robustness_fragile",
            title="Strategy is fragile under parameter variation",
            category="robustness",
            severity="critical",
            status="blocker",
            evidence_summary="Robustness score indicates fragility under logged variation.",
            source_label="Strategy Robustness",
            suggested_resolution="Investigate fragility signals and stabilize strategy parameters.",
            required_to_unfreeze=True,
        ))
    elif robustness_verdict == "requires_review":
        reasons.append(FreezeReasonData(
            reason_key="robustness_requires_review",
            title="Strategy robustness requires review",
            category="robustness",
            severity="high",
            status="review",
            evidence_summary="Robustness assessment found items requiring review.",
            source_label="Strategy Robustness",
            suggested_resolution="Review robustness dimension scorecards and resolve flagged signals.",
        ))
    elif robustness_verdict == "stable_with_watch_items":
        reasons.append(FreezeReasonData(
            reason_key="robustness_watch_items",
            title="Strategy robustness has watch items",
            category="robustness",
            severity="low",
            status="watch",
            evidence_summary="Strategy is stable but has watch items to monitor.",
            source_label="Strategy Robustness",
            suggested_resolution="Monitor robustness watch items during progression.",
        ))
    elif robustness_verdict is None:
        reasons.append(FreezeReasonData(
            reason_key="robustness_missing",
            title="Robustness data unavailable",
            category="robustness",
            severity="low",
            status="missing",
            evidence_summary="No robustness assessment has been run.",
            source_label="Strategy Robustness",
            suggested_resolution="Run a robustness assessment.",
        ))

    # 3. Promotion gates
    gates = subsystem_data.get("gates")
    promotion_verdict = getattr(gates, "promotion_verdict", None)
    if promotion_verdict == "blocked":
        reasons.append(FreezeReasonData(
            reason_key="gates_blocked",
            title=f"Promotion gates are blocked for {target_stage}",
            category="promotion_gates",
            severity="critical",
            status="blocker",
            evidence_summary=f"Promotion gate evaluation returned 'blocked' for target stage '{target_stage}'.",
            source_label="Promotion Gates",
            suggested_resolution="Resolve all gate failures before attempting progression.",
            required_to_unfreeze=True,
        ))
    elif promotion_verdict == "requires_review":
        reasons.append(FreezeReasonData(
            reason_key="gates_requires_review",
            title="Promotion gates require review",
            category="promotion_gates",
            severity="high",
            status="review",
            evidence_summary="Promotion gate evaluation requires manual review.",
            source_label="Promotion Gates",
            suggested_resolution="Review gate conditions and address any outstanding items.",
        ))
    elif promotion_verdict == "insufficient_evidence":
        reasons.append(FreezeReasonData(
            reason_key="gates_insufficient_evidence",
            title="Insufficient evidence for promotion gate evaluation",
            category="promotion_gates",
            severity="medium",
            status="missing",
            evidence_summary="Not enough evidence to evaluate promotion gates.",
            source_label="Promotion Gates",
            suggested_resolution="Gather more evidence to enable gate evaluation.",
        ))
    elif promotion_verdict == "conditional_pass":
        reasons.append(FreezeReasonData(
            reason_key="gates_conditional_pass",
            title="Promotion gates passed conditionally",
            category="promotion_gates",
            severity="low",
            status="watch",
            evidence_summary="Promotion gates passed with conditions; monitor during progression.",
            source_label="Promotion Gates",
            suggested_resolution="Monitor conditional gate items during the next stage.",
        ))

    # 4. Drift
    drift = subsystem_data.get("drift")
    drift_status = getattr(drift, "drift_status", None)
    if drift_status == "severe":
        reasons.append(FreezeReasonData(
            reason_key="drift_severe",
            title="Severe strategy drift detected",
            category="drift",
            severity="critical",
            status="blocker",
            evidence_summary="Drift analysis indicates severe deviation from baseline.",
            source_label="Strategy Drift",
            suggested_resolution="Investigate severe drift before progressing.",
        ))
    elif drift_status == "review":
        reasons.append(FreezeReasonData(
            reason_key="drift_review",
            title="Strategy drift requires review",
            category="drift",
            severity="high",
            status="review",
            evidence_summary="Drift analysis flagged items requiring review.",
            source_label="Strategy Drift",
            suggested_resolution="Review drift signals and confirm they are acceptable.",
        ))
    elif drift_status == "watch":
        reasons.append(FreezeReasonData(
            reason_key="drift_watch",
            title="Strategy drift in watch range",
            category="drift",
            severity="low",
            status="watch",
            evidence_summary="Drift is within acceptable range but trending — monitor.",
            source_label="Strategy Drift",
            suggested_resolution="Continue monitoring drift during progression.",
        ))
    elif drift_status is None or drift_status in ("insufficient_evidence", "no_shadow_runs"):
        reasons.append(FreezeReasonData(
            reason_key="drift_missing",
            title="Drift data unavailable",
            category="drift",
            severity="low",
            status="missing",
            evidence_summary="No drift assessment data available.",
            source_label="Strategy Drift",
            suggested_resolution="Run drift analysis after accumulating run history.",
        ))

    # 5. Shadow monitor
    shadow = subsystem_data.get("shadow")
    shadow_status = getattr(shadow, "monitor_status", None)
    if shadow_status == "severe":
        reasons.append(FreezeReasonData(
            reason_key="shadow_severe",
            title="Shadow monitor shows severe deviation",
            category="shadow_monitor",
            severity="critical",
            status="blocker",
            evidence_summary="Shadow production monitor reports severe divergence.",
            source_label="Shadow Monitor",
            suggested_resolution="Investigate shadow monitor deviations before progressing.",
        ))
    elif shadow_status == "review":
        reasons.append(FreezeReasonData(
            reason_key="shadow_review",
            title="Shadow monitor requires review",
            category="shadow_monitor",
            severity="high",
            status="review",
            evidence_summary="Shadow monitor flagged items requiring review.",
            source_label="Shadow Monitor",
            suggested_resolution="Review shadow monitor findings before advancing.",
        ))
    elif shadow_status == "no_shadow_runs":
        reasons.append(FreezeReasonData(
            reason_key="shadow_no_runs",
            title="No shadow runs available for monitoring",
            category="shadow_monitor",
            severity="medium",
            status="missing",
            evidence_summary="Shadow monitor has no data — no paper/live-like runs logged.",
            source_label="Shadow Monitor",
            suggested_resolution="Log a paper/live-like run to enable shadow monitoring.",
        ))
    elif shadow_status == "watch":
        reasons.append(FreezeReasonData(
            reason_key="shadow_watch",
            title="Shadow monitor in watch range",
            category="shadow_monitor",
            severity="low",
            status="watch",
            evidence_summary="Shadow monitor is within acceptable range but warrants monitoring.",
            source_label="Shadow Monitor",
            suggested_resolution="Continue monitoring shadow run performance.",
        ))

    # 6. Evidence freshness
    freshness = subsystem_data.get("freshness")
    freshness_status = getattr(freshness, "freshness_status", None)
    if freshness_status in ("stale", "missing_evidence"):
        reasons.append(FreezeReasonData(
            reason_key="freshness_stale",
            title="Evidence is stale or missing",
            category="evidence_freshness",
            severity="medium",
            status="review",
            evidence_summary=f"Evidence freshness status: {freshness_status}. Data may be outdated.",
            source_label="Evidence Freshness",
            suggested_resolution="Refresh stale evidence before progressing.",
        ))
    elif freshness_status == "aging":
        reasons.append(FreezeReasonData(
            reason_key="freshness_aging",
            title="Evidence is aging",
            category="evidence_freshness",
            severity="low",
            status="watch",
            evidence_summary="Evidence is aging and may become stale soon.",
            source_label="Evidence Freshness",
            suggested_resolution="Plan evidence refresh to maintain freshness.",
        ))
    elif freshness_status is None:
        reasons.append(FreezeReasonData(
            reason_key="freshness_missing",
            title="Evidence freshness data unavailable",
            category="evidence_freshness",
            severity="low",
            status="missing",
            evidence_summary="No evidence freshness assessment available.",
            source_label="Evidence Freshness",
            suggested_resolution="Run evidence freshness assessment.",
        ))

    # 7. Assumption health
    assumption = subsystem_data.get("assumption")  # dict or None
    assumption_status = assumption.get("status") if isinstance(assumption, dict) else None
    if assumption_status == "weak":
        reasons.append(FreezeReasonData(
            reason_key="assumption_weak",
            title="Core assumptions have weak support",
            category="assumption_health",
            severity="critical",
            status="blocker",
            evidence_summary="Assumption health score indicates weak or missing support for core assumptions.",
            source_label="Assumption Health",
            suggested_resolution="Address weak assumptions with additional evidence before progressing.",
            required_to_unfreeze=True,
        ))
    elif assumption_status == "review":
        reasons.append(FreezeReasonData(
            reason_key="assumption_review",
            title="Assumption health requires review",
            category="assumption_health",
            severity="high",
            status="review",
            evidence_summary="Some assumptions require review and additional support.",
            source_label="Assumption Health",
            suggested_resolution="Review flagged assumptions and gather supporting evidence.",
        ))
    elif assumption_status is None:
        reasons.append(FreezeReasonData(
            reason_key="assumption_missing",
            title="Assumption health data unavailable",
            category="assumption_health",
            severity="low",
            status="missing",
            evidence_summary="No assumption health assessment available.",
            source_label="Assumption Health",
            suggested_resolution="Run assumption health assessment.",
        ))

    # 8. Regression tests
    regression = subsystem_data.get("regression")
    reg_status = getattr(regression, "overall_status", None) if regression else None
    required_failed = getattr(regression, "required_failed_count", 0) if regression else 0
    if reg_status == "failed" and required_failed > 0:
        reasons.append(FreezeReasonData(
            reason_key="regression_required_failed",
            title="Required regression tests are failing",
            category="regression_tests",
            severity="critical",
            status="blocker",
            evidence_summary=f"{required_failed} required regression test(s) failed.",
            source_label="Regression Tests",
            suggested_resolution="Fix all required failing regression tests before progressing.",
            required_to_unfreeze=True,
        ))
    elif reg_status == "failed":
        reasons.append(FreezeReasonData(
            reason_key="regression_failed",
            title="Regression tests are failing",
            category="regression_tests",
            severity="high",
            status="review",
            evidence_summary="Regression test suite has failures (no required tests failed).",
            source_label="Regression Tests",
            suggested_resolution="Review and resolve regression test failures.",
        ))
    elif reg_status == "warning":
        reasons.append(FreezeReasonData(
            reason_key="regression_warning",
            title="Regression tests have warnings",
            category="regression_tests",
            severity="medium",
            status="review",
            evidence_summary="Regression test suite completed with warnings.",
            source_label="Regression Tests",
            suggested_resolution="Investigate regression test warnings.",
        ))
    elif reg_status is None:
        reasons.append(FreezeReasonData(
            reason_key="regression_missing",
            title="Regression test data unavailable",
            category="regression_tests",
            severity="low",
            status="missing",
            evidence_summary="No regression test run found for this strategy.",
            source_label="Regression Tests",
            suggested_resolution="Run the regression test suite.",
        ))

    # 9. Config policy
    policy = subsystem_data.get("policy")
    policy_status = getattr(policy, "overall_status", None) if policy else None
    if policy_status == "failed":
        reasons.append(FreezeReasonData(
            reason_key="policy_failed",
            title="Config policy evaluation failed",
            category="config_policy",
            severity="high",
            status="blocker",
            evidence_summary="Config policy check detected violations.",
            source_label="Config Policy",
            suggested_resolution="Resolve all config policy violations before progressing.",
        ))
    elif policy_status == "warning":
        reasons.append(FreezeReasonData(
            reason_key="policy_warning",
            title="Config policy has warnings",
            category="config_policy",
            severity="medium",
            status="review",
            evidence_summary="Config policy check found warnings.",
            source_label="Config Policy",
            suggested_resolution="Review and address config policy warnings.",
        ))
    elif policy_status is None:
        reasons.append(FreezeReasonData(
            reason_key="policy_missing",
            title="Config policy data unavailable",
            category="config_policy",
            severity="low",
            status="missing",
            evidence_summary="No config policy evaluation found.",
            source_label="Config Policy",
            suggested_resolution="Run config policy evaluation.",
        ))

    # 10. Evidence SLA
    sla = subsystem_data.get("sla")
    sla_status = getattr(sla, "overall_status", None) if sla else None
    violated = getattr(sla, "violated_count", 0) if sla else 0
    critical_v = getattr(sla, "critical_violation_count", 0) if sla else 0
    if sla_status == "violated" and critical_v > 0:
        reasons.append(FreezeReasonData(
            reason_key="sla_critical_violated",
            title="Critical evidence SLA violations detected",
            category="evidence_sla",
            severity="critical",
            status="blocker",
            evidence_summary=f"{critical_v} critical SLA violation(s) detected.",
            source_label="Evidence SLA",
            suggested_resolution="Resolve critical SLA violations before progressing.",
        ))
    elif sla_status == "violated":
        reasons.append(FreezeReasonData(
            reason_key="sla_violated",
            title="Evidence SLA violations detected",
            category="evidence_sla",
            severity="high",
            status="review",
            evidence_summary=f"{violated} SLA violation(s) detected.",
            source_label="Evidence SLA",
            suggested_resolution="Address evidence SLA violations.",
        ))
    elif sla_status == "warning":
        reasons.append(FreezeReasonData(
            reason_key="sla_warning",
            title="Evidence SLA warnings",
            category="evidence_sla",
            severity="medium",
            status="review",
            evidence_summary="Evidence SLA evaluation returned warnings.",
            source_label="Evidence SLA",
            suggested_resolution="Review evidence SLA warnings.",
        ))
    elif sla_status is None:
        reasons.append(FreezeReasonData(
            reason_key="sla_missing",
            title="Evidence SLA data unavailable",
            category="evidence_sla",
            severity="low",
            status="missing",
            evidence_summary="No evidence SLA evaluation found.",
            source_label="Evidence SLA",
            suggested_resolution="Run evidence SLA evaluation.",
        ))

    # 11. Review cases
    cases = subsystem_data.get("review_cases", [])
    critical_cases = [c for c in cases if getattr(c, "severity", "") == "critical"]
    high_cases = [c for c in cases if getattr(c, "severity", "") == "high"]
    for case in critical_cases[:2]:
        case_title = getattr(case, "title", "Unknown case")
        case_key_val = getattr(case, "case_key", "")
        reasons.append(FreezeReasonData(
            reason_key=f"review_case_critical_{case_key_val}",
            title=f"Critical open review case: {case_title}",
            category="review_cases",
            severity="critical",
            status="blocker",
            evidence_summary=f"Open critical review case '{case_title}' must be resolved.",
            source_label="Research Review Cases",
            source_id=str(getattr(case, "id", "")),
            suggested_resolution="Resolve or acknowledge this critical review case.",
            required_to_unfreeze=True,
        ))
    for case in high_cases[:2]:
        case_title = getattr(case, "title", "Unknown case")
        case_key_val = getattr(case, "case_key", "")
        reasons.append(FreezeReasonData(
            reason_key=f"review_case_high_{case_key_val}",
            title=f"High-severity open review case: {case_title}",
            category="review_cases",
            severity="high",
            status="review",
            evidence_summary=f"Open high-severity review case '{case_title}' requires attention.",
            source_label="Research Review Cases",
            source_id=str(getattr(case, "id", "")),
            suggested_resolution="Review and address this high-severity review case.",
        ))

    # 12. Alerts
    alerts_list = subsystem_data.get("alerts", [])
    critical_alerts = [a for a in alerts_list if getattr(a, "severity", "") == "critical"]
    high_alerts = [a for a in alerts_list if getattr(a, "severity", "") == "high"]
    for alert in critical_alerts[:2]:
        alert_title = getattr(alert, "title", "Unknown alert")
        alert_id = str(getattr(alert, "id", ""))
        reasons.append(FreezeReasonData(
            reason_key=f"alert_critical_{alert_id}",
            title=f"Critical open alert: {alert_title}",
            category="alerts",
            severity="critical",
            status="blocker",
            evidence_summary=f"Critical alert '{alert_title}' is open and requires resolution.",
            source_label="Alerts",
            source_id=alert_id,
            suggested_resolution="Resolve or acknowledge the critical alert before progressing.",
            required_to_unfreeze=True,
        ))
    for alert in high_alerts[:2]:
        alert_title = getattr(alert, "title", "Unknown alert")
        alert_id = str(getattr(alert, "id", ""))
        reasons.append(FreezeReasonData(
            reason_key=f"alert_high_{alert_id}",
            title=f"High-severity open alert: {alert_title}",
            category="alerts",
            severity="high",
            status="review",
            evidence_summary=f"High-severity alert '{alert_title}' is open.",
            source_label="Alerts",
            source_id=alert_id,
            suggested_resolution="Review and address the high-severity alert.",
        ))

    # 13. Backtest trust
    audit = subsystem_data.get("backtest_trust")
    trust = getattr(audit, "trust_score", None) if audit else None
    if trust is not None and trust < 40:
        reasons.append(FreezeReasonData(
            reason_key="backtest_trust_critical",
            title=f"Backtest trust score is critically low ({trust})",
            category="backtest_trust",
            severity="critical",
            status="blocker",
            evidence_summary=f"Backtest audit trust score {trust}/100 is below the critical threshold of 40.",
            source_label="Backtest Audit",
            suggested_resolution="Investigate and resolve backtest quality issues.",
            required_to_unfreeze=True,
        ))
    elif trust is not None and trust < 60:
        reasons.append(FreezeReasonData(
            reason_key="backtest_trust_low",
            title=f"Backtest trust score is low ({trust})",
            category="backtest_trust",
            severity="high",
            status="review",
            evidence_summary=f"Backtest audit trust score {trust}/100 is below 60.",
            source_label="Backtest Audit",
            suggested_resolution="Review backtest audit findings and improve data quality.",
        ))
    elif audit is None:
        reasons.append(FreezeReasonData(
            reason_key="backtest_trust_missing",
            title="Backtest audit data unavailable",
            category="backtest_trust",
            severity="low",
            status="missing",
            evidence_summary="No backtest audit has been run for this strategy.",
            source_label="Backtest Audit",
            suggested_resolution="Run a backtest audit to validate backtest quality.",
        ))

    return reasons


# ---------------------------------------------------------------------------
# Helper: compute freeze risk score
# ---------------------------------------------------------------------------


def _compute_freeze_risk_score(reasons: list[FreezeReasonData]) -> float:
    """Compute a 0–100 risk score from the list of freeze reasons."""
    score = 0.0
    critical_blocker_total = 0.0
    high_blocker_total = 0.0
    high_review_total = 0.0
    medium_review_total = 0.0
    watch_total = 0.0
    missing_total = 0.0

    for r in reasons:
        if r.status == "blocker" and r.severity == "critical":
            critical_blocker_total += 30
        elif r.status == "blocker" and r.severity == "high":
            high_blocker_total += 20
        elif r.status == "review" and r.severity == "high":
            high_review_total += 15
        elif r.status == "review" and r.severity == "medium":
            medium_review_total += 10
        elif r.status == "watch":
            watch_total += 5
        elif r.status == "missing":
            missing_total += 8

    score += min(critical_blocker_total, 60)
    score += min(high_blocker_total, 60)
    score += min(high_review_total, 60)
    score += min(medium_review_total, 40)
    score += min(watch_total, 20)
    score += min(missing_total, 30)

    return min(score, 100.0)


# ---------------------------------------------------------------------------
# Helper: score to recommendation
# ---------------------------------------------------------------------------


def _score_to_recommendation(score: float, reasons: list[FreezeReasonData]) -> str:
    """Convert a risk score and reasons list into a recommendation string."""
    have_critical_blocker = any(
        r.severity == "critical" and r.status == "blocker" for r in reasons
    )
    have_high_blocker = any(
        r.severity == "high" and r.status == "blocker" for r in reasons
    )

    # Override checks first
    if have_critical_blocker:
        return "freeze_progression"
    if score >= 70:
        return "freeze_progression"
    if have_high_blocker:
        return "pause_progression"
    if score >= 41:
        return "pause_progression"
    if score >= 21:
        return "monitor_before_progression"

    # Special case: insufficient evidence
    non_missing = [r for r in reasons if r.status != "missing"]
    all_watch_or_missing = all(r.status in ("watch", "missing") for r in reasons)
    if all_watch_or_missing and len(non_missing) < 4:
        return "insufficient_evidence"

    return "continue_progression"


# ---------------------------------------------------------------------------
# Helper: build unfreeze requirements
# ---------------------------------------------------------------------------


def _build_unfreeze_requirements(
    reasons: list[FreezeReasonData], recommendation: str
) -> list[UnfreezeRequirementData]:
    """Build the list of requirements to unfreeze/unpause progression."""
    requirements: list[UnfreezeRequirementData] = []
    seen_keys: set[str] = set()

    def _add(req: UnfreezeRequirementData) -> None:
        if req.requirement_key not in seen_keys:
            seen_keys.add(req.requirement_key)
            requirements.append(req)

    if recommendation == "freeze_progression":
        # Standard gate re-evaluation requirement
        _add(UnfreezeRequirementData(
            requirement_key="re_evaluate_promotion_gates",
            title="Re-evaluate promotion gates after remediation",
            priority="high",
            required=True,
            current_status="blocked",
            target_status="pass",
            suggested_action="Resolve all blockers listed, then re-run the promotion gate evaluation.",
            endpoint_hint="GET /api/strategies/{strategy_id}/promotion-gates",
        ))

        # Add requirements for each required_to_unfreeze reason
        for r in reasons:
            if r.required_to_unfreeze:
                _add(UnfreezeRequirementData(
                    requirement_key=f"resolve_{r.reason_key}",
                    title=f"Resolve: {r.title}",
                    priority="critical" if r.severity == "critical" else "high",
                    required=True,
                    current_status=r.status,
                    target_status="resolved",
                    suggested_action=r.suggested_resolution or "Resolve the listed issue.",
                ))

    elif recommendation == "pause_progression":
        # Add requirements for high-severity reasons
        for r in reasons:
            if r.severity == "high":
                _add(UnfreezeRequirementData(
                    requirement_key=f"address_{r.reason_key}",
                    title=f"Address: {r.title}",
                    priority="high",
                    required=r.required_to_unfreeze,
                    current_status=r.status,
                    target_status="resolved",
                    suggested_action=r.suggested_resolution or "Address the listed issue.",
                ))

        # Add regression test requirement if regression was an issue
        regression_issues = [r for r in reasons if r.category == "regression_tests" and r.status in ("blocker", "review")]
        if regression_issues:
            _add(UnfreezeRequirementData(
                requirement_key="run_regression_suite",
                title="Run and pass the regression test suite",
                priority="high",
                required=False,
                current_status="failing_or_warning",
                target_status="passed",
                suggested_action="Run the full regression test suite and resolve all failures.",
                endpoint_hint="POST /api/strategies/{strategy_id}/regression-tests/run",
            ))

        # Add freshness requirement if freshness was an issue
        freshness_issues = [r for r in reasons if r.category == "evidence_freshness" and r.status in ("review", "blocker")]
        if freshness_issues:
            _add(UnfreezeRequirementData(
                requirement_key="refresh_stale_evidence",
                title="Refresh stale evidence",
                priority="medium",
                required=False,
                current_status="stale",
                target_status="fresh",
                suggested_action="Refresh or re-run evidence collection for stale evidence items.",
                endpoint_hint="GET /api/strategies/{strategy_id}/evidence-freshness",
            ))

    # Sort by priority: critical > high > medium > low
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    requirements.sort(key=lambda x: priority_order.get(x.priority, 99))

    return requirements


# ---------------------------------------------------------------------------
# Helper: build subsystem statuses
# ---------------------------------------------------------------------------


def _build_subsystem_statuses(
    subsystem_data: dict, reasons: list[FreezeReasonData]
) -> list[SubsystemStatusData]:
    """Map each subsystem to a status string based on reasons and available data."""
    subsystems = [
        "readiness",
        "robustness",
        "promotion_gates",
        "drift",
        "shadow_monitor",
        "evidence_freshness",
        "assumption_health",
        "regression_tests",
        "config_policy",
        "evidence_sla",
        "review_cases",
        "alerts",
        "backtest_trust",
    ]

    def _category_for_subsystem(s: str) -> str:
        return s  # categories match subsystem names in our implementation

    def _severity_to_status(severity: str | None, status: str | None) -> str:
        if status == "blocker":
            if severity == "critical":
                return "blocked"
            return "fragile"
        if status == "review":
            if severity in ("critical", "high"):
                return "review"
            return "watch"
        if status == "watch":
            return "watch"
        if status == "missing":
            return "missing"
        return "ok"

    result: list[SubsystemStatusData] = []
    for subsystem in subsystems:
        # Find the worst reason for this subsystem category
        subsystem_reasons = [r for r in reasons if r.category == subsystem]
        if not subsystem_reasons:
            status = "ok"
        else:
            # Find worst (critical blocker > high blocker > high review > medium > watch > missing)
            severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            status_rank = {"blocker": 0, "review": 1, "watch": 2, "missing": 3}
            worst = min(
                subsystem_reasons,
                key=lambda r: (
                    status_rank.get(r.status, 99),
                    severity_rank.get(r.severity, 99),
                ),
            )
            status = _severity_to_status(worst.severity, worst.status)

        # Get score if available
        score: float | None = None
        summary: str | None = None
        if subsystem == "readiness":
            rd = subsystem_data.get("readiness")
            score_val = getattr(rd, "readiness_score", None)
            if score_val is not None:
                score = float(score_val)
        elif subsystem == "robustness":
            rb = subsystem_data.get("robustness")
            score_val = getattr(rb, "robustness_score", None)
            if score_val is not None:
                score = float(score_val)
        elif subsystem == "backtest_trust":
            audit = subsystem_data.get("backtest_trust")
            trust = getattr(audit, "trust_score", None)
            if trust is not None:
                score = float(trust)

        result.append(SubsystemStatusData(
            subsystem=subsystem,
            status=status,
            summary=summary,
            score=score,
        ))

    return result


# ---------------------------------------------------------------------------
# Helper: build summary
# ---------------------------------------------------------------------------


def _build_summary(
    recommendation: str,
    blocking_count: int,
    review_count: int,
    target_stage: str,
    top_reasons: list[FreezeReasonData],
) -> str:
    """Build a deterministic, human-readable summary string."""
    if recommendation == "freeze_progression":
        blockers = [r for r in top_reasons if r.status == "blocker"]
        if blockers:
            blocker_titles = "; ".join(r.title for r in blockers[:3])
            return (
                f"Progression to {target_stage} is frozen. "
                f"Blockers: {blocker_titles}. "
                "Resolve the listed blockers and re-evaluate promotion gates."
            )
        return (
            f"Progression to {target_stage} is frozen due to high cumulative risk. "
            "Resolve the listed issues and re-evaluate."
        )
    elif recommendation == "pause_progression":
        return (
            f"Progression to {target_stage} is paused. "
            f"{blocking_count} blocker(s) and {review_count} review item(s) require attention. "
            "Address high-severity items before advancing."
        )
    elif recommendation == "monitor_before_progression":
        return (
            f"Progression to {target_stage} can proceed with active monitoring. "
            "No critical blockers detected, but watch items require attention during transition."
        )
    elif recommendation == "insufficient_evidence":
        return (
            f"Insufficient evidence to make a confident progression recommendation for {target_stage}. "
            "Gather more evidence across readiness, robustness, and drift subsystems."
        )
    else:  # continue_progression
        return (
            f"Progression to {target_stage} can continue. "
            "No high-severity blockers detected."
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def compute_progression_freeze_recommendation(
    db: Session,
    strategy_id,
    target_stage: str | None = None,
) -> ProgressionFreezeData:
    """Compute a deterministic progression freeze recommendation for a strategy.

    Read-only. No AuditTimelineEvent created. Not investment advice.
    """
    generated_at = datetime.now(timezone.utc)

    # 1. Load strategy
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        stub_stage = "idea"
        stub_target = target_stage or "backtest_review"
        return ProgressionFreezeData(
            strategy_id=str(strategy_id),
            strategy_name="Unknown",
            generated_at=generated_at,
            target_stage=stub_target,
            current_stage=stub_stage,
            recommendation="insufficient_evidence",
            recommendation_label="Insufficient Evidence",
            freeze_risk_score=0.0,
            deterministic_summary="Strategy not found; no recommendation can be generated.",
            freeze_reasons=[],
            unfreeze_requirements=[],
            blocking_reason_count=0,
            review_reason_count=0,
            watch_reason_count=0,
            missing_evidence_count=0,
            subsystem_statuses=[],
            stage_context=StageContextData(
                current_stage=stub_stage,
                target_stage=stub_target,
                next_recommended_stage=stub_target,
                stage_path=STAGE_PATH,
            ),
            note="This is a deterministic research progression recommendation. It is not trading approval or live execution control.",
        )

    # 2. Infer current stage
    current_stage = _infer_current_stage(db, strategy_id)

    # 3. Determine target stage
    if target_stage is None:
        target_stage = _infer_target_stage(current_stage)

    # 4. Validate target_stage
    if target_stage not in VALID_TARGET_STAGES:
        target_stage = _infer_target_stage(current_stage)

    # 5. Gather subsystem data
    subsystem_data = _gather_subsystem_data(db, strategy_id, target_stage)

    # 6. Build freeze reasons
    reasons = _build_freeze_reasons(subsystem_data, target_stage)

    # 7. Compute risk score
    risk_score = _compute_freeze_risk_score(reasons)

    # 8. Determine recommendation
    recommendation = _score_to_recommendation(risk_score, reasons)

    # Override to insufficient_evidence if strategy has no runs
    try:
        run_count = (
            db.query(StrategyRun)
            .filter(StrategyRun.strategy_id == strategy_id)
            .count()
        )
        if run_count == 0:
            recommendation = "insufficient_evidence"
    except Exception:
        pass

    # 9. Build unfreeze requirements
    unfreeze_requirements = _build_unfreeze_requirements(reasons, recommendation)

    # 10. Build subsystem statuses
    subsystem_statuses = _build_subsystem_statuses(subsystem_data, reasons)

    # 11. Count reasons by type
    blocking_count = sum(1 for r in reasons if r.status == "blocker")
    review_count = sum(1 for r in reasons if r.status == "review")
    watch_count = sum(1 for r in reasons if r.status == "watch")
    missing_count = sum(1 for r in reasons if r.status == "missing")

    # 12. Build stage context
    try:
        current_idx = STAGE_PATH.index(current_stage)
    except ValueError:
        current_idx = 0
    try:
        target_idx = STAGE_PATH.index(target_stage)
    except ValueError:
        target_idx = current_idx + 1

    if recommendation in ("freeze_progression", "pause_progression", "monitor_before_progression"):
        next_recommended = current_stage
    else:
        next_recommended = target_stage

    stage_context = StageContextData(
        current_stage=current_stage,
        target_stage=target_stage,
        next_recommended_stage=next_recommended,
        stage_path=STAGE_PATH,
    )

    # 13. Build summary
    deterministic_summary = _build_summary(
        recommendation, blocking_count, review_count, target_stage, reasons
    )

    # 14. Recommendation label
    recommendation_label = recommendation.replace("_", " ").title()

    # 15. Note
    note = "This is a deterministic research progression recommendation. It is not trading approval or live execution control."

    return ProgressionFreezeData(
        strategy_id=str(strategy_id),
        strategy_name=strategy.name,
        generated_at=generated_at,
        target_stage=target_stage,
        current_stage=current_stage,
        recommendation=recommendation,
        recommendation_label=recommendation_label,
        freeze_risk_score=risk_score,
        deterministic_summary=deterministic_summary,
        freeze_reasons=reasons,
        unfreeze_requirements=unfreeze_requirements,
        blocking_reason_count=blocking_count,
        review_reason_count=review_count,
        watch_reason_count=watch_count,
        missing_evidence_count=missing_count,
        subsystem_statuses=subsystem_statuses,
        stage_context=stage_context,
        note=note,
    )
