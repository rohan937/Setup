"""Backtest Reality Check service (M8 + M13).

Purely deterministic — no AI, no database access, no external calls.

Takes a ``StrategyRun`` ORM object and an optional ``DataEvidenceSummary``
(already computed by the route from any linked dataset snapshot) and returns
an ``AuditResult`` dataclass describing realism concerns, per-category
subscores, a trust score, and a hedged plain-language summary.

Checks implemented (v1 — M8):
  A. Transaction cost realism
  B. Fill model realism
  C. Borrow / short-selling realism
  D. Sample size / trade count adequacy
  E. Turnover realism
  F. Data evidence integration
  G. Max drawdown sanity
  H. Metric plausibility (Sharpe, return, volatility)

New in v2 (M13):
  I. Cost sensitivity analysis — estimates adjusted performance under cost scenarios
  J. Fill realism analysis   — detailed fill assumption checks + fill_realism_level
  K. Fragility summary        — rolls I + J into an overall fragility assessment
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.strategy_run import StrategyRun
    from app.schemas.strategy import DataEvidenceSummary


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Cost scenarios to estimate (bps).
_COST_SCENARIOS_BPS: list[float] = [5.0, 10.0, 15.0, 25.0, 50.0]

# ---------------------------------------------------------------------------
# Penalty table
# ---------------------------------------------------------------------------

_SEVERITY_PENALTY: dict[str, int] = {
    "critical": 25,
    "high": 15,
    "medium": 8,
    "low": 3,
}

# Ordered most-severe → least-severe (for worst-severity lookup).
_SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]

# Maps issue_type → which subscore it penalises.
# Issues not listed here only affect the overall trust_score.
_ISSUE_SUBSCORE_MAP: dict[str, str] = {
    # M8
    "missing_transaction_cost": "cost_realism_score",
    "zero_transaction_cost": "cost_realism_score",
    "high_turnover_low_cost": "cost_realism_score",
    "high_turnover": "cost_realism_score",
    "missing_fill_model": "fill_realism_score",
    "close_fill_model": "fill_realism_score",
    "missing_borrow_cost": "borrow_realism_score",
    "zero_borrow_cost": "borrow_realism_score",
    "low_data_quality": "data_quality_score",
    "no_data_snapshot": "data_quality_score",
    "critical_data_issue": "data_quality_score",
    # M13 — cost sensitivity
    "high_cost_fragility": "cost_realism_score",
    "medium_cost_fragility": "cost_realism_score",
    # M13 — fill realism
    "same_bar_fill": "fill_realism_score",
    "mid_fill_no_slippage": "fill_realism_score",
    "high_participation_rate": "fill_realism_score",
    "elevated_participation_rate": "fill_realism_score",
    "missing_liquidity_filter": "liquidity_realism_score",
    "missing_execution_timing": "fill_realism_score",
    "high_trade_count_simple_fill": "fill_realism_score",
}


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AuditIssue:
    issue_type: str
    severity: str
    title: str
    description: str
    evidence_json: dict | None = None
    suggested_check: str | None = None


@dataclass
class AuditResult:
    issues: list[AuditIssue]
    trust_score: int
    lookahead_risk_score: int
    cost_realism_score: int
    fill_realism_score: int
    liquidity_realism_score: int
    borrow_realism_score: int
    data_quality_score: int
    overall_status: str
    summary: str
    # M13: structured JSON blobs — None when input data is insufficient.
    cost_sensitivity_json: dict | None = None
    fill_realism_json: dict | None = None
    fragility_summary_json: dict | None = None
    # M36: extended v3 analysis blobs.
    cost_sensitivity_sweep_json: dict | None = None
    fill_sensitivity_json: dict | None = None
    penalty_attribution_json: dict | None = None
    improvement_checks_json: dict | None = None


# ---------------------------------------------------------------------------
# Internal helpers (shared)
# ---------------------------------------------------------------------------

def _penalty(severity: str) -> int:
    return _SEVERITY_PENALTY.get(severity, 0)


def _compute_trust_score(issues: list[AuditIssue]) -> int:
    score = 100
    for issue in issues:
        score -= _penalty(issue.severity)
    return max(0, score)


def _compute_subscore(issues: list[AuditIssue], subscore_key: str) -> int:
    score = 100
    for issue in issues:
        if _ISSUE_SUBSCORE_MAP.get(issue.issue_type) == subscore_key:
            score -= _penalty(issue.severity)
    return max(0, score)


def _overall_status(trust_score: int) -> str:
    if trust_score >= 90:
        return "excellent"
    if trust_score >= 75:
        return "good"
    if trust_score >= 50:
        return "review"
    if trust_score >= 25:
        return "weak"
    return "unreliable"


def _build_summary(issues: list[AuditIssue], trust_score: int, status: str) -> str:
    if not issues:
        return (
            "No realism concerns were detected in this backtest configuration. "
            "The logged assumptions appear reasonable based on the available evidence."
        )

    n_high_plus = sum(1 for i in issues if i.severity in ("critical", "high"))
    n_medium = sum(1 for i in issues if i.severity == "medium")
    total = len(issues)

    if status == "excellent":
        note = issues[0].title.lower() if issues else "a minor note"
        return (
            f"This backtest appears well-configured. {note.capitalize()} was noted "
            f"but no significant realism concerns were detected overall."
        )
    if status == "good":
        note = issues[0].title.lower()
        return (
            f"This backtest looks reasonable overall. {note.capitalize()} may warrant "
            f"a closer look, but no critical realism concerns were detected."
        )
    if status == "review":
        titles = [i.title.lower() for i in issues[:2]]
        items = "; ".join(titles)
        return (
            f"This backtest has {total} configuration note{'s' if total != 1 else ''} "
            f"that may warrant review: {items}. "
            f"These could make results appear more favorable than may be achievable "
            f"in live trading, and require further investigation."
        )
    if status == "weak":
        return (
            f"{n_high_plus} high-severity concern{'s' if n_high_plus != 1 else ''} "
            f"and {n_medium} medium concern{'s' if n_medium != 1 else ''} were noted. "
            f"Several assumptions in this backtest could make results appear more "
            f"favorable than they may be in live conditions. These areas are flagged "
            f"for review before drawing conclusions from this run."
        )
    # unreliable
    return (
        f"Multiple significant realism concerns were noted ({total} total, "
        f"{n_high_plus} high-severity). These configurations may make backtest "
        f"results difficult to reproduce or validate in live conditions. "
        f"A thorough review of assumptions is recommended before relying on "
        f"this run's metrics."
    )


def _get_float(d: dict, *keys: str) -> float | None:
    """Return first matching key value as float, or None."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def _get_bool(d: dict, *keys: str) -> bool | None:
    """Return first matching key as bool, or None."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                return v.lower() in ("true", "yes", "1")
    return None


# ---------------------------------------------------------------------------
# M8 check functions
# ---------------------------------------------------------------------------

def _check_transaction_costs(
    assumptions: dict,
    metrics: dict,
    issues: list[AuditIssue],
) -> None:
    """A. Transaction cost realism."""
    txn_cost = _get_float(assumptions, "transaction_cost_bps", "transaction_cost")
    turnover = _get_float(metrics, "turnover", "annual_turnover")

    if txn_cost is None:
        issues.append(AuditIssue(
            issue_type="missing_transaction_cost",
            severity="medium",
            title="Transaction cost not specified",
            description=(
                "No transaction_cost_bps was found in assumptions_json. "
                "Omitting transaction costs may make backtest returns appear "
                "more favorable than they would be in live trading."
            ),
            evidence_json={"assumptions_keys": sorted(assumptions.keys())},
            suggested_check=(
                "Add transaction_cost_bps (in basis points) to assumptions_json. "
                "A typical equity round-trip is 5–20 bps."
            ),
        ))
    elif txn_cost == 0:
        issues.append(AuditIssue(
            issue_type="zero_transaction_cost",
            severity="high",
            title="Zero transaction cost assumed",
            description=(
                "transaction_cost_bps is set to 0, which means no trading friction "
                "is modelled. This could make results appear more favorable than they "
                "would be in a live environment with real execution costs."
            ),
            evidence_json={"transaction_cost_bps": 0},
            suggested_check=(
                "Set transaction_cost_bps to a realistic value. "
                "Even a conservative 1–5 bps assumption is more defensible than zero."
            ),
        ))
    elif txn_cost < 1.0:
        issues.append(AuditIssue(
            issue_type="missing_transaction_cost",
            severity="medium",
            title="Unusually low transaction cost",
            description=(
                f"transaction_cost_bps is set to {txn_cost}, which is below 1 bps "
                "and may not fully capture slippage, spread, and commissions."
            ),
            evidence_json={"transaction_cost_bps": txn_cost},
            suggested_check=(
                "Verify that transaction_cost_bps accounts for all trading friction "
                "including spread, market impact, and commissions."
            ),
        ))

    # High turnover with low cost: flag separately even if cost is non-zero.
    if (
        turnover is not None
        and turnover > 1.0
        and txn_cost is not None
        and 0 < txn_cost < 3.0
    ):
        issues.append(AuditIssue(
            issue_type="high_turnover_low_cost",
            severity="medium",
            title="High turnover with low transaction cost assumption",
            description=(
                f"Turnover of {turnover:.1f}x is noted alongside a transaction cost "
                f"of {txn_cost} bps. High-turnover strategies are more sensitive to "
                f"execution costs, and a low cost assumption could make results "
                f"appear more favorable than achievable in practice."
            ),
            evidence_json={"turnover": turnover, "transaction_cost_bps": txn_cost},
            suggested_check=(
                "For strategies with turnover above 1×, consider modelling "
                "market impact and slippage in addition to commissions."
            ),
        ))


def _check_fill_model(
    assumptions: dict,
    issues: list[AuditIssue],
) -> None:
    """B. Fill model realism (M8 basic checks — M13 adds more via fill realism analysis)."""
    fill_model = assumptions.get("fill_model")
    slippage = _get_float(assumptions, "slippage_bps", "slippage")

    if fill_model is None:
        issues.append(AuditIssue(
            issue_type="missing_fill_model",
            severity="medium",
            title="Fill model not specified",
            description=(
                "No fill_model was found in assumptions_json. Without a defined fill "
                "model it is unclear how executions are assumed to occur, which could "
                "introduce optimism bias into the backtest."
            ),
            evidence_json={"assumptions_keys": sorted(assumptions.keys())},
            suggested_check=(
                "Add fill_model to assumptions_json (e.g. 'close', 'open', 'vwap', "
                "'mid') so the execution assumption is explicit and auditable."
            ),
        ))
        return

    fill_model_str = str(fill_model).lower()
    if fill_model_str in ("close", "close-to-close", "eod"):
        issues.append(AuditIssue(
            issue_type="close_fill_model",
            severity="medium",
            title="Close-price fill model may overstate returns",
            description=(
                f"fill_model is set to '{fill_model}'. Filling orders at the closing "
                "price assumes trades execute at a price that may already incorporate "
                "the signal's information, which could overstate achievable returns."
            ),
            evidence_json={"fill_model": fill_model},
            suggested_check=(
                "Consider using an open-of-next-day or VWAP fill model to better "
                "reflect realistic execution. If close fills are intentional, "
                "document the rationale."
            ),
        ))
    elif fill_model_str in ("open", "next_open", "next-open") and slippage is None:
        issues.append(AuditIssue(
            issue_type="close_fill_model",
            severity="medium",
            title="Open fill without slippage model",
            description=(
                f"fill_model is set to '{fill_model}' but no slippage_bps was "
                "specified. Open-price fills without slippage may not fully capture "
                "market impact for larger positions."
            ),
            evidence_json={"fill_model": fill_model, "slippage_bps": None},
            suggested_check=(
                "Add slippage_bps to assumptions_json when using open-price fills, "
                "particularly for strategies with meaningful position sizes."
            ),
        ))


def _check_borrow_costs(
    assumptions: dict,
    issues: list[AuditIssue],
) -> None:
    """C. Borrow / short-selling realism."""
    short_enabled = _get_bool(assumptions, "short_enabled", "allow_short", "short_selling")
    borrow_rate = _get_float(assumptions, "borrow_rate", "borrow_cost", "borrow_cost_bps")

    if short_enabled is not True:
        return  # No short selling assumed — no borrow cost checks needed.

    if borrow_rate is None:
        issues.append(AuditIssue(
            issue_type="missing_borrow_cost",
            severity="medium",
            title="Short selling enabled but no borrow cost specified",
            description=(
                "short_enabled is true but no borrow_rate was found in "
                "assumptions_json. Borrow costs can significantly reduce returns "
                "for short-selling strategies and should be modelled explicitly."
            ),
            evidence_json={"short_enabled": True, "borrow_rate": None},
            suggested_check=(
                "Add borrow_rate (annualised, e.g. 0.005 = 50 bps/yr) to "
                "assumptions_json. Hard-to-borrow names can carry borrow costs "
                "of 5–30%+ per year."
            ),
        ))
    elif borrow_rate == 0:
        issues.append(AuditIssue(
            issue_type="zero_borrow_cost",
            severity="high",
            title="Zero borrow cost with short selling enabled",
            description=(
                "short_enabled is true and borrow_rate is 0. Assuming zero borrow "
                "cost for short positions could overstate returns, especially for "
                "high-demand or hard-to-borrow securities."
            ),
            evidence_json={"short_enabled": True, "borrow_rate": 0},
            suggested_check=(
                "Set borrow_rate to at least a conservative estimate (e.g. 0.005 "
                "for 50 bps/yr). For strategies targeting small-cap or high-short-"
                "interest names, use higher estimates."
            ),
        ))


def _check_sample_size(
    metrics: dict,
    assumptions: dict,
    issues: list[AuditIssue],
) -> None:
    """D. Sample size / trade count adequacy."""
    sharpe = _get_float(metrics, "sharpe", "sharpe_ratio")
    trade_count = _get_float(
        metrics, "trade_count", "num_trades", "n_trades", "total_trades"
    )

    if trade_count is None:
        issues.append(AuditIssue(
            issue_type="missing_trade_count",
            severity="low",
            title="Trade count not logged",
            description=(
                "No trade_count metric was found. Without knowing the number of "
                "trades it is difficult to assess whether the strategy has enough "
                "observations to support the reported performance metrics."
            ),
            evidence_json={"metrics_keys": sorted(metrics.keys())},
            suggested_check=(
                "Add trade_count (total number of round-trip trades) to metrics_json "
                "when logging backtest runs."
            ),
        ))
        return  # Can't check trade count adequacy without the value.

    if sharpe is not None and sharpe > 2.0 and trade_count < 50:
        issues.append(AuditIssue(
            issue_type="insufficient_trade_count",
            severity="high",
            title="High Sharpe ratio with very few trades",
            description=(
                f"Sharpe ratio of {sharpe:.2f} alongside only {int(trade_count)} trades "
                "may indicate an insufficiently sampled backtest. High Sharpe ratios "
                "based on few observations could reflect noise rather than a genuine edge."
            ),
            evidence_json={"sharpe": sharpe, "trade_count": trade_count, "threshold_trades": 50},
            suggested_check=(
                "Consider extending the backtest period or verifying that the "
                "strategy has sufficient trade observations to support statistical "
                "confidence in the reported Sharpe ratio."
            ),
        ))
    elif sharpe is not None and sharpe > 1.5 and trade_count < 100:
        issues.append(AuditIssue(
            issue_type="insufficient_trade_count",
            severity="medium",
            title="Elevated Sharpe ratio with limited trade count",
            description=(
                f"Sharpe ratio of {sharpe:.2f} alongside {int(trade_count)} trades "
                "may indicate limited statistical power. Performance metrics based on "
                "fewer than 100 trades require careful interpretation."
            ),
            evidence_json={"sharpe": sharpe, "trade_count": trade_count, "threshold_trades": 100},
            suggested_check=(
                "Consider whether the backtest period is long enough to generate "
                "sufficient trade observations to support the reported Sharpe ratio."
            ),
        ))


def _check_turnover(
    metrics: dict,
    issues: list[AuditIssue],
) -> None:
    """E. Turnover realism."""
    turnover = _get_float(metrics, "turnover", "annual_turnover")
    if turnover is None:
        return

    if turnover > 3.0:
        issues.append(AuditIssue(
            issue_type="high_turnover",
            severity="high",
            title="Extremely high portfolio turnover",
            description=(
                f"Annual turnover of {turnover:.1f}× is very high. Strategies with "
                "extreme turnover are sensitive to execution assumptions and may "
                "be difficult to implement at scale without significant market impact."
            ),
            evidence_json={"turnover": turnover, "threshold": 3.0},
            suggested_check=(
                "Verify that transaction cost and market impact assumptions are "
                "appropriate for a strategy with this level of turnover."
            ),
        ))
    elif turnover > 1.5:
        issues.append(AuditIssue(
            issue_type="high_turnover",
            severity="medium",
            title="High portfolio turnover",
            description=(
                f"Annual turnover of {turnover:.1f}× is elevated. Higher turnover "
                "increases sensitivity to execution assumptions and may require "
                "more realistic cost modelling."
            ),
            evidence_json={"turnover": turnover, "threshold": 1.5},
            suggested_check=(
                "Ensure that transaction costs, slippage, and market impact are "
                "adequately modelled for a strategy with this level of turnover."
            ),
        ))


def _check_data_evidence(
    data_evidence: "DataEvidenceSummary | None",
    issues: list[AuditIssue],
) -> None:
    """F. Data evidence integration."""
    if data_evidence is None:
        issues.append(AuditIssue(
            issue_type="no_data_snapshot",
            severity="low",
            title="No dataset snapshot linked",
            description=(
                "This run has no linked QuantFidelity dataset snapshot. "
                "Data quality cannot be assessed as part of the backtest audit."
            ),
            evidence_json=None,
            suggested_check=(
                "Link a dataset snapshot when logging runs (via dataset_snapshot_id) "
                "so that data health can be included in the backtest reality check."
            ),
        ))
        return

    ev = data_evidence
    if ev.health_score < 70:
        sev = "high" if ev.health_score < 50 else "medium"
        issues.append(AuditIssue(
            issue_type="low_data_quality",
            severity=sev,
            title=f"Data quality score is low ({ev.health_score}/100)",
            description=(
                f"The linked dataset snapshot '{ev.snapshot_label}' has a health "
                f"score of {ev.health_score}/100 with {ev.issue_count} issue"
                f"{'s' if ev.issue_count != 1 else ''} detected"
                f"{f' (worst: {ev.worst_severity})' if ev.worst_severity else ''}. "
                "Low data quality may affect the reliability of backtest metrics."
            ),
            evidence_json={
                "health_score": ev.health_score,
                "issue_count": ev.issue_count,
                "worst_severity": ev.worst_severity,
                "dataset_name": ev.dataset_name,
                "snapshot_label": ev.snapshot_label,
            },
            suggested_check=(
                "Review and resolve the data quality issues in the linked snapshot "
                "before drawing conclusions from this backtest run."
            ),
        ))
    elif ev.worst_severity == "critical":
        issues.append(AuditIssue(
            issue_type="critical_data_issue",
            severity="high",
            title="Critical data quality issue in linked snapshot",
            description=(
                f"The linked dataset snapshot '{ev.snapshot_label}' contains at "
                f"least one critical data quality issue (health score: "
                f"{ev.health_score}/100). Critical data issues may significantly "
                "affect backtest results even when the overall health score appears acceptable."
            ),
            evidence_json={
                "health_score": ev.health_score,
                "issue_count": ev.issue_count,
                "worst_severity": ev.worst_severity,
            },
            suggested_check=(
                "Resolve critical data quality issues in the linked snapshot. "
                "Critical issues (e.g. high < low price bars) can introduce "
                "spurious signal into backtests."
            ),
        ))


def _check_drawdown(
    metrics: dict,
    issues: list[AuditIssue],
) -> None:
    """G. Max drawdown sanity."""
    max_dd = _get_float(metrics, "max_drawdown", "maximum_drawdown")
    if max_dd is None:
        return

    abs_dd = abs(max_dd)
    if abs_dd > 0.5:
        issues.append(AuditIssue(
            issue_type="high_max_drawdown",
            severity="medium",
            title="Very large maximum drawdown",
            description=(
                f"Maximum drawdown of {max_dd:.1%} is notably large. This level of "
                "drawdown may indicate high strategy risk or potential data quality "
                "issues (e.g. fat-finger prices, survivorship bias)."
            ),
            evidence_json={"max_drawdown": max_dd, "threshold": -0.5},
            suggested_check=(
                "Verify that the drawdown figure is correct and that the backtest "
                "data does not contain anomalous price observations that may have "
                "inflated the observed drawdown."
            ),
        ))


def _check_metric_plausibility(
    metrics: dict,
    issues: list[AuditIssue],
) -> None:
    """H. Metric plausibility (Sharpe inflation, return, volatility)."""
    sharpe = _get_float(metrics, "sharpe", "sharpe_ratio")
    annual_return = _get_float(metrics, "annual_return", "annualised_return", "cagr")
    volatility = _get_float(metrics, "volatility", "annualised_vol", "annual_vol")

    if sharpe is not None:
        if sharpe > 4.0:
            sev = "high" if sharpe > 6.0 else "medium"
            issues.append(AuditIssue(
                issue_type="implausible_sharpe",
                severity=sev,
                title=f"Unusually high Sharpe ratio ({sharpe:.2f})",
                description=(
                    f"A Sharpe ratio of {sharpe:.2f} is exceptionally high for most "
                    "systematic strategies. This may indicate overfitting, look-ahead "
                    "bias, a very short backtest window, or an error in the metric "
                    "calculation."
                ),
                evidence_json={"sharpe": sharpe, "threshold": 4.0},
                suggested_check=(
                    "Verify the Sharpe calculation (annualisation factor, "
                    "risk-free rate assumption). Consider out-of-sample validation "
                    "and checking for inadvertent look-ahead in the signal."
                ),
            ))

    if annual_return is not None and annual_return > 1.0:
        issues.append(AuditIssue(
            issue_type="implausible_return",
            severity="medium",
            title=f"Annual return above 100% ({annual_return:.0%})",
            description=(
                f"An annual return of {annual_return:.0%} is extremely high and "
                "may indicate overfitting, look-ahead bias, an error in the return "
                "calculation, or leverage that has not been disclosed in the "
                "strategy assumptions."
            ),
            evidence_json={"annual_return": annual_return, "threshold": 1.0},
            suggested_check=(
                "Verify the return calculation methodology and check for "
                "implicit leverage. Returns above 100% per year are uncommon "
                "for systematic strategies without significant leverage."
            ),
        ))

    if (
        volatility is not None
        and volatility <= 0
        and annual_return is not None
        and annual_return != 0
    ):
        issues.append(AuditIssue(
            issue_type="zero_volatility",
            severity="high",
            title="Zero or negative volatility with non-zero return",
            description=(
                "Volatility is reported as zero or negative alongside a non-zero "
                "return. This is mathematically inconsistent and may indicate an "
                "error in the metric calculation or in the data used to compute returns."
            ),
            evidence_json={"volatility": volatility, "annual_return": annual_return},
            suggested_check=(
                "Review the volatility calculation. Zero volatility typically "
                "indicates a bug in the performance analytics code."
            ),
        ))


# ---------------------------------------------------------------------------
# M13 — Cost sensitivity analysis
# ---------------------------------------------------------------------------

def _analyze_cost_sensitivity(
    assumptions: dict,
    metrics: dict,
) -> dict:
    """I. Estimate how sensitive reported performance is to transaction cost levels.

    This is an approximation only — not a full re-backtest.  All outputs are
    labelled as estimates.  The function never raises; it returns a partial
    result with warnings when required inputs are missing.

    Returns
    -------
    dict
        Keys: assumed_cost_bps, turnover, base_annual_return, base_sharpe,
              scenarios, warnings, cost_fragility_level.
    """
    txn_cost = _get_float(assumptions, "transaction_cost_bps", "transaction_cost")
    assumed_cost_bps: float = txn_cost if txn_cost is not None else 0.0

    annual_return = _get_float(metrics, "annual_return", "annualised_return", "cagr")
    sharpe = _get_float(metrics, "sharpe", "sharpe_ratio")
    volatility = _get_float(metrics, "volatility", "annualised_vol", "annual_vol")
    turnover = _get_float(metrics, "turnover", "annual_turnover")
    slippage = _get_float(assumptions, "slippage_bps", "slippage")

    warnings: list[str] = [
        "These are estimates only — not a full re-backtest.  Treat as indicative."
    ]

    # Can't estimate without turnover.
    if turnover is None:
        warnings.append(
            "turnover not provided — cost sensitivity cannot be estimated. "
            "Add turnover (annual_turnover) to metrics_json to enable this analysis."
        )
        return {
            "assumed_cost_bps": assumed_cost_bps,
            "turnover": None,
            "base_annual_return": annual_return,
            "base_sharpe": sharpe,
            "scenarios": [],
            "warnings": warnings,
            "cost_fragility_level": "unknown",
        }

    # Can't estimate without at least return or sharpe.
    if annual_return is None and sharpe is None:
        warnings.append(
            "annual_return and sharpe not provided — cannot estimate adjusted performance."
        )
        return {
            "assumed_cost_bps": assumed_cost_bps,
            "turnover": turnover,
            "base_annual_return": None,
            "base_sharpe": None,
            "scenarios": [],
            "warnings": warnings,
            "cost_fragility_level": "unknown",
        }

    # Infer a volatility proxy for Sharpe approximation when volatility is absent.
    vol_proxy: float | None = None
    if volatility is not None and volatility > 0:
        vol_proxy = volatility
    elif (
        sharpe is not None
        and annual_return is not None
        and sharpe != 0
        and annual_return != 0
    ):
        # Rough estimate: vol ≈ annual_return / sharpe
        inferred = annual_return / sharpe
        if inferred > 0:
            vol_proxy = inferred
            warnings.append(
                "volatility not provided — adjusted Sharpe is approximated from "
                "annual_return / sharpe ratio.  Estimate may be less accurate."
            )

    if slippage is not None and slippage > 0:
        warnings.append(
            f"slippage_bps={slippage:.1f} is separately specified in assumptions. "
            "Cost scenarios below vary transaction_cost_bps only; total cost friction "
            "may be higher if slippage is additive."
        )

    # Build scenario set: always include assumed_cost_bps + standard tiers.
    scenario_bps_set: set[float] = {assumed_cost_bps} | set(_COST_SCENARIOS_BPS)
    scenario_bps_list = sorted(scenario_bps_set)

    scenarios: list[dict] = []
    for cost_bps in scenario_bps_list:
        # Incremental drag = extra cost vs baseline, applied each turn of turnover.
        incremental_drag = turnover * (cost_bps - assumed_cost_bps) / 10_000

        adj_return: float | None = None
        if annual_return is not None:
            adj_return = annual_return - incremental_drag

        adj_sharpe: float | None = None
        if vol_proxy is not None and vol_proxy > 0 and adj_return is not None:
            adj_sharpe = adj_return / vol_proxy
        elif sharpe is not None and annual_return is not None and annual_return != 0:
            # Secondary approximation: scale sharpe by the ratio of adjusted to base return.
            adj_sharpe = sharpe * (adj_return / annual_return) if adj_return is not None else None

        sharpe_delta: float | None = None
        if adj_sharpe is not None and sharpe is not None:
            sharpe_delta = adj_sharpe - sharpe

        scenarios.append({
            "cost_bps": cost_bps,
            "incremental_cost_drag": round(incremental_drag, 6),
            "adjusted_annual_return": round(adj_return, 6) if adj_return is not None else None,
            "adjusted_sharpe": round(adj_sharpe, 4) if adj_sharpe is not None else None,
            "sharpe_delta": round(sharpe_delta, 4) if sharpe_delta is not None else None,
        })

    # Determine fragility level from Sharpe thresholds.
    fragility = "low"
    sharpe_at: dict[float, float | None] = {}
    for sc in scenarios:
        if sc["adjusted_sharpe"] is not None:
            sharpe_at[sc["cost_bps"]] = sc["adjusted_sharpe"]

    if not sharpe_at:
        fragility = "unknown"
    else:
        sharpe_10 = sharpe_at.get(10.0)
        sharpe_25 = sharpe_at.get(25.0)
        if sharpe_10 is not None and sharpe_10 < 1.0:
            fragility = "high"
        elif sharpe_25 is not None and sharpe_25 < 1.0:
            fragility = "medium"

    return {
        "assumed_cost_bps": assumed_cost_bps,
        "turnover": turnover,
        "base_annual_return": annual_return,
        "base_sharpe": sharpe,
        "scenarios": scenarios,
        "warnings": warnings,
        "cost_fragility_level": fragility,
    }


# ---------------------------------------------------------------------------
# M13 — Fill realism analysis
# ---------------------------------------------------------------------------

_CLOSE_FILLS = frozenset({"close", "close-to-close", "eod", "same_close", "same-close"})
_SAME_BAR_FILLS = frozenset({"same_bar", "same-bar", "intrabar"})
_MID_FILLS = frozenset({"mid", "midpoint", "mid_price"})
_SIMPLE_FILLS = frozenset({"close", "open", "mid", "midpoint"})


def _analyze_fill_realism(
    assumptions: dict,
    metrics: dict,
) -> dict:
    """J. Detailed fill realism analysis.

    Examines fill_model, slippage_bps, execution_timing, participation_rate,
    liquidity_filter, trade_count, and turnover to produce a structured set
    of findings and an overall fill_realism_level.

    Returns
    -------
    dict
        Keys: fill_model, slippage_bps, execution_timing, participation_rate,
              liquidity_filter_present, fill_realism_level, findings.
    """
    fill_model = assumptions.get("fill_model")
    slippage = _get_float(assumptions, "slippage_bps", "slippage")
    execution_timing = assumptions.get("execution_timing")
    participation_rate = _get_float(assumptions, "participation_rate")
    liquidity_filter = assumptions.get("liquidity_filter")
    turnover = _get_float(metrics, "turnover", "annual_turnover")
    trade_count = _get_float(metrics, "trade_count", "num_trades", "n_trades", "total_trades")

    liquidity_filter_present = liquidity_filter is not None
    findings: list[dict] = []

    # ------------------------------------------------------------------ #
    # Fill model checks
    # ------------------------------------------------------------------ #
    if fill_model is None:
        # M8 already creates a missing_fill_model issue; capture in JSON for completeness.
        findings.append({
            "code": "missing_fill_model",
            "severity": "medium",
            "message": "fill_model not specified — execution assumption is ambiguous.",
            "suggested_check": (
                "Add fill_model to assumptions_json (e.g. 'vwap', 'open', 'arrival')."
            ),
        })
    else:
        fm = str(fill_model).lower()

        # Same-bar fill — worst-case look-ahead risk.
        if fm in _SAME_BAR_FILLS:
            findings.append({
                "code": "same_bar_fill",
                "severity": "high",
                "message": (
                    f"fill_model='{fill_model}' fills within the same bar as signal "
                    "generation — strong same-bar execution risk that may not be "
                    "achievable in practice."
                ),
                "suggested_check": (
                    "Use next-bar, next-open, or arrival-price fill models to avoid "
                    "same-bar execution. Same-bar fills may represent a form of "
                    "look-ahead bias in the backtest."
                ),
            })

        # Same-close fill — already checked in M8 via close_fill_model; replicate in JSON.
        elif fm in _CLOSE_FILLS:
            findings.append({
                "code": "same_close_fill",
                "severity": "medium",
                "message": (
                    f"fill_model='{fill_model}' may execute at the closing price used "
                    "to generate the signal, which is difficult to achieve in practice."
                ),
                "suggested_check": (
                    "Consider next-open, VWAP, or arrival-price fills. "
                    "If close fills are intentional, document the rationale."
                ),
            })

        # Mid fill without slippage.
        if fm in _MID_FILLS and slippage is None:
            findings.append({
                "code": "mid_fill_no_slippage",
                "severity": "medium",
                "message": (
                    f"fill_model='{fill_model}' (mid-price) with no slippage_bps — "
                    "mid-price fills are rarely achievable; the bid-ask spread is a "
                    "minimum cost that should be modelled explicitly."
                ),
                "suggested_check": (
                    "Add slippage_bps to account for the half-spread when using "
                    "mid-price fills (e.g. 1–3 bps for liquid equities)."
                ),
            })

        # Missing slippage for non-close fills (informational).
        if slippage is None and fm not in (_CLOSE_FILLS | _SAME_BAR_FILLS):
            findings.append({
                "code": "missing_slippage",
                "severity": "low",
                "message": "slippage_bps not specified in assumptions_json.",
                "suggested_check": (
                    "Add slippage_bps (e.g. 1–5 bps for liquid equities) to "
                    "assumptions_json to make execution friction explicit."
                ),
            })

        # High trade count with simplistic fill model.
        if (
            trade_count is not None
            and trade_count > 500
            and fm in _SIMPLE_FILLS
        ):
            findings.append({
                "code": "high_trade_count_simple_fill",
                "severity": "low",
                "message": (
                    f"trade_count={int(trade_count)} is high with fill_model='{fill_model}' — "
                    "market impact may be underestimated for high-frequency strategies."
                ),
                "suggested_check": (
                    "Consider adding a market-impact model (e.g. linear or square-root "
                    "impact) for strategies with very high trade counts."
                ),
            })

    # ------------------------------------------------------------------ #
    # Participation rate checks
    # ------------------------------------------------------------------ #
    if participation_rate is not None:
        if participation_rate > 0.5:
            findings.append({
                "code": "high_participation_rate",
                "severity": "high",
                "message": (
                    f"participation_rate={participation_rate:.0%} is very high — "
                    "strategies trading more than 50% of daily volume may face "
                    "significant market impact in live execution."
                ),
                "suggested_check": (
                    "Reduce participation_rate to ≤20% or add an explicit market-"
                    "impact model. Verify position sizes are achievable without "
                    "moving the market."
                ),
            })
        elif participation_rate > 0.2:
            findings.append({
                "code": "elevated_participation_rate",
                "severity": "medium",
                "message": (
                    f"participation_rate={participation_rate:.0%} is above 20% — "
                    "may face material market impact at scale."
                ),
                "suggested_check": (
                    "Verify that position sizes are achievable without significant "
                    "market impact at this participation rate."
                ),
            })

    # ------------------------------------------------------------------ #
    # Liquidity filter check (high turnover without filter)
    # ------------------------------------------------------------------ #
    if not liquidity_filter_present and turnover is not None and turnover > 1.5:
        findings.append({
            "code": "missing_liquidity_filter",
            "severity": "medium",
            "message": (
                f"No liquidity_filter specified alongside turnover={turnover:.1f}× — "
                "high-turnover strategies may inadvertently include illiquid names."
            ),
            "suggested_check": (
                "Add a liquidity_filter (e.g. minimum average_daily_volume) to the "
                "universe or assumptions to exclude names that cannot be traded at scale."
            ),
        })

    # ------------------------------------------------------------------ #
    # Missing execution_timing (informational)
    # ------------------------------------------------------------------ #
    if execution_timing is None:
        findings.append({
            "code": "missing_execution_timing",
            "severity": "low",
            "message": "execution_timing not specified in assumptions_json.",
            "suggested_check": (
                "Specify execution_timing (e.g. 'open', 'close', 'intraday_vwap') "
                "to make the timing of execution explicit and auditable."
            ),
        })

    # ------------------------------------------------------------------ #
    # Compute fill_realism_level
    # ------------------------------------------------------------------ #
    # Unknown when fill_model is missing (can't assess without it).
    if fill_model is None:
        fill_level = "unknown"
    else:
        has_high = any(f["severity"] == "high" for f in findings)
        medium_count = sum(1 for f in findings if f["severity"] == "medium")

        if has_high:
            fill_level = "weak"
        elif medium_count >= 2:
            fill_level = "review"
        elif medium_count == 1:
            fill_level = "review"
        elif slippage is not None and execution_timing is not None:
            fill_level = "strong"
        else:
            fill_level = "acceptable"

    return {
        "fill_model": fill_model,
        "slippage_bps": slippage,
        "execution_timing": execution_timing,
        "participation_rate": participation_rate,
        "liquidity_filter_present": liquidity_filter_present,
        "fill_realism_level": fill_level,
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# M13 — Fragility summary
# ---------------------------------------------------------------------------

def _build_fragility_summary(
    cost_sensitivity: dict,
    fill_realism: dict,
) -> dict:
    """K. Roll cost sensitivity and fill realism into an overall fragility summary."""
    cost_level = cost_sensitivity.get("cost_fragility_level", "unknown")
    fill_level = fill_realism.get("fill_realism_level", "unknown")

    # Overall fragility: worst of the two dimensions.
    if cost_level == "high" or fill_level == "weak":
        overall = "high"
    elif cost_level == "medium" or fill_level == "review":
        overall = "medium"
    elif cost_level == "low" and fill_level in ("strong", "acceptable"):
        overall = "low"
    elif cost_level == "unknown" and fill_level == "unknown":
        overall = "unknown"
    else:
        # Partial data: one known, one unknown — be conservative.
        known_levels = [l for l in (cost_level, fill_level) if l != "unknown"]
        if any(l in ("high", "medium") for l in known_levels):
            overall = max(known_levels, key=lambda l: {"high": 3, "medium": 2, "low": 1}.get(l, 0))
        else:
            overall = "unknown"

    key_concerns: list[str] = []
    if cost_level == "high":
        key_concerns.append(
            "Cost sensitivity is estimated to be high — reported Sharpe may drop "
            "below 1.0 at realistic transaction cost levels."
        )
    elif cost_level == "medium":
        key_concerns.append(
            "Cost sensitivity is estimated to be moderate — performance may be "
            "materially impacted at higher transaction cost levels."
        )
    if fill_level == "weak":
        key_concerns.append(
            "Fill realism is weak — execution assumptions may significantly "
            "overstate achievable returns in live trading."
        )
    elif fill_level == "review":
        key_concerns.append(
            "Fill realism requires review — one or more execution assumptions "
            "may be optimistic relative to live trading conditions."
        )

    return {
        "overall_fragility": overall,
        "cost_fragility_level": cost_level,
        "fill_realism_level": fill_level,
        "key_concerns": key_concerns,
    }


# ---------------------------------------------------------------------------
# M13 — Issues derived from sensitivity analysis
# ---------------------------------------------------------------------------

def _issues_from_cost_sensitivity(
    cost_sensitivity: dict,
    issues: list[AuditIssue],
) -> None:
    """Create BacktestIssue records for high/medium cost fragility findings."""
    level = cost_sensitivity.get("cost_fragility_level", "unknown")
    turnover = cost_sensitivity.get("turnover")
    base_sharpe = cost_sensitivity.get("base_sharpe")
    scenarios = cost_sensitivity.get("scenarios", [])

    # Find the 10-bps and 25-bps adjusted Sharpe values for evidence.
    sharpe_at_10: float | None = next(
        (s["adjusted_sharpe"] for s in scenarios if s["cost_bps"] == 10.0), None
    )
    sharpe_at_25: float | None = next(
        (s["adjusted_sharpe"] for s in scenarios if s["cost_bps"] == 25.0), None
    )

    if level == "high":
        issues.append(AuditIssue(
            issue_type="high_cost_fragility",
            severity="high",
            title="Strategy may be fragile to realistic transaction costs",
            description=(
                f"Cost sensitivity analysis (estimate only) suggests the Sharpe ratio "
                f"may drop below 1.0 at 10 bps of transaction cost "
                f"(estimated Sharpe at 10 bps: {sharpe_at_10:.2f} vs base {base_sharpe:.2f}). "
                f"Turnover of {turnover:.1f}× amplifies the impact of cost assumptions. "
                "These are approximations — not a full re-backtest."
            ) if (sharpe_at_10 is not None and base_sharpe is not None and turnover is not None)
            else (
                "Cost sensitivity analysis suggests high fragility to transaction costs. "
                "These are estimates only — not a full re-backtest."
            ),
            evidence_json={
                "cost_fragility_level": "high",
                "turnover": turnover,
                "base_sharpe": base_sharpe,
                "estimated_sharpe_at_10bps": sharpe_at_10,
                "estimated_sharpe_at_25bps": sharpe_at_25,
            },
            suggested_check=(
                "Re-run the backtest with explicit cost assumptions of 10–25 bps to "
                "verify whether the strategy remains viable under realistic cost levels. "
                "Consider reducing turnover or improving signal-to-noise ratio."
            ),
        ))
    elif level == "medium":
        issues.append(AuditIssue(
            issue_type="medium_cost_fragility",
            severity="medium",
            title="Strategy may be moderately sensitive to transaction costs",
            description=(
                f"Cost sensitivity analysis (estimate only) suggests the Sharpe ratio "
                f"may drop below 1.0 at 25 bps of transaction cost "
                f"(estimated Sharpe at 25 bps: {sharpe_at_25:.2f} vs base {base_sharpe:.2f}). "
                "These are approximations — not a full re-backtest."
            ) if (sharpe_at_25 is not None and base_sharpe is not None)
            else (
                "Cost sensitivity analysis suggests moderate fragility to transaction costs. "
                "These are estimates only — not a full re-backtest."
            ),
            evidence_json={
                "cost_fragility_level": "medium",
                "turnover": turnover,
                "base_sharpe": base_sharpe,
                "estimated_sharpe_at_25bps": sharpe_at_25,
            },
            suggested_check=(
                "Consider re-running the backtest with 25 bps cost assumptions. "
                "For strategies with moderate turnover, 10–25 bps is a reasonable "
                "range for realistic transaction costs."
            ),
        ))


def _issues_from_fill_realism(
    fill_realism: dict,
    issues: list[AuditIssue],
) -> None:
    """Create BacktestIssue records for NEW M13 fill realism findings.

    M8's _check_fill_model already handles missing_fill_model, close_fill_model,
    and open-fill-without-slippage.  This function creates issues only for
    NEW issue types not covered by M8.
    """
    # Issue types M8 already handles — skip to avoid duplicates.
    _M8_COVERED = {"missing_fill_model", "same_close_fill", "close_fill_model"}

    fill_model = fill_realism.get("fill_model")
    findings = fill_realism.get("findings", [])

    for finding in findings:
        code = finding["code"]
        if code in _M8_COVERED:
            continue  # Already covered by M8 checks.

        if code == "same_bar_fill":
            issues.append(AuditIssue(
                issue_type="same_bar_fill",
                severity="high",
                title="Same-bar fill model — strong execution bias risk",
                description=finding["message"],
                evidence_json={"fill_model": fill_model},
                suggested_check=finding["suggested_check"],
            ))
        elif code == "mid_fill_no_slippage":
            issues.append(AuditIssue(
                issue_type="mid_fill_no_slippage",
                severity="medium",
                title="Mid-price fill without slippage modelled",
                description=finding["message"],
                evidence_json={"fill_model": fill_model, "slippage_bps": None},
                suggested_check=finding["suggested_check"],
            ))
        elif code == "high_participation_rate":
            issues.append(AuditIssue(
                issue_type="high_participation_rate",
                severity="high",
                title="Very high participation rate assumption",
                description=finding["message"],
                evidence_json={
                    "participation_rate": fill_realism.get("participation_rate"),
                    "threshold": 0.5,
                },
                suggested_check=finding["suggested_check"],
            ))
        elif code == "elevated_participation_rate":
            issues.append(AuditIssue(
                issue_type="elevated_participation_rate",
                severity="medium",
                title="Elevated participation rate assumption",
                description=finding["message"],
                evidence_json={
                    "participation_rate": fill_realism.get("participation_rate"),
                    "threshold": 0.2,
                },
                suggested_check=finding["suggested_check"],
            ))
        elif code == "missing_liquidity_filter":
            issues.append(AuditIssue(
                issue_type="missing_liquidity_filter",
                severity="medium",
                title="No liquidity filter with high turnover",
                description=finding["message"],
                evidence_json={
                    "liquidity_filter_present": False,
                    "turnover": fill_realism.get("fill_model"),  # captured indirectly
                },
                suggested_check=finding["suggested_check"],
            ))
        elif code == "missing_execution_timing":
            issues.append(AuditIssue(
                issue_type="missing_execution_timing",
                severity="low",
                title="Execution timing not specified",
                description=finding["message"],
                evidence_json={"execution_timing": None},
                suggested_check=finding["suggested_check"],
            ))
        elif code == "high_trade_count_simple_fill":
            issues.append(AuditIssue(
                issue_type="high_trade_count_simple_fill",
                severity="low",
                title="High trade count with simplistic fill model",
                description=finding["message"],
                evidence_json={"fill_model": fill_model},
                suggested_check=finding["suggested_check"],
            ))
        # missing_slippage is informational in the JSON only — not a separate issue.


# ---------------------------------------------------------------------------
# M36 — Cost sensitivity sweep
# ---------------------------------------------------------------------------

def _run_cost_sensitivity_sweep(run: "StrategyRun") -> dict | None:
    """A. Extended cost sweep: 6 scenarios relative to the run's assumed total cost."""
    metrics: dict = run.metrics_json or {}
    assumptions: dict = run.assumptions_json or {}
    warnings: list[str] = []

    base_cost = float(assumptions.get("transaction_cost_bps") or 0)
    slippage = float(assumptions.get("slippage_bps") or 0)
    total_cost = base_cost + slippage
    turnover = float(metrics.get("turnover") or 0)
    base_return = float(metrics.get("annual_return") or 0)
    base_sharpe = float(metrics.get("sharpe") or 0)
    volatility = float(metrics.get("volatility") or 0)

    if not assumptions.get("transaction_cost_bps"):
        warnings.append(
            "transaction_cost_bps missing; sweep uses 0 bps baseline only for "
            "sensitivity approximation."
        )
    if not turnover:
        warnings.append(
            "turnover missing; cost drag estimates are not computed."
        )

    scenarios_spec = [
        ("assumed_cost", total_cost),
        ("2x_cost", total_cost * 2),
        ("3x_cost", total_cost * 3),
        ("5x_cost", total_cost * 5),
        ("assumed_plus_10bps", total_cost + 10),
        ("assumed_plus_25bps", total_cost + 25),
    ]

    result_scenarios: list[dict] = []
    for label, scenario_cost in scenarios_spec:
        incremental = scenario_cost - total_cost
        cost_drag = round((incremental / 10_000) * turnover, 4) if turnover > 0 else None
        adj_return: float | None = None
        if base_return != 0 and cost_drag is not None:
            adj_return = round(base_return - cost_drag, 4)

        adj_sharpe: float | None = None
        if adj_return is not None and volatility > 0:
            adj_sharpe = round(adj_return / volatility, 3)
        elif base_sharpe != 0 and cost_drag is not None and volatility > 0:
            adj_sharpe = round(base_sharpe - (cost_drag / volatility), 3)

        sharpe_delta: float | None = None
        if adj_sharpe is not None:
            sharpe_delta = round(adj_sharpe - base_sharpe, 3)

        if adj_sharpe is None:
            trust_impact = "unknown"
        elif adj_sharpe >= 1.5:
            trust_impact = "low"
        elif adj_sharpe >= 1.0:
            trust_impact = "medium"
        else:
            trust_impact = "high"

        result_scenarios.append({
            "scenario_label": label,
            "total_cost_bps": scenario_cost,
            "incremental_cost_bps": incremental,
            "estimated_cost_drag": cost_drag,
            "adjusted_annual_return": adj_return,
            "adjusted_sharpe": adj_sharpe,
            "sharpe_delta": sharpe_delta,
            "trust_impact": trust_impact,
        })

    high_scenarios = [s for s in result_scenarios if s["trust_impact"] == "high"]
    most_fragile = (
        high_scenarios[0]["scenario_label"]
        if high_scenarios
        else result_scenarios[-1]["scenario_label"]
    )

    summary_parts: list[str] = [
        f"Baseline cost assumption: {total_cost:.0f} bps."
        if total_cost > 0
        else "No cost baseline provided."
    ]
    high_count = len(high_scenarios)
    if high_count > 0:
        summary_parts.append(
            f"{high_count} scenario(s) estimate high trust impact under elevated costs."
        )
    else:
        summary_parts.append(
            "Estimated trust impact is manageable under all scenarios."
        )
    summary_parts.append(
        "This is a deterministic approximation, not a full re-backtest."
    )

    return {
        "baseline_cost_bps": total_cost,
        "turnover": turnover,
        "base_annual_return": base_return,
        "base_sharpe": base_sharpe,
        "scenarios": result_scenarios,
        "most_fragile_scenario": most_fragile,
        "deterministic_summary": " ".join(summary_parts),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# M36 — Fill sensitivity
# ---------------------------------------------------------------------------

def _run_fill_sensitivity(run: "StrategyRun") -> dict | None:
    """B. Rule-based fill sensitivity across 5 scenario labels."""
    assumptions: dict = run.assumptions_json or {}
    metrics: dict = run.metrics_json or {}

    reported_fill = str(assumptions.get("fill_model") or "unknown")
    slippage_bps = float(assumptions.get("slippage_bps") or 0)
    exec_timing = str(assumptions.get("execution_timing") or "unknown")
    turnover = float(metrics.get("turnover") or 0)

    _HIGH_CONCERN = {"close", "same_close", "same_bar", "exact_price", "open", "prev_close", "last"}
    _MED_CONCERN = {"mid", "vwap", "twap", "mid_price"}
    _LOW_CONCERN = {
        "next_bar_open", "next_close", "conservative",
        "mid_plus_5bps", "slippage_adjusted", "next_open",
    }

    fill_key = reported_fill.lower().replace(" ", "_")
    if fill_key in _HIGH_CONCERN:
        fill_realism = "high_concern"
    elif fill_key in _MED_CONCERN:
        fill_realism = "low_concern" if slippage_bps > 0 else "medium_concern"
    elif fill_key in _LOW_CONCERN:
        fill_realism = "low_concern"
    else:
        fill_realism = "unknown"

    rep_penalty = (
        "high" if fill_realism == "high_concern"
        else "medium" if fill_realism == "medium_concern"
        else "low" if fill_realism == "low_concern"
        else "unknown"
    )

    scenarios = [
        {
            "scenario_label": "reported_fill",
            "assumed_fill_model": reported_fill,
            "slippage_bps_assumption": slippage_bps,
            "execution_timing_assumption": exec_timing,
            "trust_penalty_estimate": rep_penalty,
            "reason": f"As reported ({reported_fill}).",
        },
        {
            "scenario_label": "mid_plus_slippage",
            "assumed_fill_model": "mid",
            "slippage_bps_assumption": max(slippage_bps, 5.0),
            "execution_timing_assumption": "next_bar",
            "trust_penalty_estimate": "medium",
            "reason": "Mid-price with slippage is a standard conservative assumption.",
        },
        {
            "scenario_label": "next_bar_open",
            "assumed_fill_model": "next_bar_open",
            "slippage_bps_assumption": max(slippage_bps, 5.0),
            "execution_timing_assumption": "next_bar",
            "trust_penalty_estimate": "low",
            "reason": "Next-bar-open is more conservative than same-bar fills.",
        },
        {
            "scenario_label": "worst_side_fill",
            "assumed_fill_model": "worst_side",
            "slippage_bps_assumption": max(slippage_bps * 2, 20.0),
            "execution_timing_assumption": "next_bar",
            "trust_penalty_estimate": "high" if turnover > 0.5 else "medium",
            "reason": (
                "Worst-side fill with doubled slippage."
                + (" High concern given turnover." if turnover > 0.5 else "")
            ),
        },
        {
            "scenario_label": "conservative_fill",
            "assumed_fill_model": "conservative",
            "slippage_bps_assumption": max(slippage_bps * 1.5, 10.0),
            "execution_timing_assumption": "next_bar",
            "trust_penalty_estimate": "high" if turnover > 1.0 else "medium",
            "reason": (
                "Conservative fill approximation."
                + (" High turnover increases penalty." if turnover > 1.0 else "")
            ),
        },
    ]

    worst = next(
        (s for s in scenarios if s["trust_penalty_estimate"] == "high"),
        scenarios[-1],
    )

    if fill_realism == "high_concern":
        note = (
            "Same-close or exact fills may overstate backtest performance by "
            "avoiding realistic market impact."
        )
    elif fill_realism == "medium_concern":
        note = (
            "Fill assumption is moderately realistic; explicit slippage "
            "assumptions are recommended."
        )
    elif fill_realism == "low_concern":
        note = "Fill assumption appears conservative and realistic."
    else:
        note = "Fill model not recognized; review fill assumption manually."

    return {
        "reported_fill_model": reported_fill,
        "fill_realism_level": fill_realism,
        "scenarios": scenarios,
        "worst_case_scenario": worst["scenario_label"],
        "deterministic_summary": (
            note + " This analysis uses rule-based estimation, not market simulation."
        ),
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# M36 — Penalty attribution
# ---------------------------------------------------------------------------

def _build_penalty_attribution(issues: list[AuditIssue]) -> dict | None:
    """C. Attribute the trust-score penalty across logical categories."""
    _KEYWORDS = {
        "lookahead": "lookahead_risk",
        "look_ahead": "lookahead_risk",
        "cost": "transaction_cost_realism",
        "transaction": "transaction_cost_realism",
        "slippage": "fill_realism",
        "fill": "fill_realism",
        "liquidity": "liquidity_realism",
        "volume": "liquidity_realism",
        "borrow": "borrow_realism",
        "short": "borrow_realism",
        "data": "data_quality",
        "quality": "data_quality",
        "sample": "sample_size_confidence",
        "trade_count": "sample_size_confidence",
        "sharpe": "metric_plausibility",
        "return": "metric_plausibility",
    }
    _SEVERITY_WEIGHTS: dict[str, int] = {
        "critical": 25,
        "high": 15,
        "medium": 8,
        "low": 3,
    }
    _SUGGESTED_CHECKS: dict[str, str] = {
        "lookahead_risk": "Review all signal calculations to ensure no future data is used.",
        "transaction_cost_realism": (
            "Add explicit transaction_cost_bps and slippage_bps assumptions."
        ),
        "fill_realism": (
            "Replace same-close or exact fill with next-bar or slippage-adjusted fill model."
        ),
        "liquidity_realism": "Add liquidity constraints or volume checks to the strategy.",
        "borrow_realism": "Add borrow_cost_bps when shorting is enabled.",
        "data_quality": "Review data quality issues before trusting backtest results.",
        "sample_size_confidence": (
            "Add trade_count to support sample-size confidence checks."
        ),
        "metric_plausibility": "Verify reported metrics are computed correctly.",
        "missing_evidence": (
            "Link dataset snapshot and add assumptions to improve audit coverage."
        ),
    }

    cats: dict[str, dict] = {}
    for issue in issues:
        cat = "missing_evidence"
        text = (
            f"{issue.issue_type or ''} "
            f"{issue.description or ''}"
        ).lower()
        for kw, c in _KEYWORDS.items():
            if kw in text:
                cat = c
                break
        cats.setdefault(cat, {"issues": [], "penalty": 0})
        cats[cat]["issues"].append(issue)
        cats[cat]["penalty"] += _SEVERITY_WEIGHTS.get(issue.severity, 3)

    result_cats: list[dict] = []
    for cat, info in sorted(cats.items(), key=lambda x: -x[1]["penalty"]):
        titles = [
            i.title
            for i in info["issues"][:3]
            if i.title
        ]
        result_cats.append({
            "category": cat,
            "issue_count": len(info["issues"]),
            "severity_weight": info["penalty"],
            "estimated_score_penalty": min(info["penalty"], 30),
            "top_issue_titles": titles,
            "suggested_check": _SUGGESTED_CHECKS.get(cat, "Review flagged issues."),
        })

    total = sum(c["estimated_score_penalty"] for c in result_cats)
    largest = result_cats[0]["category"] if result_cats else None
    summary = f"{len(result_cats)} issue category(ies) identified."
    if largest:
        summary += (
            f" {largest.replace('_', ' ').title()} contributes the most to the "
            "estimated trust score reduction."
        )
    summary += " This attribution is an approximation based on logged issues."

    return {
        "categories": result_cats,
        "total_estimated_penalty": total,
        "largest_penalty_category": largest,
        "deterministic_summary": summary,
    }


# ---------------------------------------------------------------------------
# M36 — Improvement checks
# ---------------------------------------------------------------------------

def _generate_improvement_checks(
    run: "StrategyRun",
    issues: list[AuditIssue],
    fill_sensitivity: dict | None,
) -> list[dict]:
    """D. Generate prioritised, actionable improvement checks for this run."""
    checks: list[dict] = []
    assumptions: dict = run.assumptions_json or {}
    metrics: dict = run.metrics_json or {}
    _priority_order = {"high": 0, "medium": 1, "low": 2}

    if not assumptions.get("transaction_cost_bps"):
        checks.append({
            "check_key": "add_cost_assumption",
            "title": "Add explicit transaction_cost_bps and slippage_bps assumptions",
            "description": (
                "Cost assumptions are required for meaningful cost sensitivity analysis."
            ),
            "related_category": "transaction_cost_realism",
            "priority": "high",
            "evidence": "transaction_cost_bps not found in assumptions_json",
        })

    if (
        fill_sensitivity is not None
        and fill_sensitivity.get("fill_realism_level") == "high_concern"
    ):
        checks.append({
            "check_key": "improve_fill_model",
            "title": "Replace same-close or exact fill with a more realistic fill model",
            "description": (
                "Same-close fills can overstate performance. Consider next-bar-open "
                "or slippage-adjusted fill."
            ),
            "related_category": "fill_realism",
            "priority": "high",
            "evidence": (
                f"Reported fill model: {fill_sensitivity.get('reported_fill_model')}"
            ),
        })

    if not metrics.get("trade_count"):
        checks.append({
            "check_key": "add_trade_count",
            "title": "Add trade_count to metrics",
            "description": "Trade count enables sample-size confidence checks.",
            "related_category": "sample_size_confidence",
            "priority": "medium",
            "evidence": "trade_count not found in metrics_json",
        })

    if run.dataset_snapshot_id is None:
        checks.append({
            "check_key": "link_dataset",
            "title": "Link a dataset snapshot to this run",
            "description": (
                "Dataset evidence allows data quality to be verified in the audit."
            ),
            "related_category": "data_quality",
            "priority": "medium",
            "evidence": "No dataset snapshot linked to this run",
        })

    critical_issues = [i for i in issues if i.severity == "critical"]
    if critical_issues:
        checks.append({
            "check_key": "resolve_critical_issues",
            "title": f"Review {len(critical_issues)} critical backtest issue(s)",
            "description": (
                "Critical issues may fundamentally compromise backtest reliability."
            ),
            "related_category": "missing_evidence",
            "priority": "high",
            "evidence": "; ".join(
                i.title for i in critical_issues[:2] if i.title
            ),
        })

    if assumptions.get("short_enabled") and not assumptions.get("borrow_cost_bps"):
        checks.append({
            "check_key": "add_borrow_cost",
            "title": "Add borrow_cost_bps when shorting is enabled",
            "description": "Borrow costs can significantly impact short-side returns.",
            "related_category": "borrow_realism",
            "priority": "medium",
            "evidence": "short_enabled=True but borrow_cost_bps not set",
        })

    checks.sort(key=lambda c: _priority_order.get(c.get("priority", "low"), 2))
    return checks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_backtest_audit(
    run: "StrategyRun",
    data_evidence: "DataEvidenceSummary | None" = None,
) -> AuditResult:
    """Run all backtest reality checks and return an ``AuditResult``.

    Parameters
    ----------
    run:
        The ``StrategyRun`` ORM object to audit.  Fields accessed:
        ``params_json``, ``assumptions_json``, ``metrics_json``, ``run_type``.
    data_evidence:
        Pre-computed ``DataEvidenceSummary`` from the run's linked dataset
        snapshot (if any).  Pass ``None`` when no snapshot is linked.

    Returns
    -------
    AuditResult
        Dataclass with all issues, scores, status, summary, and M13 JSON blobs.
        Ready to be persisted to the DB by the calling route.
    """
    assumptions: dict = run.assumptions_json or {}
    metrics: dict = run.metrics_json or {}
    params: dict = run.params_json or {}  # noqa: F841 — available for future checks

    issues: list[AuditIssue] = []

    # ------------------------------------------------------------------
    # M8 checks
    # ------------------------------------------------------------------
    _check_transaction_costs(assumptions, metrics, issues)
    _check_fill_model(assumptions, issues)
    _check_borrow_costs(assumptions, issues)
    _check_sample_size(metrics, assumptions, issues)
    _check_turnover(metrics, issues)
    _check_data_evidence(data_evidence, issues)
    _check_drawdown(metrics, issues)
    _check_metric_plausibility(metrics, issues)

    # ------------------------------------------------------------------
    # M13 sensitivity analyses (computed before issues so results feed issues)
    # ------------------------------------------------------------------
    cost_sensitivity = _analyze_cost_sensitivity(assumptions, metrics)
    fill_realism = _analyze_fill_realism(assumptions, metrics)
    fragility_summary = _build_fragility_summary(cost_sensitivity, fill_realism)

    # Create issues from M13 analyses.
    _issues_from_cost_sensitivity(cost_sensitivity, issues)
    _issues_from_fill_realism(fill_realism, issues)

    # ------------------------------------------------------------------
    # Sort issues most-severe first for consistent output.
    # ------------------------------------------------------------------
    _sev_rank = {s: i for i, s in enumerate(_SEVERITY_ORDER)}
    issues.sort(key=lambda x: _sev_rank.get(x.severity, len(_SEVERITY_ORDER)))

    # ------------------------------------------------------------------
    # Compute scores.
    # ------------------------------------------------------------------
    trust_score = _compute_trust_score(issues)
    cost_realism_score = _compute_subscore(issues, "cost_realism_score")
    fill_realism_score = _compute_subscore(issues, "fill_realism_score")
    liquidity_realism_score = _compute_subscore(issues, "liquidity_realism_score")
    borrow_realism_score = _compute_subscore(issues, "borrow_realism_score")
    data_quality_score = _compute_subscore(issues, "data_quality_score")

    status = _overall_status(trust_score)
    summary = _build_summary(issues, trust_score, status)

    # ------------------------------------------------------------------
    # M36 extended analyses (run after issues are finalised so attribution
    # reflects the complete issue list).
    # ------------------------------------------------------------------
    cost_sensitivity_sweep = _run_cost_sensitivity_sweep(run)
    fill_sensitivity = _run_fill_sensitivity(run)
    penalty_attribution = _build_penalty_attribution(issues)
    improvement_checks = _generate_improvement_checks(run, issues, fill_sensitivity)

    return AuditResult(
        issues=issues,
        trust_score=trust_score,
        # lookahead_risk_score reserved for a future check (no checks map to it yet).
        lookahead_risk_score=100,
        cost_realism_score=cost_realism_score,
        fill_realism_score=fill_realism_score,
        liquidity_realism_score=liquidity_realism_score,
        borrow_realism_score=borrow_realism_score,
        data_quality_score=data_quality_score,
        overall_status=status,
        summary=summary,
        cost_sensitivity_json=cost_sensitivity,
        fill_realism_json=fill_realism,
        fragility_summary_json=fragility_summary,
        cost_sensitivity_sweep_json=cost_sensitivity_sweep,
        fill_sensitivity_json=fill_sensitivity,
        penalty_attribution_json=penalty_attribution,
        improvement_checks_json={"checks": improvement_checks},
    )
