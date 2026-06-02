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
import { getPortfolioOverview } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import Badge from "@/components/Badge";
import EmptyState from "@/components/EmptyState";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function scoreColor(v: number | null): string {
  if (v === null) return "text-text-muted";
  if (v >= 80) return "text-teal-400";
  if (v >= 60) return "text-yellow-400";
  return "text-red-400";
}

const HEALTH_STATUS_CHIP: Record<string, string> = {
  healthy: "bg-teal-900/40 text-teal-300 border-teal-700/40",
  watch: "bg-yellow-900/40 text-yellow-200 border-yellow-700/40",
  review: "bg-orange-900/40 text-orange-300 border-orange-700/40",
  critical: "bg-red-900/40 text-red-300 border-red-700/40",
  insufficient_evidence: "bg-bg-600 text-text-muted border-border",
};

function healthChipClass(status: string): string {
  return HEALTH_STATUS_CHIP[status] ?? HEALTH_STATUS_CHIP.insufficient_evidence;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function HealthDot({ status }: { status: string }) {
  const dotColor: Record<string, string> = {
    healthy: "bg-teal-400",
    watch: "bg-yellow-400",
    review: "bg-orange-400",
    critical: "bg-red-400",
    insufficient_evidence: "bg-bg-500",
  };
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full shrink-0 ${dotColor[status] ?? "bg-bg-500"}`}
    />
  );
}

function CoverageBar({ score, max = 100 }: { score: number; max?: number }) {
  const pct = Math.min(100, Math.max(0, (score / max) * 100));
  const barColor =
    score >= 80 ? "bg-teal-400" : score >= 60 ? "bg-yellow-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 rounded-full bg-bg-600 overflow-hidden">
        <div
          className={`h-full rounded-full ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`font-mono text-2xs ${scoreColor(score)}`}>
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
    <div className="flex items-start gap-3 py-2.5 border-b border-border last:border-0">
      <HealthDot status={item.health_status} />
      <div className="min-w-0 flex-1">
        <Link
          to={`/strategies/${item.strategy_id}`}
          className="text-xs font-medium text-text-primary hover:text-accent-300 truncate block"
        >
          {item.name}
        </Link>
        {item.primary_concern && (
          <p className="mt-px font-mono text-2xs text-text-muted truncate">
            {item.primary_concern}
          </p>
        )}
      </div>
      <div className="shrink-0 flex items-center gap-2">
        {item.open_alert_count > 0 && (
          <span className="font-mono text-2xs text-orange-400 bg-orange-900/30 border border-orange-700/30 rounded px-1.5 py-0.5">
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
    <div className="flex items-center gap-3 py-2.5 border-b border-border last:border-0">
      <div className="min-w-0 flex-1">
        <Link
          to={`/strategies/${item.strategy_id}`}
          className="text-xs font-medium text-text-primary hover:text-accent-300 truncate block"
        >
          {item.name}
        </Link>
      </div>
      <div className="shrink-0 flex items-center gap-3">
        <CoverageBar score={item.evidence_coverage_score} />
        {item.missing_evidence_count > 0 && (
          <span className="font-mono text-2xs text-text-muted">
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
    <div className="flex items-center gap-3 py-2.5 border-b border-border last:border-0">
      <HealthDot status={item.health_status} />
      <div className="min-w-0 flex-1">
        <Link
          to={`/strategies/${item.strategy_id}`}
          className="text-xs font-medium text-text-primary hover:text-accent-300 truncate block"
        >
          {item.name}
        </Link>
      </div>
      <div className="shrink-0 flex items-center gap-3">
        <span className="font-mono text-2xs text-text-muted">cov</span>
        <CoverageBar score={item.evidence_coverage_score} />
        {item.reliability_score !== null && (
          <span className={`font-mono text-2xs ${scoreColor(item.reliability_score)}`}>
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
  if (flags.reliability_deteriorating) activeFlags.push({ key: "rel", label: "reliability" });
  if (flags.data_health_deteriorating) activeFlags.push({ key: "data", label: "data" });
  if (flags.backtest_trust_deteriorating) activeFlags.push({ key: "bt", label: "bt trust" });
  if (flags.signal_quality_deteriorating) activeFlags.push({ key: "sig", label: "signal" });

  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-border last:border-0">
      <div className="min-w-0 flex-1">
        <Link
          to={`/strategies/${item.strategy_id}`}
          className="text-xs font-medium text-text-primary hover:text-accent-300 truncate block"
        >
          {item.name}
        </Link>
      </div>
      <div className="shrink-0 flex flex-wrap gap-1">
        {activeFlags.map((f) => (
          <span
            key={f.key}
            className="font-mono text-2xs text-orange-300 bg-orange-900/30 border border-orange-700/30 rounded px-1.5 py-0.5"
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

const TH = "px-3 py-2 text-left font-mono text-2xs uppercase tracking-widest text-text-muted";
const TD = "px-3 py-2";

function PortfolioTableRow({ item }: { item: PortfolioStrategyItem }) {
  return (
    <tr className="border-b border-border last:border-0 hover:bg-bg-600">
      <td className={TD}>
        <Link
          to={`/strategies/${item.strategy_id}`}
          className="text-xs font-medium text-text-primary hover:text-accent-300"
        >
          {item.name}
        </Link>
        <p className="font-mono text-2xs text-text-muted">{item.slug}</p>
      </td>
      <td className={TD}>
        <Badge value={item.asset_class} variant="asset_class" />
      </td>
      <td className={TD}>
        <span
          className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-2xs ${healthChipClass(item.health_status)}`}
        >
          {item.health_status.replace(/_/g, " ")}
        </span>
      </td>
      <td className={`${TD} mono-num`}>
        {item.reliability_score !== null ? (
          <span className={scoreColor(item.reliability_score)}>
            {item.reliability_score.toFixed(0)}
          </span>
        ) : (
          <span className="text-text-muted">—</span>
        )}
      </td>
      <td className={TD}>
        <CoverageBar score={item.evidence_coverage_score} />
      </td>
      <td className={`${TD} mono-num`}>
        {item.open_alert_count > 0 ? (
          <span className="text-orange-400">{item.open_alert_count}</span>
        ) : (
          <span className="text-text-muted">0</span>
        )}
      </td>
      <td className={`${TD} font-mono text-2xs text-text-muted whitespace-nowrap`}>
        {item.latest_run_at
          ? new Date(item.latest_run_at).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
            })
          : "—"}
      </td>
      <td className={`${TD} font-mono text-2xs text-text-muted max-w-[180px] truncate`}>
        {item.primary_concern || "—"}
      </td>
    </tr>
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
    <div className="space-y-7">
      <PageHeader
        tag="Analysis"
        title="Portfolio Overview"
        subtitle="Evidence state across all active strategies."
      />

      {error && (
        <div className="rounded border border-red-800 bg-red-900/20 px-4 py-3 font-mono text-xs text-red-300">
          {error}
        </div>
      )}

      {loading && (
        <p className="font-mono text-2xs text-text-muted">Loading portfolio overview…</p>
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
          <div className="rounded-card border border-border bg-bg-700">
            <div className="border-b border-border px-4 py-2.5">
              <p className="caption">Portfolio Summary</p>
            </div>
            <div className="grid grid-cols-5 divide-x divide-border">
              <div className="px-4 py-3 text-center">
                <p className="font-mono text-2xs text-text-muted uppercase tracking-wider">
                  Active
                </p>
                <p className="mono-num mt-1 text-xl font-bold text-text-primary">
                  {overview.active_strategy_count}
                </p>
              </div>
              <div className="px-4 py-3 text-center">
                <p className="font-mono text-2xs text-text-muted uppercase tracking-wider">
                  Avg Health
                </p>
                <p
                  className={`mono-num mt-1 text-xl font-bold ${scoreColor(overview.average_health_score)}`}
                >
                  {overview.average_health_score !== null
                    ? overview.average_health_score.toFixed(1)
                    : "—"}
                </p>
              </div>
              <div className="px-4 py-3 text-center">
                <p className="font-mono text-2xs text-text-muted uppercase tracking-wider">
                  Avg Reliability
                </p>
                <p
                  className={`mono-num mt-1 text-xl font-bold ${scoreColor(overview.average_reliability_score)}`}
                >
                  {overview.average_reliability_score !== null
                    ? overview.average_reliability_score.toFixed(1)
                    : "—"}
                </p>
              </div>
              <div className="px-4 py-3 text-center">
                <p className="font-mono text-2xs text-text-muted uppercase tracking-wider">
                  Avg Coverage
                </p>
                <p
                  className={`mono-num mt-1 text-xl font-bold ${scoreColor(overview.average_evidence_coverage_score)}`}
                >
                  {overview.average_evidence_coverage_score !== null
                    ? overview.average_evidence_coverage_score.toFixed(1)
                    : "—"}
                </p>
              </div>
              <div className="px-4 py-3 text-center">
                <p className="font-mono text-2xs text-text-muted uppercase tracking-wider">
                  Open Alerts
                </p>
                <p
                  className={`mono-num mt-1 text-xl font-bold ${overview.open_alert_count > 0 ? "text-red-400" : "text-text-primary"}`}
                >
                  {overview.open_alert_count}
                </p>
              </div>
            </div>

            {/* Health distribution chips */}
            {Object.keys(overview.strategies_by_health_status).length > 0 && (
              <div className="border-t border-border px-4 py-2.5 flex flex-wrap gap-2">
                <p className="font-mono text-2xs text-text-muted mr-2 self-center">
                  Health:
                </p>
                {Object.entries(overview.strategies_by_health_status).map(
                  ([status, count]) => (
                    <span
                      key={status}
                      className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 font-mono text-2xs ${healthChipClass(status)}`}
                    >
                      {status.replace(/_/g, " ")}{" "}
                      <span className="font-bold">{count}</span>
                    </span>
                  ),
                )}
              </div>
            )}

            {/* Deterministic summary */}
            {overview.deterministic_summary && (
              <div className="border-t border-border px-4 py-2.5">
                <p className="font-mono text-xs text-text-muted italic">
                  {overview.deterministic_summary}
                </p>
              </div>
            )}
          </div>

          {/* -------------------------------------------------------------- */}
          {/* Review + Under-Instrumented                                     */}
          {/* -------------------------------------------------------------- */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            {/* Left: Strategies Requiring Review */}
            <div className="rounded-card border border-border bg-bg-700">
              <div className="border-b border-border px-4 py-2.5">
                <p className="caption">Strategies Requiring Review</p>
              </div>
              {overview.top_review_strategies.length === 0 ? (
                <div className="px-4 py-6">
                  <p className="font-mono text-2xs text-text-muted text-center">
                    No strategies requiring review.
                  </p>
                </div>
              ) : (
                <div className="px-4">
                  {overview.top_review_strategies.map((item) => (
                    <ReviewRow key={item.strategy_id} item={item} />
                  ))}
                </div>
              )}
            </div>

            {/* Right: Under-Instrumented */}
            <div className="rounded-card border border-border bg-bg-700">
              <div className="border-b border-border px-4 py-2.5">
                <p className="caption">Under-Instrumented Strategies</p>
              </div>
              {overview.most_under_instrumented_strategies.length === 0 ? (
                <div className="px-4 py-6">
                  <p className="font-mono text-2xs text-text-muted text-center">
                    All strategies have adequate coverage.
                  </p>
                </div>
              ) : (
                <div className="px-4">
                  {overview.most_under_instrumented_strategies.map((item) => (
                    <UnderInstrumentedRow key={item.strategy_id} item={item} />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* -------------------------------------------------------------- */}
          {/* Strongest Evidence + Deteriorating Trends                       */}
          {/* -------------------------------------------------------------- */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            {/* Left: Strongest Evidence */}
            <div className="rounded-card border border-border bg-bg-700">
              <div className="border-b border-border px-4 py-2.5">
                <p className="caption">Strongest Evidence</p>
              </div>
              {overview.strongest_evidence_strategies.length === 0 ? (
                <div className="px-4 py-6">
                  <p className="font-mono text-2xs text-text-muted text-center">
                    No data yet.
                  </p>
                </div>
              ) : (
                <div className="px-4">
                  {overview.strongest_evidence_strategies.map((item) => (
                    <StrongestRow key={item.strategy_id} item={item} />
                  ))}
                </div>
              )}
            </div>

            {/* Right: Deteriorating Trends */}
            <div className="rounded-card border border-border bg-bg-700">
              <div className="border-b border-border px-4 py-2.5">
                <p className="caption">Deteriorating Evidence Trends</p>
              </div>
              {overview.deteriorating_trend_strategies.length === 0 ? (
                <div className="px-4 py-6">
                  <p className="font-mono text-2xs text-text-muted text-center">
                    No deteriorating trends detected.
                  </p>
                </div>
              ) : (
                <div className="px-4">
                  {overview.deteriorating_trend_strategies.map((item) => (
                    <DeterioratingRow key={item.strategy_id} item={item} />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* -------------------------------------------------------------- */}
          {/* Full portfolio table                                            */}
          {/* -------------------------------------------------------------- */}
          {overview.all_items.length > 0 && (
            <div className="rounded-card border border-border bg-bg-700">
              <div className="border-b border-border px-4 py-2.5">
                <p className="caption">
                  All Strategies ({overview.all_items.length})
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border bg-bg-800">
                      <th className={TH}>Strategy</th>
                      <th className={TH}>Asset</th>
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
            <div className="rounded-card border border-border bg-bg-700">
              <div className="border-b border-border px-4 py-2.5">
                <p className="caption">Suggested Next Steps</p>
              </div>
              <ul className="px-4 py-3 space-y-1.5">
                {overview.suggested_next_steps.map((step, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 font-mono text-xs text-text-secondary"
                  >
                    <span className="mt-px text-text-muted shrink-0">{i + 1}.</span>
                    {step}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Note */}
          <p className="font-mono text-2xs text-text-muted italic text-center">
            This overview is deterministic. Not investment advice.
          </p>
        </>
      )}
    </div>
  );
}
