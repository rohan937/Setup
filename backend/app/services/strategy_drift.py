"""Strategy drift service (M47).

Computes drift between two strategy runs — comparing metrics, evidence quality,
assumptions, and trust signals. Deterministic — no AI, no causal claims, no
investment advice.

Language policy:
  Use: "logged higher score", "more complete instrumentation",
       "noted as observed", "deteriorated in logged value"
  Never: "better strategy", "more profitable", "should trade",
         "buy/sell", "alpha is stronger", "investment recommendation"
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STAGE_ORDER = ["research", "backtest", "paper", "live"]

KNOWN_METRICS: list[str] = [
    "sharpe",
    "sortino",
    "annual_return",
    "volatility",
    "max_drawdown",
    "turnover",
    "hit_rate",
    "trade_count",
    "alpha_bps",
    "transaction_cost_bps",
    "slippage_bps",
]

# Metrics where higher logged value is considered an improvement
HIGHER_BETTER = {"sharpe", "sortino", "annual_return", "hit_rate", "alpha_bps"}

# Metrics where lower logged value is considered an improvement
LOWER_BETTER = {"volatility", "max_drawdown", "turnover"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(v: object) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StrategyDriftRunSummaryData:
    run_id: uuid.UUID
    run_name: str
    run_type: str
    status: str
    created_at: datetime
    completed_at: datetime | None
    metrics_json: dict | None
    assumptions_json: dict | None
    strategy_version_label: str | None
    dataset_health: float | None
    signal_quality: float | None
    universe_symbol_count: int | None
    backtest_trust: float | None
    run_health_label: str


@dataclass
class MetricDriftItemData:
    metric: str
    baseline_value: float | None
    comparison_value: float | None
    absolute_delta: float | None
    percent_delta: float | None
    direction: str   # improved / deteriorated / changed / unchanged / unavailable
    severity: str    # none / low / medium / high


@dataclass
class EvidenceDriftItemData:
    evidence_type: str
    baseline_value: float | None
    comparison_value: float | None
    delta: float | None
    severity: str
    explanation: str


@dataclass
class AssumptionDriftItemData:
    key_path: str
    old_value: object
    new_value: object
    change_type: str
    impact_level: str
    suggested_check: str | None


@dataclass
class TrustDriftItemData:
    dimension: str
    baseline_value: float | None
    comparison_value: float | None
    delta: float | None
    severity: str
    explanation: str


@dataclass
class StrategyDriftData:
    strategy_id: uuid.UUID
    strategy_name: str
    mode: str
    generated_at: datetime
    drift_score: float | None
    drift_status: str
    baseline_run: StrategyDriftRunSummaryData | None
    comparison_run: StrategyDriftRunSummaryData | None
    stage_path: list = field(default_factory=list)
    metric_drifts: list = field(default_factory=list)
    evidence_drifts: list = field(default_factory=list)
    assumption_drifts: list = field(default_factory=list)
    trust_drifts: list = field(default_factory=list)
    highlighted_drifts: list[str] = field(default_factory=list)
    suggested_checks: list[str] = field(default_factory=list)
    deterministic_summary: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_to_summary(run, db: Session) -> StrategyDriftRunSummaryData:
    """Build a StrategyDriftRunSummaryData from a StrategyRun ORM object."""
    from app.services.strategy_run_history import _load_run_evidence

    item = _load_run_evidence(run, db)
    return StrategyDriftRunSummaryData(
        run_id=run.id,
        run_name=run.run_name,
        run_type=run.run_type,
        status=run.status,
        created_at=run.created_at,
        completed_at=run.completed_at,
        metrics_json=run.metrics_json,
        assumptions_json=run.assumptions_json,
        strategy_version_label=(
            item.strategy_version.version_label if item.strategy_version else None
        ),
        dataset_health=(
            float(item.dataset_evidence.health_score) if item.dataset_evidence else None
        ),
        signal_quality=(
            float(item.signal_evidence.quality_score) if item.signal_evidence else None
        ),
        universe_symbol_count=(
            item.universe_evidence.symbol_count if item.universe_evidence else None
        ),
        backtest_trust=(
            float(item.backtest_audit.trust_score) if item.backtest_audit else None
        ),
        run_health_label=item.run_health_label,
    )


def _compute_metric_drifts(
    base_sum: StrategyDriftRunSummaryData,
    comp_sum: StrategyDriftRunSummaryData,
) -> list[MetricDriftItemData]:
    base_m = base_sum.metrics_json or {}
    comp_m = comp_sum.metrics_json or {}
    results: list[MetricDriftItemData] = []

    for metric in KNOWN_METRICS:
        base_val = _safe_float(base_m.get(metric))
        comp_val = _safe_float(comp_m.get(metric))
        if base_val is None and comp_val is None:
            continue

        delta = (
            (comp_val - base_val)
            if (base_val is not None and comp_val is not None)
            else None
        )
        pct = (
            (delta / abs(base_val) * 100)
            if (delta is not None and base_val is not None and base_val != 0)
            else None
        )

        # Direction
        if base_val is None or comp_val is None:
            direction = "unavailable"
        elif delta == 0:
            direction = "unchanged"
        elif metric in HIGHER_BETTER:
            direction = "improved" if delta > 0 else "deteriorated"
        elif metric in LOWER_BETTER:
            if metric == "max_drawdown":
                # max_drawdown is typically negative; more negative = worse
                direction = "deteriorated" if delta < 0 else "improved"
            else:
                # volatility, turnover — lower is better
                direction = "improved" if delta < 0 else "deteriorated"
        else:
            direction = "changed"

        # Severity
        severity = "none"
        if base_val is None or comp_val is None:
            severity = "medium" if (base_val is not None or comp_val is not None) else "none"
        elif metric == "sharpe":
            if delta is not None and (abs(delta) > 0.5 or (pct is not None and abs(pct) > 25)):
                severity = "high"
            elif pct is not None and abs(pct) > 10:
                severity = "medium"
            elif delta != 0:
                severity = "low"
        elif metric == "max_drawdown":
            if pct is not None and pct < -25:
                severity = "high"
            elif pct is not None and pct < -10:
                severity = "medium"
            elif delta is not None and delta != 0:
                severity = "low"
        elif metric in ("turnover", "volatility"):
            if pct is not None and pct > 50:
                severity = "high"
            elif pct is not None and pct > 20:
                severity = "medium"
            elif pct is not None and pct > 5:
                severity = "low"
        elif delta is not None and delta != 0:
            severity = "low"

        results.append(
            MetricDriftItemData(
                metric=metric,
                baseline_value=base_val,
                comparison_value=comp_val,
                absolute_delta=round(delta, 4) if delta is not None else None,
                percent_delta=round(pct, 1) if pct is not None else None,
                direction=direction,
                severity=severity,
            )
        )

    return results


def _compute_evidence_drifts(
    base_sum: StrategyDriftRunSummaryData,
    comp_sum: StrategyDriftRunSummaryData,
) -> list[EvidenceDriftItemData]:
    drifts: list[EvidenceDriftItemData] = []

    def _add(ev_type: str, bv: float | None, cv: float | None, explanation_prefix: str) -> None:
        if bv is None and cv is None:
            return
        d = (cv - bv) if (bv is not None and cv is not None) else None
        sev = "none"
        if bv is None or cv is None:
            sev = "medium"
        elif d is not None:
            if abs(d) > 15:
                sev = "high"
            elif abs(d) > 5:
                sev = "medium"
            elif abs(d) > 0:
                sev = "low"
        expl = explanation_prefix
        if bv is not None and cv is not None:
            expl += f": {bv} → {cv}"
        elif bv is None:
            expl += " added in comparison run"
        else:
            expl += " missing in comparison run"
        drifts.append(
            EvidenceDriftItemData(
                evidence_type=ev_type,
                baseline_value=bv,
                comparison_value=cv,
                delta=d,
                severity=sev,
                explanation=expl,
            )
        )

    _add("dataset_health", base_sum.dataset_health, comp_sum.dataset_health, "Dataset health score")
    _add("signal_quality", base_sum.signal_quality, comp_sum.signal_quality, "Signal quality score")
    if base_sum.universe_symbol_count is not None or comp_sum.universe_symbol_count is not None:
        _add(
            "universe_symbol_count",
            float(base_sum.universe_symbol_count) if base_sum.universe_symbol_count is not None else None,
            float(comp_sum.universe_symbol_count) if comp_sum.universe_symbol_count is not None else None,
            "Universe symbol count",
        )
    _add("backtest_trust", base_sum.backtest_trust, comp_sum.backtest_trust, "Backtest audit trust score")
    return drifts


def _compute_assumption_drifts(
    base_sum: StrategyDriftRunSummaryData,
    comp_sum: StrategyDriftRunSummaryData,
) -> list[AssumptionDriftItemData]:
    from app.services.config_snapshots import classify_assumption_change

    drifts: list[AssumptionDriftItemData] = []
    base_a = base_sum.assumptions_json or {}
    comp_a = comp_sum.assumptions_json or {}
    all_keys = set(base_a.keys()) | set(comp_a.keys())

    for key in sorted(all_keys):
        bv = base_a.get(key)
        cv = comp_a.get(key)
        if bv == cv:
            continue
        change_type = "added" if bv is None else ("removed" if cv is None else "changed")
        try:
            impact, _reason, check = classify_assumption_change(key, bv, cv)
        except Exception:
            impact, check = "unknown", None
        drifts.append(
            AssumptionDriftItemData(
                key_path=f"assumptions.{key}",
                old_value=bv,
                new_value=cv,
                change_type=change_type,
                impact_level=impact,
                suggested_check=check,
            )
        )

    return drifts


def _compute_trust_drifts(
    base_sum: StrategyDriftRunSummaryData,
    comp_sum: StrategyDriftRunSummaryData,
) -> list[TrustDriftItemData]:
    drifts: list[TrustDriftItemData] = []

    if base_sum.backtest_trust is not None or comp_sum.backtest_trust is not None:
        bv, cv = base_sum.backtest_trust, comp_sum.backtest_trust
        d = (cv - bv) if (bv is not None and cv is not None) else None
        sev = "none"
        if d is not None and d < -20:
            sev = "high"
        elif d is not None and d < -10:
            sev = "medium"
        elif d is not None and d < 0:
            sev = "low"
        elif bv is not None and cv is None:
            sev = "medium"
        drifts.append(
            TrustDriftItemData(
                dimension="backtest_trust",
                baseline_value=bv,
                comparison_value=cv,
                delta=d,
                severity=sev,
                explanation=(
                    f"Backtest audit trust: {bv} → {cv}"
                    if (bv is not None and cv is not None)
                    else "Backtest audit availability changed"
                ),
            )
        )

    if base_sum.run_health_label != comp_sum.run_health_label:
        LABEL_ORDER = {
            "strong": 0,
            "usable": 1,
            "review": 2,
            "weak": 3,
            "insufficient_evidence": 4,
        }
        b_ord = LABEL_ORDER.get(base_sum.run_health_label, 2)
        c_ord = LABEL_ORDER.get(comp_sum.run_health_label, 2)
        sev = (
            "high" if (c_ord - b_ord) >= 2
            else "medium" if c_ord > b_ord
            else "low"
        )
        drifts.append(
            TrustDriftItemData(
                dimension="run_health_label",
                baseline_value=None,
                comparison_value=None,
                delta=None,
                severity=sev,
                explanation=(
                    f"Run health label: {base_sum.run_health_label} → {comp_sum.run_health_label}"
                ),
            )
        )

    return drifts


def _compute_drift_score(
    metric_drifts: list[MetricDriftItemData],
    evidence_drifts: list[EvidenceDriftItemData],
    assumption_drifts: list[AssumptionDriftItemData],
    trust_drifts: list[TrustDriftItemData],
) -> float:
    score = 100.0

    high_met = sum(1 for m in metric_drifts if m.severity == "high")
    med_met = sum(1 for m in metric_drifts if m.severity == "medium")
    score -= min(high_met * 20, 40)
    score -= min(med_met * 10, 30)

    ev_det = sum(
        1
        for e in evidence_drifts
        if e.severity in ("high", "medium") and e.delta is not None and e.delta < 0
    )
    score -= min(ev_det * 10, 30)

    for t in trust_drifts:
        if t.severity == "high":
            score -= 20
        elif t.severity == "medium":
            score -= 10

    weak_a = sum(1 for a in assumption_drifts if a.impact_level == "weakening")
    score -= min(weak_a * 10, 30)

    return max(0.0, round(score, 1))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_strategy_drift(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    mode: str = "latest_stage_pair",
    baseline_run_id: uuid.UUID | None = None,
    comparison_run_id: uuid.UUID | None = None,
) -> StrategyDriftData:
    """Compute drift between two strategy runs.

    Modes:
      - latest_stage_pair: compares the latest run of two different stage types
      - selected_runs: compares explicitly supplied baseline_run_id / comparison_run_id
      - full_stage_path: compares first and last stage in STAGE_ORDER

    Raises ValueError for invalid inputs. Returns StrategyDriftData with
    drift_status="insufficient_evidence" when fewer than 2 comparable runs exist.
    """
    from app.models.strategy import Strategy
    from app.models.strategy_run import StrategyRun

    now = datetime.now(timezone.utc)

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    all_runs = (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(StrategyRun.created_at.asc())
        .all()
    )

    base_run = None
    comp_run = None
    insufficient = False

    if mode == "selected_runs":
        if not baseline_run_id or not comparison_run_id:
            raise ValueError(
                "baseline_run_id and comparison_run_id required for selected_runs mode."
            )
        base_run = next((r for r in all_runs if r.id == baseline_run_id), None)
        comp_run = next((r for r in all_runs if r.id == comparison_run_id), None)
        if not base_run:
            raise ValueError(
                f"Baseline run {baseline_run_id} not found for this strategy."
            )
        if not comp_run:
            raise ValueError(
                f"Comparison run {comparison_run_id} not found for this strategy."
            )

    elif mode == "latest_stage_pair":
        by_type: dict[str, list] = {}
        for r in all_runs:
            by_type.setdefault(r.run_type, []).append(r)
        backtests = by_type.get("backtest", [])
        paper = by_type.get("paper", [])
        live = by_type.get("live", [])
        research = by_type.get("research", [])
        if backtests and (paper or live):
            base_run = backtests[-1]
            comp_run = (paper or live)[-1]
        elif research and backtests:
            base_run = research[-1]
            comp_run = backtests[-1]
        elif len(all_runs) >= 2:
            base_run = all_runs[-2]
            comp_run = all_runs[-1]
        else:
            insufficient = True

    elif mode == "full_stage_path":
        by_type = {}
        for r in all_runs:
            by_type.setdefault(r.run_type, []).append(r)
        available = [(t, by_type[t][-1]) for t in STAGE_ORDER if t in by_type]
        if len(available) < 2:
            insufficient = True
        else:
            base_run = available[0][1]
            comp_run = available[-1][1]

    if insufficient or not base_run or not comp_run:
        return StrategyDriftData(
            strategy_id=strategy_id,
            strategy_name=strategy.name,
            mode=mode,
            generated_at=now,
            drift_score=None,
            drift_status="insufficient_evidence",
            baseline_run=None,
            comparison_run=None,
            suggested_checks=[
                "Log at least two strategy runs with different run types to compute drift."
            ],
            deterministic_summary=(
                f"Insufficient evidence: fewer than 2 comparable runs found for {strategy.name}."
            ),
        )

    base_sum = _run_to_summary(base_run, db)
    comp_sum = _run_to_summary(comp_run, db)

    metric_drifts = _compute_metric_drifts(base_sum, comp_sum)
    evidence_drifts = _compute_evidence_drifts(base_sum, comp_sum)
    assumption_drifts = _compute_assumption_drifts(base_sum, comp_sum)
    trust_drifts = _compute_trust_drifts(base_sum, comp_sum)

    drift_score = _compute_drift_score(
        metric_drifts, evidence_drifts, assumption_drifts, trust_drifts
    )

    if drift_score >= 85:
        drift_status = "stable"
    elif drift_score >= 70:
        drift_status = "watch"
    elif drift_score >= 50:
        drift_status = "review"
    else:
        drift_status = "severe"

    # Highlighted drifts (up to 5)
    highlighted: list[str] = []
    for m in sorted(
        metric_drifts,
        key=lambda x: {"high": 0, "medium": 1, "low": 2, "none": 3}.get(x.severity, 3),
    ):
        if m.severity in ("high", "medium") and m.direction in ("deteriorated", "unavailable"):
            highlighted.append(
                f"{m.metric}: {m.baseline_value} → {m.comparison_value}"
                f" ({m.direction}, {m.severity})"
            )
    for e in evidence_drifts:
        if e.severity in ("high", "medium"):
            highlighted.append(f"{e.evidence_type}: {e.explanation}")
    highlighted = highlighted[:5]

    # Suggested checks
    checks: list[str] = []
    if any(m.severity == "high" for m in metric_drifts):
        checks.append("Investigate high-severity metric drift between stages.")
    if any(e.severity in ("high", "medium") for e in evidence_drifts):
        checks.append("Review evidence quality changes between runs.")
    if any(a.impact_level == "weakening" for a in assumption_drifts):
        checks.append("Investigate weakening assumption changes.")
    if any(t.severity in ("high", "medium") for t in trust_drifts):
        checks.append("Run Backtest Reality Check on the comparison run.")
    if not checks:
        checks.append(
            "Drift is stable. Continue evidence logging to maintain comparability."
        )

    # Deterministic summary
    total_high = sum(1 for m in metric_drifts if m.severity == "high")
    summary_parts = [
        f"{base_run.run_type.title()} and {comp_run.run_type.title()} runs show"
        f" {drift_status}-level drift (score: {drift_score:.0f}/100)."
    ]
    if total_high:
        summary_parts.append(f"{total_high} high-severity metric drift(s) detected.")
    ev_issues = sum(1 for e in evidence_drifts if e.severity in ("high", "medium"))
    if ev_issues:
        summary_parts.append(f"{ev_issues} evidence quality change(s) detected.")
    summary_parts.append(
        "Deterministic comparison of logged evidence. Not a trading recommendation."
    )

    return StrategyDriftData(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        mode=mode,
        generated_at=now,
        drift_score=drift_score,
        drift_status=drift_status,
        baseline_run=base_sum,
        comparison_run=comp_sum,
        metric_drifts=metric_drifts,
        evidence_drifts=evidence_drifts,
        assumption_drifts=assumption_drifts,
        trust_drifts=trust_drifts,
        highlighted_drifts=highlighted,
        suggested_checks=checks,
        deterministic_summary=" ".join(summary_parts),
    )
