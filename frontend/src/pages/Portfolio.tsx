/**
 * Portfolio Overview (M32)
 *
 * Evidence state across all active strategies.
 * Route: /portfolio
 *
 * Language policy:
 *   Use: "Portfolio Overview", "Evidence State", "Health Status",
 *        "Coverage Score", "Review Required", "Deteriorating Trends"
 *   Avoid: AI recommendations, investment advice, alpha language
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { PortfolioOverview, PortfolioStrategyItem } from "@/types";
import { getPortfolioOverview, getStrategyLifecycle } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import Badge from "@/components/Badge";
import EmptyState from "@/components/EmptyState";

// M76: lazy, fail-safe lifecycle stage chip for a single strategy row.
function PortfolioStageChip({ strategyId }: { strategyId: string }) {
  const [stage, setStage] = useState<{ label: string; blocked: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    getStrategyLifecycle(strategyId)
      .then((lc) => {
        if (!cancelled) setStage({ label: lc.current_stage_label, blocked: lc.blocked });
      })
      .catch(() => {
        if (!cancelled) setStage(null);
      });
    return () => {
      cancelled = true;
    };
  }, [strategyId]);

  if (!stage) return <span className="text-text-muted">—</span>;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-chip border px-2 py-0.5 text-2xs ${
        stage.blocked
          ? "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium"
          : "border-border-strong bg-bg-800 text-text-secondary"
      }`}
    >
      {stage.blocked && <span className="h-1.5 w-1.5 rounded-full bg-fidelity-medium" />}
      {stage.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function scoreColor(v: number | null): string {
  if (v === null) return "text-text-muted";
  if (v >= 80) return "text-teal-400";
  if (v >= 60) return "text-yellow-400";
  return "text-red-400";
}

// Calmer, desaturated status palette
const HEALTH_STATUS_CHIP: Record<string, string> = {
  healthy: "bg-teal-950/60 text-teal-300 border-teal-800/50",
  watch: "bg-yellow-950/60 text-yellow-300 border-yellow-800/50",
  review: "bg-orange-950/60 text-orange-300 border-orange-800/50",
  critical: "bg-red-950/60 text-red-300 border-red-800/50",
  insufficient_evidence: "bg-bg-700 text-text-muted border-border",
};

function healthChipClass(status: string): string {
  return HEALTH_STATUS_CHIP[status] ?? HEALTH_STATUS_CHIP.insufficient_evidence;
}

const HEALTH_DOT_COLOR: Record<string, string> = {
  healthy: "bg-teal-400",
  watch: "bg-yellow-400",
  review: "bg-orange-400",
  critical: "bg-red-400",
  insufficient_evidence: "bg-bg-500",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function HealthDot({ status }: { status: string }) {
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full shrink-0 mt-0.5 ${HEALTH_DOT_COLOR[status] ?? "bg-bg-500"}`}
    />
  );
}

function CoverageBar({ score, max = 100 }: { score: number; max?: number }) {
  const pct = Math.min(100, Math.max(0, (score / max) * 100));
  const barColor =
    score >= 80 ? "bg-teal-500" : score >= 60 ? "bg-yellow-500" : "bg-red-500/80";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1 w-20 rounded-full bg-bg-600 overflow-hidden">
        <div
          className={`h-full rounded-full ${barColor} opacity-80`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`font-mono text-2xs tabular-nums ${scoreColor(score)}`}>
        {score.toFixed(0)}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Review strategy row
// ---------------------------------------------------------------------------

function ReviewRow({ item }: { item: PortfolioStrategyItem }) {
  return (
    <div className="flex items-start gap-3 py-3 border-b border-border/60 last:border-0">
      <HealthDot status={item.health_status} />
      <div className="min-w-0 flex-1">
        <Link
          to={`/strategies/${item.strategy_id}`}
          className="text-sm font-medium text-text-primary hover:text-accent-300 truncate block transition-colors"
        >
          {item.name}
        </Link>
        {item.primary_concern && (
          <p className="mt-0.5 text-xs text-text-muted truncate">
            {item.primary_concern}
          </p>
        )}
      </div>
      <div className="shrink-0 flex items-center gap-2.5 pt-0.5">
        {item.open_alert_count > 0 && (
          <span className="text-xs text-orange-300 bg-orange-950/50 border border-orange-800/40 rounded-chip px-1.5 py-0.5 tabular-nums">
            {item.open_alert_count} alert{item.open_alert_count !== 1 ? "s" : ""}
          </span>
        )}
        <CoverageBar score={item.evidence_coverage_score} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Under-instrumented row
// ---------------------------------------------------------------------------

function UnderInstrumentedRow({ item }: { item: PortfolioStrategyItem }) {
  return (
    <div className="flex items-center gap-3 py-3 border-b border-border/60 last:border-0">
      <div className="min-w-0 flex-1">
        <Link
          to={`/strategies/${item.strategy_id}`}
          className="text-sm font-medium text-text-primary hover:text-accent-300 truncate block transition-colors"
        >
          {item.name}
        </Link>
      </div>
      <div className="shrink-0 flex items-center gap-3">
        <CoverageBar score={item.evidence_coverage_score} />
        {item.missing_evidence_count > 0 && (
          <span className="text-xs text-text-muted tabular-nums">
            {item.missing_evidence_count} missing
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Strongest evidence row
// ---------------------------------------------------------------------------

function StrongestRow({ item }: { item: PortfolioStrategyItem }) {
  return (
    <div className="flex items-center gap-3 py-3 border-b border-border/60 last:border-0">
      <HealthDot status={item.health_status} />
      <div className="min-w-0 flex-1">
        <Link
          to={`/strategies/${item.strategy_id}`}
          className="text-sm font-medium text-text-primary hover:text-accent-300 truncate block transition-colors"
        >
          {item.name}
        </Link>
      </div>
      <div className="shrink-0 flex items-center gap-3">
        <span className="text-xs text-text-muted">cov</span>
        <CoverageBar score={item.evidence_coverage_score} />
        {item.reliability_score !== null && (
          <span className={`font-mono text-2xs tabular-nums ${scoreColor(item.reliability_score)}`}>
            rel {item.reliability_score.toFixed(0)}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Deteriorating trend row
// ---------------------------------------------------------------------------

function DeterioratingRow({ item }: { item: PortfolioStrategyItem }) {
  const flags = item.trend_flags;
  const activeFlags: Array<{ key: string; label: string }> = [];
  if (flags.reliability_deteriorating) activeFlags.push({ key: "rel", label: "Reliability" });
  if (flags.data_health_deteriorating) activeFlags.push({ key: "data", label: "Data health" });
  if (flags.backtest_trust_deteriorating) activeFlags.push({ key: "bt", label: "Backtest trust" });
  if (flags.signal_quality_deteriorating) activeFlags.push({ key: "sig", label: "Signal quality" });

  return (
    <div className="flex items-start gap-3 py-3 border-b border-border/60 last:border-0">
      <div className="min-w-0 flex-1">
        <Link
          to={`/strategies/${item.strategy_id}`}
          className="text-sm font-medium text-text-primary hover:text-accent-300 truncate block transition-colors"
        >
          {item.name}
        </Link>
      </div>
      <div className="shrink-0 flex flex-wrap gap-1 pt-0.5">
        {activeFlags.map((f) => (
          <span
            key={f.key}
            className="text-xs text-orange-300 bg-orange-950/50 border border-orange-800/40 rounded-chip px-1.5 py-0.5"
          >
            {f.label}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Full portfolio table row
// ---------------------------------------------------------------------------

const TH = "px-4 py-2.5 text-left text-xs font-medium text-text-muted tracking-eyebrow";
const TD = "px-4 py-3";

function PortfolioTableRow({ item }: { item: PortfolioStrategyItem }) {
  return (
    <tr className="border-b border-border/60 last:border-0 hover:bg-bg-600/50 transition-colors">
      <td className={TD}>
        <Link
          to={`/strategies/${item.strategy_id}`}
          className="text-sm font-medium text-text-primary hover:text-accent-300 transition-colors"
        >
          {item.name}
        </Link>
        <p className="font-mono text-2xs text-text-muted mt-0.5">{item.slug}</p>
      </td>
      <td className={TD}>
        <Badge value={item.asset_class} variant="asset_class" />
      </td>
      <td className={TD}>
        <PortfolioStageChip strategyId={item.strategy_id} />
      </td>
      <td className={TD}>
        <span
          className={`inline-flex items-center gap-1.5 rounded-chip border px-2 py-0.5 text-xs ${healthChipClass(item.health_status)}`}
        >
          {item.health_status.replace(/_/g, " ")}
        </span>
      </td>
      <td className={`${TD}`}>
        {item.reliability_score !== null ? (
          <span className={`font-mono text-sm tabular-nums ${scoreColor(item.reliability_score)}`}>
            {item.reliability_score.toFixed(0)}
          </span>
        ) : (
          <span className="text-text-muted">—</span>
        )}
      </td>
      <td className={TD}>
        <CoverageBar score={item.evidence_coverage_score} />
      </td>
      <td className={`${TD}`}>
        {item.open_alert_count > 0 ? (
          <span className="font-mono text-sm tabular-nums text-orange-300">{item.open_alert_count}</span>
        ) : (
          <span className="font-mono text-sm text-text-muted">0</span>
        )}
      </td>
      <td className={`${TD} font-mono text-xs text-text-muted whitespace-nowrap tabular-nums`}>
        {item.latest_run_at
          ? new Date(item.latest_run_at).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
            })
          : "—"}
      </td>
      <td className={`${TD} text-xs text-text-muted max-w-[200px] truncate`}>
        {item.primary_concern || "—"}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Summary tile
// ---------------------------------------------------------------------------

function SummaryTile({
  label,
  value,
  valueClass,
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-5 py-4 gap-1">
      <span className="text-xs text-text-muted tracking-eyebrow">{label}</span>
      <span className={`font-mono text-2xl font-semibold tabular-nums leading-none ${valueClass ?? "text-text-primary"}`}>
        {value}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section card wrapper
// ---------------------------------------------------------------------------

function SectionCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-card border border-border bg-bg-700 shadow-card">
      <div className="border-b border-border/70 px-5 py-3">
        <p className="text-sm font-medium text-text-primary">{title}</p>
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function Portfolio() {
  const [overview, setOverview] = useState<PortfolioOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getPortfolioOverview({ limit_per_section: 10 })
      .then(setOverview)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Failed to load portfolio overview"),
      )
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        tag="Analysis"
        title="Portfolio Overview"
        subtitle="Evidence state across all active strategies."
      >
        <Link
          to="/strategies/run-compare"
          className="text-xs text-accent-500 hover:text-accent-300 transition-colors"
        >
          Compare Runs →
        </Link>
      </PageHeader>

      {error && (
        <div className="rounded-control border border-red-800/60 bg-red-950/30 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading && (
        <p className="text-xs text-text-muted">Loading portfolio overview…</p>
      )}

      {!loading && !error && overview === null && (
        <EmptyState
          title="No portfolio data"
          description="Register strategies to begin tracking portfolio-level evidence and health metrics."
        />
      )}

      {!loading && !error && overview && (
        <>
          {/* -------------------------------------------------------------- */}
          {/* Summary strip                                                   */}
          {/* -------------------------------------------------------------- */}
          <div className="rounded-card border border-border bg-bg-700 shadow-card">
            <div className="border-b border-border/70 px-5 py-3">
              <p className="text-sm font-medium text-text-primary">Portfolio Summary</p>
            </div>
            <div className="grid grid-cols-5 divide-x divide-border/60">
              <SummaryTile
                label="Active"
                value={String(overview.active_strategy_count)}
              />
              <SummaryTile
                label="Avg Health"
                value={overview.average_health_score !== null ? overview.average_health_score.toFixed(1) : "—"}
                valueClass={scoreColor(overview.average_health_score)}
              />
              <SummaryTile
                label="Avg Reliability"
                value={overview.average_reliability_score !== null ? overview.average_reliability_score.toFixed(1) : "—"}
                valueClass={scoreColor(overview.average_reliability_score)}
              />
              <SummaryTile
                label="Avg Coverage"
                value={overview.average_evidence_coverage_score !== null ? overview.average_evidence_coverage_score.toFixed(1) : "—"}
                valueClass={scoreColor(overview.average_evidence_coverage_score)}
              />
              <SummaryTile
                label="Open Alerts"
                value={String(overview.open_alert_count)}
                valueClass={overview.open_alert_count > 0 ? "text-orange-300" : "text-text-primary"}
              />
            </div>

            {/* Health distribution */}
            {Object.keys(overview.strategies_by_health_status).length > 0 && (
              <div className="border-t border-border/60 px-5 py-3 flex flex-wrap items-center gap-2">
                <span className="text-xs text-text-muted mr-1">Health breakdown</span>
                {Object.entries(overview.strategies_by_health_status).map(
                  ([status, count]) => (
                    <span
                      key={status}
                      className={`inline-flex items-center gap-1.5 rounded-chip border px-2 py-0.5 text-xs ${healthChipClass(status)}`}
                    >
                      {status.replace(/_/g, " ")}
                      <span className="font-mono font-semibold tabular-nums">{count}</span>
                    </span>
                  ),
                )}
              </div>
            )}

            {/* Deterministic summary */}
            {overview.deterministic_summary && (
              <div className="border-t border-border/60 px-5 py-3">
                <p className="text-xs text-text-muted italic leading-relaxed">
                  {overview.deterministic_summary}
                </p>
              </div>
            )}
          </div>

          {/* -------------------------------------------------------------- */}
          {/* Review + Under-Instrumented                                     */}
          {/* -------------------------------------------------------------- */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <SectionCard title="Strategies Requiring Review">
              {overview.top_review_strategies.length === 0 ? (
                <div className="px-5 py-8 text-center">
                  <p className="text-sm text-text-muted">No strategies requiring review.</p>
                </div>
              ) : (
                <div className="px-5">
                  {overview.top_review_strategies.map((item) => (
                    <ReviewRow key={item.strategy_id} item={item} />
                  ))}
                </div>
              )}
            </SectionCard>

            <SectionCard title="Under-Instrumented Strategies">
              {overview.most_under_instrumented_strategies.length === 0 ? (
                <div className="px-5 py-8 text-center">
                  <p className="text-sm text-text-muted">All strategies have adequate coverage.</p>
                </div>
              ) : (
                <div className="px-5">
                  {overview.most_under_instrumented_strategies.map((item) => (
                    <UnderInstrumentedRow key={item.strategy_id} item={item} />
                  ))}
                </div>
              )}
            </SectionCard>
          </div>

          {/* -------------------------------------------------------------- */}
          {/* Strongest Evidence + Deteriorating Trends                       */}
          {/* -------------------------------------------------------------- */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <SectionCard title="Strongest Evidence">
              {overview.strongest_evidence_strategies.length === 0 ? (
                <div className="px-5 py-8 text-center">
                  <p className="text-sm text-text-muted">No data yet.</p>
                </div>
              ) : (
                <div className="px-5">
                  {overview.strongest_evidence_strategies.map((item) => (
                    <StrongestRow key={item.strategy_id} item={item} />
                  ))}
                </div>
              )}
            </SectionCard>

            <SectionCard title="Deteriorating Evidence Trends">
              {overview.deteriorating_trend_strategies.length === 0 ? (
                <div className="px-5 py-8 text-center">
                  <p className="text-sm text-text-muted">No deteriorating trends detected.</p>
                </div>
              ) : (
                <div className="px-5">
                  {overview.deteriorating_trend_strategies.map((item) => (
                    <DeterioratingRow key={item.strategy_id} item={item} />
                  ))}
                </div>
              )}
            </SectionCard>
          </div>

          {/* -------------------------------------------------------------- */}
          {/* Full portfolio table                                            */}
          {/* -------------------------------------------------------------- */}
          {overview.all_items.length > 0 && (
            <div className="rounded-card border border-border bg-bg-700 shadow-card">
              <div className="border-b border-border/70 px-5 py-3">
                <p className="text-sm font-medium text-text-primary">
                  All Strategies
                  <span className="ml-2 font-mono text-xs text-text-muted">
                    {overview.all_items.length}
                  </span>
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border/60 bg-bg-800/60">
                      <th className={TH}>Strategy</th>
                      <th className={TH}>Asset</th>
                      <th className={TH}>Stage</th>
                      <th className={TH}>Health</th>
                      <th className={TH}>Reliability</th>
                      <th className={TH}>Coverage</th>
                      <th className={TH}>Alerts</th>
                      <th className={TH}>Last Run</th>
                      <th className={TH}>Concern</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overview.all_items.map((item) => (
                      <PortfolioTableRow key={item.strategy_id} item={item} />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* -------------------------------------------------------------- */}
          {/* Suggested next steps                                            */}
          {/* -------------------------------------------------------------- */}
          {overview.suggested_next_steps.length > 0 && (
            <div className="rounded-card border border-border bg-bg-700 shadow-card">
              <div className="border-b border-border/70 px-5 py-3">
                <p className="text-sm font-medium text-text-primary">Suggested Next Steps</p>
              </div>
              <ul className="px-5 py-4 space-y-2.5">
                {overview.suggested_next_steps.map((step, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-3 text-sm text-text-secondary"
                  >
                    <span className="mt-px font-mono text-xs text-text-muted shrink-0 w-4 text-right">
                      {i + 1}.
                    </span>
                    <span className="leading-relaxed">{step}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Footnote */}
          <p className="text-xs text-text-muted text-center pb-2">
            This overview is deterministic and does not constitute investment advice.
          </p>
        </>
      )}
    </div>
  );
}
