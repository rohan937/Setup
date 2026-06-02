from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------

class StrategyCreate(BaseModel):
    """Request body for POST /api/strategies."""

    project_id: uuid.UUID
    name: Annotated[str, StringConstraints(min_length=1, max_length=255, strip_whitespace=True)]
    slug: str | None = Field(default=None, max_length=100)
    description: str | None = None
    # See constants.AssetClass for valid values.  Defaults to equity.
    asset_class: str = "equity"
    # See constants.StrategyStatus for valid values.  Defaults to active.
    status: str = "active"


class StrategyVersionCreate(BaseModel):
    """Request body for POST /api/strategies/{strategy_id}/versions (M15)."""

    version_label: Annotated[str, StringConstraints(min_length=1, max_length=100, strip_whitespace=True)]
    git_commit: str | None = Field(default=None, max_length=255)
    branch_name: str | None = Field(default=None, max_length=255)
    code_path: str | None = Field(default=None, max_length=512)
    signal_name: str | None = Field(default=None, max_length=255)
    signal_description: str | None = None


class StrategyConfigSnapshotCreate(BaseModel):
    """Request body for POST /api/strategies/{strategy_id}/config-snapshots (M15)."""

    strategy_version_id: uuid.UUID | None = None
    label: Annotated[str, StringConstraints(min_length=1, max_length=255, strip_whitespace=True)]
    source_type: str = "manual_json"
    source_filename: str | None = Field(default=None, max_length=512)
    # Must be a JSON object (not array/scalar); validated in route.
    config_json: dict[str, Any]


class UniverseSnapshotCreate(BaseModel):
    """Request body for POST /api/strategies/{strategy_id}/universe-snapshots (M16)."""

    strategy_version_id: uuid.UUID | None = None
    label: Annotated[str, StringConstraints(min_length=1, max_length=255, strip_whitespace=True)]
    source_type: str = "manual_json"
    source_filename: str | None = Field(default=None, max_length=512)
    # Required list of symbols; normalized server-side.
    symbols: list[str]
    # Optional metadata dict; stored verbatim.
    metadata_json: dict[str, Any] | None = None


class SignalSnapshotCreate(BaseModel):
    """Request body for POST /api/strategies/{strategy_id}/signal-snapshots (M17)."""

    strategy_version_id: uuid.UUID | None = None
    universe_snapshot_id: uuid.UUID | None = None
    label: Annotated[str, StringConstraints(min_length=1, max_length=255, strip_whitespace=True)]
    signal_name: str | None = Field(default=None, max_length=255)
    source_type: str = "manual_json"
    source_filename: str | None = Field(default=None, max_length=512)
    # Column name for signal values within each row dict; default "signal"
    signal_column: str = "signal"
    # Required; must be a non-empty JSON array of objects.
    rows: list[dict[str, Any]]
    # Optional metadata dict; stored verbatim.
    metadata_json: dict[str, Any] | None = None


class StrategyRunCreate(BaseModel):
    """Request body for POST /api/strategies/{strategy_id}/runs."""

    strategy_version_id: uuid.UUID | None = None
    # M7: optional link to a QuantFidelity dataset snapshot (must be in the same project).
    dataset_snapshot_id: uuid.UUID | None = None
    # M16: optional link to a universe snapshot (must belong to the same strategy).
    universe_snapshot_id: uuid.UUID | None = None
    # M17: optional link to a signal snapshot (must belong to the same strategy).
    signal_snapshot_id: uuid.UUID | None = None
    run_name: Annotated[str, StringConstraints(min_length=1, max_length=255, strip_whitespace=True)]
    # See constants.RunType for valid values.  Required.
    run_type: str
    # See constants.RunStatus for valid values.  Defaults to completed.
    status: str = "completed"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    # Each JSON field must be a dict (object) if provided, not an array or scalar.
    params_json: dict | None = None
    assumptions_json: dict | None = None
    metrics_json: dict | None = None
    universe_name: str | None = Field(default=None, max_length=255)
    # Free-text label retained alongside dataset_snapshot_id for unlinked runs.
    dataset_version: str | None = Field(default=None, max_length=255)
    notes: str | None = None


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

class DataEvidenceSummary(BaseModel):
    """Lightweight data health evidence embedded in strategy run responses (M7).

    Computed from a linked DatasetSnapshot and its quality issues.
    Never embeds raw rows or full issue lists.
    """

    id: uuid.UUID                 # snapshot id
    dataset_id: uuid.UUID
    dataset_name: str
    snapshot_label: str           # version_label
    health_score: int
    row_count: int
    column_count: int
    symbol_count: int
    min_timestamp: str | None
    max_timestamp: str | None
    issue_count: int
    worst_severity: str | None    # None when issue_count == 0


class UniverseSnapshotSummary(BaseModel):
    """Lightweight universe evidence embedded in strategy run responses (M16).

    Never embeds the full symbol list.
    """

    id: uuid.UUID
    label: str
    symbol_count: int
    universe_hash: str            # 64-char hex; display first 8 chars in UI
    strategy_version_id: uuid.UUID | None
    created_at: datetime


class UniverseSnapshotRead(BaseModel):
    """Universe snapshot summary — no symbols_json blob (used in list responses)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version_id: uuid.UUID | None
    label: str
    source_type: str
    source_filename: str | None
    symbol_count: int
    universe_hash: str
    metadata_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class UniverseSnapshotDetail(UniverseSnapshotRead):
    """Full universe snapshot including the symbols_json payload."""

    symbols_json: list[str]


class UniverseComparisonResponse(BaseModel):
    """Deterministic universe comparison result."""

    snapshot_a_id: uuid.UUID
    snapshot_b_id: uuid.UUID
    snapshot_a_label: str
    snapshot_b_label: str
    snapshot_a_symbol_count: int
    snapshot_b_symbol_count: int
    is_same_universe: bool
    added_count: int
    removed_count: int
    common_symbols_count: int
    symbol_count_delta: int
    overlap_ratio: float
    jaccard_similarity: float
    # Capped at 50 each in the response; counts are exact.
    added_symbols: list[str]
    removed_symbols: list[str]
    highlighted_changes: list[str]
    deterministic_explanation: str


class SignalSnapshotSummary(BaseModel):
    """Lightweight signal evidence embedded in strategy run responses (M17)."""

    id: uuid.UUID
    label: str
    signal_name: str | None
    row_count: int
    symbol_count: int
    signal_value_count: int
    missing_signal_count: int
    quality_score: int
    mean_value: float | None
    stddev_value: float | None
    created_at: datetime


class SignalSnapshotRead(BaseModel):
    """Signal snapshot summary — no rows_json blob (used in list responses)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version_id: uuid.UUID | None
    universe_snapshot_id: uuid.UUID | None
    label: str
    signal_name: str | None
    source_type: str
    source_filename: str | None
    row_count: int
    symbol_count: int
    symbols_json: list[str]
    min_timestamp: str | None
    max_timestamp: str | None
    signal_value_count: int
    missing_signal_count: int
    mean_value: float | None
    min_value: float | None
    max_value: float | None
    stddev_value: float | None
    signal_hash: str
    quality_score: int
    metadata_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class SignalSnapshotDetail(SignalSnapshotRead):
    """Full signal snapshot including the rows_json payload."""

    rows_json: list[dict[str, Any]]


class SignalRowChangeOut(BaseModel):
    symbol: str | None
    timestamp: str | None
    change_type: str  # "added" | "removed" | "changed"
    old_value: float | None = None
    new_value: float | None = None
    delta: float | None = None


class SignalComparisonResponse(BaseModel):
    snapshot_a_id: uuid.UUID
    snapshot_b_id: uuid.UUID
    snapshot_a_label: str
    snapshot_b_label: str
    snapshot_a_row_count: int
    snapshot_b_row_count: int
    snapshot_a_symbol_count: int
    snapshot_b_symbol_count: int
    is_same_snapshot: bool
    row_count_delta: int
    symbol_count_delta: int
    added_count: int
    removed_count: int
    common_symbols_count: int
    overlap_ratio: float
    mean_value_delta: float | None
    min_value_delta: float | None
    max_value_delta: float | None
    stddev_value_delta: float | None
    quality_score_delta: int
    missing_signal_delta: int
    keyed_comparison_available: bool
    added_rows_count: int
    removed_rows_count: int
    changed_rows_count: int
    examples: list[SignalRowChangeOut]
    added_symbols: list[str]
    removed_symbols: list[str]
    highlighted_changes: list[str]
    deterministic_explanation: str
    warnings: list[str]


class StrategyVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    version_label: str
    git_commit: str | None
    branch_name: str | None
    code_path: str | None
    signal_name: str | None
    signal_description: str | None
    created_at: datetime
    updated_at: datetime
    # M15: config snapshot count for this version (populated by route if requested)
    config_snapshot_count: int = 0
    # M16: universe snapshot count for this version
    universe_snapshot_count: int = 0
    # M17: signal snapshot count for this version
    signal_snapshot_count: int = 0


class StrategyConfigSnapshotRead(BaseModel):
    """Config snapshot summary — no config_json blob (used in list responses)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version_id: uuid.UUID | None
    label: str
    source_type: str
    source_filename: str | None
    config_hash: str
    param_count: int
    assumption_count: int
    created_at: datetime
    updated_at: datetime


class StrategyConfigSnapshotDetail(StrategyConfigSnapshotRead):
    """Full config snapshot including the config_json payload."""

    config_json: dict[str, Any]


class ConfigKeyChangeOut(BaseModel):
    key: str
    old_value: Any = None
    new_value: Any = None
    change_type: str  # "added" | "removed" | "changed"


class ConfigComparisonSectionOut(BaseModel):
    added: list[ConfigKeyChangeOut] = []
    removed: list[ConfigKeyChangeOut] = []
    changed: list[ConfigKeyChangeOut] = []
    total_changes: int = 0


class ConfigComparisonResponse(BaseModel):
    snapshot_a_id: uuid.UUID
    snapshot_b_id: uuid.UUID
    snapshot_a_label: str
    snapshot_b_label: str
    is_same_config: bool
    top_level: ConfigComparisonSectionOut
    params: ConfigComparisonSectionOut
    assumptions: ConfigComparisonSectionOut
    highlighted_changes: list[str]
    total_changes: int


# ---------------------------------------------------------------------------
# M40: Enriched config diff schemas
# ---------------------------------------------------------------------------

class ConfigFieldChange(BaseModel):
    key: str
    key_path: str
    old_value: Any = None
    new_value: Any = None
    change_type: str  # "added" | "removed" | "changed"
    category: str
    impact_level: str  # "positive" | "neutral" | "review" | "weakening" | "unknown"
    impact_reason: str
    suggested_check: str | None = None


class ConfigDiffSection(BaseModel):
    changes: list[ConfigFieldChange] = []
    unchanged_count: int = 0
    added_count: int = 0
    removed_count: int = 0
    changed_count: int = 0


class ConfigSnapshotComparisonV2Response(BaseModel):
    snapshot_a_id: uuid.UUID
    snapshot_b_id: uuid.UUID
    snapshot_a_label: str
    snapshot_b_label: str
    is_same_config: bool
    total_changes: int
    params_diff: ConfigDiffSection
    assumptions_diff: ConfigDiffSection
    portfolio_diff: ConfigDiffSection
    risk_diff: ConfigDiffSection
    all_changes: list[ConfigFieldChange] = []
    weakening_changes: list[ConfigFieldChange] = []
    positive_changes: list[ConfigFieldChange] = []
    review_changes: list[ConfigFieldChange] = []
    highlighted_changes: list[str] = []
    suggested_checks: list[str] = []
    deterministic_explanation: str

    model_config = ConfigDict(from_attributes=True)


class StrategyRunOut(BaseModel):
    """Strategy run response — built manually in route handlers (not from_attributes).

    dataset_snapshot is populated only when the run has a linked snapshot
    and the route eagerly loads StrategyRun.snapshot → dataset + issues.
    universe_snapshot is populated only when the run has a linked universe snapshot.
    """

    id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version_id: uuid.UUID | None
    # M7: nullable FK to a linked dataset snapshot.
    dataset_snapshot_id: uuid.UUID | None = None
    # M16: nullable FK to a linked universe snapshot.
    universe_snapshot_id: uuid.UUID | None = None
    # M17: nullable FK to a linked signal snapshot.
    signal_snapshot_id: uuid.UUID | None = None
    run_name: str
    run_type: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    params_json: dict | None
    assumptions_json: dict | None
    metrics_json: dict | None
    universe_name: str | None
    dataset_version: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    # M7: data evidence summary — None when no snapshot is linked.
    dataset_snapshot: DataEvidenceSummary | None = None
    # M16: universe evidence summary — None when no universe snapshot is linked.
    universe_snapshot: UniverseSnapshotSummary | None = None
    # M17: signal evidence summary — None when no signal snapshot is linked.
    signal_snapshot: SignalSnapshotSummary | None = None


class StrategyReliabilityScoreRead(BaseModel):
    """Reliability score record for a strategy (M18)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    overall_score: float | None
    status: str
    strategy_activity_score: float | None
    data_evidence_score: float | None
    backtest_trust_score: float | None
    config_evidence_score: float | None
    universe_evidence_score: float | None
    signal_evidence_score: float | None
    alert_penalty_score: float | None
    report_coverage_score: float | None
    evidence_counts_json: dict | None
    component_summaries_json: dict | None
    missing_evidence_json: list[str] | None
    suggested_checks_json: list[str] | None
    generated_at: datetime
    created_at: datetime
    updated_at: datetime


class StrategyReliabilityScoreListResponse(BaseModel):
    """Paginated list of reliability scores (M18)."""

    total: int
    items: list[StrategyReliabilityScoreRead]


# ---------------------------------------------------------------------------
# M19: Score history response
# ---------------------------------------------------------------------------

class StrategyReliabilityScoreHistoryResponse(BaseModel):
    """Paginated per-strategy reliability score history (M19)."""

    total: int
    limit: int
    offset: int
    items: list[StrategyReliabilityScoreRead]


# ---------------------------------------------------------------------------
# M19: Score comparison schemas
# ---------------------------------------------------------------------------

class ReliabilityComponentDelta(BaseModel):
    """Per-component change between two reliability score rows (M19)."""

    component: str
    label: str
    score_a: float | None
    score_b: float | None
    delta: float | None        # score_b - score_a; None if either is None
    became_available: bool     # was None, now has value
    became_null: bool          # had value, now None


class EvidenceCountDelta(BaseModel):
    """Change in an evidence count key between two score rows (M19)."""

    key: str
    count_a: int | None
    count_b: int | None
    delta: int | None


class ReliabilityScoreComparisonResponse(BaseModel):
    """Deterministic score-to-score comparison result (M19).

    Score A is the earlier/baseline; score B is the later/current.
    No causal claims. No AI.
    """

    score_a_id: uuid.UUID
    score_b_id: uuid.UUID
    score_a_generated_at: datetime
    score_b_generated_at: datetime
    overall_score_a: float | None
    overall_score_b: float | None
    overall_delta: float | None
    status_a: str
    status_b: str
    status_changed: bool
    component_deltas: list[ReliabilityComponentDelta]
    evidence_count_deltas: list[EvidenceCountDelta]
    newly_available_evidence: list[str]
    resolved_missing_evidence: list[str]
    still_missing_evidence: list[str]
    highlighted_changes: list[str]
    deterministic_explanation: str


class ReliabilityScoreTrendResponse(BaseModel):
    """Latest vs. previous reliability score comparison for a strategy (M19).

    ``has_trend`` is False when fewer than two scores exist — no fake data.
    """

    has_trend: bool
    message: str
    latest: StrategyReliabilityScoreRead | None = None
    previous: StrategyReliabilityScoreRead | None = None
    comparison: ReliabilityScoreComparisonResponse | None = None


class StrategyListItemOut(BaseModel):
    """Strategy summary row used in the list endpoint."""

    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    name: str
    slug: str
    description: str | None
    asset_class: str
    status: str
    run_count: int
    latest_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # M18: latest reliability score (None if not yet computed)
    latest_reliability_score: StrategyReliabilityScoreRead | None = None


class StrategyDetailOut(StrategyListItemOut):
    """Full strategy detail with versions, runs, config snapshots, and universe snapshots."""

    versions: list[StrategyVersionOut] = []
    runs: list[StrategyRunOut] = []
    config_snapshots: list[StrategyConfigSnapshotRead] = []
    # M16: recent universe snapshots, newest-first.
    universe_snapshots: list[UniverseSnapshotRead] = []
    # M17: recent signal snapshots, newest-first.
    signal_snapshots: list[SignalSnapshotRead] = []
    # M18: latest reliability score
    latest_reliability_score: StrategyReliabilityScoreRead | None = None


# ---------------------------------------------------------------------------
# M20: Strategy comparison schemas
# ---------------------------------------------------------------------------


class StrategyEvidenceCoverage(BaseModel):
    """Evidence coverage counts for one strategy in a comparison (M20)."""

    run_count: int
    backtest_run_count: int
    research_run_count: int
    paper_run_count: int
    live_run_count: int
    dataset_snapshot_linked_count: int
    backtest_audit_count: int
    config_snapshot_count: int
    universe_snapshot_count: int
    signal_snapshot_count: int
    open_alert_count: int
    report_count: int
    timeline_event_count: int
    evidence_coverage_score: float


class StrategyComparisonItem(BaseModel):
    """One strategy's evidence summary in a side-by-side comparison (M20)."""

    strategy_id: uuid.UUID
    name: str
    slug: str
    asset_class: str
    status: str
    overall_reliability_score: float | None
    reliability_status: str | None
    reliability_generated_at: datetime | None
    strategy_activity_score: float | None
    data_evidence_score: float | None
    backtest_trust_score: float | None
    config_evidence_score: float | None
    universe_evidence_score: float | None
    signal_evidence_score: float | None
    alert_penalty_score: float | None
    report_coverage_score: float | None
    missing_evidence: list[str]
    suggested_checks: list[str]
    coverage: StrategyEvidenceCoverage
    latest_run_at: datetime | None
    latest_backtest_trust_score: float | None
    latest_data_health_score: float | None
    latest_signal_quality_score: float | None
    latest_report_score: float | None
    highest_severity_open_alert: str | None
    gaps: list[str]


class StrategyComparisonRankingItem(BaseModel):
    """One strategy's rank in a comparison ranking list (M20)."""

    rank: int
    strategy_id: uuid.UUID
    name: str
    score: float | None
    score_label: str   # formatted score string or "—"
    status: str


class StrategyComparisonRequest(BaseModel):
    """Request body for POST /api/strategies/compare (M20)."""

    strategy_ids: list[str]
    include_archived: bool = False


class StrategyComparisonResponse(BaseModel):
    """Full strategy comparison result (M20).

    Evidence-based comparison only — never investment advice.
    Language: "higher current reliability score", "better evidenced",
    "more complete instrumentation". Never "better strategy", "more profitable".
    """

    strategies: list[StrategyComparisonItem]
    ranked_by_reliability: list[StrategyComparisonRankingItem]
    ranked_by_evidence_coverage: list[StrategyComparisonRankingItem]
    strongest_strategy_id: uuid.UUID | None
    weakest_strategy_id: uuid.UUID | None
    shared_gaps: list[str]
    differentiators: list[str]
    deterministic_explanation: str
    generated_at: datetime


# Keep the plain StrategyOut for any internal callers that still use it.
class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    asset_class: str
    status: str
    created_at: datetime
    updated_at: datetime
