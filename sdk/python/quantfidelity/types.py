"""Lightweight TypedDict type hints for the QuantFidelity SDK.

These mirror the M22 backend evidence bundle schemas for IDE autocompletion
and static analysis. They are entirely optional — the SDK works with plain
``dict`` objects throughout; these are annotations only.

Usage::

    from quantfidelity.types import StrategyRunSection

    run: StrategyRunSection = {
        "run_name": "backtest-q1",
        "run_type": "backtest",
        "metrics_json": {"sharpe": 1.4},
    }
"""
from __future__ import annotations

from typing import Any, TypedDict


# ---------------------------------------------------------------------------
# Input sections
# ---------------------------------------------------------------------------


class StrategyVersionSection(TypedDict, total=False):
    version_label: str          # required
    git_commit: str | None
    branch_name: str | None
    code_path: str | None
    signal_name: str | None
    signal_description: str | None


class ConfigSnapshotSection(TypedDict, total=False):
    label: str                          # required
    config_json: dict[str, Any]         # required
    strategy_version_label: str | None
    source_type: str
    source_filename: str | None


class UniverseSnapshotSection(TypedDict, total=False):
    label: str                          # required
    symbols: list[str]                  # required, non-empty
    strategy_version_label: str | None
    source_type: str
    source_filename: str | None
    metadata_json: dict[str, Any] | None


class SignalSnapshotSection(TypedDict, total=False):
    label: str                               # required
    rows: list[dict[str, Any]]               # required, non-empty
    strategy_version_label: str | None
    universe_snapshot_label: str | None
    signal_name: str | None
    source_type: str
    source_filename: str | None
    signal_column: str
    metadata_json: dict[str, Any] | None


class DatasetSection(TypedDict, total=False):
    name: str                           # required
    slug: str | None
    description: str | None
    asset_class: str
    dataset_type: str
    source_type: str


class DatasetSnapshotSection(TypedDict, total=False):
    rows: list[dict[str, Any]]          # required, non-empty
    snapshot_label: str | None
    source_filename: str | None


class StrategyRunSection(TypedDict, total=False):
    run_name: str                       # required
    run_type: str                       # required
    status: str
    strategy_version_label: str | None
    dataset_snapshot_label: str | None
    universe_snapshot_label: str | None
    signal_snapshot_label: str | None
    started_at: str | None
    completed_at: str | None
    params_json: dict[str, Any] | None
    assumptions_json: dict[str, Any] | None
    metrics_json: dict[str, Any] | None
    universe_name: str | None
    dataset_version: str | None
    notes: str | None


class ActionsSection(TypedDict, total=False):
    run_backtest_audit: bool
    compute_reliability_score: bool
    generate_strategy_report: bool
    generate_alerts: bool


# ---------------------------------------------------------------------------
# Full bundle
# ---------------------------------------------------------------------------


class EvidenceBundleDict(TypedDict, total=False):
    """Full evidence bundle payload — all sections optional."""

    strategy_version: StrategyVersionSection
    config_snapshot: ConfigSnapshotSection
    universe_snapshot: UniverseSnapshotSection
    signal_snapshot: SignalSnapshotSection
    dataset: DatasetSection
    dataset_snapshot: DatasetSnapshotSection
    strategy_run: StrategyRunSection
    actions: ActionsSection


# ---------------------------------------------------------------------------
# Response types
# ---------------------------------------------------------------------------


class BundleObjectRef(TypedDict):
    id: str
    name: str
    type: str
    status: str          # "created" | "reused"


class BundleObjects(TypedDict, total=False):
    strategy_version: BundleObjectRef | None
    config_snapshot: BundleObjectRef | None
    universe_snapshot: BundleObjectRef | None
    signal_snapshot: BundleObjectRef | None
    dataset: BundleObjectRef | None
    dataset_snapshot: BundleObjectRef | None
    strategy_run: BundleObjectRef | None
    backtest_audit: BundleObjectRef | None
    reliability_score: BundleObjectRef | None
    report: BundleObjectRef | None


class EvidenceBundleResponseDict(TypedDict):
    strategy_id: str
    created_count: int
    reused_count: int
    actions_run: list[str]
    objects: BundleObjects
    alerts_generated: int
    warnings: list[str]
    summary: str
    timeline_events_created: int
    generated_at: str
