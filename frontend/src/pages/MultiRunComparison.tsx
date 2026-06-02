/**
 * M34: Multi-Strategy Run Comparison — /strategies/run-compare
 *
 * Compares the latest run evidence across 2–4 strategies.
 * Evidence-based instrumentation comparison only — never investment advice.
 *
 * Language: "higher logged trust score", "better evidenced",
 *           "more complete instrumentation", "requires review"
 * Never: "better strategy", "more profitable", "should trade"
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type {
  Strategy,
  MultiRunComparisonItem,
  MultiRunComparisonResponse,
} from "@/types";
import { getStrategies, compareStrategyRunsMulti } from "@/lib/api";
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

function healthLabelColor(label: string): string {
  const l = label.toLowerCase();
  if (l.includes("strong") || l === "strong") return "text-teal-400";
  if (l.includes("usable") || l === "usable") return "text-text-secondary";
  if (l.includes("review") || l === "review") return "text-yellow-400";
  if (l.includes("weak") || l === "weak") return "text-red-400";
  return "text-text-muted";
}

function fmtNum(v: number | null, decimals = 2): string {
  if (v === null) return "—";
  return v.toFixed(decimals);
}

function fmtScore(v: number | null): string {
  return v !== null ? v.toFixed(0) : "—";
}

const TH =
  "px-3 py-2 text-left font-mono text-2xs uppercase tracking-widest text-text-muted whitespace-nowrap";
const TD = "px-3 py-2 font-mono text-xs";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ScorePill({
  label,
  value,
}: {
  label: string;
  value: number | null;
}) {
  return (
    <div className="flex flex-col items-center rounded border border-border bg-bg-800 px-2 py-1.5 min-w-[72px]">
      <span className="font-mono text-2xs text-text-muted mb-0.5">{label}</span>
      <span className={`mono-num text-sm font-semibold ${scoreColor(value)}`}>
        {fmtScore(value)}
      </span>
    </div>
  );
}

function RunCard({ item }: { item: MultiRunComparisonItem }) {
  const ev = item.evidence;
  return (
    <div className="rounded-card border border-border bg-bg-700 p-4 flex flex-col gap-3 min-w-0">
      {/* Header */}
      <div>
        <Link
          to={`/strategies/${item.strategy_id}`}
          className="text-sm font-medium text-text-primary hover:text-accent-300"
        >
          {item.strategy_name}
        </Link>
        <div className="mt-0.5 flex items-center gap-2 flex-wrap">
          <Badge value={item.asset_class} variant="asset_class" />
          <Badge value={item.status} variant="status" />
        </div>
      </div>

      {/* Run info */}
      <div className="rounded border border-border bg-bg-800 px-3 py-2">
        <p className="font-mono text-2xs text-text-muted truncate">{item.run_name}</p>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          <span className="font-mono text-2xs text-text-muted/70">{item.run_type}</span>
          <span
            className={`font-mono text-2xs font-medium ${healthLabelColor(ev.run_health_label)}`}
          >
            {ev.run_health_label}
          </span>
        </div>
        {item.completed_at && (
          <p className="font-mono text-2xs text-text-muted/60 mt-0.5">
            completed {new Date(item.completed_at).toLocaleDateString()}
          </p>
        )}
        {item.strategy_version_label && (
          <p className="font-mono text-2xs text-text-muted/60">
            v{item.strategy_version_label}
          </p>
        )}
      </div>

      {/* Score pills */}
      <div className="flex gap-2 flex-wrap">
        <ScorePill label="BT Trust" value={ev.backtest_trust_score} />
        <ScorePill label="Data Health" value={ev.dataset_health_score} />
        <ScorePill label="Signal Quality" value={ev.signal_quality_score} />
        <ScorePill label="Ev. Coverage" value={item.evidence_coverage_score} />
      </div>

      {item.open_alert_count > 0 && (
        <p className="font-mono text-2xs text-red-400">
          {item.open_alert_count} open alert{item.open_alert_count !== 1 ? "s" : ""}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function MultiRunComparison() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MultiRunComparisonResponse | null>(null);

  useEffect(() => {
    setLoadingList(true);
    getStrategies()
      .then(setStrategies)
      .catch((err) =>
        setListError(err instanceof Error ? err.message : "Failed to load strategies."),
      )
      .finally(() => setLoadingList(false));
  }, []);

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 4) return prev;
      return [...prev, id];
    });
    setResult(null);
    setError(null);
  }

  async function handleCompare() {
    if (selectedIds.length < 2) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await compareStrategyRunsMulti({
        strategy_ids: selectedIds,
        mode: "latest",
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Comparison failed.");
    } finally {
      setLoading(false);
    }
  }

  const activeStrategies = strategies.filter((s) => s.status !== "archived");

  // Evidence matrix rows
  const evidenceRows: { label: string; key: string; isScore?: boolean }[] = [
    { label: "Dataset Health", key: "dataset_health_score", isScore: true },
    { label: "Dataset Issues", key: "dataset_issue_count" },
    { label: "Signal Quality", key: "signal_quality_score", isScore: true },
    { label: "Signal Missing", key: "signal_missing_count" },
    { label: "Universe Symbols", key: "universe_symbol_count" },
    { label: "Backtest Trust", key: "backtest_trust_score", isScore: true },
    { label: "BT Issues", key: "backtest_issue_count" },
    { label: "Reliability", key: "reliability_score", isScore: true },
    { label: "Evidence Coverage", key: "evidence_coverage_score", isScore: true },
    { label: "Open Alerts", key: "open_alert_count" },
  ];

  // Metric rows
  const metricRows: { label: string; key: string; isInt?: boolean }[] = [
    { label: "Sharpe", key: "sharpe" },
    { label: "Sortino", key: "sortino" },
    { label: "Annual Return", key: "annual_return" },
    { label: "Volatility", key: "volatility" },
    { label: "Max Drawdown", key: "max_drawdown" },
    { label: "Turnover", key: "turnover" },
    { label: "Hit Rate", key: "hit_rate" },
    { label: "Trade Count", key: "trade_count", isInt: true },
    { label: "Alpha bps", key: "alpha_bps" },
    { label: "Transaction Cost bps", key: "transaction_cost_bps" },
  ];

  // Assumption rows
  const assumptionRows: { label: string; key: string }[] = [
    { label: "Transaction Cost", key: "transaction_cost_bps" },
    { label: "Slippage", key: "slippage_bps" },
    { label: "Fill Model", key: "fill_model" },
    { label: "Borrow Cost", key: "borrow_cost_bps" },
    { label: "Short Enabled", key: "short_enabled" },
    { label: "Execution Timing", key: "execution_timing" },
  ];

  // Rankings metadata
  const rankingMeta: { key: string; title: string }[] = [
    { key: "by_backtest_trust", title: "Highest Logged Trust Score" },
    { key: "by_data_health", title: "Strongest Linked Data Health" },
    { key: "by_signal_quality", title: "Best Logged Signal Quality" },
    { key: "by_reliability", title: "Current Reliability Score" },
    { key: "by_evidence_completeness", title: "Most Complete Evidence Coverage" },
  ];

  return (
    <>
      {/* A. Page Header */}
      <PageHeader
        tag="Research"
        title="Multi-Strategy Run Comparison"
        subtitle="Compare logged run evidence across strategies. Not an investment recommendation."
      >
        <Link
          to="/strategies"
          className="rounded-control border border-border px-3.5 py-1.5 text-xs font-mono text-text-muted hover:text-text-primary"
        >
          ← Back to Strategies
        </Link>
      </PageHeader>

      {/* B. Strategy selector */}
      <div className="rounded-card border border-border bg-bg-700 p-4 mb-4">
        <div className="flex items-center justify-between mb-3">
          <p className="font-mono text-xs text-text-secondary">
            Select 2–4 strategies to compare latest runs
            {selectedIds.length > 0 && (
              <span className="ml-2 text-accent-400">({selectedIds.length} selected)</span>
            )}
          </p>
          <button
            onClick={handleCompare}
            disabled={selectedIds.length < 2 || loading}
            className="rounded-control bg-accent-500 px-4 py-1.5 text-xs font-medium text-text-inverse hover:bg-accent-600 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? "Comparing…" : "Compare Latest Runs"}
          </button>
        </div>

        {loadingList && (
          <p className="font-mono text-2xs text-text-muted">Loading strategies…</p>
        )}
        {listError && (
          <p className="font-mono text-xs text-red-400">{listError}</p>
        )}

        {!loadingList && !listError && activeStrategies.length === 0 && (
          <EmptyState
            title="No strategies found"
            description="Register a strategy to get started."
          />
        )}

        {!loadingList && !listError && activeStrategies.length >= 1 && (
          <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 lg:grid-cols-3">
            {activeStrategies.map((s) => {
              const isSelected = selectedIds.includes(s.id);
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
                    disabled={!isSelected && selectedIds.length >= 4}
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
      {error && (
        <div className="rounded-card border border-red-700/40 bg-red-900/10 px-4 py-3 mb-4">
          <p className="font-mono text-xs text-red-400">{error}</p>
        </div>
      )}

      {/* C. Results */}
      {result && (
        <div className="space-y-4">
          {/* Explanation */}
          <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
            <div className="flex items-center justify-between mb-2">
              <p className="font-mono text-2xs uppercase tracking-widest text-text-muted">
                Run Evidence Summary
              </p>
              <p className="font-mono text-2xs text-text-muted/60">
                {new Date(result.compared_at).toLocaleTimeString()} · mode: {result.mode}
              </p>
            </div>
            <p className="text-sm text-text-secondary leading-relaxed italic">
              {result.deterministic_explanation}
            </p>
            {result.highlighted_differences.length > 0 && (
              <ul className="mt-2 list-disc list-inside space-y-0.5">
                {result.highlighted_differences.map((d, i) => (
                  <li key={i} className="font-mono text-2xs text-text-muted">
                    {d}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* D. Run cards */}
          <div>
            <p className="font-mono text-2xs uppercase tracking-widest text-text-muted mb-2">
              Run Evidence Cards
            </p>
            <div
              className="grid gap-4"
              style={{
                gridTemplateColumns: `repeat(${Math.min(result.items.length, 3)}, minmax(0, 1fr))`,
              }}
            >
              {result.items.map((item) => (
                <RunCard key={item.run_id} item={item} />
              ))}
            </div>
          </div>

          {/* E. Evidence matrix */}
          <div>
            <p className="font-mono text-2xs uppercase tracking-widest text-text-muted mb-2">
              Evidence Comparison
            </p>
            <div className="overflow-x-auto rounded-card border border-border">
              <table className="w-full min-w-[600px] text-left">
                <thead>
                  <tr className="border-b border-border bg-bg-800">
                    <th className={TH}>Dimension</th>
                    {result.items.map((item) => (
                      <th key={item.run_id} className={TH}>
                        <Link
                          to={`/strategies/${item.strategy_id}`}
                          className="text-text-primary hover:text-accent-300"
                        >
                          {item.strategy_name}
                        </Link>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {evidenceRows.map((row) => (
                    <tr
                      key={row.key}
                      className="border-b border-border last:border-0 hover:bg-bg-600 transition-colors"
                    >
                      <td className={`${TD} text-text-muted whitespace-nowrap`}>{row.label}</td>
                      {result.items.map((item) => {
                        let val: number | null = null;
                        if (row.key === "reliability_score") val = item.reliability_score;
                        else if (row.key === "evidence_coverage_score") val = item.evidence_coverage_score;
                        else if (row.key === "open_alert_count") val = item.open_alert_count;
                        else {
                          const evVal = (item.evidence as unknown as Record<string, unknown>)[row.key];
                          val = typeof evVal === "number" ? evVal : null;
                        }
                        return (
                          <td key={item.run_id} className={`${TD} mono-num`}>
                            {row.isScore ? (
                              <span className={scoreColor(val)}>{fmtScore(val)}</span>
                            ) : val !== null ? (
                              val
                            ) : (
                              "—"
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* F. Metric matrix */}
          {result.items.some((item) =>
            metricRows.some((r) => (item.metrics as unknown as Record<string, unknown>)[r.key] !== null),
          ) && (
            <div>
              <p className="font-mono text-2xs uppercase tracking-widest text-text-muted mb-2">
                Logged Metrics
              </p>
              <div className="overflow-x-auto rounded-card border border-border">
                <table className="w-full min-w-[600px] text-left">
                  <thead>
                    <tr className="border-b border-border bg-bg-800">
                      <th className={TH}>Metric</th>
                      {result.items.map((item) => (
                        <th key={item.run_id} className={TH}>
                          {item.strategy_name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {metricRows
                      .filter((row) =>
                        result.items.some(
                          (item) =>
                            (item.metrics as unknown as Record<string, unknown>)[row.key] !== null,
                        ),
                      )
                      .map((row) => (
                        <tr
                          key={row.key}
                          className="border-b border-border last:border-0 hover:bg-bg-600 transition-colors"
                        >
                          <td className={`${TD} text-text-muted whitespace-nowrap`}>{row.label}</td>
                          {result.items.map((item) => {
                            const val = (item.metrics as unknown as Record<string, unknown>)[row.key] as
                              | number
                              | null;
                            return (
                              <td key={item.run_id} className={`${TD} mono-num`}>
                                {row.isInt ? (val !== null ? val : "—") : fmtNum(val)}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* G. Assumption matrix */}
          <div>
            <p className="font-mono text-2xs uppercase tracking-widest text-text-muted mb-2">
              Run Assumptions
            </p>
            <div className="overflow-x-auto rounded-card border border-border">
              <table className="w-full min-w-[600px] text-left">
                <thead>
                  <tr className="border-b border-border bg-bg-800">
                    <th className={TH}>Assumption</th>
                    {result.items.map((item) => (
                      <th key={item.run_id} className={TH}>
                        {item.strategy_name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {assumptionRows.map((row) => (
                    <tr
                      key={row.key}
                      className="border-b border-border last:border-0 hover:bg-bg-600 transition-colors"
                    >
                      <td className={`${TD} text-text-muted whitespace-nowrap`}>{row.label}</td>
                      {result.items.map((item) => {
                        const raw = (item.assumptions as unknown as Record<string, unknown>)[row.key];
                        const display =
                          raw === null || raw === undefined
                            ? "—"
                            : typeof raw === "boolean"
                            ? raw ? "yes" : "no"
                            : String(raw);
                        return (
                          <td key={item.run_id} className={`${TD} mono-num`}>
                            {display}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* H. Rankings */}
          {Object.keys(result.rankings).length > 0 && (
            <div>
              <p className="font-mono text-2xs uppercase tracking-widest text-text-muted mb-2">
                Rankings (higher = better evidenced)
              </p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {rankingMeta
                  .filter((m) => result.rankings[m.key]?.length > 0)
                  .map((meta) => (
                    <div
                      key={meta.key}
                      className="rounded-card border border-border bg-bg-700 overflow-hidden"
                    >
                      <div className="px-3 py-2 border-b border-border bg-bg-800">
                        <p className="font-mono text-2xs uppercase tracking-widest text-text-muted">
                          {meta.title}
                        </p>
                      </div>
                      <div className="divide-y divide-border">
                        {result.rankings[meta.key].map((item) => (
                          <div
                            key={item.strategy_id}
                            className="flex items-center gap-2 px-3 py-2"
                          >
                            <span className="font-mono text-2xs text-text-muted w-4">
                              {item.rank}.
                            </span>
                            <span className="flex-1 font-mono text-xs text-text-primary truncate">
                              {item.strategy_name}
                            </span>
                            <span className="font-mono text-xs text-text-secondary mono-num">
                              {item.value_label}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* I. Missing evidence / gaps */}
          {(result.shared_gaps.length > 0 ||
            Object.values(result.gaps).some((g) => g.length > 0)) && (
            <div>
              <p className="font-mono text-2xs uppercase tracking-widest text-text-muted mb-2">
                Instrumentation Gaps
              </p>
              <div className="rounded-card border border-border bg-bg-700 px-4 py-3 space-y-3">
                {result.shared_gaps.length > 0 && (
                  <div>
                    <p className="font-mono text-2xs text-text-muted mb-1">
                      Shared gaps across all strategies:
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {result.shared_gaps.map((g) => (
                        <span
                          key={g}
                          className="inline-flex rounded border border-border bg-bg-600 px-1.5 py-px font-mono text-2xs text-text-muted"
                        >
                          {g}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {result.items.map((item) => {
                  const stratGaps = result.gaps[item.strategy_id] ?? [];
                  if (stratGaps.length === 0) return null;
                  return (
                    <div key={item.run_id}>
                      <p className="font-mono text-2xs text-text-muted mb-1">
                        {item.strategy_name}:
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {stratGaps.map((g) => (
                          <span
                            key={g}
                            className="inline-flex rounded border border-yellow-700/30 bg-yellow-900/20 px-1.5 py-px font-mono text-2xs text-yellow-300"
                          >
                            {g}
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Suggested next steps */}
          {result.suggested_next_steps.length > 0 && (
            <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
              <p className="font-mono text-2xs uppercase tracking-widest text-text-muted mb-2">
                Suggested Next Steps
              </p>
              <ul className="list-disc list-inside space-y-0.5">
                {result.suggested_next_steps.map((s, i) => (
                  <li key={i} className="font-mono text-2xs text-text-muted">
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* J. Disclaimer */}
          <p className="font-mono text-2xs text-text-muted/50 text-center pb-2">
            Comparison is deterministic. Logged metrics may not reflect live trading performance.
            Not investment advice.
          </p>
        </div>
      )}
    </>
  );
}
