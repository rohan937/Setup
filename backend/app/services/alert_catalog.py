"""Alert catalog — M85.

Maps every ``AlertRuleType`` to a deterministic, concrete recommended-fix
string describing what the operator should do next.  No AI, no live data; the
strings are static and load-bearing for the operator UX.
"""

from __future__ import annotations

from app.core.constants import AlertRuleType

# Shown alongside every alert so operators understand the intent of the signal.
DISCLAIMER = "Research reliability signal, not a trading recommendation."

# Generic fallback when a rule_type is not explicitly catalogued.
_GENERIC_FIX = (
    "Review the linked evidence for this alert and address the underlying issue, "
    "then re-run alert generation to confirm it clears."
)

RULE_RECOMMENDED_FIX: dict[str, str] = {
    # --- M11 legacy checks -------------------------------------------------
    str(AlertRuleType.data_health_below_threshold): (
        "Open the flagged dataset snapshot, resolve the data-quality issues "
        "lowering its health score, and upload a corrected snapshot."
    ),
    str(AlertRuleType.backtest_trust_below_threshold): (
        "Open the latest backtest audit and resolve the high/critical issues "
        "lowering its trust score, then re-run the Backtest Reality Check."
    ),
    str(AlertRuleType.data_quality_issue_high_or_critical): (
        "Fix the flagged data-quality issue in the dataset snapshot "
        "(missing values, duplicates, or invalid prices) and re-upload."
    ),
    str(AlertRuleType.backtest_issue_high_or_critical): (
        "Open the latest backtest audit and resolve the high/critical issue "
        "(costs, fills, or trade-count assumptions) lowering trust."
    ),
    str(AlertRuleType.strategy_run_missing_dataset_evidence): (
        "Use Fix evidence links on the run to attach the dataset snapshot it "
        "was produced from."
    ),
    # --- M33 evidence-quality checks --------------------------------------
    str(AlertRuleType.evidence_coverage_below_threshold): (
        "Open the Evidence Coverage Matrix and fill the missing evidence cells "
        "(dataset, signal, universe, config) for the affected runs."
    ),
    str(AlertRuleType.strategy_health_review_or_critical): (
        "Open the strategy's Overview tab, review the primary concern, and "
        "resolve the open alerts and evidence gaps driving the health status."
    ),
    str(AlertRuleType.reliability_score_deteriorating): (
        "Investigate what changed between the last two runs, then recompute the "
        "reliability score after resolving the flagged evidence items."
    ),
    str(AlertRuleType.data_health_deteriorating): (
        "Inspect the recent dataset snapshots on the Strategy Detail page and "
        "address the data-quality regression lowering health."
    ),
    str(AlertRuleType.signal_quality_deteriorating): (
        "Inspect the recent signal snapshots and quality scores on the Strategy "
        "Detail page and investigate the signal-quality regression."
    ),
    str(AlertRuleType.backtest_trust_deteriorating): (
        "Open the latest backtest audit and resolve the high/critical issues, "
        "then re-run the Backtest Reality Check after updating cost and fill "
        "assumptions."
    ),
    str(AlertRuleType.stale_strategy_run): (
        "Log a new strategy run to refresh evidence for this strategy."
    ),
    str(AlertRuleType.repeated_failed_ingestion): (
        "Investigate the recent failed ingestion batches in the SDK/ingestion "
        "log and re-submit after fixing the upload."
    ),
    str(AlertRuleType.missing_signal_evidence): (
        "Log a signal snapshot for this strategy to capture signal-quality "
        "evidence."
    ),
    str(AlertRuleType.missing_universe_evidence): (
        "Log a universe snapshot for this strategy to capture universe evidence."
    ),
    str(AlertRuleType.missing_config_evidence): (
        "Log a config snapshot for this strategy to capture configuration "
        "evidence."
    ),
    # --- M85 new lifecycle checks -----------------------------------------
    str(AlertRuleType.regression_test_failed): (
        "Review the failing regression test in the Governance tab and re-run "
        "the suite after addressing the metric regression."
    ),
    str(AlertRuleType.evidence_sla_breached): (
        "Refresh the stale or missing evidence listed in the SLA monitor for "
        "this strategy."
    ),
    str(AlertRuleType.reliability_report_missing): (
        "Generate a reliability report for the latest run from the Exports tab."
    ),
    str(AlertRuleType.promotion_gate_blocked): (
        "Resolve the blocking promotion gates in the Governance tab before "
        "promoting this strategy."
    ),
    str(AlertRuleType.paper_backtest_drift): (
        "Open the Drift monitor, compare the paper run against the backtest "
        "baseline, and investigate the drifting metrics."
    ),
    str(AlertRuleType.assumption_health_degraded): (
        "Open the Assumption Health panel and strengthen the weak assumption "
        "categories (costs, slippage, fills, liquidity, risk controls)."
    ),
    str(AlertRuleType.run_missing_linked_evidence): (
        "Use Fix evidence links on the run to attach the missing dataset, "
        "signal, universe, or strategy version."
    ),
}


def recommended_fix_for(rule_type: str) -> str:
    """Return the concrete recommended-fix string for *rule_type*.

    Falls back to a sensible generic message for unknown rule types so callers
    never receive an empty value.
    """
    return RULE_RECOMMENDED_FIX.get(str(rule_type), _GENERIC_FIX)
