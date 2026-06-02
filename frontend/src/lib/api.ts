import type {
  Alert,
  AlertFilters,
  EvidenceBundleRequest,
  EvidenceBundleResponse,
  EvidenceCoverageMatrixResponse,
  EvidenceCoverageParams,
  AlertGenerateResponse,
  AlertListResponse,
  AlertUpdateRequest,
  ApiInfo,
  ApiError,
  BacktestAudit,
  BacktestAuditListItem,
  ConfigComparisonResponse,
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
  ReliabilityScoreComparisonResponse,
  ReliabilityScoreTrendResponse,
  ReportDetail,
  ReportFilters,
  ReportListResponse,
  SignalComparisonResponse,
  SignalSnapshotCreateRequest,
  SignalSnapshotDetail,
  SignalSnapshotRead,
  Strategy,
  StrategyComparisonRequest,
  StrategyComparisonResponse,
  StrategyConfigSnapshotCreateRequest,
  StrategyConfigSnapshotDetail,
  StrategyConfigSnapshotRead,
  StrategyDetail,
  StrategyReliabilityScore,
  StrategyReliabilityScoreHistoryResponse,
  StrategyReliabilityScoreListResponse,
  StrategyRun,
  StrategyCreateRequest,
  StrategyRunCreateRequest,
  StrategyVersion,
  StrategyVersionCreateRequest,
  RunComparisonResponse,
  UniverseComparisonResponse,
  UniverseSnapshotCreateRequest,
  UniverseSnapshotDetail,
  UniverseSnapshotRead,
  ApiKeyCreateRequest,
  ApiKeyCreateResponse,
  ApiKeyListResponse,
  ApiKeyRevokeResponse,
  StrategyHealth,
  StrategyHealthListResponse,
  ProjectHealth,
  ProjectHealthListResponse,
  StrategyRunHistoryResponse,
  StrategyTimelineDrilldownResponse,
  StrategyEvidenceTrendsResponse,
  StrategyExportResponse,
  PortfolioOverview,
  MultiRunComparisonRequest,
  MultiRunComparisonResponse,
  StrategyVersionLineageResponse,
  DatasetQualityDrilldownResponse,
  SignalQualityDrilldownResponse,
  UniverseCoverageAnalysisResponse,
  ConfigSnapshotComparisonV2Response,
  StrategyAssumptionHealthResponse,
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

// ---------------------------------------------------------------------------
// Reliability Reports (M14)
// ---------------------------------------------------------------------------

function _buildReportQS(filters: ReportFilters): string {
  const params = new URLSearchParams();
  if (filters.report_type) params.set("report_type", filters.report_type);
  if (filters.strategy_id) params.set("strategy_id", filters.strategy_id);
  if (filters.source_type) params.set("source_type", filters.source_type);
  if (filters.limit != null) params.set("limit", String(filters.limit));
  if (filters.offset != null) params.set("offset", String(filters.offset));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export async function generateStrategyReport(
  strategyId: string,
): Promise<ReportDetail> {
  return request<ReportDetail>(`/api/reports/strategy/${strategyId}`, {
    method: "POST",
  });
}

export async function generateBacktestAuditReport(
  auditId: string,
): Promise<ReportDetail> {
  return request<ReportDetail>(`/api/reports/backtest-audit/${auditId}`, {
    method: "POST",
  });
}

export async function generateDatasetSnapshotReport(
  snapshotId: string,
): Promise<ReportDetail> {
  return request<ReportDetail>(`/api/reports/dataset-snapshot/${snapshotId}`, {
    method: "POST",
  });
}

export async function getReports(
  filters: ReportFilters = {},
): Promise<ReportListResponse> {
  return request<ReportListResponse>(`/api/reports${_buildReportQS(filters)}`);
}

export async function getReport(reportId: string): Promise<ReportDetail> {
  return request<ReportDetail>(`/api/reports/${reportId}`);
}

// ---------------------------------------------------------------------------
// Strategy versions (M15)
// ---------------------------------------------------------------------------

export async function createStrategyVersion(
  strategyId: string,
  data: StrategyVersionCreateRequest,
): Promise<StrategyVersion> {
  return request<StrategyVersion>(`/api/strategies/${strategyId}/versions`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getStrategyVersions(
  strategyId: string,
): Promise<StrategyVersion[]> {
  return request<StrategyVersion[]>(`/api/strategies/${strategyId}/versions`);
}

// ---------------------------------------------------------------------------
// Config snapshots (M15)
// ---------------------------------------------------------------------------

export async function createConfigSnapshot(
  strategyId: string,
  data: StrategyConfigSnapshotCreateRequest,
): Promise<StrategyConfigSnapshotRead> {
  return request<StrategyConfigSnapshotRead>(
    `/api/strategies/${strategyId}/config-snapshots`,
    { method: "POST", body: JSON.stringify(data) },
  );
}

export async function getConfigSnapshots(
  strategyId: string,
  versionId?: string,
): Promise<StrategyConfigSnapshotRead[]> {
  const qs = versionId ? `?version_id=${versionId}` : "";
  return request<StrategyConfigSnapshotRead[]>(
    `/api/strategies/${strategyId}/config-snapshots${qs}`,
  );
}

export async function compareConfigSnapshots(
  strategyId: string,
  snapshotAId: string,
  snapshotBId: string,
): Promise<ConfigComparisonResponse> {
  return request<ConfigComparisonResponse>(
    `/api/strategies/${strategyId}/config-snapshots/compare?snapshot_a_id=${snapshotAId}&snapshot_b_id=${snapshotBId}`,
  );
}

export async function getConfigSnapshot(
  snapshotId: string,
): Promise<StrategyConfigSnapshotDetail> {
  return request<StrategyConfigSnapshotDetail>(`/api/config-snapshots/${snapshotId}`);
}

// ---------------------------------------------------------------------------
// Universe snapshots (M16)
// ---------------------------------------------------------------------------

export async function createUniverseSnapshot(
  strategyId: string,
  data: UniverseSnapshotCreateRequest,
): Promise<UniverseSnapshotRead> {
  return request<UniverseSnapshotRead>(
    `/api/strategies/${strategyId}/universe-snapshots`,
    { method: "POST", body: JSON.stringify(data) },
  );
}

export async function getUniverseSnapshots(
  strategyId: string,
  versionId?: string,
): Promise<UniverseSnapshotRead[]> {
  const qs = versionId ? `?version_id=${versionId}` : "";
  return request<UniverseSnapshotRead[]>(
    `/api/strategies/${strategyId}/universe-snapshots${qs}`,
  );
}

export async function getUniverseSnapshot(
  snapshotId: string,
): Promise<UniverseSnapshotDetail> {
  return request<UniverseSnapshotDetail>(`/api/universe-snapshots/${snapshotId}`);
}

export async function compareUniverseSnapshots(
  strategyId: string,
  snapshotAId: string,
  snapshotBId: string,
): Promise<UniverseComparisonResponse> {
  return request<UniverseComparisonResponse>(
    `/api/strategies/${strategyId}/universe-snapshots/compare?snapshot_a_id=${snapshotAId}&snapshot_b_id=${snapshotBId}`,
  );
}

// ---------------------------------------------------------------------------
// Signal snapshots (M17)
// ---------------------------------------------------------------------------

export async function createSignalSnapshot(
  strategyId: string,
  data: SignalSnapshotCreateRequest,
): Promise<SignalSnapshotRead> {
  return request<SignalSnapshotRead>(
    `/api/strategies/${strategyId}/signal-snapshots`,
    { method: "POST", body: JSON.stringify(data) },
  );
}

export async function getSignalSnapshots(
  strategyId: string,
  versionId?: string,
): Promise<SignalSnapshotRead[]> {
  const qs = versionId ? `?version_id=${versionId}` : "";
  return request<SignalSnapshotRead[]>(
    `/api/strategies/${strategyId}/signal-snapshots${qs}`,
  );
}

export async function getSignalSnapshot(
  snapshotId: string,
): Promise<SignalSnapshotDetail> {
  return request<SignalSnapshotDetail>(`/api/signal-snapshots/${snapshotId}`);
}

export async function compareSignalSnapshots(
  strategyId: string,
  snapshotAId: string,
  snapshotBId: string,
): Promise<SignalComparisonResponse> {
  return request<SignalComparisonResponse>(
    `/api/strategies/${strategyId}/signal-snapshots/compare?snapshot_a_id=${snapshotAId}&snapshot_b_id=${snapshotBId}`,
  );
}

// ---------------------------------------------------------------------------
// Strategy Reliability Score (M18)
// ---------------------------------------------------------------------------

/** Compute (or recompute) the reliability score for a strategy. */
export async function computeStrategyReliabilityScore(
  strategyId: string,
): Promise<StrategyReliabilityScore> {
  return request<StrategyReliabilityScore>(
    `/api/strategies/${strategyId}/reliability-score`,
    { method: "POST" },
  );
}

/** Get the latest computed reliability score for a strategy. Throws if none exists. */
export async function getStrategyReliabilityScore(
  strategyId: string,
): Promise<StrategyReliabilityScore> {
  return request<StrategyReliabilityScore>(
    `/api/strategies/${strategyId}/reliability-score`,
  );
}

/** List reliability scores globally, with optional filters. */
export async function getReliabilityScores(params?: {
  status?: string;
  strategy_id?: string;
  limit?: number;
  offset?: number;
}): Promise<StrategyReliabilityScoreListResponse> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.strategy_id) qs.set("strategy_id", params.strategy_id);
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null) qs.set("offset", String(params.offset));
  const q = qs.toString();
  return request<StrategyReliabilityScoreListResponse>(
    `/api/reliability-scores${q ? `?${q}` : ""}`,
  );
}

// ---------------------------------------------------------------------------
// Reliability Score History + Comparison (M19)
// ---------------------------------------------------------------------------

/** Get the reliability score history for a strategy, newest-first. */
export async function getStrategyReliabilityScoreHistory(
  strategyId: string,
  params?: { limit?: number; offset?: number },
): Promise<StrategyReliabilityScoreHistoryResponse> {
  const qs = new URLSearchParams();
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null) qs.set("offset", String(params.offset));
  const q = qs.toString();
  return request<StrategyReliabilityScoreHistoryResponse>(
    `/api/strategies/${strategyId}/reliability-scores${q ? `?${q}` : ""}`,
  );
}

/** Deterministically compare two reliability score rows for a strategy. */
export async function compareStrategyReliabilityScores(
  strategyId: string,
  scoreAId: string,
  scoreBId: string,
): Promise<ReliabilityScoreComparisonResponse> {
  return request<ReliabilityScoreComparisonResponse>(
    `/api/strategies/${strategyId}/reliability-scores/compare?score_a_id=${scoreAId}&score_b_id=${scoreBId}`,
  );
}

/** Get latest-vs-previous trend for a strategy (has_trend=false if < 2 scores). */
export async function getStrategyReliabilityScoreTrend(
  strategyId: string,
): Promise<ReliabilityScoreTrendResponse> {
  return request<ReliabilityScoreTrendResponse>(
    `/api/strategies/${strategyId}/reliability-score/trend`,
  );
}

// ---------------------------------------------------------------------------
// Strategy comparison (M20)
// ---------------------------------------------------------------------------

/** Compare 2–8 strategies side-by-side using logged evidence. Evidence-based only — not investment advice. */
export async function compareStrategies(
  payload: StrategyComparisonRequest,
): Promise<StrategyComparisonResponse> {
  return request<StrategyComparisonResponse>("/api/strategies/compare", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// Evidence Coverage Matrix (M21)
// ---------------------------------------------------------------------------

/** Return the evidence coverage matrix for all strategies matching the given filters. */
export async function getEvidenceCoverage(
  params: EvidenceCoverageParams = {},
): Promise<EvidenceCoverageMatrixResponse> {
  const qs = new URLSearchParams();
  if (params.include_archived != null)
    qs.set("include_archived", String(params.include_archived));
  if (params.asset_class) qs.set("asset_class", params.asset_class);
  if (params.status) qs.set("status", params.status);
  if (params.limit != null) qs.set("limit", String(params.limit));
  if (params.offset != null) qs.set("offset", String(params.offset));
  const q = qs.toString();
  return request<EvidenceCoverageMatrixResponse>(
    `/api/evidence/coverage${q ? `?${q}` : ""}`,
  );
}

// M22: Evidence Bundle Ingestion
export async function ingestEvidenceBundle(
  strategyId: string,
  payload: EvidenceBundleRequest,
): Promise<EvidenceBundleResponse> {
  return request<EvidenceBundleResponse>(
    `/api/strategies/${strategyId}/evidence-bundles`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function getEvidenceBundleExample(
  strategyId: string,
): Promise<EvidenceBundleRequest> {
  return request<EvidenceBundleRequest>(
    `/api/strategies/${strategyId}/evidence-bundles/example`,
  );
}

// ---------------------------------------------------------------------------
// API Keys (M24)
// ---------------------------------------------------------------------------

export async function createApiKey(
  data: ApiKeyCreateRequest,
): Promise<ApiKeyCreateResponse> {
  return request<ApiKeyCreateResponse>("/api/api-keys", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getApiKeys(params?: {
  organization_id?: string;
  project_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<ApiKeyListResponse> {
  const qs = new URLSearchParams();
  if (params?.organization_id) qs.set("organization_id", params.organization_id);
  if (params?.project_id) qs.set("project_id", params.project_id);
  if (params?.status) qs.set("status", params.status);
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null) qs.set("offset", String(params.offset));
  const q = qs.toString();
  return request<ApiKeyListResponse>(`/api/api-keys${q ? `?${q}` : ""}`);
}

export async function revokeApiKey(apiKeyId: string): Promise<ApiKeyRevokeResponse> {
  return request<ApiKeyRevokeResponse>(`/api/api-keys/${apiKeyId}/revoke`, {
    method: "PATCH",
  });
}

// ---------------------------------------------------------------------------
// M27: Strategy Health
// ---------------------------------------------------------------------------

export async function getStrategyHealth(strategyId: string): Promise<StrategyHealth> {
  return request<StrategyHealth>(`/api/strategies/${strategyId}/health`);
}

export async function getStrategiesHealth(params?: {
  status?: string;
  asset_class?: string;
  limit?: number;
  offset?: number;
}): Promise<StrategyHealthListResponse> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.asset_class) qs.set("asset_class", params.asset_class);
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null) qs.set("offset", String(params.offset));
  const q = qs.toString();
  return request<StrategyHealthListResponse>(`/api/strategies/health${q ? `?${q}` : ""}`);
}

// ---------------------------------------------------------------------------
// M28: Project Health
// ---------------------------------------------------------------------------

export async function getProjectHealth(projectId: string): Promise<ProjectHealth> {
  return request<ProjectHealth>(`/api/projects/${projectId}/health`);
}

export async function getProjectsHealth(params?: {
  organization_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<ProjectHealthListResponse> {
  const qs = new URLSearchParams();
  if (params?.organization_id) qs.set("organization_id", params.organization_id);
  if (params?.status) qs.set("status", params.status);
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null) qs.set("offset", String(params.offset));
  const q = qs.toString();
  return request<ProjectHealthListResponse>(`/api/projects/health${q ? `?${q}` : ""}`);
}

// ---------------------------------------------------------------------------
// M29: Run History and Timeline Drilldown
// ---------------------------------------------------------------------------

export async function getStrategyRunHistory(
  strategyId: string,
  params?: {
    run_type?: string;
    status?: string;
    evidence_status?: string;
    limit?: number;
    offset?: number;
  },
): Promise<StrategyRunHistoryResponse> {
  const qs = new URLSearchParams();
  if (params?.run_type) qs.set("run_type", params.run_type);
  if (params?.status) qs.set("status", params.status);
  if (params?.evidence_status) qs.set("evidence_status", params.evidence_status);
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null) qs.set("offset", String(params.offset));
  const q = qs.toString();
  return request<StrategyRunHistoryResponse>(
    `/api/strategies/${strategyId}/run-history${q ? `?${q}` : ""}`,
  );
}

export async function getStrategyTimelineDrilldown(
  strategyId: string,
  params?: {
    limit?: number;
    offset?: number;
    event_type?: string;
    source_type?: string;
  },
): Promise<StrategyTimelineDrilldownResponse> {
  const qs = new URLSearchParams();
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null) qs.set("offset", String(params.offset));
  if (params?.event_type) qs.set("event_type", params.event_type);
  if (params?.source_type) qs.set("source_type", params.source_type);
  const q = qs.toString();
  return request<StrategyTimelineDrilldownResponse>(
    `/api/strategies/${strategyId}/timeline/drilldown${q ? `?${q}` : ""}`,
  );
}

export async function getStrategyEvidenceTrends(
  strategyId: string,
  params?: {
    limit_per_series?: number;
  },
): Promise<StrategyEvidenceTrendsResponse> {
  const qs = new URLSearchParams();
  if (params?.limit_per_series != null)
    qs.set("limit_per_series", String(params.limit_per_series));
  const q = qs.toString();
  return request<StrategyEvidenceTrendsResponse>(
    `/api/strategies/${strategyId}/evidence-trends${q ? `?${q}` : ""}`,
  );
}

export async function exportStrategyEvidence(
  strategyId: string,
  params?: {
    format?: string;
    include_raw_json?: boolean;
    limit_recent_runs?: number;
    limit_timeline_events?: number;
  },
): Promise<StrategyExportResponse> {
  const qs = new URLSearchParams();
  if (params?.format) qs.set("format", params.format);
  if (params?.include_raw_json != null)
    qs.set("include_raw_json", String(params.include_raw_json));
  if (params?.limit_recent_runs != null)
    qs.set("limit_recent_runs", String(params.limit_recent_runs));
  if (params?.limit_timeline_events != null)
    qs.set("limit_timeline_events", String(params.limit_timeline_events));
  const q = qs.toString();
  return request<StrategyExportResponse>(
    `/api/strategies/${strategyId}/export${q ? `?${q}` : ""}`,
  );
}

export async function getPortfolioOverview(params?: {
  project_id?: string;
  organization_id?: string;
  include_archived?: boolean;
  limit_per_section?: number;
}): Promise<PortfolioOverview> {
  const qs = new URLSearchParams();
  if (params?.project_id) qs.set("project_id", params.project_id);
  if (params?.organization_id) qs.set("organization_id", params.organization_id);
  if (params?.include_archived != null)
    qs.set("include_archived", String(params.include_archived));
  if (params?.limit_per_section != null)
    qs.set("limit_per_section", String(params.limit_per_section));
  const q = qs.toString();
  return request<PortfolioOverview>(
    `/api/portfolio/overview${q ? `?${q}` : ""}`,
  );
}

export async function compareStrategyRunsMulti(
  payload: MultiRunComparisonRequest,
): Promise<MultiRunComparisonResponse> {
  return request<MultiRunComparisonResponse>("/api/strategies/runs/compare-multi", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getStrategyVersionLineage(
  strategyId: string,
): Promise<StrategyVersionLineageResponse> {
  return request<StrategyVersionLineageResponse>(
    `/api/strategies/${strategyId}/version-lineage`,
  );
}

// ---------------------------------------------------------------------------
// M37: Dataset Quality Drilldown
// ---------------------------------------------------------------------------

export async function getDatasetSnapshotQualityDrilldown(
  snapshotId: string,
): Promise<DatasetQualityDrilldownResponse> {
  return request<DatasetQualityDrilldownResponse>(
    `/api/dataset-snapshots/${snapshotId}/quality-drilldown`,
  );
}

// ---------------------------------------------------------------------------
// M38: Signal Quality Drilldown
// ---------------------------------------------------------------------------

export async function getSignalSnapshotQualityDrilldown(
  snapshotId: string,
): Promise<SignalQualityDrilldownResponse> {
  return request<SignalQualityDrilldownResponse>(
    `/api/signal-snapshots/${snapshotId}/quality-drilldown`,
  );
}

// ---------------------------------------------------------------------------
// M39: Universe Coverage Analysis
// ---------------------------------------------------------------------------

export async function getUniverseSnapshotCoverageAnalysis(
  snapshotId: string,
): Promise<UniverseCoverageAnalysisResponse> {
  return request<UniverseCoverageAnalysisResponse>(
    `/api/universe-snapshots/${snapshotId}/coverage-analysis`,
  );
}

// ---------------------------------------------------------------------------
// M40: Config Snapshot Diff V2
// ---------------------------------------------------------------------------

export async function compareConfigSnapshotsV2(
  strategyId: string,
  snapshotAId: string,
  snapshotBId: string,
): Promise<ConfigSnapshotComparisonV2Response> {
  return request<ConfigSnapshotComparisonV2Response>(
    `/api/strategies/${strategyId}/config-snapshots/compare-v2?snapshot_a_id=${snapshotAId}&snapshot_b_id=${snapshotBId}`,
  );
}

// ---------------------------------------------------------------------------
// M41: Assumption Health
// ---------------------------------------------------------------------------

export async function getStrategyAssumptionHealth(
  strategyId: string,
): Promise<StrategyAssumptionHealthResponse> {
  return request<StrategyAssumptionHealthResponse>(
    `/api/strategies/${strategyId}/assumption-health`,
  );
}
