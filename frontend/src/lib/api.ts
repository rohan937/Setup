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
  StrategyTimelineAnalyticsResponse,
  StrategyComparisonReportRequest,
  StrategyComparisonReportResponse,
  SystemHealthResponse,
  DemoSeedRequest,
  DemoSeedResponse,
  AdvancedDemoSeedResponse,
  DemoStatusResponse,
  StrategyDriftResponse,
  StrategyEvidenceFreshnessResponse,
  ActionQueueResponse,
  StrategyLifecycleResponse,
  RepairOptionsResponse,
  RunLinkUpdateRequest,
  RunLinkSummary,
  StrategyUpdateRequest,
  StrategyManagementSummary,
  StrategyReadinessResponse,
  StrategyShadowMonitorResponse,
  StrategyPromotionGateResponse,
  StrategyEvidenceGraphResponse,
  StrategyRegressionTest,
  StrategyRegressionTestRun,
  StrategyRegressionTestRunListResponse,
  StrategyRegressionTestRunRequest,
  StrategyConfigPolicy,
  StrategyConfigPolicyCreate,
  ConfigPolicyEvaluationRequest,
  ConfigPolicyEvaluation,
  ConfigPolicyEvaluationListResponse,
  ResearchReviewCase,
  ResearchReviewCaseGenerateResponse,
  ResearchReviewCaseListResponse,
  EvidenceSLAPolicy,
  EvidenceSLAPolicyCreate,
  EvidenceSLAEvaluation,
  EvidenceSLAEvaluationListResponse,
  UserRegisterRequest,
  UserLoginRequest,
  AuthTokenResponse,
  CurrentUserResponse,
  AuthStatusResponse,
} from "@/types";

// ---------------------------------------------------------------------------
// M71: API base URL helpers — resolved from VITE_API_BASE_URL env var.
// Trailing slashes are trimmed so path concatenation is safe regardless of
// how the env var is set in the Vercel dashboard.
// ---------------------------------------------------------------------------

/** Return the configured backend API base URL, trailing-slash trimmed. */
export function getApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  return raw.replace(/\/+$/, "");
}

/** Return the configured frontend environment (local | staging | production). */
export function getFrontendEnvironment(): string {
  return import.meta.env.VITE_APP_ENV ?? "local";
}

/** True when VITE_DEMO_MODE=true is set (reserved for M73). */
export function isDemoMode(): boolean {
  return import.meta.env.VITE_DEMO_MODE === "true";
}

const API_BASE_URL = getApiBaseUrl();

export function setAuthToken(token: string): void { localStorage.setItem("qf_access_token", token); }
export function getAuthToken(): string | null { return localStorage.getItem("qf_access_token"); }
export function clearAuthToken(): void { localStorage.removeItem("qf_access_token"); }

export function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem("qf_access_token");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = "Bearer " + token;
  return headers;
}

/**
 * Structured HTTP error — carries the HTTP status code so callers can
 * distinguish auth failures (401) from server errors (5xx) or network
 * problems, rather than treating every failure as identical.
 *
 * Used by AuthContext.refreshCurrentUser() to only clear the stored token
 * on a genuine 401 (token expired/invalid), NOT on transient 5xx errors or
 * network failures that would otherwise permanently sign the user out.
 */
export class HttpError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "HttpError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Attach the Authorization bearer header when a token is present so that
  // web ingestion and all calls are authenticated and RBAC applies.
  // Backward compatible: no token => no Authorization header => unchanged.
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { ...getAuthHeaders(), ...init?.headers },
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
    throw new HttpError(res.status, message);
  }
  return (await res.json()) as T;
}

export async function fetchApiInfo(): Promise<ApiInfo> {
  return request<ApiInfo>("/api");
}

export async function getProjects(): Promise<Project[]> {
  return request<Project[]>("/api/projects");
}

export interface ProjectCreateRequest {
  name: string;
  slug?: string;
  description?: string;
  organization_id?: string;
}

export async function createProject(
  data: ProjectCreateRequest,
): Promise<Project> {
  return request<Project>("/api/projects", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getStrategies(
  status?: "active" | "archived" | "all",
): Promise<Strategy[]> {
  const qs = status && status !== "all" ? `?status=${status}` : "";
  return request<Strategy[]>(`/api/strategies${qs}`);
}

export async function getStrategy(id: string): Promise<StrategyDetail> {
  return request<StrategyDetail>(`/api/strategies/${id}`);
}

// M75: Evidence Repair + Strategy Management ---------------------------------

export async function getStrategyRepairOptions(
  id: string,
): Promise<RepairOptionsResponse> {
  return request<RepairOptionsResponse>(`/api/strategies/${id}/repair-options`);
}

export async function linkRunEvidence(
  strategyId: string,
  runId: string,
  links: RunLinkUpdateRequest,
): Promise<RunLinkSummary> {
  return request<RunLinkSummary>(
    `/api/strategies/${strategyId}/runs/${runId}/links`,
    { method: "PATCH", body: JSON.stringify(links) },
  );
}

export async function updateStrategy(
  id: string,
  data: StrategyUpdateRequest,
): Promise<StrategyManagementSummary> {
  return request<StrategyManagementSummary>(`/api/strategies/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function archiveStrategy(
  id: string,
): Promise<StrategyManagementSummary> {
  return request<StrategyManagementSummary>(
    `/api/strategies/${id}?confirm=true`,
    { method: "DELETE" },
  );
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

// ---------------------------------------------------------------------------
// M43: Timeline Analytics
// ---------------------------------------------------------------------------

export async function getStrategyTimelineAnalytics(
  strategyId: string,
  params?: { bucket?: string; lookback_days?: number },
): Promise<StrategyTimelineAnalyticsResponse> {
  const qs = new URLSearchParams();
  if (params?.bucket) qs.set("bucket", params.bucket);
  if (params?.lookback_days != null) qs.set("lookback_days", String(params.lookback_days));
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return request<StrategyTimelineAnalyticsResponse>(
    `/api/strategies/${strategyId}/timeline/analytics${query}`,
  );
}

// ---------------------------------------------------------------------------
// M44: Strategy Comparison Report
// ---------------------------------------------------------------------------

export async function generateStrategyComparisonReport(
  payload: StrategyComparisonReportRequest,
): Promise<StrategyComparisonReportResponse> {
  return request<StrategyComparisonReportResponse>("/api/strategies/compare/report", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// M45: System Health
// ---------------------------------------------------------------------------

export async function getSystemHealth(): Promise<SystemHealthResponse> {
  return request<SystemHealthResponse>("/api/admin/system-health");
}

// ---------------------------------------------------------------------------
// M46: Demo Mode
// ---------------------------------------------------------------------------

export async function seedDemoData(payload: DemoSeedRequest): Promise<DemoSeedResponse> {
  return request<DemoSeedResponse>("/api/admin/seed-demo", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getDemoStatus(): Promise<DemoStatusResponse> {
  return request<DemoStatusResponse>("/api/admin/demo-status");
}

// M78: seed the advanced demo strategy
export async function seedAdvancedDemoStrategy(): Promise<AdvancedDemoSeedResponse> {
  return request<AdvancedDemoSeedResponse>("/api/admin/demo/advanced-strategy", {
    method: "POST",
  });
}

// ---------------------------------------------------------------------------
// M47: Strategy Drift
// ---------------------------------------------------------------------------

export async function getStrategyDrift(
  strategyId: string,
  params?: { mode?: string; baseline_run_id?: string; comparison_run_id?: string },
): Promise<StrategyDriftResponse> {
  const qs = new URLSearchParams();
  if (params?.mode) qs.set("mode", params.mode);
  if (params?.baseline_run_id) qs.set("baseline_run_id", params.baseline_run_id);
  if (params?.comparison_run_id) qs.set("comparison_run_id", params.comparison_run_id);
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return request<StrategyDriftResponse>(
    `/api/strategies/${strategyId}/drift${query}`,
  );
}

// ---------------------------------------------------------------------------
// M48: Evidence Freshness
// ---------------------------------------------------------------------------

export async function getStrategyEvidenceFreshness(
  strategyId: string,
): Promise<StrategyEvidenceFreshnessResponse> {
  return request<StrategyEvidenceFreshnessResponse>(
    `/api/strategies/${strategyId}/freshness`,
  );
}

// ---------------------------------------------------------------------------
// M49: Strategy Readiness
// ---------------------------------------------------------------------------

export async function getStrategyReadiness(
  strategyId: string,
): Promise<StrategyReadinessResponse> {
  return request<StrategyReadinessResponse>(
    `/api/strategies/${strategyId}/readiness`,
  );
}

// ---------------------------------------------------------------------------
// M74: Strategy Action Queue
// ---------------------------------------------------------------------------

export async function getStrategyActionQueue(
  strategyId: string,
  limit?: number,
): Promise<ActionQueueResponse> {
  const qs = new URLSearchParams();
  if (limit !== undefined) qs.set("limit", String(limit));
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return request<ActionQueueResponse>(
    `/api/strategies/${strategyId}/action-queue${query}`,
  );
}

// M76: strategy lifecycle inference
export async function getStrategyLifecycle(
  strategyId: string,
): Promise<StrategyLifecycleResponse> {
  return request<StrategyLifecycleResponse>(
    `/api/strategies/${strategyId}/lifecycle`,
  );
}

// ---------------------------------------------------------------------------
// M50: Shadow Production Monitor
// ---------------------------------------------------------------------------

export async function getStrategyShadowMonitor(
  strategyId: string,
  params?: { mode?: string; baseline_run_id?: string; shadow_run_id?: string },
): Promise<StrategyShadowMonitorResponse> {
  const qs = new URLSearchParams();
  if (params?.mode) qs.set("mode", params.mode);
  if (params?.baseline_run_id) qs.set("baseline_run_id", params.baseline_run_id);
  if (params?.shadow_run_id) qs.set("shadow_run_id", params.shadow_run_id);
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return request<StrategyShadowMonitorResponse>(
    `/api/strategies/${strategyId}/shadow-monitor${query}`,
  );
}

// ---------------------------------------------------------------------------
// M51: Promotion Gates
// ---------------------------------------------------------------------------

export async function getStrategyPromotionGates(
  strategyId: string,
  targetStage: string,
): Promise<StrategyPromotionGateResponse> {
  const qs = new URLSearchParams();
  qs.set("target_stage", targetStage);
  return request<StrategyPromotionGateResponse>(
    `/api/strategies/${strategyId}/promotion-gates?${qs.toString()}`,
  );
}

// ---------------------------------------------------------------------------
// M52: Evidence Dependency Graph
// ---------------------------------------------------------------------------

export async function getStrategyEvidenceGraph(
  strategyId: string,
  params?: {
    focus_node_id?: string;
    focus_node_type?: string;
    include_timeline?: boolean;
    include_computed?: boolean;
  },
): Promise<StrategyEvidenceGraphResponse> {
  const qs = new URLSearchParams();
  if (params?.focus_node_id) qs.set("focus_node_id", params.focus_node_id);
  if (params?.focus_node_type) qs.set("focus_node_type", params.focus_node_type);
  if (params?.include_timeline !== undefined) qs.set("include_timeline", String(params.include_timeline));
  if (params?.include_computed !== undefined) qs.set("include_computed", String(params.include_computed));
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return request<StrategyEvidenceGraphResponse>(
    `/api/strategies/${strategyId}/evidence-graph${query}`,
  );
}

// ---------------------------------------------------------------------------
// M53: Regression Test Suite
// ---------------------------------------------------------------------------

export async function createDefaultRegressionTests(
  strategyId: string,
): Promise<StrategyRegressionTest[]> {
  return request<StrategyRegressionTest[]>(
    `/api/strategies/${strategyId}/regression-tests/defaults`,
    { method: "POST" },
  );
}

export async function getStrategyRegressionTests(
  strategyId: string,
): Promise<StrategyRegressionTest[]> {
  return request<StrategyRegressionTest[]>(
    `/api/strategies/${strategyId}/regression-tests`,
  );
}

export async function runStrategyRegressionTests(
  strategyId: string,
  payload: StrategyRegressionTestRunRequest,
): Promise<StrategyRegressionTestRun> {
  return request<StrategyRegressionTestRun>(
    `/api/strategies/${strategyId}/regression-tests/run`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function getStrategyRegressionTestRuns(
  strategyId: string,
  params?: { limit?: number; offset?: number },
): Promise<StrategyRegressionTestRunListResponse> {
  const qs = new URLSearchParams();
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  if (params?.offset !== undefined) qs.set("offset", String(params.offset));
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return request<StrategyRegressionTestRunListResponse>(
    `/api/strategies/${strategyId}/regression-tests/runs${query}`,
  );
}

export async function getRegressionTestRun(
  testRunId: string,
): Promise<StrategyRegressionTestRun> {
  return request<StrategyRegressionTestRun>(
    `/api/regression-test-runs/${testRunId}`,
  );
}

// M54 — Config Policy Engine
export async function createDefaultConfigPolicy(
  strategyId: string,
): Promise<StrategyConfigPolicy> {
  return request<StrategyConfigPolicy>(
    `/api/strategies/${strategyId}/config-policies/default`,
    { method: "POST" },
  );
}

export async function createConfigPolicy(
  strategyId: string,
  payload: StrategyConfigPolicyCreate,
): Promise<StrategyConfigPolicy> {
  return request<StrategyConfigPolicy>(
    `/api/strategies/${strategyId}/config-policies`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function getStrategyConfigPolicies(
  strategyId: string,
): Promise<StrategyConfigPolicy[]> {
  return request<StrategyConfigPolicy[]>(
    `/api/strategies/${strategyId}/config-policies`,
  );
}

export async function evaluateConfigPolicy(
  strategyId: string,
  policyId: string,
  payload: ConfigPolicyEvaluationRequest,
): Promise<ConfigPolicyEvaluation> {
  return request<ConfigPolicyEvaluation>(
    `/api/strategies/${strategyId}/config-policies/${policyId}/evaluate`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function getConfigPolicyEvaluations(
  strategyId: string,
): Promise<ConfigPolicyEvaluationListResponse> {
  return request<ConfigPolicyEvaluationListResponse>(
    `/api/strategies/${strategyId}/config-policy-evaluations`,
  );
}

export async function getConfigPolicyEvaluation(
  evaluationId: string,
): Promise<ConfigPolicyEvaluation> {
  return request<ConfigPolicyEvaluation>(
    `/api/config-policy-evaluations/${evaluationId}`,
  );
}

// M55 — Research Review Cases
export async function generateResearchReviewCases(
  strategyId: string,
): Promise<ResearchReviewCaseGenerateResponse> {
  return request<ResearchReviewCaseGenerateResponse>(
    `/api/strategies/${strategyId}/review-cases/generate`,
    { method: "POST" },
  );
}

export async function getStrategyReviewCases(
  strategyId: string,
  status?: string,
): Promise<ResearchReviewCaseListResponse> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<ResearchReviewCaseListResponse>(
    `/api/strategies/${strategyId}/review-cases${qs}`,
  );
}

export async function getResearchReviewCase(
  caseId: string,
): Promise<ResearchReviewCase> {
  return request<ResearchReviewCase>(`/api/review-cases/${caseId}`);
}

export async function acknowledgeResearchReviewCase(
  caseId: string,
): Promise<ResearchReviewCase> {
  return request<ResearchReviewCase>(`/api/review-cases/${caseId}/acknowledge`, {
    method: "POST",
  });
}

export async function resolveResearchReviewCase(
  caseId: string,
): Promise<ResearchReviewCase> {
  return request<ResearchReviewCase>(`/api/review-cases/${caseId}/resolve`, {
    method: "POST",
  });
}

// M56 — Evidence SLA Monitor
export async function createDefaultEvidenceSLAPolicy(
  strategyId: string,
): Promise<EvidenceSLAPolicy> {
  return request<EvidenceSLAPolicy>(
    `/api/strategies/${strategyId}/evidence-sla/default`,
    { method: "POST" },
  );
}

export async function createEvidenceSLAPolicy(
  strategyId: string,
  payload: EvidenceSLAPolicyCreate,
): Promise<EvidenceSLAPolicy> {
  return request<EvidenceSLAPolicy>(
    `/api/strategies/${strategyId}/evidence-sla/policies`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function getEvidenceSLAPolicies(
  strategyId: string,
): Promise<EvidenceSLAPolicy[]> {
  return request<EvidenceSLAPolicy[]>(
    `/api/strategies/${strategyId}/evidence-sla/policies`,
  );
}

export async function evaluateEvidenceSLAPolicy(
  strategyId: string,
  policyId: string,
): Promise<EvidenceSLAEvaluation> {
  return request<EvidenceSLAEvaluation>(
    `/api/strategies/${strategyId}/evidence-sla/policies/${policyId}/evaluate`,
    { method: "POST" },
  );
}

export async function getEvidenceSLAEvaluations(
  strategyId: string,
): Promise<EvidenceSLAEvaluationListResponse> {
  return request<EvidenceSLAEvaluationListResponse>(
    `/api/strategies/${strategyId}/evidence-sla/evaluations`,
  );
}

export async function getEvidenceSLAEvaluation(
  evaluationId: string,
): Promise<EvidenceSLAEvaluation> {
  return request<EvidenceSLAEvaluation>(
    `/api/evidence-sla/evaluations/${evaluationId}`,
  );
}

// M57 - Strategy Change Impact Analysis
export async function getStrategyChangeImpact(
  strategyId: string,
  params?: {
    mode?: string;
    focus_node_id?: string;
    focus_node_type?: string;
  },
): Promise<import("@/types").StrategyChangeImpactResponse> {
  const query = new URLSearchParams();
  if (params?.mode) query.set("mode", params.mode);
  if (params?.focus_node_id) query.set("focus_node_id", params.focus_node_id);
  if (params?.focus_node_type)
    query.set("focus_node_type", params.focus_node_type);
  const qs = query.toString();
  return request<import("@/types").StrategyChangeImpactResponse>(
    `/api/strategies/${strategyId}/change-impact${qs ? `?${qs}` : ""}`,
  );
}

// M58 - Run Replay Pack
export async function getRunReplayPack(
  strategyId: string,
  runId: string,
  params?: { format?: string; include_raw_json?: boolean },
): Promise<import("@/types").RunReplayResponse> {
  const query = new URLSearchParams();
  if (params?.format) query.set("format", params.format);
  if (params?.include_raw_json !== undefined)
    query.set("include_raw_json", String(params.include_raw_json));
  const qs = query.toString();
  return request<import("@/types").RunReplayResponse>(
    `/api/strategies/${strategyId}/runs/${runId}/replay-pack${qs ? `?${qs}` : ""}`,
  );
}

// M59 - Experiment Registry
export async function createStrategyExperiment(
  strategyId: string,
  payload: import("@/types").StrategyExperimentCreate,
): Promise<import("@/types").StrategyExperiment> {
  return request<import("@/types").StrategyExperiment>(
    `/api/strategies/${strategyId}/experiments`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function getStrategyExperiments(
  strategyId: string,
  params?: { status?: string },
): Promise<{ items: import("@/types").StrategyExperiment[]; total: number }> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  const qs = query.toString();
  return request<{ items: import("@/types").StrategyExperiment[]; total: number }>(
    `/api/strategies/${strategyId}/experiments${qs ? `?${qs}` : ""}`,
  );
}

export async function getStrategyExperiment(
  experimentId: string,
): Promise<import("@/types").StrategyExperimentDetail> {
  return request<import("@/types").StrategyExperimentDetail>(
    `/api/experiments/${experimentId}`,
  );
}

export async function addRunToExperiment(
  experimentId: string,
  payload: import("@/types").ExperimentRunAddRequest,
): Promise<import("@/types").StrategyExperimentRun> {
  return request<import("@/types").StrategyExperimentRun>(
    `/api/experiments/${experimentId}/runs`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function removeRunFromExperiment(
  experimentId: string,
  runId: string,
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/experiments/${experimentId}/runs/${runId}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "Request failed");
    throw new Error(text);
  }
}

export async function analyzeStrategyExperiment(
  experimentId: string,
): Promise<import("@/types").StrategyExperimentAnalysis> {
  return request<import("@/types").StrategyExperimentAnalysis>(
    `/api/experiments/${experimentId}/analyze`,
    { method: "POST" },
  );
}

export async function getExperimentAnalyses(
  experimentId: string,
): Promise<import("@/types").StrategyExperimentAnalysisListResponse> {
  return request<import("@/types").StrategyExperimentAnalysisListResponse>(
    `/api/experiments/${experimentId}/analyses`,
  );
}

export async function getExperimentAnalysis(
  analysisId: string,
): Promise<import("@/types").StrategyExperimentAnalysis> {
  return request<import("@/types").StrategyExperimentAnalysis>(
    `/api/experiment-analyses/${analysisId}`,
  );
}

// M61 - Strategy Robustness Score
export async function getStrategyRobustness(
  strategyId: string,
): Promise<import("@/types").StrategyRobustnessResponse> {
  return request<import("@/types").StrategyRobustnessResponse>(
    `/api/strategies/${strategyId}/robustness`,
  );
}

// M60 - Parameter Sweep Reliability Analysis
export async function analyzeParameterSweep(
  experimentId: string,
  payload: import("@/types").ParameterSweepAnalysisRequest,
): Promise<import("@/types").ParameterSweepAnalysisResponse> {
  return request<import("@/types").ParameterSweepAnalysisResponse>(
    `/api/experiments/${experimentId}/sweep-analysis`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

// M62 - Progression Freeze Recommendations
export async function getStrategyProgressionFreeze(
  strategyId: string,
  params?: { target_stage?: string },
): Promise<import("@/types").StrategyProgressionFreezeResponse> {
  const qs = params?.target_stage ? `?target_stage=${params.target_stage}` : "";
  return request<import("@/types").StrategyProgressionFreezeResponse>(
    `/api/strategies/${strategyId}/progression-freeze${qs}`,
  );
}

// M63 - Quant Research Audit Trail
export async function getStrategyResearchAuditTrail(
  strategyId: string,
  params?: {
    limit?: number;
    offset?: number;
    category?: string;
    severity?: string;
    include_context?: boolean;
  },
): Promise<import("@/types").ResearchAuditTrailResponse> {
  const sp = new URLSearchParams();
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.offset) sp.set("offset", String(params.offset));
  if (params?.category) sp.set("category", params.category);
  if (params?.severity) sp.set("severity", params.severity);
  if (params?.include_context === false) sp.set("include_context", "false");
  const qs = sp.toString();
  return request<import("@/types").ResearchAuditTrailResponse>(
    `/api/strategies/${strategyId}/research-audit-trail${qs ? "?" + qs : ""}`,
  );
}

// M64 - Strategy Reliability Command Center
export async function getStrategyReliabilityCommandCenter(
  strategyId: string
): Promise<import("@/types").StrategyReliabilityCommandCenterResponse> {
  return request<import("@/types").StrategyReliabilityCommandCenterResponse>(
    `/api/strategies/${strategyId}/command-center`,
  );
}

// M65A - Strategy Reliability Snapshot Cache
export async function refreshStrategyReliabilitySnapshot(
  strategyId: string,
  force?: boolean
): Promise<import("@/types").StrategyReliabilitySnapshot> {
  const qs = force ? "?force=true" : "";
  return request<import("@/types").StrategyReliabilitySnapshot>(
    `/api/strategies/${strategyId}/reliability-snapshot/refresh${qs}`,
    { method: "POST" },
  );
}

export async function getStrategyReliabilitySnapshot(
  strategyId: string
): Promise<import("@/types").StrategyReliabilitySnapshot> {
  return request<import("@/types").StrategyReliabilitySnapshot>(
    `/api/strategies/${strategyId}/reliability-snapshot`,
  );
}

export async function getStrategyReliabilitySnapshotHistory(
  strategyId: string
): Promise<import("@/types").StrategyReliabilitySnapshotListResponse> {
  return request<import("@/types").StrategyReliabilitySnapshotListResponse>(
    `/api/strategies/${strategyId}/reliability-snapshots`,
  );
}

// M65 - Deployment Readiness
export async function getDeploymentReadiness(): Promise<import("@/types").DeploymentReadinessResponse> {
  return request<import("@/types").DeploymentReadinessResponse>(
    "/api/admin/deployment-readiness",
  );
}

// M67 - Workspace Settings + Members Foundation
export async function getWorkspaceSummary(): Promise<import("@/types").WorkspaceSummary> {
  return request<import("@/types").WorkspaceSummary>("/api/workspace/settings");
}

export async function updateWorkspaceSettings(
  payload: import("@/types").WorkspaceSettingsUpdate,
): Promise<import("@/types").WorkspaceSummary> {
  return request<import("@/types").WorkspaceSummary>("/api/workspace/settings", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function getWorkspaceMembers(params?: {
  status?: string;
}): Promise<import("@/types").WorkspaceMemberListResponse> {
  const qs = params?.status ? `?status=${params.status}` : "";
  return request<import("@/types").WorkspaceMemberListResponse>(
    `/api/workspace/members${qs}`,
  );
}

export async function createWorkspaceMember(
  payload: import("@/types").WorkspaceMemberCreate,
): Promise<import("@/types").WorkspaceMember> {
  return request<import("@/types").WorkspaceMember>("/api/workspace/members", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateWorkspaceMember(
  memberId: string,
  payload: import("@/types").WorkspaceMemberUpdate,
): Promise<import("@/types").WorkspaceMember> {
  return request<import("@/types").WorkspaceMember>(
    `/api/workspace/members/${memberId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export async function removeWorkspaceMember(memberId: string): Promise<void> {
  await request<void>(`/api/workspace/members/${memberId}`, {
    method: "DELETE",
  });
}

// M68 - Auth + User Accounts
export async function registerUser(payload: UserRegisterRequest): Promise<AuthTokenResponse> {
  const res = await fetch(API_BASE_URL + "/api/auth/register", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function loginUser(payload: UserLoginRequest): Promise<AuthTokenResponse> {
  const res = await fetch(API_BASE_URL + "/api/auth/login", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getCurrentUser(): Promise<CurrentUserResponse> {
  const res = await fetch(API_BASE_URL + "/api/auth/me", { headers: getAuthHeaders() });
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (typeof body.detail === "string") message = body.detail;
    } catch { /* ignore */ }
    throw new HttpError(res.status, message);
  }
  return res.json() as Promise<CurrentUserResponse>;
}

export async function logoutUser(): Promise<void> {
  await fetch(API_BASE_URL + "/api/auth/logout", { method: "POST", headers: getAuthHeaders() });
  clearAuthToken();
}

// First-owner bootstrap: promote the current user to owner of the default
// workspace. The backend only permits this while no owner exists anywhere.
export async function bootstrapFirstOwner(): Promise<CurrentUserResponse> {
  const res = await fetch(API_BASE_URL + "/api/auth/bootstrap-first-owner", {
    method: "POST",
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function getAuthStatus(): Promise<AuthStatusResponse> {
  const res = await fetch(API_BASE_URL + "/api/auth/status", { headers: getAuthHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
