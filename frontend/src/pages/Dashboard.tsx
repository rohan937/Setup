import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { DashboardSummary, RecentEvidenceItem, Strategy } from "@/types";
import { getDashboardSummary, getStrategies } from "@/lib/api";
import Badge from "@/components/Badge";

// ---------------------------------------------------------------------------
// Score helpers
// ---------------------------------------------------------------------------

function scoreColor(score: number | null): string {
  if (score === null) return "text-text-muted";
  if (score >= 80) return "text-green-400";
  if (score >= 60) return "text-yellow-400";
  if (score >= 40) return "text-orange-400";
  return "text-red-400";
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatShortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

// ---------------------------------------------------------------------------
// Score pillar (top strip)
// ---------------------------------------------------------------------------

function ScorePillar({
  label,
  description,
  score,
}: {
  label: string;
  description: string;
  score: number | null;
}) {
  return (
    <div className="flex flex-col gap-1 border-r border-border last:border-r-0 px-4 first:pl-0 last:pr-0 py-2">
      <p className="caption">{label}</p>
      <p className={`mono-num text-2xl font-bold ${scoreColor(score)}`}>
        {score !== null ? score.toFixed(1) : "—"}
      </p>
      <p className="font-mono text-2xs text-text-muted leading-relaxed">{description}</p>
      {score === null && (
        <p className="font-mono text-2xs text-text-muted italic">No evidence yet</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Evidence counter chip
// ---------------------------------------------------------------------------

function CountChip({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-border bg-bg-800 px-4 py-3 text-center">
      <p className="mono-num text-2xl font-semibold text-text-primary">{value}</p>
      <p className="mt-0.5 font-mono text-2xs uppercase tracking-wider text-text-muted">
        {label}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Recent evidence row
// ---------------------------------------------------------------------------

function RecentItem({ item }: { item: RecentEvidenceItem }) {
  return (
    <div className="flex items-start justify-between py-2 border-b border-border last:border-0">
      <div className="min-w-0 flex-1 pr-2">
        <p className="text-xs text-text-secondary truncate">{item.title}</p>
        {item.strategy_name && (
          <p className="mt-px font-mono text-2xs text-text-muted truncate">
            {item.strategy_name}
          </p>
        )}
        {item.status && (
          <p className="mt-px font-mono text-2xs text-text-muted">{item.status}</p>
        )}
      </div>
      <div className="flex flex-col items-end gap-0.5 shrink-0">
        {item.score !== null && (
          <span className={`mono-num font-semibold text-sm ${scoreColor(item.score)}`}>
            {item.score.toFixed(0)}
          </span>
        )}
        <span className="font-mono text-2xs text-text-muted">
          {formatShortDate(item.timestamp)}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Severity chip (for issue breakdowns)
// ---------------------------------------------------------------------------

function SevChip({ severity, count }: { severity: string; count: number }) {
  const palette: Record<string, string> = {
    critical: "bg-red-900/40 text-red-300",
    high: "bg-orange-900/40 text-orange-300",
    medium: "bg-yellow-900/40 text-yellow-200",
    low: "bg-blue-900/40 text-blue-300",
  };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 font-mono text-2xs ${palette[severity] ?? "bg-bg-600 text-text-muted"}`}
    >
      {severity} <span className="font-semibold">{count}</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getDashboardSummary(), getStrategies()])
      .then(([s, strats]) => {
        setSummary(s);
        setStrategies(strats);
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Failed to load"),
      )
      .finally(() => setLoading(false));
  }, []);

  const scores = summary?.scores ?? null;
  const counts = summary?.counts ?? null;

  return (
    <div className="space-y-7">
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                              */}
      {/* ------------------------------------------------------------------ */}
      <div>
        <p className="caption mb-1">Reliability Cockpit</p>
        <h1 className="text-xl font-semibold text-text-primary">
          Strategy Reliability Overview
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          Evidence coverage across data quality, backtest assumptions, and
          strategy activity.
        </p>
      </div>

      {error && (
        <div className="rounded border border-red-800 bg-red-900/20 px-4 py-3 font-mono text-xs text-red-300">
          {error}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Reliability score strip                                             */}
      {/* ------------------------------------------------------------------ */}
      <div className="rounded-card border border-border bg-bg-700">
        <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
          <p className="caption">Reliability Pillars</p>
          {summary && (
            <p className="font-mono text-2xs text-text-muted">
              as of {formatDate(summary.generated_at)}
            </p>
          )}
        </div>

        {loading ? (
          <div className="px-4 py-6">
            <p className="font-mono text-2xs text-text-muted">Loading…</p>
          </div>
        ) : (
          <div className="grid grid-cols-4 divide-x divide-border px-4 py-4">
            <ScorePillar
              label="Overall Reliability"
              description="Avg of available dimension scores"
              score={scores?.overall_reliability_score ?? null}
            />
            <ScorePillar
              label="Data Health"
              description="Avg snapshot health across datasets"
              score={scores?.data_health_score ?? null}
            />
            <ScorePillar
              label="Backtest Trust"
              description="Avg trust score across audits"
              score={scores?.backtest_trust_score ?? null}
            />
            <ScorePillar
              label="Strategy Activity"
              description="Based on strategy and run counts"
              score={scores?.strategy_activity_score ?? null}
            />
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Evidence counters                                                   */}
      {/* ------------------------------------------------------------------ */}
      {!loading && counts && (
        <div className="grid grid-cols-4 gap-3">
          <CountChip label="Strategies" value={counts.total_strategies} />
          <CountChip label="Total Runs" value={counts.total_runs} />
          <CountChip
            label="Dataset Snapshots"
            value={counts.total_dataset_snapshots}
          />
          <CountChip
            label="Backtest Audits"
            value={counts.total_backtest_audits}
          />
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Active strategies table                                             */}
      {/* ------------------------------------------------------------------ */}
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

        {!loading && strategies.length === 0 && (
          <div className="rounded-card border border-dashed border-border bg-bg-800 px-5 py-8 text-center">
            <p className="font-mono text-2xs text-text-muted">
              No strategies registered.
            </p>
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
                  {["Strategy", "Asset", "Status", "Runs", "Last Run"].map(
                    (h) => (
                      <th
                        key={h}
                        className="px-4 py-2 text-left font-mono text-2xs uppercase tracking-widest text-text-muted"
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {strategies.slice(0, 6).map((s, i) => (
                  <tr
                    key={s.id}
                    className={`hover:bg-bg-600 ${
                      i < Math.min(strategies.length, 6) - 1
                        ? "border-b border-border"
                        : ""
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

      {/* ------------------------------------------------------------------ */}
      {/* Data health + Backtest trust detail panels                          */}
      {/* ------------------------------------------------------------------ */}
      {!loading && counts && scores && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Data health panel */}
          <div className="rounded-card border border-border bg-bg-700">
            <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
              <p className="caption">Data Health</p>
              {scores.data_health_score !== null && (
                <span
                  className={`mono-num font-semibold text-sm ${scoreColor(scores.data_health_score)}`}
                >
                  {scores.data_health_score.toFixed(1)}
                </span>
              )}
            </div>
            <div className="p-4 space-y-3">
              {counts.total_dataset_snapshots === 0 ? (
                <p className="font-mono text-2xs text-text-muted">
                  No dataset snapshots uploaded yet.{" "}
                  <Link
                    to="/datasets"
                    className="text-accent-500 hover:text-accent-300"
                  >
                    Upload a snapshot →
                  </Link>
                </p>
              ) : (
                <>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <p className="font-mono text-2xs text-text-muted">
                        Snapshots
                      </p>
                      <p className="mono-num text-lg font-semibold text-text-primary">
                        {counts.total_dataset_snapshots}
                      </p>
                    </div>
                    <div>
                      <p className="font-mono text-2xs text-text-muted">
                        With Issues
                      </p>
                      <p className="mono-num text-lg font-semibold text-text-primary">
                        {counts.snapshots_with_issues}
                      </p>
                    </div>
                    <div>
                      <p className="font-mono text-2xs text-text-muted">
                        Lowest Score
                      </p>
                      <p
                        className={`mono-num text-lg font-semibold ${scoreColor(scores.lowest_data_health_score ?? null)}`}
                      >
                        {scores.lowest_data_health_score ?? "—"}
                      </p>
                    </div>
                  </div>

                  {Object.keys(counts.data_issues_by_severity).length > 0 && (
                    <div>
                      <p className="font-mono text-2xs text-text-muted mb-1.5">
                        Issues by severity
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(counts.data_issues_by_severity).map(
                          ([sev, cnt]) => (
                            <SevChip key={sev} severity={sev} count={cnt} />
                          ),
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Backtest trust panel */}
          <div className="rounded-card border border-border bg-bg-700">
            <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
              <p className="caption">Backtest Trust</p>
              {scores.backtest_trust_score !== null && (
                <span
                  className={`mono-num font-semibold text-sm ${scoreColor(scores.backtest_trust_score)}`}
                >
                  {scores.backtest_trust_score.toFixed(1)}
                </span>
              )}
            </div>
            <div className="p-4 space-y-3">
              {counts.total_backtest_audits === 0 ? (
                <p className="font-mono text-2xs text-text-muted">
                  No backtest audits yet.{" "}
                  <Link
                    to="/backtests"
                    className="text-accent-500 hover:text-accent-300"
                  >
                    Run an audit →
                  </Link>
                </p>
              ) : (
                <>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <p className="font-mono text-2xs text-text-muted">
                        Audits
                      </p>
                      <p className="mono-num text-lg font-semibold text-text-primary">
                        {counts.total_backtest_audits}
                      </p>
                    </div>
                    <div>
                      <p className="font-mono text-2xs text-text-muted">
                        Issues Found
                      </p>
                      <p className="mono-num text-lg font-semibold text-text-primary">
                        {counts.total_backtest_issues}
                      </p>
                    </div>
                    <div>
                      <p className="font-mono text-2xs text-text-muted">
                        Lowest Trust
                      </p>
                      <p
                        className={`mono-num text-lg font-semibold ${scoreColor(scores.lowest_backtest_trust_score ?? null)}`}
                      >
                        {scores.lowest_backtest_trust_score ?? "—"}
                      </p>
                    </div>
                  </div>

                  {Object.keys(counts.audits_by_status).length > 0 && (
                    <div>
                      <p className="font-mono text-2xs text-text-muted mb-1.5">
                        Audits by status
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(counts.audits_by_status).map(
                          ([status, cnt]) => (
                            <span
                              key={status}
                              className="inline-flex items-center gap-1 rounded px-2 py-0.5 font-mono text-2xs bg-bg-600 text-text-secondary"
                            >
                              {status}{" "}
                              <span className="font-semibold">{cnt}</span>
                            </span>
                          ),
                        )}
                      </div>
                    </div>
                  )}

                  {Object.keys(counts.backtest_issues_by_severity).length >
                    0 && (
                    <div>
                      <p className="font-mono text-2xs text-text-muted mb-1.5">
                        Issues by severity
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(
                          counts.backtest_issues_by_severity,
                        ).map(([sev, cnt]) => (
                          <SevChip key={sev} severity={sev} count={cnt} />
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Recent activity                                                     */}
      {/* ------------------------------------------------------------------ */}
      {!loading && summary && (
        <div>
          <p className="caption mb-3">Recent Activity</p>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-4">
            {/* Recent runs */}
            <div className="rounded-card border border-border bg-bg-700">
              <div className="border-b border-border px-4 py-2.5">
                <p className="caption">Recent Runs</p>
              </div>
              <div className="p-4">
                {summary.recent_runs.length === 0 ? (
                  <p className="font-mono text-2xs text-text-muted">
                    No runs yet.
                  </p>
                ) : (
                  summary.recent_runs.map((item) => (
                    <RecentItem key={item.id} item={item} />
                  ))
                )}
              </div>
            </div>

            {/* Recent snapshots */}
            <div className="rounded-card border border-border bg-bg-700">
              <div className="border-b border-border px-4 py-2.5">
                <p className="caption">Recent Snapshots</p>
              </div>
              <div className="p-4">
                {summary.recent_snapshots.length === 0 ? (
                  <p className="font-mono text-2xs text-text-muted">
                    No snapshots yet.
                  </p>
                ) : (
                  summary.recent_snapshots.map((item) => (
                    <RecentItem key={item.id} item={item} />
                  ))
                )}
              </div>
            </div>

            {/* Recent audits */}
            <div className="rounded-card border border-border bg-bg-700">
              <div className="border-b border-border px-4 py-2.5">
                <p className="caption">Recent Audits</p>
              </div>
              <div className="p-4">
                {summary.recent_audits.length === 0 ? (
                  <p className="font-mono text-2xs text-text-muted">
                    No audits yet.
                  </p>
                ) : (
                  summary.recent_audits.map((item) => (
                    <RecentItem key={item.id} item={item} />
                  ))
                )}
              </div>
            </div>

            {/* Recent timeline events */}
            <div className="rounded-card border border-border bg-bg-700">
              <div className="border-b border-border px-4 py-2.5">
                <p className="caption">Timeline</p>
              </div>
              <div className="p-4">
                {summary.recent_timeline_events.length === 0 ? (
                  <p className="font-mono text-2xs text-text-muted">
                    No events yet.
                  </p>
                ) : (
                  summary.recent_timeline_events.map((item) => (
                    <RecentItem key={item.id} item={item} />
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
