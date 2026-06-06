/**
 * Portfolio Reliability (M86)
 *
 * Portfolio-level view of strategy research readiness, evidence health, and
 * blockers. Route: /portfolio/reliability
 *
 * Language policy: deterministic research reliability signals only — not
 * trading or investment advice.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type {
  PortfolioReliabilityResponse,
  PortfolioReliabilityRow,
} from "@/types";
import {
  downloadTextFile,
  exportPortfolioReliability,
  generateAlerts,
  generateWeeklyReviewPack,
  getPortfolioReliability,
  refreshPortfolioScores,
} from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { SkeletonCard } from "@/components/Skeleton";
import { startWalkthrough } from "@/lib/demoWalkthrough";

// ---------------------------------------------------------------------------
// Visual helpers
// ---------------------------------------------------------------------------

const HEALTH_CHIP: Record<string, string> = {
  healthy: "bg-teal-950/60 text-teal-300 border-teal-800/50",
  review: "bg-orange-950/60 text-orange-300 border-orange-800/50",
  blocked: "bg-red-950/60 text-red-300 border-red-800/50",
};

const SEVERITY_TEXT: Record<string, string> = {
  critical: "text-red-300",
  high: "text-orange-300",
  medium: "text-yellow-300",
  low: "text-blue-300",
  info: "text-text-muted",
};

const SEVERITY_CHIP: Record<string, string> = {
  critical: "bg-red-950/60 text-red-300 border-red-800/50",
  high: "bg-orange-950/60 text-orange-300 border-orange-800/50",
  medium: "bg-yellow-950/60 text-yellow-300 border-yellow-800/50",
  low: "bg-blue-950/60 text-blue-300 border-blue-800/50",
  info: "bg-bg-700 text-text-muted border-border",
};

function scoreColor(v: number | null): string {
  if (v === null) return "text-text-muted";
  if (v >= 80) return "text-teal-400";
  if (v >= 60) return "text-yellow-400";
  return "text-red-400";
}

function healthChipClass(c: string): string {
  return HEALTH_CHIP[c] ?? "bg-bg-700 text-text-muted border-border";
}

function severityChipClass(s: string): string {
  return SEVERITY_CHIP[s] ?? "bg-bg-700 text-text-muted border-border";
}

// M87 — review-status chip palette (mirrors the workflow component).
const REVIEW_STATUS_CHIP: Record<string, string> = {
  draft: "border-border bg-bg-700 text-text-muted",
  submitted: "border-blue-800/50 bg-blue-950/50 text-blue-300",
  approved: "border-teal-800/50 bg-teal-950/50 text-teal-300",
  rejected: "border-red-800/50 bg-red-950/50 text-red-300",
  changes_requested: "border-amber-800/50 bg-amber-950/50 text-amber-300",
  cancelled: "border-border bg-bg-700 text-text-muted",
};

function reviewStatusChipClass(s: string): string {
  return REVIEW_STATUS_CHIP[s] ?? "border-border bg-bg-700 text-text-muted";
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function titleCase(v: string): string {
  return v.replace(/_/g, " ");
}

// ---------------------------------------------------------------------------
// Score change arrow
// ---------------------------------------------------------------------------

function ScoreChange({ row }: { row: PortfolioReliabilityRow }) {
  const change = row.recent_score_change;
  if (!change) {
    return (
      <span className="font-mono text-2xs italic text-text-muted/70">
        insufficient history
      </span>
    );
  }
  const dir = change.direction;
  const arrow = dir === "up" ? "▲" : dir === "down" ? "▼" : "▬";
  const color =
    dir === "up"
      ? "text-teal-300"
      : dir === "down"
        ? "text-red-300"
        : "text-text-muted";
  const sign = change.delta > 0 ? "+" : "";
  return (
    <span className={`font-mono text-xs tabular-nums ${color}`}>
      {arrow} {sign}
      {change.delta.toFixed(1)}
    </span>
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
    <div className="flex flex-col gap-1 rounded-card border border-border bg-bg-700 px-4 py-3 shadow-card">
      <span className="text-2xs tracking-eyebrow text-text-muted">{label}</span>
      <span
        className={`font-mono text-xl font-semibold tabular-nums leading-none ${valueClass ?? "text-text-primary"}`}
      >
        {value}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section card
// ---------------------------------------------------------------------------

function SectionCard({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-card border border-border bg-bg-700 shadow-card">
      <div className="flex items-center justify-between border-b border-border/70 px-5 py-3">
        <p className="text-sm font-medium text-text-primary">{title}</p>
        {count != null && (
          <span className="font-mono text-2xs text-text-muted">{count}</span>
        )}
      </div>
      {children}
    </div>
  );
}

function EmptyRow({ text }: { text: string }) {
  return (
    <div className="px-5 py-8 text-center">
      <p className="text-sm text-text-muted">{text}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Toolbar button
// ---------------------------------------------------------------------------

function ToolbarButton({
  label,
  onClick,
  busy,
  variant = "default",
}: {
  label: string;
  onClick: () => void;
  busy?: boolean;
  variant?: "default" | "accent";
}) {
  const base =
    variant === "accent"
      ? "border-accent-600 bg-accent-900/30 text-accent-300 hover:bg-accent-900/50"
      : "border-border bg-bg-600 text-text-secondary hover:border-border-strong hover:text-text-primary";
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className={`rounded border px-3 py-1.5 font-mono text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${base}`}
    >
      {busy ? "Working…" : label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Filter select
// ---------------------------------------------------------------------------

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex items-center gap-1.5">
      <span className="font-mono text-2xs uppercase tracking-wider text-text-muted">
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-border bg-bg-800 px-2 py-1 font-mono text-2xs text-text-secondary focus:outline-none focus:ring-1 focus:ring-accent-500"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Table styling tokens
// ---------------------------------------------------------------------------

const TH = "px-3 py-2.5 text-left text-2xs font-medium text-text-muted tracking-eyebrow whitespace-nowrap";
const TD = "px-3 py-3 align-top";

// ---------------------------------------------------------------------------
// Sort options
// ---------------------------------------------------------------------------

type SortKey =
  | "reliability_desc"
  | "reliability_asc"
  | "worst_blockers"
  | "stale_evidence"
  | "score_drop"
  | "last_run";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "reliability_desc", label: "Reliability ↓" },
  { value: "reliability_asc", label: "Reliability ↑" },
  { value: "worst_blockers", label: "Worst blockers first" },
  { value: "stale_evidence", label: "Stale evidence first" },
  { value: "score_drop", label: "Most recent score drop" },
  { value: "last_run", label: "Last run date" },
];

const SEVERITY_RANK: Record<string, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
  info: 0,
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function PortfolioReliability() {
  const navigate = useNavigate();

  const [data, setData] = useState<PortfolioReliabilityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ msg: string; isError: boolean } | null>(
    null,
  );

  // Filters / sorting (client-side)
  const [search, setSearch] = useState("");
  const [healthFilter, setHealthFilter] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [assetFilter, setAssetFilter] = useState("");
  const [projectFilter, setProjectFilter] = useState("");
  const [blockerFilter, setBlockerFilter] = useState("");
  const [missingReportFilter, setMissingReportFilter] = useState("");
  const [staleFilter, setStaleFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("worst_blockers");

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    getPortfolioReliability()
      .then(setData)
      .catch((e: unknown) =>
        setError(
          e instanceof Error ? e.message : "Failed to load portfolio reliability",
        ),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const rows = data?.strategies ?? [];

  // Distinct filter option sets derived from the data
  const stageOptions = useMemo(
    () => Array.from(new Set(rows.map((r) => r.promotion_stage))).sort(),
    [rows],
  );
  const assetOptions = useMemo(
    () => Array.from(new Set(rows.map((r) => r.asset_class))).sort(),
    [rows],
  );
  const projectOptions = useMemo(
    () => Array.from(new Set(rows.map((r) => r.project_name))).sort(),
    [rows],
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const out = rows.filter((r) => {
      if (q && !r.name.toLowerCase().includes(q)) return false;
      if (healthFilter && r.health_classification !== healthFilter) return false;
      if (stageFilter && r.promotion_stage !== stageFilter) return false;
      if (assetFilter && r.asset_class !== assetFilter) return false;
      if (projectFilter && r.project_name !== projectFilter) return false;
      if (blockerFilter === "yes" && !r.top_blocker) return false;
      if (blockerFilter === "no" && r.top_blocker) return false;
      if (missingReportFilter === "yes" && !r.missing_report) return false;
      if (missingReportFilter === "no" && r.missing_report) return false;
      if (staleFilter === "yes" && r.stale_evidence_count <= 0) return false;
      if (staleFilter === "no" && r.stale_evidence_count > 0) return false;
      if (severityFilter) {
        const minRank = SEVERITY_RANK[severityFilter] ?? 0;
        const blockerRank = r.top_blocker
          ? (SEVERITY_RANK[r.top_blocker.severity] ?? 0)
          : -1;
        if (blockerRank < minRank) return false;
      }
      return true;
    });

    const sorted = [...out];
    sorted.sort((a, b) => {
      switch (sortKey) {
        case "reliability_asc":
          return (a.reliability_score ?? -1) - (b.reliability_score ?? -1);
        case "reliability_desc":
          return (b.reliability_score ?? -1) - (a.reliability_score ?? -1);
        case "worst_blockers": {
          const ra = a.top_blocker ? (SEVERITY_RANK[a.top_blocker.severity] ?? 0) : -1;
          const rb = b.top_blocker ? (SEVERITY_RANK[b.top_blocker.severity] ?? 0) : -1;
          if (rb !== ra) return rb - ra;
          return b.high_critical_alert_count - a.high_critical_alert_count;
        }
        case "stale_evidence":
          return b.stale_evidence_count - a.stale_evidence_count;
        case "score_drop": {
          const da = a.recent_score_change?.delta ?? 0;
          const db = b.recent_score_change?.delta ?? 0;
          return da - db; // most negative first
        }
        case "last_run": {
          const ta = a.latest_run_at ? new Date(a.latest_run_at).getTime() : 0;
          const tb = b.latest_run_at ? new Date(b.latest_run_at).getTime() : 0;
          return tb - ta;
        }
        default:
          return 0;
      }
    });
    return sorted;
  }, [
    rows,
    search,
    healthFilter,
    stageFilter,
    assetFilter,
    projectFilter,
    blockerFilter,
    missingReportFilter,
    staleFilter,
    severityFilter,
    sortKey,
  ]);

  // -------------------------------------------------------------------------
  // Mutating actions
  // -------------------------------------------------------------------------

  async function runAction(
    key: string,
    fn: () => Promise<void>,
    successMsg?: string,
  ) {
    setBusyAction(key);
    setNotice(null);
    try {
      await fn();
      if (successMsg) setNotice({ msg: successMsg, isError: false });
    } catch (e: unknown) {
      setNotice({
        msg: e instanceof Error ? e.message : "Action failed",
        isError: true,
      });
    } finally {
      setBusyAction(null);
    }
  }

  function handleExport(format: "json" | "markdown") {
    void runAction(`export-${format}`, async () => {
      const res = await exportPortfolioReliability(format);
      const mime = format === "json" ? "application/json" : "text/markdown";
      downloadTextFile(res.filename, res.content, mime);
    });
  }

  function handleWeeklyPack() {
    void runAction("weekly-pack", async () => {
      const res = await generateWeeklyReviewPack("markdown");
      downloadTextFile(res.filename, res.content, "text/markdown");
    });
  }

  function handleRefreshScores() {
    void runAction(
      "refresh-scores",
      async () => {
        const res = await refreshPortfolioScores();
        reload();
        setNotice({
          msg: `Refreshed ${res.strategies_refreshed} strategy scores.`,
          isError: false,
        });
      },
    );
  }

  function handleGenerateAlerts() {
    void runAction("generate-alerts", async () => {
      const res = await generateAlerts();
      reload();
      setNotice({
        msg: `Generated alerts: +${res.alerts_created} created · ${res.alerts_auto_resolved} auto-resolved.`,
        isError: false,
      });
    });
  }

  function openDetail(strategyId: string) {
    navigate(`/strategies/${strategyId}`);
  }

  function openBlocker(strategyId: string, tab: string) {
    navigate(`/strategies/${strategyId}?tab=${encodeURIComponent(tab)}`);
  }

  function openReview(strategyId: string) {
    navigate(`/strategies/${strategyId}?tab=governance`);
  }

  const summary = data?.summary;

  return (
    <div className="space-y-6">
      <PageHeader
        tag="Analysis"
        title="Portfolio Reliability"
        subtitle="Portfolio-level view of strategy research readiness, evidence health, and blockers."
      />

      {/* M91: Guided demo trigger */}
      <div className="mb-4 flex items-center justify-end">
        <button
          type="button"
          onClick={() => startWalkthrough(true)}
          className="rounded-control border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 text-xs font-medium text-accent-400 hover:bg-accent-500/20 transition-colors"
        >
          Start guided demo
        </button>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <ToolbarButton
          label="Compare strategies"
          onClick={() => navigate("/strategies/compare")}
        />
        <ToolbarButton
          label="Export JSON"
          busy={busyAction === "export-json"}
          onClick={() => handleExport("json")}
        />
        <ToolbarButton
          label="Export Markdown"
          busy={busyAction === "export-markdown"}
          onClick={() => handleExport("markdown")}
        />
        <ToolbarButton
          label="Generate weekly review pack"
          busy={busyAction === "weekly-pack"}
          onClick={handleWeeklyPack}
        />
        <ToolbarButton
          label="Refresh portfolio scores"
          busy={busyAction === "refresh-scores"}
          onClick={handleRefreshScores}
        />
        <ToolbarButton
          label="Generate alerts for all strategies"
          variant="accent"
          busy={busyAction === "generate-alerts"}
          onClick={handleGenerateAlerts}
        />
      </div>

      {notice && (
        <div
          className={`rounded border px-4 py-2 font-mono text-2xs ${
            notice.isError
              ? "border-red-800 bg-red-900/20 text-red-300"
              : "border-teal-700/40 bg-teal-900/20 text-teal-300"
          }`}
        >
          {notice.msg}
        </div>
      )}

      {error && (
        <div className="rounded-control border border-red-800/60 bg-red-950/30 px-4 py-3 text-sm text-red-300">
          <p>{error}</p>
          <button
            onClick={reload}
            className="mt-2 rounded border border-red-700/50 bg-red-900/30 px-2.5 py-1 font-mono text-2xs text-red-200 hover:bg-red-900/50"
          >
            Retry
          </button>
        </div>
      )}

      {loading && <SkeletonCard />}

      {!loading && !error && data && rows.length === 0 && (
        <EmptyState
          title="No strategies"
          description="Register strategies to begin tracking portfolio-level reliability, evidence health, and blockers."
        />
      )}

      {!loading && !error && data && rows.length > 0 && summary && (
        <>
          {/* Manager summary cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <SummaryTile label="Total" value={String(summary.total_strategies)} />
            <SummaryTile
              label="Healthy"
              value={String(summary.healthy_count)}
              valueClass="text-teal-300"
            />
            <SummaryTile
              label="In review"
              value={String(summary.review_count)}
              valueClass="text-orange-300"
            />
            <SummaryTile
              label="Blocked"
              value={String(summary.blocked_count)}
              valueClass={summary.blocked_count > 0 ? "text-red-300" : undefined}
            />
            <SummaryTile
              label="Average reliability"
              value={
                summary.average_reliability !== null
                  ? summary.average_reliability.toFixed(1)
                  : "—"
              }
              valueClass={scoreColor(summary.average_reliability)}
            />
            <SummaryTile
              label="Stale evidence"
              value={String(summary.strategies_with_stale_evidence)}
              valueClass={
                summary.strategies_with_stale_evidence > 0
                  ? "text-orange-300"
                  : undefined
              }
            />
            <SummaryTile
              label="Missing reports"
              value={String(summary.strategies_missing_reports)}
              valueClass={
                summary.strategies_missing_reports > 0
                  ? "text-orange-300"
                  : undefined
              }
            />
            <SummaryTile
              label="Open high/critical alerts"
              value={String(summary.open_high_critical_alerts)}
              valueClass={
                summary.open_high_critical_alerts > 0 ? "text-red-300" : undefined
              }
            />
            <SummaryTile
              label="Ready for paper"
              value={String(summary.ready_for_paper_candidate)}
            />
            <SummaryTile
              label="Ready for production"
              value={String(summary.ready_for_production_candidate)}
            />
          </div>

          {/* Top sections */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <SectionCard title="Worst Blockers" count={data.worst_blockers.length}>
              {data.worst_blockers.length === 0 ? (
                <EmptyRow text="No blockers across the portfolio." />
              ) : (
                <div className="px-5">
                  {data.worst_blockers.slice(0, 5).map((b, i) => (
                    <div
                      key={`${b.strategy_id}-${i}`}
                      className="flex items-start gap-3 border-b border-border/60 py-3 last:border-0"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-text-primary">
                          {b.strategy_name}
                        </p>
                        <p className="mt-0.5 text-xs text-text-secondary leading-snug">
                          {b.blocker_title}
                        </p>
                        <p className="mt-0.5 text-2xs text-text-muted leading-snug">
                          {b.recommended_action}
                        </p>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1.5">
                        <span
                          className={`rounded-chip border px-1.5 py-0.5 text-2xs ${severityChipClass(b.severity)}`}
                        >
                          {b.severity}
                        </span>
                        <button
                          onClick={() => openBlocker(b.strategy_id, b.target_tab)}
                          className="font-mono text-2xs text-accent-500 hover:text-accent-300"
                        >
                          Open blocker →
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </SectionCard>

            <SectionCard title="Stale Evidence" count={data.stale_evidence.length}>
              {data.stale_evidence.length === 0 ? (
                <EmptyRow text="No stale evidence detected." />
              ) : (
                <div className="px-5">
                  {data.stale_evidence.map((s) => (
                    <div
                      key={s.strategy_id}
                      className="flex items-center gap-3 border-b border-border/60 py-3 last:border-0"
                    >
                      <button
                        onClick={() => openDetail(s.strategy_id)}
                        className="min-w-0 flex-1 truncate text-left text-sm font-medium text-text-primary hover:text-accent-300"
                      >
                        {s.strategy_name}
                      </button>
                      <div className="flex shrink-0 items-center gap-2 font-mono text-2xs text-text-muted tabular-nums">
                        <span className="text-orange-300">{s.stale_count} stale</span>
                        <span>{s.aging_count} aging</span>
                        <span>{s.missing_count} missing</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </SectionCard>

            <SectionCard
              title="Missing Reports"
              count={data.missing_reports.length}
            >
              {data.missing_reports.length === 0 ? (
                <EmptyRow text="All strategies have current reports." />
              ) : (
                <div className="px-5">
                  {data.missing_reports.map((m) => (
                    <div
                      key={m.strategy_id}
                      className="flex items-center gap-3 border-b border-border/60 py-3 last:border-0"
                    >
                      <button
                        onClick={() => openDetail(m.strategy_id)}
                        className="min-w-0 flex-1 truncate text-left text-sm font-medium text-text-primary hover:text-accent-300"
                      >
                        {m.strategy_name}
                      </button>
                      <span className="shrink-0 font-mono text-2xs text-text-muted whitespace-nowrap">
                        last run {fmtDate(m.latest_run_at)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </SectionCard>

            <SectionCard
              title="Recent Score Changes"
              count={data.recent_score_changes.length}
            >
              {data.recent_score_changes.length === 0 ? (
                <EmptyRow text="No recent score changes (insufficient history)." />
              ) : (
                <div className="px-5">
                  {data.recent_score_changes.map((c) => {
                    const color =
                      c.direction === "up"
                        ? "text-teal-300"
                        : c.direction === "down"
                          ? "text-red-300"
                          : "text-text-muted";
                    const arrow =
                      c.direction === "up"
                        ? "▲"
                        : c.direction === "down"
                          ? "▼"
                          : "▬";
                    const sign = c.delta > 0 ? "+" : "";
                    return (
                      <div
                        key={c.strategy_id}
                        className="flex items-center gap-3 border-b border-border/60 py-3 last:border-0"
                      >
                        <button
                          onClick={() => openDetail(c.strategy_id)}
                          className="min-w-0 flex-1 truncate text-left text-sm font-medium text-text-primary hover:text-accent-300"
                        >
                          {c.strategy_name}
                        </button>
                        <div className="flex shrink-0 items-center gap-2 font-mono text-2xs tabular-nums">
                          <span className={color}>
                            {arrow} {sign}
                            {c.delta.toFixed(1)}
                          </span>
                          <span className="text-text-muted">
                            {c.previous.toFixed(0)} → {c.latest.toFixed(0)}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </SectionCard>
          </div>

          {/* Filters + sort */}
          <div className="flex flex-wrap items-center gap-3 rounded-card border border-border bg-bg-700 px-4 py-3">
            <label className="flex items-center gap-1.5">
              <span className="font-mono text-2xs uppercase tracking-wider text-text-muted">
                Search
              </span>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="strategy name"
                className="w-44 rounded border border-border bg-bg-800 px-2 py-1 font-mono text-2xs text-text-secondary placeholder:text-text-muted/50 focus:outline-none focus:ring-1 focus:ring-accent-500"
              />
            </label>
            <FilterSelect
              label="Health"
              value={healthFilter}
              onChange={setHealthFilter}
              options={[
                { value: "", label: "All" },
                { value: "healthy", label: "Healthy" },
                { value: "review", label: "Review" },
                { value: "blocked", label: "Blocked" },
              ]}
            />
            <FilterSelect
              label="Stage"
              value={stageFilter}
              onChange={setStageFilter}
              options={[
                { value: "", label: "All" },
                ...stageOptions.map((s) => ({ value: s, label: titleCase(s) })),
              ]}
            />
            <FilterSelect
              label="Asset"
              value={assetFilter}
              onChange={setAssetFilter}
              options={[
                { value: "", label: "All" },
                ...assetOptions.map((a) => ({ value: a, label: titleCase(a) })),
              ]}
            />
            <FilterSelect
              label="Project"
              value={projectFilter}
              onChange={setProjectFilter}
              options={[
                { value: "", label: "All" },
                ...projectOptions.map((p) => ({ value: p, label: p })),
              ]}
            />
            <FilterSelect
              label="Blockers"
              value={blockerFilter}
              onChange={setBlockerFilter}
              options={[
                { value: "", label: "All" },
                { value: "yes", label: "Has blockers" },
                { value: "no", label: "No blockers" },
              ]}
            />
            <FilterSelect
              label="Missing report"
              value={missingReportFilter}
              onChange={setMissingReportFilter}
              options={[
                { value: "", label: "All" },
                { value: "yes", label: "Missing" },
                { value: "no", label: "Present" },
              ]}
            />
            <FilterSelect
              label="Stale"
              value={staleFilter}
              onChange={setStaleFilter}
              options={[
                { value: "", label: "All" },
                { value: "yes", label: "Has stale" },
                { value: "no", label: "None" },
              ]}
            />
            <FilterSelect
              label="Alert sev"
              value={severityFilter}
              onChange={setSeverityFilter}
              options={[
                { value: "", label: "All" },
                { value: "critical", label: "Critical+" },
                { value: "high", label: "High+" },
                { value: "medium", label: "Medium+" },
                { value: "low", label: "Low+" },
              ]}
            />
            <FilterSelect
              label="Sort"
              value={sortKey}
              onChange={(v) => setSortKey(v as SortKey)}
              options={SORT_OPTIONS}
            />
            <span className="ml-auto font-mono text-2xs text-text-muted">
              {filtered.length} of {rows.length}
            </span>
          </div>

          {/* Ranked strategy table */}
          <div className="rounded-card border border-border bg-bg-700 shadow-card">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border/60 bg-bg-800/60">
                    <th className={TH}>Strategy</th>
                    <th className={TH}>Project</th>
                    <th className={TH}>Asset</th>
                    <th className={TH}>Status</th>
                    <th className={TH}>Reliability</th>
                    <th className={TH}>Health</th>
                    <th className={TH}>Promotion stage</th>
                    <th className={TH}>Open alerts</th>
                    <th className={TH}>Top blocker</th>
                    <th className={TH}>Review</th>
                    <th className={TH}>Stale evidence</th>
                    <th className={TH}>Missing report</th>
                    <th className={TH}>Recent score change</th>
                    <th className={TH}>Last run</th>
                    <th className={TH}>Owner</th>
                    <th className={TH}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr>
                      <td
                        colSpan={16}
                        className="px-4 py-10 text-center text-sm text-text-muted"
                      >
                        No strategies match the selected filters.
                      </td>
                    </tr>
                  ) : (
                    filtered.map((r) => (
                      <tr
                        key={r.strategy_id}
                        className="border-b border-border/60 last:border-0 hover:bg-bg-600/50 transition-colors"
                      >
                        <td className={TD}>
                          <button
                            onClick={() => openDetail(r.strategy_id)}
                            className="text-left text-sm font-medium text-text-primary hover:text-accent-300 transition-colors"
                          >
                            {r.name}
                          </button>
                        </td>
                        <td className={`${TD} text-xs text-text-secondary whitespace-nowrap`}>
                          {r.project_name}
                        </td>
                        <td className={`${TD} text-xs text-text-secondary whitespace-nowrap`}>
                          {titleCase(r.asset_class)}
                        </td>
                        <td className={`${TD} text-xs text-text-muted whitespace-nowrap`}>
                          {titleCase(r.status)}
                        </td>
                        <td className={TD}>
                          {r.reliability_score !== null ? (
                            <span
                              className={`font-mono text-sm tabular-nums ${scoreColor(r.reliability_score)}`}
                            >
                              {r.reliability_score.toFixed(0)}
                            </span>
                          ) : (
                            <span className="text-text-muted">—</span>
                          )}
                        </td>
                        <td className={TD}>
                          <span
                            className={`inline-flex items-center rounded-chip border px-2 py-0.5 text-2xs ${healthChipClass(r.health_classification)}`}
                          >
                            {r.health_classification}
                          </span>
                        </td>
                        <td className={`${TD} text-xs text-text-secondary whitespace-nowrap`}>
                          {titleCase(r.promotion_stage)}
                        </td>
                        <td className={TD}>
                          {r.open_alert_count > 0 ? (
                            <span className="font-mono text-sm tabular-nums text-orange-300">
                              {r.open_alert_count}
                              {r.high_critical_alert_count > 0 && (
                                <span className="ml-1 text-2xs text-red-300">
                                  ({r.high_critical_alert_count} h/c)
                                </span>
                              )}
                            </span>
                          ) : (
                            <span className="font-mono text-sm text-text-muted">0</span>
                          )}
                        </td>
                        <td className={`${TD} max-w-[200px]`}>
                          {r.top_blocker ? (
                            <div className="flex flex-col gap-0.5">
                              <span
                                className={`text-xs ${SEVERITY_TEXT[r.top_blocker.severity] ?? "text-text-secondary"}`}
                              >
                                {r.top_blocker.title}
                              </span>
                              <span className="text-2xs text-text-muted">
                                {titleCase(r.top_blocker.category)}
                              </span>
                            </div>
                          ) : (
                            <span className="text-text-muted">—</span>
                          )}
                        </td>
                        <td className={TD}>
                          {r.pending_review ? (
                            <div className="flex flex-col gap-0.5">
                              <span
                                className={`inline-flex w-fit items-center rounded-chip border px-1.5 py-0.5 font-mono text-2xs ${reviewStatusChipClass(r.pending_review.status)}`}
                              >
                                {titleCase(r.pending_review.status)}
                              </span>
                              <span className="text-2xs text-text-muted whitespace-nowrap">
                                → {titleCase(r.pending_review.target_stage)}
                              </span>
                            </div>
                          ) : (
                            <span className="text-text-muted">—</span>
                          )}
                        </td>
                        <td className={TD}>
                          {r.stale_evidence_count > 0 ? (
                            <span className="font-mono text-sm tabular-nums text-orange-300">
                              {r.stale_evidence_count}
                            </span>
                          ) : (
                            <span className="font-mono text-sm text-text-muted">0</span>
                          )}
                        </td>
                        <td className={TD}>
                          {r.missing_report ? (
                            <span className="font-mono text-2xs text-red-300">yes</span>
                          ) : (
                            <span className="font-mono text-2xs text-text-muted">no</span>
                          )}
                        </td>
                        <td className={`${TD} whitespace-nowrap`}>
                          <ScoreChange row={r} />
                        </td>
                        <td className={`${TD} font-mono text-2xs text-text-muted whitespace-nowrap tabular-nums`}>
                          {fmtDate(r.latest_run_at)}
                        </td>
                        <td className={`${TD} text-xs text-text-secondary whitespace-nowrap`}>
                          {r.owner_name ?? <span className="text-text-muted">—</span>}
                        </td>
                        <td className={TD}>
                          <div className="flex flex-col gap-1">
                            <button
                              onClick={() => openDetail(r.strategy_id)}
                              className="text-left font-mono text-2xs text-accent-500 hover:text-accent-300 whitespace-nowrap"
                            >
                              Open detail →
                            </button>
                            {r.top_blocker && (
                              <button
                                onClick={() =>
                                  openBlocker(r.strategy_id, r.top_blocker!.target_tab)
                                }
                                className="text-left font-mono text-2xs text-orange-300 hover:text-orange-200 whitespace-nowrap"
                              >
                                Open blocker →
                              </button>
                            )}
                            {r.pending_review && (
                              <button
                                onClick={() => openReview(r.strategy_id)}
                                className="text-left font-mono text-2xs text-accent-500 hover:text-accent-300 whitespace-nowrap"
                              >
                                Open review →
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Footer disclaimer */}
          <p className="pb-2 text-center text-2xs text-text-muted">
            {data.disclaimer}
          </p>
        </>
      )}
    </div>
  );
}
