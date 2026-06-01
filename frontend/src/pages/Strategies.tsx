import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { Strategy, StrategyReliabilityScore } from "@/types";
import { getStrategies } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import Badge from "@/components/Badge";
import EmptyState from "@/components/EmptyState";
import StrategyCreateDrawer from "@/components/StrategyCreateDrawer";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

const TH = "px-4 py-2 text-left font-mono text-2xs uppercase tracking-widest text-text-muted";

function ReliabilityBadge({ score }: { score: StrategyReliabilityScore | null }) {
  if (!score) {
    return <span className="font-mono text-2xs text-text-muted/50">—</span>;
  }
  const statusColors: Record<string, string> = {
    excellent: "bg-cyan-900/40 text-cyan-300 border-cyan-700/40",
    good:      "bg-teal-900/40 text-teal-300 border-teal-700/40",
    review:    "bg-yellow-900/40 text-yellow-200 border-yellow-700/40",
    weak:      "bg-red-900/40 text-red-300 border-red-700/40",
    insufficient_evidence: "bg-bg-600 text-text-muted border-border",
  };
  const cls = statusColors[score.status] ?? statusColors.insufficient_evidence;
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`mono-num text-sm font-semibold ${score.overall_score !== null && score.overall_score >= 75 ? "text-green-400" : score.overall_score !== null && score.overall_score >= 55 ? "text-yellow-400" : "text-text-muted"}`}>
        {score.overall_score !== null ? score.overall_score.toFixed(0) : "—"}
      </span>
      <span className={`inline-flex rounded border px-1.5 py-px font-mono text-2xs ${cls}`}>
        {score.status.replace("_", " ")}
      </span>
    </span>
  );
}

export default function Strategies() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navigate = useNavigate();

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getStrategies()
      .then(setStrategies)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <>
      <PageHeader
        tag="Research"
        title="Strategy Lab"
        subtitle="Register and track every systematic strategy across data, backtest, and live execution."
      >
        <button
          onClick={() => navigate("/strategies/compare")}
          className="rounded-control border border-border bg-bg-700 px-3.5 py-1.5 text-xs font-medium text-text-secondary hover:border-accent-500/50 hover:text-accent-300"
        >
          Compare Strategies
        </button>
        <button
          onClick={() => setDrawerOpen(true)}
          className="rounded-control bg-accent-500 px-3.5 py-1.5 text-xs font-medium text-text-inverse hover:bg-accent-600"
        >
          + Register Strategy
        </button>
      </PageHeader>

      {loading && (
        <p className="font-mono text-2xs text-text-muted">Loading strategies…</p>
      )}

      {!loading && error && (
        <div className="rounded-card border border-fidelity-low/30 bg-fidelity-low/10 px-4 py-3">
          <p className="font-mono text-xs text-fidelity-low">{error}</p>
          <button onClick={load} className="mt-1.5 font-mono text-2xs text-accent-500 hover:text-accent-300">
            retry
          </button>
        </div>
      )}

      {!loading && !error && strategies.length === 0 && (
        <EmptyState
          title="No strategies registered"
          description="Register your first strategy to begin tracking run evidence and reliability metrics."
        />
      )}

      {!loading && !error && strategies.length > 0 && (
        <div className="overflow-hidden rounded-card border border-border">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-bg-800">
                <th className={TH}>Strategy</th>
                <th className={TH}>Project</th>
                <th className={TH}>Asset</th>
                <th className={TH}>Status</th>
                <th className={`${TH} text-right`}>Runs</th>
                <th className={TH}>Reliability</th>
                <th className={TH}>Last Run</th>
                <th className={TH}>Registered</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map((s, i) => (
                <tr
                  key={s.id}
                  className={`hover:bg-bg-600 transition-colors ${
                    i < strategies.length - 1 ? "border-b border-border" : ""
                  }`}
                >
                  <td className="px-4 py-3">
                    <Link
                      to={`/strategies/${s.id}`}
                      className="text-sm font-medium text-text-primary hover:text-accent-300"
                    >
                      {s.name}
                    </Link>
                    {s.description && (
                      <p className="mt-0.5 max-w-xs truncate font-mono text-2xs text-text-muted">
                        {s.description}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-text-muted">{s.project_name}</td>
                  <td className="px-4 py-3">
                    <Badge value={s.asset_class} variant="asset_class" />
                  </td>
                  <td className="px-4 py-3">
                    <Badge value={s.status} variant="status" />
                  </td>
                  <td className="mono-num px-4 py-3 text-right text-sm text-text-secondary">
                    {s.run_count}
                  </td>
                  <td className="px-4 py-3">
                    <ReliabilityBadge score={s.latest_reliability_score} />
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-text-muted">
                    {formatDate(s.latest_run_at)}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-text-muted">
                    {formatDate(s.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <StrategyCreateDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onCreated={load}
      />
    </>
  );
}
