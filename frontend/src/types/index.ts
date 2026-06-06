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
  /** M58: optional human-readable tag for the run. */
  run_tag?: string | null;
  /** M58: lifecycle stage of the run (e.g. "backtest", "shadow", "live"). */
  stage?: string | null;
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

export type AlertStatus =
  | "open"
  | "acknowledged"
  | "resolved"
  | "snoozed"
  | "dismissed";

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
  /** M85: deterministic recommended remediation, null when none applies. */
  recommended_fix: string | null;
  /** M85: assigned owner user id, null when unassigned. */
  owner_user_id: string | null;
  /** M85: type of the linked evidence object (alias of source_type). */
  evidence_type: string | null;
  /** M85: id of the linked evidence object (alias of source_id). */
  evidence_id: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// M85: Alert history, rules, and summaries
// ---------------------------------------------------------------------------

export interface AlertHistory {
  id: string;
  alert_id: string;
  actor_user_id: string | null;
  action: string;
  note: string | null;
  created_at: string;
}

export interface AlertHistoryListResponse {
  items: AlertHistory[];
}

export interface AlertRule {
  id: string;
  rule_key: string;
  enabled: boolean;
  severity: string;
  threshold_json: Record<string, unknown> | null;
  strategy_id: string | null;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertRuleListResponse {
  items: AlertRule[];
}

export interface AlertSeverityBreakdown {
  critical: number;
  high: number;
  medium: number;
  low: number;
}

export interface AlertSummary {
  open: number;
  acknowledged: number;
  snoozed: number;
  resolved: number;
  by_severity: AlertSeverityBreakdown;
}

export interface StrategyAlertSummary extends AlertSummary {
  blocking_promotion: number;
}

export interface AlertActionRequest {
  note?: string;
}

export interface AlertSnoozeRequest {
  hours?: number;
  snoozed_until?: string;
  note?: string;
}

export interface AlertRuleUpdateRequest {
  enabled?: boolean;
  severity?: string;
  threshold_json?: Record<string, unknown>;
  name?: string;
  description?: string;
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
  /** M85: alerts auto-resolved because their condition no longer holds. */
  alerts_auto_resolved: number;
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
  status?: string;
  owner_user_id?: string | null;
  note?: string;
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

// ---------------------------------------------------------------------------
// M40: Config Snapshot Diff V2
// ---------------------------------------------------------------------------

export interface ConfigFieldChange {
  key: string;
  key_path: string;
  change_type: string;
  category: string;
  impact_level: string;
  impact_reason: string;
  old_value: unknown;
  new_value: unknown;
  suggested_check: string | null;
}

export interface ConfigDiffSection {
  changes: ConfigFieldChange[];
  unchanged_count: number;
  added_count: number;
  removed_count: number;
  changed_count: number;
}

export interface ConfigSnapshotComparisonV2Response {
  snapshot_a_id: string;
  snapshot_b_id: string;
  snapshot_a_label: string;
  snapshot_b_label: string;
  deterministic_explanation: string;
  is_same_config: boolean;
  total_changes: number;
  params_diff: ConfigDiffSection;
  assumptions_diff: ConfigDiffSection;
  portfolio_diff: ConfigDiffSection;
  risk_diff: ConfigDiffSection;
  all_changes: ConfigFieldChange[];
  weakening_changes: ConfigFieldChange[];
  positive_changes: ConfigFieldChange[];
  review_changes: ConfigFieldChange[];
  highlighted_changes: string[];
  suggested_checks: string[];
}

// ---------------------------------------------------------------------------
// M41: Assumption Health
// ---------------------------------------------------------------------------

export interface AssumptionCategoryScorecard {
  category_key: string;
  title: string;
  status: string;
  score: number | null;
  evidence_count: number;
  positive_evidence: string[];
  review_items: string[];
  weakening_changes: string[];
  suggested_checks: string[];
}

export interface ConfigDiffAssumptionSummary {
  snapshot_a_label: string | null;
  snapshot_b_label: string | null;
  total_changes: number;
  positive_change_count: number;
  weakening_change_count: number;
  review_change_count: number;
  key_assumption_changes: Record<string, unknown>[];
  warning: string | null;
}

export interface BacktestAuditAssumptionSummary {
  backtest_audit_id: string;
  trust_score: number;
  overall_status: string;
  cost_fragility_level: string | null;
  fill_realism_level: string | null;
  largest_penalty_category: string | null;
  top_improvement_checks: unknown[];
}

export interface StrategyAssumptionHealthResponse {
  strategy_id: string;
  strategy_name: string;
  status: string;
  deterministic_summary: string;
  overall_assumption_score: number | null;
  generated_at: string;
  category_scorecards: AssumptionCategoryScorecard[];
  latest_config_diff_summary: ConfigDiffAssumptionSummary | null;
  latest_backtest_audit_summary: BacktestAuditAssumptionSummary | null;
  key_assumption_changes: Record<string, unknown>[];
  weakening_change_count: number;
  positive_change_count: number;
  review_change_count: number;
  suggested_checks: string[];
}

// ---------------------------------------------------------------------------
// M43: Timeline Analytics
// ---------------------------------------------------------------------------

export interface TimelineAnalyticsBucket {
  bucket_start: string;
  bucket_end: string;
  total_events: number;
  event_type_counts: Record<string, number>;
  source_type_counts: Record<string, number>;
  evidence_category_counts: Record<string, number>;
}

export interface TimelineInactivityGap {
  gap_start: string;
  gap_end: string;
  gap_days: number;
  previous_event_title: string | null;
  next_event_title: string | null;
}

export type TimelineStalenessStatus = "active" | "watch" | "stale" | "no_activity";

export interface StrategyTimelineAnalyticsResponse {
  strategy_id: string;
  strategy_name: string;
  bucket: string;
  staleness_status: TimelineStalenessStatus;
  deterministic_summary: string;
  generated_at: string;
  lookback_days: number;
  total_events: number;
  active_bucket_count: number;
  empty_bucket_count: number;
  most_active_bucket_event_count: number;
  latest_event_at: string | null;
  most_active_bucket_start: string | null;
  days_since_latest_event: number | null;
  longest_inactivity_gap_days: number | null;
  dominant_event_type: string | null;
  dominant_evidence_category: string | null;
  buckets: TimelineAnalyticsBucket[];
  gaps: TimelineInactivityGap[];
  suggested_checks: string[];
}

// ---------------------------------------------------------------------------
// M44: Strategy Comparison Report
// ---------------------------------------------------------------------------

export interface StrategyComparisonReportRequest {
  strategy_ids: string[];
  format?: string;
  include_raw_json?: boolean;
}

export interface StrategyComparisonReportMetadata {
  report_id: string;
  format: string;
  note: string;
  generated_at: string;
  strategy_count: number;
  strategy_ids: string[];
}

export interface StrategyComparisonReportSection {
  section_key: string;
  title: string;
  summary: string;
  severity: string | null;
  evidence_json: Record<string, unknown> | null;
}

export interface StrategyComparisonReportStrategySummary {
  strategy_id: string;
  name: string;
  asset_class: string;
  status: string;
  health_status: string | null;
  health_score: number | null;
  primary_concern: string | null;
  reliability_score: number | null;
  reliability_status: string | null;
  evidence_coverage_score: number | null;
  assumption_status: string | null;
  assumption_score: number | null;
  reliability_trend: string | null;
  data_health_trend: string | null;
  backtest_trust_trend: string | null;
  signal_quality_trend: string | null;
  weakening_change_count: number;
  positive_change_count: number;
  open_alert_count: number;
  high_critical_alert_count: number;
  suggested_checks: string[];
}

export interface StrategyComparisonReportResponse {
  format: string;
  filename: string;
  metadata: StrategyComparisonReportMetadata;
  sections: StrategyComparisonReportSection[];
  strategy_summaries: StrategyComparisonReportStrategySummary[];
  rankings: Record<string, unknown[]>;
  suggested_review_agenda: string[];
  content: string | null;
  raw_evidence: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// M45: System Health
// ---------------------------------------------------------------------------

export interface SystemEntityCounts {
  total_strategies: number;
  active_strategies: number;
  total_runs: number;
  total_datasets: number;
  total_dataset_snapshots: number;
  total_signal_snapshots: number;
  total_universe_snapshots: number;
  total_config_snapshots: number;
  total_backtest_audits: number;
  total_timeline_events: number;
  open_alerts: number;
  total_alerts: number;
  total_reports: number;
  total_api_keys: number;
  active_api_keys: number;
  total_ingestion_batches: number;
}

export interface SystemIngestionHealth {
  total_batches: number;
  completed_batches: number;
  failed_batches: number;
  recent_failed_batches_count: number;
  failure_rate: number;
  latest_batch_at: string | null;
  latest_failed_batch_at: string | null;
  ingestion_status: string;
}

export interface SystemApiKeyHealth {
  active_api_keys: number;
  revoked_api_keys: number;
  keys_used_last_7d: number;
  keys_never_used: number;
  stale_keys_count: number;
  api_key_status: string;
}

export interface SystemEvidenceActivity {
  events_last_24h: number;
  events_last_7d: number;
  events_last_30d: number;
  latest_event_at: string | null;
  activity_status: string;
}

export interface SystemProjectHealthRollup {
  project_count_by_health_status: Record<string, number>;
  projects_requiring_review: Array<Record<string, unknown>>;
  healthiest_projects: Array<Record<string, unknown>>;
}

export interface SystemStrategyHealthRollup {
  strategy_count_by_health_status: Record<string, number>;
  strategies_requiring_review: Array<Record<string, unknown>>;
  most_active_strategies: Array<Record<string, unknown>>;
}

export interface SystemOperationalActivityItem {
  item_type: string;
  title: string;
  timestamp: string | null;
  detail: string | null;
}

export interface SystemHealthResponse {
  generated_at: string;
  environment: string;
  db_type: string;
  note: string;
  system_status: string;
  system_score: number | null;
  entity_counts: SystemEntityCounts;
  ingestion_health: SystemIngestionHealth;
  api_key_health: SystemApiKeyHealth;
  evidence_activity: SystemEvidenceActivity;
  project_health_rollup: SystemProjectHealthRollup;
  strategy_health_rollup: SystemStrategyHealthRollup;
  recent_activity: SystemOperationalActivityItem[];
  suggested_operational_checks: string[];
}

// ---------------------------------------------------------------------------
// M46: Demo Mode
// ---------------------------------------------------------------------------

export interface DemoSeedRequest {
  mode?: string;
  confirm_reset?: boolean;
  include_reports?: boolean;
  include_alerts?: boolean;
  include_backtest_audits?: boolean;
}

export interface DemoSeedResponse {
  mode: string;
  summary: string;
  organization_id: string | null;
  project_id: string | null;
  strategy_ids: string[];
  created_counts: Record<string, number>;
  reused_counts: Record<string, number>;
  reset_counts: Record<string, number>;
  generated_artifacts: string[];
  warnings: string[];
}

export interface DemoStatusResponse {
  demo_org_exists: boolean;
  demo_project_exists: boolean;
  strategy_count: number;
  demo_strategy_names: string[];
  generated_artifacts: string[];
  last_seeded_at: string | null;
  summary: string;
}

// M78: advanced demo strategy seed
export interface AdvancedDemoSeedResponse {
  status: string; // created | refreshed
  strategy_id: string;
  strategy_name: string;
  strategy_slug: string;
  organization_id: string;
  project_id: string;
  counts: Record<string, number>;
  total_artifacts: number;
  summary: string;
  disclaimer: string;
}

// ---------------------------------------------------------------------------
// M47: Strategy Drift
// ---------------------------------------------------------------------------

export interface StrategyDriftRunSummary {
  run_id: string;
  run_name: string;
  run_type: string;
  status: string;
  run_health_label: string;
  created_at: string;
  completed_at: string | null;
  strategy_version_label: string | null;
  dataset_health: number | null;
  signal_quality: number | null;
  backtest_trust: number | null;
  universe_symbol_count: number | null;
  metrics_json: Record<string, unknown> | null;
  assumptions_json: Record<string, unknown> | null;
}

export interface MetricDriftItem {
  metric: string;
  direction: string;
  severity: string;
  baseline_value: number | null;
  comparison_value: number | null;
  absolute_delta: number | null;
  percent_delta: number | null;
}

export interface EvidenceDriftItem {
  evidence_type: string;
  severity: string;
  explanation: string;
  baseline_value: number | null;
  comparison_value: number | null;
  delta: number | null;
}

export interface AssumptionDriftItem {
  key_path: string;
  change_type: string;
  impact_level: string;
  old_value: unknown;
  new_value: unknown;
  suggested_check: string | null;
}

export interface TrustDriftItem {
  dimension: string;
  severity: string;
  explanation: string;
  baseline_value: number | null;
  comparison_value: number | null;
  delta: number | null;
}

export interface StrategyDriftResponse {
  strategy_id: string;
  strategy_name: string;
  mode: string;
  drift_status: string;
  deterministic_summary: string;
  generated_at: string;
  drift_score: number | null;
  baseline_run: StrategyDriftRunSummary | null;
  comparison_run: StrategyDriftRunSummary | null;
  stage_path: unknown[];
  metric_drifts: MetricDriftItem[];
  evidence_drifts: EvidenceDriftItem[];
  assumption_drifts: AssumptionDriftItem[];
  trust_drifts: TrustDriftItem[];
  highlighted_drifts: string[];
  suggested_checks: string[];
}

// ---------------------------------------------------------------------------
// M48: Evidence Freshness
// ---------------------------------------------------------------------------

export type EvidenceFreshnessStatus =
  | "fresh"
  | "aging"
  | "stale"
  | "missing"
  | "missing_evidence";

export interface EvidenceFreshnessItem {
  evidence_type: string;
  label: string;
  status: EvidenceFreshnessStatus;
  severity: string;
  summary: string;
  latest_at: string | null;
  days_since_latest: number | null;
  count: number;
  threshold_days: number;
  suggested_check: string | null;
  latest_object_id: string | null;
  latest_object_label: string | null;
}

export interface StrategyEvidenceFreshnessResponse {
  strategy_id: string;
  strategy_name: string;
  freshness_status: string;
  deterministic_summary: string;
  generated_at: string;
  overall_freshness_score: number | null;
  stale_count: number;
  missing_count: number;
  aging_count: number;
  fresh_count: number;
  evidence_items: EvidenceFreshnessItem[];
  oldest_evidence_type: string | null;
  freshest_evidence_type: string | null;
  suggested_refresh_order: string[];
}

// ---------------------------------------------------------------------------
// M49: Strategy Readiness
// ---------------------------------------------------------------------------

export type StrategyReadinessVerdict =
  | "ready_for_backtest_review"
  | "ready_for_paper_trading_consideration"
  | "requires_review_before_progression"
  | "under_instrumented"
  | "blocked";

export interface StrategyReadinessDimension {
  dimension_key: string;
  title: string;
  status: string;
  evidence_summary: string;
  score: number | null;
  blockers: string[];
  warnings: string[];
  suggested_actions: string[];
}

export interface StrategyProgressionPath {
  current_stage: string;
  next_recommended_stage: string;
  required_before_next_stage: string[];
}

export interface StrategyReadinessResponse {
  strategy_id: string;
  strategy_name: string;
  readiness_verdict: StrategyReadinessVerdict;
  verdict_label: string;
  verdict_summary: string;
  deterministic_summary: string;
  generated_at: string;
  readiness_score: number | null;
  dimension_scorecards: StrategyReadinessDimension[];
  blockers: string[];
  review_items: string[];
  suggested_next_actions: string[];
  progression_path: StrategyProgressionPath;
}

// ---------------------------------------------------------------------------
// M50: Shadow Production Monitor
// ---------------------------------------------------------------------------

export type ShadowMonitorStatus =
  | "stable"
  | "watch"
  | "review"
  | "severe"
  | "no_shadow_runs"
  | "insufficient_baseline";

export interface ShadowRunSummary {
  run_id: string;
  run_name: string;
  run_type: string;
  status: string;
  run_health_label: string;
  created_at: string;
  completed_at: string | null;
  strategy_version_label: string | null;
  dataset_health: number | null;
  signal_quality: number | null;
  backtest_trust: number | null;
  universe_symbol_count: number | null;
  metrics_json: object | null;
  assumptions_json: object | null;
}

export interface ShadowMetricComparison {
  metric_key: string;
  direction: string;
  severity: string;
  explanation: string;
  baseline_value: number | null;
  comparison_value: number | null;
  absolute_delta: number | null;
  percent_delta: number | null;
}

export interface ShadowEvidenceComparison {
  evidence_type: string;
  severity: string;
  explanation: string;
  baseline_value: number | null;
  comparison_value: number | null;
  delta: number | null;
}

export interface ShadowAssumptionChange {
  key_path: string;
  change_type: string;
  impact_level: string;
  old_value: unknown;
  new_value: unknown;
  impact_reason: string | null;
  suggested_check: string | null;
}

export interface ShadowTrustComparison {
  dimension: string;
  severity: string;
  explanation: string;
  baseline_value: number | null;
  comparison_value: number | null;
  delta: number | null;
}

export interface ShadowProductionCheck {
  check_key: string;
  title: string;
  severity: string;
  evidence: string;
  passed: boolean;
  suggested_action: string | null;
}

export interface StrategyShadowMonitorResponse {
  strategy_id: string;
  strategy_name: string;
  monitor_status: ShadowMonitorStatus;
  deterministic_summary: string;
  generated_at: string;
  shadow_stability_score: number | null;
  baseline_run: ShadowRunSummary | null;
  shadow_run: ShadowRunSummary | null;
  metric_comparisons: ShadowMetricComparison[];
  evidence_comparisons: ShadowEvidenceComparison[];
  assumption_changes: ShadowAssumptionChange[];
  trust_comparison: ShadowTrustComparison[];
  production_checks: ShadowProductionCheck[];
  highlighted_findings: string[];
  blockers: string[];
  suggested_actions: string[];
}

// ---------------------------------------------------------------------------
// M51: Promotion Gates
// ---------------------------------------------------------------------------

export type StrategyStage =
  | "idea"
  | "research"
  | "backtest_review"
  | "paper_candidate"
  | "shadow_production"
  | "production_candidate"
  | "archived";

export type PromotionVerdict =
  | "pass"
  | "conditional_pass"
  | "requires_review"
  | "blocked"
  | "insufficient_evidence";

export interface PromotionGateCheck {
  gate_key: string;
  title: string;
  category: string;
  status: string;
  severity: string;
  evidence_summary: string;
  required: boolean;
  passed: boolean;
  observed_value: string | null;
  required_value: string | null;
  suggested_action: string | null;
}

export interface StrategyPromotionGateResponse {
  strategy_id: string;
  strategy_name: string;
  current_stage: string;
  target_stage: string;
  promotion_verdict: PromotionVerdict;
  deterministic_summary: string;
  note: string;
  generated_at: string;
  gate_score: number | null;
  required_pass_count: number;
  required_fail_count: number;
  recommended_pass_count: number;
  recommended_fail_count: number;
  blocker_count: number;
  review_count: number;
  gate_checks: PromotionGateCheck[];
  blockers: string[];
  warnings: string[];
  suggested_actions: string[];
  stage_path: string[];
}

// ---------------------------------------------------------------------------
// M52: Evidence Dependency Graph
// ---------------------------------------------------------------------------

export interface EvidenceGraphNode {
  node_id: string;
  node_type: string;
  label: string;
  status: string;
  severity: string;
  subtitle: string | null;
  route_hint: string | null;
  created_at: string | null;
  updated_at: string | null;
  score: number | null;
  metadata_json: Record<string, unknown>;
}

export interface EvidenceGraphEdge {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  relationship: string;
  label: string;
  metadata_json: Record<string, unknown>;
}

export interface EvidenceBlastRadius {
  focus_node_id: string;
  focus_node_type: string;
  blast_radius_severity: string;
  upstream_count: number;
  downstream_count: number;
  affected_run_count: number;
  affected_report_count: number;
  affected_alert_count: number;
  affected_audit_count: number;
  affected_readiness: boolean;
  affected_shadow_monitor: boolean;
  affected_promotion_gates: boolean;
  affected_nodes: EvidenceGraphNode[];
}

export interface EvidenceGraphSummary {
  strategy_id: string;
  strategy_name: string;
  graph_status: string;
  deterministic_summary: string;
  generated_at: string;
  node_count: number;
  edge_count: number;
  weak_node_count: number;
  missing_node_count: number;
  high_critical_alert_node_count: number;
  connected_run_count: number;
  orphan_evidence_count: number;
  suggested_checks: string[];
}

export interface StrategyEvidenceGraphResponse {
  summary: EvidenceGraphSummary;
  nodes: EvidenceGraphNode[];
  edges: EvidenceGraphEdge[];
  blast_radius: EvidenceBlastRadius | null;
}

// ---------------------------------------------------------------------------
// M53: Regression Test Suite
// ---------------------------------------------------------------------------

export type RegressionTestStatus = "passed" | "warning" | "failed" | "skipped";

export type RegressionTestOverallStatus =
  | "passed"
  | "warning"
  | "failed"
  | "insufficient_evidence";

export interface StrategyRegressionTest {
  id: string;
  strategy_id: string;
  name: string;
  test_key: string;
  test_type: string;
  operator: string;
  severity: string;
  metric_key: string | null;
  threshold_value: number | null;
  threshold_json: unknown | null;
  is_required: boolean;
  is_enabled: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface StrategyRegressionTestRunRequest {
  mode?: string;
  baseline_run_id?: string | null;
  comparison_run_id?: string | null;
  suite_label?: string | null;
}

export interface StrategyRegressionTestResult {
  id: string;
  test_key: string;
  title: string;
  status: string;
  severity: string;
  is_required: boolean;
  observed_value: string | null;
  expected_value: string | null;
  baseline_value: string | null;
  comparison_value: string | null;
  suggested_action: string | null;
  evidence_json: Record<string, unknown> | null;
  created_at: string;
}

export interface StrategyRegressionTestRun {
  id: string;
  strategy_id: string;
  mode: string;
  overall_status: string;
  suite_label: string | null;
  baseline_run_id: string | null;
  comparison_run_id: string | null;
  passed_count: number;
  failed_count: number;
  warning_count: number;
  skipped_count: number;
  required_failed_count: number;
  deterministic_summary: string | null;
  results: StrategyRegressionTestResult[];
  created_at: string;
}

export interface StrategyRegressionTestRunListResponse {
  items: StrategyRegressionTestRun[];
  total: number;
  limit: number;
  offset: number;
}

// ============================================================
// M54 — Config Policy Engine
// ============================================================

export interface StrategyConfigPolicy {
  id: string;
  strategy_id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  policy_json: Record<string, unknown>;
  rule_count: number;
  created_at: string;
  updated_at: string;
}

export interface StrategyConfigPolicyCreate {
  name: string;
  description?: string;
  is_active?: boolean;
  policy_json: Record<string, unknown>;
}

export interface ConfigPolicyEvaluationRequest {
  config_snapshot_id?: string;
}

export interface ConfigPolicyResult {
  id: string;
  evaluation_id: string;
  rule_key: string;
  title: string;
  status: 'passed' | 'warning' | 'failed' | 'skipped';
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical';
  is_required: boolean;
  observed_value: string | null;
  expected_value: string | null;
  key_path: string | null;
  evidence_json: Record<string, unknown> | null;
  suggested_action: string | null;
  created_at: string;
}

export interface ConfigPolicyEvaluation {
  id: string;
  strategy_id: string;
  policy_id: string;
  config_snapshot_id: string | null;
  overall_status: 'passed' | 'warning' | 'failed' | 'insufficient_evidence';
  passed_count: number;
  warning_count: number;
  failed_count: number;
  skipped_count: number;
  critical_failed_count: number;
  result_json: unknown | null;
  deterministic_summary: string | null;
  created_at: string;
  results: ConfigPolicyResult[];
}

export interface ConfigPolicyEvaluationListResponse {
  items: ConfigPolicyEvaluation[];
  total: number;
}

// ============================================================
// M55 — Research Review Cases
// ============================================================

export type ResearchReviewCaseStatus = 'open' | 'acknowledged' | 'resolved';

export interface ResearchReviewCaseEvent {
  id: string;
  case_id: string;
  event_type: string;
  title: string;
  description: string | null;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
}

export interface ResearchReviewCase {
  id: string;
  strategy_id: string;
  title: string;
  case_key: string;
  status: ResearchReviewCaseStatus;
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical';
  category: string;
  summary: string | null;
  deterministic_summary: string | null;
  evidence_json: Record<string, unknown> | null;
  suggested_actions_json: string[] | null;
  linked_alert_ids_json: string[] | null;
  linked_regression_run_ids_json: string[] | null;
  linked_policy_evaluation_ids_json: string[] | null;
  linked_backtest_audit_ids_json: string[] | null;
  linked_run_ids_json: string[] | null;
  linked_snapshot_ids_json: string[] | null;
  opened_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
  events: ResearchReviewCaseEvent[];
}

export interface ResearchReviewCaseGenerateResponse {
  strategy_id: string;
  generated_count: number;
  refreshed_count: number;
  total_open: number;
  cases: ResearchReviewCase[];
}

export interface ResearchReviewCaseListResponse {
  items: ResearchReviewCase[];
  total: number;
}

// ============================================================
// M56 — Evidence SLA Monitor
// ============================================================

export interface EvidenceSLAPolicy {
  id: string;
  strategy_id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  policy_json: Record<string, unknown>;
  rule_count: number;
  created_at: string;
  updated_at: string;
}

export interface EvidenceSLAPolicyCreate {
  name: string;
  description?: string;
  is_active?: boolean;
  policy_json: Record<string, unknown>;
}

export interface EvidenceSLAResult {
  id: string;
  evaluation_id: string;
  rule_key: string;
  title: string;
  evidence_type: string | null;
  status: 'passed' | 'warning' | 'violated' | 'skipped';
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical';
  is_required: boolean;
  observed_value: string | null;
  expected_value: string | null;
  days_since_latest: number | null;
  latest_at: string | null;
  evidence_json: Record<string, unknown> | null;
  suggested_action: string | null;
  created_at: string;
}

export interface EvidenceSLAEvaluation {
  id: string;
  strategy_id: string;
  policy_id: string;
  overall_status: 'passed' | 'warning' | 'violated' | 'insufficient_evidence';
  passed_count: number;
  warning_count: number;
  violated_count: number;
  skipped_count: number;
  critical_violation_count: number;
  result_json: unknown | null;
  deterministic_summary: string | null;
  created_at: string;
  results: EvidenceSLAResult[];
}

export interface EvidenceSLAEvaluationListResponse {
  items: EvidenceSLAEvaluation[];
  total: number;
}

// M57 - Strategy Change Impact Analysis
export type ChangeImpactStatus =
  | "no_change_detected"
  | "low"
  | "medium"
  | "high"
  | "requires_review";

export interface ChangeImpactFocusNode {
  node_id: string;
  node_type: string;
  label: string;
  created_at: string | null;
  score: number | null;
  status: string | null;
  route_hint: string | null;
  metadata_json: unknown | null;
}

export interface ImpactedArtifact {
  artifact_id: string;
  artifact_type: string;
  label: string;
  relationship: string;
  impact_level: "none" | "low" | "medium" | "high" | "critical";
  reason: string;
  current_status: string | null;
  current_score: number | null;
  route_hint: string | null;
  suggested_recheck: string | null;
}

export interface RecommendedRecheck {
  recheck_key: string;
  title: string;
  priority: "low" | "medium" | "high" | "critical";
  reason: string;
  endpoint_hint: string | null;
  depends_on: string[];
  status: "recommended" | "required" | "optional" | "not_needed";
}

export interface AssumptionImpactSummary {
  has_assumption_change: boolean;
  positive_change_count: number;
  weakening_change_count: number;
  review_change_count: number;
  key_changes: string[];
  impact_level: string;
  suggested_checks: string[];
}

export interface QualityImpactSummary {
  quality_impact_count: number;
  degraded_quality_count: number;
  missing_quality_count: number;
  key_quality_findings: string[];
}

export interface ReadinessImpactSummary {
  readiness_verdict: string | null;
  promotion_risk_count: number;
  failed_regression_count: number;
  failed_policy_count: number;
  sla_violation_count: number;
  open_review_case_count: number;
  impact_level: string;
  suggested_checks: string[];
}

export interface GraphBlastRadiusSummary {
  available: boolean;
  upstream_count: number;
  downstream_count: number;
  affected_run_count: number;
  affected_report_count: number;
  affected_alert_count: number;
  affected_audit_count: number;
  affected_readiness: boolean;
  affected_shadow_monitor: boolean;
  affected_promotion_gates: boolean;
  blast_radius_severity: string;
}

export interface StrategyChangeImpactResponse {
  strategy_id: string;
  strategy_name: string;
  generated_at: string;
  mode: string;
  focus_node: ChangeImpactFocusNode | null;
  impact_status: ChangeImpactStatus;
  impact_score: number | null;
  downstream_summary: string;
  impacted_artifacts: ImpactedArtifact[];
  recommended_rechecks: RecommendedRecheck[];
  assumption_impacts: AssumptionImpactSummary;
  quality_impacts: QualityImpactSummary;
  readiness_impacts: ReadinessImpactSummary;
  graph_blast_radius: GraphBlastRadiusSummary | null;
  deterministic_summary: string;
  suggested_actions: string[];
}

// M58 - Run Replay Pack
export type RunReplayStatus = "complete" | "review" | "incomplete" | "sparse";

export interface RunReplaySection {
  section_key: string;
  title: string;
  summary: string;
  severity: string | null;
  evidence_json: Record<string, unknown>;
}

export interface RunReplayMissingEvidence {
  evidence_type: string;
  severity: "low" | "medium" | "high";
  suggested_action: string;
}

export interface RunReplayMetadata {
  replay_id: string;
  generated_at: string;
  format: string;
  strategy_id: string;
  run_id: string;
  filename: string;
  deterministic_note: string;
  no_execution_replay_note: string;
}

export interface RunReplayResponse {
  metadata: RunReplayMetadata;
  replay_status: RunReplayStatus;
  replay_completeness_score: number;
  sections: RunReplaySection[];
  missing_evidence: RunReplayMissingEvidence[];
  suggested_review_checks: string[];
  content: string | null;
  raw_evidence: Record<string, unknown> | null;
}

// M59 - Experiment Registry
export interface StrategyExperiment {
  id: string;
  strategy_id: string;
  name: string;
  slug: string;
  description: string | null;
  experiment_type: string | null;
  hypothesis: string | null;
  status: "active" | "archived";
  metadata_json: Record<string, unknown> | null;
  run_count: number;
  created_at: string;
  updated_at: string;
}

export interface StrategyExperimentRun {
  id: string;
  experiment_id: string;
  strategy_run_id: string;
  variant_label: string | null;
  variant_key: string | null;
  variant_params_json: Record<string, unknown> | null;
  notes: string | null;
  created_at: string;
}

export interface StrategyExperimentDetail extends StrategyExperiment {
  experiment_runs: StrategyExperimentRun[];
}

export interface StrategyExperimentCreate {
  name: string;
  description?: string;
  experiment_type?: string;
  hypothesis?: string;
  slug?: string;
}

export interface ExperimentRunAddRequest {
  strategy_run_id: string;
  variant_label?: string;
  variant_key?: string;
  variant_params_json?: Record<string, unknown>;
  notes?: string;
}

export interface ExperimentVariantSummary {
  experiment_run_id: string;
  run_id: string;
  run_name: string;
  run_type: string;
  variant_label: string | null;
  variant_key: string | null;
  variant_params_json: Record<string, unknown> | null;
  evidence_score: number;
  trust_score: number | null;
  dataset_health: number | null;
  signal_quality: number | null;
  replay_completeness: number | null;
  variant_status: string;
  review_reasons: string[];
}

export interface ExperimentMetricComparison {
  metric_key: string;
  available_count: number;
  min_value: number | null;
  max_value: number | null;
  mean_value: number | null;
  spread: number | null;
  values_by_run_id: Record<string, number>;
}

export interface ExperimentRankingItem {
  rank: number;
  run_id: string;
  variant_label: string | null;
  score: number | null;
  reason: string;
}

export interface StrategyExperimentAnalysis {
  id: string;
  experiment_id: string;
  analysis_label: string | null;
  overall_status: string;
  variant_count: number;
  run_count: number;
  best_evidenced_run_id: string | null;
  weakest_evidence_run_id: string | null;
  deterministic_summary: string | null;
  result_json: unknown;
  created_at: string;
}

export interface StrategyExperimentAnalysisListResponse {
  items: StrategyExperimentAnalysis[];
  total: number;
}

// M60 - Parameter Sweep Reliability Analysis
export interface ParameterSweepAnalysisRequest {
  parameter_key?: string;
  analysis_label?: string;
  persist?: boolean;
}

export interface DetectedParameter {
  parameter_key: string;
  value_count: number;
  numeric: boolean;
  unique_values: unknown[];
  coverage_rate: number;
  examples: unknown[];
}

export interface ParameterSweepVariant {
  experiment_run_id: string;
  run_id: string;
  run_name: string;
  run_type: string;
  variant_label: string | null;
  parameter_key: string | null;
  parameter_value: string | null;
  parameter_value_numeric: number | null;
  sharpe: number | null;
  annual_return: number | null;
  max_drawdown: number | null;
  volatility: number | null;
  turnover: number | null;
  hit_rate: number | null;
  trade_count: number | null;
  dataset_health: number | null;
  signal_quality: number | null;
  backtest_trust: number | null;
  evidence_score: number;
  variant_status: string;
  review_reasons: string[];
  suggested_checks: string[];
}

export interface ParameterSweepMetricComparison {
  metric_key: string;
  available_count: number;
  min_value: number | null;
  max_value: number | null;
  mean_value: number | null;
  range_value: number | null;
  values_by_run_id: Record<string, unknown>;
}

export interface ParameterSweepRegion {
  region_key: string;
  label: string;
  parameter_min: number | null;
  parameter_max: number | null;
  variant_count: number;
  run_ids: string[];
  status: string;
  evidence_score_avg: number | null;
  backtest_trust_avg: number | null;
  metric_stability_score: number | null;
  reason: string;
  suggested_check: string | null;
}

export interface ParameterSweepFragilitySignals {
  fragile_variant_count: number;
  review_variant_count: number;
  under_instrumented_variant_count: number;
  narrow_peak_detected: boolean;
  evidence_degradation_detected: boolean;
  trust_degradation_detected: boolean;
  metric_instability_detected: boolean;
}

export interface ParameterSweepRankingItem {
  rank: number;
  run_id: string;
  variant_label: string | null;
  parameter_value: string | null;
  score: number | null;
  reason: string;
}

export interface ParameterSweepAnalysisResponse {
  experiment_id: string;
  strategy_id: string;
  parameter_key: string | null;
  generated_at: string;
  sweep_status: string;
  sweep_reliability_score: number | null;
  detected_parameters: DetectedParameter[];
  variant_summaries: ParameterSweepVariant[];
  metric_comparisons: ParameterSweepMetricComparison[];
  regions: ParameterSweepRegion[];
  fragility_signals: ParameterSweepFragilitySignals;
  rankings: ParameterSweepRankingItem[];
  suggested_checks: string[];
  deterministic_summary: string;
  analysis_id: string | null;
}

// M61 - Strategy Robustness Score
export type RobustnessStatus = "robust" | "stable" | "watch" | "review" | "fragile" | "insufficient_evidence";
export type RobustnessVerdict = "robust_under_logged_variation" | "stable_with_watch_items" | "requires_review" | "fragile_under_variation" | "insufficient_evidence";

export interface RobustnessDimensionScorecard {
  dimension_key: string;
  title: string;
  score: number | null;
  status: string;
  evidence_count: number;
  fragility_signals: string[];
  positive_evidence: string[];
  review_items: string[];
  suggested_actions: string[];
  source_refs_json: Record<string, unknown> | null;
}

export interface RobustnessFragilitySignal {
  signal_key: string;
  title: string;
  severity: "low" | "medium" | "high" | "critical";
  evidence_summary: string;
  suggested_action: string;
  source_dimension: string;
}

export interface StrategyRobustnessResponse {
  strategy_id: string;
  strategy_name: string;
  generated_at: string;
  robustness_score: number | null;
  robustness_status: RobustnessStatus;
  robustness_verdict: RobustnessVerdict;
  verdict_label: string;
  deterministic_summary: string;
  dimension_scorecards: RobustnessDimensionScorecard[];
  fragility_signals: RobustnessFragilitySignal[];
  top_review_drivers: string[];
  suggested_actions: string[];
  evidence_gaps: string[];
  robustness_vs_readiness_note: string;
}

// M62 - Progression Freeze Recommendations
export type ProgressionFreezeRecommendation = "continue_progression" | "monitor_before_progression" | "pause_progression" | "freeze_progression" | "insufficient_evidence";

export interface ProgressionFreezeReason {
  reason_key: string;
  title: string;
  category: string;
  severity: "low" | "medium" | "high" | "critical";
  status: "blocker" | "review" | "watch" | "missing";
  evidence_summary: string;
  source_label: string;
  source_id: string | null;
  suggested_resolution: string;
  required_to_unfreeze: boolean;
}

export interface ProgressionUnfreezeRequirement {
  requirement_key: string;
  title: string;
  priority: "low" | "medium" | "high" | "critical";
  required: boolean;
  current_status: string;
  target_status: string;
  suggested_action: string;
  endpoint_hint: string | null;
}

export interface ProgressionSubsystemStatus {
  subsystem: string;
  status: string;
  summary: string | null;
  score: number | null;
}

export interface ProgressionStageContext {
  current_stage: string;
  target_stage: string;
  next_recommended_stage: string;
  stage_path: string[];
}

export interface StrategyProgressionFreezeResponse {
  strategy_id: string;
  strategy_name: string;
  generated_at: string;
  target_stage: string;
  current_stage: string;
  recommendation: ProgressionFreezeRecommendation;
  recommendation_label: string;
  freeze_risk_score: number;
  deterministic_summary: string;
  freeze_reasons: ProgressionFreezeReason[];
  unfreeze_requirements: ProgressionUnfreezeRequirement[];
  blocking_reason_count: number;
  review_reason_count: number;
  watch_reason_count: number;
  missing_evidence_count: number;
  subsystem_statuses: ProgressionSubsystemStatus[];
  stage_context: ProgressionStageContext;
  note: string;
}

// M63 - Quant Research Audit Trail
export type ResearchAuditCategory = "evidence" | "run" | "data" | "signal" | "universe" | "config" | "backtest" | "reliability" | "readiness" | "robustness" | "promotion" | "freeze" | "regression" | "policy" | "sla" | "review_case" | "alert" | "report" | "experiment" | "replay" | "ingestion" | "system" | "other";
export type ResearchAuditImportance = "low" | "medium" | "high" | "critical";

export interface ResearchAuditLinkedObject {
  object_type: string;
  object_id: string;
  label: string;
  route_hint: string | null;
}

export interface ResearchAuditStatusTransition {
  previous_status: string | null;
  new_status: string | null;
  status_type: string | null;
  transition_label: string | null;
}

export interface ResearchAuditDownstreamContext {
  impacted_artifact_count: number;
  recommended_rechecks: string[];
  affected_readiness: boolean;
  affected_promotion_gates: boolean;
  affected_review_cases: boolean;
  affected_freeze_recommendation: boolean;
}

export interface ResearchAuditEvent {
  event_id: string;
  event_time: string;
  event_type: string;
  title: string;
  description: string | null;
  severity: string;
  source_type: string | null;
  source_id: string | null;
  category: string;
  importance: ResearchAuditImportance;
  research_phase: string;
  linked_object: ResearchAuditLinkedObject | null;
  downstream_context: ResearchAuditDownstreamContext | null;
  status_transition: ResearchAuditStatusTransition | null;
  evidence_summary_json: Record<string, unknown>;
  suggested_action: string | null;
}

export interface ResearchAuditTrailResponse {
  strategy_id: string;
  strategy_name: string;
  generated_at: string;
  total_events: number;
  returned_count: number;
  category_counts: Record<string, number>;
  importance_counts: Record<string, number>;
  phase_counts: Record<string, number>;
  high_importance_count: number;
  latest_event_at: string | null;
  latest_governance_event_at: string | null;
  latest_evidence_event_at: string | null;
  unresolved_review_case_count: number;
  open_alert_count: number;
  latest_freeze_recommendation: string | null;
  deterministic_summary: string;
  suggested_checks: string[];
  events: ResearchAuditEvent[];
}

// M64 - Strategy Reliability Command Center (Final Advanced Feature)
export type CommandCenterStatus = "clear" | "monitor" | "review" | "blocked" | "insufficient_evidence";

export interface CommandCenterSubsystemStatus {
  subsystem_key: string;
  title: string;
  status: "healthy" | "watch" | "review" | "blocked" | "missing" | "error";
  score: number | null;
  severity: string;
  summary: string | null;
  top_issue: string | null;
  suggested_action: string | null;
  route_hint: string | null;
  source_json: Record<string, unknown> | null;
}

export interface CommandCenterBlocker {
  blocker_key: string;
  title: string;
  category: string;
  severity: string;
  evidence_summary: string;
  source_subsystem: string;
  required_before_progression: boolean;
  suggested_resolution: string;
}

export interface CommandCenterAction {
  action_key: string;
  title: string;
  priority: "low" | "medium" | "high" | "critical";
  action_type: string;
  reason: string;
  endpoint_hint: string | null;
  route_hint: string | null;
  depends_on: string[];
}

export interface CommandCenterGovernanceSummary {
  open_review_case_count: number;
  acknowledged_review_case_count: number;
  high_critical_alert_count: number;
  latest_regression_status: string | null;
  latest_policy_status: string | null;
  latest_sla_status: string | null;
  latest_freeze_recommendation: string | null;
  promotion_gate_paper_verdict: string | null;
  promotion_gate_production_verdict: string | null;
}

export interface CommandCenterEvidenceSummary {
  freshness_status: string | null;
  coverage_score: number | null;
  missing_evidence_count: number;
  stale_evidence_count: number;
  graph_status: string | null;
  replay_pack_recommended: boolean;
  latest_run_id: string | null;
  latest_run_label: string | null;
}

export interface CommandCenterWorkflowSummary {
  current_stage: string;
  next_recommended_stage: string;
  stage_path: string[];
  active_experiment_count: number;
  latest_experiment_analysis_status: string | null;
  latest_sweep_status: string | null;
  latest_audit_event_at: string | null;
}

export interface StrategyReliabilityCommandCenterResponse {
  strategy_id: string;
  strategy_name: string;
  generated_at: string;
  command_status: CommandCenterStatus;
  command_score: number | null;
  deterministic_summary: string;
  subsystem_statuses: CommandCenterSubsystemStatus[];
  top_blockers: CommandCenterBlocker[];
  action_queue: CommandCenterAction[];
  governance_summary: CommandCenterGovernanceSummary;
  evidence_summary: CommandCenterEvidenceSummary;
  workflow_summary: CommandCenterWorkflowSummary;
  note: string;
}

// M65A - Strategy Reliability Snapshot Cache
export type ReliabilitySnapshotStatus = "fresh" | "stale" | "error";

export interface StrategyReliabilitySnapshot {
  id: string;
  strategy_id: string;
  snapshot_status: ReliabilitySnapshotStatus;
  command_status: string | null;
  command_score: number | null;
  readiness_verdict: string | null;
  readiness_score: number | null;
  robustness_verdict: string | null;
  robustness_score: number | null;
  freeze_recommendation: string | null;
  freeze_risk_score: number | null;
  freshness_status: string | null;
  freshness_score: number | null;
  drift_status: string | null;
  drift_score: number | null;
  shadow_status: string | null;
  shadow_score: number | null;
  open_review_case_count: number;
  high_critical_alert_count: number;
  latest_regression_status: string | null;
  latest_config_policy_status: string | null;
  latest_sla_status: string | null;
  top_blockers_json: unknown[] | null;
  action_queue_json: unknown[] | null;
  subsystem_statuses_json: unknown[] | null;
  deterministic_summary: string | null;
  source_hash: string | null;
  generated_at: string;
  stale_after: string;
  created_at: string;
  is_stale: boolean;
  stale_reasons: string[];
}

export interface StrategyReliabilitySnapshotListResponse {
  items: StrategyReliabilitySnapshot[];
  total: number;
}

// M65 - Deployment Readiness
export type DeploymentReadinessStatus = "local_demo_ready" | "deployment_prep_ready" | "needs_review" | "blocked";

export interface DeploymentReadinessCheck {
  check_key: string;
  title: string;
  category: string;
  status: "pass" | "warning" | "fail" | "manual" | "not_applicable";
  severity: "info" | "low" | "medium" | "high" | "critical";
  observed_value: string | null;
  expected_value: string | null;
  explanation: string;
  suggested_action: string | null;
}

export interface DeploymentReadinessCategory {
  category_key: string;
  title: string;
  status: "pass" | "warning" | "fail" | "manual";
  pass_count: number;
  warning_count: number;
  fail_count: number;
  manual_count: number;
  checks: DeploymentReadinessCheck[];
}

export interface DeploymentReadinessResponse {
  generated_at: string;
  overall_status: DeploymentReadinessStatus;
  readiness_score: number;
  pass_count: number;
  warning_count: number;
  fail_count: number;
  manual_count: number;
  blocker_count: number;
  categories: DeploymentReadinessCategory[];
  blockers: string[];
  warnings: string[];
  suggested_next_steps: string[];
  deterministic_summary: string;
}

// M67 - Workspace Settings + Members Foundation
export interface WorkspaceProjectSummary {
  project_id: string;
  name: string;
  strategy_count: number;
  created_at: string;
}

export interface WorkspaceSummary {
  workspace_id: string | null;
  workspace_name: string;
  display_name: string | null;
  description: string | null;
  website: string | null;
  project_count: number;
  strategy_count: number;
  member_count: number;
  active_member_count: number;
  api_key_count: number;
  created_at: string | null;
  updated_at: string | null;
  projects: WorkspaceProjectSummary[];
  readiness_note: string;
}

export interface WorkspaceSettingsUpdate {
  display_name?: string;
  description?: string;
  website?: string;
}

export interface WorkspaceMember {
  id: string;
  organization_id: string;
  display_name: string;
  email: string;
  role: "owner" | "admin" | "member" | "viewer";
  status: "active" | "invited" | "disabled";
  title: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceMemberCreate {
  display_name: string;
  email: string;
  role?: string;
  status?: string;
  title?: string;
  notes?: string;
}

export interface WorkspaceMemberUpdate {
  display_name?: string;
  email?: string;
  role?: string;
  status?: string;
  title?: string;
  notes?: string;
}

export interface WorkspaceMemberListResponse {
  items: WorkspaceMember[];
  total: number;
}

// M68 - Auth + User Accounts
export interface User {
  id: string;
  email: string;
  display_name: string;
  status: string;
  is_superuser: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
  /** M84: whether the user's email has been verified. */
  email_verified: boolean;
  /** M84: ISO timestamp of verification, null if not yet verified. */
  email_verified_at: string | null;
}

export interface UserRegisterRequest {
  email: string;
  display_name: string;
  password: string;
}

export interface UserLoginRequest {
  email: string;
  password: string;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface CurrentUserWorkspaceMembership {
  member_id: string;
  organization_id: string;
  workspace_name: string;
  role: string;
  status: string;
  linked: boolean;
}

// M69 - RBAC permission set resolved from the user's primary membership.
export interface PermissionSet {
  can_read_research: boolean;
  can_write_research: boolean;
  can_manage_workspace: boolean;
  can_manage_members: boolean;
  can_manage_api_keys: boolean;
  can_seed_demo: boolean;
}

export interface CurrentUserResponse {
  user: User;
  workspace_memberships: CurrentUserWorkspaceMembership[];
  // M69 — role + permissions for permission-aware UI.
  role: string | null;
  organization_id: string | null;
  permissions: PermissionSet;
}

export interface AuthStatusResponse {
  auth_enabled: boolean;
  has_users: boolean;
  registration_enabled: boolean;
}

// ---------------------------------------------------------------------------
// M74: Strategy Action Queue
// ---------------------------------------------------------------------------

export type ActionSeverity = "critical" | "high" | "medium" | "low" | "info";
export type ActionStatus = "pending" | "done" | "blocked" | "optional";

export interface ActionItem {
  id: string;
  strategy_id: string;
  title: string;
  description: string;
  why_it_matters: string;
  severity: ActionSeverity;
  priority_rank: number;
  status: ActionStatus;
  category: string;
  source: string;
  target_tab: string | null;
  target_panel_label: string | null;
  action_label: string;
  action_type: string;
  related_object_id: string | null;
  related_object_type: string | null;
  deterministic_reason: string;
  created_from: string[];
}

export interface ActionQueueResponse {
  strategy_id: string;
  strategy_name: string;
  generated_at: string;
  items: ActionItem[];
  total_action_count: number;
  completed_count: number;
  pending_count: number;
  blocked_count: number;
  optional_count: number;
  deterministic_summary: string;
  disclaimer: string;
}

// ---------------------------------------------------------------------------
// M75: Evidence Repair + Strategy Management
// ---------------------------------------------------------------------------

export interface RepairOptionItem {
  id: string;
  label: string;
  created_at: string | null;
  quality_score: number | null;
  row_count: number | null;
  symbol_count: number | null;
  linked_run_count: number | null;
  recommended: boolean;
  detail: string | null;
}

export interface RunMissingLinks {
  run_id: string;
  run_name: string;
  run_type: string;
  created_at: string | null;
  missing: string[];
  dataset_snapshot_id: string | null;
  signal_snapshot_id: string | null;
  universe_snapshot_id: string | null;
  strategy_version_id: string | null;
}

export interface RepairOptionsResponse {
  strategy_id: string;
  strategy_name: string;
  dataset_snapshots: RepairOptionItem[];
  signal_snapshots: RepairOptionItem[];
  universe_snapshots: RepairOptionItem[];
  strategy_versions: RepairOptionItem[];
  runs_missing_links: RunMissingLinks[];
}

export interface RunLinkUpdateRequest {
  dataset_snapshot_id?: string | null;
  signal_snapshot_id?: string | null;
  universe_snapshot_id?: string | null;
  strategy_version_id?: string | null;
}

export interface RunLinkSummary {
  run_id: string;
  strategy_id: string;
  run_name: string;
  run_type: string;
  status: string;
  dataset_snapshot_id: string | null;
  signal_snapshot_id: string | null;
  universe_snapshot_id: string | null;
  strategy_version_id: string | null;
  dataset_snapshot_label: string | null;
  signal_snapshot_label: string | null;
  universe_snapshot_label: string | null;
  strategy_version_label: string | null;
  linked_fields: string[];
  updated_at: string | null;
  message: string;
}

export interface StrategyUpdateRequest {
  name?: string | null;
  description?: string | null;
  status?: string | null;
  asset_class?: string | null;
}

export interface StrategyManagementSummary {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  asset_class: string;
  status: string;
  archived: boolean;
  message: string;
}

// ---------------------------------------------------------------------------
// M76: Strategy Lifecycle
// ---------------------------------------------------------------------------

export type LifecycleStageState = "completed" | "current" | "blocked" | "upcoming";

export interface LifecycleStage {
  key: string;
  label: string;
  index: number;
  state: LifecycleStageState;
}

export interface LifecycleBlocker {
  reason: string;
  detail: string;
  severity: string;
  action_type: string;
  action_label: string;
  target_tab: string | null;
  related_run_id: string | null;
}

export interface StrategyLifecycleResponse {
  strategy_id: string;
  strategy_name: string;
  generated_at: string;
  stages: LifecycleStage[];
  current_stage: string;
  current_stage_label: string;
  next_stage: string | null;
  next_stage_label: string | null;
  blocked: boolean;
  blocked_stage: string | null;
  blocked_stage_label: string | null;
  blockers: LifecycleBlocker[];
  suggested_actions: string[];
  deterministic_summary: string;
  disclaimer: string;
}

// ---------------------------------------------------------------------------
// M86: Portfolio Reliability
// ---------------------------------------------------------------------------

export interface PortfolioReliabilityTopBlocker {
  title: string;
  severity: string;
  category: string;
  recommended_action: string;
  target_tab: string;
}

export interface PortfolioReliabilityRow {
  strategy_id: string;
  name: string;
  project_name: string;
  asset_class: string;
  status: string;
  reliability_score: number | null;
  reliability_status: string;
  health_classification: "healthy" | "review" | "blocked";
  health_status: string;
  promotion_stage: string;
  open_alert_count: number;
  high_critical_alert_count: number;
  top_blocker: PortfolioReliabilityTopBlocker | null;
  stale_evidence_count: number;
  missing_report: boolean;
  recent_score_change: {
    delta: number;
    latest: number;
    previous: number;
    direction: string;
  } | null;
  latest_run_at: string | null;
  days_since_latest_run: number | null;
  owner_name: string | null;
  regression_failed_count: number;
}

export interface PortfolioReliabilitySummary {
  total_strategies: number;
  healthy_count: number;
  review_count: number;
  blocked_count: number;
  average_reliability: number | null;
  strategies_with_stale_evidence: number;
  strategies_missing_reports: number;
  open_high_critical_alerts: number;
  ready_for_paper_candidate: number;
  ready_for_production_candidate: number;
}

export interface PortfolioWorstBlocker {
  strategy_id: string;
  strategy_name: string;
  blocker_title: string;
  severity: string;
  recommended_action: string;
  category: string;
  target_tab: string;
}

export interface PortfolioStaleEvidence {
  strategy_id: string;
  strategy_name: string;
  stale_count: number;
  missing_count: number;
  aging_count: number;
}

export interface PortfolioMissingReport {
  strategy_id: string;
  strategy_name: string;
  latest_run_at: string | null;
}

export interface PortfolioRecentScoreChange {
  strategy_id: string;
  strategy_name: string;
  delta: number;
  latest: number;
  previous: number;
  direction: string;
}

export interface PortfolioReliabilityResponse {
  generated_at: string;
  summary: PortfolioReliabilitySummary;
  strategies: PortfolioReliabilityRow[];
  worst_blockers: PortfolioWorstBlocker[];
  stale_evidence: PortfolioStaleEvidence[];
  missing_reports: PortfolioMissingReport[];
  recent_score_changes: PortfolioRecentScoreChange[];
  disclaimer: string;
}

export interface PortfolioExportResponse {
  filename: string;
  format: string;
  content: string;
}
