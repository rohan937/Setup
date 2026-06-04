import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import PageHeader from "@/components/PageHeader";
import type { Strategy } from "@/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function fetchStrategies(): Promise<Strategy[]> {
  const res = await fetch(`${API_BASE_URL}/api/strategies`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as Strategy[];
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function CommandCenter() {
  const [strategies, setStrategies] = useState<Strategy[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchStrategies()
      .then((data) => {
        setStrategies(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
  }, []);

  return (
    <div className="flex flex-col gap-4 px-6 py-6 max-w-3xl mx-auto">
      <PageHeader
        title="Reliability Command Center"
        subtitle="Aggregate reliability view across all strategies"
      />

      {/* Description */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="text-sm text-text-secondary">
          Open the Strategy Reliability Command Center from any strategy to see aggregated
          readiness, robustness, freeze recommendations, subsystem health, and prioritized
          action queue.
        </p>
      </div>

      {/* Strategy list */}
      <div className="rounded-card border border-border bg-bg-700">
        <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
          <p className="caption">Strategies</p>
          <Link to="/strategies" className="text-xs text-accent-500 hover:text-accent-300">
            All strategies →
          </Link>
        </div>

        {loading && (
          <div className="px-4 py-4">
            <p className="text-sm text-text-muted animate-pulse">Loading strategies…</p>
          </div>
        )}

        {error && (
          <div className="px-4 py-4 space-y-2">
            <p className="text-sm text-amber-400">
              Could not load strategies: {error}
            </p>
            <p className="text-sm text-text-muted">
              Open{" "}
              <Link to="/strategies" className="text-accent-500 hover:text-accent-300">
                Strategies
              </Link>{" "}
              to navigate to individual Command Centers.
            </p>
          </div>
        )}

        {!loading && !error && strategies && strategies.length === 0 && (
          <div className="px-4 py-6 flex flex-col gap-1">
            <p className="text-sm text-text-secondary">No strategies yet.</p>
            <p className="text-sm text-text-muted">
              <Link to="/strategies" className="text-accent-500 hover:text-accent-300">
                Create your first strategy →
              </Link>
            </p>
          </div>
        )}

        {!loading && !error && strategies && strategies.length > 0 && (
          <div className="divide-y divide-border">
            {strategies.map((strategy) => (
              <div
                key={strategy.id}
                className="flex items-center justify-between px-4 py-2.5 hover:bg-bg-600/30 transition-colors"
              >
                <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                  <span className="text-sm text-text-primary font-medium truncate">
                    {strategy.name}
                  </span>
                  {strategy.slug && (
                    <span className="font-mono text-2xs text-text-muted truncate">
                      {strategy.slug}
                    </span>
                  )}
                </div>
                <Link
                  to={`/strategies/${strategy.id}`}
                  className="shrink-0 ml-4 text-xs border border-border bg-bg-600 text-text-secondary hover:text-accent-500 hover:border-accent-500/40 rounded-control px-2.5 py-1 transition-colors"
                >
                  Open
                </Link>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* How to access */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="caption mb-1.5">How to access</p>
        <p className="text-sm text-text-secondary">
          The full Command Center is available inside each Strategy Detail page. Select a
          strategy above or navigate to{" "}
          <Link to="/strategies" className="text-accent-500 hover:text-accent-300">
            Strategies
          </Link>{" "}
          to open the reliability view for a specific strategy.
        </p>
      </div>

      {/* Footer note */}
      <p className="text-xs text-text-muted pb-2">
        Deterministic research governance only. Not trading approval.
      </p>
    </div>
  );
}
