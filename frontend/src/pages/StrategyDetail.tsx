import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type {
  BacktestAudit,
  BacktestIssue,
  BacktestStatus,
  CostSensitivityScenario,
  DataEvidenceSummary,
  ReportDetail,
  SignalSnapshotRead,
  SignalSnapshotSummary,
  StrategyConfigSnapshotRead,
  StrategyDetail as StrategyDetailType,
  StrategyRun,
  StrategyVersion,
  TimelineEvent,
  UniverseSnapshotRead,
  UniverseSnapshotSummary,
} from "@/types";
import { generateStrategyReport, getStrategy, getStrategyTimeline, runBacktestAudit } from "@/lib/api";
import Badge from "@/components/Badge";
import ConfigSnapshotDrawer from "@/components/ConfigSnapshotDrawer";
import RunLogDrawer from "@/components/RunLogDrawer";
import RunComparisonPanel from "@/components/RunComparisonPanel";
import SignalSnapshotDrawer from "@/components/SignalSnapshotDrawer";
import UniverseSnapshotDrawer from "@/components/UniverseSnapshotDrawer";
import VersionCreateDrawer from "@/components/VersionCreateDrawer";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function fmtDateShort(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

function StatCell({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="caption mb-1">{label}</p>
      <p className="mono-num text-sm font-medium text-text-primary">{value}</p>
    </div>
  );
}

function MetricChip({ label, value }: { label: string; value: unknown }) {
  return (
    <span className="inline-flex items-baseline gap-1.5 rounded-chip border border-border px-2 py-1">
      <span className="font-mono text-2xs text-text-muted">{label}</span>
      <span className="mono-num text-sm font-semibold text-text-primary">{String(value)}</span>
    </span>
  );
}

const BackArrow = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
    <path d="M7.5 2L3.5 6l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

// ---------------------------------------------------------------------------
// Data evidence helpers
// ---------------------------------------------------------------------------

function healthColor(score: number): string {
  if (score >= 90) return "text-fidelity-high";
  if (score >= 60) return "text-fidelity-medium";
  return "text-fidelity-low";
}

function healthBg(score: number): string {
  if (score >= 90) return "border-fidelity-high/30 bg-fidelity-high/10";
  if (score >= 60) return "border-fidelity-medium/30 bg-fidelity-medium/10";
  return "border-fidelity-low/30 bg-fidelity-low/10";
}

function severityColor(s: string | null): string {
  switch (s) {
    case "critical": return "text-fidelity-low";
    case "high":     return "text-fidelity-low";
    case "medium":   return "text-fidelity-medium";
    default:         return "text-text-muted";
  }
}

// ---------------------------------------------------------------------------
// Inline data evidence chip for run evidence rows
// ---------------------------------------------------------------------------

function DataEvidenceChip({ ev }: { ev: DataEvidenceSummary }) {
  return (
    <div className={`mt-2.5 rounded-control border px-3 py-2 ${healthBg(ev.health_score)}`}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <div className="flex items-center gap-1.5">
          <span className="caption">data</span>
          <span className={`mono-num text-sm font-semibold ${healthColor(ev.health_score)}`}>
            {ev.health_score}/100
          </span>
        </div>
        <span className="font-mono text-2xs text-text-secondary">
          {ev.dataset_name}
        </span>
        <span className="font-mono text-2xs text-text-muted">
          {ev.snapshot_label}
        </span>
        <span className="font-mono text-2xs text-text-muted">
          {ev.row_count.toLocaleString()} rows
        </span>
        {ev.symbol_count > 0 && (
          <span className="font-mono text-2xs text-text-muted">
            {ev.symbol_count} symbol{ev.symbol_count !== 1 ? "s" : ""}
          </span>
        )}
        {ev.min_timestamp && ev.max_timestamp && (
          <span className="font-mono text-2xs text-text-muted">
            {ev.min_timestamp} → {ev.max_timestamp}
          </span>
        )}
        {ev.issue_count > 0 ? (
          <span className={`font-mono text-2xs ${severityColor(ev.worst_severity)}`}>
            {ev.issue_count} issue{ev.issue_count !== 1 ? "s" : ""}
            {ev.worst_severity ? ` · worst: ${ev.worst_severity}` : ""}
          </span>
        ) : (
          <span className="font-mono text-2xs text-fidelity-high">no issues</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Data Evidence summary panel (M7) — shows best (most recent) linked snapshot
// ---------------------------------------------------------------------------

function DataEvidencePanel({ runs }: { runs: StrategyRun[] }) {
  const linkedRuns = runs.filter((r) => r.dataset_snapshot !== null);
  if (linkedRuns.length === 0) return null;

  // Use the most recent run that has linked evidence.
  const latest = linkedRuns[0];
  const ev = latest.dataset_snapshot!;

  return (
    <div className="rounded-card border border-border bg-bg-700">
      <div className="border-b border-border px-4 py-2.5">
        <p className="caption">Data Evidence</p>
      </div>
      <div className="p-4 space-y-3">
        {/* Health score bar */}
        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between">
            <span className="font-mono text-xs text-text-secondary">
              {ev.dataset_name} · {ev.snapshot_label}
            </span>
            <span className={`mono-num text-lg font-bold ${healthColor(ev.health_score)}`}>
              {ev.health_score}
              <span className="text-xs font-normal text-text-muted">/100</span>
            </span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-bg-600">
            <div
              className={`h-1.5 rounded-full transition-all ${
                ev.health_score >= 90
                  ? "bg-fidelity-high"
                  : ev.health_score >= 60
                    ? "bg-fidelity-medium"
                    : "bg-fidelity-low"
              }`}
              style={{ width: `${ev.health_score}%` }}
            />
          </div>
        </div>

        {/* Evidence stats */}
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 font-mono text-2xs text-text-muted sm:grid-cols-4">
          <div>
            <p className="caption mb-0.5">Rows</p>
            <p className="mono-num text-text-secondary">{ev.row_count.toLocaleString()}</p>
          </div>
          <div>
            <p className="caption mb-0.5">Symbols</p>
            <p className="mono-num text-text-secondary">{ev.symbol_count}</p>
          </div>
          <div>
            <p className="caption mb-0.5">Columns</p>
            <p className="mono-num text-text-secondary">{ev.column_count}</p>
          </div>
          <div>
            <p className="caption mb-0.5">Issues</p>
            <p className={`mono-num ${ev.issue_count > 0 ? severityColor(ev.worst_severity) : "text-fidelity-high"}`}>
              {ev.issue_count === 0 ? "none" : `${ev.issue_count} · ${ev.worst_severity}`}
            </p>
          </div>
        </div>

        {ev.min_timestamp && (
          <p className="font-mono text-2xs text-text-muted">
            range: {ev.min_timestamp} → {ev.max_timestamp}
          </p>
        )}

        <p className="font-mono text-2xs text-text-muted">
          from run:{" "}
          <span className="text-text-secondary">{latest.run_name}</span>
          {" · "}
          {fmtDateShort(latest.created_at)}
          {linkedRuns.length > 1 && (
            <span> · {linkedRuns.length} run{linkedRuns.length !== 1 ? "s" : ""} linked</span>
          )}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Universe evidence helpers (M16)
// ---------------------------------------------------------------------------

function UniverseEvidenceChip({ uni }: { uni: UniverseSnapshotSummary }) {
  return (
    <div className="mt-2 rounded-control border border-accent-500/20 bg-accent-500/5 px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <div className="flex items-center gap-1.5">
          <span className="caption">universe</span>
          <span className="mono-num text-sm font-semibold text-accent-300">
            {uni.symbol_count}
          </span>
          <span className="font-mono text-2xs text-text-muted">symbols</span>
        </div>
        <span className="font-mono text-2xs text-text-secondary">{uni.label}</span>
        <span
          className="font-mono text-2xs text-text-muted/60 cursor-default"
          title={uni.universe_hash}
        >
          hash: {uni.universe_hash.slice(0, 8)}…
        </span>
      </div>
    </div>
  );
}

function UniverseEvidencePanel({
  universeSnapshots,
  onLogUniverse,
}: {
  universeSnapshots: UniverseSnapshotRead[];
  onLogUniverse: () => void;
}) {
  return (
    <div className="rounded-card border border-border bg-bg-700">
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <p className="caption">Universe Evidence</p>
        <button
          onClick={onLogUniverse}
          className="rounded-control border border-border px-2.5 py-1 font-mono text-2xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
        >
          + Log Universe
        </button>
      </div>
      <div className="p-4">
        {universeSnapshots.length === 0 ? (
          <p className="font-mono text-2xs text-text-muted">
            No universe snapshots logged yet. Log a snapshot to track eligible symbol coverage over time.
          </p>
        ) : (
          <div className="space-y-2">
            {universeSnapshots.slice(0, 5).map((us) => (
              <div key={us.id} className="flex items-start justify-between gap-3 rounded-control border border-border/60 bg-bg-800 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-xs text-text-secondary">{us.label}</p>
                  <div className="mt-0.5 flex flex-wrap gap-3 font-mono text-2xs text-text-muted">
                    <span className="mono-num text-accent-300 font-semibold">
                      {us.symbol_count} symbols
                    </span>
                    <span>{us.source_type}</span>
                    {us.source_filename && <span>{us.source_filename}</span>}
                    <span
                      className="text-text-muted/50 cursor-default"
                      title={us.universe_hash}
                    >
                      hash: {us.universe_hash.slice(0, 8)}…
                    </span>
                  </div>
                </div>
                <span className="shrink-0 font-mono text-2xs text-text-muted whitespace-nowrap">
                  {fmtDateShort(us.created_at)}
                </span>
              </div>
            ))}
            {universeSnapshots.length > 5 && (
              <p className="font-mono text-2xs text-text-muted/60 pt-1">
                + {universeSnapshots.length - 5} more snapshot{universeSnapshots.length - 5 !== 1 ? "s" : ""}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Signal evidence helpers (M17)
// ---------------------------------------------------------------------------

function SignalEvidenceChip({ sig }: { sig: SignalSnapshotSummary }) {
  return (
    <div className="mt-2 rounded-control border border-accent-500/20 bg-accent-500/5 px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <div className="flex items-center gap-1.5">
          <span className="caption">signal</span>
          <span className={`mono-num text-sm font-semibold ${healthColor(sig.quality_score)}`}>
            {sig.quality_score}/100
          </span>
        </div>
        {sig.signal_name && (
          <span className="font-mono text-2xs text-accent-300">{sig.signal_name}</span>
        )}
        <span className="font-mono text-2xs text-text-secondary">{sig.label}</span>
        <span className="font-mono text-2xs text-text-muted">
          {sig.symbol_count} symbol{sig.symbol_count !== 1 ? "s" : ""}
        </span>
        {sig.mean_value !== null && (
          <span className="font-mono text-2xs text-text-muted">
            mean: {sig.mean_value.toFixed(3)}
          </span>
        )}
        {sig.stddev_value !== null && (
          <span className="font-mono text-2xs text-text-muted">
            σ: {sig.stddev_value.toFixed(3)}
          </span>
        )}
      </div>
    </div>
  );
}

function SignalEvidencePanel({
  signalSnapshots,
  onLogSignal,
}: {
  signalSnapshots: SignalSnapshotRead[];
  onLogSignal: () => void;
}) {
  return (
    <div className="rounded-card border border-border bg-bg-700">
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <p className="caption">Signal Evidence</p>
        <button
          onClick={onLogSignal}
          className="rounded-control border border-border px-2.5 py-1 font-mono text-2xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
        >
          + Log Signal
        </button>
      </div>
      <div className="p-4">
        {signalSnapshots.length === 0 ? (
          <p className="font-mono text-2xs text-text-muted">
            No signal snapshots logged yet. Log a snapshot to track signal distributions and coverage over time.
          </p>
        ) : (
          <div className="space-y-2">
            {signalSnapshots.slice(0, 5).map((ss) => (
              <div key={ss.id} className="flex items-start justify-between gap-3 rounded-control border border-border/60 bg-bg-800 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-xs text-text-secondary">{ss.label}</p>
                  <div className="mt-0.5 flex flex-wrap gap-3 font-mono text-2xs text-text-muted">
                    <span className={`mono-num font-semibold ${healthColor(ss.quality_score)}`}>
                      quality: {ss.quality_score}/100
                    </span>
                    <span className="mono-num text-accent-300">
                      {ss.symbol_count} symbols
                    </span>
                    <span>{ss.row_count} rows</span>
                    {ss.signal_name && (
                      <span className="text-accent-300/80">{ss.signal_name}</span>
                    )}
                    {ss.source_type && <span>{ss.source_type}</span>}
                    <span
                      className="text-text-muted/50 cursor-default"
                      title={ss.signal_hash}
                    >
                      hash: {ss.signal_hash.slice(0, 8)}…
                    </span>
                  </div>
                </div>
                <span className="shrink-0 font-mono text-2xs text-text-muted whitespace-nowrap">
                  {fmtDateShort(ss.created_at)}
                </span>
              </div>
            ))}
            {signalSnapshots.length > 5 && (
              <p className="font-mono text-2xs text-text-muted/60 pt-1">
                + {signalSnapshots.length - 5} more snapshot{signalSnapshots.length - 5 !== 1 ? "s" : ""}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Backtest audit helpers (M8)
// ---------------------------------------------------------------------------

function trustColor(score: number): string {
  if (score >= 75) return "text-fidelity-high";
  if (score >= 50) return "text-fidelity-medium";
  return "text-fidelity-low";
}

function statusStyle(status: BacktestStatus): string {
  switch (status) {
    case "excellent":
      return "border-fidelity-high/30 bg-fidelity-high/10 text-fidelity-high";
    case "good":
      return "border-fidelity-high/20 bg-fidelity-high/5 text-fidelity-high";
    case "review":
      return "border-fidelity-medium/30 bg-fidelity-medium/10 text-fidelity-medium";
    case "weak":
      return "border-fidelity-low/30 bg-fidelity-low/10 text-fidelity-low";
    case "unreliable":
      return "border-fidelity-low/50 bg-fidelity-low/20 text-fidelity-low";
  }
}

function issueSeverityColor(severity: string): string {
  switch (severity) {
    case "critical":
    case "high":
      return "text-fidelity-low";
    case "medium":
      return "text-fidelity-medium";
    default:
      return "text-text-muted";
  }
}

function issueSeverityDot(severity: string): string {
  switch (severity) {
    case "critical":
    case "high":
      return "bg-fidelity-low";
    case "medium":
      return "bg-fidelity-medium";
    default:
      return "bg-text-muted";
  }
}

function TrustScoreBar({ score }: { score: number }) {
  const bar =
    score >= 75 ? "bg-fidelity-high" : score >= 50 ? "bg-fidelity-medium" : "bg-fidelity-low";
  return (
    <div className="h-1 w-full rounded-full bg-bg-600">
      <div className={`h-1 rounded-full transition-all ${bar}`} style={{ width: `${score}%` }} />
    </div>
  );
}

function AuditIssueRow({ issue }: { issue: BacktestIssue }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="py-2 first:pt-0 last:pb-0">
      <button
        className="flex w-full items-start gap-2 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${issueSeverityDot(issue.severity)}`} />
        <div className="flex-1 min-w-0">
          <span className={`font-mono text-xs font-medium ${issueSeverityColor(issue.severity)}`}>
            {issue.title}
          </span>
          <span className="ml-2 font-mono text-2xs text-text-muted/60">[{issue.severity}]</span>
        </div>
        <span className="shrink-0 font-mono text-2xs text-text-muted/50">{expanded ? "▲" : "▼"}</span>
      </button>
      {expanded && (
        <div className="mt-1.5 ml-3.5 space-y-1.5">
          <p className="text-xs text-text-secondary leading-relaxed">{issue.description}</p>
          {issue.suggested_check && (
            <p className="font-mono text-2xs text-accent-300">
              ↳ {issue.suggested_check}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Audit Trail panel (M10) — compact 5-event preview for this strategy
// ---------------------------------------------------------------------------

function auditEventTypeBadgeClass(type: string): string {
  const palette: Record<string, string> = {
    strategy_created:
      "bg-teal-900/30 text-teal-400 border-teal-700/30",
    strategy_run_logged:
      "bg-blue-900/30 text-blue-400 border-blue-700/30",
    dataset_snapshot_uploaded:
      "bg-violet-900/30 text-violet-400 border-violet-700/30",
    backtest_audited:
      "bg-orange-900/30 text-orange-400 border-orange-700/30",
  };
  return palette[type] ?? "bg-bg-600 text-text-muted border-border";
}

function AuditTrailPanel({ strategyId }: { strategyId: string }) {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    getStrategyTimeline(strategyId, { limit: 5 })
      .then((resp) => {
        setEvents(resp.items);
        setTotal(resp.total);
      })
      .catch(() => {}); // non-critical — don't surface timeline errors on strategy page
  }, [strategyId]);

  if (events.length === 0) return null;

  return (
    <div className="rounded-card border border-border bg-bg-700">
      <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
        <p className="caption">Audit Trail</p>
        <Link
          to="/timeline"
          className="font-mono text-2xs text-accent-500 hover:text-accent-300"
        >
          full trail →
        </Link>
      </div>
      <div className="divide-y divide-border px-4">
        {events.map((ev) => (
          <div key={ev.id} className="flex items-start gap-2.5 py-2.5">
            <span
              className={`mt-0.5 inline-block rounded border px-1.5 py-0.5 font-mono text-2xs leading-none shrink-0 ${auditEventTypeBadgeClass(ev.event_type)}`}
            >
              {ev.event_type.replace(/_/g, " ")}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs text-text-secondary leading-snug truncate">
                {ev.title}
              </p>
            </div>
            <span className="shrink-0 font-mono text-2xs text-text-muted whitespace-nowrap">
              {new Date(ev.event_time).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })}
            </span>
          </div>
        ))}
      </div>
      {total > 5 && (
        <div className="border-t border-border px-4 py-2 text-center">
          <span className="font-mono text-2xs text-text-muted">
            {total - 5} more event{total - 6 !== 0 ? "s" : ""} — see full trail
          </span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// M13 sub-components for BacktestAuditPanel
// ---------------------------------------------------------------------------

function fragilityLevelBadge(level: string | null | undefined): string {
  switch (level) {
    case "high":
    case "weak":
      return "border-fidelity-low/30 bg-fidelity-low/10 text-fidelity-low";
    case "medium":
    case "review":
      return "border-fidelity-medium/30 bg-fidelity-medium/10 text-fidelity-medium";
    case "low":
    case "strong":
    case "acceptable":
      return "border-fidelity-high/30 bg-fidelity-high/10 text-fidelity-high";
    default:
      return "border-border bg-bg-600 text-text-muted";
  }
}

/** Inline Sharpe value coloured by threshold. */
function SharpeValue({ v }: { v: number | null }) {
  if (v === null) return <span className="text-text-muted">—</span>;
  const cls = v < 0 ? "text-fidelity-low" : v < 1.0 ? "text-fidelity-medium" : "text-fidelity-high";
  return <span className={cls}>{v.toFixed(2)}</span>;
}

/** Compact table of cost scenarios. */
function CostSensitivityTable({ scenarios, baseSharpe, baseReturn }: {
  scenarios: CostSensitivityScenario[];
  baseSharpe: number | null;
  baseReturn: number | null;
}) {
  const standard = [5, 10, 15, 25, 50];
  const filtered = scenarios.filter((s) => standard.includes(s.cost_bps));

  if (filtered.length === 0) return null;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-2xs font-mono">
        <thead>
          <tr className="border-b border-border/50">
            <th className="py-1 pr-3 text-text-muted font-normal">Cost</th>
            <th className="py-1 pr-3 text-text-muted font-normal">Adj. Return</th>
            <th className="py-1 pr-3 text-text-muted font-normal">Adj. Sharpe</th>
            <th className="py-1 text-text-muted font-normal">ΔSharpe</th>
          </tr>
        </thead>
        <tbody>
          {/* Baseline row */}
          <tr className="border-b border-border/30">
            <td className="py-1 pr-3 text-text-muted">base</td>
            <td className="py-1 pr-3 text-text-secondary">
              {baseReturn !== null ? `${(baseReturn * 100).toFixed(1)}%` : "—"}
            </td>
            <td className="py-1 pr-3">
              <SharpeValue v={baseSharpe} />
            </td>
            <td className="py-1 text-text-muted">—</td>
          </tr>
          {filtered.map((s) => (
            <tr key={s.cost_bps} className="border-b border-border/20 last:border-0">
              <td className="py-1 pr-3 text-text-secondary">{s.cost_bps} bps</td>
              <td className="py-1 pr-3 text-text-secondary">
                {s.adjusted_annual_return !== null
                  ? `${(s.adjusted_annual_return * 100).toFixed(1)}%`
                  : "—"}
              </td>
              <td className="py-1 pr-3">
                <SharpeValue v={s.adjusted_sharpe} />
              </td>
              <td className="py-1">
                {s.sharpe_delta !== null ? (
                  <span className={s.sharpe_delta < 0 ? "text-fidelity-low" : "text-fidelity-high"}>
                    {s.sharpe_delta > 0 ? "+" : ""}{s.sharpe_delta.toFixed(2)}
                  </span>
                ) : (
                  <span className="text-text-muted">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BacktestAuditPanel({ audit }: { audit: BacktestAudit }) {
  const [showCostDetail, setShowCostDetail] = useState(false);
  const [showFillDetail, setShowFillDetail] = useState(false);

  const cs = audit.cost_sensitivity_json;
  const fr = audit.fill_realism_json;
  const fs = audit.fragility_summary_json;

  const hasCostData = cs !== null && cs.scenarios.length > 0;
  const hasFillData = fr !== null;
  const hasFragility = fs !== null;

  return (
    <div className="mt-3 rounded-control border border-border bg-bg-800 p-3 space-y-3">
      {/* Header: trust score + status */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <span className="caption">Backtest Audit</span>
          <span className={`mono-num text-lg font-bold leading-none ${trustColor(audit.trust_score)}`}>
            {audit.trust_score}
            <span className="text-xs font-normal text-text-muted">/100</span>
          </span>
        </div>
        <span className={`rounded-chip border px-2 py-0.5 font-mono text-xs font-medium ${statusStyle(audit.overall_status)}`}>
          {audit.overall_status}
        </span>
      </div>

      {/* Trust score bar */}
      <TrustScoreBar score={audit.trust_score} />

      {/* Summary */}
      <p className="text-xs text-text-secondary leading-relaxed">{audit.summary}</p>

      {/* M13: Fragility summary key concerns */}
      {hasFragility && fs!.key_concerns.length > 0 && (
        <div className="rounded-control border border-fidelity-medium/20 bg-fidelity-medium/5 px-2.5 py-2 space-y-1">
          <p className="caption text-fidelity-medium">Fragility concerns</p>
          {fs!.key_concerns.map((concern, i) => (
            <p key={i} className="font-mono text-2xs text-fidelity-medium leading-relaxed">
              • {concern}
            </p>
          ))}
        </div>
      )}

      {/* Subscores */}
      <div className="grid grid-cols-5 gap-1.5 rounded-control border border-border/50 bg-bg-700 px-3 py-2">
        {[
          { label: "Cost", value: audit.cost_realism_score },
          { label: "Fill", value: audit.fill_realism_score },
          { label: "Liquidity", value: audit.liquidity_realism_score },
          { label: "Borrow", value: audit.borrow_realism_score },
          { label: "Data", value: audit.data_quality_score },
        ].map(({ label, value }) => (
          <div key={label} className="text-center">
            <p className="caption mb-0.5 truncate text-2xs">{label}</p>
            <p className={`mono-num text-sm font-semibold ${trustColor(value)}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* M13: Cost Sensitivity section */}
      {hasCostData && (
        <div className="rounded-control border border-border/50 bg-bg-700">
          <button
            className="flex w-full items-center justify-between px-3 py-2"
            onClick={() => setShowCostDetail((v) => !v)}
          >
            <div className="flex items-center gap-2">
              <p className="caption">Cost Sensitivity</p>
              {cs!.cost_fragility_level !== "unknown" && (
                <span className={`rounded-chip border px-1.5 py-0.5 font-mono text-2xs ${fragilityLevelBadge(cs!.cost_fragility_level)}`}>
                  {cs!.cost_fragility_level}
                </span>
              )}
            </div>
            <span className="font-mono text-2xs text-text-muted/60">
              {showCostDetail ? "▲" : "▼"}
            </span>
          </button>
          {showCostDetail && (
            <div className="border-t border-border/50 px-3 py-2 space-y-2">
              <p className="font-mono text-2xs text-text-muted italic">
                Estimated only — not a full re-backtest. Treat values as indicative.
              </p>
              <CostSensitivityTable
                scenarios={cs!.scenarios}
                baseSharpe={cs!.base_sharpe}
                baseReturn={cs!.base_annual_return}
              />
              {cs!.warnings.slice(1).map((w, i) => (
                <p key={i} className="font-mono text-2xs text-text-muted">
                  ⚠ {w}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* M13: Fill Realism section */}
      {hasFillData && (
        <div className="rounded-control border border-border/50 bg-bg-700">
          <button
            className="flex w-full items-center justify-between px-3 py-2"
            onClick={() => setShowFillDetail((v) => !v)}
          >
            <div className="flex items-center gap-2">
              <p className="caption">Fill Realism</p>
              {fr!.fill_realism_level !== "unknown" && (
                <span className={`rounded-chip border px-1.5 py-0.5 font-mono text-2xs ${fragilityLevelBadge(fr!.fill_realism_level)}`}>
                  {fr!.fill_realism_level}
                </span>
              )}
              {fr!.fill_model && (
                <span className="font-mono text-2xs text-text-muted">
                  model: {fr!.fill_model}
                </span>
              )}
            </div>
            <span className="font-mono text-2xs text-text-muted/60">
              {showFillDetail ? "▲" : "▼"}
            </span>
          </button>
          {showFillDetail && (
            <div className="border-t border-border/50 px-3 py-2 space-y-1.5">
              {fr!.findings.length === 0 ? (
                <p className="font-mono text-2xs text-fidelity-high">
                  ✓ No fill realism concerns noted
                </p>
              ) : (
                fr!.findings
                  .filter((f) => f.code !== "missing_slippage")
                  .map((f, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span
                        className={`mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                          f.severity === "high" || f.severity === "critical"
                            ? "bg-fidelity-low"
                            : f.severity === "medium"
                              ? "bg-fidelity-medium"
                              : "bg-text-muted"
                        }`}
                      />
                      <p
                        className={`font-mono text-2xs leading-relaxed ${
                          f.severity === "high" || f.severity === "critical"
                            ? "text-fidelity-low"
                            : f.severity === "medium"
                              ? "text-fidelity-medium"
                              : "text-text-muted"
                        }`}
                      >
                        {f.message}
                      </p>
                    </div>
                  ))
              )}
              {fr!.slippage_bps !== null && (
                <p className="font-mono text-2xs text-text-muted">
                  slippage: {fr!.slippage_bps} bps
                </p>
              )}
              {fr!.execution_timing && (
                <p className="font-mono text-2xs text-text-muted">
                  execution timing: {fr!.execution_timing}
                </p>
              )}
              {fr!.participation_rate !== null && (
                <p className="font-mono text-2xs text-text-muted">
                  participation rate: {(fr!.participation_rate * 100).toFixed(0)}%
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Issues */}
      {audit.issues.length === 0 ? (
        <p className="font-mono text-2xs text-fidelity-high">✓ No realism concerns detected</p>
      ) : (
        <div className="divide-y divide-border/50">
          {audit.issues.map((issue) => (
            <AuditIssueRow key={issue.id} issue={issue} />
          ))}
        </div>
      )}

      <p className="font-mono text-2xs text-text-muted/50">
        audited {fmtDateShort(audit.created_at)}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// M15: Version & Config Evidence section
// ---------------------------------------------------------------------------

function VersionRow({ version, snapshots }: {
  version: StrategyVersion;
  snapshots: StrategyConfigSnapshotRead[];
}) {
  const [expanded, setExpanded] = useState(false);
  const versionSnaps = snapshots.filter((s) => s.strategy_version_id === version.id);
  const count = versionSnaps.length;

  return (
    <div className="py-3 first:pt-0 last:pb-0">
      {/* Version header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="mono-num text-sm font-semibold text-text-primary">
              {version.version_label}
            </span>
            {count > 0 && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="rounded-chip border border-border px-1.5 py-0.5 font-mono text-2xs text-text-muted hover:border-accent-500/40 hover:text-accent-300"
              >
                {count} config{count !== 1 ? "s" : ""} {expanded ? "▲" : "▼"}
              </button>
            )}
          </div>
          {version.signal_name && (
            <p className="mt-0.5 font-mono text-xs text-text-secondary">
              signal: <span className="text-accent-300">{version.signal_name}</span>
            </p>
          )}
          {version.branch_name && (
            <p className="mt-0.5 font-mono text-2xs text-text-muted">
              {version.branch_name}
              {version.code_path && <span> · {version.code_path}</span>}
              {version.git_commit && <span> · <span className="text-accent-300/70">{version.git_commit.slice(0, 7)}</span></span>}
            </p>
          )}
          {version.signal_description && (
            <p className="mt-1 max-w-xl text-xs text-text-muted leading-relaxed">
              {version.signal_description}
            </p>
          )}
        </div>
        <span className="shrink-0 font-mono text-2xs text-text-muted whitespace-nowrap">
          {fmtDateShort(version.created_at)}
        </span>
      </div>

      {/* Inline config snapshots */}
      {expanded && count > 0 && (
        <div className="mt-2 ml-3 space-y-1.5 border-l border-border/50 pl-3">
          {versionSnaps.map((s) => (
            <div key={s.id} className="rounded-control border border-border/60 bg-bg-800 px-2.5 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs text-text-secondary">{s.label}</span>
                <span className="font-mono text-2xs text-text-muted">{s.source_type}</span>
              </div>
              <div className="mt-0.5 flex flex-wrap gap-3 font-mono text-2xs text-text-muted">
                {s.param_count > 0 && <span>{s.param_count} param{s.param_count !== 1 ? "s" : ""}</span>}
                {s.assumption_count > 0 && <span>{s.assumption_count} assumption{s.assumption_count !== 1 ? "s" : ""}</span>}
                <span title={s.config_hash} className="text-text-muted/60 truncate max-w-24">
                  {s.config_hash.slice(0, 8)}…
                </span>
                <span>{fmtDateShort(s.created_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ConfigSnapshotRow({ snapshot }: { snapshot: StrategyConfigSnapshotRead }) {
  return (
    <div className="flex items-start justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
      <div className="min-w-0 flex-1">
        <p className="font-mono text-xs text-text-secondary">{snapshot.label}</p>
        <div className="mt-0.5 flex flex-wrap gap-3 font-mono text-2xs text-text-muted">
          <span>{snapshot.source_type}</span>
          {snapshot.param_count > 0 && (
            <span>{snapshot.param_count} param{snapshot.param_count !== 1 ? "s" : ""}</span>
          )}
          {snapshot.assumption_count > 0 && (
            <span>{snapshot.assumption_count} assumption{snapshot.assumption_count !== 1 ? "s" : ""}</span>
          )}
          {snapshot.source_filename && <span>{snapshot.source_filename}</span>}
          <span title={snapshot.config_hash} className="text-text-muted/50">
            hash: {snapshot.config_hash.slice(0, 8)}…
          </span>
        </div>
      </div>
      <span className="shrink-0 font-mono text-2xs text-text-muted whitespace-nowrap">
        {fmtDateShort(snapshot.created_at)}
      </span>
    </div>
  );
}

function VersionConfigSection({
  versions,
  configSnapshots,
  onCreateVersion,
  onLogConfig,
}: {
  versions: StrategyVersion[];
  configSnapshots: StrategyConfigSnapshotRead[];
  onCreateVersion: () => void;
  onLogConfig: () => void;
}) {
  // Unlinked snapshots — those with no strategy_version_id
  const unlinked = configSnapshots.filter((s) => s.strategy_version_id === null);

  return (
    <div className="rounded-card border border-border bg-bg-700">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <p className="caption">Version &amp; Config Evidence</p>
        <div className="flex items-center gap-2">
          <button
            onClick={onLogConfig}
            className="rounded-control border border-border px-2.5 py-1 font-mono text-2xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            + Log Config
          </button>
          <button
            onClick={onCreateVersion}
            className="rounded-control border border-border px-2.5 py-1 font-mono text-2xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            + Create Version
          </button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Versions */}
        {versions.length === 0 ? (
          <p className="font-mono text-2xs text-text-muted">No versions recorded.</p>
        ) : (
          <div className="divide-y divide-border">
            {versions.map((v) => (
              <VersionRow key={v.id} version={v} snapshots={configSnapshots} />
            ))}
          </div>
        )}

        {/* Unlinked config snapshots — shown when any exist */}
        {unlinked.length > 0 && (
          <div>
            <p className="caption mb-2 text-text-muted">Unlinked Config Snapshots</p>
            <div className="divide-y divide-border/50">
              {unlinked.map((s) => (
                <ConfigSnapshotRow key={s.id} snapshot={s} />
              ))}
            </div>
          </div>
        )}

        {versions.length === 0 && unlinked.length === 0 && configSnapshots.length === 0 && (
          <p className="font-mono text-2xs text-text-muted">No version or config evidence yet.</p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function reportScoreColor(score: number | null): string {
  if (score === null) return "text-text-muted";
  if (score >= 75) return "text-fidelity-high";
  if (score >= 50) return "text-fidelity-medium";
  return "text-fidelity-low";
}

export default function StrategyDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [strategy, setStrategy] = useState<StrategyDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runDrawerOpen, setRunDrawerOpen] = useState(false);
  // M15: version and config snapshot drawer state
  const [versionDrawerOpen, setVersionDrawerOpen] = useState(false);
  const [configSnapshotDrawerOpen, setConfigSnapshotDrawerOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  // M16: universe snapshot drawer state
  const [universeSnapshotDrawerOpen, setUniverseSnapshotDrawerOpen] = useState(false);

  // M17: signal snapshot drawer state
  const [signalSnapshotDrawerOpen, setSignalSnapshotDrawerOpen] = useState(false);

  // M8: backtest audit state — keyed by run id.
  const [audits, setAudits] = useState<Record<string, BacktestAudit>>({});
  const [auditingRunId, setAuditingRunId] = useState<string | null>(null);
  const [auditErrors, setAuditErrors] = useState<Record<string, string>>({});

  // M14: reliability report generation
  const [latestReport, setLatestReport] = useState<ReportDetail | null>(null);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);

  async function handleGenerateReport() {
    if (!id) return;
    setGeneratingReport(true);
    setReportError(null);
    try {
      const report = await generateStrategyReport(id);
      setLatestReport(report);
    } catch (err) {
      setReportError(err instanceof Error ? err.message : "Report generation failed.");
    } finally {
      setGeneratingReport(false);
    }
  }

  async function handleAuditRun(runId: string) {
    setAuditingRunId(runId);
    setAuditErrors((prev) => ({ ...prev, [runId]: "" }));
    try {
      const result = await runBacktestAudit(runId);
      setAudits((prev) => ({ ...prev, [runId]: result }));
    } catch (err) {
      setAuditErrors((prev) => ({
        ...prev,
        [runId]: err instanceof Error ? err.message : "Audit failed.",
      }));
    } finally {
      setAuditingRunId(null);
    }
  }

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getStrategy(id)
      .then(setStrategy)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load strategy."))
      .finally(() => setLoading(false));
  }, [id, refreshKey]);

  const backLink = (
    <Link
      to="/strategies"
      className="mb-5 inline-flex items-center gap-1.5 font-mono text-2xs text-text-muted hover:text-text-secondary"
    >
      <BackArrow />
      Strategy Lab
    </Link>
  );

  if (loading) {
    return (
      <div>
        {backLink}
        <p className="font-mono text-2xs text-text-muted">Loading…</p>
      </div>
    );
  }

  if (error || !strategy) {
    return (
      <div>
        {backLink}
        <div className="rounded-card border border-fidelity-low/30 bg-fidelity-low/10 px-4 py-3">
          <p className="font-mono text-xs text-fidelity-low">{error ?? "Strategy not found."}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {backLink}

      {/* Strategy header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="caption mb-1">{strategy.project_name}</p>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-xl font-semibold tracking-tight text-text-primary">
              {strategy.name}
            </h1>
            <Badge value={strategy.asset_class} variant="asset_class" />
            <Badge value={strategy.status} variant="status" />
          </div>
          {strategy.description && (
            <p className="mt-1.5 max-w-2xl text-sm text-text-secondary">{strategy.description}</p>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <button
            onClick={handleGenerateReport}
            disabled={generatingReport}
            className="rounded-control border border-border px-3 py-2 font-mono text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {generatingReport ? "Generating…" : "Generate Report"}
          </button>
          <button
            onClick={() => setVersionDrawerOpen(true)}
            className="rounded-control border border-border px-3 py-2 font-mono text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            + Create Version
          </button>
          <button
            onClick={() => setConfigSnapshotDrawerOpen(true)}
            className="rounded-control border border-border px-3 py-2 font-mono text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            + Log Config
          </button>
          <button
            onClick={() => setUniverseSnapshotDrawerOpen(true)}
            className="rounded-control border border-border px-3 py-2 font-mono text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            + Log Universe
          </button>
          <button
            onClick={() => setSignalSnapshotDrawerOpen(true)}
            className="rounded-control border border-border px-3 py-2 font-mono text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            + Log Signal
          </button>
          <button
            onClick={() => setRunDrawerOpen(true)}
            className="rounded-control bg-accent-500 px-3.5 py-2 font-mono text-xs font-medium text-text-inverse hover:bg-accent-600"
          >
            + Log Run
          </button>
        </div>
      </div>

      <RunLogDrawer
        open={runDrawerOpen}
        strategyId={id!}
        versions={strategy.versions}
        universeSnapshots={strategy.universe_snapshots}
        signalSnapshots={strategy.signal_snapshots}
        onClose={() => setRunDrawerOpen(false)}
        onLogged={() => {
          setRunDrawerOpen(false);
          setRefreshKey((k) => k + 1);
        }}
      />

      {/* M15: Version and Config Snapshot drawers */}
      <VersionCreateDrawer
        open={versionDrawerOpen}
        strategyId={id!}
        onClose={() => setVersionDrawerOpen(false)}
        onCreated={() => setRefreshKey((k) => k + 1)}
      />
      <ConfigSnapshotDrawer
        open={configSnapshotDrawerOpen}
        strategyId={id!}
        versions={strategy.versions}
        onClose={() => setConfigSnapshotDrawerOpen(false)}
        onCreated={() => setRefreshKey((k) => k + 1)}
      />

      {/* M16: Universe Snapshot drawer */}
      <UniverseSnapshotDrawer
        open={universeSnapshotDrawerOpen}
        strategyId={id!}
        versions={strategy.versions}
        onClose={() => setUniverseSnapshotDrawerOpen(false)}
        onCreated={() => setRefreshKey((k) => k + 1)}
      />

      {/* M17: Signal Snapshot drawer */}
      <SignalSnapshotDrawer
        open={signalSnapshotDrawerOpen}
        strategyId={id!}
        versions={strategy.versions}
        universeSnapshots={strategy.universe_snapshots}
        onClose={() => setSignalSnapshotDrawerOpen(false)}
        onCreated={() => setRefreshKey((k) => k + 1)}
      />

      {/* Stat strip */}
      <div className="flex flex-wrap gap-6 rounded-card border border-border bg-bg-700 px-5 py-3">
        <StatCell label="Runs" value={strategy.run_count} />
        <StatCell label="Last Run" value={fmtDate(strategy.latest_run_at)} />
        <StatCell label="Registered" value={fmtDate(strategy.created_at)} />
        <StatCell
          label="Slug"
          value={<span className="font-mono text-xs text-text-muted">{strategy.slug}</span>}
        />
      </div>

      {/* M14: Report error */}
      {reportError && (
        <div className="rounded-control border border-fidelity-low/30 bg-fidelity-low/10 px-3 py-2 font-mono text-xs text-fidelity-low">
          {reportError}
        </div>
      )}

      {/* M14: Latest generated report summary */}
      {latestReport && (
        <div className="rounded-card border border-border bg-bg-700">
          <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
            <p className="caption">Latest Reliability Report</p>
            <button
              onClick={() => navigate(`/reports/${latestReport.id}`)}
              className="font-mono text-2xs text-accent-500 hover:text-accent-300"
            >
              view full report →
            </button>
          </div>
          <div className="flex items-start gap-4 p-4">
            {/* Score */}
            <div className="shrink-0 text-center">
              {latestReport.score !== null ? (
                <div>
                  <p className={`mono-num text-2xl font-bold leading-none ${reportScoreColor(latestReport.score)}`}>
                    {latestReport.score}
                  </p>
                  <p className="font-mono text-2xs text-text-muted">/100</p>
                </div>
              ) : (
                <p className="font-mono text-xs text-text-muted">n/a</p>
              )}
            </div>
            {/* Summary */}
            <div className="flex-1 min-w-0 space-y-1.5">
              <p className="text-xs font-medium text-text-primary">{latestReport.title}</p>
              <p className="text-2xs text-text-secondary leading-relaxed line-clamp-3">
                {latestReport.summary}
              </p>
              <p className="font-mono text-2xs text-text-muted">
                {latestReport.sections.length} section{latestReport.sections.length !== 1 ? "s" : ""}
                {" · "}
                {new Date(latestReport.generated_at).toLocaleString("en-US", {
                  month: "short", day: "numeric",
                  hour: "2-digit", minute: "2-digit", hour12: false,
                })}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* M7: Data Evidence panel — shown when any run has a linked snapshot */}
      <DataEvidencePanel runs={strategy.runs} />

      {/* M16: Universe Evidence panel */}
      <UniverseEvidencePanel
        universeSnapshots={strategy.universe_snapshots}
        onLogUniverse={() => setUniverseSnapshotDrawerOpen(true)}
      />

      {/* M17: Signal Evidence panel */}
      <SignalEvidencePanel
        signalSnapshots={strategy.signal_snapshots}
        onLogSignal={() => setSignalSnapshotDrawerOpen(true)}
      />

      {/* M15: Version & Config Evidence */}
      <VersionConfigSection
        versions={strategy.versions}
        configSnapshots={strategy.config_snapshots}
        onCreateVersion={() => setVersionDrawerOpen(true)}
        onLogConfig={() => setConfigSnapshotDrawerOpen(true)}
      />

      {/* Run evidence */}
      <div className="rounded-card border border-border bg-bg-700">
        <div className="border-b border-border px-4 py-2.5">
          <p className="caption">Run Evidence</p>
        </div>
        <div className="p-4">
          {strategy.runs.length === 0 ? (
            <p className="font-mono text-2xs text-text-muted">No runs logged yet.</p>
          ) : (
            <div className="divide-y divide-border">
              {strategy.runs.map((r) => (
                <div key={r.id} className="py-4 first:pt-0 last:pb-0">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm font-medium text-text-primary">{r.run_name}</span>
                    <div className="flex items-center gap-2">
                      <Badge value={r.run_type} variant="run_type" />
                      <Badge value={r.status} variant="run_status" />
                    </div>
                  </div>

                  {r.metrics_json && Object.keys(r.metrics_json).length > 0 && (
                    <div className="mt-2.5 flex flex-wrap gap-2">
                      {Object.entries(r.metrics_json).map(([k, v]) => (
                        <MetricChip key={k} label={k} value={v} />
                      ))}
                    </div>
                  )}

                  {/* M7: Data evidence chip */}
                  {r.dataset_snapshot ? (
                    <DataEvidenceChip ev={r.dataset_snapshot} />
                  ) : (
                    <p className="mt-2 font-mono text-2xs text-text-muted/60">
                      No dataset snapshot linked
                    </p>
                  )}

                  {/* M16: Universe evidence chip */}
                  {r.universe_snapshot && (
                    <UniverseEvidenceChip uni={r.universe_snapshot} />
                  )}

                  {/* M17: Signal evidence chip */}
                  {r.signal_snapshot && (
                    <SignalEvidenceChip sig={r.signal_snapshot} />
                  )}

                  <div className="mt-2 flex flex-wrap gap-4 font-mono text-2xs text-text-muted">
                    {r.universe_name && <span>universe: {r.universe_name}</span>}
                    {r.dataset_version && <span>dataset ver: {r.dataset_version}</span>}
                    <span>{fmtDate(r.started_at)}</span>
                  </div>
                  {r.notes && (
                    <p className="mt-1.5 text-xs text-text-muted">{r.notes}</p>
                  )}

                  {/* M8: Backtest audit button + results */}
                  {r.run_type === "live" ? (
                    <p className="mt-2.5 font-mono text-2xs text-text-muted/50">
                      Backtest audit not available for live runs
                    </p>
                  ) : (
                    <div className="mt-2.5">
                      {!audits[r.id] && (
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleAuditRun(r.id)}
                            disabled={auditingRunId === r.id}
                            className="rounded-control border border-border px-2.5 py-1 font-mono text-2xs text-text-secondary hover:bg-bg-600 hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {auditingRunId === r.id ? "Auditing…" : "Run Backtest Audit"}
                          </button>
                          {auditErrors[r.id] && (
                            <span className="font-mono text-2xs text-fidelity-low">
                              {auditErrors[r.id]}
                            </span>
                          )}
                        </div>
                      )}
                      {audits[r.id] && (
                        <div>
                          <BacktestAuditPanel audit={audits[r.id]} />
                          <button
                            onClick={() => handleAuditRun(r.id)}
                            disabled={auditingRunId === r.id}
                            className="mt-1.5 font-mono text-2xs text-text-muted/60 hover:text-text-muted disabled:cursor-not-allowed"
                          >
                            {auditingRunId === r.id ? "Re-auditing…" : "Re-audit"}
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* M10: Strategy audit trail preview */}
      <AuditTrailPanel strategyId={id!} />

      {/* Run comparison (M5) */}
      <RunComparisonPanel strategyId={id!} runs={strategy.runs} />
    </div>
  );
}
