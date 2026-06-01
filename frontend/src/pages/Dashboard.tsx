import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { DashboardAlertItem, DashboardSummary, EvidenceCoverageSummary, RecentEvidenceItem, Strategy } from "@/types";
import { getDashboardSummary, getEvidenceCoverage, getStrategies } from "@/lib/api";
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
// Alert signal row (for the Reliability Signals panel)
// ---------------------------------------------------------------------------

const SEVERITY_DOT_MAP: Record<string, string> = {
  low: "bg-blue-400",
  medium: "bg-yellow-400",
  high: "bg-orange-400",
  critical: "bg-red-500",
};

const RULE_LABEL_MAP: Record<string, string> = {
  data_health_below_threshold: "Data Health",
  backtest_trust_below_threshold: "Backtest Trust",
  data_quality_issue_high_or_critical: "Data Quality",
  backtest_issue_high_or_critical: "Backtest Issue",
  strategy_run_missing_dataset_evidence: "Missing Evidence",
};

function AlertSignalRow({ alert }: { alert: DashboardAlertItem }) {
  const dot = SEVERITY_DOT_MAP[alert.severity] ?? "bg-bg-600";
  return (
    <div className="flex items-start gap-2.5 py-2 border-b border-border last:border-0">
      <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${dot}`} />
      <div className="min-w-0 flex-1">
        <p className="text-xs text-text-secondary leading-snug truncate">{alert.title}</p>
        <div className="mt-0.5 flex gap-2">
          <span className="font-mono text-2xs text-text-muted">
            {RULE_LABEL_MAP[alert.rule_type] ?? alert.rule_type.replace(/_/g, " ")}
          </span>
          <span className="font-mono text-2xs text-text-muted">{alert.status}</span>
        </div>
      </div>
      <span className="shrink-0 font-mono text-2xs text-text-muted whitespace-nowrap">
        {formatShortDate(alert.triggered_at)}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [coverageSummary, setCoverageSummary] = useState<EvidenceCoverageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      getDashboardSummary(),
      getStrategies(),
      getEvidenceCoverage({ limit: 1 }),
    ])
      .then(([s, strats, cov]) => {
        setSummary(s);
        setStrategies(strats);
        setCoverageSummary(cov.summary);
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
          <>
            <div className="grid grid-cols-5 divide-x divide-border px-4 py-4">
              <ScorePillar
                label="Overall Reliability"
                description="Avg of available dimension scores"
                score={scores?.overall_reliability_score ?? null}
              />
              <ScorePillar
                label="Avg Reliability"
                description="Avg of latest per-strategy scores"
                score={scores?.average_strategy_reliability_score ?? null}
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

            {/* M18: Reliability status breakdown chips */}
            {scores && scores.strategies_by_reliability_status && Object.keys(scores.strategies_by_reliability_status).length > 0 && (
              <div className="border-t border-border px-4 py-2.5 flex flex-wrap gap-2">
                <p className="font-mono text-2xs text-text-muted mr-2 self-center">Reliability Status:</p>
                {Object.entries(scores.strategies_by_reliability_status).map(([status, count]) => {
                  const cls: Record<string, string> = {
                    excellent: "bg-cyan-900/40 text-cyan-300 border-cyan-700/40",
                    good: "bg-teal-900/40 text-teal-300 border-teal-700/40",
                    review: "bg-yellow-900/40 text-yellow-200 border-yellow-700/40",
                    weak: "bg-red-900/40 text-red-300 border-red-700/40",
                    insufficient_evidence: "bg-bg-600 text-text-muted border-border",
                  };
                  return (
                    <span
                      key={status}
                      className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 font-mono text-2xs ${cls[status] ?? cls.insufficient_evidence}`}
                    >
                      {status.replace("_", " ")} <span className="font-bold">{count}</span>
                    </span>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Evidence Coverage quick card (M21)                                 */}
      {/* ------------------------------------------------------------------ */}
      {!loading && coverageSummary && coverageSummary.strategy_count > 0 && (
        <div className="rounded-card border border-border bg-bg-700">
          <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
            <p className="caption">Instrumentation Coverage</p>
            <Link
              to="/evidence/coverage"
              className="font-mono text-2xs text-accent-500 hover:text-accent-300"
            >
              full matrix →
            </Link>
          </div>
          <div className="grid grid-cols-2 divide-x divide-border sm:grid-cols-4 px-0 py-0">
            {[
              {
                label: "Avg Coverage",
                value: `${coverageSummary.average_coverage_score.toFixed(1)}`,
                color:
                  coverageSummary.average_coverage_score >= 80
                    ? "text-teal-400"
                    : coverageSummary.average_coverage_score >= 50
                    ? "text-yellow-400"
                    : "text-orange-400",
              },
              {
                label: "Complete Cells",
                value: coverageSummary.complete_cell_count,
                color: "text-teal-400",
              },
              {
                label: "Missing Cells",
                value: coverageSummary.missing_cell_count,
                color:
                  coverageSummary.missing_cell_count > 0 ? "text-text-muted" : "text-teal-400",
              },
              {
                label: "Review Cells",
                value: coverageSummary.review_cell_count,
                color:
                  coverageSummary.review_cell_count > 0 ? "text-orange-400" : "text-teal-400",
              },
            ].map(({ label, value, color }) => (
              <div key={label} className="px-4 py-3 text-center">
                <p className="font-mono text-2xs text-text-muted uppercase tracking-wider">
                  {label}
                </p>
                <p className={`mono-num mt-1 text-xl font-bold ${color}`}>{value}</p>
              </div>
            ))}
          </div>
          {coverageSummary.most_common_missing_evidence.length > 0 && (
            <div className="border-t border-border px-4 py-2 flex flex-wrap gap-x-3 gap-y-1">
              <p className="font-mono text-2xs text-text-muted self-center">
                Most missing:
              </p>
              {coverageSummary.most_common_missing_evidence.slice(0, 4).map((label) => (
                <span
                  key={label}
                  className="font-mono text-2xs text-text-muted bg-bg-800 border border-border rounded px-1.5 py-0.5"
                >
                  {label}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

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
      {/* Reliability Signals (M11 alerts)                                   */}
      {/* ------------------------------------------------------------------ */}
      {!loading && counts && (
        <div className="rounded-card border border-border bg-bg-700">
          <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <p className="caption">Reliability Signals</p>
              {counts.open_alert_count > 0 && (
                <span className="inline-flex items-center gap-1 rounded border border-red-700/40 bg-red-900/30 px-2 py-0.5 font-mono text-2xs text-red-300">
                  {counts.open_alert_count} open
                </span>
              )}
              {counts.high_critical_alert_count > 0 && (
                <span className="inline-flex items-center gap-1 rounded border border-orange-700/40 bg-orange-900/30 px-2 py-0.5 font-mono text-2xs text-orange-300">
                  {counts.high_critical_alert_count} high/critical
                </span>
              )}
            </div>
            <Link
              to="/alerts"
              className="font-mono text-2xs text-accent-500 hover:text-accent-300"
            >
              all alerts →
            </Link>
          </div>
          <div className="px-4 py-2">
            {!summary || summary.recent_alerts.length === 0 ? (
              <p className="py-4 font-mono text-2xs text-text-muted">
                No alerts yet.{" "}
                <Link to="/alerts" className="text-accent-500 hover:text-accent-300">
                  Run an alert check →
                </Link>
              </p>
            ) : (
              summary.recent_alerts.map((alert) => (
                <AlertSignalRow key={alert.id} alert={alert} />
              ))
            )}
          </div>
        </div>
      )}

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
