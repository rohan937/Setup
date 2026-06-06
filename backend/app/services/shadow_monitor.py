"""Shadow monitor drift engine (M88).

Explicit drift-threshold service for comparing baseline (backtest/research)
runs against live-like (paper/live) runs. Distinct from the M50
shadow_production.py which performs 11 production-readiness checks.

This service focuses on deterministic metric drift scoring with explicit
thresholds. No AI, no causal claims, no investment advice.

Language policy:
  Use: "logged", "observed", "noted", "deteriorated in logged value"
  Never: "better strategy", "more profitable", "should trade", "buy/sell"
  Always add disclaimer: "Shadow monitoring is a research reliability check,
  not a trading recommendation."
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "Shadow monitoring is a research reliability check, not a trading recommendation."
)

# Key metrics subject to explicit drift thresholds (M88 spec)
KEY_METRICS = [
    "turnover",
    "volatility",
    "max_drawdown",
    "trade_count",
    "annual_return",
    "sharpe",
]

METRIC_LABELS = {
    "turnover": "Turnover",
    "volatility": "Volatility",
    "max_drawdown": "Max Drawdown",
    "trade_count": "Trade Count",
    "annual_return": "Annual Return",
    "sharpe": "Sharpe Ratio",
}

# Drift thresholds per M88 spec
# For increase-is-drift metrics (turnover, volatility, trade_count):
#   percent increase in comparison vs baseline
INCREASE_DRIFT_THRESHOLDS = {
    "turnover":    {"watch": 0.50, "fail": 1.00},
    "volatility":  {"watch": 0.25, "fail": 0.50},
    "trade_count": {"watch": 0.50, "fail": 1.00},
}

# For degradation metrics (annual_return, sharpe):
#   percent degradation = (baseline - comparison) / abs(baseline)
DEGRADATION_DRIFT_THRESHOLDS = {
    "annual_return": {"watch": 0.25, "fail": 0.50},
    "sharpe":        {"watch": 0.25, "fail": 0.50},
}

# max_drawdown uses absolute pp worse
# pp_worse = baseline - comparison  (both typically negative, e.g. -0.10 vs -0.20)
MAX_DRAWDOWN_THRESHOLDS = {
    "watch": 0.05,   # 5pp worse
    "fail":  0.10,   # 10pp worse
}

SEVERITY_FOR_STATUS = {
    "fail": "high",
    "watch": "medium",
    "pass": "low",
    "missing": "info",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ShadowDriftMetric:
    key: str
    label: str
    baseline_value: Optional[float]
    comparison_value: Optional[float]
    absolute_delta: Optional[float]
    percent_delta: Optional[float]
    status: str   # pass | watch | fail | missing
    severity: str  # info | low | medium | high | critical
    explanation: str


@dataclass
class ShadowMonitorData:
    strategy_id: uuid.UUID
    strategy_name: str
    baseline_run_id: Optional[uuid.UUID]
    baseline_run_name: Optional[str]
    baseline_run_type: Optional[str]
    comparison_run_id: Optional[uuid.UUID]
    comparison_run_name: Optional[str]
    comparison_run_type: Optional[str]
    verdict: str           # stable | watch | drifted | insufficient_data
    drift_score: Optional[float]  # 0-100
    severity: str          # low | medium | high | critical
    primary_concern: Optional[str]
    metrics: list          # list[ShadowDriftMetric]
    top_concerns: list     # list[str]
    suggested_actions: list  # list[str]
    blockers: list         # list[str]
    missing_metric_keys: list  # list[str]
    missing_metric_coverage: float  # 0.0-1.0
    generated_at: datetime
    disclaimer: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_float(v: object) -> Optional[float]:
    """Safely coerce value to float, returning None on failure."""
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _get_metric(metrics_json: Optional[dict], key: str) -> Optional[float]:
    if not metrics_json:
        return None
    return _safe_float(metrics_json.get(key))


def _compute_single_metric_drift(
    key: str,
    baseline_val: Optional[float],
    comparison_val: Optional[float],
) -> ShadowDriftMetric:
    """Compute drift status for one metric using M88 thresholds."""
    label = METRIC_LABELS.get(key, key)

    if baseline_val is None and comparison_val is None:
        return ShadowDriftMetric(
            key=key,
            label=label,
            baseline_value=None,
            comparison_value=None,
            absolute_delta=None,
            percent_delta=None,
            status="missing",
            severity="info",
            explanation=f"{label} was not logged in either the baseline or comparison run.",
        )

    if baseline_val is None:
        return ShadowDriftMetric(
            key=key,
            label=label,
            baseline_value=None,
            comparison_value=comparison_val,
            absolute_delta=None,
            percent_delta=None,
            status="missing",
            severity="info",
            explanation=f"{label} was not logged in the baseline run; comparison value observed as {comparison_val}.",
        )

    if comparison_val is None:
        return ShadowDriftMetric(
            key=key,
            label=label,
            baseline_value=baseline_val,
            comparison_value=None,
            absolute_delta=None,
            percent_delta=None,
            status="missing",
            severity="info",
            explanation=f"{label} was not logged in the comparison run; baseline value was {baseline_val}.",
        )

    abs_delta = comparison_val - baseline_val

    # --- max_drawdown: absolute pp worse ---
    if key == "max_drawdown":
        # pp_worse = baseline - comparison
        # e.g. baseline=-0.10, comparison=-0.20 → pp_worse=0.10 (worse)
        # e.g. baseline=-0.10, comparison=-0.05 → pp_worse=-0.05 (not worse = pass)
        pp_worse = baseline_val - comparison_val
        pct_delta = (comparison_val - baseline_val) / abs(baseline_val) if baseline_val != 0 else None
        if pp_worse >= MAX_DRAWDOWN_THRESHOLDS["fail"]:
            status = "fail"
            explanation = (
                f"{label} deteriorated in logged value by {pp_worse*100:.1f}pp "
                f"(baseline: {baseline_val:.4f}, observed: {comparison_val:.4f}). "
                f"Threshold: fail >= {MAX_DRAWDOWN_THRESHOLDS['fail']*100:.0f}pp worse."
            )
        elif pp_worse >= MAX_DRAWDOWN_THRESHOLDS["watch"]:
            status = "watch"
            explanation = (
                f"{label} noted as {pp_worse*100:.1f}pp worse in logged value "
                f"(baseline: {baseline_val:.4f}, observed: {comparison_val:.4f}). "
                f"Watch threshold: >= {MAX_DRAWDOWN_THRESHOLDS['watch']*100:.0f}pp worse."
            )
        else:
            status = "pass"
            if pp_worse < 0:
                explanation = (
                    f"{label} logged as less negative in comparison run "
                    f"(baseline: {baseline_val:.4f}, observed: {comparison_val:.4f}). "
                    "No drift noted."
                )
            else:
                explanation = (
                    f"{label} logged within acceptable range "
                    f"(baseline: {baseline_val:.4f}, observed: {comparison_val:.4f})."
                )
        return ShadowDriftMetric(
            key=key,
            label=label,
            baseline_value=baseline_val,
            comparison_value=comparison_val,
            absolute_delta=abs_delta,
            percent_delta=pct_delta,
            status=status,
            severity=SEVERITY_FOR_STATUS[status],
            explanation=explanation,
        )

    # --- increase-is-drift metrics: turnover, volatility, trade_count ---
    if key in INCREASE_DRIFT_THRESHOLDS:
        thresholds = INCREASE_DRIFT_THRESHOLDS[key]
        if baseline_val != 0:
            pct = (comparison_val - baseline_val) / abs(baseline_val)
        else:
            pct = None

        if pct is not None and pct >= thresholds["fail"]:
            status = "fail"
            explanation = (
                f"{label} observed at {pct*100:.1f}% increase vs baseline "
                f"(baseline: {baseline_val}, observed: {comparison_val}). "
                f"Fail threshold: >= {thresholds['fail']*100:.0f}% increase."
            )
        elif pct is not None and pct >= thresholds["watch"]:
            status = "watch"
            explanation = (
                f"{label} noted at {pct*100:.1f}% increase vs baseline "
                f"(baseline: {baseline_val}, observed: {comparison_val}). "
                f"Watch threshold: >= {thresholds['watch']*100:.0f}% increase."
            )
        else:
            status = "pass"
            pct_str = f"{pct*100:.1f}%" if pct is not None else "N/A"
            explanation = (
                f"{label} within logged range: {pct_str} change observed "
                f"(baseline: {baseline_val}, observed: {comparison_val})."
            )
        return ShadowDriftMetric(
            key=key,
            label=label,
            baseline_value=baseline_val,
            comparison_value=comparison_val,
            absolute_delta=abs_delta,
            percent_delta=pct,
            status=status,
            severity=SEVERITY_FOR_STATUS[status],
            explanation=explanation,
        )

    # --- degradation metrics: annual_return, sharpe ---
    if key in DEGRADATION_DRIFT_THRESHOLDS:
        thresholds = DEGRADATION_DRIFT_THRESHOLDS[key]
        if baseline_val != 0:
            degradation = (baseline_val - comparison_val) / abs(baseline_val)
        else:
            degradation = None

        pct_delta = (comparison_val - baseline_val) / abs(baseline_val) if baseline_val != 0 else None

        if degradation is not None and degradation >= thresholds["fail"]:
            status = "fail"
            explanation = (
                f"{label} deteriorated in logged value by {degradation*100:.1f}% "
                f"(baseline: {baseline_val}, observed: {comparison_val}). "
                f"Fail threshold: >= {thresholds['fail']*100:.0f}% degradation."
            )
        elif degradation is not None and degradation >= thresholds["watch"]:
            status = "watch"
            explanation = (
                f"{label} noted as {degradation*100:.1f}% lower in logged value "
                f"(baseline: {baseline_val}, observed: {comparison_val}). "
                f"Watch threshold: >= {thresholds['watch']*100:.0f}% degradation."
            )
        else:
            status = "pass"
            if degradation is not None and degradation < 0:
                explanation = (
                    f"{label} logged higher in comparison run "
                    f"(baseline: {baseline_val}, observed: {comparison_val}). "
                    "No drift noted."
                )
            else:
                explanation = (
                    f"{label} within acceptable logged range "
                    f"(baseline: {baseline_val}, observed: {comparison_val})."
                )
        return ShadowDriftMetric(
            key=key,
            label=label,
            baseline_value=baseline_val,
            comparison_value=comparison_val,
            absolute_delta=abs_delta,
            percent_delta=pct_delta,
            status=status,
            severity=SEVERITY_FOR_STATUS[status],
            explanation=explanation,
        )

    # Fallback (should not reach here for the 6 key metrics)
    return ShadowDriftMetric(
        key=key,
        label=label,
        baseline_value=baseline_val,
        comparison_value=comparison_val,
        absolute_delta=abs_delta,
        percent_delta=None,
        status="pass",
        severity="low",
        explanation=f"{label} logged (baseline: {baseline_val}, observed: {comparison_val}).",
    )


def _build_suggested_actions(
    metrics: list[ShadowDriftMetric],
    verdict: str,
    missing_keys: list[str],
) -> list[str]:
    actions: list[str] = []
    fail_keys = [m.key for m in metrics if m.status == "fail"]
    watch_keys = [m.key for m in metrics if m.status == "watch"]

    if fail_keys:
        actions.append(
            f"Investigate logged drift in: {', '.join(fail_keys)}. "
            "Review parameter changes between baseline and comparison runs."
        )
    if watch_keys:
        actions.append(
            f"Monitor elevated logged change in: {', '.join(watch_keys)}. "
            "Consider logging additional comparison runs."
        )
    if missing_keys:
        actions.append(
            f"Log the following metrics in both runs to improve coverage: "
            f"{', '.join(missing_keys)}."
        )
    if verdict == "insufficient_data":
        actions.append(
            "Upload a paper or shadow run with metrics_json populated to enable drift scoring."
        )
    if not actions:
        actions.append(
            "No drift noted. Continue logging paper or live-like runs to maintain coverage."
        )
    return actions


def _build_blockers(metrics: list[ShadowDriftMetric], verdict: str) -> list[str]:
    blockers: list[str] = []
    fail_metrics = [m for m in metrics if m.status == "fail"]
    for m in fail_metrics:
        blockers.append(
            f"{m.label} logged as failed threshold: {m.explanation}"
        )
    return blockers


def _build_top_concerns(metrics: list[ShadowDriftMetric]) -> list[str]:
    concerns: list[str] = []
    ordered = sorted(
        metrics,
        key=lambda m: ({"fail": 0, "watch": 1, "missing": 2, "pass": 3}.get(m.status, 4)),
    )
    for m in ordered:
        if m.status in ("fail", "watch"):
            concerns.append(m.explanation)
    return concerns[:5]


# ---------------------------------------------------------------------------
# Public: run selection
# ---------------------------------------------------------------------------

def get_baseline_backtest(strategy_id: uuid.UUID, db: Session):
    """Select the latest backtest run; fallback to latest research run.

    Returns StrategyRun or None.
    """
    from app.models.strategy_run import StrategyRun

    backtest = (
        db.query(StrategyRun)
        .filter(
            StrategyRun.strategy_id == strategy_id,
            StrategyRun.run_type == "backtest",
        )
        .order_by(StrategyRun.created_at.desc())
        .first()
    )
    if backtest is not None:
        return backtest

    research = (
        db.query(StrategyRun)
        .filter(
            StrategyRun.strategy_id == strategy_id,
            StrategyRun.run_type == "research",
        )
        .order_by(StrategyRun.created_at.desc())
        .first()
    )
    return research


def get_latest_live_like_run(strategy_id: uuid.UUID, db: Session):
    """Select the latest paper or live run.

    Returns StrategyRun or None.
    """
    from app.models.strategy_run import StrategyRun

    run = (
        db.query(StrategyRun)
        .filter(
            StrategyRun.strategy_id == strategy_id,
            StrategyRun.run_type.in_(["paper", "live"]),
        )
        .order_by(StrategyRun.created_at.desc())
        .first()
    )
    return run


# ---------------------------------------------------------------------------
# Public: core scoring
# ---------------------------------------------------------------------------

def compute_shadow_drift_score(
    metrics: list[ShadowDriftMetric],
) -> tuple[float, str, str]:
    """Compute drift score, severity, and verdict from a list of ShadowDriftMetric.

    drift_score = (fail_count*30 + watch_count*15) / (total_key_metrics*30) * 100
                  + missing_penalty

    Capped at 100.

    Returns:
        (drift_score: float 0-100, severity: str, verdict: str)
    """
    total_key = len(KEY_METRICS)
    fail_count = sum(1 for m in metrics if m.status == "fail")
    watch_count = sum(1 for m in metrics if m.status == "watch")
    missing_count = sum(1 for m in metrics if m.status == "missing")

    missing_coverage = missing_count / total_key if total_key > 0 else 0.0

    raw = (fail_count * 30 + watch_count * 15) / (total_key * 30) * 100
    # Missing penalty: each missing metric adds 5 points (capped contribution)
    missing_penalty = missing_count * 5
    drift_score = min(100.0, raw + missing_penalty)

    # Verdict / severity determination
    if fail_count >= 2:
        severity = "critical"
        verdict = "drifted"
    elif fail_count == 1:
        severity = "high"
        verdict = "drifted"
    elif watch_count >= 2:
        severity = "medium"
        verdict = "watch"
    elif watch_count == 1:
        severity = "medium"
        verdict = "watch"
    elif missing_coverage >= 0.5 and fail_count == 0:
        severity = "low"
        verdict = "insufficient_data"
    else:
        severity = "low"
        verdict = "stable"

    return (drift_score, severity, verdict)


# ---------------------------------------------------------------------------
# Public: compare
# ---------------------------------------------------------------------------

def compare_backtest_to_paper(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    baseline_run_id: Optional[uuid.UUID] = None,
    comparison_run_id: Optional[uuid.UUID] = None,
) -> ShadowMonitorData:
    """Core comparison function.

    Compares a baseline (backtest or research) run against a live-like
    (paper or live) run and returns a ShadowMonitorData dataclass.

    If baseline is None → verdict="insufficient_data", drift_score=None
    If comparison is None → verdict="insufficient_data", drift_score=None,
        message: no paper run uploaded yet.
    """
    from app.models.strategy import Strategy
    from app.models.strategy_run import StrategyRun

    now = datetime.now(timezone.utc)

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found.")

    # Resolve baseline run
    if baseline_run_id is not None:
        baseline_run = (
            db.query(StrategyRun)
            .filter(StrategyRun.id == baseline_run_id, StrategyRun.strategy_id == strategy_id)
            .first()
        )
    else:
        baseline_run = get_baseline_backtest(strategy_id, db)

    # Resolve comparison run
    if comparison_run_id is not None:
        comparison_run = (
            db.query(StrategyRun)
            .filter(StrategyRun.id == comparison_run_id, StrategyRun.strategy_id == strategy_id)
            .first()
        )
    else:
        comparison_run = get_latest_live_like_run(strategy_id, db)

    # No baseline
    if baseline_run is None:
        return ShadowMonitorData(
            strategy_id=strategy_id,
            strategy_name=strategy.name,
            baseline_run_id=None,
            baseline_run_name=None,
            baseline_run_type=None,
            comparison_run_id=None,
            comparison_run_name=None,
            comparison_run_type=None,
            verdict="insufficient_data",
            drift_score=None,
            severity="low",
            primary_concern="No baseline backtest or research run found.",
            metrics=[],
            top_concerns=[],
            suggested_actions=[
                "Log a backtest or research run as the strategy baseline before enabling shadow monitoring."
            ],
            blockers=["No baseline run found for this strategy."],
            missing_metric_keys=KEY_METRICS,
            missing_metric_coverage=1.0,
            generated_at=now,
            disclaimer=DISCLAIMER,
        )

    # No comparison
    if comparison_run is None:
        return ShadowMonitorData(
            strategy_id=strategy_id,
            strategy_name=strategy.name,
            baseline_run_id=baseline_run.id,
            baseline_run_name=baseline_run.run_name,
            baseline_run_type=baseline_run.run_type,
            comparison_run_id=None,
            comparison_run_name=None,
            comparison_run_type=None,
            verdict="insufficient_data",
            drift_score=None,
            severity="low",
            primary_concern=(
                "No paper or shadow run uploaded yet. Upload a paper run to compare "
                "research behavior against live-like behavior."
            ),
            metrics=[],
            top_concerns=[],
            suggested_actions=[
                "Upload a paper or live-like run with metrics_json populated to enable drift comparison."
            ],
            blockers=[],
            missing_metric_keys=KEY_METRICS,
            missing_metric_coverage=1.0,
            generated_at=now,
            disclaimer=DISCLAIMER,
        )

    # Both runs present — compute metric drifts
    baseline_metrics = baseline_run.metrics_json or {}
    comparison_metrics = comparison_run.metrics_json or {}

    drift_metrics: list[ShadowDriftMetric] = []
    for key in KEY_METRICS:
        bv = _get_metric(baseline_metrics, key)
        cv = _get_metric(comparison_metrics, key)
        drift_metrics.append(_compute_single_metric_drift(key, bv, cv))

    drift_score, severity, verdict = compute_shadow_drift_score(drift_metrics)

    missing_keys = [m.key for m in drift_metrics if m.status == "missing"]
    missing_coverage = len(missing_keys) / len(KEY_METRICS) if KEY_METRICS else 0.0

    top_concerns = _build_top_concerns(drift_metrics)
    suggested_actions = _build_suggested_actions(drift_metrics, verdict, missing_keys)
    blockers = _build_blockers(drift_metrics, verdict)

    primary_concern: Optional[str] = top_concerns[0] if top_concerns else None

    return ShadowMonitorData(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        baseline_run_id=baseline_run.id,
        baseline_run_name=baseline_run.run_name,
        baseline_run_type=baseline_run.run_type,
        comparison_run_id=comparison_run.id,
        comparison_run_name=comparison_run.run_name,
        comparison_run_type=comparison_run.run_type,
        verdict=verdict,
        drift_score=drift_score,
        severity=severity,
        primary_concern=primary_concern,
        metrics=drift_metrics,
        top_concerns=top_concerns,
        suggested_actions=suggested_actions,
        blockers=blockers,
        missing_metric_keys=missing_keys,
        missing_metric_coverage=missing_coverage,
        generated_at=now,
        disclaimer=DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Public: wrapper
# ---------------------------------------------------------------------------

def generate_shadow_monitor_summary(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    baseline_run_id: Optional[uuid.UUID] = None,
    comparison_run_id: Optional[uuid.UUID] = None,
) -> ShadowMonitorData:
    """Wrapper around compare_backtest_to_paper.

    Returns ShadowMonitorData for the given strategy.
    """
    return compare_backtest_to_paper(
        strategy_id,
        db,
        baseline_run_id=baseline_run_id,
        comparison_run_id=comparison_run_id,
    )


# ---------------------------------------------------------------------------
# Public: report generation
# ---------------------------------------------------------------------------

def generate_shadow_report(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    format: str = "json",
    baseline_run_id: Optional[uuid.UUID] = None,
    comparison_run_id: Optional[uuid.UUID] = None,
) -> str:
    """Generate a shadow monitor report as JSON or Markdown.

    Args:
        strategy_id: UUID of the strategy.
        db: SQLAlchemy session.
        format: "json" or "markdown".
        baseline_run_id: Optional baseline run override.
        comparison_run_id: Optional comparison run override.

    Returns:
        Report as a string (JSON or Markdown).
    """
    data = compare_backtest_to_paper(
        strategy_id,
        db,
        baseline_run_id=baseline_run_id,
        comparison_run_id=comparison_run_id,
    )

    if format == "json":
        return _to_json_report(data)
    elif format == "markdown":
        return _to_markdown_report(data)
    else:
        raise ValueError(f"Unsupported report format: {format!r}. Use 'json' or 'markdown'.")


def _to_json_report(data: ShadowMonitorData) -> str:
    """Serialize ShadowMonitorData to a JSON string."""
    def _metric_dict(m: ShadowDriftMetric) -> dict:
        return {
            "key": m.key,
            "label": m.label,
            "baseline_value": m.baseline_value,
            "comparison_value": m.comparison_value,
            "absolute_delta": m.absolute_delta,
            "percent_delta": m.percent_delta,
            "status": m.status,
            "severity": m.severity,
            "explanation": m.explanation,
        }

    report = {
        "strategy_id": str(data.strategy_id),
        "strategy_name": data.strategy_name,
        "baseline_run": {
            "run_id": str(data.baseline_run_id) if data.baseline_run_id else None,
            "run_name": data.baseline_run_name,
            "run_type": data.baseline_run_type,
        },
        "comparison_run": {
            "run_id": str(data.comparison_run_id) if data.comparison_run_id else None,
            "run_name": data.comparison_run_name,
            "run_type": data.comparison_run_type,
        },
        "verdict": data.verdict,
        "drift_score": data.drift_score,
        "severity": data.severity,
        "primary_concern": data.primary_concern,
        "metrics": [_metric_dict(m) for m in data.metrics],
        "top_concerns": data.top_concerns,
        "suggested_actions": data.suggested_actions,
        "blockers": data.blockers,
        "missing_metric_keys": data.missing_metric_keys,
        "missing_metric_coverage": data.missing_metric_coverage,
        "generated_at": data.generated_at.isoformat(),
        "disclaimer": data.disclaimer,
    }
    return json.dumps(report, indent=2)


def _to_markdown_report(data: ShadowMonitorData) -> str:
    """Serialize ShadowMonitorData to a Markdown string."""
    lines: list[str] = []

    lines.append(f"# Shadow Monitor Report: {data.strategy_name}")
    lines.append("")
    lines.append(f"**Generated:** {data.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"**Verdict:** `{data.verdict.upper()}`")
    if data.drift_score is not None:
        lines.append(f"**Drift Score:** {data.drift_score:.1f} / 100")
    lines.append(f"**Severity:** {data.severity}")
    lines.append("")

    lines.append("## Runs")
    baseline_name = data.baseline_run_name or "—"
    baseline_type = data.baseline_run_type or "—"
    comparison_name = data.comparison_run_name or "—"
    comparison_type = data.comparison_run_type or "—"
    lines.append(f"- **Baseline:** {baseline_name} ({baseline_type})")
    lines.append(f"- **Comparison:** {comparison_name} ({comparison_type})")
    lines.append("")

    if data.primary_concern:
        lines.append("## Primary Concern")
        lines.append(data.primary_concern)
        lines.append("")

    if data.metrics:
        lines.append("## Metric Drift Comparison")
        lines.append("")
        lines.append(
            "| Metric | Baseline | Comparison | Delta | Status | Explanation |"
        )
        lines.append("|--------|----------|------------|-------|--------|-------------|")
        for m in data.metrics:
            bv = f"{m.baseline_value:.4f}" if m.baseline_value is not None else "—"
            cv = f"{m.comparison_value:.4f}" if m.comparison_value is not None else "—"
            delta = f"{m.absolute_delta:+.4f}" if m.absolute_delta is not None else "—"
            status_badge = m.status.upper()
            # Truncate long explanations for table readability
            expl = m.explanation[:80] + "..." if len(m.explanation) > 80 else m.explanation
            lines.append(f"| {m.label} | {bv} | {cv} | {delta} | {status_badge} | {expl} |")
        lines.append("")

    if data.top_concerns:
        lines.append("## Top Concerns")
        for concern in data.top_concerns:
            lines.append(f"- {concern}")
        lines.append("")

    if data.blockers:
        lines.append("## Blockers")
        for b in data.blockers:
            lines.append(f"- {b}")
        lines.append("")

    if data.suggested_actions:
        lines.append("## Suggested Actions")
        for a in data.suggested_actions:
            lines.append(f"- {a}")
        lines.append("")

    if data.missing_metric_keys:
        lines.append("## Missing Metrics")
        lines.append(f"Coverage gap: {data.missing_metric_coverage*100:.0f}% of key metrics not logged.")
        lines.append(f"Missing: {', '.join(data.missing_metric_keys)}")
        lines.append("")

    lines.append("---")
    lines.append(f"*{data.disclaimer}*")

    return "\n".join(lines)
