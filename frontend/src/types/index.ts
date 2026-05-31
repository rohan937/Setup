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

export interface StrategyRun {
  id: string;
  strategy_id: string;
  strategy_version_id: string | null;
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

export interface ApiError {
  detail: string | { msg: string; type: string }[];
}
