import type { ApiInfo } from "@/types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function fetchApiInfo(): Promise<ApiInfo> {
  const res = await fetch(`${API_BASE_URL}/api`);
  if (!res.ok) {
    throw new Error(`API responded ${res.status}`);
  }
  return (await res.json()) as ApiInfo;
}
