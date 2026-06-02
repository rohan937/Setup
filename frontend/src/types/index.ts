export interface NavItem {
  label: string;
  path: string;
  section?: string;
}

export interface ApiInfo {
  name: string;
  version: string;
  environment: string;
  api_version: string;
  docs_url: string;
}

export interface Project {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Strategy {
  id: string;
  project_id: string;
  project_name: string;
  name: string;
  slug: string;
  description: string | null;
  asset_class: string;
  status: string;
  run_count: number;
  latest_run_at: string | null;
  created_at: string;
  updated_at: string;
  /** M18: latest computed reliability score, null if not yet scored. */
  latest_reliability_score: StrategyReliabilityScore | null;
}

export interface StrategyVersion {
  id: string;
  strategy_id: string;
  version_label: string;
  git_commit: string | null;
  branch_name: string | null;
  code_path: string | null;
  signal_name: string | null;
  signal_description: string | null;
  created_at: string;
  updated_at: string;
  /** M15: number of config snapshots linked to this version. */
  config_snapshot_count: number;
  /** M16: number of universe snapshots linked to this version. */
  universe_snapshot_count: number;
  /** M17: number of signal snapshots linked to this version. */
  signal_snapshot_count: number;
}

// ---------------------------------------------------------------------------
// Config snapshots (M15)
// ---------------------------------------------------------------------------

export interface StrategyConfigSnapshotRead {
  id: string;
  strategy_id: string;
  strategy_version_id: string | null;
  label: string;
  source_type: string;
  source_filename: string | null;
  config_hash: string;
  param_count: number;
  assumption_count: number;
  created_at: string;
  updated_at: string;
}

export interface StrategyConfigSnapshotDetail extends StrategyConfigSnapshotRead {
  config_json: Record<string, unknown>;
}

export interface StrategyVersionCreateRequest {
  version_label: string;
  git_commit?: string;
  branch_name?: string;
  code_path?: string;
  signal_name?: string;
  signal_description?: string;
}

export interface StrategyConfigSnapshotCreateRequest {
  strategy_version_id?: string;
  label: string;
  source_type?: string;
  source_filename?: string;
  config_json: Record<string, unknown>;
}

export interface ConfigKeyChange {
  key: string;
  old_value: unknown;
  new_value: unknown;
  /** "added" | "removed" | "changed" */
  change_type: string;
}

export interface ConfigComparisonSection {
  added: ConfigKeyChange[];
  removed: ConfigKeyChange[];
  changed: ConfigKeyChange[];
  total_changes: number;
}

export interface ConfigComparisonResponse {
  snapshot_a_id: string;
  snapshot_b_id: string;
  snapshot_a_label: string;
  snapshot_b_label: string;
  is_same_config: boolean;
  top_level: ConfigComparisonSection;
  params: ConfigComparisonSection;
  assumptions: ConfigComparisonSection;
  highlighted_changes: string[];
  total_changes: number;
}

// ---------------------------------------------------------------------------
// Data evidence summary (M7)
// ---------------------------------------------------------------------------

export interface DataEvidenceSummary {
  id: string;           // snapshot id
  dataset_id: string;
  dataset_name: string;
  snapshot_label: string;
  health_score: number;
  row_count: number;
  column_count: number;
  symbol_count: number;
  min_timestamp: string | null;
  max_timestamp: string | null;
  issue_count: number;
  worst_severity: string | null;  // null when issue_count === 0
}

// ---------------------------------------------------------------------------
// Universe snapshots (M16)
// ---------------------------------------------------------------------------

/** Lightweight universe evidence embedded in strategy run responses. */
export interface UniverseSnapshotSummary {
  id: string;
  label: string;
  symbol_count: number;
  /** SHA-256 hex; display first 8 chars in UI. */
  universe_hash: string;
  strategy_version_id: string | null;
  created_at: string;
}

/** Universe snapshot summary row — no symbols_json blob. */
export interface UniverseSnapshotRead {
  id: string;
  strategy_id: string;
  strategy_version_id: string | null;
  label: string;
  source_type: string;
  source_filename: string | null;
  symbol_count: number;
  universe_hash: string;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

/** Full universe snapshot including the symbols_json payload. */
export interface UniverseSnapshotDetail extends UniverseSnapshotRead {
  symbols_json: string[];
}

export interface UniverseSnapshotCreateRequest {
  strategy_version_id?: string;
  label: string;
  source_type?: string;
  source_filename?: string;
  /** Required; normalized server-side (trimmed, uppercased, deduped, sorted). */
  symbols: string[];
  metadata_json?: Record<string, unknown>;
}

export interface UniverseComparisonResponse {
  snapshot_a_id: string;
  snapshot_b_id: string;
  snapshot_a_label: string;
  snapshot_b_label: string;
  snapshot_a_symbol_count: number;
  snapshot_b_symbol_count: number;
  is_same_universe: boolean;
  added_count: number;
  removed_count: number;
  common_symbols_count: number;
  symbol_count_delta: number;
  overlap_ratio: number;
  jaccard_similarity: number;
  /** Capped at 50. */
  added_symbols: string[];
  /** Capped at 50. */
  removed_symbols: string[];
  highlighted_changes: string[];
  deterministic_explanation: string;
}

// ---------------------------------------------------------------------------
// Signal snapshots (M17)
// ---------------------------------------------------------------------------

/** Lightweight signal evidence embedded in strategy run responses. */
export interface SignalSnapshotSummary {
  id: string;
  label: string;
  signal_name: string | null;
  row_count: number;
  symbol_count: number;
  signal_value_count: number;
  missing_signal_count: number;
  quality_score: number;
  mean_value: number | null;
  stddev_value: number | null;
  created_at: string;
}

/** Signal snapshot summary row — no rows_json blob. */
export interface SignalSnapshotRead {
  id: string;
  strategy_id: string;
  strategy_version_id: string | null;
  universe_snapshot_id: string | null;
  label: string;
  signal_name: string | null;
  source_type: string;
  source_filename: string | null;
  row_count: number;
  symbol_count: number;
  symbols_json: string[];
  min_timestamp: string | null;
  max_timestamp: string | null;
  signal_value_count: number;
  missing_signal_count: number;
  mean_value: number | null;
  min_value: number | null;
  max_value: number | null;
  stddev_value: number | null;
  signal_hash: string;
  quality_score: number;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

/** Full signal snapshot including the rows_json payload. */
export interface SignalSnapshotDetail extends SignalSnapshotRead {
  rows_json: Record<string, unknown>[];
}

export interface SignalSnapshotCreateRequest {
  strategy_version_id?: string;
  universe_snapshot_id?: string;
  label: string;
  signal_name?: string;
  source_type?: string;
  source_filename?: string;
  signal_column?: string;
  /** Required; must be a non-empty array of objects. */
  rows: Record<string, unknown>[];
  metadata_json?: Record<string, unknown>;
}

export interface SignalRowChange {
  symbol: string | null;
  timestamp: string | null;
  /** "added" | "removed" | "changed" */
  change_type: string;
  old_value: number | null;
  new_value: number | null;
  delta: number | null;
}

export interface SignalComparisonResponse {
  snapshot_a_id: string;
  snapshot_b_id: string;
  snapshot_a_label: string;
  snapshot_b_label: string;
  snapshot_a_row_count: number;
  snapshot_b_row_count: number;
  snapshot_a_symbol_count: number;
  snapshot_b_symbol_count: number;
  is_same_snapshot: boolean;
  row_count_delta: number;
  symbol_count_delta: number;
  added_count: number;
  removed_count: number;
  common_symbols_count: number;
  overlap_ratio: number;
  mean_value_delta: number | null;
  min_value_delta: number | null;
  max_value_delta: number | null;
  stddev_value_delta: number | null;
  quality_score_delta: number;
  missing_signal_delta: number;
  keyed_comparison_available: boolean;
  added_rows_count: number;
  removed_rows_count: number;
  changed_rows_count: number;
  /** Capped at 20. */
  examples: SignalRowChange[];
  /** Capped at 50. */
  added_symbols: string[];
  /** Capped at 50. */
  removed_symbols: string[];
  highlighted_changes: string[];
  deterministic_explanation: string;
  warnings: string[];
}

export interface StrategyRun {
  id: string;
  strategy_id: string;
  strategy_version_id: string | null;
  /** M7: nullable FK to a linked dataset snapshot. */
  dataset_snapshot_id: string | null;
  /** M16: nullable FK to a linked universe snapshot. */
  universe_snapshot_id: string | null;
  /** M17: nullable FK to a linked signal snapshot. */
  signal_snapshot_id: string | null;
  run_name: string;
  run_type: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  params_json: Record<string, unknown> | null;
  assumptions_json: Record<string, unknown> | null;
  metrics_json: Record<string, unknown> | null;
  universe_name: string | null;
  dataset_version: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  /** M7: lightweight data health evidence — null when no snapshot is linked. */
  dataset_snapshot: DataEvidenceSummary | null;
  /** M16: lightweight universe evidence — null when no snapshot is linked. */
  universe_snapshot: UniverseSnapshotSummary | null;
  /** M17: lightweight signal evidence — null when no signal snapshot is linked. */
  signal_snapshot: SignalSnapshotSummary | null;
}

export interface StrategyDetail extends Strategy {
  versions: StrategyVersion[];
  runs: StrategyRun[];
  /** M15: config snapshots linked to this strategy, newest-first. */
  config_snapshots: StrategyConfigSnapshotRead[];
  /** M16: universe snapshots linked to this strategy, newest-first. */
  universe_snapshots: UniverseSnapshotRead[];
  /** M17: signal snapshots linked to this strategy, newest-first. */
  signal_snapshots: SignalSnapshotRead[];
  /** M18: latest computed reliability score, null if not yet scored. */
  latest_reliability_score: StrategyReliabilityScore | null;
}

export interface StrategyCreateRequest {
  project_id: string;
  name: string;
  slug?: string;
  description?: string;
  asset_class?: string;
  status?: string;
}

export interface StrategyRunCreateRequest {
  strategy_version_id?: string;
  /** M7: optional link to a QuantFidelity dataset snapshot. */
  dataset_snapshot_id?: string;
  /** M16: optional link to a universe snapshot (must belong to same strategy). */
  universe_snapshot_id?: string;
  /** M17: optional link to a signal snapshot (must belong to same strategy). */
  signal_snapshot_id?: string;
  run_name: string;
  run_type: string;
  status?: string;
  started_at?: string;
  completed_at?: string;
  params_json?: Record<string, unknown>;
  assumptions_json?: Record<string, unknown>;
  metrics_json?: Record<string, unknown>;
  universe_name?: string;
  dataset_version?: string;
  notes?: string;
}

// ---------------------------------------------------------------------------
// Run comparison (M5)
// ---------------------------------------------------------------------------

export interface FieldChange {
  field: string;
  old_value: unknown;
  new_value: unknown;
  /** "added" | "removed" | "changed" */
  change_type: string;
  /** Numeric delta (new - old) when both values are numeric; null otherwise. */
  delta: number | null;
  /** Percent change relative to old_value; null when not applicable. */
  pct_delta: number | null;
}

export interface ComparisonSection {
  added: FieldChange[];
  removed: FieldChange[];
  changed: FieldChange[];
  unchanged_count: number;
  total_changes: number;
}

export interface RunComparisonResponse {
  strategy_id: string;
  run_a_id: string;
  run_b_id: string;
  run_a_name: string;
  run_b_name: string;
  run_a_created_at: string;
  run_b_created_at: string;
  is_same_run: boolean;
  metadata: ComparisonSection;
  params: ComparisonSection;
  assumptions: ComparisonSection;
  metrics: ComparisonSection;
  highlighted_changes: string[];
  deterministic_explanation: string;
  warnings: string[];
  total_changes: number;
}

// ---------------------------------------------------------------------------
// Data health (M6)
// ---------------------------------------------------------------------------

export interface Dataset {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  dataset_type: string;
  source_type: string;
  snapshot_count: number;
  created_at: string;
  updated_at: string;
}

export interface DatasetCreateRequest {
  project_id: string;
  name: string;
  description?: string;
  dataset_type?: string;
  source_type?: string;
}

export interface DatasetSnapshotRead {
  id: string;
  dataset_id: string;
  version_label: string;
  row_count: number;
  health_score: number;
  created_at: string;
  updated_at: string;
}

export interface DataQualityIssue {
  id: string;
  snapshot_id: string;
  issue_type: string;
  severity: string;
  field_name: string | null;
  row_index: number | null;
  detail: string | null;
  created_at: string;
}

export interface DatasetSnapshotDetail extends DatasetSnapshotRead {
  issues: DataQualityIssue[];
}

export interface DatasetDetail extends Dataset {
  snapshots: DatasetSnapshotRead[];
}

export interface DatasetSnapshotCreateRequest {
  version_label: string;
  rows: Record<string, unknown>[];
}

export interface ApiError {
  detail: string | { msg: string; type: string }[];
}

// ---------------------------------------------------------------------------
// Backtest Reality Check (M8)
// ---------------------------------------------------------------------------

export interface BacktestIssue {
  id: string;
  issue_type: string;
  severity: string;
  title: string;
  description: string;
  evidence_json: Record<string, unknown> | null;
  suggested_check: string | null;
  created_at: string;
}

export type BacktestStatus = "excellent" | "good" | "review" | "weak" | "unreliable";

// ---------------------------------------------------------------------------
// M13: Cost sensitivity + fill realism typed nested schemas
// ---------------------------------------------------------------------------

export interface CostSensitivityScenario {
  cost_bps: number;
  incremental_cost_drag: number | null;
  adjusted_annual_return: number | null;
  adjusted_sharpe: number | null;
  sharpe_delta: number | null;
}

export interface CostSensitivityResult {
  assumed_cost_bps: number | null;
  turnover: number | null;
  base_annual_return: number | null;
  base_sharpe: number | null;
  scenarios: CostSensitivityScenario[];
  warnings: string[];
  cost_fragility_level: "high" | "medium" | "low" | "unknown";
}

export interface FillRealismFinding {
  code: string;
  severity: string;
  message: string;
  suggested_check?: string;
}

export interface FillRealismResult {
  fill_model: string | null;
  slippage_bps: number | null;
  execution_timing: string | null;
  participation_rate: number | null;
  liquidity_filter_present: boolean | null;
  fill_realism_level: "strong" | "acceptable" | "review" | "weak" | "unknown";
  findings: FillRealismFinding[];
}

export interface FragilitySummary {
  overall_fragility: "high" | "medium" | "low" | "unknown";
  cost_fragility_level: "high" | "medium" | "low" | "unknown";
  fill_realism_level: "strong" | "acceptable" | "review" | "weak" | "unknown";
  key_concerns: string[];
}

// ---------------------------------------------------------------------------
// M36: Cost sweep, fill sensitivity, penalty attribution, improvement checks
// ---------------------------------------------------------------------------

export interface CostSweepScenario {
  scenario_label: string;
  trust_impact: string;
  total_cost_bps: number;
  incremental_cost_bps: number;
  estimated_cost_drag: number | null;
  adjusted_annual_return: number | null;
  adjusted_sharpe: number | null;
  sharpe_delta: number | null;
}

export interface CostSensitivitySweep {
  baseline_cost_bps: number;
  turnover: number;
  base_annual_return: number;
  base_sharpe: number;
  scenarios: CostSweepScenario[];
  most_fragile_scenario: string;
  deterministic_summary: string;
  warnings: string[];
}

export interface FillSensitivityScenario {
  scenario_label: string;
  assumed_fill_model: string;
  execution_timing_assumption: string;
  slippage_bps_assumption: number;
  trust_penalty_estimate: string;
  reason: string;
}

export interface FillSensitivity {
  reported_fill_model: string;
  fill_realism_level: string;
  worst_case_scenario: string;
  deterministic_summary: string;
  scenarios: FillSensitivityScenario[];
  warnings: string[];
}

export interface PenaltyAttributionCategory {
  category: string;
  issue_count: number;
  severity_weight: number;
  estimated_score_penalty: number;
  top_issue_titles: string[];
  suggested_check: string;
}

export interface PenaltyAttribution {
  total_estimated_penalty: number;
  largest_penalty_category: string | null;
  deterministic_summary: string;
  categories: PenaltyAttributionCategory[];
}

export interface ImprovementCheck {
  check_key: string;
  title: string;
  description: string;
  related_category: string;
  priority: string;
  evidence: string;
}

export interface BacktestAudit {
  id: string;
  strategy_run_id: string;
  trust_score: number;
  lookahead_risk_score: number;
  cost_realism_score: number;
  fill_realism_score: number;
  liquidity_realism_score: number;
  borrow_realism_score: number;
  data_quality_score: number;
  overall_status: BacktestStatus;
  summary: string;
  // M13: optional analysis blobs (null when insufficient input data)
  cost_sensitivity_json: CostSensitivityResult | null;
  fill_realism_json: FillRealismResult | null;
  fragility_summary_json: FragilitySummary | null;
  // M36: extended analysis blobs
  cost_sensitivity_sweep_json: CostSensitivitySweep | null;
  fill_sensitivity_json: FillSensitivity | null;
  penalty_attribution_json: PenaltyAttribution | null;
  improvement_checks_json: ImprovementCheck[] | null;
  issues: BacktestIssue[];
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Audit Timeline (M10)
// ---------------------------------------------------------------------------

export interface TimelineEvent {
  id: string;
  organization_id: string;
  project_id: string | null;
  strategy_id: string | null;
  event_type: string;
  title: string;
  description: string | null;
  source_type: string | null;
  source_id: string | null;
  severity: string;
  event_time: string;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
}

export interface TimelineListResponse {
  items: TimelineEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface TimelineFilters {
  project_id?: string;
  strategy_id?: string;
  event_type?: string;
  severity?: string;
  source_type?: string;
  limit?: number;
  offset?: number;
}

// ---------------------------------------------------------------------------
// Reliability Dashboard (M9)
// ---------------------------------------------------------------------------

export interface RecentEvidenceItem {
  id: string;
  item_type: string;     // "run" | "snapshot" | "audit" | "timeline_event"
  title: string;
  strategy_name: string | null;
  score: number | null;  // health_score, trust_score, etc. — null where N/A
  status: string | null;
  timestamp: string;
}

export interface DashboardCounts {
  // Strategies
  total_strategies: number;
  active_strategies: number;
  archived_strategies: number;
  strategies_by_asset_class: Record<string, number>;
  // Runs
  total_runs: number;
  backtest_run_count: number;
  research_run_count: number;
  paper_run_count: number;
  live_run_count: number;
  latest_run_at: string | null;
  // Data
  total_datasets: number;
  total_dataset_snapshots: number;
  snapshots_with_issues: number;
  total_data_quality_issues: number;
  data_issues_by_severity: Record<string, number>;
  // Backtest audits
  total_backtest_audits: number;
  total_backtest_issues: number;
  backtest_issues_by_severity: Record<string, number>;
  audits_by_status: Record<string, number>;
  // Alerts (M11)
  open_alert_count: number;
  high_critical_alert_count: number;
}

export interface DashboardScores {
  data_health_score: number | null;
  lowest_data_health_score: number | null;
  backtest_trust_score: number | null;
  lowest_backtest_trust_score: number | null;
  strategy_activity_score: number | null;
  overall_reliability_score: number | null;
  /** M18: average of latest per-strategy reliability scores. */
  average_strategy_reliability_score: number | null;
  /** M18: count of strategies per reliability status. */
  strategies_by_reliability_status: Record<string, number>;
}

export interface DashboardAlertItem {
  id: string;
  rule_type: string;
  severity: string;
  status: string;
  title: string;
  triggered_at: string;
  strategy_id: string | null;
}

export interface DashboardSummary {
  generated_at: string;
  counts: DashboardCounts;
  scores: DashboardScores;
  recent_runs: RecentEvidenceItem[];
  recent_snapshots: RecentEvidenceItem[];
  recent_audits: RecentEvidenceItem[];
  recent_timeline_events: RecentEvidenceItem[];
  recent_alerts: DashboardAlertItem[];
}

// ---------------------------------------------------------------------------
// Alerts Engine (M11)
// ---------------------------------------------------------------------------

export type AlertStatus = "open" | "acknowledged" | "resolved" | "snoozed";

export type AlertRuleType =
  | "data_health_below_threshold"
  | "backtest_trust_below_threshold"
  | "data_quality_issue_high_or_critical"
  | "backtest_issue_high_or_critical"
  | "strategy_run_missing_dataset_evidence"
  | "evidence_coverage_below_threshold"
  | "strategy_health_review_or_critical"
  | "reliability_score_deteriorating"
  | "data_health_deteriorating"
  | "signal_quality_deteriorating"
  | "backtest_trust_deteriorating"
  | "stale_strategy_run"
  | "repeated_failed_ingestion"
  | "missing_signal_evidence"
  | "missing_universe_evidence"
  | "missing_config_evidence";

export interface Alert {
  id: string;
  organization_id: string;
  rule_type: string;
  status: AlertStatus;
  severity: string;
  title: string;
  description: string | null;
  source_type: string | null;
  source_id: string | null;
  strategy_id: string | null;
  triggered_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  snoozed_until: string | null;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface AlertListResponse {
  items: Alert[];
  total: number;
  limit: number;
  offset: number;
}

export interface AlertGenerateResponse {
  alerts_created: number;
  alerts_skipped_duplicate: number;
  total_alerts_open: number;
}

export interface AlertFilters {
  status?: string;
  severity?: string;
  rule_type?: string;
  strategy_id?: string;
  limit?: number;
  offset?: number;
}

export interface AlertUpdateRequest {
  status: string;
}

export interface BacktestAuditListItem {
  id: string;
  strategy_run_id: string;
  strategy_id: string;
  strategy_name: string;
  run_name: string;
  run_type: string;
  trust_score: number;
  lookahead_risk_score: number;
  cost_realism_score: number;
  fill_realism_score: number;
  liquidity_realism_score: number;
  borrow_realism_score: number;
  data_quality_score: number;
  overall_status: BacktestStatus;
  summary: string;
  issue_count: number;
  top_issues: BacktestIssue[];
  // M13: analysis blobs (also available inline)
  cost_sensitivity_json: CostSensitivityResult | null;
  fill_realism_json: FillRealismResult | null;
  fragility_summary_json: FragilitySummary | null;
  // M13: extracted for quick display (null = unknown/unavailable)
  cost_fragility_level: string | null;
  fill_realism_level: string | null;
  // M36: extended sweep blobs (also available inline)
  cost_sensitivity_sweep_json: CostSensitivitySweep | null;
  fill_sensitivity_json: FillSensitivity | null;
  // M36: extracted for quick display (null = unknown/unavailable)
  largest_penalty_category: string | null;
  most_fragile_cost_scenario: string | null;
  worst_fill_scenario: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Dataset Snapshot Comparison (M12)
// ---------------------------------------------------------------------------

export interface MetadataComparison {
  snapshot_a_label: string;
  snapshot_b_label: string;
  row_count_a: number;
  row_count_b: number;
  row_count_delta: number;
}

export interface TypeChange {
  column: string;
  type_a: string;
  type_b: string;
}

export interface SchemaComparison {
  columns_a: string[];
  columns_b: string[];
  added_columns: string[];
  removed_columns: string[];
  type_changes: TypeChange[];
  unchanged_columns_count: number;
  total_changes: number;
}

export interface SymbolCoverageComparison {
  symbol_count_a: number;
  symbol_count_b: number;
  symbol_count_delta: number;
  added_symbols: string[];
  removed_symbols: string[];
  common_symbols_count: number;
  keyed_by_symbol: boolean;
}

export interface TimestampCoverageComparison {
  min_timestamp_a: string | null;
  max_timestamp_a: string | null;
  min_timestamp_b: string | null;
  max_timestamp_b: string | null;
  min_changed: boolean;
  max_changed: boolean;
  date_range_days_a: number | null;
  date_range_days_b: number | null;
  date_range_days_delta: number | null;
}

export interface DataHealthComparison {
  health_score_a: number;
  health_score_b: number;
  health_score_delta: number;
  issue_count_a: number;
  issue_count_b: number;
  issue_count_delta: number;
  worst_severity_a: string | null;
  worst_severity_b: string | null;
  issue_types_a: string[];
  issue_types_b: string[];
  issue_types_added: string[];
  issue_types_removed: string[];
}

export interface ValueRevisionExample {
  symbol: string | null;
  timestamp: string | null;
  change_type: "added" | "removed" | "changed";
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  changed_fields: string[];
  field_deltas: Record<string, number>;
}

export interface ValueRevisionsComparison {
  rows_available_a: boolean;
  rows_available_b: boolean;
  keyed_comparison_available: boolean;
  added_rows_count: number;
  removed_rows_count: number;
  changed_rows_count: number;
  examples: ValueRevisionExample[];
  total_examples_capped: boolean;
  max_examples: number;
}

export interface DatasetSnapshotComparisonResponse {
  dataset_id: string;
  snapshot_a_id: string;
  snapshot_b_id: string;
  snapshot_a_label: string;
  snapshot_b_label: string;
  is_same_snapshot: boolean;
  summary: string;
  metadata: MetadataComparison;
  schema_diff: SchemaComparison;
  symbol_coverage: SymbolCoverageComparison;
  timestamp_coverage: TimestampCoverageComparison;
  data_health: DataHealthComparison;
  value_revisions: ValueRevisionsComparison;
  highlighted_changes: string[];
  deterministic_explanation: string;
  warnings: string[];
  generated_at: string;
}

// ---------------------------------------------------------------------------
// Reliability Reports (M14)
// ---------------------------------------------------------------------------

export type ReportType =
  | "strategy_reliability"
  | "backtest_audit"
  | "dataset_health";

export type ReportStatus = "generated" | "stale" | "archived";

export interface ReportSection {
  id: string;
  report_id: string;
  section_key: string;
  title: string;
  summary: string;
  severity: string | null;
  order_index: number;
  evidence_json: Record<string, unknown> | null;
  created_at: string;
}

export interface ReportRead {
  id: string;
  organization_id: string;
  project_id: string | null;
  strategy_id: string | null;
  report_type: ReportType;
  title: string;
  status: ReportStatus;
  summary: string;
  generated_at: string;
  source_type: string | null;
  source_id: string | null;
  score: number | null;
  report_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ReportDetail extends ReportRead {
  sections: ReportSection[];
}

export interface ReportListResponse {
  items: ReportRead[];
  total: number;
  limit: number;
  offset: number;
}

export interface ReportFilters {
  report_type?: ReportType;
  strategy_id?: string;
  source_type?: string;
  limit?: number;
  offset?: number;
}

// ---------------------------------------------------------------------------
// Strategy Reliability Score (M18)
// ---------------------------------------------------------------------------

export interface StrategyReliabilityScore {
  id: string;
  strategy_id: string;
  overall_score: number | null;
  /** "excellent" | "good" | "review" | "weak" | "insufficient_evidence" */
  status: string;
  strategy_activity_score: number | null;
  data_evidence_score: number | null;
  backtest_trust_score: number | null;
  config_evidence_score: number | null;
  universe_evidence_score: number | null;
  signal_evidence_score: number | null;
  alert_penalty_score: number | null;
  report_coverage_score: number | null;
  evidence_counts_json: Record<string, number> | null;
  component_summaries_json: Record<string, string> | null;
  missing_evidence_json: string[] | null;
  suggested_checks_json: string[] | null;
  generated_at: string;
  created_at: string;
  updated_at: string;
}

export interface StrategyReliabilityScoreListResponse {
  total: number;
  items: StrategyReliabilityScore[];
}

// ---------------------------------------------------------------------------
// M19: Reliability score history + comparison types
// ---------------------------------------------------------------------------

export interface StrategyReliabilityScoreHistoryResponse {
  total: number;
  limit: number;
  offset: number;
  items: StrategyReliabilityScore[];
}

export interface ReliabilityComponentDelta {
  component: string;
  label: string;
  score_a: number | null;
  score_b: number | null;
  /** score_b - score_a; null if either side is null */
  delta: number | null;
  /** Was null in A, now has a value in B */
  became_available: boolean;
  /** Had a value in A, now null in B */
  became_null: boolean;
}

export interface EvidenceCountDelta {
  key: string;
  count_a: number | null;
  count_b: number | null;
  delta: number | null;
}

export interface ReliabilityScoreComparisonResponse {
  score_a_id: string;
  score_b_id: string;
  score_a_generated_at: string;
  score_b_generated_at: string;
  overall_score_a: number | null;
  overall_score_b: number | null;
  /** overall_score_b - overall_score_a; null if either is null */
  overall_delta: number | null;
  status_a: string;
  status_b: string;
  status_changed: boolean;
  component_deltas: ReliabilityComponentDelta[];
  evidence_count_deltas: EvidenceCountDelta[];
  newly_available_evidence: string[];
  resolved_missing_evidence: string[];
  still_missing_evidence: string[];
  highlighted_changes: string[];
  deterministic_explanation: string;
}

export interface ReliabilityScoreTrendResponse {
  has_trend: boolean;
  message: string;
  latest: StrategyReliabilityScore | null;
  previous: StrategyReliabilityScore | null;
  comparison: ReliabilityScoreComparisonResponse | null;
}

// ---------------------------------------------------------------------------
// M20: Strategy comparison types
// ---------------------------------------------------------------------------

export interface StrategyEvidenceCoverage {
  run_count: number;
  backtest_run_count: number;
  research_run_count: number;
  paper_run_count: number;
  live_run_count: number;
  dataset_snapshot_linked_count: number;
  backtest_audit_count: number;
  config_snapshot_count: number;
  universe_snapshot_count: number;
  signal_snapshot_count: number;
  open_alert_count: number;
  report_count: number;
  timeline_event_count: number;
  evidence_coverage_score: number;
}

export interface StrategyComparisonItem {
  strategy_id: string;
  name: string;
  slug: string;
  asset_class: string;
  status: string;
  overall_reliability_score: number | null;
  reliability_status: string | null;
  reliability_generated_at: string | null;
  strategy_activity_score: number | null;
  data_evidence_score: number | null;
  backtest_trust_score: number | null;
  config_evidence_score: number | null;
  universe_evidence_score: number | null;
  signal_evidence_score: number | null;
  alert_penalty_score: number | null;
  report_coverage_score: number | null;
  missing_evidence: string[];
  suggested_checks: string[];
  coverage: StrategyEvidenceCoverage;
  latest_run_at: string | null;
  latest_backtest_trust_score: number | null;
  latest_data_health_score: number | null;
  latest_signal_quality_score: number | null;
  latest_report_score: number | null;
  highest_severity_open_alert: string | null;
  gaps: string[];
}

export interface StrategyComparisonRankingItem {
  rank: number;
  strategy_id: string;
  name: string;
  score: number | null;
  score_label: string;
  status: string;
}

export interface StrategyComparisonRequest {
  strategy_ids: string[];
  include_archived?: boolean;
}

export interface StrategyComparisonResponse {
  strategies: StrategyComparisonItem[];
  ranked_by_reliability: StrategyComparisonRankingItem[];
  ranked_by_evidence_coverage: StrategyComparisonRankingItem[];
  strongest_strategy_id: string | null;
  weakest_strategy_id: string | null;
  shared_gaps: string[];
  differentiators: string[];
  deterministic_explanation: string;
  generated_at: string;
}

// ---------------------------------------------------------------------------
// M21: Evidence Coverage Matrix types
// ---------------------------------------------------------------------------

/** Coverage status + metadata for a single evidence layer. */
export interface EvidenceCoverageCell {
  /** "complete" | "partial" | "review" | "missing" */
  status: string;
  count: number;
  latest_at: string | null;
  summary: string;
  suggested_check: string | null;
}

/** Full coverage row for one strategy across all 11 evidence columns. */
export interface StrategyEvidenceCoverageRow {
  strategy_id: string;
  name: string;
  slug: string;
  asset_class: string;
  status: string;
  evidence_coverage_score: number;
  missing_count: number;
  review_count: number;
  partial_count: number;
  complete_count: number;
  strategy_runs: EvidenceCoverageCell;
  backtest_runs: EvidenceCoverageCell;
  dataset_evidence: EvidenceCoverageCell;
  backtest_audits: EvidenceCoverageCell;
  config_snapshots: EvidenceCoverageCell;
  universe_snapshots: EvidenceCoverageCell;
  signal_snapshots: EvidenceCoverageCell;
  alerts: EvidenceCoverageCell;
  reports: EvidenceCoverageCell;
  reliability_scores: EvidenceCoverageCell;
  timeline_events: EvidenceCoverageCell;
  suggested_next_steps: string[];
}

/** Aggregate summary over all matched strategies. */
export interface EvidenceCoverageSummary {
  strategy_count: number;
  average_coverage_score: number;
  complete_cell_count: number;
  partial_cell_count: number;
  review_cell_count: number;
  missing_cell_count: number;
  most_common_missing_evidence: string[];
}

/** Paginated evidence coverage matrix response. */
export interface EvidenceCoverageMatrixResponse {
  items: StrategyEvidenceCoverageRow[];
  total: number;
  limit: number;
  offset: number;
  generated_at: string;
  summary: EvidenceCoverageSummary;
}

export interface EvidenceCoverageParams {
  include_archived?: boolean;
  asset_class?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

// M22: Evidence Bundle Ingestion types
export interface EvidenceBundleObjectRef {
  id: string;
  name: string;
  type: string;
  status: "created" | "reused";
}

export interface EvidenceBundleObjects {
  strategy_version?: EvidenceBundleObjectRef;
  config_snapshot?: EvidenceBundleObjectRef;
  universe_snapshot?: EvidenceBundleObjectRef;
  signal_snapshot?: EvidenceBundleObjectRef;
  dataset?: EvidenceBundleObjectRef;
  dataset_snapshot?: EvidenceBundleObjectRef;
  strategy_run?: EvidenceBundleObjectRef;
  backtest_audit?: EvidenceBundleObjectRef;
  reliability_score?: EvidenceBundleObjectRef;
  report?: EvidenceBundleObjectRef;
}

export interface EvidenceBundleActions {
  run_backtest_audit?: boolean;
  compute_reliability_score?: boolean;
  generate_strategy_report?: boolean;
  generate_alerts?: boolean;
}

export interface EvidenceBundleRequest {
  strategy_version?: {
    version_label: string;
    git_commit?: string;
    branch_name?: string;
    code_path?: string;
    signal_name?: string;
    signal_description?: string;
  };
  config_snapshot?: {
    strategy_version_label?: string;
    label: string;
    source_type?: string;
    source_filename?: string;
    config_json: Record<string, unknown>;
  };
  universe_snapshot?: {
    strategy_version_label?: string;
    label: string;
    source_type?: string;
    source_filename?: string;
    symbols: string[];
    metadata_json?: Record<string, unknown>;
  };
  signal_snapshot?: {
    strategy_version_label?: string;
    universe_snapshot_label?: string;
    label: string;
    signal_name?: string;
    source_type?: string;
    source_filename?: string;
    signal_column?: string;
    rows: Record<string, unknown>[];
    metadata_json?: Record<string, unknown>;
  };
  dataset?: {
    name: string;
    slug?: string;
    description?: string;
    asset_class?: string;
    dataset_type?: string;
    source_type?: string;
  };
  dataset_snapshot?: {
    snapshot_label?: string;
    source_filename?: string;
    rows: Record<string, unknown>[];
  };
  strategy_run?: {
    strategy_version_label?: string;
    dataset_snapshot_label?: string;
    universe_snapshot_label?: string;
    signal_snapshot_label?: string;
    run_name: string;
    run_type: string;
    status?: string;
    started_at?: string;
    completed_at?: string;
    params_json?: Record<string, unknown>;
    assumptions_json?: Record<string, unknown>;
    metrics_json?: Record<string, unknown>;
    universe_name?: string;
    dataset_version?: string;
    notes?: string;
  };
  actions?: EvidenceBundleActions;
}

export interface EvidenceBundleResponse {
  strategy_id: string;
  created_count: number;
  reused_count: number;
  actions_run: string[];
  objects: EvidenceBundleObjects;
  alerts_generated: number;
  warnings: string[];
  summary: string;
  timeline_events_created: number;
  generated_at: string;
}

// ---------------------------------------------------------------------------
// M24: API Key types
// ---------------------------------------------------------------------------

export interface ApiKey {
  id: string;
  organization_id: string;
  project_id: string | null;
  project_name?: string | null;
  name: string;
  key_prefix: string;
  scopes_json: string[] | null;
  status: "active" | "revoked";
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApiKeyCreateRequest {
  name: string;
  organization_id?: string;
  project_id?: string;
  scopes?: string[];
}

export interface ApiKeyCreateResponse {
  api_key: ApiKey;
  raw_key: string;
  warning: string;
}

export interface ApiKeyListResponse {
  items: ApiKey[];
  total: number;
}

export interface ApiKeyRevokeResponse {
  id: string;
  status: string;
  revoked_at: string;
}

// ---------------------------------------------------------------------------
// M27: Strategy Health types
// ---------------------------------------------------------------------------

export type StrategyHealthStatus = "healthy" | "watch" | "review" | "critical" | "insufficient_evidence";

export interface StrategyHealth {
  strategy_id: string;
  strategy_name: string;
  asset_class: string;
  status: string;
  health_score: number | null;
  health_status: StrategyHealthStatus;
  primary_concern: string;
  latest_run_at: string | null;
  days_since_latest_run: number | null;
  latest_reliability_score: number | null;
  reliability_status: string | null;
  evidence_coverage_score: number;
  open_alert_count: number;
  high_critical_alert_count: number;
  latest_ingestion_status: string | null;
  latest_ingestion_at: string | null;
  latest_backtest_trust_score: number | null;
  latest_data_health_score: number | null;
  latest_signal_quality_score: number | null;
  latest_report_score: number | null;
  missing_evidence: string[];
  suggested_checks: string[];
  generated_at: string;
}

export interface StrategyHealthListResponse {
  items: StrategyHealth[];
  total: number;
  limit: number;
  offset: number;
  generated_at: string;
}

// ---------------------------------------------------------------------------
// M28: Project Health types
// ---------------------------------------------------------------------------

export type ProjectHealthStatus = "healthy" | "watch" | "review" | "critical" | "insufficient_evidence";

export interface ProjectHealth {
  project_id: string;
  project_name: string;
  organization_id: string;
  health_score: number | null;
  health_status: ProjectHealthStatus;
  strategy_count: number;
  healthy_strategy_count: number;
  watch_strategy_count: number;
  review_strategy_count: number;
  critical_strategy_count: number;
  insufficient_evidence_strategy_count: number;
  average_strategy_health_score: number | null;
  average_reliability_score: number | null;
  average_evidence_coverage_score: number | null;
  open_alert_count: number;
  high_critical_alert_count: number;
  recent_failed_ingestion_count: number;
  latest_activity_at: string | null;
  primary_concern: string;
  suggested_checks: string[];
  generated_at: string;
}

export interface ProjectHealthListResponse {
  items: ProjectHealth[];
  total: number;
  limit: number;
  offset: number;
  generated_at: string;
}

// ---------------------------------------------------------------------------
// M29: Run History and Timeline Drilldown types
// ---------------------------------------------------------------------------

export interface StrategyRunVersionSummary {
  version_id: string;
  version_label: string;
  git_commit: string | null;
  branch_name: string | null;
  signal_name: string | null;
}

export interface RunDatasetEvidence {
  dataset_snapshot_id: string;
  dataset_name: string;
  snapshot_label: string;
  health_score: number;
  issue_count: number;
  worst_severity: string | null;
}

export interface RunUniverseEvidence {
  universe_snapshot_id: string;
  label: string;
  symbol_count: number;
  universe_hash: string;
}

export interface RunSignalEvidence {
  signal_snapshot_id: string;
  label: string;
  signal_name: string | null;
  quality_score: number;
  missing_signal_count: number;
  symbol_count: number;
  mean_value: number | null;
  stddev_value: number | null;
}

export interface RunBacktestAuditSummary {
  audit_id: string;
  trust_score: number;
  overall_status: string;
  issue_count: number;
  high_critical_issue_count: number;
  cost_fragility_level: string | null;
  fill_realism_level: string | null;
}

export type RunHealthLabel = "strong" | "usable" | "review" | "weak" | "insufficient_evidence";

export interface StrategyRunHistoryItem {
  run_id: string;
  run_name: string;
  run_type: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  params_json: Record<string, unknown> | null;
  assumptions_json: Record<string, unknown> | null;
  metrics_json: Record<string, unknown> | null;
  notes: string | null;
  strategy_version: StrategyRunVersionSummary | null;
  dataset_evidence: RunDatasetEvidence | null;
  universe_evidence: RunUniverseEvidence | null;
  signal_evidence: RunSignalEvidence | null;
  backtest_audit: RunBacktestAuditSummary | null;
  has_dataset_evidence: boolean;
  has_universe_evidence: boolean;
  has_signal_evidence: boolean;
  has_backtest_audit: boolean;
  has_strategy_version: boolean;
  run_health_label: RunHealthLabel;
}

export interface StrategyRunHistorySummary {
  total_runs: number;
  strong_count: number;
  usable_count: number;
  review_count: number;
  weak_count: number;
  insufficient_evidence_count: number;
  runs_missing_dataset: number;
  runs_missing_signal: number;
  runs_missing_universe: number;
  runs_missing_audit: number;
  latest_run_at: string | null;
}

export interface StrategyRunHistoryResponse {
  items: StrategyRunHistoryItem[];
  total: number;
  limit: number;
  offset: number;
  summary: StrategyRunHistorySummary;
}

export interface StrategyTimelineDrilldownItem {
  event_id: string;
  event_type: string;
  title: string;
  severity: string;
  description: string | null;
  source_type: string | null;
  source_id: string | null;
  linked_url_hint: string | null;
  event_time: string;
  created_at: string;
  evidence_category: string;
  source_label: string;
}

export interface StrategyTimelineDrilldownSummary {
  total_events: number;
  event_type_counts: Record<string, number>;
  source_type_counts: Record<string, number>;
  latest_event_at: string | null;
}

export interface StrategyTimelineDrilldownResponse {
  items: StrategyTimelineDrilldownItem[];
  total: number;
  limit: number;
  offset: number;
  summary: StrategyTimelineDrilldownSummary;
}

// ---------------------------------------------------------------------------
// M30: Evidence Trends
// ---------------------------------------------------------------------------

export interface TrendPoint {
  id: string;
  label: string;
  value: number | null;
  status: string | null;
  timestamp: string;
  metadata_json?: Record<string, unknown> | null;
}

export type EvidenceTrendDirection =
  | "improving"
  | "deteriorating"
  | "flat"
  | "insufficient_history";

export interface TrendSummary {
  points: TrendPoint[];
  latest_value: number | null;
  previous_value: number | null;
  delta: number | null;
  direction: EvidenceTrendDirection;
  point_count: number;
  min_value: number | null;
  max_value: number | null;
  average_value: number | null;
  latest_label: string | null;
  latest_at: string | null;
  deterministic_summary: string;
}

export interface EvidenceCoverageCurrent {
  evidence_coverage_score: number;
  missing_count: number;
  review_count: number;
  complete_count: number;
}

export interface StrategyEvidenceTrendsResponse {
  strategy_id: string;
  strategy_name: string;
  generated_at: string;
  reliability_trend: TrendSummary;
  data_health_trend: TrendSummary;
  backtest_trust_trend: TrendSummary;
  signal_quality_trend: TrendSummary;
  coverage_current: EvidenceCoverageCurrent | null;
  overall_summary: string;
  suggested_checks: string[];
}

// ---------------------------------------------------------------------------
// M31: Strategy Evidence Export
// ---------------------------------------------------------------------------

export interface StrategyExportSection {
  section_key: string;
  title: string;
  summary: string;
  severity: string | null;
  evidence_json?: object | null;
}

export interface StrategyExportMetadata {
  export_id: string;
  strategy_id: string;
  strategy_name: string;
  strategy_slug: string;
  generated_at: string;
  format: string;
  filename: string;
  milestone: string;
  note: string;
}

export interface StrategyExportResponse {
  format: string;
  filename: string;
  metadata: StrategyExportMetadata;
  sections: StrategyExportSection[];
  content?: string | null;
  raw_evidence?: object | null;
}

// ---------------------------------------------------------------------------
// M32: Portfolio Overview
// ---------------------------------------------------------------------------

export interface PortfolioTrendFlags {
  reliability_deteriorating: boolean;
  data_health_deteriorating: boolean;
  backtest_trust_deteriorating: boolean;
  signal_quality_deteriorating: boolean;
}

export interface PortfolioStrategyItem {
  strategy_id: string;
  name: string;
  slug: string;
  asset_class: string;
  status: string;
  health_score: number | null;
  health_status: string;
  primary_concern: string;
  reliability_score: number | null;
  reliability_status: string | null;
  evidence_coverage_score: number;
  open_alert_count: number;
  high_critical_alert_count: number;
  latest_run_at: string | null;
  days_since_latest_run: number | null;
  trend_flags: PortfolioTrendFlags;
  missing_evidence_count: number;
  review_reason: string | null;
}

export interface PortfolioRecentActivityItem {
  strategy_name: string;
  event_type: string;
  description: string;
  timestamp: string;
}

export interface PortfolioOverview {
  generated_at: string;
  strategy_count: number;
  active_strategy_count: number;
  archived_strategy_count: number;
  average_health_score: number | null;
  average_reliability_score: number | null;
  average_evidence_coverage_score: number | null;
  open_alert_count: number;
  high_critical_alert_count: number;
  strategies_by_health_status: Record<string, number>;
  strategies_by_reliability_status: Record<string, number>;
  strategies_by_asset_class: Record<string, number>;
  all_items: PortfolioStrategyItem[];
  top_review_strategies: PortfolioStrategyItem[];
  most_under_instrumented_strategies: PortfolioStrategyItem[];
  strongest_evidence_strategies: PortfolioStrategyItem[];
  deteriorating_trend_strategies: PortfolioStrategyItem[];
  recent_activity: PortfolioRecentActivityItem[];
  suggested_next_steps: string[];
  deterministic_summary: string;
}

// ---------------------------------------------------------------------------
// M34: Multi-Run Comparison
// ---------------------------------------------------------------------------

export interface RunMetrics {
  sharpe: number | null;
  sortino: number | null;
  annual_return: number | null;
  volatility: number | null;
  max_drawdown: number | null;
  turnover: number | null;
  hit_rate: number | null;
  trade_count: number | null;
  alpha_bps: number | null;
  transaction_cost_bps: number | null;
  slippage_bps: number | null;
}

export interface RunAssumptions {
  transaction_cost_bps: number | null;
  slippage_bps: number | null;
  borrow_cost_bps: number | null;
  fill_model: string | null;
  short_enabled: boolean | null;
  execution_timing: string | null;
}

export interface RunEvidenceSummary {
  dataset_health_score: number | null;
  signal_quality_score: number | null;
  universe_symbol_count: number | null;
  backtest_trust_score: number | null;
  dataset_issue_count: number;
  signal_missing_count: number;
  backtest_issue_count: number;
  dataset_label: string | null;
  signal_label: string | null;
  universe_label: string | null;
  backtest_status: string | null;
  cost_fragility_level: string | null;
  fill_realism_level: string | null;
  run_health_label: string;
}

export interface MultiRunComparisonItem {
  strategy_id: string;
  strategy_name: string;
  asset_class: string;
  status: string;
  run_id: string;
  run_name: string;
  run_type: string;
  run_status: string;
  completed_at: string | null;
  strategy_version_label: string | null;
  created_at: string;
  open_alert_count: number;
  reliability_score: number | null;
  reliability_status: string | null;
  evidence_coverage_score: number | null;
  metrics: RunMetrics;
  assumptions: RunAssumptions;
  evidence: RunEvidenceSummary;
}

export interface MultiRunRankingItem {
  rank: number;
  strategy_id: string;
  strategy_name: string;
  value_label: string;
  run_name: string;
  value: number | null;
}

export interface MultiRunComparisonRequest {
  strategy_ids: string[];
  mode?: string;
  run_ids?: string[];
}

export interface MultiRunComparisonResponse {
  compared_at: string;
  mode: string;
  deterministic_explanation: string;
  items: MultiRunComparisonItem[];
  metric_matrix: Record<string, Record<string, number | null>>;
  assumption_matrix: Record<string, Record<string, number | null>>;
  evidence_matrix: Record<string, Record<string, number | null>>;
  rankings: Record<string, MultiRunRankingItem[]>;
  gaps: Record<string, string[]>;
  shared_gaps: string[];
  highlighted_differences: string[];
  suggested_next_steps: string[];
}

// M35: Version Lineage
export interface StrategyVersionLineageItem {
  version_id: string;
  version_label: string;
  git_commit: string | null;
  branch_name: string | null;
  code_path: string | null;
  signal_name: string | null;
  signal_description: string | null;
  created_at: string;
  updated_at: string;
  run_count: number;
  backtest_run_count: number;
  research_run_count: number;
  paper_run_count: number;
  live_run_count: number;
  config_snapshot_count: number;
  universe_snapshot_count: number;
  signal_snapshot_count: number;
  dataset_linked_run_count: number;
  backtest_audit_count: number;
  latest_run_at: string | null;
  latest_config_snapshot_label: string | null;
  latest_universe_snapshot_label: string | null;
  latest_signal_snapshot_label: string | null;
  latest_backtest_trust_score: number | null;
  latest_data_health_score: number | null;
  latest_signal_quality_score: number | null;
  has_config: boolean;
  has_universe: boolean;
  has_signal: boolean;
  has_runs: boolean;
  has_dataset_linked_runs: boolean;
  has_backtest_audit: boolean;
  version_evidence_score: number;
  lineage_status: string;
  suggested_checks: string[];
}

export interface StrategyVersionTransition {
  from_version_label: string;
  to_version_label: string;
  created_at_delta_days: number;
  git_commit_changed: boolean;
  branch_changed: boolean;
  signal_name_changed: boolean;
  config_hash_changed: boolean | null;
  universe_hash_changed: boolean | null;
  signal_hash_changed: boolean | null;
}

export interface StrategyVersionLineageSummary {
  strategy_id: string;
  strategy_name: string;
  latest_version_label: string;
  version_count: number;
  versions_missing_config: number;
  versions_missing_signal: number;
  versions_missing_universe: number;
  versions_without_runs: number;
  most_instrumented_version_id: string | null;
  least_instrumented_version_id: string | null;
  average_version_evidence_score: number | null;
  deterministic_summary: string;
  generated_at: string;
}

export interface StrategyVersionLineageResponse {
  summary: StrategyVersionLineageSummary;
  versions: StrategyVersionLineageItem[];
  transitions: StrategyVersionTransition[];
}

// ---------------------------------------------------------------------------
// M39: Universe Coverage Analysis
// ---------------------------------------------------------------------------

export interface UniverseSymbolQuality {
  symbol: string;
  normalized_symbol: string;
  quality_status: string;
  is_duplicate: boolean;
  has_invalid_format: boolean;
  format_issues: string[];
  issues: string[];
}

export interface UniverseMetadataBreakdown {
  has_symbol_metadata: boolean;
  metadata_coverage_rate: number;
  missing_metadata_symbols: number;
  by_sector: Record<string, number>;
  by_country: Record<string, number>;
  by_exchange: Record<string, number>;
  by_liquidity_bucket: Record<string, number>;
  warnings: string[];
}

export interface UniverseDelta {
  has_previous: boolean;
  previous_snapshot_id: string | null;
  previous_label: string | null;
  delta_status: string | null;
  added_symbols: string[];
  removed_symbols: string[];
  common_symbols_count: number;
  added_count: number;
  removed_count: number;
  overlap_ratio: number | null;
  jaccard_similarity: number | null;
  churn_rate: number | null;
}

export interface UniverseQualitySummary {
  symbol_count: number;
  unique_symbol_count: number;
  duplicate_symbol_count: number;
  invalid_symbol_count: number;
  clean_symbol_count: number;
  review_symbol_count: number;
  weak_symbol_count: number;
  coverage_status: string;
  suggested_checks: string[];
}

export interface UniverseCoverageAnalysis extends UniverseQualitySummary {
  linked_run_count: number;
  is_used_by_runs: boolean;
  linkage_status: string | null;
  version_label: string | null;
}

export interface UniverseCoverageAnalysisResponse {
  snapshot_id: string;
  strategy_id: string;
  label: string;
  universe_hash: string;
  symbol_count: number;
  generated_at: string;
  coverage_analysis: UniverseCoverageAnalysis;
  symbol_quality: UniverseSymbolQuality[];
  metadata_breakdown: UniverseMetadataBreakdown;
  universe_delta: UniverseDelta;
  quality_summary: UniverseQualitySummary;
  warnings: string[];
}

// ---------------------------------------------------------------------------
// M37: Dataset Quality Drilldown
// ---------------------------------------------------------------------------

export interface ColumnQuality {
  column_name: string;
  inferred_type: string;
  quality_status: string;
  non_null_count: number;
  null_count: number;
  unique_count: number;
  duplicate_value_count: number;
  numeric_count: number;
  string_count: number;
  boolean_count: number;
  timestamp_parseable_count: number;
  invalid_timestamp_count: number;
  zero_count: number;
  negative_count: number;
  outlier_count: number;
  null_rate: number;
  min_value: number | null;
  max_value: number | null;
  mean_value: number | null;
  stddev_value: number | null;
  sample_values: string[];
  issues: string[];
}

export interface RowQualitySample {
  row_index: number;
  issue_type: string;
  severity: string;
  summary: string;
  evidence_json: Record<string, unknown>;
}

export interface RowQualitySamples {
  duplicate_rows: RowQualitySample[];
  duplicate_symbol_timestamp: RowQualitySample[];
  invalid_timestamp_rows: RowQualitySample[];
  invalid_ohlc_rows: RowQualitySample[];
  suspicious_return_rows: RowQualitySample[];
  missing_value_rows: RowQualitySample[];
  outlier_rows: RowQualitySample[];
}

export interface DatasetQualitySummary {
  total_rows: number;
  total_columns: number;
  clean_column_count: number;
  review_column_count: number;
  weak_column_count: number;
  unusable_column_count: number;
  total_missing_values: number;
  total_outliers: number;
  total_invalid_timestamps: number;
  total_duplicate_rows: number;
  total_duplicate_symbol_timestamps: number;
  worst_columns: string[];
  suggested_checks: string[];
}

export interface DatasetQualityDrilldownResponse {
  snapshot_id: string;
  dataset_id: string;
  dataset_name: string;
  snapshot_label: string;
  health_score: number;
  row_count: number;
  column_count: number;
  generated_at: string;
  column_quality: ColumnQuality[];
  row_quality: RowQualitySamples;
  quality_summary: DatasetQualitySummary;
  warnings: string[];
}

// ---------------------------------------------------------------------------
// M38: Signal Quality Drilldown
// ---------------------------------------------------------------------------

export interface SignalDistribution {
  signal_column: string;
  distribution_status: string;
  value_count: number;
  missing_count: number;
  non_numeric_count: number;
  zero_count: number;
  positive_count: number;
  negative_count: number;
  unique_value_count: number;
  outlier_count: number;
  extreme_positive_count: number;
  extreme_negative_count: number;
  mean_value: number | null;
  median_value: number | null;
  min_value: number | null;
  max_value: number | null;
  stddev_value: number | null;
  issues: string[];
}

export interface SymbolSignalQuality {
  symbol: string;
  quality_status: string;
  row_count: number;
  signal_value_count: number;
  missing_signal_count: number;
  non_numeric_count: number;
  duplicate_timestamp_count: number;
  outlier_count: number;
  missing_rate: number;
  min_timestamp: string | null;
  max_timestamp: string | null;
  mean_value: number | null;
  stddev_value: number | null;
  issues: string[];
}

export interface SignalTimestampCoverage {
  timestamp_status: string;
  total_timestamp_count: number;
  duplicate_symbol_timestamp_count: number;
  invalid_timestamp_count: number;
  min_timestamp: string | null;
  max_timestamp: string | null;
  symbols_with_gaps_count: number | null;
}

export interface SignalRowQualitySample {
  row_index: number;
  issue_type: string;
  severity: string;
  summary: string;
  symbol: string | null;
  timestamp: string | null;
  signal_value: string | null;
  evidence_json: Record<string, unknown>;
}

export interface SignalRowQualitySamples {
  missing_signal_rows: SignalRowQualitySample[];
  non_numeric_signal_rows: SignalRowQualitySample[];
  duplicate_symbol_timestamp_rows: SignalRowQualitySample[];
  outlier_signal_rows: SignalRowQualitySample[];
  invalid_timestamp_rows: SignalRowQualitySample[];
}

export interface SignalQualitySummary {
  total_rows: number;
  symbol_count: number;
  signal_value_count: number;
  missing_signal_count: number;
  non_numeric_signal_count: number;
  outlier_count: number;
  duplicate_symbol_timestamp_count: number;
  invalid_timestamp_count: number;
  clean_symbol_count: number;
  review_symbol_count: number;
  weak_symbol_count: number;
  unusable_symbol_count: number;
  worst_symbols: string[];
  suggested_checks: string[];
}

export interface SignalQualityDrilldownResponse {
  snapshot_id: string;
  strategy_id: string;
  label: string;
  signal_name: string | null;
  quality_score: number | null;
  row_count: number;
  symbol_count: number;
  generated_at: string;
  signal_distribution: SignalDistribution;
  symbol_quality: SymbolSignalQuality[];
  timestamp_coverage: SignalTimestampCoverage;
  row_quality: SignalRowQualitySamples;
  quality_summary: SignalQualitySummary;
  warnings: string[];
}
