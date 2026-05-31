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

export interface StrategyRun {
  id: string;
  strategy_id: string;
  strategy_version_id: string | null;
  /** M7: nullable FK to a linked dataset snapshot. */
  dataset_snapshot_id: string | null;
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
}

export interface StrategyDetail extends Strategy {
  versions: StrategyVersion[];
  runs: StrategyRun[];
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
  | "strategy_run_missing_dataset_evidence";

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
