"""M64 Strategy Reliability Command Center service.

Aggregates all reliability sub-systems into a single governance view.
Deterministic, read-only — no AuditTimelineEvent created.
Not investment advice or trading authorisation.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun
from app.models.alert import Alert

try:
    from app.models.review_case import ResearchReviewCase as _ReviewCase  # noqa: F401
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Optional service imports — each wrapped individually so a missing service
# never breaks the whole command-center.
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
    from app.services.progression_freeze import compute_progression_freeze_recommendation
except ImportError:
    compute_progression_freeze_recommendation = None  # type: ignore[assignment]

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

try:
    from app.services.experiments import get_strategy_experiments
except ImportError:
    get_strategy_experiments = None  # type: ignore[assignment]

try:
    from app.services.evidence_graph import build_strategy_evidence_graph
except ImportError:
    build_strategy_evidence_graph = None  # type: ignore[assignment]

try:
    from app.services.change_impact import analyze_strategy_change_impact
except ImportError:
    analyze_strategy_change_impact = None  # type: ignore[assignment]

try:
    from app.services.research_audit_trail import get_strategy_research_audit_trail
except ImportError:
    get_strategy_research_audit_trail = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SubsystemStatusData:
    subsystem_key: str
    title: str
    status: str  # healthy/watch/review/blocked/missing/error
    score: float | None = None
    severity: str = "info"  # info/low/medium/high/critical
    summary: str | None = None
    top_issue: str | None = None
    suggested_action: str | None = None
    route_hint: str | None = None
    source_json: dict | None = None


@dataclass
class CommandCenterBlockerData:
    blocker_key: str
    title: str
    category: str
    severity: str
    evidence_summary: str
    source_subsystem: str
    required_before_progression: bool = False
    suggested_resolution: str = ""


@dataclass
class CommandCenterActionData:
    action_key: str
    title: str
    priority: str  # low/medium/high/critical
    action_type: str
    reason: str
    endpoint_hint: str | None = None
    route_hint: str | None = None
    depends_on: list = field(default_factory=list)


@dataclass
class GovernanceSummaryData:
    open_review_case_count: int = 0
    acknowledged_review_case_count: int = 0
    high_critical_alert_count: int = 0
    latest_regression_status: str | None = None
    latest_policy_status: str | None = None
    latest_sla_status: str | None = None
    latest_freeze_recommendation: str | None = None
    promotion_gate_paper_verdict: str | None = None
    promotion_gate_production_verdict: str | None = None


@dataclass
class EvidenceSummaryData:
    freshness_status: str | None = None
    coverage_score: float | None = None
    missing_evidence_count: int = 0
    stale_evidence_count: int = 0
    graph_status: str | None = None
    replay_pack_recommended: bool = False
    latest_run_id: str | None = None
    latest_run_label: str | None = None


@dataclass
class WorkflowSummaryData:
    current_stage: str = "idea"
    next_recommended_stage: str = "backtest_review"
    stage_path: list = field(default_factory=list)
    active_experiment_count: int = 0
    latest_experiment_analysis_status: str | None = None
    latest_sweep_status: str | None = None
    latest_audit_event_at: datetime | None = None


@dataclass
class StrategyReliabilityCommandCenterData:
    strategy_id: str
    strategy_name: str
    generated_at: datetime
    command_status: str  # clear/monitor/review/blocked/insufficient_evidence
    command_score: float | None
    deterministic_summary: str
    subsystem_statuses: list  # list[SubsystemStatusData]
    top_blockers: list  # list[CommandCenterBlockerData]
    action_queue: list  # list[CommandCenterActionData]
    governance_summary: GovernanceSummaryData
    evidence_summary: EvidenceSummaryData
    workflow_summary: WorkflowSummaryData
    note: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_call(fn, *args, **kwargs):
    """Call fn safely; return (result, None) or (None, error_str)."""
    if fn is None:
        return None, "service not available"
    try:
        return fn(*args, **kwargs), None
    except Exception as exc:
        return None, str(exc)


def _infer_current_stage(db: Session, strategy_id: uuid.UUID) -> str:
    """Infer the current research stage from the latest strategy run."""
    run = (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(StrategyRun.created_at.desc())
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
    return run_type_map.get(str(run.run_type), "research")


def _score_to_status(
    score: float | None,
    healthy_thresh: float = 80.0,
    watch_thresh: float = 65.0,
    review_thresh: float = 45.0,
) -> str:
    if score is None:
        return "missing"
    if score >= healthy_thresh:
        return "healthy"
    if score >= watch_thresh:
        return "watch"
    if score >= review_thresh:
        return "review"
    return "blocked"


# ---------------------------------------------------------------------------
# Subsystem builder
# ---------------------------------------------------------------------------

def _build_subsystem_statuses(subsystem_data: dict) -> list[SubsystemStatusData]:  # noqa: C901
    statuses: list[SubsystemStatusData] = []

    # 1. readiness
    result = subsystem_data.get("readiness")
    score = getattr(result, "readiness_score", None)
    verdict = getattr(result, "readiness_verdict", None)
    if verdict == "blocked":
        status = "blocked"
    elif verdict in ("requires_review_before_progression", "under_instrumented"):
        status = "review"
    else:
        status = _score_to_status(score)
    top_issue = getattr(result, "primary_concern", None)
    statuses.append(SubsystemStatusData(
        subsystem_key="readiness",
        title="Strategy Readiness",
        status=status,
        score=score,
        severity="high" if status in ("blocked", "review") else "info",
        top_issue=top_issue,
        route_hint="/strategies/{id}#readiness",
    ))

    # 2. robustness
    result = subsystem_data.get("robustness")
    score = getattr(result, "robustness_score", None)
    verdict = getattr(result, "robustness_verdict", None)
    if verdict == "fragile_under_variation":
        status = "blocked"
    elif verdict == "requires_review":
        status = "review"
    else:
        status = _score_to_status(score)
    statuses.append(SubsystemStatusData(
        subsystem_key="robustness",
        title="Strategy Robustness",
        status=status,
        score=score,
        severity="high" if status in ("blocked", "review") else "info",
        route_hint="/strategies/{id}#robustness",
    ))

    # 3. progression_freeze
    result = subsystem_data.get("freeze")
    risk = getattr(result, "freeze_risk_score", None)
    rec = getattr(result, "recommendation", None)
    score = (100.0 - float(risk)) if risk is not None else None
    if rec == "freeze_progression":
        status = "blocked"
    elif rec == "pause_progression":
        status = "review"
    elif rec == "monitor_before_progression":
        status = "watch"
    elif rec == "continue_progression":
        status = "healthy"
    else:
        status = "missing"
    statuses.append(SubsystemStatusData(
        subsystem_key="progression_freeze",
        title="Progression Freeze Check",
        status=status,
        score=score,
        severity="critical" if status == "blocked" else ("high" if status == "review" else "info"),
        route_hint="/strategies/{id}#progression-freeze",
    ))

    # 4. promotion_gates_paper
    result = subsystem_data.get("gates_paper")
    verdict = getattr(result, "promotion_verdict", None)
    gate_score = getattr(result, "gate_score", None)
    _gate_map = {
        "blocked": "blocked",
        "requires_review": "review",
        "conditional_pass": "watch",
        "pass": "healthy",
        "insufficient_evidence": "missing",
    }
    status = _gate_map.get(str(verdict), "missing") if verdict else "missing"
    statuses.append(SubsystemStatusData(
        subsystem_key="promotion_gates_paper",
        title="Promotion Gates (Paper)",
        status=status,
        score=gate_score,
        severity="high" if status in ("blocked", "review") else "info",
        route_hint="/strategies/{id}#promotion-gates",
    ))

    # 5. promotion_gates_production
    result = subsystem_data.get("gates_production")
    verdict = getattr(result, "promotion_verdict", None)
    gate_score = getattr(result, "gate_score", None)
    status = _gate_map.get(str(verdict), "missing") if verdict else "missing"
    statuses.append(SubsystemStatusData(
        subsystem_key="promotion_gates_production",
        title="Promotion Gates (Production)",
        status=status,
        score=gate_score,
        severity="high" if status in ("blocked", "review") else "info",
        route_hint="/strategies/{id}#promotion-gates",
    ))

    # 6. evidence_freshness
    result = subsystem_data.get("freshness")
    score = getattr(result, "overall_freshness_score", None)
    f_status = getattr(result, "freshness_status", None)
    if f_status in ("stale", "missing_evidence"):
        status = "review"
    elif f_status == "aging":
        status = "watch"
    elif f_status == "fresh":
        status = "healthy"
    else:
        status = _score_to_status(score)
    statuses.append(SubsystemStatusData(
        subsystem_key="evidence_freshness",
        title="Evidence Freshness",
        status=status,
        score=score,
        severity="medium" if status in ("review", "blocked") else "info",
        route_hint="/strategies/{id}#evidence-freshness",
    ))

    # 7. drift
    result = subsystem_data.get("drift")
    score = getattr(result, "drift_score", None)
    drift_status = getattr(result, "drift_status", None)
    if drift_status == "severe":
        status = "blocked"
    elif drift_status == "review":
        status = "review"
    elif drift_status == "watch":
        status = "watch"
    elif drift_status in (None, "insufficient_evidence", "no_shadow_runs"):
        status = "missing"
    else:
        status = "healthy"
    statuses.append(SubsystemStatusData(
        subsystem_key="drift",
        title="Strategy Drift",
        status=status,
        score=score,
        severity="high" if status == "blocked" else "info",
        route_hint="/strategies/{id}#drift",
    ))

    # 8. shadow_monitor
    result = subsystem_data.get("shadow")
    score = getattr(result, "shadow_stability_score", None)
    m_status = getattr(result, "monitor_status", None)
    if m_status == "severe":
        status = "blocked"
    elif m_status == "review":
        status = "review"
    elif m_status in (None, "no_shadow_runs", "insufficient_baseline"):
        status = "missing"
    else:
        status = "healthy"
    suggested_action = None
    if m_status == "no_shadow_runs":
        suggested_action = "Log a paper/live-like run to enable shadow monitoring"
    statuses.append(SubsystemStatusData(
        subsystem_key="shadow_monitor",
        title="Shadow Production Monitor",
        status=status,
        score=score,
        severity="medium" if status == "missing" else ("high" if status == "blocked" else "info"),
        suggested_action=suggested_action,
        route_hint="/strategies/{id}#shadow-monitor",
    ))

    # 9. assumption_health
    result = subsystem_data.get("assumption")  # dict
    score = result.get("overall_assumption_score") if isinstance(result, dict) else None
    a_status = result.get("overall_status") if isinstance(result, dict) else None
    if a_status == "weak":
        status = "blocked"
    elif a_status == "review":
        status = "review"
    elif a_status == "acceptable":
        status = "watch"
    elif a_status == "strong":
        status = "healthy"
    else:
        status = "missing"
    statuses.append(SubsystemStatusData(
        subsystem_key="assumption_health",
        title="Assumption Health",
        status=status,
        score=score,
        severity="high" if status in ("blocked", "review") else "info",
        route_hint="/strategies/{id}#assumption-health",
    ))

    # 10. regression_tests
    result = subsystem_data.get("regression")
    reg_status = getattr(result, "overall_status", None) if result is not None else None
    _reg_score_map: dict[str, float | None] = {
        "passed": 90.0, "warning": 65.0, "failed": 30.0, "insufficient_evidence": None
    }
    score = _reg_score_map.get(str(reg_status)) if reg_status else None
    if reg_status == "failed":
        status = "blocked"
    elif reg_status == "warning":
        status = "review"
    elif reg_status == "passed":
        status = "healthy"
    else:
        status = "missing"
    statuses.append(SubsystemStatusData(
        subsystem_key="regression_tests",
        title="Regression Tests",
        status=status,
        score=score,
        severity="critical" if status == "blocked" else ("high" if status == "review" else "info"),
        route_hint="/strategies/{id}#regression-tests",
    ))

    # 11. config_policy
    result = subsystem_data.get("policy")
    p_status = getattr(result, "overall_status", None) if result is not None else None
    _policy_score_map: dict[str, float | None] = {
        "passed": 90.0, "warning": 65.0, "failed": 30.0, "insufficient_evidence": None
    }
    score = _policy_score_map.get(str(p_status)) if p_status else None
    if p_status == "failed":
        status = "blocked"
    elif p_status == "warning":
        status = "review"
    elif p_status == "passed":
        status = "healthy"
    else:
        status = "missing"
    statuses.append(SubsystemStatusData(
        subsystem_key="config_policy",
        title="Config Policy Evaluation",
        status=status,
        score=score,
        severity="high" if status in ("blocked", "review") else "info",
        route_hint="/strategies/{id}#config-policy",
    ))

    # 12. evidence_sla
    result = subsystem_data.get("sla")
    s_status = getattr(result, "overall_status", None) if result is not None else None
    violated = getattr(result, "violated_count", 0) if result is not None else 0
    _sla_score_map: dict[str, float | None] = {
        "passed": 90.0, "warning": 65.0, "violated": 30.0, "insufficient_evidence": None
    }
    score = _sla_score_map.get(str(s_status)) if s_status else None
    if s_status == "violated":
        status = "blocked"
    elif s_status == "warning":
        status = "review"
    elif s_status == "passed":
        status = "healthy"
    else:
        status = "missing"
    statuses.append(SubsystemStatusData(
        subsystem_key="evidence_sla",
        title="Evidence SLA",
        status=status,
        score=score,
        severity="high" if status in ("blocked", "review") else "info",
        summary=f"{violated} violated SLA(s)" if violated else None,
        route_hint="/strategies/{id}#evidence-sla",
    ))

    # 13. review_cases
    cases = subsystem_data.get("review_cases") or []
    crit_count = sum(1 for c in cases if getattr(c, "severity", "") == "critical")
    high_count = sum(1 for c in cases if getattr(c, "severity", "") == "high")
    total = len(cases)
    score = max(0.0, min(100.0, 90.0 - crit_count * 35 - high_count * 20))
    if crit_count >= 2:
        status = "blocked"
    elif high_count > 0 or crit_count == 1:
        status = "review"
    elif total > 0:
        status = "watch"
    else:
        status = "healthy"
    statuses.append(SubsystemStatusData(
        subsystem_key="review_cases",
        title="Review Cases",
        status=status,
        score=score,
        severity="critical" if status == "blocked" else ("high" if status == "review" else "info"),
        summary=f"{total} open review case(s)",
        route_hint="/strategies/{id}#review-cases",
    ))

    # 14. alerts
    alerts_list = subsystem_data.get("alerts") or []
    crit_a = sum(1 for a in alerts_list if getattr(a, "severity", "") == "critical")
    high_a = sum(1 for a in alerts_list if getattr(a, "severity", "") == "high")
    score = max(0.0, min(100.0, 90.0 - crit_a * 35 - high_a * 20))
    if crit_a > 0:
        status = "blocked"
    elif high_a > 0:
        status = "review"
    elif len(alerts_list) > 0:
        status = "watch"
    else:
        status = "healthy"
    statuses.append(SubsystemStatusData(
        subsystem_key="alerts",
        title="Open Alerts",
        status=status,
        score=score,
        severity="critical" if crit_a > 0 else ("high" if high_a > 0 else "info"),
        summary=f"{len(alerts_list)} open alert(s)",
        route_hint="/strategies/{id}#alerts",
    ))

    # 15. change_impact
    result = subsystem_data.get("change_impact")
    imp_status = result.get("impact_status") if isinstance(result, dict) else getattr(result, "impact_status", None)
    imp_score = result.get("impact_score") if isinstance(result, dict) else getattr(result, "impact_score", None)
    score = float(imp_score) if imp_score is not None else None
    if imp_status in ("requires_review", "high"):
        status = "review"
    elif imp_status == "medium":
        status = "watch"
    elif imp_status in ("low", "no_change_detected"):
        status = "healthy"
    else:
        status = "missing"
    statuses.append(SubsystemStatusData(
        subsystem_key="change_impact",
        title="Change Impact",
        status=status,
        score=score,
        severity="medium" if status == "review" else "info",
        route_hint="/strategies/{id}#change-impact",
    ))

    # 16. research_audit_trail
    result = subsystem_data.get("audit_trail")
    high_imp = getattr(result, "high_importance_count", 0) if result is not None else 0
    total = getattr(result, "total_events", 0) if result is not None else 0
    score = 80.0 if total > 0 else None
    if high_imp > 0 and total > 0:
        status = "review"
    elif total > 0:
        status = "healthy"
    else:
        status = "missing"
    statuses.append(SubsystemStatusData(
        subsystem_key="research_audit_trail",
        title="Research Audit Trail",
        status=status,
        score=score,
        severity="low" if status == "review" else "info",
        summary=f"{total} audit events, {high_imp} high-importance",
        route_hint="/strategies/{id}#audit-trail",
    ))

    # 17. evidence_graph
    result = subsystem_data.get("evidence_graph")
    g_status = getattr(result, "graph_status", None) if result is not None else None
    node_count = getattr(result, "node_count", 0) if result is not None else 0
    if node_count > 5:
        score = 80.0
    elif node_count > 0:
        score = 50.0
    else:
        score = None
    _graph_status_map = {
        "complete": "healthy",
        "partial": "watch",
        "review": "review",
        "sparse": "blocked",
    }
    status = _graph_status_map.get(str(g_status), "missing") if g_status else "missing"
    statuses.append(SubsystemStatusData(
        subsystem_key="evidence_graph",
        title="Evidence Graph",
        status=status,
        score=score,
        severity="medium" if status == "blocked" else "info",
        route_hint="/strategies/{id}#evidence-graph",
    ))

    # 18. experiments
    experiments = subsystem_data.get("experiments") or []
    count = len(experiments)
    score = 80.0 if count > 0 else None
    status = "watch" if count > 0 else "missing"
    statuses.append(SubsystemStatusData(
        subsystem_key="experiments",
        title="Experiments",
        status=status,
        score=score,
        severity="info",
        summary=f"{count} active experiment(s)",
        route_hint="/strategies/{id}#experiments",
    ))

    return statuses


# ---------------------------------------------------------------------------
# Blockers builder
# ---------------------------------------------------------------------------

def _build_blockers(subsystem_statuses: list[SubsystemStatusData]) -> list[CommandCenterBlockerData]:
    _severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    blockers: list[CommandCenterBlockerData] = []

    for ss in subsystem_statuses:
        if ss.status not in ("blocked", "review"):
            continue
        severity = "critical" if ss.status == "blocked" else "high"
        required = ss.status == "blocked"
        evidence = ss.summary or ss.top_issue or f"{ss.title} requires attention"
        blocker = CommandCenterBlockerData(
            blocker_key=ss.subsystem_key,
            title=ss.title,
            category=ss.subsystem_key,
            severity=severity,
            evidence_summary=evidence,
            source_subsystem=ss.subsystem_key,
            required_before_progression=required,
            suggested_resolution=ss.suggested_action or f"Review {ss.title.lower()} and resolve issues",
        )
        blockers.append(blocker)

    blockers.sort(key=lambda b: _severity_order.get(b.severity, 99))
    return blockers[:10]


# ---------------------------------------------------------------------------
# Action queue builder
# ---------------------------------------------------------------------------

_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _build_action_queue(  # noqa: C901
    subsystem_statuses: list[SubsystemStatusData],
    freeze_data,
    freshness_data,
    regression_data,
    policy_data,
    sla_data,
) -> list[CommandCenterActionData]:
    actions: list[CommandCenterActionData] = []
    seen: set[str] = set()

    def _add(key: str, title: str, priority: str, action_type: str, reason: str,
             endpoint_hint: str | None = None, route_hint: str | None = None,
             depends_on: list | None = None) -> None:
        if key in seen:
            return
        seen.add(key)
        actions.append(CommandCenterActionData(
            action_key=key,
            title=title,
            priority=priority,
            action_type=action_type,
            reason=reason,
            endpoint_hint=endpoint_hint,
            route_hint=route_hint,
            depends_on=depends_on or [],
        ))

    ss_map = {s.subsystem_key: s for s in subsystem_statuses}

    alerts_ss = ss_map.get("alerts")
    if alerts_ss and alerts_ss.status == "blocked":
        _add("resolve_alert", "Resolve critical open alerts", "critical",
             "resolve_alert", "Critical alerts require resolution before progression")

    rc_ss = ss_map.get("review_cases")
    if rc_ss and rc_ss.status == "blocked":
        _add("review_critical_case", "Resolve critical review cases", "critical",
             "review_case", "Critical review cases block progression")
    elif rc_ss and rc_ss.status == "review":
        _add("review_high_case", "Address high-priority review cases", "high",
             "review_case", "High-priority review cases require attention")

    reg_ss = ss_map.get("regression_tests")
    if reg_ss and reg_ss.status == "blocked":
        _add("run_regression", "Run and fix regression tests", "critical",
             "run_regression", "Regression tests failed — re-run after fixing issues",
             route_hint="/strategies/{id}#regression-tests")

    policy_ss = ss_map.get("config_policy")
    if policy_ss and policy_ss.status in ("blocked", "review"):
        _add("evaluate_policy", "Re-evaluate config policies", "high",
             "evaluate_policy", "Config policy issues require resolution",
             route_hint="/strategies/{id}#config-policy")

    sla_ss = ss_map.get("evidence_sla")
    if sla_ss and sla_ss.status in ("blocked", "review"):
        _add("evaluate_sla", "Review evidence SLA violations", "high",
             "evaluate_sla", "Evidence SLA issues require review",
             route_hint="/strategies/{id}#evidence-sla")

    readiness_ss = ss_map.get("readiness")
    if readiness_ss and readiness_ss.status in ("blocked", "review"):
        _add("review_promotion_gate", "Review promotion gates before progression", "high",
             "review_promotion_gate", "Readiness issues must be resolved before stage progression",
             route_hint="/strategies/{id}#readiness")

    freshness_ss = ss_map.get("evidence_freshness")
    if freshness_ss and freshness_ss.status in ("review", "blocked"):
        _add("refresh_evidence", "Refresh stale evidence", "medium",
             "refresh_evidence", "Evidence freshness is low — update evidence artefacts",
             route_hint="/strategies/{id}#evidence-freshness")

    shadow_ss = ss_map.get("shadow_monitor")
    if shadow_ss and shadow_ss.status == "missing":
        _add("run_shadow_monitor", "Log a shadow/paper run to enable shadow monitoring", "medium",
             "run_shadow_monitor", "No shadow runs available for monitoring",
             route_hint="/strategies/{id}#shadow-monitor")

    change_ss = ss_map.get("change_impact")
    if change_ss and change_ss.status in ("review", "blocked"):
        _add("run_change_impact", "Assess change impact on downstream evidence", "medium",
             "run_change_impact", "Recent changes may affect evidence quality",
             route_hint="/strategies/{id}#change-impact")

    exp_ss = ss_map.get("experiments")
    if exp_ss and exp_ss.status == "missing":
        _add("analyze_experiment", "Create an experiment to track research progress", "low",
             "analyze_experiment", "No experiments found — consider registering one",
             route_hint="/strategies/{id}#experiments")

    actions.sort(key=lambda a: _PRIORITY_ORDER.get(a.priority, 99))
    return actions[:12]


# ---------------------------------------------------------------------------
# Scoring / status
# ---------------------------------------------------------------------------

_WEIGHTS: dict[str, float] = {
    "readiness": 0.15,
    "robustness": 0.15,
    "progression_freeze": 0.15,
    "promotion_gates_paper": 0.10,
    "evidence_freshness": 0.08,
    "drift": 0.08,
    "shadow_monitor": 0.08,
    "regression_tests": 0.04,
    "config_policy": 0.03,
    "evidence_sla": 0.03,
    "review_cases": 0.04,
    "alerts": 0.03,
    "assumption_health": 0.08,
    "change_impact": 0.03,
    "evidence_graph": 0.02,
    "research_audit_trail": 0.01,
}


def _compute_command_score(subsystem_statuses: list[SubsystemStatusData]) -> float | None:
    total_weight = 0.0
    weighted_sum = 0.0
    non_null_count = 0

    for ss in subsystem_statuses:
        weight = _WEIGHTS.get(ss.subsystem_key, 0.0)
        if weight == 0.0 or ss.score is None:
            continue
        weighted_sum += ss.score * weight
        total_weight += weight
        non_null_count += 1

    if non_null_count < 5:
        return None
    if total_weight == 0.0:
        return None
    return round(weighted_sum / total_weight, 2)


def _compute_command_status(
    score: float | None,
    subsystem_statuses: list[SubsystemStatusData],
    freeze_rec: str | None,
) -> str:
    # Hard overrides
    for ss in subsystem_statuses:
        if ss.status == "blocked":
            return "blocked"
    if freeze_rec == "freeze_progression":
        return "blocked"
    # Score-based
    if score is None:
        return "insufficient_evidence"
    if score >= 80:
        return "clear"
    if score >= 65:
        return "monitor"
    if score >= 45:
        return "review"
    return "blocked"


# ---------------------------------------------------------------------------
# Summary builders
# ---------------------------------------------------------------------------

def _build_governance_summary(subsystem_data: dict) -> GovernanceSummaryData:
    review_cases = subsystem_data.get("review_cases") or []
    open_count = len(review_cases)
    ack_count = sum(
        1 for c in review_cases
        if getattr(c, "status", "") == "acknowledged"
    )

    alerts_list = subsystem_data.get("alerts") or []
    hc_alerts = sum(
        1 for a in alerts_list
        if getattr(a, "severity", "") in ("high", "critical")
    )

    regression = subsystem_data.get("regression")
    reg_status = getattr(regression, "overall_status", None) if regression else None

    policy = subsystem_data.get("policy")
    policy_status = getattr(policy, "overall_status", None) if policy else None

    sla = subsystem_data.get("sla")
    sla_status = getattr(sla, "overall_status", None) if sla else None

    freeze = subsystem_data.get("freeze")
    freeze_rec = getattr(freeze, "recommendation", None) if freeze else None

    gates_paper = subsystem_data.get("gates_paper")
    paper_verdict = getattr(gates_paper, "promotion_verdict", None) if gates_paper else None

    gates_prod = subsystem_data.get("gates_production")
    prod_verdict = getattr(gates_prod, "promotion_verdict", None) if gates_prod else None

    return GovernanceSummaryData(
        open_review_case_count=open_count,
        acknowledged_review_case_count=ack_count,
        high_critical_alert_count=hc_alerts,
        latest_regression_status=reg_status,
        latest_policy_status=policy_status,
        latest_sla_status=sla_status,
        latest_freeze_recommendation=freeze_rec,
        promotion_gate_paper_verdict=paper_verdict,
        promotion_gate_production_verdict=prod_verdict,
    )


def _build_evidence_summary(
    db: Session,
    strategy_id: uuid.UUID,
    subsystem_data: dict,
) -> EvidenceSummaryData:
    freshness = subsystem_data.get("freshness")
    f_status = getattr(freshness, "freshness_status", None) if freshness else None
    f_score = getattr(freshness, "overall_freshness_score", None) if freshness else None
    missing_count = getattr(freshness, "missing_count", 0) if freshness else 0
    stale_count = getattr(freshness, "stale_count", 0) if freshness else 0

    evidence_graph = subsystem_data.get("evidence_graph")
    g_status = getattr(evidence_graph, "graph_status", None) if evidence_graph else None
    node_count = getattr(evidence_graph, "node_count", 0) if evidence_graph else 0

    coverage_score = f_score
    if coverage_score is None and node_count > 0:
        coverage_score = min(100.0, float(node_count) * 10)

    # Latest run
    latest_run = (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(StrategyRun.created_at.desc())
        .first()
    )
    latest_run_id = str(latest_run.id) if latest_run else None
    latest_run_label = getattr(latest_run, "run_name", None) if latest_run else None

    replay_recommended = (
        f_status in ("stale", "missing_evidence")
        or missing_count > 0
        or latest_run is None
    )

    return EvidenceSummaryData(
        freshness_status=f_status,
        coverage_score=coverage_score,
        missing_evidence_count=missing_count,
        stale_evidence_count=stale_count,
        graph_status=g_status,
        replay_pack_recommended=replay_recommended,
        latest_run_id=latest_run_id,
        latest_run_label=latest_run_label,
    )


def _build_workflow_summary(
    db: Session,
    strategy_id: uuid.UUID,
    subsystem_data: dict,
    current_stage: str,
) -> WorkflowSummaryData:
    _stage_progression = [
        "idea", "research", "backtest_review", "paper_candidate",
        "shadow_production", "production_candidate",
    ]
    try:
        idx = _stage_progression.index(current_stage)
        next_stage = _stage_progression[idx + 1] if idx + 1 < len(_stage_progression) else current_stage
    except ValueError:
        next_stage = "backtest_review"

    experiments = subsystem_data.get("experiments") or []
    active_count = sum(
        1 for e in experiments
        if getattr(e, "status", "") == "active"
    )

    audit_trail = subsystem_data.get("audit_trail")
    latest_event_at = getattr(audit_trail, "latest_event_at", None) if audit_trail else None

    return WorkflowSummaryData(
        current_stage=current_stage,
        next_recommended_stage=next_stage,
        stage_path=_stage_progression,
        active_experiment_count=active_count,
        latest_audit_event_at=latest_event_at,
    )


def _build_deterministic_summary(
    command_status: str,
    blockers: list[CommandCenterBlockerData],
    action_count: int,
    stage: str,
) -> str:
    status_label = command_status.replace("_", " ")
    parts = [f"Command status is {status_label}."]

    critical_blockers = [b for b in blockers if b.severity == "critical"]
    if critical_blockers:
        blocker_names = ", ".join(b.title.lower() for b in critical_blockers[:3])
        parts.append(f"Critical blockers: {blocker_names}.")
        parts.append(f"Resolve blockers and re-evaluate promotion gates before progressing to {stage}.")
    elif blockers:
        blocker_names = ", ".join(b.title.lower() for b in blockers[:3])
        parts.append(f"Items requiring attention: {blocker_names}.")
    else:
        parts.append("No blockers detected across monitored subsystems.")

    if action_count > 0:
        parts.append(f"{action_count} action(s) in the queue.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def get_strategy_reliability_command_center(
    db: Session,
    strategy_id: uuid.UUID,
) -> StrategyReliabilityCommandCenterData:
    """Build the Reliability Command Center for a strategy.

    Read-only.  Deterministic.  Not investment advice.
    """
    now = datetime.now(timezone.utc)

    # 1. Load strategy
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        return StrategyReliabilityCommandCenterData(
            strategy_id=str(strategy_id),
            strategy_name="unknown",
            generated_at=now,
            command_status="insufficient_evidence",
            command_score=None,
            deterministic_summary="Strategy not found.",
            subsystem_statuses=[],
            top_blockers=[],
            action_queue=[],
            governance_summary=GovernanceSummaryData(),
            evidence_summary=EvidenceSummaryData(),
            workflow_summary=WorkflowSummaryData(),
            note="This is a deterministic research governance command center. "
                 "It is not trading approval or live execution control.",
        )

    # 2. Infer current stage
    current_stage = _infer_current_stage(db, strategy_id)

    # 3. Gather subsystem data
    subsystem_data: dict = {}

    readiness_result, _ = _safe_call(compute_strategy_readiness, db, strategy_id)
    subsystem_data["readiness"] = readiness_result

    robustness_result, _ = _safe_call(compute_strategy_robustness, db, strategy_id)
    subsystem_data["robustness"] = robustness_result

    freeze_result, _ = _safe_call(compute_progression_freeze_recommendation, db, strategy_id)
    subsystem_data["freeze"] = freeze_result

    gates_paper_result, _ = _safe_call(evaluate_promotion_gates, strategy_id, "paper_candidate", db)
    subsystem_data["gates_paper"] = gates_paper_result

    gates_prod_result, _ = _safe_call(evaluate_promotion_gates, strategy_id, "production_candidate", db)
    subsystem_data["gates_production"] = gates_prod_result

    drift_result, _ = _safe_call(compute_strategy_drift, db, strategy_id)
    subsystem_data["drift"] = drift_result

    shadow_result, _ = _safe_call(compute_shadow_production_monitor, db, strategy_id)
    subsystem_data["shadow"] = shadow_result

    freshness_result, _ = _safe_call(compute_evidence_freshness, db, strategy_id)
    subsystem_data["freshness"] = freshness_result

    assumption_result, _ = _safe_call(compute_assumption_health, strategy_id, db)
    subsystem_data["assumption"] = assumption_result

    regression_list, _ = _safe_call(get_regression_test_runs, strategy_id, db, limit=1)
    regression_result = (regression_list[0] if regression_list else None)
    subsystem_data["regression"] = regression_result

    policy_list, _ = _safe_call(get_config_policy_evaluations, db, str(strategy_id), limit=1)
    policy_result = (policy_list[0] if policy_list else None)
    subsystem_data["policy"] = policy_result

    sla_list, _ = _safe_call(get_evidence_sla_evaluations, db, str(strategy_id), limit=1)
    sla_result = (sla_list[0] if sla_list else None)
    subsystem_data["sla"] = sla_result

    review_cases_result, _ = _safe_call(get_research_review_cases, db, str(strategy_id), status="open")
    subsystem_data["review_cases"] = review_cases_result or []

    # Query alerts directly — Alert.strategy_id is String(36)
    try:
        alerts_list = (
            db.query(Alert)
            .filter(
                Alert.strategy_id == str(strategy_id),
                Alert.status == "open",
            )
            .all()
        )
    except Exception:
        alerts_list = []
    subsystem_data["alerts"] = alerts_list

    experiments_result, _ = _safe_call(get_strategy_experiments, db, str(strategy_id), limit=10)
    subsystem_data["experiments"] = experiments_result or []

    evidence_graph_result, _ = _safe_call(
        build_strategy_evidence_graph,
        strategy_id,
        db,
        include_timeline=False,
        include_computed=True,
    )
    subsystem_data["evidence_graph"] = evidence_graph_result

    change_impact_result, _ = _safe_call(analyze_strategy_change_impact, db, strategy_id)
    subsystem_data["change_impact"] = change_impact_result

    audit_trail_result, _ = _safe_call(
        get_strategy_research_audit_trail,
        db,
        strategy_id,
        limit=50,
        include_context=False,
    )
    subsystem_data["audit_trail"] = audit_trail_result

    # 4. Build subsystem statuses
    subsystem_statuses = _build_subsystem_statuses(subsystem_data)

    # 5. Build blockers
    top_blockers = _build_blockers(subsystem_statuses)

    # 6. Build action queue
    action_queue = _build_action_queue(
        subsystem_statuses,
        freeze_result,
        freshness_result,
        regression_result,
        policy_result,
        sla_result,
    )

    # 7. Compute score
    command_score = _compute_command_score(subsystem_statuses)

    # 8. Compute status
    freeze_rec = getattr(freeze_result, "recommendation", None) if freeze_result else None
    command_status = _compute_command_status(command_score, subsystem_statuses, freeze_rec)

    # 9. Governance summary
    governance_summary = _build_governance_summary(subsystem_data)

    # 10. Evidence summary
    evidence_summary = _build_evidence_summary(db, strategy_id, subsystem_data)

    # 11. Workflow summary
    workflow_summary = _build_workflow_summary(db, strategy_id, subsystem_data, current_stage)

    # 12. Deterministic summary
    deterministic_summary = _build_deterministic_summary(
        command_status, top_blockers, len(action_queue), workflow_summary.next_recommended_stage
    )

    # 13. Note
    note = (
        "This is a deterministic research governance command center. "
        "It is not trading approval or live execution control."
    )

    return StrategyReliabilityCommandCenterData(
        strategy_id=str(strategy_id),
        strategy_name=strategy.name,
        generated_at=now,
        command_status=command_status,
        command_score=command_score,
        deterministic_summary=deterministic_summary,
        subsystem_statuses=subsystem_statuses,
        top_blockers=top_blockers,
        action_queue=action_queue,
        governance_summary=governance_summary,
        evidence_summary=evidence_summary,
        workflow_summary=workflow_summary,
        note=note,
    )
