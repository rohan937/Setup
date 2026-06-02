"""Strategy Readiness service (M49).

Computes a multi-dimensional readiness scorecard for a strategy.
Deterministic — no AI, no live market data, no external calls.
Read-only — no AuditTimelineEvent created.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

WEIGHTS: dict[str, float] = {
    "strategy_health": 0.15,
    "evidence_coverage": 0.15,
    "evidence_freshness": 0.10,
    "backtest_trust": 0.20,
    "assumption_health": 0.15,
    "drift_stability": 0.10,
    "alert_state": 0.10,
    "run_evidence": 0.05,
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class StrategyReadinessDimensionData:
    dimension_key: str
    title: str
    score: float | None
    status: str  # ready / watch / review / blocked / missing
    evidence_summary: str
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)


@dataclass
class StrategyProgressionPathData:
    current_stage: str  # no_runs / research / backtest / paper / live_like
    next_recommended_stage: str  # add_evidence / backtest_review / paper_trading_consideration / continue_monitoring / blocked_until_review
    required_before_next_stage: list[str] = field(default_factory=list)


@dataclass
class StrategyReadinessData:
    strategy_id: uuid.UUID
    strategy_name: str
    generated_at: datetime
    readiness_score: float | None
    readiness_verdict: str
    verdict_label: str
    verdict_summary: str
    dimension_scorecards: list
    blockers: list[str]
    review_items: list[str]
    suggested_next_actions: list[str]
    progression_path: StrategyProgressionPathData
    deterministic_summary: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def _dim_status_from_score(score, t_ready: float = 85, t_watch: float = 70, t_review: float = 50) -> str:
    if score is None:
        return "missing"
    if score >= t_ready:
        return "ready"
    elif score >= t_watch:
        return "watch"
    elif score >= t_review:
        return "review"
    else:
        return "blocked"


# ---------------------------------------------------------------------------
# Per-dimension functions
# ---------------------------------------------------------------------------


def _dim_strategy_health(strategy_id: uuid.UUID, db: Session) -> StrategyReadinessDimensionData:
    from app.services.strategy_health import compute_strategy_health
    try:
        h = compute_strategy_health(strategy_id, db)
        score = h.health_score
        status = (
            "blocked" if h.health_status == "critical"
            else ("review" if h.health_status in ("review", "watch")
                  else ("ready" if h.health_status == "healthy" else "missing"))
        )
        blockers = ["Strategy health is critical. Resolve before progression."] if h.health_status == "critical" else []
        warnings = [h.primary_concern] if h.health_status in ("review", "watch") and h.primary_concern else []
        actions = h.suggested_checks[:2] if hasattr(h, "suggested_checks") else []
        summary = (
            f"{h.health_status} health (score: {score:.0f}/100)" if score
            else f"{h.health_status}"
        )
        return StrategyReadinessDimensionData(
            "strategy_health", "Strategy Health", score, status, summary, blockers, warnings, actions
        )
    except Exception:
        return StrategyReadinessDimensionData(
            "strategy_health", "Strategy Health", None, "missing", "Health unavailable.", [], [],
            ["Compute strategy health evidence."]
        )


def _dim_evidence_coverage(strategy_id: uuid.UUID, db: Session) -> StrategyReadinessDimensionData:
    from app.models.strategy import Strategy
    from app.services.evidence_coverage import _compute_row
    try:
        strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
        cov = _compute_row(strategy, db)
        score = cov.evidence_coverage_score
        status = _dim_status_from_score(score, 80, 65, 50)
        blockers = [f"Evidence coverage critically low ({score:.0f}/100)."] if score < 40 else []
        warnings = (
            [f"{cov.missing_count} evidence cell(s) missing."]
            if cov.missing_count > 0 and status in ("review", "watch")
            else []
        )
        actions = cov.suggested_next_steps[:2] if cov.missing_count > 0 else []
        summary = f"{score:.0f}/100 ({cov.complete_count} complete, {cov.missing_count} missing)"
        return StrategyReadinessDimensionData(
            "evidence_coverage", "Evidence Coverage", score, status, summary, blockers, warnings, actions
        )
    except Exception:
        return StrategyReadinessDimensionData(
            "evidence_coverage", "Evidence Coverage", None, "missing", "Coverage unavailable.", [], [],
            ["Log evidence to compute coverage."]
        )


def _dim_evidence_freshness(strategy_id: uuid.UUID, db: Session) -> StrategyReadinessDimensionData:
    from app.services.evidence_freshness import compute_evidence_freshness
    try:
        f = compute_evidence_freshness(strategy_id, db)
        score = f.overall_freshness_score
        status = (
            "missing" if f.freshness_status == "missing_evidence"
            else _dim_status_from_score(score or 0, 85, 65, 50)
        )
        stale_items = [i.label for i in f.evidence_items if i.status == "stale"]
        blockers = []
        warnings = [f"Stale: {', '.join(stale_items[:3])}."] if stale_items else []
        actions = f.suggested_refresh_order[:2]
        summary = (
            f"{f.freshness_status} ({f.fresh_count} fresh, {f.stale_count} stale, {f.missing_count} missing)"
        )
        return StrategyReadinessDimensionData(
            "evidence_freshness", "Evidence Freshness", score, status, summary, blockers, warnings, actions
        )
    except Exception:
        return StrategyReadinessDimensionData(
            "evidence_freshness", "Evidence Freshness", None, "missing", "Freshness unavailable.", [], [], []
        )


def _dim_backtest_trust(strategy_id: uuid.UUID, db: Session) -> StrategyReadinessDimensionData:
    from app.models.backtest_audit import BacktestAudit
    from app.models.strategy_run import StrategyRun
    try:
        latest_audit = (
            db.query(BacktestAudit)
            .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
            .filter(StrategyRun.strategy_id == strategy_id)
            .order_by(BacktestAudit.created_at.desc())
            .first()
        )
        if not latest_audit:
            return StrategyReadinessDimensionData(
                "backtest_trust", "Backtest Trust", None, "missing",
                "No backtest audit found.",
                ["Run Backtest Reality Check."], [],
                ["Run Backtest Reality Check before considering progression."]
            )
        score = float(latest_audit.trust_score)
        status = (
            "blocked" if score < 40
            else ("review" if score < 65
                  else ("watch" if score < 80 else "ready"))
        )
        blockers = [f"Backtest trust score is {score:.0f}/100 — critically low."] if score < 40 else []
        warnings = (
            [f"Backtest trust is {score:.0f}/100 ({latest_audit.overall_status})."]
            if score < 75 else []
        )
        actions = ["Rerun Backtest Reality Check after updating assumptions."] if score < 65 else []
        fragility_note = ""
        if latest_audit.cost_sensitivity_sweep_json:
            frag = latest_audit.cost_sensitivity_sweep_json.get("most_fragile_scenario")
            if frag and "5x" in str(frag):
                fragility_note = f" Cost fragility: {frag}."
        summary = f"{score:.0f}/100 ({latest_audit.overall_status}){fragility_note}"
        return StrategyReadinessDimensionData(
            "backtest_trust", "Backtest Trust", score, status, summary, blockers, warnings, actions
        )
    except Exception:
        return StrategyReadinessDimensionData(
            "backtest_trust", "Backtest Trust", None, "missing",
            "Backtest audit unavailable.",
            ["Run Backtest Reality Check."], [],
            ["Run Backtest Reality Check."]
        )


def _dim_assumption_health(strategy_id: uuid.UUID, db: Session) -> StrategyReadinessDimensionData:
    from app.services.assumption_health import compute_assumption_health
    try:
        ah = compute_assumption_health(strategy_id, db)
        score = _safe_float(ah.get("overall_assumption_score"))
        ah_status = ah.get("status", "missing_evidence")
        status = (
            "blocked" if ah_status == "weak"
            else ("review" if ah_status == "review"
                  else ("watch" if ah_status == "watch"
                        else ("ready" if ah_status in ("acceptable", "strong") else "missing")))
        )
        w_count = ah.get("weakening_change_count", 0)
        blockers = ["Assumption health is weak."] if ah_status == "weak" else []
        warnings = [f"{w_count} weakening assumption change(s)."] if w_count > 0 else []
        checks = (ah.get("suggested_checks") or [])[:2]
        summary = (
            f"{ah_status} assumption health"
            + (f", {w_count} weakening changes" if w_count > 0 else "")
        )
        return StrategyReadinessDimensionData(
            "assumption_health", "Assumption Health", score, status, summary, blockers, warnings, checks
        )
    except Exception:
        return StrategyReadinessDimensionData(
            "assumption_health", "Assumption Health", None, "missing", "Assumption health unavailable.", [], [], []
        )


def _dim_drift_stability(strategy_id: uuid.UUID, db: Session) -> StrategyReadinessDimensionData:
    from app.services.strategy_drift import compute_strategy_drift
    try:
        d = compute_strategy_drift(strategy_id, db, mode="latest_stage_pair")
        if d.drift_status == "insufficient_evidence":
            return StrategyReadinessDimensionData(
                "drift_stability", "Drift Stability", None, "missing",
                "Insufficient runs for drift analysis.", [],
                ["Need 2+ runs to assess drift."],
                ["Log multiple run stages to enable drift analysis."]
            )
        score = d.drift_score
        status = (
            "blocked" if d.drift_status == "severe"
            else ("review" if d.drift_status == "review"
                  else ("watch" if d.drift_status == "watch" else "ready"))
        )
        blockers = ["Drift is severe — metrics diverged significantly between stages."] if d.drift_status == "severe" else []
        warnings = d.highlighted_drifts[:2]
        actions = d.suggested_checks[:2]
        summary = (
            f"Drift: {d.drift_status} (score {score:.0f}/100)" if score
            else f"Drift: {d.drift_status}"
        )
        return StrategyReadinessDimensionData(
            "drift_stability", "Drift Stability", score, status, summary, blockers, warnings, actions
        )
    except Exception:
        return StrategyReadinessDimensionData(
            "drift_stability", "Drift Stability", None, "missing", "Drift analysis unavailable.", [], [], []
        )


def _dim_alert_state(strategy_id: uuid.UUID, db: Session) -> StrategyReadinessDimensionData:
    from app.models.alert import Alert
    try:
        open_alerts = (
            db.query(Alert)
            .filter(
                Alert.strategy_id == str(strategy_id),
                Alert.status.in_(["open", "acknowledged", "snoozed"]),
            )
            .all()
        )
        open_count = len(open_alerts)
        crit_count = sum(1 for a in open_alerts if a.severity == "critical")
        high_count = sum(1 for a in open_alerts if a.severity == "high")
        if crit_count > 0:
            score = 20
            status = "blocked"
        elif high_count > 0:
            score = 45
            status = "review"
        elif open_count > 0:
            score = 75
            status = "watch"
        else:
            score = 100
            status = "ready"
        blockers = [f"{crit_count} critical alert(s) open."] if crit_count > 0 else []
        warnings = (
            [f"{high_count} high-severity alert(s) open."]
            if high_count > 0 and not crit_count
            else ([f"{open_count} alert(s) open."] if open_count > 0 else [])
        )
        actions = (
            ["Resolve open critical alerts."] if crit_count > 0
            else (["Review and resolve high-severity alerts."] if high_count > 0 else [])
        )
        summary = (
            f"{open_count} open alert(s)"
            + (f", {crit_count} critical" if crit_count else "")
            + (f", {high_count} high" if high_count else "")
        )
        return StrategyReadinessDimensionData(
            "alert_state", "Alert State", float(score), status, summary, blockers, warnings, actions
        )
    except Exception:
        return StrategyReadinessDimensionData(
            "alert_state", "Alert State", None, "missing", "Alert state unavailable.", [], [], []
        )


def _dim_run_evidence(strategy_id: uuid.UUID, db: Session) -> StrategyReadinessDimensionData:
    from app.models.strategy_run import StrategyRun
    from app.services.strategy_run_history import get_strategy_run_history
    try:
        run_hist, summary = get_strategy_run_history(strategy_id, db, limit=5)
        if summary.total_runs == 0:
            return StrategyReadinessDimensionData(
                "run_evidence", "Run Evidence", 0.0, "missing",
                "No strategy runs logged.",
                ["Log at least one strategy run."], [],
                ["Log a research or backtest run."]
            )
        has_backtest = (
            summary.backtest_run_count > 0
            if hasattr(summary, "backtest_run_count")
            else any(r.run_type == "backtest" for r in run_hist)
        )
        has_paper = any(r.run_type == "paper" for r in run_hist)
        strong_count = summary.strong_count
        score = 40.0
        if has_backtest:
            score += 30
        if strong_count > 0:
            score += 20
        if has_paper:
            score += 10
        score = min(100.0, score)
        status = _dim_status_from_score(score, 80, 60, 40)
        blockers = ["No backtest run logged."] if not has_backtest and summary.total_runs > 0 else []
        warnings = [f"{summary.weak_count} weak run(s) detected."] if summary.weak_count > 0 else []
        actions = ["Log a backtest run."] if not has_backtest else []
        run_summary = (
            f"{summary.total_runs} run(s): {strong_count} strong, "
            f"{summary.review_count} review, {summary.weak_count} weak"
        )
        return StrategyReadinessDimensionData(
            "run_evidence", "Run Evidence", score, status, run_summary, blockers, warnings, actions
        )
    except Exception:
        return StrategyReadinessDimensionData(
            "run_evidence", "Run Evidence", None, "missing", "Run evidence unavailable.", [], [],
            ["Log strategy runs to enable run evidence analysis."]
        )


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------


def compute_strategy_readiness(strategy_id: uuid.UUID, db: Session) -> StrategyReadinessData:
    """Compute multi-dimensional readiness scorecard for a strategy."""
    from app.models.strategy import Strategy
    from app.models.strategy_run import StrategyRun

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    now = datetime.now(timezone.utc)

    # Compute all dimensions
    dims = [
        _dim_strategy_health(strategy_id, db),
        _dim_evidence_coverage(strategy_id, db),
        _dim_evidence_freshness(strategy_id, db),
        _dim_backtest_trust(strategy_id, db),
        _dim_assumption_health(strategy_id, db),
        _dim_drift_stability(strategy_id, db),
        _dim_alert_state(strategy_id, db),
        _dim_run_evidence(strategy_id, db),
    ]

    # Overall weighted score
    scored = [
        (d, WEIGHTS[d.dimension_key])
        for d in dims
        if d.score is not None and WEIGHTS.get(d.dimension_key, 0) > 0
    ]
    if len(scored) < 4:
        overall_score = None
    else:
        total_w = sum(w for _, w in scored)
        overall_score = round(sum(d.score * w for d, w in scored) / total_w, 1)

    # Progression path — determine current stage
    all_runs = db.query(StrategyRun).filter(StrategyRun.strategy_id == strategy_id).all()
    run_types = set(r.run_type for r in all_runs)
    if not all_runs:
        current_stage = "no_runs"
    elif "live" in run_types:
        current_stage = "live_like"
    elif "paper" in run_types:
        current_stage = "paper"
    elif "backtest" in run_types:
        current_stage = "backtest"
    else:
        current_stage = "research"

    # Aggregate blockers, warnings, actions
    all_blockers = list(dict.fromkeys(b for d in dims for b in d.blockers))
    all_warnings = list(dict.fromkeys(w for d in dims for w in d.warnings))
    all_actions = list(dict.fromkeys(a for d in dims for a in d.suggested_actions))[:8]

    has_critical_alert = any(d.dimension_key == "alert_state" and d.status == "blocked" for d in dims)
    bt_trust_dim = next((d for d in dims if d.dimension_key == "backtest_trust"), None)
    bt_trust_blocked = bt_trust_dim and bt_trust_dim.status == "blocked"
    bt_trust_missing = bt_trust_dim and bt_trust_dim.status == "missing"
    drift_dim = next((d for d in dims if d.dimension_key == "drift_stability"), None)
    drift_severe = drift_dim and drift_dim.status == "blocked"
    ah_dim = next((d for d in dims if d.dimension_key == "assumption_health"), None)
    ah_weak = ah_dim and ah_dim.status == "blocked"

    cov_dim = next((d for d in dims if d.dimension_key == "evidence_coverage"), None)
    cov_score = cov_dim.score if cov_dim else None
    fresh_dim = next((d for d in dims if d.dimension_key == "evidence_freshness"), None)
    fresh_status = fresh_dim.status if fresh_dim else "missing"

    # Verdict
    if overall_score is None or current_stage == "no_runs":
        verdict = "under_instrumented"
    elif has_critical_alert or bt_trust_blocked or drift_severe or ah_weak:
        verdict = "blocked"
    elif (
        overall_score < 75
        or any(
            d.status in ("review", "blocked")
            for d in dims
            if d.dimension_key in ("strategy_health", "backtest_trust", "alert_state", "assumption_health")
        )
    ):
        verdict = "requires_review_before_progression"
    elif (
        overall_score >= 85
        and bt_trust_dim and (bt_trust_dim.score or 0) >= 75
        and not has_critical_alert
        and (cov_score or 0) >= 80
        and fresh_status in ("ready", "watch")
    ):
        verdict = "ready_for_paper_trading_consideration"
    elif overall_score >= 75 and not bt_trust_missing and (cov_score or 0) >= 70:
        verdict = "ready_for_backtest_review"
    else:
        verdict = "requires_review_before_progression"

    VERDICT_LABELS = {
        "ready_for_backtest_review": "Ready for Backtest Review",
        "ready_for_paper_trading_consideration": "Ready for Paper Trading Consideration",
        "requires_review_before_progression": "Requires Review Before Progression",
        "under_instrumented": "Under-Instrumented",
        "blocked": "Blocked",
    }
    verdict_label = VERDICT_LABELS.get(verdict, verdict)

    # Next recommended stage
    required_before_next: list[str] = []
    if verdict == "blocked":
        next_stage = "blocked_until_review"
        required_before_next = all_blockers[:3]
    elif verdict == "under_instrumented":
        next_stage = "add_evidence"
        required_before_next = ["Log strategy runs and evidence snapshots."]
    elif verdict == "ready_for_paper_trading_consideration":
        next_stage = "paper_trading_consideration"
    elif verdict == "ready_for_backtest_review":
        next_stage = "backtest_review"
        required_before_next = [w for w in all_warnings[:2] if w]
    else:
        next_stage = (
            "backtest_review"
            if current_stage in ("research", "backtest")
            else "continue_monitoring"
        )
        required_before_next = all_blockers[:2] + all_warnings[:1]

    progression_path = StrategyProgressionPathData(
        current_stage=current_stage,
        next_recommended_stage=next_stage,
        required_before_next_stage=required_before_next[:4],
    )

    # Verdict summary
    verdict_summary = {
        "ready_for_paper_trading_consideration": (
            f"{strategy.name} has strong evidence quality and is ready for paper trading consideration."
        ),
        "ready_for_backtest_review": (
            f"{strategy.name} has sufficient evidence for backtest review."
        ),
        "requires_review_before_progression": (
            f"{strategy.name} requires review before advancing to the next research stage."
        ),
        "under_instrumented": (
            f"{strategy.name} lacks sufficient evidence for readiness assessment."
        ),
        "blocked": (
            f"{strategy.name} is blocked by critical issues that must be resolved first."
        ),
    }.get(verdict, "")

    summary_parts = [f"Strategy readiness for {strategy.name}: {verdict_label}."]
    if all_blockers:
        summary_parts.append(f"Blocking issue: {all_blockers[0]}")
    if overall_score is not None:
        summary_parts.append(f"Readiness score: {overall_score:.0f}/100.")
    summary_parts.append("This is a deterministic evidence summary, not a trading recommendation.")

    return StrategyReadinessData(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        generated_at=now,
        readiness_score=overall_score,
        readiness_verdict=verdict,
        verdict_label=verdict_label,
        verdict_summary=verdict_summary,
        dimension_scorecards=dims,
        blockers=all_blockers,
        review_items=all_warnings,
        suggested_next_actions=all_actions,
        progression_path=progression_path,
        deterministic_summary=" ".join(summary_parts),
    )
