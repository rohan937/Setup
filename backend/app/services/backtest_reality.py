"""Backtest Reality Check service (M8).

Purely deterministic — no AI, no database access, no external calls.

Takes a ``StrategyRun`` ORM object and an optional ``DataEvidenceSummary``
(already computed by the route from any linked dataset snapshot) and returns
an ``AuditResult`` dataclass describing realism concerns, per-category
subscores, a trust score, and a hedged plain-language summary.

Checks implemented (v1):
  A. Transaction cost realism
  B. Fill model realism
  C. Borrow / short-selling realism
  D. Sample size / trade count adequacy
  E. Turnover realism
  F. Data evidence integration
  G. Max drawdown sanity
  H. Metric plausibility (Sharpe, return, volatility)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.strategy_run import StrategyRun
    from app.schemas.strategy import DataEvidenceSummary


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


# ---------------------------------------------------------------------------
# Internal helpers
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
# Individual check functions
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
    """B. Fill model realism."""
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
        Dataclass with all issues, scores, status, and summary.
        Ready to be persisted to the DB by the calling route.
    """
    assumptions: dict = run.assumptions_json or {}
    metrics: dict = run.metrics_json or {}
    params: dict = run.params_json or {}  # noqa: F841 — available for future checks

    issues: list[AuditIssue] = []

    # Run all checks.
    _check_transaction_costs(assumptions, metrics, issues)
    _check_fill_model(assumptions, issues)
    _check_borrow_costs(assumptions, issues)
    _check_sample_size(metrics, assumptions, issues)
    _check_turnover(metrics, issues)
    _check_data_evidence(data_evidence, issues)
    _check_drawdown(metrics, issues)
    _check_metric_plausibility(metrics, issues)

    # Sort issues most-severe first for consistent output.
    _sev_rank = {s: i for i, s in enumerate(_SEVERITY_ORDER)}
    issues.sort(key=lambda x: _sev_rank.get(x.severity, len(_SEVERITY_ORDER)))

    # Compute scores.
    trust_score = _compute_trust_score(issues)
    cost_realism_score = _compute_subscore(issues, "cost_realism_score")
    fill_realism_score = _compute_subscore(issues, "fill_realism_score")
    borrow_realism_score = _compute_subscore(issues, "borrow_realism_score")
    data_quality_score = _compute_subscore(issues, "data_quality_score")

    status = _overall_status(trust_score)
    summary = _build_summary(issues, trust_score, status)

    return AuditResult(
        issues=issues,
        trust_score=trust_score,
        # lookahead_risk_score and liquidity_realism_score are reserved for v2.
        # No checks map to them in v1, so they remain at 100.
        lookahead_risk_score=100,
        cost_realism_score=cost_realism_score,
        fill_realism_score=fill_realism_score,
        liquidity_realism_score=100,
        borrow_realism_score=borrow_realism_score,
        data_quality_score=data_quality_score,
        overall_status=status,
        summary=summary,
    )
