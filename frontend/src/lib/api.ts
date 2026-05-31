import type {
  ApiInfo,
  ApiError,
  Project,
  Strategy,
  StrategyDetail,
  StrategyRun,
  StrategyCreateRequest,
  StrategyRunCreateRequest,
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
