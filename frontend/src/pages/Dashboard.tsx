import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Strategy } from "@/types";
import { getStrategies } from "@/lib/api";
import Badge from "@/components/Badge";

// Compact reliability pillar — replaces the old large ScoreCard grid
function Pillar({ label, description }: { label: string; description: string }) {
  return (
    <div className="flex flex-col gap-1 border-r border-border last:border-r-0 px-4 first:pl-0 last:pr-0 py-1">
      <p className="caption">{label}</p>
      <p className="mono-num text-lg font-semibold text-text-muted">—</p>
      <p className="font-mono text-2xs text-text-muted leading-relaxed">{description}</p>
    </div>
  );
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

export default function Dashboard() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getStrategies()
      .then(setStrategies)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-7">
      {/* Cockpit header */}
      <div>
        <p className="caption mb-1">Reliability Cockpit</p>
        <h1 className="text-xl font-semibold text-text-primary">
          Strategy Reliability Overview
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          Where alpha breaks between research, backtest, and live execution.
        </p>
      </div>

      {/* Score strip — horizontal compact pillars */}
      <div className="rounded-card border border-border bg-bg-700">
        <div className="border-b border-border px-4 py-2.5">
          <p className="caption">Reliability Pillars</p>
        </div>
        <div className="grid grid-cols-4 divide-x divide-border px-4 py-4">
          <Pillar
            label="Data Health"
            description="Source freshness, revisions, coverage gaps"
          />
          <Pillar
            label="Backtest Trust"
            description="Look-ahead, overfitting, assumption realism"
          />
          <Pillar
            label="Execution Fidelity"
            description="Fill slippage vs backtest assumptions"
          />
          <Pillar
            label="Research–Live Gap"
            description="Live Sharpe vs backtest Sharpe delta"
          />
        </div>
      </div>

      {/* Active strategies */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <p className="caption">Active Strategies</p>
          <Link
            to="/strategies"
            className="font-mono text-2xs text-accent-500 hover:text-accent-300"
          >
            all strategies →
          </Link>
        </div>

        {loading && (
          <p className="font-mono text-2xs text-text-muted">Loading…</p>
        )}

        {!loading && strategies.length === 0 && (
          <div className="rounded-card border border-dashed border-border bg-bg-800 px-5 py-8 text-center">
            <p className="font-mono text-2xs text-text-muted">No strategies registered.</p>
            <Link
              to="/strategies"
              className="mt-2 inline-block font-mono text-2xs text-accent-500 hover:text-accent-300"
            >
              Register a strategy →
            </Link>
          </div>
        )}

        {!loading && strategies.length > 0 && (
          <div className="overflow-hidden rounded-card border border-border">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-bg-800">
                  {["Strategy", "Asset", "Status", "Runs", "Last Run"].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-2 text-left font-mono text-2xs uppercase tracking-widest text-text-muted"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {strategies.slice(0, 6).map((s, i) => (
                  <tr
                    key={s.id}
                    className={`hover:bg-bg-600 ${
                      i < Math.min(strategies.length, 6) - 1 ? "border-b border-border" : ""
                    }`}
                  >
                    <td className="px-4 py-2.5">
                      <Link
                        to={`/strategies/${s.id}`}
                        className="text-sm font-medium text-text-primary hover:text-accent-300"
                      >
                        {s.name}
                      </Link>
                      <p className="mt-px font-mono text-2xs text-text-muted">
                        {s.project_name}
                      </p>
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge value={s.asset_class} variant="asset_class" />
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge value={s.status} variant="status" />
                    </td>
                    <td className="mono-num px-4 py-2.5 text-sm text-text-secondary">
                      {s.run_count}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-text-muted">
                      {formatDate(s.latest_run_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Evidence panels row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Recent run evidence */}
        <div className="rounded-card border border-border bg-bg-700">
          <div className="border-b border-border px-4 py-2.5">
            <p className="caption">Run Evidence</p>
          </div>
          <div className="p-4">
            {!loading && strategies.some((s) => s.run_count > 0) ? (
              <div className="space-y-2">
                {strategies
                  .filter((s) => s.run_count > 0)
                  .slice(0, 4)
                  .map((s) => (
                    <div key={s.id} className="flex items-center justify-between">
                      <div>
                        <Link
                          to={`/strategies/${s.id}`}
                          className="font-mono text-xs text-text-secondary hover:text-accent-300"
                        >
                          {s.name}
                        </Link>
                      </div>
                      <span className="font-mono text-2xs text-text-muted">
                        {s.run_count} run{s.run_count !== 1 ? "s" : ""}
                        {" · "}
                        {formatDate(s.latest_run_at)}
                      </span>
                    </div>
                  ))}
              </div>
            ) : (
              <p className="font-mono text-2xs text-text-muted">
                No run evidence yet. Register a strategy and log a run.
              </p>
            )}
          </div>
        </div>

        {/* Assumption coverage placeholder */}
        <div className="rounded-card border border-border bg-bg-700">
          <div className="border-b border-border px-4 py-2.5">
            <p className="caption">Assumption Coverage</p>
          </div>
          <div className="p-4">
            <p className="font-mono text-2xs text-text-muted">
              Transaction cost assumptions, fill model coverage, and universe
              constraints arrive with ingestion in a later milestone.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
