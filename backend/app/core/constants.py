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
    dataset_snapshot_uploaded = "dataset_snapshot_uploaded"
    data_issue_detected = "data_issue_detected"
    live_run_started = "live_run_started"
    live_run_completed = "live_run_completed"
    reliability_diagnosed = "reliability_diagnosed"
    alert_raised = "alert_raised"


class Severity(StrEnum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"
