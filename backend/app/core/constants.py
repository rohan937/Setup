"""Domain-level string constants used as enum values throughout the app.

We use plain string literals (rather than native SQLAlchemy ENUM types) to
avoid CREATE TYPE migrations on PostgreSQL and to keep SQLite compatibility.
The Python-level StrEnum classes give IDE completion and type checking.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    owner = "owner"
    admin = "admin"
    member = "member"
    viewer = "viewer"


class StrategyStatus(StrEnum):
    active = "active"
    paused = "paused"
    archived = "archived"
    draft = "draft"


class AssetClass(StrEnum):
    equity = "equity"
    etf = "etf"
    future = "future"
    option = "option"
    fx = "fx"
    crypto = "crypto"
    rate = "rate"
    commodity = "commodity"
    other = "other"


class RunType(StrEnum):
    research = "research"
    backtest = "backtest"
    paper = "paper"
    live = "live"


class RunStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


class EventType(StrEnum):
    strategy_created = "strategy_created"
    strategy_updated = "strategy_updated"
    strategy_version_created = "strategy_version_created"
    strategy_run_logged = "strategy_run_logged"
    backtest_run_logged = "backtest_run_logged"
    backtest_audited = "backtest_audited"
    dataset_snapshot_uploaded = "dataset_snapshot_uploaded"
    data_issue_detected = "data_issue_detected"
    live_run_started = "live_run_started"
    live_run_completed = "live_run_completed"
    reliability_diagnosed = "reliability_diagnosed"
    alert_raised = "alert_raised"
    alert_generated = "alert_generated"
    alert_status_changed = "alert_status_changed"
    report_generated = "report_generated"
    strategy_config_snapshot_logged = "strategy_config_snapshot_logged"
    universe_snapshot_logged = "universe_snapshot_logged"
    signal_snapshot_logged = "signal_snapshot_logged"
    strategy_reliability_scored = "strategy_reliability_scored"
    evidence_bundle_ingested = "evidence_bundle_ingested"
    api_key_created = "api_key_created"
    api_key_revoked = "api_key_revoked"
    demo_seeded = "demo_seeded"
    regression_tests_run = "regression_tests_run"
    config_policy_evaluated = "config_policy_evaluated"
    research_review_cases_generated = "research_review_cases_generated"
    research_review_case_acknowledged = "research_review_case_acknowledged"
    research_review_case_resolved = "research_review_case_resolved"
    evidence_sla_evaluated = "evidence_sla_evaluated"
    strategy_change_impact_analyzed = "strategy_change_impact_analyzed"
    strategy_experiment_created = "strategy_experiment_created"
    strategy_experiment_run_added = "strategy_experiment_run_added"
    strategy_experiment_analyzed = "strategy_experiment_analyzed"
    strategy_sweep_analyzed = "strategy_sweep_analyzed"
    reliability_snapshot_refreshed = "reliability_snapshot_refreshed"
    workspace_settings_updated = "workspace_settings_updated"
    workspace_member_added = "workspace_member_added"
    workspace_member_updated = "workspace_member_updated"
    workspace_member_removed = "workspace_member_removed"
    user_registered = "user_registered"
    user_logged_in = "user_logged_in"


class ReliabilityScoreStatus(StrEnum):
    excellent = "excellent"
    good = "good"
    review = "review"
    weak = "weak"
    insufficient_evidence = "insufficient_evidence"


class Severity(StrEnum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class DatasetType(StrEnum):
    ohlcv = "ohlcv"
    factors = "factors"
    fundamentals = "fundamentals"
    returns = "returns"
    custom = "custom"


class DatasetSourceType(StrEnum):
    manual = "manual"
    vendor = "vendor"
    computed = "computed"
    sdk = "sdk"


class IssueType(StrEnum):
    missing_values = "missing_values"
    duplicate_rows = "duplicate_rows"
    duplicate_symbol_timestamp = "duplicate_symbol_timestamp"
    invalid_timestamp = "invalid_timestamp"
    negative_zero_price = "negative_zero_price"
    high_lt_low = "high_lt_low"
    close_outside_range = "close_outside_range"
    open_outside_range = "open_outside_range"
    negative_volume = "negative_volume"
    suspicious_return_jump = "suspicious_return_jump"


class BacktestStatus(StrEnum):
    excellent = "excellent"
    good = "good"
    review = "review"
    weak = "weak"
    unreliable = "unreliable"


class AlertRuleType(StrEnum):
    data_health_below_threshold = "data_health_below_threshold"
    backtest_trust_below_threshold = "backtest_trust_below_threshold"
    data_quality_issue_high_or_critical = "data_quality_issue_high_or_critical"
    backtest_issue_high_or_critical = "backtest_issue_high_or_critical"
    strategy_run_missing_dataset_evidence = "strategy_run_missing_dataset_evidence"
    # M33: evidence quality checks
    evidence_coverage_below_threshold = "evidence_coverage_below_threshold"
    strategy_health_review_or_critical = "strategy_health_review_or_critical"
    reliability_score_deteriorating = "reliability_score_deteriorating"
    data_health_deteriorating = "data_health_deteriorating"
    signal_quality_deteriorating = "signal_quality_deteriorating"
    backtest_trust_deteriorating = "backtest_trust_deteriorating"
    stale_strategy_run = "stale_strategy_run"
    repeated_failed_ingestion = "repeated_failed_ingestion"
    missing_signal_evidence = "missing_signal_evidence"
    missing_universe_evidence = "missing_universe_evidence"
    missing_config_evidence = "missing_config_evidence"


class AlertStatus(StrEnum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"
    snoozed = "snoozed"


class ReportType(StrEnum):
    strategy_reliability = "strategy_reliability"
    backtest_audit = "backtest_audit"
    dataset_health = "dataset_health"


class ReportStatus(StrEnum):
    generated = "generated"
    stale = "stale"
    archived = "archived"


class BacktestIssueType(StrEnum):
    missing_transaction_cost = "missing_transaction_cost"
    zero_transaction_cost = "zero_transaction_cost"
    high_turnover_low_cost = "high_turnover_low_cost"
    high_turnover = "high_turnover"
    missing_fill_model = "missing_fill_model"
    close_fill_model = "close_fill_model"
    missing_borrow_cost = "missing_borrow_cost"
    zero_borrow_cost = "zero_borrow_cost"
    insufficient_trade_count = "insufficient_trade_count"
    missing_trade_count = "missing_trade_count"
    low_data_quality = "low_data_quality"
    no_data_snapshot = "no_data_snapshot"
    critical_data_issue = "critical_data_issue"
    high_max_drawdown = "high_max_drawdown"
    implausible_sharpe = "implausible_sharpe"
    implausible_return = "implausible_return"
    zero_volatility = "zero_volatility"
    # M13: cost sensitivity
    high_cost_fragility = "high_cost_fragility"
    medium_cost_fragility = "medium_cost_fragility"
    # M13: fill realism (new checks beyond M8)
    same_bar_fill = "same_bar_fill"
    mid_fill_no_slippage = "mid_fill_no_slippage"
    high_participation_rate = "high_participation_rate"
    elevated_participation_rate = "elevated_participation_rate"
    missing_liquidity_filter = "missing_liquidity_filter"
    missing_execution_timing = "missing_execution_timing"
    high_trade_count_simple_fill = "high_trade_count_simple_fill"
