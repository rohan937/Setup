import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { DashboardAlertItem, DashboardSummary, EvidenceCoverageSummary, PortfolioOverview, ProjectHealth, RecentEvidenceItem, Strategy, StrategyHealthListResponse, SystemHealthResponse } from "@/types";
import { getDashboardSummary, getEvidenceCoverage, getPortfolioOverview, getProjectsHealth, getStrategies, getStrategiesHealth, getSystemHealth } from "@/lib/api";
import Badge from "@/components/Badge";

// ---------------------------------------------------------------------------
// Score helpers
// ---------------------------------------------------------------------------

function scoreColor(score: number | null): string {
  if (score === null) return "text-text-muted";
  if (score >= 80) return "text-fidelity-high";
  if (score >= 60) return "text-fidelity-medium";
  if (score >= 40) return "text-fidelity-low";
  return "text-severity-critical";
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
    <div className="flex flex-col gap-1.5 border-r border-border last:border-r-0 px-5 first:pl-0 last:pr-0 py-3">
      <p className="caption">{label}</p>
      <p className={`mono-num text-2xl font-bold leading-none ${scoreColor(score)}`}>
        {score !== null ? score.toFixed(1) : "—"}
      </p>
      <p className="text-xs text-text-muted leading-relaxed">{description}</p>
      {score === null && (
        <p className="text-xs text-text-muted italic">No evidence yet</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Evidence counter chip
// ---------------------------------------------------------------------------

function CountChip({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-card border border-border bg-bg-800 px-4 py-4 text-center">
      <p className="mono-num text-2xl font-semibold text-text-primary">{value}</p>
      <p className="mt-1 caption">{label}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Recent evidence row
// ---------------------------------------------------------------------------

const STATUS_CHIP: Record<string, string> = {
  pass: "bg-teal-900/30 text-teal-300 border-teal-700/30",
  passed: "bg-teal-900/30 text-teal-300 border-teal-700/30",
  fail: "bg-red-900/30 text-severity-high border-red-800/30",
  failed: "bg-red-900/30 text-severity-high border-red-800/30",
  warning: "bg-yellow-900/30 text-fidelity-medium border-yellow-800/30",
  review: "bg-orange-900/30 text-fidelity-low border-orange-800/30",
  pending: "bg-bg-600 text-text-muted border-border",
  running: "bg-accent-600/10 text-accent-300 border-accent-600/30",
};

function RecentItem({ item }: { item: RecentEvidenceItem }) {
  const statusKey = (item.status ?? "").toLowerCase();
  const statusChip = STATUS_CHIP[statusKey];
  return (
    <div className="flex items-start justify-between py-2.5 border-b border-border last:border-0">
      <div className="min-w-0 flex-1 pr-3">
        <p className="text-sm text-text-secondary leading-snug truncate">{item.title}</p>
        {item.strategy_name && (
          <p className="mt-0.5 text-xs text-text-muted truncate">
            {item.strategy_name}
          </p>
        )}
        {item.status && (
          statusChip ? (
            <span
              className={`mt-1 inline-flex items-center rounded border px-1.5 py-px text-xs font-medium ${statusChip}`}
            >
              {item.status}
            </span>
          ) : (
            <p className="mt-0.5 text-xs text-text-muted">{item.status}</p>
          )
        )}
      </div>
      <div className="flex flex-col items-end gap-0.5 shrink-0">
        {item.score !== null && (
          <span className={`mono-num font-semibold text-sm ${scoreColor(item.score)}`}>
            {item.score.toFixed(0)}
          </span>
        )}
        <span className="text-xs text-text-muted">
          {formatShortDate(item.timestamp)}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Severity chip (for issue breakdowns)
// ---------------------------------------------------------------------------

const SEV_CHIP: Record<string, string> = {
  critical: "bg-red-900/30 text-severity-critical border-red-800/30",
  high: "bg-orange-900/30 text-severity-high border-orange-800/30",
  medium: "bg-yellow-900/30 text-severity-medium border-yellow-800/30",
  low: "bg-blue-900/30 text-severity-low border-blue-800/30",
};

function SevChip({ severity, count }: { severity: string; count: number }) {
  const cls = SEV_CHIP[severity] ?? "bg-bg-600 text-text-muted border-border";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs ${cls}`}
    >
      <span className="capitalize">{severity}</span>
      <span className="font-semibold mono-num">{count}</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Alert signal row (for the Reliability Signals panel)
// ---------------------------------------------------------------------------

const SEVERITY_DOT_MAP: Record<string, string> = {
  low: "bg-severity-low",
  medium: "bg-severity-medium",
  high: "bg-severity-high",
  critical: "bg-severity-critical",
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
    <div className="flex items-start gap-3 py-2.5 border-b border-border last:border-0">
      <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${dot}`} />
      <div className="min-w-0 flex-1">
        <p className="text-sm text-text-secondary leading-snug truncate">{alert.title}</p>
        <div className="mt-0.5 flex gap-2.5">
          <span className="text-xs text-text-muted">
            {RULE_LABEL_MAP[alert.rule_type] ?? alert.rule_type.replace(/_/g, " ")}
          </span>
          <span className="text-xs text-text-muted capitalize">{alert.status}</span>
        </div>
      </div>
      <span className="shrink-0 text-xs text-text-muted whitespace-nowrap">
        {formatShortDate(alert.triggered_at)}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared section-header row
// ---------------------------------------------------------------------------

function SectionHeader({
  title,
  linkTo,
  linkLabel,
}: {
  title: string;
  linkTo?: string;
  linkLabel?: string;
}) {
  return (
    <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
      <h2 className="text-sm font-semibold text-text-primary">{title}</h2>
      {linkTo && linkLabel && (
        <Link to={linkTo} className="text-xs text-accent-500 hover:text-accent-300">
          {linkLabel}
        </Link>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

type HealthStatusCounts = {
  healthy: number;
  watch: number;
  review: number;
  critical: number;
  insufficient_evidence: number;
};

// Reliability status chip palette (desaturated)
const RELIABILITY_CHIP: Record<string, string> = {
  excellent: "bg-teal-900/30 text-teal-300 border-teal-700/30",
  good: "bg-blue-900/30 text-accent-300 border-accent-600/30",
  review: "bg-yellow-900/30 text-fidelity-medium border-yellow-800/30",
  weak: "bg-red-900/30 text-severity-high border-red-800/30",
  insufficient_evidence: "bg-bg-600 text-text-muted border-border",
};

// Strategy / project health chip palette (desaturated)
const HEALTH_CHIP: Record<string, string> = {
  healthy: "bg-teal-900/30 text-teal-300 border-teal-700/30",
  watch: "bg-yellow-900/30 text-fidelity-medium border-yellow-800/30",
  review: "bg-orange-900/30 text-fidelity-low border-orange-800/30",
  critical: "bg-red-900/30 text-severity-critical border-red-800/30",
  insufficient_evidence: "bg-bg-600 text-text-muted border-border",
};

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [coverageSummary, setCoverageSummary] = useState<EvidenceCoverageSummary | null>(null);
  const [healthSummary, setHealthSummary] = useState<HealthStatusCounts | null>(null);
  const [projectsHealth, setProjectsHealth] = useState<ProjectHealth[]>([]);
  const [portfolioOverview, setPortfolioOverview] = useState<PortfolioOverview | null>(null);
  const [systemHealth, setSystemHealth] = useState<SystemHealthResponse | null>(null);
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
    // M27: load health summary in parallel (best-effort)
    getStrategiesHealth({ limit: 500 })
      .then((r: StrategyHealthListResponse) => {
        const statusCounts: HealthStatusCounts = {
          healthy: 0, watch: 0, review: 0, critical: 0, insufficient_evidence: 0,
        };
        r.items.forEach((h) => {
          if (h.health_status in statusCounts) {
            (statusCounts as Record<string, number>)[h.health_status]++;
          }
        });
        setHealthSummary(statusCounts);
      })
      .catch(() => {});
    // M28: load project health in parallel (best-effort)
    getProjectsHealth({ limit: 50 })
      .then((r) => setProjectsHealth(r.items))
      .catch(() => {});
    // M32: load portfolio overview in parallel (best-effort)
    getPortfolioOverview({ limit_per_section: 3 })
      .then(setPortfolioOverview)
      .catch(() => {});
    // M45: load system health in parallel (best-effort)
    getSystemHealth().then(setSystemHealth).catch(() => {});
  }, []);

  const scores = summary?.scores ?? null;
  const counts = summary?.counts ?? null;

  return (
    <div className="space-y-6">
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
        <div className="rounded-card border border-red-800/60 bg-red-900/20 px-4 py-3 text-sm text-severity-high">
          {error}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Reliability score strip                                             */}
      {/* ------------------------------------------------------------------ */}
      <div className="rounded-card border border-border bg-bg-700 shadow-card">
        <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-text-primary">Reliability Pillars</h2>
          {summary && (
            <span className="text-xs text-text-muted">
              as of {formatDate(summary.generated_at)}
            </span>
          )}
        </div>

        {loading ? (
          <div className="px-4 py-6">
            <p className="text-xs text-text-muted">Loading…</p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-5 divide-x divide-border px-5 py-4">
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

            {/* Reliability status breakdown */}
            {scores && scores.strategies_by_reliability_status && Object.keys(scores.strategies_by_reliability_status).length > 0 && (
              <div className="border-t border-border px-4 py-2.5 flex flex-wrap gap-2 items-center">
                <span className="text-xs text-text-muted mr-1">By reliability:</span>
                {Object.entries(scores.strategies_by_reliability_status).map(([status, count]) => (
                  <span
                    key={status}
                    className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs ${RELIABILITY_CHIP[status] ?? RELIABILITY_CHIP.insufficient_evidence}`}
                  >
                    <span className="capitalize">{status.replace(/_/g, " ")}</span>
                    <span className="font-semibold mono-num">{count}</span>
                  </span>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Evidence counters                                                   */}
      {/* ------------------------------------------------------------------ */}
      {!loading && counts && (
        <div className="grid grid-cols-4 gap-3">
          <CountChip label="Strategies" value={counts.total_strategies} />
          <CountChip label="Total Runs" value={counts.total_runs} />
          <CountChip label="Dataset Snapshots" value={counts.total_dataset_snapshots} />
          <CountChip label="Backtest Audits" value={counts.total_backtest_audits} />
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Evidence Coverage quick card (M21)                                 */}
      {/* ------------------------------------------------------------------ */}
      {!loading && coverageSummary && coverageSummary.strategy_count > 0 && (
        <div className="rounded-card border border-border bg-bg-700 shadow-card">
          <SectionHeader
            title="Instrumentation Coverage"
            linkTo="/evidence/coverage"
            linkLabel="Full matrix →"
          />
          <div className="grid grid-cols-2 divide-x divide-border sm:grid-cols-4">
            {[
              {
                label: "Avg Coverage",
                value: `${coverageSummary.average_coverage_score.toFixed(1)}`,
                color:
                  coverageSummary.average_coverage_score >= 80
                    ? "text-fidelity-high"
                    : coverageSummary.average_coverage_score >= 50
                    ? "text-fidelity-medium"
                    : "text-fidelity-low",
              },
              {
                label: "Complete Cells",
                value: coverageSummary.complete_cell_count,
                color: "text-fidelity-high",
              },
              {
                label: "Missing Cells",
                value: coverageSummary.missing_cell_count,
                color:
                  coverageSummary.missing_cell_count > 0 ? "text-text-muted" : "text-fidelity-high",
              },
              {
                label: "Review Cells",
                value: coverageSummary.review_cell_count,
                color:
                  coverageSummary.review_cell_count > 0 ? "text-fidelity-low" : "text-fidelity-high",
              },
            ].map(({ label, value, color }) => (
              <div key={label} className="px-4 py-3.5 text-center">
                <p className="caption">{label}</p>
                <p className={`mono-num mt-1.5 text-xl font-bold ${color}`}>{value}</p>
              </div>
            ))}
          </div>
          {coverageSummary.most_common_missing_evidence.length > 0 && (
            <div className="border-t border-border px-4 py-2.5 flex flex-wrap gap-x-2 gap-y-1 items-center">
              <span className="text-xs text-text-muted">Most missing:</span>
              {coverageSummary.most_common_missing_evidence.slice(0, 4).map((label) => (
                <span
                  key={label}
                  className="text-xs text-text-muted bg-bg-800 border border-border rounded-chip px-1.5 py-0.5"
                >
                  {label}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Strategy Health summary (M27)                                      */}
      {/* ------------------------------------------------------------------ */}
      {!loading && healthSummary && strategies.length > 0 && (
        <div className="rounded-card border border-border bg-bg-700 shadow-card">
          <SectionHeader
            title="Strategy Health"
            linkTo="/strategies"
            linkLabel="All strategies →"
          />
          <div className="px-4 py-3 flex flex-wrap gap-2">
            {(
              [
                { key: "healthy",               label: "Healthy" },
                { key: "watch",                 label: "Watch" },
                { key: "review",                label: "Review" },
                { key: "critical",              label: "Critical" },
                { key: "insufficient_evidence", label: "Insufficient Evidence" },
              ] as const
            ).map(({ key, label }) => (
              <span
                key={key}
                className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs ${HEALTH_CHIP[key]}`}
              >
                {label}
                <span className="font-semibold mono-num">{healthSummary[key]}</span>
              </span>
            ))}
          </div>
          {(healthSummary.critical + healthSummary.review) > 0 && (
            <div className="border-t border-border px-4 py-2">
              <span className="text-xs text-fidelity-low">
                {healthSummary.critical + healthSummary.review}{" "}
                {healthSummary.critical + healthSummary.review === 1
                  ? "strategy requires"
                  : "strategies require"}{" "}
                attention
              </span>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Project Health summary (M28)                                       */}
      {/* ------------------------------------------------------------------ */}
      {!loading && projectsHealth.length > 0 && (
        <div className="rounded-card border border-border bg-bg-700 shadow-card">
          <SectionHeader
            title="Project Health"
            linkTo="/strategies"
            linkLabel="All strategies →"
          />
          <div className="divide-y divide-border">
            {projectsHealth.map((p) => {
              const chip = HEALTH_CHIP[p.health_status] ?? HEALTH_CHIP.insufficient_evidence;
              return (
                <div key={p.project_id} className="flex items-center gap-3 px-4 py-2.5">
                  <span className="min-w-0 flex-1 text-sm text-text-primary truncate">
                    {p.project_name}
                  </span>
                  <span
                    className={`shrink-0 inline-flex items-center rounded border px-2 py-0.5 text-xs capitalize ${chip}`}
                  >
                    {p.health_status.replace(/_/g, " ")}
                  </span>
                  <span className="shrink-0 text-xs text-text-muted">
                    {p.strategy_count} {p.strategy_count === 1 ? "strategy" : "strategies"}
                  </span>
                  {p.health_score !== null && (
                    <span className={`shrink-0 mono-num font-semibold text-sm ${scoreColor(p.health_score)}`}>
                      {p.health_score.toFixed(1)}
                    </span>
                  )}
                  {p.primary_concern && (
                    <span className="hidden sm:block shrink-0 max-w-[180px] truncate text-xs text-text-muted">
                      {p.primary_concern}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Portfolio Overview panel (M32)                                     */}
      {/* ------------------------------------------------------------------ */}
      {!loading && portfolioOverview && (
        <div className="rounded-card border border-border bg-bg-700 shadow-card">
          <SectionHeader
            title="Portfolio Overview"
            linkTo="/portfolio"
            linkLabel="Full view →"
          />
          <div className="grid grid-cols-4 divide-x divide-border">
            <div className="px-4 py-3.5 text-center">
              <p className="caption">Strategies</p>
              <p className="mono-num mt-1.5 text-xl font-bold text-text-primary">
                {portfolioOverview.active_strategy_count}
              </p>
            </div>
            <div className="px-4 py-3.5 text-center">
              <p className="caption">Review</p>
              <p
                className={`mono-num mt-1.5 text-xl font-bold ${
                  portfolioOverview.top_review_strategies.length > 0
                    ? "text-fidelity-low"
                    : "text-text-primary"
                }`}
              >
                {portfolioOverview.top_review_strategies.length}
              </p>
            </div>
            <div className="px-4 py-3.5 text-center">
              <p className="caption">Avg Health</p>
              <p
                className={`mono-num mt-1.5 text-xl font-bold ${
                  portfolioOverview.average_health_score === null
                    ? "text-text-muted"
                    : portfolioOverview.average_health_score >= 80
                    ? "text-fidelity-high"
                    : portfolioOverview.average_health_score >= 60
                    ? "text-fidelity-medium"
                    : "text-severity-critical"
                }`}
              >
                {portfolioOverview.average_health_score !== null
                  ? portfolioOverview.average_health_score.toFixed(1)
                  : "—"}
              </p>
            </div>
            <div className="px-4 py-3.5 text-center">
              <p className="caption">Avg Coverage</p>
              <p
                className={`mono-num mt-1.5 text-xl font-bold ${
                  portfolioOverview.average_evidence_coverage_score === null
                    ? "text-text-muted"
                    : portfolioOverview.average_evidence_coverage_score >= 80
                    ? "text-fidelity-high"
                    : portfolioOverview.average_evidence_coverage_score >= 60
                    ? "text-fidelity-medium"
                    : "text-severity-critical"
                }`}
              >
                {portfolioOverview.average_evidence_coverage_score !== null
                  ? portfolioOverview.average_evidence_coverage_score.toFixed(1)
                  : "—"}
              </p>
            </div>
          </div>
          <div className="border-t border-border px-4 py-2">
            <Link
              to="/portfolio"
              className="text-xs text-accent-500 hover:text-accent-300"
            >
              View full portfolio overview →
            </Link>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* System Health card (M45)                                           */}
      {/* ------------------------------------------------------------------ */}
      {!loading && systemHealth && (
        <div className="rounded-card border border-border bg-bg-700 shadow-card">
          <SectionHeader
            title="System Health"
            linkTo="/admin/system-health"
            linkLabel="Ops dashboard →"
          />
          <div className="grid grid-cols-4 divide-x divide-border">
            <div className="px-4 py-3.5 text-center">
              <p className="caption">Score</p>
              <p className={`mono-num mt-1.5 text-xl font-bold ${scoreColor(systemHealth.system_score)}`}>
                {systemHealth.system_score !== null ? systemHealth.system_score.toFixed(1) : "—"}
              </p>
            </div>
            <div className="px-4 py-3.5 text-center">
              <p className="caption">Strategies</p>
              <p className="mono-num mt-1.5 text-xl font-bold text-text-primary">
                {systemHealth.entity_counts.active_strategies}
              </p>
            </div>
            <div className="px-4 py-3.5 text-center">
              <p className="caption">Ingestion</p>
              <p className={`mono-num mt-1.5 text-sm font-semibold capitalize ${
                systemHealth.ingestion_health.ingestion_status === "healthy" ? "text-fidelity-high" :
                systemHealth.ingestion_health.ingestion_status === "watch" ? "text-fidelity-medium" :
                systemHealth.ingestion_health.ingestion_status === "degraded" ? "text-severity-critical" :
                "text-text-muted"
              }`}>
                {systemHealth.ingestion_health.ingestion_status.replace(/_/g, " ")}
              </p>
            </div>
            <div className="px-4 py-3.5 text-center">
              <p className="caption">Activity</p>
              <p className={`mono-num mt-1.5 text-sm font-semibold capitalize ${
                systemHealth.evidence_activity.activity_status === "healthy" ? "text-fidelity-high" :
                systemHealth.evidence_activity.activity_status === "watch" ? "text-fidelity-medium" :
                systemHealth.evidence_activity.activity_status === "degraded" ? "text-severity-critical" :
                "text-text-muted"
              }`}>
                {systemHealth.evidence_activity.activity_status.replace(/_/g, " ")}
              </p>
            </div>
          </div>
          {(systemHealth.system_status === "degraded" || systemHealth.system_status === "review") && (
            <div className="border-t border-border px-4 py-2">
              <span className="text-xs text-fidelity-low capitalize">
                System status: {systemHealth.system_status.replace(/_/g, " ")} — review ops dashboard
              </span>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Active strategies table                                             */}
      {/* ------------------------------------------------------------------ */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-text-primary">Active Strategies</h2>
          <Link
            to="/strategies"
            className="text-xs text-accent-500 hover:text-accent-300"
          >
            All strategies →
          </Link>
        </div>

        {!loading && strategies.length === 0 && (
          <div className="rounded-card border border-dashed border-border bg-bg-800 px-5 py-10 text-center">
            <p className="text-sm text-text-muted">No strategies registered yet.</p>
            <Link
              to="/strategies"
              className="mt-2 inline-block text-xs text-accent-500 hover:text-accent-300"
            >
              Register a strategy →
            </Link>
          </div>
        )}

        {!loading && strategies.length > 0 && (
          <div className="overflow-hidden rounded-card border border-border shadow-card">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-bg-800">
                  {["Strategy", "Asset", "Status", "Runs", "Last Run"].map(
                    (h) => (
                      <th
                        key={h}
                        className="px-4 py-2.5 text-left text-xs font-medium tracking-eyebrow text-text-muted"
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
                    className={`hover:bg-bg-600 transition-colors ${
                      i < Math.min(strategies.length, 6) - 1
                        ? "border-b border-border"
                        : ""
                    }`}
                  >
                    <td className="px-4 py-3">
                      <Link
                        to={`/strategies/${s.id}`}
                        className="text-sm font-medium text-text-primary hover:text-accent-300 transition-colors"
                      >
                        {s.name}
                      </Link>
                      <p className="mt-0.5 text-xs text-text-muted">
                        {s.project_name}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <Badge value={s.asset_class} variant="asset_class" />
                    </td>
                    <td className="px-4 py-3">
                      <Badge value={s.status} variant="status" />
                    </td>
                    <td className="mono-num px-4 py-3 text-sm text-text-secondary">
                      {s.run_count}
                    </td>
                    <td className="px-4 py-3 text-xs text-text-muted">
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
        <div className="rounded-card border border-border bg-bg-700 shadow-card">
          <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h2 className="text-sm font-semibold text-text-primary">Reliability Signals</h2>
              {counts.open_alert_count > 0 && (
                <span className="inline-flex items-center gap-1.5 rounded border border-red-800/40 bg-red-900/20 px-2 py-0.5 text-xs text-severity-high">
                  <span className="mono-num font-semibold">{counts.open_alert_count}</span> open
                </span>
              )}
              {counts.high_critical_alert_count > 0 && (
                <span className="inline-flex items-center gap-1.5 rounded border border-orange-800/40 bg-orange-900/20 px-2 py-0.5 text-xs text-severity-high">
                  <span className="mono-num font-semibold">{counts.high_critical_alert_count}</span> high/critical
                </span>
              )}
            </div>
            <Link
              to="/alerts"
              className="text-xs text-accent-500 hover:text-accent-300"
            >
              All alerts →
            </Link>
          </div>
          <div className="px-4 py-1">
            {!summary || summary.recent_alerts.length === 0 ? (
              <p className="py-4 text-sm text-text-muted">
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
          <div className="rounded-card border border-border bg-bg-700 shadow-card">
            <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-primary">Data Health</h2>
              {scores.data_health_score !== null && (
                <span className={`mono-num font-semibold text-sm ${scoreColor(scores.data_health_score)}`}>
                  {scores.data_health_score.toFixed(1)}
                </span>
              )}
            </div>
            <div className="p-4 space-y-4">
              {counts.total_dataset_snapshots === 0 ? (
                <p className="text-sm text-text-muted">
                  No dataset snapshots uploaded yet.{" "}
                  <Link to="/datasets" className="text-accent-500 hover:text-accent-300">
                    Upload a snapshot →
                  </Link>
                </p>
              ) : (
                <>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <p className="caption">Snapshots</p>
                      <p className="mono-num mt-1 text-lg font-semibold text-text-primary">
                        {counts.total_dataset_snapshots}
                      </p>
                    </div>
                    <div>
                      <p className="caption">With Issues</p>
                      <p className="mono-num mt-1 text-lg font-semibold text-text-primary">
                        {counts.snapshots_with_issues}
                      </p>
                    </div>
                    <div>
                      <p className="caption">Lowest Score</p>
                      <p className={`mono-num mt-1 text-lg font-semibold ${scoreColor(scores.lowest_data_health_score ?? null)}`}>
                        {scores.lowest_data_health_score ?? "—"}
                      </p>
                    </div>
                  </div>

                  {Object.keys(counts.data_issues_by_severity).length > 0 && (
                    <div>
                      <p className="caption mb-2">Issues by severity</p>
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
          <div className="rounded-card border border-border bg-bg-700 shadow-card">
            <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-primary">Backtest Trust</h2>
              {scores.backtest_trust_score !== null && (
                <span className={`mono-num font-semibold text-sm ${scoreColor(scores.backtest_trust_score)}`}>
                  {scores.backtest_trust_score.toFixed(1)}
                </span>
              )}
            </div>
            <div className="p-4 space-y-4">
              {counts.total_backtest_audits === 0 ? (
                <p className="text-sm text-text-muted">
                  No backtest audits yet.{" "}
                  <Link to="/backtests" className="text-accent-500 hover:text-accent-300">
                    Run an audit →
                  </Link>
                </p>
              ) : (
                <>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <p className="caption">Audits</p>
                      <p className="mono-num mt-1 text-lg font-semibold text-text-primary">
                        {counts.total_backtest_audits}
                      </p>
                    </div>
                    <div>
                      <p className="caption">Issues Found</p>
                      <p className="mono-num mt-1 text-lg font-semibold text-text-primary">
                        {counts.total_backtest_issues}
                      </p>
                    </div>
                    <div>
                      <p className="caption">Lowest Trust</p>
                      <p className={`mono-num mt-1 text-lg font-semibold ${scoreColor(scores.lowest_backtest_trust_score ?? null)}`}>
                        {scores.lowest_backtest_trust_score ?? "—"}
                      </p>
                    </div>
                  </div>

                  {Object.keys(counts.audits_by_status).length > 0 && (
                    <div>
                      <p className="caption mb-2">Audits by status</p>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(counts.audits_by_status).map(
                          ([status, cnt]) => (
                            <span
                              key={status}
                              className="inline-flex items-center gap-1.5 rounded border border-border px-2 py-0.5 text-xs bg-bg-600 text-text-secondary capitalize"
                            >
                              {status}
                              <span className="font-semibold mono-num">{cnt}</span>
                            </span>
                          ),
                        )}
                      </div>
                    </div>
                  )}

                  {Object.keys(counts.backtest_issues_by_severity).length > 0 && (
                    <div>
                      <p className="caption mb-2">Issues by severity</p>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(counts.backtest_issues_by_severity).map(
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
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Recent activity                                                     */}
      {/* ------------------------------------------------------------------ */}
      {!loading && summary && (
        <div>
          <h2 className="text-sm font-semibold text-text-primary mb-3">Recent Activity</h2>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-4">
            {/* Recent runs */}
            <div className="rounded-card border border-border bg-bg-700 shadow-card">
              <SectionHeader title="Recent Runs" />
              <div className="px-4 py-1">
                {summary.recent_runs.length === 0 ? (
                  <p className="py-4 text-sm text-text-muted">No runs yet.</p>
                ) : (
                  summary.recent_runs.map((item) => (
                    <RecentItem key={item.id} item={item} />
                  ))
                )}
              </div>
            </div>

            {/* Recent snapshots */}
            <div className="rounded-card border border-border bg-bg-700 shadow-card">
              <SectionHeader title="Recent Snapshots" />
              <div className="px-4 py-1">
                {summary.recent_snapshots.length === 0 ? (
                  <p className="py-4 text-sm text-text-muted">No snapshots yet.</p>
                ) : (
                  summary.recent_snapshots.map((item) => (
                    <RecentItem key={item.id} item={item} />
                  ))
                )}
              </div>
            </div>

            {/* Recent audits */}
            <div className="rounded-card border border-border bg-bg-700 shadow-card">
              <SectionHeader title="Recent Audits" />
              <div className="px-4 py-1">
                {summary.recent_audits.length === 0 ? (
                  <p className="py-4 text-sm text-text-muted">No audits yet.</p>
                ) : (
                  summary.recent_audits.map((item) => (
                    <RecentItem key={item.id} item={item} />
                  ))
                )}
              </div>
            </div>

            {/* Recent timeline events */}
            <div className="rounded-card border border-border bg-bg-700 shadow-card">
              <SectionHeader title="Timeline" />
              <div className="px-4 py-1">
                {summary.recent_timeline_events.length === 0 ? (
                  <p className="py-4 text-sm text-text-muted">No events yet.</p>
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
