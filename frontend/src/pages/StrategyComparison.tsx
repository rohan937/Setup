/**
 * M20: Strategy Comparison Page — /strategies/compare
 *
 * Compares 2–8 strategies side-by-side using logged evidence.
 * Evidence-based instrumentation comparison only — never investment advice.
 *
 * Language: "higher current reliability score", "better evidenced",
 *           "more complete instrumentation", "requires review"
 * Never: "better strategy", "more profitable", "should trade"
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type {
  Strategy,
  StrategyComparisonItem,
  StrategyComparisonResponse,
} from "@/types";
import { getStrategies, compareStrategies } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import Badge from "@/components/Badge";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function scoreColor(score: number | null): string {
  if (score === null) return "text-text-muted";
  if (score >= 75) return "text-green-400";
  if (score >= 55) return "text-yellow-400";
  return "text-red-400";
}

function coverageColor(score: number): string {
  if (score >= 80) return "text-green-400";
  if (score >= 40) return "text-yellow-400";
  return "text-red-400";
}

function formatScore(score: number | null): string {
  return score !== null ? score.toFixed(0) : "—";
}

function formatFloat(score: number | null): string {
  return score !== null ? score.toFixed(1) : "—";
}

const GAP_LABEL: Record<string, string> = {
  no_runs: "No runs",
  no_dataset_evidence: "No dataset evidence",
  no_backtest_audit: "No backtest audit",
  no_signal_evidence: "No signal snapshots",
  no_universe_evidence: "No universe snapshots",
  no_config_snapshot: "No config snapshots",
  open_high_alerts: "High/critical alerts",
  insufficient_reliability_score: "No reliability score",
  stale_reliability_score: "Stale score (>30d)",
};

const STATUS_COLORS: Record<string, string> = {
  excellent: "text-cyan-300",
  good:      "text-teal-300",
  review:    "text-yellow-300",
  weak:      "text-red-400",
  insufficient_evidence: "text-text-muted",
  no_score:  "text-text-muted",
};

const TH = "px-3 py-2 text-left font-mono text-2xs uppercase tracking-widest text-text-muted whitespace-nowrap";
const TD = "px-3 py-2 font-mono text-xs";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ReliabilityStatusChip({ status }: { status: string | null }) {
  if (!status || status === "no_score") {
    return <span className="text-text-muted/50 text-2xs">—</span>;
  }
  const cls = STATUS_COLORS[status] ?? "text-text-muted";
  return (
    <span className={`font-mono text-2xs ${cls}`}>
      {status.replace("_", " ")}
    </span>
  );
}

function GapChip({ gap }: { gap: string }) {
  const isAlert = gap === "open_high_alerts";
  const isInsuff = gap === "insufficient_reliability_score" || gap === "stale_reliability_score";
  const cls = isAlert
    ? "bg-red-900/30 text-red-300 border-red-700/40"
    : isInsuff
    ? "bg-yellow-900/20 text-yellow-300 border-yellow-700/30"
    : "bg-bg-600 text-text-muted border-border";
  return (
    <span
      className={`inline-flex rounded border px-1.5 py-px font-mono text-2xs mr-1 mb-1 ${cls}`}
    >
      {GAP_LABEL[gap] ?? gap}
    </span>
  );
}

function CoverageBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, score));
  const barColor =
    pct >= 80 ? "bg-green-500/70" : pct >= 40 ? "bg-yellow-500/70" : "bg-red-500/70";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 rounded-full bg-bg-600 overflow-hidden">
        <div
          className={`h-full rounded-full ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`font-mono text-xs ${coverageColor(pct)}`}>
        {pct.toFixed(0)}/100
      </span>
    </div>
  );
}

// Compact side-by-side card for one strategy
function StrategyCard({ item }: { item: StrategyComparisonItem }) {
  const cov = item.coverage;
  return (
    <div className="rounded-card border border-border bg-bg-700 p-4 flex flex-col gap-3 min-w-0">
      {/* Header */}
      <div>
        <Link
          to={`/strategies/${item.strategy_id}`}
          className="text-sm font-medium text-text-primary hover:text-accent-300"
        >
          {item.name}
        </Link>
        <div className="mt-0.5 flex items-center gap-2">
          <Badge value={item.asset_class} variant="asset_class" />
          <Badge value={item.status} variant="status" />
        </div>
      </div>

      {/* Reliability score */}
      <div className="rounded border border-border bg-bg-800 px-3 py-2">
        <p className="font-mono text-2xs uppercase tracking-widest text-text-muted mb-1">
          Reliability Score
        </p>
        <div className="flex items-baseline gap-2">
          <span
            className={`mono-num text-xl font-bold ${scoreColor(item.overall_reliability_score)}`}
          >
            {formatScore(item.overall_reliability_score)}
          </span>
          {item.overall_reliability_score !== null && (
            <span className="font-mono text-xs text-text-muted">/100</span>
          )}
          <ReliabilityStatusChip status={item.reliability_status} />
        </div>
        {item.reliability_generated_at && (
          <p className="mt-0.5 font-mono text-2xs text-text-muted/60">
            scored {new Date(item.reliability_generated_at).toLocaleDateString()}
          </p>
        )}
      </div>

      {/* Evidence coverage */}
      <div>
        <p className="font-mono text-2xs uppercase tracking-widest text-text-muted mb-1">
          Evidence Coverage
        </p>
        <CoverageBar score={cov.evidence_coverage_score} />
        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
          <span className="font-mono text-2xs text-text-muted">Runs</span>
          <span className="mono-num font-mono text-2xs text-text-secondary">{cov.run_count}</span>
          <span className="font-mono text-2xs text-text-muted">Backtest runs</span>
          <span className="mono-num font-mono text-2xs text-text-secondary">{cov.backtest_run_count}</span>
          <span className="font-mono text-2xs text-text-muted">Dataset evidence</span>
          <span className="mono-num font-mono text-2xs text-text-secondary">{cov.dataset_snapshot_linked_count}</span>
          <span className="font-mono text-2xs text-text-muted">Backtest audits</span>
          <span className="mono-num font-mono text-2xs text-text-secondary">{cov.backtest_audit_count}</span>
          <span className="font-mono text-2xs text-text-muted">Signal snapshots</span>
          <span className="mono-num font-mono text-2xs text-text-secondary">{cov.signal_snapshot_count}</span>
          <span className="font-mono text-2xs text-text-muted">Universe snapshots</span>
          <span className="mono-num font-mono text-2xs text-text-secondary">{cov.universe_snapshot_count}</span>
          <span className="font-mono text-2xs text-text-muted">Config snapshots</span>
          <span className="mono-num font-mono text-2xs text-text-secondary">{cov.config_snapshot_count}</span>
          <span className="font-mono text-2xs text-text-muted">Reports</span>
          <span className="mono-num font-mono text-2xs text-text-secondary">{cov.report_count}</span>
          {cov.open_alert_count > 0 && (
            <>
              <span className="font-mono text-2xs text-red-400">Open alerts</span>
              <span className="mono-num font-mono text-2xs text-red-400">{cov.open_alert_count}</span>
            </>
          )}
        </div>
      </div>

      {/* Component scores */}
      {item.overall_reliability_score !== null && (
        <div>
          <p className="font-mono text-2xs uppercase tracking-widest text-text-muted mb-1">
            Component Scores
          </p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            {[
              ["Activity", item.strategy_activity_score],
              ["Data", item.data_evidence_score],
              ["Backtest", item.backtest_trust_score],
              ["Config", item.config_evidence_score],
              ["Universe", item.universe_evidence_score],
              ["Signal", item.signal_evidence_score],
              ["Alert Pen.", item.alert_penalty_score],
              ["Reports", item.report_coverage_score],
            ].map(([label, val]) => (
              <span key={label as string} className="contents">
                <span className="font-mono text-2xs text-text-muted">{label as string}</span>
                <span
                  className={`mono-num font-mono text-2xs ${scoreColor(val as number | null)}`}
                >
                  {formatFloat(val as number | null)}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Instrumentation gaps */}
      {item.gaps.length > 0 && (
        <div>
          <p className="font-mono text-2xs uppercase tracking-widest text-text-muted mb-1">
            Instrumentation Gaps
          </p>
          <div className="flex flex-wrap">
            {item.gaps.map((g) => (
              <GapChip key={g} gap={g} />
            ))}
          </div>
        </div>
      )}

      {/* Suggested checks */}
      {item.suggested_checks.length > 0 && (
        <div>
          <p className="font-mono text-2xs uppercase tracking-widest text-text-muted mb-1">
            Suggested Checks
          </p>
          <ul className="list-disc list-inside space-y-0.5">
            {item.suggested_checks.slice(0, 4).map((s, i) => (
              <li key={i} className="font-mono text-2xs text-text-muted">
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// Ranking table
function RankingTable({
  title,
  items,
}: {
  title: string;
  items: { rank: number; name: string; strategy_id: string; score: number | null; score_label: string; status: string }[];
}) {
  return (
    <div className="rounded-card border border-border bg-bg-700 overflow-hidden">
      <div className="px-4 py-2.5 border-b border-border bg-bg-800">
        <p className="font-mono text-2xs uppercase tracking-widest text-text-muted">{title}</p>
      </div>
      <table className="w-full">
        <tbody>
          {items.map((item) => (
            <tr key={item.strategy_id} className="border-b border-border last:border-0 hover:bg-bg-600 transition-colors">
              <td className={`${TD} w-8 text-text-muted`}>#{item.rank}</td>
              <td className={TD}>
                <Link
                  to={`/strategies/${item.strategy_id}`}
                  className="text-text-primary hover:text-accent-300"
                >
                  {item.name}
                </Link>
              </td>
              <td className={`${TD} text-right`}>
                <span className={`mono-num ${scoreColor(item.score)}`}>
                  {item.score_label}
                </span>
              </td>
              <td className={`${TD} w-24`}>
                <ReliabilityStatusChip status={item.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function StrategyComparison() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [comparing, setComparing] = useState(false);
  const [result, setResult] = useState<StrategyComparisonResponse | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);

  useEffect(() => {
    setLoadingList(true);
    getStrategies()
      .then(setStrategies)
      .catch((err) =>
        setListError(err instanceof Error ? err.message : "Failed to load strategies.")
      )
      .finally(() => setLoadingList(false));
  }, []);

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < 8) {
        next.add(id);
      }
      return next;
    });
    // Clear previous result when selection changes
    setResult(null);
    setCompareError(null);
  }

  async function handleCompare() {
    if (selected.size < 2) return;
    setComparing(true);
    setCompareError(null);
    setResult(null);
    try {
      const res = await compareStrategies({ strategy_ids: Array.from(selected) });
      setResult(res);
    } catch (err) {
      setCompareError(err instanceof Error ? err.message : "Comparison failed.");
    } finally {
      setComparing(false);
    }
  }

  const activeStrategies = strategies.filter((s) => s.status !== "archived");

  return (
    <>
      <PageHeader
        tag="Research"
        title="Strategy Comparison"
        subtitle="Compare strategies side-by-side based on reliability scores and evidence instrumentation coverage."
      >
        <Link
          to="/strategies"
          className="rounded-control border border-border px-3.5 py-1.5 text-xs font-mono text-text-muted hover:text-text-primary"
        >
          ← Strategy Lab
        </Link>
      </PageHeader>

      {/* Selector */}
      <div className="rounded-card border border-border bg-bg-700 p-4 mb-4">
        <div className="flex items-center justify-between mb-3">
          <p className="font-mono text-xs text-text-secondary">
            Select 2–8 strategies to compare
            {selected.size > 0 && (
              <span className="ml-2 text-accent-400">({selected.size} selected)</span>
            )}
          </p>
          <button
            onClick={handleCompare}
            disabled={selected.size < 2 || comparing}
            className="rounded-control bg-accent-500 px-4 py-1.5 text-xs font-medium text-text-inverse hover:bg-accent-600 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {comparing ? "Comparing…" : "Compare Strategies"}
          </button>
        </div>

        {loadingList && (
          <p className="font-mono text-2xs text-text-muted">Loading strategies…</p>
        )}
        {listError && (
          <p className="font-mono text-xs text-red-400">{listError}</p>
        )}

        {!loadingList && !listError && activeStrategies.length === 0 && (
          <p className="font-mono text-xs text-text-muted">
            No active strategies found.{" "}
            <Link to="/strategies" className="text-accent-400 hover:text-accent-300">
              Register a strategy
            </Link>{" "}
            to get started.
          </p>
        )}

        {!loadingList && !listError && activeStrategies.length < 2 && activeStrategies.length > 0 && (
          <p className="font-mono text-xs text-yellow-400">
            At least 2 strategies are required for comparison.{" "}
            <Link to="/strategies" className="text-accent-400 hover:text-accent-300">
              Register more strategies.
            </Link>
          </p>
        )}

        {!loadingList && !listError && activeStrategies.length >= 2 && (
          <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 lg:grid-cols-3">
            {activeStrategies.map((s) => {
              const isSelected = selected.has(s.id);
              const score = s.latest_reliability_score;
              return (
                <label
                  key={s.id}
                  className={`flex cursor-pointer items-center gap-3 rounded border px-3 py-2 transition-colors ${
                    isSelected
                      ? "border-accent-500/60 bg-accent-900/20"
                      : "border-border bg-bg-800 hover:border-border-hover"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleSelect(s.id)}
                    disabled={!isSelected && selected.size >= 8}
                    className="accent-accent-500"
                  />
                  <span className="flex-1 min-w-0">
                    <span className="block text-xs font-medium text-text-primary truncate">
                      {s.name}
                    </span>
                    <span className="font-mono text-2xs text-text-muted">
                      {s.asset_class} · {s.run_count} run{s.run_count !== 1 ? "s" : ""}
                    </span>
                  </span>
                  {score ? (
                    <span
                      className={`mono-num text-sm font-semibold ${scoreColor(score.overall_score)}`}
                    >
                      {score.overall_score !== null ? score.overall_score.toFixed(0) : "—"}
                    </span>
                  ) : (
                    <span className="font-mono text-2xs text-text-muted/40">—</span>
                  )}
                </label>
              );
            })}
          </div>
        )}
      </div>

      {/* Error */}
      {compareError && (
        <div className="rounded-card border border-red-700/40 bg-red-900/10 px-4 py-3 mb-4">
          <p className="font-mono text-xs text-red-400">{compareError}</p>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* Explanation */}
          <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
            <div className="flex items-center justify-between mb-2">
              <p className="font-mono text-2xs uppercase tracking-widest text-text-muted">
                Evidence Comparison Summary
              </p>
              <p className="font-mono text-2xs text-text-muted/60">
                generated {new Date(result.generated_at).toLocaleTimeString()}
              </p>
            </div>
            <p className="text-sm text-text-secondary leading-relaxed">
              {result.deterministic_explanation}
            </p>

            {result.differentiators.length > 0 && (
              <ul className="mt-2 list-disc list-inside space-y-0.5">
                {result.differentiators.map((d, i) => (
                  <li key={i} className="font-mono text-2xs text-text-muted">
                    {d}
                  </li>
                ))}
              </ul>
            )}

            {result.shared_gaps.length > 0 && (
              <div className="mt-2">
                <span className="font-mono text-2xs text-text-muted mr-2">
                  Shared gaps across all strategies:
                </span>
                {result.shared_gaps.map((g) => (
                  <GapChip key={g} gap={g} />
                ))}
              </div>
            )}
          </div>

          {/* Rankings side-by-side */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <RankingTable
              title="Reliability Ranking"
              items={result.ranked_by_reliability}
            />
            <RankingTable
              title="Evidence Coverage Ranking"
              items={result.ranked_by_evidence_coverage}
            />
          </div>

          {/* Side-by-side strategy cards */}
          <div>
            <p className="font-mono text-2xs uppercase tracking-widest text-text-muted mb-2">
              Side-by-Side Comparison
            </p>
            <div
              className="grid gap-4"
              style={{
                gridTemplateColumns: `repeat(${Math.min(result.strategies.length, 3)}, minmax(0, 1fr))`,
              }}
            >
              {result.strategies.map((item) => (
                <StrategyCard key={item.strategy_id} item={item} />
              ))}
            </div>
          </div>

          {/* Compact comparison table */}
          <div>
            <p className="font-mono text-2xs uppercase tracking-widest text-text-muted mb-2">
              Evidence Comparison Table
            </p>
            <div className="overflow-x-auto rounded-card border border-border">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-border bg-bg-800">
                    <th className={TH}>Metric</th>
                    {result.strategies.map((s) => (
                      <th key={s.strategy_id} className={TH}>
                        <Link
                          to={`/strategies/${s.strategy_id}`}
                          className="text-text-primary hover:text-accent-300"
                        >
                          {s.name}
                        </Link>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[
                    {
                      label: "Reliability Score",
                      get: (s: StrategyComparisonItem) => (
                        <span className={scoreColor(s.overall_reliability_score)}>
                          {formatScore(s.overall_reliability_score)}
                        </span>
                      ),
                    },
                    {
                      label: "Rel. Status",
                      get: (s: StrategyComparisonItem) => (
                        <ReliabilityStatusChip status={s.reliability_status} />
                      ),
                    },
                    {
                      label: "Coverage Score",
                      get: (s: StrategyComparisonItem) => (
                        <span className={coverageColor(s.coverage.evidence_coverage_score)}>
                          {s.coverage.evidence_coverage_score.toFixed(0)}/100
                        </span>
                      ),
                    },
                    {
                      label: "Total Runs",
                      get: (s: StrategyComparisonItem) => s.coverage.run_count,
                    },
                    {
                      label: "Backtest Runs",
                      get: (s: StrategyComparisonItem) => s.coverage.backtest_run_count,
                    },
                    {
                      label: "Dataset Evidence",
                      get: (s: StrategyComparisonItem) => s.coverage.dataset_snapshot_linked_count,
                    },
                    {
                      label: "Backtest Audits",
                      get: (s: StrategyComparisonItem) => s.coverage.backtest_audit_count,
                    },
                    {
                      label: "Signal Snapshots",
                      get: (s: StrategyComparisonItem) => s.coverage.signal_snapshot_count,
                    },
                    {
                      label: "Universe Snapshots",
                      get: (s: StrategyComparisonItem) => s.coverage.universe_snapshot_count,
                    },
                    {
                      label: "Config Snapshots",
                      get: (s: StrategyComparisonItem) => s.coverage.config_snapshot_count,
                    },
                    {
                      label: "Reports",
                      get: (s: StrategyComparisonItem) => s.coverage.report_count,
                    },
                    {
                      label: "Open Alerts",
                      get: (s: StrategyComparisonItem) =>
                        s.coverage.open_alert_count > 0 ? (
                          <span className="text-red-400">{s.coverage.open_alert_count}</span>
                        ) : (
                          0
                        ),
                    },
                    {
                      label: "Latest BT Trust",
                      get: (s: StrategyComparisonItem) => (
                        <span className={scoreColor(s.latest_backtest_trust_score)}>
                          {formatScore(s.latest_backtest_trust_score)}
                        </span>
                      ),
                    },
                    {
                      label: "Latest Data Health",
                      get: (s: StrategyComparisonItem) => (
                        <span className={scoreColor(s.latest_data_health_score)}>
                          {formatScore(s.latest_data_health_score)}
                        </span>
                      ),
                    },
                    {
                      label: "Latest Signal Quality",
                      get: (s: StrategyComparisonItem) => (
                        <span className={scoreColor(s.latest_signal_quality_score)}>
                          {formatScore(s.latest_signal_quality_score)}
                        </span>
                      ),
                    },
                    {
                      label: "Gaps",
                      get: (s: StrategyComparisonItem) =>
                        s.gaps.length > 0 ? (
                          <span className="text-yellow-400 font-mono text-2xs">
                            {s.gaps.length} gap{s.gaps.length !== 1 ? "s" : ""}
                          </span>
                        ) : (
                          <span className="text-green-400 font-mono text-2xs">none</span>
                        ),
                    },
                  ].map((row) => (
                    <tr
                      key={row.label}
                      className="border-b border-border last:border-0 hover:bg-bg-600 transition-colors"
                    >
                      <td className={`${TD} text-text-muted whitespace-nowrap`}>{row.label}</td>
                      {result.strategies.map((s) => (
                        <td key={s.strategy_id} className={`${TD} mono-num`}>
                          {row.get(s)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Disclaimer */}
          <p className="font-mono text-2xs text-text-muted/50 text-center pb-2">
            This comparison is based on logged QuantFidelity evidence only. It is not investment
            advice or a recommendation to trade any strategy.
          </p>
        </div>
      )}
    </>
  );
}
