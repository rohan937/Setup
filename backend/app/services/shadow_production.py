"""Shadow production monitoring service (M50).

Compares a baseline (research/backtest) run against a shadow (paper/live) run
to assess whether the strategy is stable enough for production consideration.

Deterministic — no AI, no causal claims, no investment advice.

Language policy:
  Use: "logged", "observed", "noted", "deteriorated in logged value"
  Never: "better strategy", "more profitable", "should trade",
         "buy/sell", "alpha is stronger", "investment recommendation"
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.services.strategy_drift import (
    _run_to_summary,
    _compute_metric_drifts,
    _compute_evidence_drifts,
    _compute_assumption_drifts,
    _compute_trust_drifts,
    StrategyDriftRunSummaryData,
    MetricDriftItemData,
    EvidenceDriftItemData,
    AssumptionDriftItemData,
    TrustDriftItemData,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASELINE_RUN_TYPES = {"research", "backtest"}
SHADOW_RUN_TYPES = {"paper", "live"}

PRODUCTION_CHECK_KEYS = [
    "has_shadow_run",
    "shadow_run_has_metrics",
    "shadow_run_has_dataset_evidence",
    "shadow_run_has_signal_evidence",
    "shadow_run_has_universe_evidence",
    "shadow_run_has_assumptions",
    "shadow_run_has_audit",
    "no_high_or_critical_alerts",
    "freshness_not_stale",
    "readiness_not_blocked",
    "drift_not_severe",
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ShadowProductionCheckData:
    check_key: str
    title: str
    passed: bool
    severity: str  # info / low / medium / high
    evidence: str
    suggested_action: str | None


@dataclass
class StrategyShadowMonitorData:
    strategy_id: uuid.UUID
    strategy_name: str
    generated_at: datetime
    monitor_status: str  # stable / watch / review / severe / no_shadow_runs / insufficient_baseline
    shadow_stability_score: float | None
    baseline_run: StrategyDriftRunSummaryData | None
    shadow_run: StrategyDriftRunSummaryData | None
    metric_comparisons: list
    evidence_comparisons: list
    assumption_changes: list
    trust_comparison: list
    production_checks: list
    highlighted_findings: list[str]
    blockers: list[str]
    suggested_actions: list[str]
    deterministic_summary: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _select_runs(strategy_id, db, mode, baseline_run_id, shadow_run_id):
    """Select baseline and shadow runs based on mode.

    Returns (baseline_run, shadow_run, warnings).
    """
    from app.models.strategy_run import StrategyRun

    all_runs = (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(StrategyRun.created_at.asc())
        .all()
    )

    if mode == "selected":
        if not baseline_run_id or not shadow_run_id:
            raise ValueError("baseline_run_id and shadow_run_id required for selected mode.")
        baseline = next((r for r in all_runs if r.id == baseline_run_id), None)
        shadow = next((r for r in all_runs if r.id == shadow_run_id), None)
        if not baseline:
            raise ValueError(f"Baseline run {baseline_run_id} not found.")
        if not shadow:
            raise ValueError(f"Shadow run {shadow_run_id} not found.")
        return baseline, shadow, []

    # latest mode
    warnings: list[str] = []
    by_type: dict[str, list] = {}
    for r in all_runs:
        by_type.setdefault(r.run_type, []).append(r)

    baselines = by_type.get("backtest", []) or by_type.get("research", [])
    if not baselines:
        return None, None, ["No research or backtest run found. Log a research or backtest run as baseline."]
    baseline = baselines[-1]

    shadows = by_type.get("live", []) or by_type.get("paper", [])
    if not shadows:
        return baseline, None, ["No paper or live-like run found."]
    shadow = shadows[-1]

    return baseline, shadow, warnings


def _compute_production_checks(shadow_sum, db, strategy_id) -> list[ShadowProductionCheckData]:
    """Compute all production readiness checks."""
    checks: list[ShadowProductionCheckData] = []

    # has_shadow_run
    checks.append(ShadowProductionCheckData(
        check_key="has_shadow_run",
        title="Shadow Run Logged",
        passed=shadow_sum is not None,
        severity="high" if shadow_sum is None else "info",
        evidence=(
            "A paper or live-like run is required for shadow monitoring."
            if shadow_sum is None
            else f"{shadow_sum.run_type} run {shadow_sum.run_name} found."
        ),
        suggested_action=(
            "Log a paper or live-like run through the SDK."
            if shadow_sum is None
            else None
        ),
    ))

    if shadow_sum is None:
        return checks

    # shadow_run_has_metrics
    has_metrics = bool(
        shadow_sum.metrics_json
        and any(v is not None for v in shadow_sum.metrics_json.values())
    )
    checks.append(ShadowProductionCheckData(
        check_key="shadow_run_has_metrics",
        title="Shadow Run Has Metrics",
        passed=has_metrics,
        severity="medium" if not has_metrics else "info",
        evidence="Shadow run metrics_json present." if has_metrics else "Shadow run has no metrics.",
        suggested_action="Add metrics to the shadow run's metrics_json." if not has_metrics else None,
    ))

    # shadow_run_has_dataset_evidence
    has_ds = shadow_sum.dataset_health is not None
    checks.append(ShadowProductionCheckData(
        check_key="shadow_run_has_dataset_evidence",
        title="Shadow Run Has Dataset Evidence",
        passed=has_ds,
        severity="high" if not has_ds else "info",
        evidence=f"Dataset health: {shadow_sum.dataset_health:.0f}" if has_ds else "No linked dataset snapshot.",
        suggested_action="Link a dataset snapshot to the shadow run." if not has_ds else None,
    ))

    # shadow_run_has_signal_evidence
    has_sig = shadow_sum.signal_quality is not None
    checks.append(ShadowProductionCheckData(
        check_key="shadow_run_has_signal_evidence",
        title="Shadow Run Has Signal Evidence",
        passed=has_sig,
        severity="medium" if not has_sig else "info",
        evidence=f"Signal quality: {shadow_sum.signal_quality:.0f}" if has_sig else "No linked signal snapshot.",
        suggested_action="Link a signal snapshot to the shadow run." if not has_sig else None,
    ))

    # shadow_run_has_universe_evidence
    has_uni = shadow_sum.universe_symbol_count is not None
    checks.append(ShadowProductionCheckData(
        check_key="shadow_run_has_universe_evidence",
        title="Shadow Run Has Universe Evidence",
        passed=has_uni,
        severity="low" if not has_uni else "info",
        evidence=f"Universe: {shadow_sum.universe_symbol_count} symbols" if has_uni else "No linked universe snapshot.",
        suggested_action="Link a universe snapshot to the shadow run." if not has_uni else None,
    ))

    # shadow_run_has_assumptions
    has_asum = bool(shadow_sum.assumptions_json and len(shadow_sum.assumptions_json) > 0)
    checks.append(ShadowProductionCheckData(
        check_key="shadow_run_has_assumptions",
        title="Shadow Run Has Assumptions",
        passed=has_asum,
        severity="medium" if not has_asum else "info",
        evidence="Assumptions present." if has_asum else "No assumptions_json on shadow run.",
        suggested_action="Add explicit assumptions to the shadow run." if not has_asum else None,
    ))

    # shadow_run_has_audit
    has_audit = shadow_sum.backtest_trust is not None
    checks.append(ShadowProductionCheckData(
        check_key="shadow_run_has_audit",
        title="Shadow Run Has Backtest Audit",
        passed=has_audit,
        severity="medium" if not has_audit else "info",
        evidence=f"Trust score: {shadow_sum.backtest_trust:.0f}" if has_audit else "No backtest audit on shadow run.",
        suggested_action="Run Backtest Reality Check on the shadow run." if not has_audit else None,
    ))

    # no_high_or_critical_alerts
    from app.models.alert import Alert
    hc_alerts = (
        db.query(Alert)
        .filter(
            Alert.strategy_id == str(strategy_id),
            Alert.status.in_(["open", "acknowledged", "snoozed"]),
            Alert.severity.in_(["high", "critical"]),
        )
        .count()
    )
    no_hc = hc_alerts == 0
    checks.append(ShadowProductionCheckData(
        check_key="no_high_or_critical_alerts",
        title="No High/Critical Alerts Open",
        passed=no_hc,
        severity="high" if not no_hc else "info",
        evidence=f"{hc_alerts} high/critical alert(s) open." if not no_hc else "No high/critical alerts open.",
        suggested_action="Resolve high/critical alerts before considering production progression." if not no_hc else None,
    ))

    # freshness_not_stale
    try:
        from app.services.evidence_freshness import compute_evidence_freshness
        fresh = compute_evidence_freshness(strategy_id, db)
        not_stale = fresh.freshness_status not in ("stale", "missing_evidence")
        checks.append(ShadowProductionCheckData(
            check_key="freshness_not_stale",
            title="Evidence Not Stale",
            passed=not_stale,
            severity="medium" if not not_stale else "info",
            evidence=f"Freshness: {fresh.freshness_status}",
            suggested_action="Refresh stale evidence before shadow monitoring." if not not_stale else None,
        ))
    except Exception:
        checks.append(ShadowProductionCheckData(
            check_key="freshness_not_stale",
            title="Evidence Not Stale",
            passed=False,
            severity="low",
            evidence="Freshness unavailable.",
            suggested_action=None,
        ))

    # readiness_not_blocked
    try:
        from app.services.strategy_readiness import compute_strategy_readiness
        ready = compute_strategy_readiness(strategy_id, db)
        not_blocked = ready.readiness_verdict not in ("blocked", "under_instrumented")
        checks.append(ShadowProductionCheckData(
            check_key="readiness_not_blocked",
            title="Readiness Not Blocked",
            passed=not_blocked,
            severity=(
                "high" if ready.readiness_verdict == "blocked"
                else "medium" if ready.readiness_verdict == "under_instrumented"
                else "info"
            ),
            evidence=f"Readiness: {ready.verdict_label}",
            suggested_action=(
                "Resolve blocking readiness issues before shadow production monitoring."
                if not not_blocked
                else None
            ),
        ))
    except Exception:
        checks.append(ShadowProductionCheckData(
            check_key="readiness_not_blocked",
            title="Readiness Not Blocked",
            passed=False,
            severity="low",
            evidence="Readiness unavailable.",
            suggested_action=None,
        ))

    # drift_not_severe
    try:
        from app.services.strategy_drift import compute_strategy_drift
        drift = compute_strategy_drift(strategy_id, db, mode="latest_stage_pair")
        not_severe = drift.drift_status not in ("severe",)
        checks.append(ShadowProductionCheckData(
            check_key="drift_not_severe",
            title="Drift Not Severe",
            passed=not_severe,
            severity="high" if not not_severe else "info",
            evidence=f"Drift: {drift.drift_status}",
            suggested_action=(
                "Investigate severe drift before shadow production consideration."
                if not not_severe
                else None
            ),
        ))
    except Exception:
        checks.append(ShadowProductionCheckData(
            check_key="drift_not_severe",
            title="Drift Not Severe",
            passed=False,
            severity="low",
            evidence="Drift unavailable.",
            suggested_action=None,
        ))

    return checks


def _compute_shadow_score(
    metric_comps: list,
    ev_comps: list,
    assump_changes: list,
    prod_checks: list,
    trust_comps: list,
) -> float:
    """Compute shadow stability score (0-100)."""
    score = 100.0

    high_met = sum(1 for m in metric_comps if m.severity == "high" and m.direction == "deteriorated")
    med_met = sum(1 for m in metric_comps if m.severity == "medium" and m.direction in ("deteriorated", "unavailable"))
    score -= min(high_met * 20, 40)
    score -= min(med_met * 10, 30)

    high_ev = sum(1 for e in ev_comps if e.severity == "high")
    med_ev = sum(1 for e in ev_comps if e.severity == "medium")
    score -= min(high_ev * 20, 40)
    score -= min(med_ev * 10, 30)

    weak_a = sum(1 for a in assump_changes if a.impact_level == "weakening")
    score -= min(weak_a * 10, 30)

    for c in prod_checks:
        if not c.passed:
            if c.severity == "high":
                score -= 15
            elif c.severity == "medium":
                score -= 8
            elif c.severity == "low":
                score -= 3

    score = max(0.0, round(min(score, 100.0), 1))

    # Trust penalty
    trust_status = "stable"
    for t in trust_comps:
        if "severe" in t.explanation.lower() or t.severity == "high":
            trust_status = "severe"
        elif "review" in t.explanation.lower() and trust_status not in ("severe",):
            trust_status = "review"

    if trust_status == "severe":
        score -= 25
    elif trust_status == "review":
        score -= 15

    return max(0.0, round(score, 1))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_shadow_production_monitor(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    mode: str = "latest",
    baseline_run_id=None,
    shadow_run_id=None,
) -> StrategyShadowMonitorData:
    """Compute shadow production monitor for a strategy.

    Deterministic — no AI, no live market data.
    Read-only — no AuditTimelineEvent created.
    """
    from app.models.strategy import Strategy

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    now = datetime.now(timezone.utc)

    if mode not in ("latest", "selected"):
        raise ValueError(f"Invalid mode: {mode!r}")

    base_run, shadow_run, warnings = _select_runs(strategy_id, db, mode, baseline_run_id, shadow_run_id)

    if base_run is None:
        return StrategyShadowMonitorData(
            strategy_id=strategy_id,
            strategy_name=strategy.name,
            generated_at=now,
            monitor_status="insufficient_baseline",
            shadow_stability_score=None,
            baseline_run=None,
            shadow_run=None,
            metric_comparisons=[],
            evidence_comparisons=[],
            assumption_changes=[],
            trust_comparison=[],
            production_checks=[],
            highlighted_findings=[],
            blockers=["No research or backtest run found. Log a baseline run first."],
            suggested_actions=["Log a research or backtest run as the strategy baseline."],
            deterministic_summary=(
                f"No baseline run found for {strategy.name}. "
                "Log a research or backtest run first."
            ),
        )

    if shadow_run is None:
        prod_checks = _compute_production_checks(None, db, strategy_id)
        return StrategyShadowMonitorData(
            strategy_id=strategy_id,
            strategy_name=strategy.name,
            generated_at=now,
            monitor_status="no_shadow_runs",
            shadow_stability_score=None,
            baseline_run=_run_to_summary(base_run, db),
            shadow_run=None,
            metric_comparisons=[],
            evidence_comparisons=[],
            assumption_changes=[],
            trust_comparison=[],
            production_checks=prod_checks,
            highlighted_findings=["No paper or live-like run has been logged."],
            blockers=[],
            suggested_actions=["Log a paper or live-like run through the SDK or API to enable shadow monitoring."],
            deterministic_summary=(
                f"No shadow run found for {strategy.name}. "
                "Log a paper or live-like run to enable shadow production monitoring."
            ),
        )

    base_sum = _run_to_summary(base_run, db)
    shadow_sum = _run_to_summary(shadow_run, db)

    metric_comps = _compute_metric_drifts(base_sum, shadow_sum)
    ev_comps = _compute_evidence_drifts(base_sum, shadow_sum)
    assump_changes = _compute_assumption_drifts(base_sum, shadow_sum)
    trust_comps = _compute_trust_drifts(base_sum, shadow_sum)
    prod_checks = _compute_production_checks(shadow_sum, db, strategy_id)

    score = _compute_shadow_score(metric_comps, ev_comps, assump_changes, prod_checks, trust_comps)

    if score >= 85:
        status = "stable"
    elif score >= 70:
        status = "watch"
    elif score >= 50:
        status = "review"
    else:
        status = "severe"

    # Build highlighted findings
    highlighted: list[str] = []
    severity_order = {"high": 0, "medium": 1, "low": 2, "none": 3}
    for m in sorted(metric_comps, key=lambda x: severity_order.get(x.severity, 3)):
        if m.severity in ("high", "medium") and m.direction in ("deteriorated", "unavailable"):
            highlighted.append(
                f"Metric: {m.metric} {m.baseline_value} → {m.comparison_value} ({m.direction})"
            )
    for e in ev_comps:
        if e.severity in ("high", "medium"):
            highlighted.append(f"Evidence: {e.explanation}")
    highlighted = highlighted[:5]

    all_actions = list(
        dict.fromkeys(
            c.suggested_action
            for c in prod_checks
            if not c.passed and c.suggested_action
        )
    )[:6]

    all_blockers = (
        [m.direction[:80] for m in metric_comps if m.severity == "high" and m.direction == "deteriorated"]
        + [c.evidence for c in prod_checks if not c.passed and c.severity == "high"]
    )
    all_blockers = list(dict.fromkeys(all_blockers))[:5]

    # Build deterministic summary
    summary_parts = [
        f"{base_run.run_type.title()} and {shadow_run.run_type.title()} runs show "
        f"{status}-level shadow stability (score: {score:.0f}/100)."
    ]
    h_met = sum(1 for m in metric_comps if m.severity == "high")
    h_ev = sum(1 for e in ev_comps if e.severity == "high")
    if h_met:
        summary_parts.append(f"{h_met} high-severity metric drift(s).")
    if h_ev:
        summary_parts.append(f"{h_ev} high-severity evidence deterioration(s).")
    if warnings:
        summary_parts.extend(warnings[:1])
    summary_parts.append(
        "Deterministic comparison of logged evidence. Not a trading recommendation."
    )

    return StrategyShadowMonitorData(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        generated_at=now,
        monitor_status=status,
        shadow_stability_score=score,
        baseline_run=base_sum,
        shadow_run=shadow_sum,
        metric_comparisons=metric_comps,
        evidence_comparisons=ev_comps,
        assumption_changes=assump_changes,
        trust_comparison=trust_comps,
        production_checks=prod_checks,
        highlighted_findings=highlighted,
        blockers=all_blockers,
        suggested_actions=all_actions,
        deterministic_summary=" ".join(summary_parts),
    )
