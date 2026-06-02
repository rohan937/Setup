import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type {
  BacktestAudit,
  BacktestIssue,
  BacktestStatus,
  CostSensitivityScenario,
  DataEvidenceSummary,
  EvidenceBundleRequest,
  EvidenceBundleResponse,
  ReliabilityScoreComparisonResponse,
  ReliabilityScoreTrendResponse,
  ReportDetail,
  SignalSnapshotRead,
  SignalSnapshotSummary,
  StrategyConfigSnapshotRead,
  StrategyDetail as StrategyDetailType,
  StrategyHealth,
  StrategyReliabilityScore,
  StrategyRun,
  StrategyRunHistoryItem,
  StrategyRunHistoryResponse,
  StrategyEvidenceTrendsResponse,
  StrategyTimelineDrilldownItem,
  StrategyTimelineDrilldownResponse,
  StrategyVersion,
  TrendPoint,
  TrendSummary,
  TimelineEvent,
  UniverseSnapshotRead,
  UniverseSnapshotSummary,
} from "@/types";
import {
  computeStrategyReliabilityScore,
  generateStrategyReport,
  getEvidenceBundleExample,
  getStrategy,
  getStrategyHealth,
  getStrategyReliabilityScoreHistory,
  getStrategyRunHistory,
  getStrategyTimeline,
  getStrategyEvidenceTrends,
  getStrategyTimelineDrilldown,
  ingestEvidenceBundle,
  runBacktestAudit,
} from "@/lib/api";
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
// M18/M19: Strategy Reliability panel (with history + trend)
// ---------------------------------------------------------------------------

function reliabilityStatusBadge(status: string): string {
  switch (status) {
    case "excellent": return "bg-cyan-900/40 text-cyan-300 border-cyan-700/40";
    case "good":      return "bg-teal-900/40 text-teal-300 border-teal-700/40";
    case "review":    return "bg-yellow-900/40 text-yellow-200 border-yellow-700/40";
    case "weak":      return "bg-red-900/40 text-red-300 border-red-700/40";
    default:          return "bg-bg-600 text-text-muted border-border";
  }
}

function scoreComponentColor(val: number | null): string {
  if (val === null) return "text-text-muted";
  if (val >= 75) return "text-green-400";
  if (val >= 55) return "text-yellow-400";
  return "text-red-400";
}

function timeAgo(isoStr: string): string {
  const d = new Date(isoStr);
  const now = Date.now();
  const diff = Math.floor((now - d.getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function deltaColor(delta: number | null): string {
  if (delta === null) return "text-text-muted";
  if (delta > 0.05) return "text-green-400";
  if (delta < -0.05) return "text-red-400";
  return "text-text-muted";
}

function deltaSign(delta: number | null): string {
  if (delta === null) return "—";
  if (delta > 0.05) return `▲ +${delta.toFixed(1)}`;
  if (delta < -0.05) return `▼ ${delta.toFixed(1)}`;
  return "≈";
}

const COMPONENT_LABELS: Record<string, string> = {
  strategy_activity_score: "Activity",
  data_evidence_score: "Data Evidence",
  backtest_trust_score: "Backtest Trust",
  config_evidence_score: "Config",
  universe_evidence_score: "Universe",
  signal_evidence_score: "Signal",
  alert_penalty_score: "Alert Penalty",
  report_coverage_score: "Report Coverage",
};

// Lightweight score sparkline using div bars (no chart library).
function ScoreSparkline({ scores }: { scores: (number | null)[] }) {
  if (scores.length === 0) return null;
  return (
    <div className="flex items-end gap-0.5 h-6">
      {scores.map((s, i) => {
        const pct = s != null ? Math.max(4, (s / 100) * 100) : 4;
        return (
          <div
            key={i}
            className={`flex-1 rounded-sm transition-all ${
              s == null ? "bg-border/50" : s >= 75 ? "bg-green-500/60" : s >= 55 ? "bg-yellow-400/60" : "bg-red-400/60"
            }`}
            style={{ height: `${pct}%` }}
            title={s != null ? `${s.toFixed(1)}` : "N/A"}
          />
        );
      })}
    </div>
  );
}

// Score history row strip: up to 5 most-recent scores, newest first.
function ScoreHistoryStrip({ items }: { items: StrategyReliabilityScore[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="caption mb-1.5">Score History</p>
      <div className="overflow-x-auto">
        <table className="w-full font-mono text-2xs">
          <thead>
            <tr className="border-b border-border/50">
              <th className="pb-1 text-left text-text-muted font-normal pr-3">When</th>
              <th className="pb-1 text-right text-text-muted font-normal pr-3">Score</th>
              <th className="pb-1 text-right text-text-muted font-normal pr-3">Status</th>
              <th className="pb-1 text-right text-text-muted font-normal pr-3">Activity</th>
              <th className="pb-1 text-right text-text-muted font-normal pr-3">Data</th>
              <th className="pb-1 text-right text-text-muted font-normal pr-3">Backtest</th>
              <th className="pb-1 text-right text-text-muted font-normal">Signal</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/30">
            {items.slice(0, 5).map((item) => (
              <tr key={item.id}>
                <td className="py-1 pr-3 text-text-muted whitespace-nowrap">
                  {timeAgo(item.generated_at)}
                </td>
                <td className={`py-1 pr-3 text-right tabular-nums ${scoreComponentColor(item.overall_score)}`}>
                  {item.overall_score != null ? item.overall_score.toFixed(1) : "—"}
                </td>
                <td className="py-1 pr-3 text-right">
                  <span className={`rounded px-1 py-0.5 text-2xs ${reliabilityStatusBadge(item.status)}`}>
                    {item.status.replace(/_/g, " ")}
                  </span>
                </td>
                <td className={`py-1 pr-3 text-right tabular-nums ${scoreComponentColor(item.strategy_activity_score)}`}>
                  {item.strategy_activity_score != null ? item.strategy_activity_score.toFixed(0) : "—"}
                </td>
                <td className={`py-1 pr-3 text-right tabular-nums ${scoreComponentColor(item.data_evidence_score)}`}>
                  {item.data_evidence_score != null ? item.data_evidence_score.toFixed(0) : "—"}
                </td>
                <td className={`py-1 pr-3 text-right tabular-nums ${scoreComponentColor(item.backtest_trust_score)}`}>
                  {item.backtest_trust_score != null ? item.backtest_trust_score.toFixed(0) : "—"}
                </td>
                <td className={`py-1 text-right tabular-nums ${scoreComponentColor(item.signal_evidence_score)}`}>
                  {item.signal_evidence_score != null ? item.signal_evidence_score.toFixed(0) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Trend comparison: latest vs previous.
function TrendSection({
  trend,
}: {
  trend: ReliabilityScoreTrendResponse;
}) {
  if (!trend.has_trend || !trend.comparison) {
    return (
      <div className="rounded-control border border-border/50 bg-bg-800 px-3 py-2">
        <p className="font-mono text-2xs text-text-muted italic">{trend.message}</p>
      </div>
    );
  }

  const cmp: ReliabilityScoreComparisonResponse = trend.comparison;

  // Top component movers (abs delta ≥ 1.0, non-null)
  const movers = cmp.component_deltas
    .filter((d) => d.delta !== null && Math.abs(d.delta) >= 1.0)
    .sort((a, b) => Math.abs(b.delta ?? 0) - Math.abs(a.delta ?? 0))
    .slice(0, 4);

  return (
    <div className="space-y-3">
      <p className="caption">Latest vs. Previous</p>

      {/* Overall delta */}
      <div className="flex items-center gap-4">
        <div className="text-center shrink-0">
          <p className={`mono-num text-lg font-bold leading-none ${deltaColor(cmp.overall_delta)}`}>
            {deltaSign(cmp.overall_delta)}
          </p>
          <p className="font-mono text-2xs text-text-muted mt-0.5">overall</p>
        </div>
        {cmp.status_changed && (
          <div className="flex items-center gap-1.5 font-mono text-2xs">
            <span className={`rounded border px-1.5 py-0.5 ${reliabilityStatusBadge(cmp.status_a)}`}>
              {cmp.status_a.replace(/_/g, " ")}
            </span>
            <span className="text-text-muted">→</span>
            <span className={`rounded border px-1.5 py-0.5 ${reliabilityStatusBadge(cmp.status_b)}`}>
              {cmp.status_b.replace(/_/g, " ")}
            </span>
          </div>
        )}
      </div>

      {/* Component movers */}
      {movers.length > 0 && (
        <div>
          <p className="font-mono text-2xs text-text-muted mb-1">Component changes</p>
          <div className="grid grid-cols-2 gap-1 sm:grid-cols-4">
            {movers.map((d) => (
              <div
                key={d.component}
                className="rounded-control border border-border/40 bg-bg-800 px-2 py-1.5"
              >
                <p className="font-mono text-2xs text-text-muted leading-tight">{d.label}</p>
                <p className={`mono-num text-sm font-semibold ${deltaColor(d.delta)}`}>
                  {deltaSign(d.delta)}
                </p>
                <p className="font-mono text-2xs text-text-muted">
                  {d.score_a != null ? d.score_a.toFixed(0) : "—"}
                  {" → "}
                  {d.score_b != null ? d.score_b.toFixed(0) : "—"}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Evidence changes */}
      {cmp.resolved_missing_evidence.length > 0 && (
        <div>
          <p className="font-mono text-2xs text-green-400/80 mb-0.5">✓ Evidence gaps addressed</p>
          <ul className="space-y-0.5">
            {cmp.resolved_missing_evidence.map((item, i) => (
              <li key={i} className="font-mono text-2xs text-green-300/70">· {item}</li>
            ))}
          </ul>
        </div>
      )}
      {cmp.still_missing_evidence.length > 0 && (
        <div>
          <p className="font-mono text-2xs text-yellow-300/80 mb-0.5">△ Still missing</p>
          <ul className="space-y-0.5">
            {cmp.still_missing_evidence.map((item, i) => (
              <li key={i} className="font-mono text-2xs text-yellow-200/70">· {item}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Explanation */}
      <p className="font-mono text-2xs text-text-muted/70 italic leading-relaxed">
        {cmp.deterministic_explanation}
      </p>
    </div>
  );
}

function ReliabilityPanel({
  score,
  history,
  trend,
  onCompute,
  computing,
}: {
  score: StrategyReliabilityScore | null;
  history: StrategyReliabilityScore[];
  trend: ReliabilityScoreTrendResponse | null;
  onCompute: () => void;
  computing: boolean;
}) {
  // Sparkline uses up to the last 10 scores in chronological order.
  const sparkScores = [...history].reverse().map((s) => s.overall_score);

  return (
    <div className="rounded-card border border-border bg-bg-700">
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <p className="caption">Strategy Reliability</p>
        <button
          onClick={onCompute}
          disabled={computing}
          className="rounded-control border border-border px-2.5 py-1 font-mono text-2xs text-text-secondary hover:bg-bg-600 hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
        >
          {computing ? "Computing…" : score ? "Refresh Score" : "Compute Score"}
        </button>
      </div>

      {score === null ? (
        <div className="px-4 py-6 text-center">
          <p className="font-mono text-2xs text-text-muted">
            No reliability score computed yet.
          </p>
          <button
            onClick={onCompute}
            disabled={computing}
            className="mt-3 rounded-control bg-accent-500 px-3.5 py-1.5 font-mono text-xs font-medium text-text-inverse hover:bg-accent-600 disabled:opacity-50"
          >
            {computing ? "Computing…" : "Compute Score"}
          </button>
        </div>
      ) : (
        <div className="p-4 space-y-4">
          {/* Overall score + status + sparkline */}
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="text-center shrink-0">
                <p className={`mono-num text-3xl font-bold leading-none ${scoreComponentColor(score.overall_score)}`}>
                  {score.overall_score !== null ? score.overall_score.toFixed(1) : "—"}
                </p>
                <p className="font-mono text-2xs text-text-muted mt-0.5">/100</p>
              </div>
              <div className="flex flex-col gap-1.5">
                <span className={`inline-flex w-fit items-center rounded border px-2.5 py-0.5 font-mono text-xs font-semibold uppercase tracking-wider ${reliabilityStatusBadge(score.status)}`}>
                  {score.status.replace(/_/g, " ")}
                </span>
                <p className="font-mono text-2xs text-text-muted">
                  generated {timeAgo(score.generated_at)}
                </p>
              </div>
            </div>
            {/* Sparkline — only shown when ≥2 scores exist */}
            {sparkScores.length >= 2 && (
              <div className="w-24 shrink-0">
                <p className="font-mono text-2xs text-text-muted mb-1 text-right">
                  {sparkScores.length} scores
                </p>
                <ScoreSparkline scores={sparkScores} />
              </div>
            )}
          </div>

          {/* Component scores grid */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {Object.entries(COMPONENT_LABELS).map(([key, label]) => {
              const val = score[key as keyof StrategyReliabilityScore] as number | null;
              return (
                <div
                  key={key}
                  className="rounded-control border border-border/50 bg-bg-800 px-2.5 py-2"
                >
                  <p className="font-mono text-2xs text-text-muted leading-tight">{label}</p>
                  <p className={`mono-num mt-0.5 text-sm font-semibold ${scoreComponentColor(val)}`}>
                    {val !== null ? val.toFixed(1) : "—"}
                  </p>
                </div>
              );
            })}
          </div>

          {/* Missing evidence */}
          {score.missing_evidence_json && score.missing_evidence_json.length > 0 && (
            <div>
              <p className="caption mb-1.5">Missing Evidence</p>
              <ul className="space-y-0.5">
                {score.missing_evidence_json.map((item, i) => (
                  <li key={i} className="font-mono text-2xs text-yellow-300/80">
                    · {item}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Suggested checks */}
          {score.suggested_checks_json && score.suggested_checks_json.length > 0 && (
            <div>
              <p className="caption mb-1.5">Suggested Checks</p>
              <ul className="space-y-0.5">
                {score.suggested_checks_json.map((item, i) => (
                  <li key={i} className="font-mono text-2xs text-text-secondary">
                    ☐ {item}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* M19: Trend section — latest vs previous */}
          {trend && (
            <div className="border-t border-border/50 pt-4">
              <TrendSection trend={trend} />
            </div>
          )}

          {/* M19: Score history strip */}
          {history.length > 1 && (
            <div className="border-t border-border/50 pt-4">
              <ScoreHistoryStrip items={history} />
            </div>
          )}
        </div>
      )}
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
// M22: Evidence Bundle Ingestion Panel (developer tool)
// ---------------------------------------------------------------------------

function IngestionPanel({
  strategyId,
  bundlePayload,
  setBundlePayload,
  bundleResult,
  setBundleResult,
  bundleLoading,
  setBundleLoading,
  bundleError,
  setBundleError,
  idempotencyKey,
  setIdempotencyKey,
  onSuccess,
}: {
  strategyId: string;
  bundlePayload: string;
  setBundlePayload: (v: string) => void;
  bundleResult: EvidenceBundleResponse | null;
  setBundleResult: (v: EvidenceBundleResponse | null) => void;
  bundleLoading: boolean;
  setBundleLoading: (v: boolean) => void;
  bundleError: string | null;
  setBundleError: (v: string | null) => void;
  idempotencyKey: string;
  setIdempotencyKey: (v: string) => void;
  onSuccess: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [loadingExample, setLoadingExample] = useState(false);

  async function handleLoadExample() {
    setLoadingExample(true);
    setBundleError(null);
    try {
      const example = await getEvidenceBundleExample(strategyId);
      setBundlePayload(JSON.stringify(example, null, 2));
    } catch (err) {
      setBundleError(err instanceof Error ? err.message : "Failed to load example.");
    } finally {
      setLoadingExample(false);
    }
  }

  async function handleIngest() {
    setBundleError(null);
    setBundleResult(null);
    let parsed: EvidenceBundleRequest;
    try {
      parsed = JSON.parse(bundlePayload) as EvidenceBundleRequest;
    } catch {
      setBundleError("Invalid JSON — please fix the payload before ingesting.");
      return;
    }
    if (idempotencyKey.trim()) {
      (parsed as Record<string, unknown>).idempotency_key = idempotencyKey.trim();
    }
    setBundleLoading(true);
    try {
      const result = await ingestEvidenceBundle(strategyId, parsed);
      setBundleResult(result);
      onSuccess();
    } catch (err) {
      setBundleError(err instanceof Error ? err.message : "Ingestion failed.");
    } finally {
      setBundleLoading(false);
    }
  }

  return (
    <div className="rounded-panel border border-border bg-bg-800">
      {/* Header / toggle */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-5 py-3.5 text-left"
      >
        <div className="flex items-center gap-2.5">
          <span className="font-mono text-xs font-semibold uppercase tracking-widest text-cyan-400">
            Evidence Bundle Ingestion
          </span>
          <span className="rounded border border-cyan-700/40 bg-cyan-900/30 px-1.5 py-0.5 font-mono text-2xs text-cyan-400/70">
            DEV TOOL
          </span>
        </div>
        <span className="font-mono text-xs text-text-muted">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-border px-5 pb-5 pt-4">
          <p className="mb-3 font-mono text-2xs text-text-muted">
            POST a single JSON payload to ingest all evidence layers at once (version, config,
            universe, signal, dataset, run, audit, reliability, report).
          </p>

          {/* Textarea */}
          <textarea
            rows={15}
            value={bundlePayload}
            onChange={(e) => setBundlePayload(e.target.value)}
            spellCheck={false}
            placeholder='{\n  "strategy_run": { "run_name": "...", "run_type": "backtest" }\n}'
            className="w-full resize-y rounded border border-border bg-bg-900 p-3 font-mono text-xs text-teal-300 placeholder:text-text-muted/40 focus:border-cyan-600 focus:outline-none"
          />

          {/* Idempotency key */}
          <div className="mt-3">
            <label className="mb-1 block font-mono text-2xs text-text-muted/70">
              Idempotency Key{" "}
              <span className="text-text-muted/40">(optional)</span>
            </label>
            <input
              type="text"
              value={idempotencyKey}
              onChange={(e) => setIdempotencyKey(e.target.value)}
              placeholder="e.g. backtest-q1-2024-run1"
              spellCheck={false}
              className="w-full rounded border border-border bg-bg-900 px-3 py-1.5 font-mono text-xs text-teal-300 placeholder:text-text-muted/40 focus:border-cyan-600 focus:outline-none"
            />
            <p className="mt-1 font-mono text-2xs text-text-muted/50">
              Use idempotency keys for safe retries from SDK/CI.
            </p>
          </div>

          {/* Action buttons */}
          <div className="mt-3 flex items-center gap-3">
            <button
              onClick={handleLoadExample}
              disabled={loadingExample || bundleLoading}
              className="rounded-control border border-cyan-700/50 bg-cyan-900/20 px-3 py-1.5 font-mono text-xs text-cyan-400 hover:bg-cyan-900/40 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loadingExample ? "Loading…" : "Load Example"}
            </button>
            <button
              onClick={handleIngest}
              disabled={bundleLoading || !bundlePayload.trim()}
              className="rounded-control border border-teal-600/60 bg-teal-900/30 px-3 py-1.5 font-mono text-xs font-semibold text-teal-300 hover:bg-teal-900/50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {bundleLoading ? "Ingesting…" : "Ingest Bundle"}
            </button>
            {(bundleResult || bundleError) && (
              <button
                onClick={() => {
                  setBundleResult(null);
                  setBundleError(null);
                }}
                className="ml-auto font-mono text-2xs text-text-muted/60 hover:text-text-muted"
              >
                Clear results
              </button>
            )}
          </div>

          {/* Error banner */}
          {bundleError && (
            <div className="mt-3 rounded border border-red-700/40 bg-red-900/20 px-3 py-2 font-mono text-xs text-red-400">
              {bundleError}
            </div>
          )}

          {/* Result panel */}
          {bundleResult && (
            <div className="mt-4 space-y-3 rounded border border-teal-700/30 bg-bg-900/60 p-4">
              {/* Summary */}
              <p className="font-mono text-xs text-teal-300">{bundleResult.summary}</p>

              {/* Counts */}
              <div className="flex gap-5">
                <span className="font-mono text-2xs text-text-muted">
                  Created:{" "}
                  <span className="text-fidelity-high">{bundleResult.created_count}</span>
                </span>
                <span className="font-mono text-2xs text-text-muted">
                  Reused:{" "}
                  <span className="text-text-secondary">{bundleResult.reused_count}</span>
                </span>
                <span className="font-mono text-2xs text-text-muted">
                  Timeline events:{" "}
                  <span className="text-text-secondary">{bundleResult.timeline_events_created}</span>
                </span>
                <span className="font-mono text-2xs text-text-muted">
                  Alerts:{" "}
                  <span className="text-text-secondary">{bundleResult.alerts_generated}</span>
                </span>
              </div>

              {/* Objects */}
              {Object.keys(bundleResult.objects).length > 0 && (
                <div>
                  <p className="mb-1.5 font-mono text-2xs font-semibold uppercase tracking-wider text-text-muted/60">
                    Objects
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {(
                      Object.entries(bundleResult.objects) as [
                        string,
                        { id: string; name: string; type: string; status: "created" | "reused" },
                      ][]
                    ).map(([key, obj]) => (
                      <div
                        key={key}
                        className="flex items-center gap-1.5 rounded border border-border bg-bg-700 px-2 py-1"
                      >
                        <span className="font-mono text-2xs text-text-muted">{obj.type}</span>
                        <span className="font-mono text-2xs text-text-secondary">{obj.name}</span>
                        <span
                          className={`font-mono text-2xs ${
                            obj.status === "created" ? "text-fidelity-high" : "text-text-muted/60"
                          }`}
                        >
                          [{obj.status}]
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Actions run */}
              {bundleResult.actions_run.length > 0 && (
                <div>
                  <p className="mb-1 font-mono text-2xs font-semibold uppercase tracking-wider text-text-muted/60">
                    Actions run
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {bundleResult.actions_run.map((a) => (
                      <span
                        key={a}
                        className="rounded border border-cyan-700/40 bg-cyan-900/20 px-1.5 py-0.5 font-mono text-2xs text-cyan-400"
                      >
                        {a}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Warnings */}
              {bundleResult.warnings.length > 0 && (
                <div>
                  <p className="mb-1 font-mono text-2xs font-semibold uppercase tracking-wider text-amber-500/70">
                    Warnings
                  </p>
                  <ul className="space-y-0.5">
                    {bundleResult.warnings.map((w, i) => (
                      <li key={i} className="font-mono text-2xs text-amber-400">
                        {w}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="font-mono text-2xs text-text-muted/50">
                Generated at {bundleResult.generated_at}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// M27: Strategy Health card
// ---------------------------------------------------------------------------

function StrategyHealthCard({ health }: { health: StrategyHealth }) {
  const STATUS_COLORS: Record<string, { bg: string; border: string; text: string; dot: string }> = {
    healthy:               { bg: "bg-teal-900/20",   border: "border-teal-700/40",   text: "text-teal-300",   dot: "bg-teal-400" },
    watch:                 { bg: "bg-yellow-900/20", border: "border-yellow-700/40", text: "text-yellow-300", dot: "bg-yellow-400" },
    review:                { bg: "bg-orange-900/20", border: "border-orange-700/40", text: "text-orange-300", dot: "bg-orange-400" },
    critical:              { bg: "bg-red-900/20",    border: "border-red-700/40",    text: "text-red-300",    dot: "bg-red-500" },
    insufficient_evidence: { bg: "bg-bg-700",        border: "border-border",        text: "text-text-muted", dot: "bg-bg-500" },
  };
  const cls = STATUS_COLORS[health.health_status] ?? STATUS_COLORS.insufficient_evidence;
  const scoreColor = (s: number | null) =>
    s === null ? "text-text-muted" : s >= 75 ? "text-teal-400" : s >= 55 ? "text-yellow-400" : "text-red-400";

  return (
    <div className={`rounded-card border ${cls.border} ${cls.bg}`}>
      {/* Header */}
      <div className={`flex items-center justify-between px-4 py-2.5 border-b ${cls.border}`}>
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${cls.dot}`} />
          <p className="caption">Current Strategy Health</p>
        </div>
        <span className={`inline-flex items-center rounded border px-2 py-0.5 font-mono text-2xs ${cls.border} ${cls.bg} ${cls.text}`}>
          {health.health_status.replace(/_/g, " ")}
        </span>
      </div>

      {/* Score metrics grid */}
      <div className="grid grid-cols-2 divide-x divide-border sm:grid-cols-4">
        {[
          { label: "Health Score",  value: health.health_score !== null ? health.health_score.toFixed(1) : "—",               color: scoreColor(health.health_score) },
          { label: "Reliability",   value: health.latest_reliability_score !== null ? health.latest_reliability_score.toFixed(1) : "—", color: scoreColor(health.latest_reliability_score) },
          { label: "Coverage",      value: health.evidence_coverage_score.toFixed(0),                                          color: scoreColor(health.evidence_coverage_score) },
          { label: "Open Alerts",   value: health.open_alert_count.toString(),                                                 color: health.high_critical_alert_count > 0 ? "text-red-400" : health.open_alert_count > 0 ? "text-yellow-400" : "text-teal-400" },
        ].map(({ label, value, color }) => (
          <div key={label} className="px-4 py-2.5 text-center">
            <p className="font-mono text-2xs text-text-muted uppercase tracking-wider">{label}</p>
            <p className={`mono-num mt-0.5 text-xl font-bold ${color}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Primary concern */}
      <div className={`border-t ${cls.border} px-4 py-2`}>
        <span className="font-mono text-2xs text-text-muted mr-2">Primary Concern:</span>
        <span className={`font-mono text-xs ${cls.text}`}>{health.primary_concern}</span>
      </div>

      {/* Latest run / ingestion row */}
      <div className={`border-t ${cls.border} px-4 py-2 flex flex-wrap gap-x-6 gap-y-1`}>
        <span className="font-mono text-2xs text-text-muted">
          Last run: {health.days_since_latest_run !== null ? `${health.days_since_latest_run}d ago` : "never"}
        </span>
        {health.latest_ingestion_status && (
          <span className="font-mono text-2xs text-text-muted">
            Last ingest:{" "}
            <span className={health.latest_ingestion_status === "failed" ? "text-red-400" : "text-text-secondary"}>
              {health.latest_ingestion_status}
            </span>
          </span>
        )}
      </div>

      {/* Missing evidence */}
      {health.missing_evidence.length > 0 && (
        <div className={`border-t ${cls.border} px-4 py-2`}>
          <p className="font-mono text-2xs text-text-muted mb-1">Missing Evidence:</p>
          <div className="flex flex-wrap gap-1.5">
            {health.missing_evidence.slice(0, 6).map((e) => (
              <span
                key={e}
                className="font-mono text-2xs bg-bg-800 border border-border rounded px-1.5 py-0.5 text-text-muted"
              >
                {e}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// M29: RunHistoryPanel
// ---------------------------------------------------------------------------

function runHealthColor(label: string): string {
  switch (label) {
    case "strong": return "text-teal-400";
    case "usable": return "text-text-secondary";
    case "review": return "text-yellow-400";
    case "weak": return "text-red-400";
    default: return "text-text-muted";
  }
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-text-muted";
  if (score >= 80) return "text-teal-400";
  if (score >= 60) return "text-yellow-400";
  return "text-red-400";
}

function RunHistoryPanel({ history }: { history: StrategyRunHistoryResponse }) {
  const s = history.summary;
  return (
    <div className="rounded-card border border-border bg-bg-700">
      <div className="border-b border-border px-4 py-2.5">
        <p className="caption">Run History</p>
      </div>
      <div className="p-4 space-y-4">
        {/* Summary chips */}
        <div className="flex flex-wrap gap-2">
          <span className="rounded border border-border bg-bg-800 px-2 py-0.5 font-mono text-2xs text-text-muted">
            Total <span className="mono-num ml-1 text-text-primary">{s.total_runs}</span>
          </span>
          {s.strong_count > 0 && (
            <span className="rounded border border-teal-700/40 bg-teal-900/30 px-2 py-0.5 font-mono text-2xs text-teal-400">
              Strong <span className="mono-num ml-1">{s.strong_count}</span>
            </span>
          )}
          {s.review_count > 0 && (
            <span className="rounded border border-yellow-700/40 bg-yellow-900/30 px-2 py-0.5 font-mono text-2xs text-yellow-400">
              Review <span className="mono-num ml-1">{s.review_count}</span>
            </span>
          )}
          {s.weak_count > 0 && (
            <span className="rounded border border-red-700/40 bg-red-900/30 px-2 py-0.5 font-mono text-2xs text-red-400">
              Weak <span className="mono-num ml-1">{s.weak_count}</span>
            </span>
          )}
          {s.runs_missing_dataset > 0 && (
            <span className="rounded border border-border bg-bg-800 px-2 py-0.5 font-mono text-2xs text-text-muted">
              No Dataset <span className="mono-num ml-1">{s.runs_missing_dataset}</span>
            </span>
          )}
          {s.runs_missing_signal > 0 && (
            <span className="rounded border border-border bg-bg-800 px-2 py-0.5 font-mono text-2xs text-text-muted">
              No Signal <span className="mono-num ml-1">{s.runs_missing_signal}</span>
            </span>
          )}
          {s.runs_missing_audit > 0 && (
            <span className="rounded border border-border bg-bg-800 px-2 py-0.5 font-mono text-2xs text-text-muted">
              No Audit <span className="mono-num ml-1">{s.runs_missing_audit}</span>
            </span>
          )}
        </div>

        {/* Table */}
        {history.items.length === 0 ? (
          <p className="font-mono text-2xs text-text-muted">No runs recorded.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border">
                  {["Run Name", "Type", "Health", "Date", "Version", "Data", "Signal", "BT Trust", "Missing"].map((col) => (
                    <th key={col} className="pb-2 pr-4 font-mono text-2xs text-text-muted uppercase tracking-wider whitespace-nowrap">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {history.items.map((r: StrategyRunHistoryItem) => {
                  const missing: string[] = [];
                  if (!r.has_dataset_evidence) missing.push("data");
                  if (!r.has_universe_evidence) missing.push("universe");
                  if (!r.has_signal_evidence) missing.push("signal");
                  if (!r.has_backtest_audit) missing.push("audit");
                  if (!r.has_strategy_version) missing.push("version");

                  return (
                    <tr key={r.run_id} className="border-b border-border/50 last:border-0">
                      <td className="py-2 pr-4 text-xs text-text-primary whitespace-nowrap max-w-[140px] truncate">
                        {r.run_name}
                      </td>
                      <td className="py-2 pr-4 font-mono text-2xs text-text-muted whitespace-nowrap">
                        {r.run_type}
                      </td>
                      <td className={`py-2 pr-4 font-mono text-2xs whitespace-nowrap ${runHealthColor(r.run_health_label)}`}>
                        {r.run_health_label.replace("_", " ")}
                      </td>
                      <td className="py-2 pr-4 font-mono text-2xs text-text-muted whitespace-nowrap">
                        {r.started_at ? new Date(r.started_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—"}
                      </td>
                      <td className="py-2 pr-4 font-mono text-2xs whitespace-nowrap">
                        {r.strategy_version ? (
                          <span className="text-text-secondary">{r.strategy_version.version_label}</span>
                        ) : (
                          <span className="text-text-muted/40">—</span>
                        )}
                      </td>
                      <td className={`py-2 pr-4 font-mono text-2xs whitespace-nowrap ${scoreColor(r.dataset_evidence?.health_score ?? null)}`}>
                        {r.dataset_evidence != null ? r.dataset_evidence.health_score : "—"}
                      </td>
                      <td className={`py-2 pr-4 font-mono text-2xs whitespace-nowrap ${scoreColor(r.signal_evidence?.quality_score ?? null)}`}>
                        {r.signal_evidence != null ? r.signal_evidence.quality_score : "—"}
                      </td>
                      <td className={`py-2 pr-4 font-mono text-2xs whitespace-nowrap ${scoreColor(r.backtest_audit?.trust_score ?? null)}`}>
                        {r.backtest_audit != null ? r.backtest_audit.trust_score : "—"}
                      </td>
                      <td className="py-2 font-mono text-2xs">
                        {missing.length === 0 ? (
                          <span className="text-teal-400">complete</span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {missing.map((m) => (
                              <span key={m} className="rounded border border-border bg-bg-800 px-1 py-0.5 text-2xs text-text-muted">
                                {m}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// M29: EvidenceTimelinePanel
// ---------------------------------------------------------------------------

function categoryDotClass(category: string): string {
  const map: Record<string, string> = {
    run: "bg-accent-500",
    data: "bg-blue-400",
    backtest: "bg-yellow-400",
    config: "bg-text-muted",
    universe: "bg-teal-400",
    signal: "bg-cyan-400",
    reliability: "bg-green-400",
    report: "bg-purple-400",
    alert: "bg-red-400",
    ingestion: "bg-orange-400",
    other: "bg-bg-500",
  };
  return map[category] ?? "bg-bg-500";
}

function categoryBadgeClass(category: string): string {
  const map: Record<string, string> = {
    run: "bg-accent-900/30 text-accent-400 border-accent-700/40",
    data: "bg-blue-900/30 text-blue-400 border-blue-700/40",
    backtest: "bg-yellow-900/30 text-yellow-400 border-yellow-700/40",
    config: "bg-bg-700 text-text-muted border-border",
    universe: "bg-teal-900/30 text-teal-400 border-teal-700/40",
    signal: "bg-cyan-900/30 text-cyan-400 border-cyan-700/40",
    reliability: "bg-green-900/30 text-green-400 border-green-700/40",
    report: "bg-purple-900/30 text-purple-400 border-purple-700/40",
    alert: "bg-red-900/30 text-red-400 border-red-700/40",
    ingestion: "bg-orange-900/30 text-orange-400 border-orange-700/40",
    other: "bg-bg-700 text-text-muted border-border",
  };
  return map[category] ?? "bg-bg-700 text-text-muted border-border";
}

function EvidenceTimelinePanel({
  drilldown,
}: {
  drilldown: StrategyTimelineDrilldownResponse;
  strategyId?: string | undefined;
}) {
  const remaining = drilldown.total - drilldown.items.length;
  return (
    <div className="rounded-card border border-border bg-bg-700">
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <p className="caption">Evidence Timeline</p>
        <Link
          to="/timeline"
          className="font-mono text-2xs text-accent-500 hover:text-accent-300"
        >
          full timeline →
        </Link>
      </div>
      <div className="divide-y divide-border px-4">
        {drilldown.items.length === 0 ? (
          <p className="py-4 font-mono text-2xs text-text-muted">No timeline events yet.</p>
        ) : (
          drilldown.items.map((ev: StrategyTimelineDrilldownItem) => (
            <div key={ev.event_id} className="flex items-start gap-3 py-3">
              {/* Category dot */}
              <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${categoryDotClass(ev.evidence_category)}`} />
              {/* Content */}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                  <div className="flex flex-wrap items-center gap-2 min-w-0">
                    <span className={`inline-block rounded border px-1.5 py-0.5 font-mono text-2xs leading-none ${categoryBadgeClass(ev.evidence_category)}`}>
                      {ev.evidence_category}
                    </span>
                    <span className="text-xs text-text-primary truncate max-w-[240px]">
                      {ev.title}
                    </span>
                  </div>
                  <span className="shrink-0 font-mono text-2xs text-text-muted whitespace-nowrap">
                    {new Date(ev.event_time).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </span>
                </div>
                {ev.source_label && (
                  <p className="mt-0.5 font-mono text-2xs text-text-muted/60">{ev.source_label}</p>
                )}
              </div>
            </div>
          ))
        )}
      </div>
      {remaining > 0 && (
        <div className="border-t border-border px-4 py-2.5">
          <p className="font-mono text-2xs text-text-muted/60">
            +{remaining} more event{remaining !== 1 ? "s" : ""} — view full timeline
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// M30: Evidence Trends sub-components
// ---------------------------------------------------------------------------

function trendScoreColor(value: number | null): string {
  if (value === null) return "text-text-muted";
  if (value >= 80) return "text-teal-400";
  if (value >= 60) return "text-yellow-400";
  return "text-red-400";
}

function MiniSparkline({ points, height = 24 }: { points: TrendPoint[]; height?: number }) {
  const valid = points.filter((p) => p.value !== null);
  if (valid.length === 0) {
    return <div style={{ height }} className="flex items-end gap-0.5 opacity-20">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} style={{ width: 6, height: 4 }} className="rounded-sm bg-bg-500" />
      ))}
    </div>;
  }
  return (
    <div style={{ height }} className="flex items-end gap-0.5">
      {valid.map((p) => {
        const v = p.value as number;
        const barHeight = Math.max(2, Math.round((v / 100) * height));
        const colorClass =
          v >= 80 ? "bg-teal-500/80" : v >= 60 ? "bg-yellow-500/80" : "bg-red-500/70";
        return (
          <div
            key={p.id}
            title={`${p.label}: ${v}`}
            style={{ width: 6, height: barHeight }}
            className={`rounded-sm ${colorClass}`}
          />
        );
      })}
    </div>
  );
}

function TrendPanel({ title, trend }: { title: string; trend: TrendSummary }) {
  const directionConfig: Record<
    string,
    { label: string; cls: string }
  > = {
    improving: {
      label: "Improving",
      cls: "text-teal-400 bg-teal-900/20 border border-teal-700/30",
    },
    deteriorating: {
      label: "Deteriorating",
      cls: "text-red-400 bg-red-900/20 border border-red-700/30",
    },
    flat: {
      label: "Flat",
      cls: "text-yellow-400 bg-yellow-900/20 border border-yellow-700/30",
    },
    insufficient_history: {
      label: "Insufficient History",
      cls: "text-text-muted bg-bg-700 border border-border",
    },
  };
  const dir = directionConfig[trend.direction] ?? directionConfig.insufficient_history;

  return (
    <div className="rounded-card border border-border bg-bg-600 p-3 space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-2xs uppercase tracking-wide text-text-muted">{title}</span>
        <span className={`rounded px-1.5 py-0.5 font-mono text-2xs ${dir.cls}`}>{dir.label}</span>
      </div>

      {/* Score row */}
      <div className="flex items-baseline gap-2">
        <span className={`mono-num text-lg font-bold ${trendScoreColor(trend.latest_value)}`}>
          {trend.latest_value !== null ? trend.latest_value.toFixed(1) : "—"}
          {trend.latest_value !== null && (
            <span className="text-xs font-normal text-text-muted">/100</span>
          )}
        </span>
        {trend.delta !== null && (
          <span
            className={`font-mono text-xs ${trend.delta >= 0 ? "text-teal-400" : "text-red-400"}`}
          >
            {trend.delta >= 0 ? "+" : ""}
            {trend.delta.toFixed(1)}
          </span>
        )}
        <span className="font-mono text-2xs text-text-muted ml-auto">
          {trend.point_count} pts
        </span>
      </div>

      {/* Sparkline */}
      <MiniSparkline points={trend.points} />

      {/* Deterministic summary */}
      <p className="font-mono text-2xs text-text-muted leading-relaxed">
        {trend.deterministic_summary}
      </p>
    </div>
  );
}

function EvidenceTrendsPanel({ trends }: { trends: StrategyEvidenceTrendsResponse }) {
  return (
    <div className="rounded-card border border-border bg-bg-700">
      {/* Header */}
      <div className="border-b border-border px-4 py-2.5 flex items-center justify-between gap-2">
        <p className="caption">Evidence Trends</p>
        <span className="font-mono text-2xs text-text-muted">
          {new Date(trends.generated_at).toLocaleString("en-US", {
            month: "short", day: "numeric", year: "numeric",
            hour: "2-digit", minute: "2-digit",
          })}
        </span>
      </div>

      <div className="p-4 space-y-4">
        {/* Overall summary */}
        {trends.overall_summary && (
          <p className="font-mono text-2xs text-text-secondary leading-relaxed">
            {trends.overall_summary}
          </p>
        )}

        {/* Coverage current summary */}
        {trends.coverage_current && (
          <div className="flex flex-wrap gap-4 rounded border border-border/50 bg-bg-600 px-3 py-2 font-mono text-2xs text-text-muted">
            <span>
              Coverage Score:{" "}
              <span className={`mono-num font-bold ${trendScoreColor(trends.coverage_current.evidence_coverage_score)}`}>
                {trends.coverage_current.evidence_coverage_score}
              </span>
            </span>
            <span>
              Complete: <span className="text-teal-400">{trends.coverage_current.complete_count}</span>
            </span>
            <span>
              Review: <span className="text-yellow-400">{trends.coverage_current.review_count}</span>
            </span>
            <span>
              Missing: <span className="text-red-400">{trends.coverage_current.missing_count}</span>
            </span>
          </div>
        )}

        {/* 2x2 grid of TrendPanel */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TrendPanel title="Reliability Score" trend={trends.reliability_trend} />
          <TrendPanel title="Data Health" trend={trends.data_health_trend} />
          <TrendPanel title="Backtest Trust" trend={trends.backtest_trust_trend} />
          <TrendPanel title="Signal Quality" trend={trends.signal_quality_trend} />
        </div>

        {/* Suggested checks */}
        {trends.suggested_checks.length > 0 && (
          <div>
            <p className="caption mb-1.5">Suggested Checks</p>
            <ul className="space-y-0.5">
              {trends.suggested_checks.map((item, i) => (
                <li key={i} className="font-mono text-2xs text-text-secondary">
                  ☐ {item}
                </li>
              ))}
            </ul>
          </div>
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

  // M18/M19: reliability score state + history + trend
  const [computingReliability, setComputingReliability] = useState(false);
  const [reliabilityScore, setReliabilityScore] = useState<StrategyReliabilityScore | null>(null);
  const [scoreHistory, setScoreHistory] = useState<StrategyReliabilityScore[]>([]);
  const [scoreTrend, setScoreTrend] = useState<ReliabilityScoreTrendResponse | null>(null);

  // M8: backtest audit state — keyed by run id.
  const [audits, setAudits] = useState<Record<string, BacktestAudit>>({});
  const [auditingRunId, setAuditingRunId] = useState<string | null>(null);
  const [auditErrors, setAuditErrors] = useState<Record<string, string>>({});

  // M14: reliability report generation
  const [latestReport, setLatestReport] = useState<ReportDetail | null>(null);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);

  // M22: evidence bundle ingestion
  const [bundlePayload, setBundlePayload] = useState("");
  const [bundleResult, setBundleResult] = useState<EvidenceBundleResponse | null>(null);
  const [bundleLoading, setBundleLoading] = useState(false);
  const [bundleError, setBundleError] = useState<string | null>(null);
  // M25: idempotency key for safe retries
  const [idempotencyKey, setIdempotencyKey] = useState("");

  // M27: strategy health
  const [health, setHealth] = useState<StrategyHealth | null>(null);

  // M29: run history and timeline drilldown
  const [runHistory, setRunHistory] = useState<StrategyRunHistoryResponse | null>(null);
  const [timelineDrilldown, setTimelineDrilldown] = useState<StrategyTimelineDrilldownResponse | null>(null);

  // M30: evidence trends
  const [evidenceTrends, setEvidenceTrends] = useState<StrategyEvidenceTrendsResponse | null>(null);

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

  /** M19: load score history and compute synthetic trend from history items. */
  function loadReliabilityHistory(strategyId: string) {
    getStrategyReliabilityScoreHistory(strategyId, { limit: 10 })
      .then((hist) => {
        setScoreHistory(hist.items);
        // Build trend from the two most-recent items (no extra API call).
        if (hist.items.length >= 2) {
          const [latest, previous] = hist.items; // newest-first
          setScoreTrend({
            has_trend: true,
            message: "Comparing previous score to latest score.",
            latest,
            previous,
            // Comparison will be loaded when needed; defer to avoid extra call.
            comparison: null,
          });
        } else {
          setScoreTrend({
            has_trend: false,
            message: "Compute at least two reliability scores to see trend.",
            latest: hist.items[0] ?? null,
            previous: null,
            comparison: null,
          });
        }
      })
      .catch(() => {/* silently ignore — history is optional UI enhancement */});
  }

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getStrategy(id)
      .then((s) => {
        setStrategy(s);
        // Seed the reliability score from the strategy detail response (M18)
        if (s.latest_reliability_score) {
          setReliabilityScore(s.latest_reliability_score);
          // M19: also load score history + trend
          loadReliabilityHistory(id);
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load strategy."))
      .finally(() => setLoading(false));
    // M27: load health in parallel
    getStrategyHealth(id).then(setHealth).catch(() => setHealth(null));
    // M29: load run history and timeline drilldown in parallel
    getStrategyRunHistory(id, { limit: 50 }).then(setRunHistory).catch(() => setRunHistory(null));
    getStrategyTimelineDrilldown(id, { limit: 30 }).then(setTimelineDrilldown).catch(() => setTimelineDrilldown(null));
    // M30: load evidence trends in parallel
    getStrategyEvidenceTrends(id).then(setEvidenceTrends).catch(() => setEvidenceTrends(null));
  }, [id, refreshKey]);

  async function handleComputeReliabilityScore() {
    if (!id) return;
    setComputingReliability(true);
    try {
      const score = await computeStrategyReliabilityScore(id);
      setReliabilityScore(score);
      // M19: refresh history + trend after every new computation.
      loadReliabilityHistory(id);
    } catch (_err) {
      // silently ignore; panel will show last known score
    } finally {
      setComputingReliability(false);
    }
  }

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

      {/* M27: Strategy Health card */}
      {health && <StrategyHealthCard health={health} />}

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

      {/* M18/M19: Strategy Reliability panel with history + trend */}
      <ReliabilityPanel
        score={reliabilityScore}
        history={scoreHistory}
        trend={scoreTrend}
        onCompute={handleComputeReliabilityScore}
        computing={computingReliability}
      />

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

      {/* M29: Run History panel */}
      {runHistory && <RunHistoryPanel history={runHistory} />}

      {/* M29: Evidence Timeline drilldown */}
      {timelineDrilldown && <EvidenceTimelinePanel drilldown={timelineDrilldown} strategyId={id} />}

      {/* M30: Evidence Trends */}
      {evidenceTrends && <EvidenceTrendsPanel trends={evidenceTrends} />}

      {/* M22: Evidence Bundle Ingestion (developer tool) */}
      <IngestionPanel
        strategyId={id!}
        bundlePayload={bundlePayload}
        setBundlePayload={setBundlePayload}
        bundleResult={bundleResult}
        setBundleResult={setBundleResult}
        bundleLoading={bundleLoading}
        setBundleLoading={setBundleLoading}
        bundleError={bundleError}
        setBundleError={setBundleError}
        idempotencyKey={idempotencyKey}
        setIdempotencyKey={setIdempotencyKey}
        onSuccess={() => setRefreshKey((k) => k + 1)}
      />
    </div>
  );
}
