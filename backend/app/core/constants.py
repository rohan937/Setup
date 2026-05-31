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


class AlertStatus(StrEnum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"
    snoozed = "snoozed"


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
