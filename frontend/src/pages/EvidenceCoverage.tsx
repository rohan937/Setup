/**
 * Evidence Coverage Matrix (M21)
 *
 * Shows which strategies are instrumented and which evidence layers are missing.
 * Route: /evidence/coverage
 *
 * Language policy:
 *   Use: "Evidence Coverage", "Instrumentation Coverage", "Missing Evidence",
 *        "Review Required", "Suggested Next Steps", "Coverage Matrix"
 *   Avoid: AI recommendations, investment advice, alpha language
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type {
  EvidenceCoverageCell,
  EvidenceCoverageMatrixResponse,
  EvidenceCoverageParams,
  StrategyEvidenceCoverageRow,
} from "@/types";
import { getEvidenceCoverage } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import Badge from "@/components/Badge";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const COLUMNS: Array<{
  key: keyof StrategyEvidenceCoverageRow;
  label: string;
  abbr: string;
}> = [
  { key: "strategy_runs",    label: "Runs",     abbr: "Runs" },
  { key: "backtest_runs",    label: "Backtests", abbr: "BT" },
  { key: "dataset_evidence", label: "Data",      abbr: "Data" },
  { key: "backtest_audits",  label: "Audits",    abbr: "Audit" },
  { key: "config_snapshots", label: "Config",    abbr: "Cfg" },
  { key: "universe_snapshots", label: "Universe", abbr: "Uni" },
  { key: "signal_snapshots", label: "Signal",    abbr: "Sig" },
  { key: "alerts",           label: "Alerts",    abbr: "Alerts" },
  { key: "reports",          label: "Reports",   abbr: "Rpt" },
  { key: "reliability_scores", label: "Score",   abbr: "Score" },
  { key: "timeline_events",  label: "Timeline",  abbr: "TL" },
];

// ---------------------------------------------------------------------------
// Cell status helpers
// ---------------------------------------------------------------------------

const STATUS_DOT: Record<string, string> = {
  complete: "bg-teal-400",
  partial:  "bg-yellow-400",
  review:   "bg-orange-400",
  missing:  "bg-bg-500 border border-border",
};

const STATUS_TEXT: Record<string, string> = {
  complete: "text-teal-400",
  partial:  "text-yellow-400",
  review:   "text-orange-400",
  missing:  "text-text-muted",
};

const STATUS_BG: Record<string, string> = {
  complete: "bg-teal-900/20",
  partial:  "bg-yellow-900/20",
  review:   "bg-orange-900/20",
  missing:  "bg-bg-800",
};

function coverageColor(score: number): string {
  if (score >= 80) return "text-teal-400";
  if (score >= 50) return "text-yellow-400";
  if (score >= 25) return "text-orange-400";
  return "text-red-400";
}

function coverageBarWidth(score: number): string {
  return `${Math.max(2, Math.round(score))}%`;
}

function coverageBarColor(score: number): string {
  if (score >= 80) return "bg-teal-500/70";
  if (score >= 50) return "bg-yellow-500/70";
  if (score >= 25) return "bg-orange-500/70";
  return "bg-red-500/70";
}

// ---------------------------------------------------------------------------
// Cell component — compact dot + count
// ---------------------------------------------------------------------------

function CoverageCell({ cell }: { cell: EvidenceCoverageCell }) {
  const dot = STATUS_DOT[cell.status] ?? STATUS_DOT.missing;
  const countColor = STATUS_TEXT[cell.status] ?? STATUS_TEXT.missing;
  return (
    <div className="flex flex-col items-center gap-0.5" title={`${cell.summary}${cell.suggested_check ? `\n→ ${cell.suggested_check}` : ""}`}>
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      <span className={`mono-num text-2xs font-medium ${countColor}`}>
        {cell.count > 0 ? cell.count : "—"}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary card strip
// ---------------------------------------------------------------------------

function SummaryCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
      <p className="font-mono text-2xs uppercase tracking-wider text-text-muted">{label}</p>
      <p className={`mono-num mt-1 text-2xl font-bold ${color ?? "text-text-primary"}`}>
        {value}
      </p>
      {sub && <p className="mt-0.5 font-mono text-2xs text-text-muted">{sub}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status legend pill
// ---------------------------------------------------------------------------

function LegendPill({
  status,
  label,
}: {
  status: string;
  label: string;
}) {
  const dot = STATUS_DOT[status] ?? STATUS_DOT.missing;
  const text = STATUS_TEXT[status] ?? STATUS_TEXT.missing;
  return (
    <span className={`inline-flex items-center gap-1.5 font-mono text-2xs ${text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Suggested next steps panel
// ---------------------------------------------------------------------------

function SuggestedPanel({ missing }: { missing: string[] }) {
  if (missing.length === 0) return null;
  return (
    <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
      <p className="caption mb-2">Most Common Missing Evidence</p>
      <ul className="space-y-1">
        {missing.map((label, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-bg-500 border border-border" />
            <span className="font-mono text-xs text-text-secondary">{label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Filter bar
// ---------------------------------------------------------------------------

const ASSET_CLASSES = ["", "equity", "fx", "rates", "commodities", "crypto", "alternatives"];
const STRATEGY_STATUSES = ["", "active", "inactive", "archived", "paper", "live"];

function FilterBar({
  assetClass,
  status,
  onAssetClass,
  onStatus,
}: {
  assetClass: string;
  status: string;
  onAssetClass: (v: string) => void;
  onStatus: (v: string) => void;
}) {
  const selectCls =
    "rounded border border-border bg-bg-800 px-2 py-1 font-mono text-xs text-text-secondary focus:outline-none focus:border-accent-500/50";
  return (
    <div className="flex flex-wrap items-center gap-3">
      <p className="font-mono text-2xs text-text-muted">Filter:</p>
      <div className="flex items-center gap-1.5">
        <label className="font-mono text-2xs text-text-muted">Asset</label>
        <select
          value={assetClass}
          onChange={(e) => onAssetClass(e.target.value)}
          className={selectCls}
        >
          {ASSET_CLASSES.map((ac) => (
            <option key={ac} value={ac}>
              {ac || "All"}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-1.5">
        <label className="font-mono text-2xs text-text-muted">Status</label>
        <select
          value={status}
          onChange={(e) => onStatus(e.target.value)}
          className={selectCls}
        >
          {STRATEGY_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s || "All"}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const TH =
  "px-2 py-2 text-center font-mono text-2xs uppercase tracking-widest text-text-muted";
const TH_LEFT =
  "px-4 py-2 text-left font-mono text-2xs uppercase tracking-widest text-text-muted";

export default function EvidenceCoverage() {
  const [data, setData] = useState<EvidenceCoverageMatrixResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [assetClass, setAssetClass] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const load = useCallback(
    (params: EvidenceCoverageParams = {}) => {
      setLoading(true);
      setError(null);
      getEvidenceCoverage(params)
        .then(setData)
        .catch((e: unknown) =>
          setError(e instanceof Error ? e.message : "Failed to load coverage matrix."),
        )
        .finally(() => setLoading(false));
    },
    [],
  );

  useEffect(() => {
    load({
      asset_class: assetClass || undefined,
      status: statusFilter || undefined,
    });
  }, [load, assetClass, statusFilter]);

  const summary = data?.summary;
  const items = data?.items ?? [];

  // Top under-instrumented strategies (lowest coverage score, at most 5)
  const underInstrumented = [...items]
    .sort((a, b) => a.evidence_coverage_score - b.evidence_coverage_score)
    .slice(0, 5)
    .filter((r) => r.evidence_coverage_score < 80);

  return (
    <>
      <PageHeader
        tag="Analysis"
        title="Evidence Coverage Matrix"
        subtitle="See which strategies are instrumented and which evidence layers are missing."
      >
        <Link
          to="/strategies/compare"
          className="rounded-control border border-border bg-bg-700 px-3.5 py-1.5 text-xs font-medium text-text-secondary hover:border-accent-500/50 hover:text-accent-300"
        >
          Compare Strategies
        </Link>
      </PageHeader>

      {/* Error */}
      {error && (
        <div className="rounded-card border border-fidelity-low/30 bg-fidelity-low/10 px-4 py-3">
          <p className="font-mono text-xs text-fidelity-low">{error}</p>
          <button
            onClick={() => load({ asset_class: assetClass || undefined, status: statusFilter || undefined })}
            className="mt-1.5 font-mono text-2xs text-accent-500 hover:text-accent-300"
          >
            retry
          </button>
        </div>
      )}

      {/* Summary cards */}
      {!loading && summary && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <SummaryCard
            label="Strategies"
            value={summary.strategy_count}
            sub="in coverage matrix"
          />
          <SummaryCard
            label="Avg Coverage"
            value={`${summary.average_coverage_score.toFixed(1)}`}
            sub="out of 100"
            color={coverageColor(summary.average_coverage_score)}
          />
          <SummaryCard
            label="Missing Cells"
            value={summary.missing_cell_count}
            sub="evidence not logged"
            color={summary.missing_cell_count > 0 ? "text-text-muted" : "text-teal-400"}
          />
          <SummaryCard
            label="Review Cells"
            value={summary.review_cell_count}
            sub="below quality threshold"
            color={summary.review_cell_count > 0 ? "text-orange-400" : "text-teal-400"}
          />
        </div>
      )}

      {loading && (
        <p className="font-mono text-2xs text-text-muted">Loading coverage matrix…</p>
      )}

      {!loading && !error && items.length === 0 && (
        <EmptyState
          title="No strategies found"
          description="Register a strategy and log evidence to see coverage."
        />
      )}

      {!loading && !error && items.length > 0 && (
        <>
          {/* Filter bar + legend */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <FilterBar
              assetClass={assetClass}
              status={statusFilter}
              onAssetClass={setAssetClass}
              onStatus={setStatusFilter}
            />
            <div className="flex flex-wrap items-center gap-4">
              <LegendPill status="complete" label="Complete" />
              <LegendPill status="partial"  label="Partial" />
              <LegendPill status="review"   label="Review Required" />
              <LegendPill status="missing"  label="Missing" />
            </div>
          </div>

          {/* Matrix table */}
          <div className="overflow-x-auto rounded-card border border-border">
            <table className="w-full min-w-[900px]">
              <thead>
                <tr className="border-b border-border bg-bg-800">
                  <th className={TH_LEFT} style={{ minWidth: 200 }}>Strategy</th>
                  <th className={TH_LEFT} style={{ minWidth: 120 }}>Coverage</th>
                  {COLUMNS.map((col) => (
                    <th key={col.key} className={TH} style={{ minWidth: 54 }} title={col.label}>
                      {col.abbr}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((row, i) => (
                  <MatrixRow
                    key={row.strategy_id}
                    row={row}
                    isLast={i === items.length - 1}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {/* Bottom panels: suggested next steps + under-instrumented list */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {summary && (
              <SuggestedPanel missing={summary.most_common_missing_evidence} />
            )}

            {underInstrumented.length > 0 && (
              <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
                <p className="caption mb-2">Under-instrumented Strategies</p>
                <table className="w-full">
                  <tbody>
                    {underInstrumented.map((r) => (
                      <tr key={r.strategy_id} className="border-b border-border last:border-0">
                        <td className="py-1.5 pr-3">
                          <Link
                            to={`/strategies/${r.strategy_id}`}
                            className="font-mono text-xs text-text-secondary hover:text-accent-300"
                          >
                            {r.name}
                          </Link>
                        </td>
                        <td className="py-1.5 pr-3">
                          <span
                            className={`mono-num text-sm font-semibold ${coverageColor(r.evidence_coverage_score)}`}
                          >
                            {r.evidence_coverage_score.toFixed(0)}
                          </span>
                          <span className="font-mono text-2xs text-text-muted">/100</span>
                        </td>
                        <td className="py-1.5">
                          <span className="font-mono text-2xs text-text-muted">
                            {r.missing_count} missing
                            {r.review_count > 0 ? `, ${r.review_count} review` : ""}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Pagination hint */}
          {data && data.total > data.limit && (
            <p className="font-mono text-2xs text-text-muted text-right">
              Showing {items.length} of {data.total} strategies
            </p>
          )}
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// MatrixRow
// ---------------------------------------------------------------------------

function MatrixRow({
  row,
  isLast,
}: {
  row: StrategyEvidenceCoverageRow;
  isLast: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const score = row.evidence_coverage_score;

  return (
    <>
      <tr
        className={`hover:bg-bg-600 transition-colors cursor-pointer ${
          isLast && !expanded ? "" : "border-b border-border"
        }`}
        onClick={() => setExpanded((v) => !v)}
      >
        {/* Strategy name */}
        <td className="px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="font-mono text-2xs text-text-muted">{expanded ? "▾" : "▸"}</span>
            <Link
              to={`/strategies/${row.strategy_id}`}
              className="text-sm font-medium text-text-primary hover:text-accent-300"
              onClick={(e) => e.stopPropagation()}
            >
              {row.name}
            </Link>
          </div>
          <div className="ml-5 mt-0.5 flex gap-1.5">
            <Badge value={row.asset_class} variant="asset_class" />
            <Badge value={row.status} variant="status" />
          </div>
        </td>

        {/* Coverage score + bar */}
        <td className="px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className={`mono-num text-sm font-semibold ${coverageColor(score)}`}>
              {score.toFixed(0)}
            </span>
            <div className="flex-1 h-1.5 rounded-full bg-bg-600 max-w-[80px]">
              <div
                className={`h-1.5 rounded-full ${coverageBarColor(score)}`}
                style={{ width: coverageBarWidth(score) }}
              />
            </div>
          </div>
          <p className="font-mono text-2xs text-text-muted mt-0.5">
            {row.missing_count > 0 && (
              <span className="text-text-muted">{row.missing_count} missing</span>
            )}
            {row.review_count > 0 && (
              <span className="text-orange-400 ml-1.5">{row.review_count} review</span>
            )}
            {row.partial_count > 0 && (
              <span className="text-yellow-400 ml-1.5">{row.partial_count} partial</span>
            )}
          </p>
        </td>

        {/* Evidence cells */}
        {COLUMNS.map((col) => {
          const cell = row[col.key] as EvidenceCoverageCell;
          return (
            <td key={col.key} className={`px-2 py-2.5 ${STATUS_BG[cell.status] ?? ""}`}>
              <CoverageCell cell={cell} />
            </td>
          );
        })}
      </tr>

      {/* Expanded detail row */}
      {expanded && (
        <tr className={isLast ? "" : "border-b border-border"}>
          <td colSpan={COLUMNS.length + 2} className="bg-bg-800 px-6 py-3">
            <ExpandedDetail row={row} />
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// ExpandedDetail — shown when row is clicked
// ---------------------------------------------------------------------------

function ExpandedDetail({ row }: { row: StrategyEvidenceCoverageRow }) {
  const cells: Array<{ label: string; cell: EvidenceCoverageCell }> = COLUMNS.map((col) => ({
    label: col.label,
    cell: row[col.key] as EvidenceCoverageCell,
  }));

  const steps = row.suggested_next_steps;

  return (
    <div className="space-y-3">
      {/* Cell summary grid */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3 lg:grid-cols-4">
        {cells.map(({ label, cell }) => (
          <div key={label} className="flex items-start gap-2 py-0.5">
            <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${STATUS_DOT[cell.status] ?? STATUS_DOT.missing}`} />
            <div className="min-w-0">
              <p className="font-mono text-2xs text-text-muted">{label}</p>
              <p className={`font-mono text-xs ${STATUS_TEXT[cell.status] ?? STATUS_TEXT.missing}`}>
                {cell.summary}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Suggested next steps */}
      {steps.length > 0 && (
        <div>
          <p className="font-mono text-2xs text-text-muted mb-1">Suggested Next Steps</p>
          <ul className="space-y-1">
            {steps.map((step, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-500/50" />
                <span className="font-mono text-xs text-text-secondary">{step}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {steps.length === 0 && (
        <p className="font-mono text-2xs text-teal-400">
          All evidence layers are complete or under review. No immediate actions required.
        </p>
      )}
    </div>
  );
}
