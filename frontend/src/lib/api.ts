import type {
  ApiInfo,
  ApiError,
  BacktestAudit,
  BacktestAuditListItem,
  DashboardSummary,
  Dataset,
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
