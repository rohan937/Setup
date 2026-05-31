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
  issues: BacktestIssue[];
  created_at: string;
  updated_at: string;
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
  created_at: string;
  updated_at: string;
}
