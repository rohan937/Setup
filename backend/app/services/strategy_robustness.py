"""M61: Strategy Robustness Score service.

Computes a multi-dimensional robustness score for a strategy based on
logged evidence of parameter stability, cost/fill sensitivity, drift,
shadow stability, assumption health, regression results, evidence freshness,
policy/SLA compliance, and open review case pressure.

Read-only — no AuditTimelineEvent created.
Deterministic — no AI, no live market data, no investment advice.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.strategy import Strategy
from app.models.backtest_audit import BacktestAudit
from app.models.strategy_run import StrategyRun
from app.models.experiment import StrategyExperiment, StrategyExperimentAnalysis

try:
    from app.services.strategy_drift import compute_strategy_drift
except ImportError:
    compute_strategy_drift = None  # type: ignore[assignment]

try:
    from app.services.shadow_production import compute_shadow_production_monitor
except ImportError:
    compute_shadow_production_monitor = None  # type: ignore[assignment]

try:
    from app.services.assumption_health import compute_assumption_health  # returns DICT
except ImportError:
    compute_assumption_health = None  # type: ignore[assignment]

try:
    from app.services.evidence_freshness import compute_evidence_freshness
except ImportError:
    compute_evidence_freshness = None  # type: ignore[assignment]

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
    from app.services.parameter_sweep import analyze_parameter_sweep
except ImportError:
    analyze_parameter_sweep = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RobustnessDimensionData:
    dimension_key: str
    title: str
    score: float | None = None
    status: str = "missing"  # robust/stable/watch/review/fragile/missing
    evidence_count: int = 0
    fragility_signals: list = field(default_factory=list)
    positive_evidence: list = field(default_factory=list)
    review_items: list = field(default_factory=list)
    suggested_actions: list = field(default_factory=list)
    source_refs_json: dict | None = None


@dataclass
class RobustnessFragilitySignalData:
    signal_key: str
    title: str
    severity: str  # low/medium/high/critical
    evidence_summary: str
    suggested_action: str
    source_dimension: str


@dataclass
class StrategyRobustnessData:
    strategy_id: str
    strategy_name: str
    generated_at: datetime
    robustness_score: float | None
    robustness_status: str  # robust/stable/watch/review/fragile/insufficient_evidence
    robustness_verdict: str  # robust_under_logged_variation/stable_with_watch_items/requires_review/fragile_under_variation/insufficient_evidence
    verdict_label: str
    deterministic_summary: str
    dimension_scorecards: list  # list[RobustnessDimensionData]
    fragility_signals: list  # list[RobustnessFragilitySignalData]
    top_review_drivers: list  # list[str]
    suggested_actions: list  # list[str] deduplicated
    evidence_gaps: list  # list[str]
    robustness_vs_readiness_note: str


# ---------------------------------------------------------------------------
# Score → status helper
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _score_to_status(score: float | None) -> str:
    if score is None:
        return "missing"
    if score >= 85:
        return "robust"
    if score >= 75:
        return "stable"
    if score >= 60:
        return "watch"
    if score >= 40:
        return "review"
    return "fragile"


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Dimension: parameter_stability
# ---------------------------------------------------------------------------


def _dim_parameter_stability(db: Session, strategy_id: uuid.UUID) -> RobustnessDimensionData:
    dim = RobustnessDimensionData(
        dimension_key="parameter_stability",
        title="Parameter Stability",
    )

    # Find latest experiment for this strategy
    experiment = (
        db.query(StrategyExperiment)
        .filter(StrategyExperiment.strategy_id == strategy_id)
        .order_by(StrategyExperiment.created_at.desc())
        .first()
    )
    if experiment is None:
        dim.status = "missing"
        dim.suggested_actions = ["Create an experiment and run parameter sweep analysis"]
        return dim

    # Find latest sweep analysis for this experiment
    analyses = (
        db.query(StrategyExperimentAnalysis)
        .filter(StrategyExperimentAnalysis.experiment_id == experiment.id)
        .order_by(StrategyExperimentAnalysis.created_at.desc())
        .all()
    )

    sweep_analysis = None
    for a in analyses:
        rj = a.result_json or {}
        if "sweep_reliability_score" in rj:
            sweep_analysis = a
            break

    if sweep_analysis is None:
        dim.status = "missing"
        dim.suggested_actions = ["Run parameter sweep analysis for the experiment"]
        return dim

    rj = sweep_analysis.result_json or {}
    sweep_reliability_score = rj.get("sweep_reliability_score")
    fragility_signals_raw = rj.get("fragility_signals") or {}
    narrow_peak_detected = fragility_signals_raw.get("narrow_peak_detected", False)
    fragile_variant_count = fragility_signals_raw.get("fragile_variant_count", 0)
    under_instrumented_variant_count = fragility_signals_raw.get("under_instrumented_variant_count", 0)

    score = float(sweep_reliability_score) if sweep_reliability_score is not None else None

    if score is not None:
        if narrow_peak_detected:
            score = _clamp(score - 15)
            dim.fragility_signals.append(
                RobustnessFragilitySignalData(
                    signal_key="narrow_peak_detected",
                    title="Narrow Performance Peak Detected",
                    severity="high",
                    evidence_summary="Parameter sweep found a narrow peak — performance is sensitive to small parameter changes.",
                    suggested_action="Review parameter ranges and widen the stable performance region before proceeding.",
                    source_dimension="parameter_stability",
                )
            )
        score = _clamp(score - fragile_variant_count * 10)

    if fragile_variant_count > 0:
        dim.review_items.append(
            f"{fragile_variant_count} fragile parameter variant(s) detected in sweep."
        )

    if under_instrumented_variant_count > 0:
        dim.review_items.append(
            f"{under_instrumented_variant_count} parameter variant(s) are under-instrumented."
        )

    if sweep_reliability_score is not None and not narrow_peak_detected and fragile_variant_count == 0:
        dim.positive_evidence.append("Parameter sweep shows no narrow peaks and no fragile variants.")

    dim.score = score
    dim.status = _score_to_status(score)
    dim.evidence_count = 1
    return dim


# ---------------------------------------------------------------------------
# Dimension: cost_sensitivity
# ---------------------------------------------------------------------------


def _dim_cost_sensitivity(db: Session, strategy_id: uuid.UUID) -> RobustnessDimensionData:
    dim = RobustnessDimensionData(
        dimension_key="cost_sensitivity",
        title="Cost Sensitivity",
    )

    audit = (
        db.query(BacktestAudit)
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(BacktestAudit.created_at.desc())
        .first()
    )

    if audit is None:
        dim.status = "missing"
        dim.suggested_actions = ["Run a backtest with a backtest audit to assess cost sensitivity."]
        return dim

    score = 80.0
    dim.evidence_count = 1

    # M36 cost_sensitivity_sweep_json
    css = audit.cost_sensitivity_sweep_json
    if css is not None:
        # Check for most_fragile_scenario
        most_fragile = css.get("most_fragile_scenario") or {}
        trust_impact = most_fragile.get("trust_impact", "")
        if trust_impact == "high":
            score = _clamp(score - 25)
            dim.fragility_signals.append(
                RobustnessFragilitySignalData(
                    signal_key="cost_high_trust_impact",
                    title="High Cost Sensitivity Trust Impact",
                    severity="high",
                    evidence_summary=f"Most fragile cost scenario has high trust impact: {most_fragile.get('scenario_label', 'unknown')}.",
                    suggested_action="Review cost assumptions and add realistic transaction cost estimates before progressing.",
                    source_dimension="cost_sensitivity",
                )
            )
        elif trust_impact == "medium":
            score = _clamp(score - 15)
            dim.review_items.append(
                f"Cost sensitivity has medium trust impact (scenario: {most_fragile.get('scenario_label', 'unknown')})."
            )
        elif trust_impact == "low":
            dim.positive_evidence.append("Cost sensitivity scenarios show low trust impact.")

        if "transaction_cost_bps" not in css:
            score = _clamp(score - 20)
            dim.review_items.append("Cost sensitivity sweep is missing transaction_cost_bps field.")

        # cost_fragility_level at top level of css
        cost_fragility_level = css.get("cost_fragility_level", "")
        if cost_fragility_level in ("high", "severe"):
            score = _clamp(score - 20)
        elif cost_fragility_level == "medium":
            score = _clamp(score - 10)
    else:
        # Fallback: M13 fragility_summary_json
        fsj = audit.fragility_summary_json or {}
        cost_fragility_level = fsj.get("fragility_level", "")
        if cost_fragility_level in ("high", "severe"):
            score = _clamp(score - 20)
            dim.review_items.append(f"Cost fragility level is {cost_fragility_level} (legacy audit).")
        elif cost_fragility_level == "medium":
            score = _clamp(score - 10)
            dim.review_items.append("Cost fragility level is medium (legacy audit).")

    dim.score = _clamp(score)
    dim.status = _score_to_status(dim.score)
    return dim


# ---------------------------------------------------------------------------
# Dimension: fill_realism
# ---------------------------------------------------------------------------


def _dim_fill_realism(db: Session, strategy_id: uuid.UUID) -> RobustnessDimensionData:
    dim = RobustnessDimensionData(
        dimension_key="fill_realism",
        title="Fill Realism",
    )

    audit = (
        db.query(BacktestAudit)
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(BacktestAudit.created_at.desc())
        .first()
    )

    if audit is None:
        dim.status = "missing"
        dim.suggested_actions = ["Run a backtest with a backtest audit to assess fill realism."]
        return dim

    score = 80.0
    dim.evidence_count = 1

    # Determine fill_realism_level — M36: fill_sensitivity_json, fallback M13: fill_realism_json
    fill_realism_level = ""
    fs = audit.fill_sensitivity_json
    if fs is not None:
        fill_realism_level = fs.get("fill_realism_level", "")
        # Check worst_case_scenario trust_penalty_estimate
        worst_case = fs.get("worst_case_scenario") or {}
        if worst_case.get("trust_penalty_estimate", "") == "high":
            score = _clamp(score - 15)
            dim.review_items.append("Fill sensitivity worst-case scenario has high trust penalty estimate.")
    else:
        frj = audit.fill_realism_json or {}
        fill_realism_level = frj.get("fragility_level", frj.get("fill_realism_level", ""))

    if fill_realism_level in ("high_concern", "severe"):
        score = _clamp(score - 30)
        dim.fragility_signals.append(
            RobustnessFragilitySignalData(
                signal_key="fill_realism_high_concern",
                title="Fill Realism High Concern",
                severity="high",
                evidence_summary=f"Fill realism level is '{fill_realism_level}' — backtest fills may not reflect live execution.",
                suggested_action="Review fill assumptions and add realistic slippage/partial fill modeling before progressing.",
                source_dimension="fill_realism",
            )
        )
    elif fill_realism_level == "medium_concern":
        score = _clamp(score - 15)
        dim.review_items.append("Fill realism level is medium_concern — review fill assumptions.")
    elif fill_realism_level == "low_concern":
        score = _clamp(score + 5)
        dim.positive_evidence.append("Fill realism level is low_concern.")

    dim.score = _clamp(score)
    dim.status = _score_to_status(dim.score)
    return dim


# ---------------------------------------------------------------------------
# Dimension: drift_stability
# ---------------------------------------------------------------------------


def _dim_drift_stability(db: Session, strategy_id: uuid.UUID) -> RobustnessDimensionData:
    dim = RobustnessDimensionData(
        dimension_key="drift_stability",
        title="Drift Stability",
    )

    if compute_strategy_drift is None:
        dim.status = "missing"
        return dim

    try:
        result = compute_strategy_drift(strategy_id, db)
    except Exception:
        dim.status = "missing"
        dim.suggested_actions = ["Add runs at different stages to enable drift stability assessment."]
        return dim

    drift_score = getattr(result, "drift_score", None)
    drift_status = getattr(result, "drift_status", "insufficient_evidence")

    if drift_status in ("insufficient_evidence", "no_shadow_runs", "insufficient_baseline"):
        dim.status = "missing"
        dim.suggested_actions = ["Add runs at different stages to enable drift stability assessment."]
        return dim

    score = float(drift_score) if drift_score is not None else None
    dim.evidence_count = 1

    if drift_status == "severe":
        dim.fragility_signals.append(
            RobustnessFragilitySignalData(
                signal_key="severe_drift_detected",
                title="Severe Strategy Drift Detected",
                severity="critical",
                evidence_summary="Drift analysis shows severe performance divergence between stage runs.",
                suggested_action="Investigate and resolve sources of drift before progressing to the next stage.",
                source_dimension="drift_stability",
            )
        )
    elif drift_status == "moderate":
        dim.fragility_signals.append(
            RobustnessFragilitySignalData(
                signal_key="moderate_drift_detected",
                title="Moderate Strategy Drift Detected",
                severity="medium",
                evidence_summary="Drift analysis shows moderate performance divergence between stage runs.",
                suggested_action="Review drift sources and confirm they are expected before progressing.",
                source_dimension="drift_stability",
            )
        )
    elif drift_status == "review":
        dim.fragility_signals.append(
            RobustnessFragilitySignalData(
                signal_key="drift_requires_review",
                title="Drift Requires Review",
                severity="medium",
                evidence_summary="Drift analysis flagged review-level divergence.",
                suggested_action="Review highlighted drift items before progressing.",
                source_dimension="drift_stability",
            )
        )
    elif drift_status in ("stable", "watch"):
        dim.positive_evidence.append(f"Drift status is '{drift_status}' — performance is relatively consistent across stages.")

    dim.score = score
    dim.status = _score_to_status(score) if score is not None else "missing"
    # Override status for severe drift
    if drift_status == "severe" and score is not None and score < 40:
        dim.status = "fragile"
    return dim


# ---------------------------------------------------------------------------
# Dimension: shadow_stability
# ---------------------------------------------------------------------------


def _dim_shadow_stability(db: Session, strategy_id: uuid.UUID) -> RobustnessDimensionData:
    dim = RobustnessDimensionData(
        dimension_key="shadow_stability",
        title="Shadow Stability",
    )

    if compute_shadow_production_monitor is None:
        dim.status = "missing"
        return dim

    try:
        result = compute_shadow_production_monitor(strategy_id, db)
    except Exception:
        dim.status = "missing"
        dim.suggested_actions = ["Log a paper/live-like run to enable shadow stability assessment."]
        return dim

    monitor_status = getattr(result, "monitor_status", None)
    shadow_stability_score = getattr(result, "shadow_stability_score", None)

    if monitor_status in ("no_shadow_runs", None):
        dim.status = "missing"
        dim.suggested_actions = ["Log a paper/live-like run to enable shadow stability assessment."]
        return dim

    if monitor_status == "insufficient_baseline":
        dim.status = "missing"
        dim.suggested_actions = ["Add more baseline run data to enable shadow stability assessment."]
        return dim

    score = float(shadow_stability_score) if shadow_stability_score is not None else None
    dim.evidence_count = 1

    if monitor_status == "severe":
        dim.fragility_signals.append(
            RobustnessFragilitySignalData(
                signal_key="shadow_severe_divergence",
                title="Severe Shadow Divergence",
                severity="critical",
                evidence_summary="Shadow monitor shows severe divergence between paper and live-like runs.",
                suggested_action="Resolve shadow divergence before progressing to live trading consideration.",
                source_dimension="shadow_stability",
            )
        )
    elif monitor_status == "review":
        dim.fragility_signals.append(
            RobustnessFragilitySignalData(
                signal_key="shadow_review_divergence",
                title="Shadow Stability Requires Review",
                severity="medium",
                evidence_summary="Shadow monitor shows review-level divergence.",
                suggested_action="Review shadow comparison findings before progressing.",
                source_dimension="shadow_stability",
            )
        )
    elif monitor_status == "watch":
        dim.review_items.append("Shadow monitor status is 'watch' — monitor for further divergence.")
    elif monitor_status == "stable":
        dim.positive_evidence.append("Shadow monitor status is 'stable'.")

    dim.score = score
    dim.status = _score_to_status(score)
    return dim


# ---------------------------------------------------------------------------
# Dimension: assumption_stability
# ---------------------------------------------------------------------------


def _dim_assumption_stability(db: Session, strategy_id: uuid.UUID) -> RobustnessDimensionData:
    dim = RobustnessDimensionData(
        dimension_key="assumption_stability",
        title="Assumption Stability",
    )

    if compute_assumption_health is None:
        dim.status = "missing"
        return dim

    try:
        result = compute_assumption_health(strategy_id, db)
    except Exception:
        dim.status = "missing"
        dim.suggested_actions = ["Log assumption evidence to enable assumption stability assessment."]
        return dim

    if not result:
        dim.status = "missing"
        return dim

    overall_score = result.get("overall_assumption_score")
    status_val = result.get("status")
    weakening_count = result.get("weakening_change_count", 0) or 0

    score = float(overall_score) if overall_score is not None else None
    dim.evidence_count = 1

    if score is not None and weakening_count > 0:
        score = _clamp(score - weakening_count * 10)

    if status_val == "weak":
        dim.fragility_signals.append(
            RobustnessFragilitySignalData(
                signal_key="weak_assumption_health",
                title="Weak Assumption Health",
                severity="high",
                evidence_summary="Assumption health is rated 'weak' — key strategy assumptions are not well-supported by logged evidence.",
                suggested_action="Review and strengthen the weakest assumption categories before progressing.",
                source_dimension="assumption_stability",
            )
        )
    elif status_val == "review":
        dim.review_items.append("Assumption health requires review — some categories are below acceptable threshold.")
    elif status_val in ("strong", "acceptable"):
        dim.positive_evidence.append(f"Assumption health is '{status_val}'.")

    if weakening_count > 0:
        dim.review_items.append(
            f"{weakening_count} weakening assumption change(s) detected in latest config diff."
        )

    dim.score = score
    dim.status = _score_to_status(score)
    return dim


# ---------------------------------------------------------------------------
# Dimension: regression_stability
# ---------------------------------------------------------------------------


def _dim_regression_stability(db: Session, strategy_id: uuid.UUID) -> RobustnessDimensionData:
    dim = RobustnessDimensionData(
        dimension_key="regression_stability",
        title="Regression Stability",
    )

    if get_regression_test_runs is None:
        dim.status = "missing"
        return dim

    try:
        latest_runs = get_regression_test_runs(strategy_id, db, limit=1)
    except Exception:
        dim.status = "missing"
        return dim

    if not latest_runs:
        dim.status = "missing"
        dim.suggested_actions = ["Create and run regression tests to track strategy stability over time."]
        return dim

    latest = latest_runs[0]
    if getattr(latest, "overall_status", None) == "insufficient_evidence":
        dim.status = "missing"
        return dim

    status_to_score = {"passed": 90.0, "warning": 70.0, "failed": 35.0}
    overall_status = getattr(latest, "overall_status", "failed")
    score = status_to_score.get(overall_status, 35.0)

    required_failed_count = getattr(latest, "required_failed_count", 0) or 0
    score = _clamp(score - required_failed_count * 15)

    dim.evidence_count = 1

    if overall_status == "failed":
        dim.fragility_signals.append(
            RobustnessFragilitySignalData(
                signal_key="regression_tests_failed",
                title="Regression Tests Failed",
                severity="high",
                evidence_summary=f"Latest regression test run has status 'failed' ({required_failed_count} required test(s) failed).",
                suggested_action="Investigate and fix failing regression tests before progressing.",
                source_dimension="regression_stability",
            )
        )
    elif overall_status == "warning":
        dim.review_items.append("Latest regression test run has warning-level failures.")
    elif overall_status == "passed":
        dim.positive_evidence.append("Latest regression test run passed.")

    dim.score = score
    dim.status = _score_to_status(score)
    return dim


# ---------------------------------------------------------------------------
# Dimension: evidence_freshness
# ---------------------------------------------------------------------------


def _dim_evidence_freshness(db: Session, strategy_id: uuid.UUID) -> RobustnessDimensionData:
    dim = RobustnessDimensionData(
        dimension_key="evidence_freshness",
        title="Evidence Freshness",
    )

    if compute_evidence_freshness is None:
        dim.status = "missing"
        return dim

    try:
        result = compute_evidence_freshness(strategy_id, db)
    except Exception:
        dim.status = "missing"
        dim.suggested_actions = ["Log evidence to enable freshness assessment."]
        return dim

    freshness_score = getattr(result, "overall_freshness_score", None)
    freshness_status = getattr(result, "freshness_status", None)

    if freshness_status == "missing_evidence":
        dim.status = "missing"
        dim.suggested_actions = ["Log evidence items to enable freshness tracking."]
        return dim

    score = float(freshness_score) if freshness_score is not None else None
    dim.evidence_count = getattr(result, "fresh_count", 0) + getattr(result, "aging_count", 0)

    if freshness_status == "stale":
        dim.fragility_signals.append(
            RobustnessFragilitySignalData(
                signal_key="stale_evidence",
                title="Stale Evidence Detected",
                severity="medium",
                evidence_summary=f"Evidence freshness is 'stale' — {getattr(result, 'stale_count', 0)} stale evidence item(s).",
                suggested_action="Refresh stale evidence items in suggested order before progressing.",
                source_dimension="evidence_freshness",
            )
        )
    elif freshness_status == "aging":
        dim.review_items.append(
            f"Evidence freshness is 'aging' — {getattr(result, 'aging_count', 0)} aging item(s) need refresh."
        )
    elif freshness_status == "fresh":
        dim.positive_evidence.append("All evidence items are fresh.")

    dim.score = score
    dim.status = _score_to_status(score)
    return dim


# ---------------------------------------------------------------------------
# Dimension: policy_sla_compliance
# ---------------------------------------------------------------------------


def _dim_policy_sla_compliance(db: Session, strategy_id: uuid.UUID) -> RobustnessDimensionData:
    dim = RobustnessDimensionData(
        dimension_key="policy_sla_compliance",
        title="Policy & SLA Compliance",
    )

    status_to_score = {
        "passed": 90.0,
        "warning": 70.0,
        "failed": 35.0,
        "violated": 35.0,
        "insufficient_evidence": None,
    }

    policy_score: float | None = None
    sla_score: float | None = None

    if get_config_policy_evaluations is not None:
        try:
            policy_evals = get_config_policy_evaluations(db, str(strategy_id), limit=1)
            if policy_evals:
                ps = policy_evals[0].overall_status
                policy_score = status_to_score.get(ps)
                dim.evidence_count += 1
                if ps == "failed":
                    failed_count = getattr(policy_evals[0], "failed_count", 0) or 0
                    critical_failed = getattr(policy_evals[0], "critical_failed_count", 0) or 0
                    dim.fragility_signals.append(
                        RobustnessFragilitySignalData(
                            signal_key="config_policy_failed",
                            title="Config Policy Evaluation Failed",
                            severity="high" if critical_failed > 0 else "medium",
                            evidence_summary=f"Config policy evaluation has {failed_count} failed rule(s) ({critical_failed} critical).",
                            suggested_action="Resolve failing config policy rules before progressing.",
                            source_dimension="policy_sla_compliance",
                        )
                    )
                elif ps == "warning":
                    dim.review_items.append("Config policy evaluation has warning-level failures.")
                elif ps == "passed":
                    dim.positive_evidence.append("Config policy evaluation passed.")
        except Exception:
            pass

    if get_evidence_sla_evaluations is not None:
        try:
            sla_evals = get_evidence_sla_evaluations(db, str(strategy_id), limit=1)
            if sla_evals:
                ss = sla_evals[0].overall_status
                sla_score = status_to_score.get(ss)
                dim.evidence_count += 1
                if ss in ("failed", "violated"):
                    violated_count = getattr(sla_evals[0], "violated_count", 0) or 0
                    dim.fragility_signals.append(
                        RobustnessFragilitySignalData(
                            signal_key="evidence_sla_violated",
                            title="Evidence SLA Violated",
                            severity="medium",
                            evidence_summary=f"Evidence SLA evaluation has {violated_count} violation(s).",
                            suggested_action="Address SLA violations to ensure evidence is collected on schedule.",
                            source_dimension="policy_sla_compliance",
                        )
                    )
                elif ss == "warning":
                    dim.review_items.append("Evidence SLA evaluation has warning-level issues.")
                elif ss == "passed":
                    dim.positive_evidence.append("Evidence SLA evaluation passed.")
        except Exception:
            pass

    if dim.evidence_count == 0:
        dim.status = "missing"
        dim.suggested_actions = ["Configure config policies and SLA schedules to enable compliance tracking."]
        return dim

    # Combine available scores via average
    available_scores = [s for s in [policy_score, sla_score] if s is not None]
    combined_score: float | None = None
    if available_scores:
        combined_score = sum(available_scores) / len(available_scores)

    dim.score = combined_score
    dim.status = _score_to_status(combined_score)
    return dim


# ---------------------------------------------------------------------------
# Dimension: review_case_pressure
# ---------------------------------------------------------------------------


def _dim_review_case_pressure(db: Session, strategy_id: uuid.UUID) -> RobustnessDimensionData:
    dim = RobustnessDimensionData(
        dimension_key="review_case_pressure",
        title="Review Case Pressure",
    )

    if get_research_review_cases is None:
        # No open cases = good
        dim.score = 90.0
        dim.status = _score_to_status(dim.score)
        return dim

    try:
        cases = get_research_review_cases(db, str(strategy_id), status="open")
    except Exception:
        dim.score = 90.0
        dim.status = _score_to_status(dim.score)
        return dim

    if not cases:
        dim.score = 90.0
        dim.status = _score_to_status(dim.score)
        dim.positive_evidence.append("No open review cases.")
        return dim

    critical_count = sum(1 for c in cases if getattr(c, "severity", "") == "critical")
    high_count = sum(1 for c in cases if getattr(c, "severity", "") == "high")
    other_count = len(cases) - critical_count - high_count

    score = _clamp(90.0 - critical_count * 35 - high_count * 20 - other_count * 8)
    dim.evidence_count = len(cases)

    if critical_count > 0:
        dim.fragility_signals.append(
            RobustnessFragilitySignalData(
                signal_key="critical_review_cases_open",
                title=f"{critical_count} Critical Review Case(s) Open",
                severity="critical",
                evidence_summary=f"{critical_count} critical open review case(s) require immediate attention.",
                suggested_action="Resolve all critical open review cases before progressing.",
                source_dimension="review_case_pressure",
            )
        )

    if high_count > 0:
        dim.fragility_signals.append(
            RobustnessFragilitySignalData(
                signal_key="high_review_cases_open",
                title=f"{high_count} High-Severity Review Case(s) Open",
                severity="high",
                evidence_summary=f"{high_count} high-severity open review case(s) are unresolved.",
                suggested_action="Resolve high-severity review cases before progressing.",
                source_dimension="review_case_pressure",
            )
        )

    if other_count > 0:
        dim.review_items.append(f"{other_count} open review case(s) with medium or lower severity.")

    dim.score = score
    dim.status = _score_to_status(score)
    return dim


# ---------------------------------------------------------------------------
# Main compute function
# ---------------------------------------------------------------------------

DIMENSION_WEIGHTS = {
    "parameter_stability": 0.15,
    "cost_sensitivity": 0.12,
    "fill_realism": 0.12,
    "drift_stability": 0.12,
    "shadow_stability": 0.10,
    "assumption_stability": 0.12,
    "regression_stability": 0.10,
    "evidence_freshness": 0.07,
    "policy_sla_compliance": 0.05,
    "review_case_pressure": 0.05,
}


def compute_strategy_robustness(
    db: Session,
    strategy_id: uuid.UUID,
) -> StrategyRobustnessData:
    """Compute a multi-dimensional robustness score for a strategy.

    Deterministic — no AI, no live market data.
    Read-only — no AuditTimelineEvent created.
    Not investment advice.
    """
    now = datetime.now(timezone.utc)

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        return StrategyRobustnessData(
            strategy_id=str(strategy_id),
            strategy_name="Unknown",
            generated_at=now,
            robustness_score=None,
            robustness_status="insufficient_evidence",
            robustness_verdict="insufficient_evidence",
            verdict_label="Insufficient Evidence",
            deterministic_summary="Strategy not found — cannot compute robustness score.",
            dimension_scorecards=[],
            fragility_signals=[],
            top_review_drivers=[],
            suggested_actions=[],
            evidence_gaps=[],
            robustness_vs_readiness_note=(
                "Readiness checks whether the strategy can progress now. "
                "Robustness checks whether logged evidence suggests the strategy "
                "survives variation, sensitivity, and stage drift."
            ),
        )

    # Compute all dimensions (each wrapped in try/except)
    dim_fns = [
        ("parameter_stability", _dim_parameter_stability),
        ("cost_sensitivity", _dim_cost_sensitivity),
        ("fill_realism", _dim_fill_realism),
        ("drift_stability", _dim_drift_stability),
        ("shadow_stability", _dim_shadow_stability),
        ("assumption_stability", _dim_assumption_stability),
        ("regression_stability", _dim_regression_stability),
        ("evidence_freshness", _dim_evidence_freshness),
        ("policy_sla_compliance", _dim_policy_sla_compliance),
        ("review_case_pressure", _dim_review_case_pressure),
    ]

    dimension_scorecards: list[RobustnessDimensionData] = []
    for key, fn in dim_fns:
        try:
            dim = fn(db, strategy_id)
        except Exception:
            dim = RobustnessDimensionData(
                dimension_key=key,
                title=key.replace("_", " ").title(),
                status="missing",
            )
        dimension_scorecards.append(dim)

    # Weighted average
    total_weight = 0.0
    weighted_sum = 0.0
    scored_count = 0
    for dim in dimension_scorecards:
        if dim.score is not None:
            w = DIMENSION_WEIGHTS.get(dim.dimension_key, 0.0)
            weighted_sum += dim.score * w
            total_weight += w
            scored_count += 1

    overall_score: float | None = None
    if scored_count >= 5 and total_weight > 0:
        overall_score = round(weighted_sum / total_weight, 1)

    robustness_status = _score_to_status(overall_score)
    if overall_score is None:
        robustness_status = "insufficient_evidence"

    # Collect all fragility signals across dimensions
    all_signals: list[RobustnessFragilitySignalData] = []
    for dim in dimension_scorecards:
        for sig in dim.fragility_signals:
            if isinstance(sig, RobustnessFragilitySignalData):
                all_signals.append(sig)

    # Sort by severity (critical > high > medium > low)
    all_signals.sort(key=lambda s: _SEVERITY_ORDER.get(s.severity, 99))
    all_signals = all_signals[:10]

    # Determine verdict
    has_critical = any(s.severity == "critical" for s in all_signals)
    has_high = any(s.severity == "high" for s in all_signals)
    has_medium = any(s.severity == "medium" for s in all_signals)

    if overall_score is None:
        robustness_verdict = "insufficient_evidence"
    elif has_critical or robustness_status == "fragile":
        robustness_verdict = "fragile_under_variation"
    elif overall_score < 75 or has_high:
        robustness_verdict = "requires_review"
    elif overall_score >= 75 and has_medium:
        robustness_verdict = "stable_with_watch_items"
    elif overall_score >= 85 and not has_high and not has_critical:
        robustness_verdict = "robust_under_logged_variation"
    else:
        robustness_verdict = "requires_review"

    verdict_label = robustness_verdict.replace("_", " ").title()

    # Top review drivers
    top_review_drivers = [s.title for s in all_signals[:5]]

    # Suggested actions: collect from all dimensions, deduplicate, cap at 10
    seen_actions: set[str] = set()
    suggested_actions: list[str] = []
    for dim in dimension_scorecards:
        for action in dim.suggested_actions:
            if action not in seen_actions:
                seen_actions.add(action)
                suggested_actions.append(action)
                if len(suggested_actions) >= 10:
                    break
        if len(suggested_actions) >= 10:
            break

    # Evidence gaps: dimensions with status "missing"
    evidence_gaps = [
        dim.title for dim in dimension_scorecards if dim.status == "missing"
    ]

    # Deterministic summary
    missing_count = len(evidence_gaps)
    score_display = f"{overall_score:.0f}/100" if overall_score is not None else "N/A"
    main_concerns: list[str] = []
    for sig in all_signals[:2]:
        main_concerns.append(sig.title.lower())

    if overall_score is None:
        summary = (
            f"Strategy robustness score could not be computed — fewer than 5 dimensions "
            f"have scored evidence. {missing_count} dimension(s) are missing evidence."
        )
    else:
        concern_part = ""
        if main_concerns:
            concern_part = f" {' and '.join(c.capitalize() for c in main_concerns)} are the main robustness concerns."
        gaps_part = ""
        if missing_count > 0:
            gaps_part = f" {missing_count} dimension(s) are missing evidence."
        summary = (
            f"Strategy robustness {robustness_verdict.replace('_', ' ')} (score: {score_display})."
            f"{concern_part}{gaps_part}"
        )

    robustness_vs_readiness_note = (
        "Readiness checks whether the strategy can progress now. "
        "Robustness checks whether logged evidence suggests the strategy "
        "survives variation, sensitivity, and stage drift."
    )

    return StrategyRobustnessData(
        strategy_id=str(strategy.id),
        strategy_name=strategy.name,
        generated_at=now,
        robustness_score=overall_score,
        robustness_status=robustness_status,
        robustness_verdict=robustness_verdict,
        verdict_label=verdict_label,
        deterministic_summary=summary,
        dimension_scorecards=dimension_scorecards,
        fragility_signals=all_signals,
        top_review_drivers=top_review_drivers,
        suggested_actions=suggested_actions,
        evidence_gaps=evidence_gaps,
        robustness_vs_readiness_note=robustness_vs_readiness_note,
    )
