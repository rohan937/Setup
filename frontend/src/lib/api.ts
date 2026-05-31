import type {
  Alert,
  AlertFilters,
  AlertGenerateResponse,
  AlertListResponse,
  AlertUpdateRequest,
  ApiInfo,
  ApiError,
  BacktestAudit,
  BacktestAuditListItem,
  DashboardSummary,
  Dataset,
  DatasetSnapshotComparisonResponse,
  TimelineListResponse,
  TimelineFilters,
  DatasetCreateRequest,
  DatasetDetail,
  DatasetSnapshotCreateRequest,
  DatasetSnapshotDetail,
  DatasetSnapshotRead,
  Project,
  Strategy,
  StrategyDetail,
  StrategyRun,
  StrategyCreateRequest,
  StrategyRunCreateRequest,
  RunComparisonResponse,
} from "@/types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    let err: ApiError = { detail: `HTTP ${res.status}` };
    try {
      err = (await res.json()) as ApiError;
    } catch {
      // leave default
    }
    const message =
      typeof err.detail === "string"
        ? err.detail
        : err.detail.map((e) => e.msg).join(", ");
    throw new Error(message);
  }
  return (await res.json()) as T;
}

export async function fetchApiInfo(): Promise<ApiInfo> {
  return request<ApiInfo>("/api");
}

export async function getProjects(): Promise<Project[]> {
  return request<Project[]>("/api/projects");
}

export async function getStrategies(): Promise<Strategy[]> {
  return request<Strategy[]>("/api/strategies");
}

export async function getStrategy(id: string): Promise<StrategyDetail> {
  return request<StrategyDetail>(`/api/strategies/${id}`);
}

export async function createStrategy(
  data: StrategyCreateRequest,
): Promise<Strategy> {
  return request<Strategy>("/api/strategies", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function createStrategyRun(
  strategyId: string,
  data: StrategyRunCreateRequest,
): Promise<StrategyRun> {
  return request<StrategyRun>(`/api/strategies/${strategyId}/runs`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function compareStrategyRuns(
  strategyId: string,
  runAId: string,
  runBId: string,
): Promise<RunComparisonResponse> {
  return request<RunComparisonResponse>(
    `/api/strategies/${strategyId}/runs/compare?run_a_id=${runAId}&run_b_id=${runBId}`,
  );
}

// ---------------------------------------------------------------------------
// Dataset endpoints (M6)
// ---------------------------------------------------------------------------

export async function getDatasets(): Promise<Dataset[]> {
  return request<Dataset[]>("/api/datasets");
}

export async function getDataset(datasetId: string): Promise<DatasetDetail> {
  return request<DatasetDetail>(`/api/datasets/${datasetId}`);
}

export async function createDataset(data: DatasetCreateRequest): Promise<Dataset> {
  return request<Dataset>("/api/datasets", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function createDatasetSnapshot(
  datasetId: string,
  data: DatasetSnapshotCreateRequest,
): Promise<DatasetSnapshotDetail> {
  return request<DatasetSnapshotDetail>(`/api/datasets/${datasetId}/snapshots`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getDatasetSnapshots(
  datasetId: string,
): Promise<DatasetSnapshotRead[]> {
  return request<DatasetSnapshotRead[]>(`/api/datasets/${datasetId}/snapshots`);
}

export async function getDatasetSnapshot(
  snapshotId: string,
): Promise<DatasetSnapshotDetail> {
  return request<DatasetSnapshotDetail>(`/api/dataset-snapshots/${snapshotId}`);
}

export async function compareDatasetSnapshots(
  datasetId: string,
  snapshotAId: string,
  snapshotBId: string,
): Promise<DatasetSnapshotComparisonResponse> {
  return request<DatasetSnapshotComparisonResponse>(
    `/api/datasets/${datasetId}/snapshots/compare?snapshot_a_id=${snapshotAId}&snapshot_b_id=${snapshotBId}`,
  );
}

// ---------------------------------------------------------------------------
// Backtest Reality Check endpoints (M8)
// ---------------------------------------------------------------------------

export async function runBacktestAudit(runId: string): Promise<BacktestAudit> {
  return request<BacktestAudit>(`/api/strategy-runs/${runId}/backtest-audit`, {
    method: "POST",
  });
}

export async function getBacktestAudit(runId: string): Promise<BacktestAudit> {
  return request<BacktestAudit>(`/api/strategy-runs/${runId}/backtest-audit`);
}

export async function getBacktestAudits(): Promise<BacktestAuditListItem[]> {
  return request<BacktestAuditListItem[]>("/api/backtests/audits");
}

// ---------------------------------------------------------------------------
// Dashboard summary (M9)
// ---------------------------------------------------------------------------

export async function getDashboardSummary(): Promise<DashboardSummary> {
  return request<DashboardSummary>("/api/dashboard/summary");
}

// ---------------------------------------------------------------------------
// Audit timeline (M10)
// ---------------------------------------------------------------------------

function _buildTimelineQS(filters: TimelineFilters): string {
  const params = new URLSearchParams();
  if (filters.project_id) params.set("project_id", filters.project_id);
  if (filters.strategy_id) params.set("strategy_id", filters.strategy_id);
  if (filters.event_type) params.set("event_type", filters.event_type);
  if (filters.severity) params.set("severity", filters.severity);
  if (filters.source_type) params.set("source_type", filters.source_type);
  if (filters.limit != null) params.set("limit", String(filters.limit));
  if (filters.offset != null) params.set("offset", String(filters.offset));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export async function getTimeline(
  filters: TimelineFilters = {},
): Promise<TimelineListResponse> {
  return request<TimelineListResponse>(`/api/timeline${_buildTimelineQS(filters)}`);
}

export async function getStrategyTimeline(
  strategyId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<TimelineListResponse> {
  const qs = _buildTimelineQS(params);
  return request<TimelineListResponse>(
    `/api/strategies/${strategyId}/timeline${qs}`,
  );
}

// ---------------------------------------------------------------------------
// Alerts Engine (M11)
// ---------------------------------------------------------------------------

function _buildAlertQS(filters: AlertFilters): string {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.severity) params.set("severity", filters.severity);
  if (filters.rule_type) params.set("rule_type", filters.rule_type);
  if (filters.strategy_id) params.set("strategy_id", filters.strategy_id);
  if (filters.limit != null) params.set("limit", String(filters.limit));
  if (filters.offset != null) params.set("offset", String(filters.offset));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export async function generateAlerts(): Promise<AlertGenerateResponse> {
  return request<AlertGenerateResponse>("/api/alerts/generate", { method: "POST" });
}

export async function getAlerts(
  filters: AlertFilters = {},
): Promise<AlertListResponse> {
  return request<AlertListResponse>(`/api/alerts${_buildAlertQS(filters)}`);
}

export async function getAlert(alertId: string): Promise<Alert> {
  return request<Alert>(`/api/alerts/${alertId}`);
}

export async function updateAlert(
  alertId: string,
  data: AlertUpdateRequest,
): Promise<Alert> {
  return request<Alert>(`/api/alerts/${alertId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}
