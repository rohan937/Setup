"""Strategy Sandbox / What-If service (M98).

A deterministic, READ-ONLY "what-if" engine that estimates how a strategy's
research reliability signals would change under a hypothetical scenario
(higher costs, worse drawdown, stale signals, evidence verification failures,
paper drift, etc.).

Design notes
------------
* READ-ONLY: this module never calls db.add / db.commit / db.flush. It only
  issues read queries and calls other read-only services.
* The projected backtest reality is computed by feeding an *in-memory shim
  run* (``_ShimRun`` — never an ORM object, never added to a session) into the
  PURE ``run_backtest_audit`` function from ``backtest_reality``. No new
  backtest is ever executed and nothing is persisted.
* Deterministic: no AI, no live market data, no randomness. The same inputs
  always produce the same output.

Language policy: this is research reliability estimation, not trading advice.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.services.backtest_reality import run_backtest_audit
from app.services.backtest_reality_score import (
    compute_backtest_reality_check,
    get_latest_backtest_run,
)
from app.services.promotion_gates import (
    VALID_TARGET_STAGES,
    evaluate_promotion_gates,
)
from app.services.strategy_readiness import compute_strategy_readiness


DISCLAIMER = (
    "What-if sandbox estimates research reliability impact. "
    "It is not a trading recommendation or a re-backtest."
)


# ---------------------------------------------------------------------------
# Shim run (in-memory only — NEVER an ORM model, NEVER added to a session)
# ---------------------------------------------------------------------------


class _ShimRun:
    """Plain in-memory stand-in for a StrategyRun, used only to feed the PURE
    ``run_backtest_audit`` function. It is never persisted."""

    __slots__ = (
        "params_json",
        "assumptions_json",
        "metrics_json",
        "run_type",
        "dataset_snapshot_id",
        "universe_snapshot_id",
    )

    def __init__(
        self,
        params_json: dict | None,
        assumptions_json: dict | None,
        metrics_json: dict | None,
        run_type: str | None,
        dataset_snapshot_id=None,
        universe_snapshot_id=None,
    ) -> None:
        self.params_json = params_json
        self.assumptions_json = assumptions_json
        self.metrics_json = metrics_json
        self.run_type = run_type
        # The PURE audit reads dataset_snapshot_id for improvement checks;
        # mirror the source run's linkage so the projection is faithful.
        self.dataset_snapshot_id = dataset_snapshot_id
        self.universe_snapshot_id = universe_snapshot_id


# ---------------------------------------------------------------------------
# Scenario presets
# ---------------------------------------------------------------------------

SCENARIO_PRESETS: list[dict] = [
    {
        "key": "higher_costs",
        "name": "Higher transaction costs",
        "description": "Stress the strategy with 15 bps transaction costs.",
        "assumption_overrides": {"transaction_cost_bps": 15},
        "metric_overrides": {},
        "evidence_overrides": {},
        "target_stage": "paper_candidate",
    },
    {
        "key": "higher_slippage",
        "name": "Higher slippage",
        "description": "Stress execution realism with 12 bps slippage.",
        "assumption_overrides": {"slippage_bps": 12},
        "metric_overrides": {},
        "evidence_overrides": {},
        "target_stage": "paper_candidate",
    },
    {
        "key": "turnover_stress",
        "name": "Turnover stress",
        "description": (
            "Double the current turnover (1.6x fallback) and raise the trade "
            "count to test cost sensitivity."
        ),
        "assumption_overrides": {},
        # turnover/trade_count are resolved relative to the current run at
        # simulation time; see _resolve_turnover_stress_overrides.
        "metric_overrides": {"__turnover_stress__": True},
        "evidence_overrides": {},
        "target_stage": "paper_candidate",
    },
    {
        "key": "worse_drawdown",
        "name": "Worse drawdown",
        "description": "Stress risk with a -25% maximum drawdown.",
        "assumption_overrides": {},
        "metric_overrides": {"max_drawdown": -0.25},
        "evidence_overrides": {},
        "target_stage": "paper_candidate",
    },
    {
        "key": "signal_stale",
        "name": "Stale signal evidence",
        "description": "Model the impact of a stale signal snapshot.",
        "assumption_overrides": {},
        "metric_overrides": {},
        "evidence_overrides": {"signal_stale": True},
        "target_stage": "paper_candidate",
    },
    {
        "key": "evidence_verification_failure",
        "name": "Evidence verification failure",
        "description": "Model a failed evidence verification chain.",
        "assumption_overrides": {},
        "metric_overrides": {},
        "evidence_overrides": {"evidence_verification_failed": True},
        "target_stage": "paper_candidate",
    },
    {
        "key": "paper_drift_stress",
        "name": "Paper/backtest drift stress",
        "description": "Model high drift between paper and backtest runs.",
        "assumption_overrides": {},
        "metric_overrides": {},
        "evidence_overrides": {"paper_drift_high": True},
        "target_stage": "production_candidate",
    },
    {
        "key": "production_readiness_stress",
        "name": "Production readiness stress",
        "description": (
            "Combine higher costs, a worse drawdown, and a missing reliability "
            "report to stress production readiness."
        ),
        "assumption_overrides": {"transaction_cost_bps": 15},
        "metric_overrides": {"max_drawdown": -0.25},
        "evidence_overrides": {"report_missing": True},
        "target_stage": "production_candidate",
    },
]


def get_scenario_presets() -> list[dict]:
    """Return the catalog of built-in what-if scenario presets."""
    return SCENARIO_PRESETS


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SandboxScores:
    reliability_score: float | None
    backtest_reality_score: float | None
    readiness_score: float | None
    promotion_verdict: str  # ready / review / blocked


@dataclass
class SandboxDelta:
    key: str
    label: str
    current_value: object
    projected_value: object
    impact: float  # estimated points (negative = worse)
    explanation: str


@dataclass
class SandboxData:
    strategy_id: uuid.UUID
    strategy_name: str
    scenario_name: str
    target_stage: str
    current: SandboxScores
    projected: SandboxScores
    deltas: list[SandboxDelta]
    new_blockers: list[str]
    resolved_blockers: list[str]
    warnings: list[str]
    suggested_actions: list[str]
    generated_at: datetime
    disclaimer: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _safe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _normalize_target_stage(target_stage: str | None) -> str:
    """Normalize a target stage label, mapping shadow -> shadow_production and
    defaulting to paper_candidate."""
    if not target_stage:
        return "paper_candidate"
    stage = str(target_stage).strip().lower()
    if stage == "shadow":
        return "shadow_production"
    if stage in VALID_TARGET_STAGES:
        return stage
    return "paper_candidate"


def _map_promotion_verdict(verdict: str) -> str:
    """Map a promotion-gate verdict to the sandbox's ready/review/blocked scale."""
    if verdict in ("pass", "conditional_pass"):
        return "ready"
    if verdict in ("blocked", "insufficient_evidence"):
        return "blocked"
    return "review"


def _current_reliability_score(strategy_id: uuid.UUID, db: Session) -> float | None:
    """Latest persisted StrategyReliabilityScore.overall_score, or None."""
    try:
        from app.models.strategy_reliability_score import StrategyReliabilityScore

        latest = (
            db.query(StrategyReliabilityScore)
            .filter(StrategyReliabilityScore.strategy_id == strategy_id)
            .order_by(StrategyReliabilityScore.generated_at.desc())
            .first()
        )
        if latest is not None:
            return _safe_float(latest.overall_score)
    except Exception:
        pass
    return None


def _current_readiness_score(strategy_id: uuid.UUID, db: Session) -> float | None:
    try:
        return compute_strategy_readiness(strategy_id, db).readiness_score
    except Exception:
        return None


def _current_backtest_reality_score(
    strategy_id: uuid.UUID, db: Session
) -> float | None:
    try:
        data = compute_backtest_reality_check(strategy_id, db)
        if data.verdict == "insufficient_data":
            return None
        return data.backtest_reality_score
    except Exception:
        return None


def _current_promotion_verdict(
    strategy_id: uuid.UUID, target_stage: str, db: Session
) -> str:
    try:
        result = evaluate_promotion_gates(strategy_id, target_stage, db)
        return _map_promotion_verdict(result.promotion_verdict)
    except Exception:
        return "review"


def _current_blockers(
    strategy_id: uuid.UUID, target_stage: str, db: Session
) -> list[str]:
    try:
        return list(evaluate_promotion_gates(strategy_id, target_stage, db).blockers)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Turnover-stress override resolution
# ---------------------------------------------------------------------------


def _resolve_turnover_stress_overrides(
    run, metric_overrides: dict
) -> dict:
    """If a turnover-stress marker is present, resolve concrete turnover/
    trade_count overrides relative to the current run. Returns a *new* dict
    with the marker removed."""
    overrides = dict(metric_overrides or {})
    if not overrides.pop("__turnover_stress__", False):
        return overrides

    metrics = (run.metrics_json or {}) if run is not None else {}
    current_turnover = _safe_float(
        metrics.get("turnover") or metrics.get("annual_turnover")
    )
    if current_turnover and current_turnover > 0:
        overrides.setdefault("turnover", round(current_turnover * 2, 4))
    else:
        overrides.setdefault("turnover", 1.6)

    current_trades = _safe_float(
        metrics.get("trade_count")
        or metrics.get("num_trades")
        or metrics.get("n_trades")
        or metrics.get("total_trades")
    )
    if current_trades and current_trades > 0:
        overrides.setdefault("trade_count", int(round(current_trades * 2)))
    else:
        overrides.setdefault("trade_count", 500)
    return overrides


# ---------------------------------------------------------------------------
# Helper: projected backtest reality under a scenario
# ---------------------------------------------------------------------------


def estimate_backtest_reality_under_scenario(
    run,
    assumption_overrides: dict | None,
    metric_overrides: dict | None,
    evidence_overrides: dict | None,
) -> float | None:
    """Estimate the projected backtest reality (0-100) under a scenario.

    Feeds an in-memory ``_ShimRun`` (copies of the run's JSON blobs with the
    overrides applied) into the PURE ``run_backtest_audit`` function, then
    applies evidence-driven caps. Returns None when there is no run.
    """
    if run is None:
        return None

    assumption_overrides = assumption_overrides or {}
    metric_overrides = metric_overrides or {}
    evidence_overrides = evidence_overrides or {}

    assumptions = dict(run.assumptions_json or {})
    assumptions.update(assumption_overrides)
    metrics = dict(run.metrics_json or {})
    metrics.update(metric_overrides)

    shim = _ShimRun(
        params_json=run.params_json,
        assumptions_json=assumptions,
        metrics_json=metrics,
        run_type=run.run_type,
        dataset_snapshot_id=getattr(run, "dataset_snapshot_id", None),
        universe_snapshot_id=getattr(run, "universe_snapshot_id", None),
    )

    result = run_backtest_audit(shim)
    projected = float(result.trust_score)

    # Evidence-override caps (mirrors M93 caps).
    if evidence_overrides.get("evidence_verification_failed"):
        projected = min(projected, 60.0)
    if evidence_overrides.get("paper_drift_high"):
        projected = min(projected, 55.0)

    return _clamp(projected)


# ---------------------------------------------------------------------------
# Helper: projected readiness under a scenario
# ---------------------------------------------------------------------------


def estimate_readiness_under_scenario(
    current_readiness: float | None,
    evidence_overrides: dict | None,
    reality_drop: float,
    target_stage: str,
) -> float:
    """Deterministic, explainable readiness projection.

    ``reality_drop`` is the positive number of points by which the projected
    backtest reality dropped versus the current backtest reality (0 if it
    improved or is unknown).
    """
    evidence_overrides = evidence_overrides or {}
    score = float(current_readiness) if current_readiness is not None else 0.0

    if evidence_overrides.get("signal_stale"):
        score -= 10  # freshness
    if evidence_overrides.get("dataset_stale"):
        score -= 8
    if evidence_overrides.get("report_missing"):
        score -= 5

    high_alerts = _safe_float(evidence_overrides.get("high_alerts_open")) or 0
    if high_alerts > 0:
        score -= min(15.0, high_alerts * 8.0)

    if evidence_overrides.get("paper_drift_high") and target_stage in (
        "shadow_production",
        "production_candidate",
    ):
        score -= 15

    # Backtest reality erosion pulls readiness down proportionally.
    if reality_drop > 0:
        score -= 0.3 * reality_drop

    # Evidence verification failure caps readiness.
    if evidence_overrides.get("evidence_verification_failed"):
        score = min(score, 60.0)

    return _clamp(score)


# ---------------------------------------------------------------------------
# Helper: projected reliability under a scenario
# ---------------------------------------------------------------------------


def _estimate_reliability_under_scenario(
    current_reliability: float | None,
    current_reality: float | None,
    projected_reality: float | None,
    evidence_overrides: dict | None,
) -> float | None:
    evidence_overrides = evidence_overrides or {}

    if current_reliability is not None:
        start = float(current_reliability)
    elif current_reality is not None:
        start = float(current_reality)
    else:
        start = 80.0

    score = start
    # Reliability tracks backtest trust strongly.
    if projected_reality is not None and current_reality is not None:
        score += 0.5 * (projected_reality - current_reality)

    if evidence_overrides.get("evidence_verification_failed"):
        score = min(score, 60.0)

    return _clamp(score)


# ---------------------------------------------------------------------------
# Helper: projected promotion gate impact
# ---------------------------------------------------------------------------


def estimate_promotion_gate_impact(
    projected_scores: SandboxScores,
    evidence_overrides: dict | None,
    target_stage: str,
) -> tuple[str, list[str]]:
    """Deterministically estimate the projected promotion verdict and the list
    of new blockers introduced by the scenario.

    Returns ``(verdict, new_blockers)`` where verdict is ready/review/blocked.
    """
    evidence_overrides = evidence_overrides or {}
    new_blockers: list[str] = []
    high_severity = False

    if evidence_overrides.get("report_missing"):
        new_blockers.append("Reliability report missing.")

    high_alerts = int(_safe_float(evidence_overrides.get("high_alerts_open")) or 0)
    if high_alerts > 0:
        new_blockers.append(f"{high_alerts} high/critical alert(s) open.")
        high_severity = True

    if evidence_overrides.get("evidence_verification_failed"):
        new_blockers.append("Evidence verification failed.")
        high_severity = True

    if evidence_overrides.get("paper_drift_high") and target_stage in (
        "shadow_production",
        "production_candidate",
    ):
        new_blockers.append(
            "High paper/backtest drift blocks production readiness."
        )
        high_severity = True

    if (
        projected_scores.backtest_reality_score is not None
        and projected_scores.backtest_reality_score < 50
    ):
        new_blockers.append("Backtest reality weak under scenario.")
        high_severity = True

    # Verdict.
    if high_severity:
        verdict = "blocked"
    elif new_blockers or (
        projected_scores.readiness_score is not None
        and projected_scores.readiness_score < 75
    ):
        verdict = "review"
    else:
        verdict = "ready"

    return verdict, new_blockers


# ---------------------------------------------------------------------------
# Helper: build deltas
# ---------------------------------------------------------------------------


_ASSUMPTION_DELTA_SPECS = [
    ("transaction_cost_bps", "Transaction cost (bps)", ("transaction_cost_bps", "transaction_cost")),
    ("slippage_bps", "Slippage (bps)", ("slippage_bps", "slippage")),
    ("fill_model", "Fill model", ("fill_model",)),
]
_METRIC_DELTA_SPECS = [
    ("turnover", "Turnover", ("turnover", "annual_turnover")),
    ("trade_count", "Trade count", ("trade_count", "num_trades", "n_trades", "total_trades")),
    ("max_drawdown", "Max drawdown", ("max_drawdown", "maximum_drawdown")),
    ("volatility", "Volatility", ("volatility", "annualised_vol", "annual_vol")),
    ("sharpe", "Sharpe", ("sharpe", "sharpe_ratio")),
]

_EVIDENCE_DELTA_SPECS = {
    "signal_stale": ("Signal freshness", "Signal snapshot modelled as stale.", -10.0),
    "dataset_stale": ("Dataset freshness", "Dataset snapshot modelled as stale.", -8.0),
    "report_missing": ("Reliability report", "Reliability report modelled as missing.", -5.0),
    "evidence_verification_failed": (
        "Evidence verification",
        "Evidence verification modelled as failed (caps reliability and reality).",
        -15.0,
    ),
    "paper_drift_high": (
        "Paper/backtest drift",
        "High paper/backtest drift modelled (caps backtest reality at 55).",
        -15.0,
    ),
}


def _lookup(d: dict, keys: tuple[str, ...]):
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    return None


def _build_deltas(
    run,
    assumption_overrides: dict,
    metric_overrides: dict,
    evidence_overrides: dict,
    reality_impact: float,
) -> list[SandboxDelta]:
    deltas: list[SandboxDelta] = []
    assumptions = (run.assumptions_json or {}) if run is not None else {}
    metrics = (run.metrics_json or {}) if run is not None else {}

    # Assumption overrides.
    for override_key, label, lookup_keys in _ASSUMPTION_DELTA_SPECS:
        if override_key in assumption_overrides:
            current_value = _lookup(assumptions, lookup_keys)
            projected_value = assumption_overrides[override_key]
            if current_value == projected_value:
                continue
            deltas.append(
                SandboxDelta(
                    key=override_key,
                    label=label,
                    current_value=current_value,
                    projected_value=projected_value,
                    impact=round(reality_impact, 1),
                    explanation=(
                        f"{label} changes from {current_value} to "
                        f"{projected_value} under the scenario."
                    ),
                )
            )

    # Metric overrides.
    for override_key, label, lookup_keys in _METRIC_DELTA_SPECS:
        if override_key in metric_overrides:
            current_value = _lookup(metrics, lookup_keys)
            projected_value = metric_overrides[override_key]
            if current_value == projected_value:
                continue
            deltas.append(
                SandboxDelta(
                    key=override_key,
                    label=label,
                    current_value=current_value,
                    projected_value=projected_value,
                    impact=round(reality_impact, 1),
                    explanation=(
                        f"{label} changes from {current_value} to "
                        f"{projected_value} under the scenario."
                    ),
                )
            )

    # Evidence overrides.
    for ev_key, (label, explanation, impact) in _EVIDENCE_DELTA_SPECS.items():
        if evidence_overrides.get(ev_key):
            deltas.append(
                SandboxDelta(
                    key=ev_key,
                    label=label,
                    current_value=False,
                    projected_value=True,
                    impact=impact,
                    explanation=explanation,
                )
            )

    high_alerts = int(_safe_float(evidence_overrides.get("high_alerts_open")) or 0)
    if high_alerts > 0:
        deltas.append(
            SandboxDelta(
                key="high_alerts_open",
                label="Open high/critical alerts",
                current_value=0,
                projected_value=high_alerts,
                impact=-min(15.0, high_alerts * 8.0),
                explanation=(
                    f"{high_alerts} high/critical alert(s) modelled as open, "
                    "reducing readiness."
                ),
            )
        )

    return deltas


# ---------------------------------------------------------------------------
# Helper: warnings + suggested actions
# ---------------------------------------------------------------------------


def _build_warnings_and_actions(
    deltas: list[SandboxDelta],
    new_blockers: list[str],
    assumption_overrides: dict,
    metric_overrides: dict,
    evidence_overrides: dict,
    run,
) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    actions: list[str] = []

    # Turnover + cost interaction.
    metrics = (run.metrics_json or {}) if run is not None else {}
    current_turnover = _safe_float(
        metrics.get("turnover") or metrics.get("annual_turnover")
    )
    projected_turnover = _safe_float(metric_overrides.get("turnover"))
    cost_increased = (
        "transaction_cost_bps" in assumption_overrides
        or "slippage_bps" in assumption_overrides
    )
    turnover_doubled = (
        projected_turnover is not None
        and current_turnover is not None
        and current_turnover > 0
        and projected_turnover >= 2 * current_turnover
    )
    if turnover_doubled and cost_increased:
        warnings.append(
            "High turnover combined with elevated costs materially erodes "
            "estimated reliability."
        )
        actions.append(
            "Add liquidity/capacity assumptions before raising turnover."
        )

    if evidence_overrides.get("report_missing"):
        actions.append("Generate a reliability report before promotion.")
    if evidence_overrides.get("evidence_verification_failed"):
        actions.append(
            "Resolve evidence verification failures before drawing conclusions."
        )
    if evidence_overrides.get("signal_stale") or evidence_overrides.get(
        "dataset_stale"
    ):
        actions.append("Refresh stale evidence snapshots.")
    if int(_safe_float(evidence_overrides.get("high_alerts_open")) or 0) > 0:
        actions.append("Resolve open alerts before promotion.")
    if evidence_overrides.get("paper_drift_high"):
        actions.append(
            "Investigate paper/backtest drift before production readiness."
        )

    # Large negative deltas.
    for d in deltas:
        if d.impact <= -10 and d.key in ("transaction_cost_bps", "slippage_bps"):
            warnings.append(
                f"{d.label} change has a large estimated impact "
                f"({d.impact:.0f} pts) on backtest reality."
            )

    if new_blockers and not actions:
        actions.append("Resolve the new blockers introduced by this scenario.")

    # De-duplicate while preserving order.
    warnings = list(dict.fromkeys(warnings))
    actions = list(dict.fromkeys(actions))
    return warnings, actions


# ---------------------------------------------------------------------------
# Public: current-state sandbox
# ---------------------------------------------------------------------------


def build_current_sandbox_state(
    strategy_id: uuid.UUID,
    db: Session,
    target_stage: str | None = None,
) -> SandboxData:
    """Build the current (no-scenario) sandbox state — current == projected."""
    from app.models.strategy import Strategy

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    resolved_stage = _normalize_target_stage(target_stage)
    now = datetime.now(timezone.utc)

    reliability = _current_reliability_score(strategy_id, db)
    # Baseline backtest reality through the SAME engine the projection uses
    # (empty-scenario run_backtest_audit), so current and projected are on one
    # consistent scale and the sandbox delta is honest. The capped M93
    # governance score is surfaced separately in the Backtest Reality panel.
    _baseline_run = get_latest_backtest_run(strategy_id, db)
    backtest_reality = estimate_backtest_reality_under_scenario(
        _baseline_run, None, None, None
    )
    readiness = _current_readiness_score(strategy_id, db)
    promotion_verdict = _current_promotion_verdict(strategy_id, resolved_stage, db)

    current = SandboxScores(
        reliability_score=reliability,
        backtest_reality_score=backtest_reality,
        readiness_score=readiness,
        promotion_verdict=promotion_verdict,
    )
    # current == projected for the no-scenario state.
    projected = SandboxScores(
        reliability_score=reliability,
        backtest_reality_score=backtest_reality,
        readiness_score=readiness,
        promotion_verdict=promotion_verdict,
    )

    return SandboxData(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        scenario_name="Current state",
        target_stage=resolved_stage,
        current=current,
        projected=projected,
        deltas=[],
        new_blockers=[],
        resolved_blockers=[],
        warnings=[],
        suggested_actions=[],
        generated_at=now,
        disclaimer=DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Public: simulate a scenario
# ---------------------------------------------------------------------------


def simulate_strategy_sandbox(
    strategy_id: uuid.UUID,
    db: Session,
    scenario: dict,
) -> SandboxData:
    """Simulate a what-if scenario for a strategy (READ-ONLY).

    ``scenario`` is a dict with keys:
        scenario_name, assumption_overrides, metric_overrides,
        evidence_overrides, target_stage.

    Returns a ``SandboxData`` with current vs projected scores, deltas,
    blockers, warnings, and suggested actions. Never writes to the database.
    """
    from app.models.strategy import Strategy

    # 1. Load strategy; resolve target stage.
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    scenario = scenario or {}
    scenario_name = scenario.get("scenario_name") or "Custom scenario"
    target_stage = _normalize_target_stage(scenario.get("target_stage"))
    assumption_overrides = dict(scenario.get("assumption_overrides") or {})
    raw_metric_overrides = dict(scenario.get("metric_overrides") or {})
    evidence_overrides = dict(scenario.get("evidence_overrides") or {})

    now = datetime.now(timezone.utc)
    warnings: list[str] = []

    # 2. Latest backtest run (fetched first so current and projected reality
    #    are computed through the SAME run_backtest_audit engine on one scale).
    run = get_latest_backtest_run(strategy_id, db)
    if run is None:
        warnings.append(
            "No backtest run — backtest reality estimate unavailable."
        )

    # 3. Current scores. Baseline backtest reality is the empty-scenario
    #    projection (same engine/scale as the projected score below), making
    #    the current -> projected delta apples-to-apples.
    current_reliability = _current_reliability_score(strategy_id, db)
    current_reality = estimate_backtest_reality_under_scenario(
        run, None, None, None
    )
    current_readiness = _current_readiness_score(strategy_id, db)
    current_verdict = _current_promotion_verdict(strategy_id, target_stage, db)
    current_blockers = _current_blockers(strategy_id, target_stage, db)

    current = SandboxScores(
        reliability_score=current_reliability,
        backtest_reality_score=current_reality,
        readiness_score=current_readiness,
        promotion_verdict=current_verdict,
    )

    # Resolve turnover-stress marker into concrete overrides relative to the run.
    metric_overrides = _resolve_turnover_stress_overrides(run, raw_metric_overrides)

    # 4. Projected backtest reality.
    projected_reality = estimate_backtest_reality_under_scenario(
        run, assumption_overrides, metric_overrides, evidence_overrides
    )

    # Reality drop (positive points lost) vs current.
    reality_drop = 0.0
    if projected_reality is not None and current_reality is not None:
        reality_drop = max(0.0, current_reality - projected_reality)

    # 5. Projected readiness.
    projected_readiness = estimate_readiness_under_scenario(
        current_readiness, evidence_overrides, reality_drop, target_stage
    )

    # 6. Projected reliability.
    projected_reliability = _estimate_reliability_under_scenario(
        current_reliability, current_reality, projected_reality, evidence_overrides
    )

    projected = SandboxScores(
        reliability_score=projected_reliability,
        backtest_reality_score=projected_reality,
        readiness_score=projected_readiness,
        promotion_verdict=current_verdict,  # placeholder; recomputed below
    )

    # 7. Projected promotion verdict + new blockers.
    projected_verdict, new_blockers = estimate_promotion_gate_impact(
        projected, evidence_overrides, target_stage
    )
    projected.promotion_verdict = projected_verdict

    # resolved_blockers: current blockers not reintroduced by the scenario
    # (best-effort — only when overrides do not re-trigger them).
    resolved_blockers: list[str] = []
    new_blocker_set = {b.lower() for b in new_blockers}
    for cb in current_blockers:
        if cb.lower() not in new_blocker_set:
            # Conservative: a current blocker is only "resolved" if the scenario
            # explicitly improves the relevant signal. The sandbox never claims
            # improvements unless overrides reduce a concern, so leave empty by
            # default. (Kept here for forward compatibility.)
            pass

    # 8. Deltas.
    reality_impact = -reality_drop if reality_drop > 0 else 0.0
    deltas = _build_deltas(
        run,
        assumption_overrides,
        metric_overrides,
        evidence_overrides,
        reality_impact,
    )

    # 9. Warnings + suggested actions.
    scenario_warnings, suggested_actions = _build_warnings_and_actions(
        deltas,
        new_blockers,
        assumption_overrides,
        metric_overrides,
        evidence_overrides,
        run,
    )
    warnings.extend(scenario_warnings)
    warnings = list(dict.fromkeys(warnings))

    return SandboxData(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        scenario_name=scenario_name,
        target_stage=target_stage,
        current=current,
        projected=projected,
        deltas=deltas,
        new_blockers=new_blockers,
        resolved_blockers=resolved_blockers,
        warnings=warnings,
        suggested_actions=suggested_actions,
        generated_at=now,
        disclaimer=DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Public: report generation
# ---------------------------------------------------------------------------


def _scores_to_dict(s: SandboxScores) -> dict:
    return {
        "reliability_score": s.reliability_score,
        "backtest_reality_score": s.backtest_reality_score,
        "readiness_score": s.readiness_score,
        "promotion_verdict": s.promotion_verdict,
    }


def generate_sandbox_report(
    strategy_id: uuid.UUID,
    db: Session,
    scenario: dict,
    format: str = "json",
) -> str:
    """Generate a what-if sandbox report (JSON or Markdown). READ-ONLY."""
    data = simulate_strategy_sandbox(strategy_id, db, scenario)

    if format == "markdown":
        cur, proj = data.current, data.projected

        def _fmt(v) -> str:
            if v is None:
                return "n/a"
            if isinstance(v, float):
                return f"{v:.1f}"
            return str(v)

        lines: list[str] = [
            f"# What-If Sandbox: {data.strategy_name}",
            "",
            f"**Strategy ID:** {data.strategy_id}  ",
            f"**Scenario:** {data.scenario_name}  ",
            f"**Target stage:** {data.target_stage}  ",
            f"**Generated:** {data.generated_at.isoformat()}  ",
            "",
            "## Scores: Current vs Projected",
            "",
            "| Metric | Current | Projected |",
            "|--------|---------|-----------|",
            f"| Reliability | {_fmt(cur.reliability_score)} | {_fmt(proj.reliability_score)} |",
            f"| Backtest reality | {_fmt(cur.backtest_reality_score)} | {_fmt(proj.backtest_reality_score)} |",
            f"| Readiness | {_fmt(cur.readiness_score)} | {_fmt(proj.readiness_score)} |",
            f"| Promotion verdict | {cur.promotion_verdict} | {proj.promotion_verdict} |",
        ]

        if data.deltas:
            lines += [
                "",
                "## Deltas",
                "",
                "| Key | Label | Current | Projected | Impact |",
                "|-----|-------|---------|-----------|--------|",
            ]
            for d in data.deltas:
                lines.append(
                    f"| `{d.key}` | {d.label} | {_fmt(d.current_value)} | "
                    f"{_fmt(d.projected_value)} | {d.impact:+.1f} |"
                )

        if data.new_blockers:
            lines += ["", "## New Blockers", ""]
            lines += [f"- {b}" for b in data.new_blockers]

        if data.warnings:
            lines += ["", "## Warnings", ""]
            lines += [f"- {w}" for w in data.warnings]

        if data.suggested_actions:
            lines += ["", "## Suggested Actions", ""]
            lines += [f"{i}. {a}" for i, a in enumerate(data.suggested_actions, 1)]

        lines += ["", "---", "", f"*{data.disclaimer}*"]
        return "\n".join(lines)

    # Default: JSON
    payload = {
        "strategy_id": str(data.strategy_id),
        "strategy_name": data.strategy_name,
        "scenario_name": data.scenario_name,
        "target_stage": data.target_stage,
        "current": _scores_to_dict(data.current),
        "projected": _scores_to_dict(data.projected),
        "deltas": [
            {
                "key": d.key,
                "label": d.label,
                "current_value": d.current_value,
                "projected_value": d.projected_value,
                "impact": d.impact,
                "explanation": d.explanation,
            }
            for d in data.deltas
        ],
        "new_blockers": data.new_blockers,
        "resolved_blockers": data.resolved_blockers,
        "warnings": data.warnings,
        "suggested_actions": data.suggested_actions,
        "generated_at": data.generated_at.isoformat(),
        "disclaimer": data.disclaimer,
    }
    return json.dumps(payload, indent=2, default=str)
