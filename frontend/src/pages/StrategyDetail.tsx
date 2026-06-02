import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type {
  BacktestAudit,
  BacktestIssue,
  BacktestStatus,
  CostSensitivityScenario,
  CostSensitivitySweep,
  CostSweepScenario,
  FillSensitivity,
  FillSensitivityScenario,
  ImprovementCheck,
  PenaltyAttribution,
  PenaltyAttributionCategory,
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
  StrategyExportResponse,
  StrategyHealth,
  StrategyReliabilityScore,
  StrategyRun,
  StrategyRunHistoryItem,
  StrategyRunHistoryResponse,
  StrategyEvidenceTrendsResponse,
  StrategyTimelineDrilldownItem,
  StrategyTimelineDrilldownResponse,
  StrategyVersion,
  StrategyVersionLineageResponse,
  StrategyVersionLineageItem,
  StrategyVersionTransition,
  TrendPoint,
  TrendSummary,
  TimelineEvent,
  UniverseSnapshotRead,
  UniverseSnapshotSummary,
  SignalQualityDrilldownResponse,
  SymbolSignalQuality,
  SignalRowQualitySample,
  UniverseCoverageAnalysisResponse,
  ConfigSnapshotComparisonV2Response,
  ConfigFieldChange,
  ConfigDiffSection,
  StrategyAssumptionHealthResponse,
  AssumptionCategoryScorecard,
  StrategyTimelineAnalyticsResponse,
  TimelineAnalyticsBucket,
  TimelineInactivityGap,
  StrategyDriftResponse,
  MetricDriftItem,
  EvidenceDriftItem,
  AssumptionDriftItem,
  StrategyEvidenceFreshnessResponse,
  EvidenceFreshnessItem,
  StrategyReadinessResponse,
  StrategyReadinessDimension,
  StrategyShadowMonitorResponse,
  ShadowProductionCheck,
  ShadowMetricComparison,
  StrategyPromotionGateResponse,
  PromotionGateCheck,
  StrategyEvidenceGraphResponse,
  EvidenceGraphNode,
  EvidenceBlastRadius,
  StrategyRegressionTest,
  StrategyRegressionTestRun,
  RegressionTestStatus,
  RegressionTestOverallStatus,
  StrategyConfigPolicy,
  ConfigPolicyEvaluation,
  ResearchReviewCase,
  EvidenceSLAPolicy,
  EvidenceSLAEvaluation,
  StrategyChangeImpactResponse,
  ImpactedArtifact,
  RecommendedRecheck,
  RunReplayResponse,
  RunReplayStatus,
} from "@/types";
import {
  computeStrategyReliabilityScore,
  exportStrategyEvidence,
  generateStrategyReport,
  getEvidenceBundleExample,
  getStrategy,
  getStrategyHealth,
  getStrategyReliabilityScoreHistory,
  getStrategyRunHistory,
  getStrategyTimeline,
  getStrategyEvidenceTrends,
  getStrategyTimelineDrilldown,
  getStrategyVersionLineage,
  ingestEvidenceBundle,
  runBacktestAudit,
  getSignalSnapshotQualityDrilldown,
  getUniverseSnapshotCoverageAnalysis,
  compareConfigSnapshotsV2,
  getStrategyAssumptionHealth,
  getStrategyTimelineAnalytics,
  getStrategyDrift,
  getStrategyEvidenceFreshness,
  getStrategyReadiness,
  getStrategyShadowMonitor,
  getStrategyPromotionGates,
  getStrategyEvidenceGraph,
  createDefaultRegressionTests,
  getStrategyRegressionTests,
  runStrategyRegressionTests,
  createDefaultConfigPolicy,
  getStrategyConfigPolicies,
  evaluateConfigPolicy,
  getConfigPolicyEvaluations,
  generateResearchReviewCases,
  getStrategyReviewCases,
  acknowledgeResearchReviewCase,
  resolveResearchReviewCase,
  createDefaultEvidenceSLAPolicy,
  getEvidenceSLAPolicies,
  evaluateEvidenceSLAPolicy,
  getEvidenceSLAEvaluations,
  getStrategyChangeImpact,
  getRunReplayPack,
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
  onInspectCoverage,
}: {
  universeSnapshots: UniverseSnapshotRead[];
  onLogUniverse: () => void;
  onInspectCoverage?: (snapshotId: string) => void;
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
                <div className="flex items-center gap-2 shrink-0">
                  {onInspectCoverage && (
                    <button
                      onClick={() => onInspectCoverage(us.id)}
                      className="rounded-control border border-border px-2 py-0.5 font-mono text-2xs text-text-muted hover:border-accent-500/40 hover:text-accent-300"
                    >
                      Inspect Coverage
                    </button>
                  )}
                  <span className="font-mono text-2xs text-text-muted whitespace-nowrap">
                    {fmtDateShort(us.created_at)}
                  </span>
                </div>
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
  onInspectQuality,
}: {
  signalSnapshots: SignalSnapshotRead[];
  onLogSignal: () => void;
  onInspectQuality?: (snapshotId: string) => void;
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
                <div className="flex items-center gap-2 shrink-0">
                  {onInspectQuality && (
                    <button
                      onClick={() => onInspectQuality(ss.id)}
                      className="rounded-control border border-border px-2 py-0.5 font-mono text-2xs text-text-muted hover:border-accent-500/40 hover:text-accent-300"
                    >
                      Inspect Quality
                    </button>
                  )}
                  <span className="font-mono text-2xs text-text-muted whitespace-nowrap">
                    {fmtDateShort(ss.created_at)}
                  </span>
                </div>
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

// ---------------------------------------------------------------------------
// M36: V3 extended audit panel — cost sweep, fill sensitivity, penalty
//       attribution, and improvement checks
// ---------------------------------------------------------------------------

function trustImpactBadge(impact: string): string {
  switch (impact) {
    case "high":
      return "text-fidelity-low";
    case "medium":
      return "text-fidelity-medium";
    case "low":
      return "text-fidelity-high";
    default:
      return "text-text-muted";
  }
}

function priorityBadgeStyle(priority: string): string {
  switch (priority) {
    case "high":
      return "border-fidelity-low/30 bg-fidelity-low/10 text-fidelity-low";
    case "medium":
      return "border-fidelity-medium/30 bg-fidelity-medium/10 text-fidelity-medium";
    default:
      return "border-border bg-bg-600 text-text-muted";
  }
}

function BacktestV3Panel({ audit }: { audit: BacktestAudit }) {
  const sweep = audit.cost_sensitivity_sweep_json as CostSensitivitySweep | null;
  const fillSens = audit.fill_sensitivity_json as FillSensitivity | null;
  const penalty = audit.penalty_attribution_json as PenaltyAttribution | null;
  const checks = audit.improvement_checks_json as ImprovementCheck[] | null;

  if (!sweep && !fillSens && !penalty && !checks) return null;

  const sortedChecks = checks
    ? [...checks].sort((a, b) => {
        const order: Record<string, number> = { high: 0, medium: 1, low: 2 };
        return (order[a.priority] ?? 3) - (order[b.priority] ?? 3);
      })
    : [];

  return (
    <div className="mt-3 rounded-card border border-border bg-bg-700 p-3 space-y-2">
      <p className="caption text-text-muted">M36 Analysis</p>

      {/* Section 1: Cost Sweep */}
      {sweep && (
        <details className="rounded-control border border-border/50 bg-bg-800">
          <summary className="flex cursor-pointer items-center justify-between px-3 py-2 list-none">
            <div className="flex items-center gap-2">
              <span className="caption">Cost Sweep</span>
              {sweep.most_fragile_scenario && (
                <span className="font-mono text-2xs text-text-muted">
                  fragile: {sweep.most_fragile_scenario}
                </span>
              )}
            </div>
          </summary>
          <div className="border-t border-border/50 px-3 py-2 space-y-2">
            <p className="font-mono text-2xs text-text-secondary leading-relaxed">
              {sweep.deterministic_summary}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left font-mono text-2xs">
                <thead>
                  <tr className="border-b border-border/50">
                    <th className="py-1 pr-3 text-text-muted font-normal">Scenario</th>
                    <th className="py-1 pr-3 text-text-muted font-normal">Cost bps</th>
                    <th className="py-1 pr-3 text-text-muted font-normal">Adj. Return</th>
                    <th className="py-1 pr-3 text-text-muted font-normal">Adj. Sharpe</th>
                    <th className="py-1 text-text-muted font-normal">Trust Impact</th>
                  </tr>
                </thead>
                <tbody>
                  {(sweep.scenarios as CostSweepScenario[]).map((s, i) => (
                    <tr key={i} className="border-b border-border/20 last:border-0">
                      <td className="py-1 pr-3 text-text-secondary">{s.scenario_label}</td>
                      <td className="py-1 pr-3 text-text-secondary">{s.total_cost_bps}</td>
                      <td className="py-1 pr-3 text-text-secondary">
                        {s.adjusted_annual_return !== null
                          ? `${(s.adjusted_annual_return * 100).toFixed(1)}%`
                          : "—"}
                      </td>
                      <td className="py-1 pr-3 text-text-secondary">
                        {s.adjusted_sharpe !== null ? s.adjusted_sharpe.toFixed(2) : "—"}
                      </td>
                      <td className={`py-1 ${trustImpactBadge(s.trust_impact)}`}>
                        {s.trust_impact}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {sweep.warnings.map((w, i) => (
              <p key={i} className="font-mono text-2xs text-text-muted">⚠ {w}</p>
            ))}
          </div>
        </details>
      )}

      {/* Section 2: Fill Sensitivity */}
      {fillSens && (
        <details className="rounded-control border border-border/50 bg-bg-800">
          <summary className="flex cursor-pointer items-center justify-between px-3 py-2 list-none">
            <div className="flex items-center gap-2">
              <span className="caption">Fill Sensitivity</span>
              <span className={`rounded-chip border px-1.5 py-0.5 font-mono text-2xs ${fragilityLevelBadge(fillSens.fill_realism_level)}`}>
                {fillSens.fill_realism_level}
              </span>
            </div>
          </summary>
          <div className="border-t border-border/50 px-3 py-2 space-y-2">
            <p className="font-mono text-2xs text-text-secondary leading-relaxed">
              {fillSens.deterministic_summary}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left font-mono text-2xs">
                <thead>
                  <tr className="border-b border-border/50">
                    <th className="py-1 pr-3 text-text-muted font-normal">Scenario</th>
                    <th className="py-1 pr-3 text-text-muted font-normal">Fill Model</th>
                    <th className="py-1 pr-3 text-text-muted font-normal">Slippage</th>
                    <th className="py-1 pr-3 text-text-muted font-normal">Penalty Est.</th>
                    <th className="py-1 text-text-muted font-normal">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {(fillSens.scenarios as FillSensitivityScenario[]).map((s, i) => (
                    <tr key={i} className="border-b border-border/20 last:border-0">
                      <td className="py-1 pr-3 text-text-secondary">{s.scenario_label}</td>
                      <td className="py-1 pr-3 text-text-secondary">{s.assumed_fill_model}</td>
                      <td className="py-1 pr-3 text-text-secondary">{s.slippage_bps_assumption} bps</td>
                      <td className="py-1 pr-3 text-text-secondary">{s.trust_penalty_estimate}</td>
                      <td className="py-1 text-text-muted">{s.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {fillSens.warnings.map((w, i) => (
              <p key={i} className="font-mono text-2xs text-text-muted">⚠ {w}</p>
            ))}
          </div>
        </details>
      )}

      {/* Section 3: Penalty Attribution */}
      {penalty && (
        <details className="rounded-control border border-border/50 bg-bg-800">
          <summary className="flex cursor-pointer items-center justify-between px-3 py-2 list-none">
            <div className="flex items-center gap-2">
              <span className="caption">Penalty Attribution</span>
              {penalty.largest_penalty_category !== null && (
                <span className="font-mono text-2xs text-fidelity-medium">
                  top: {penalty.largest_penalty_category}
                </span>
              )}
            </div>
          </summary>
          <div className="border-t border-border/50 px-3 py-2 space-y-2">
            <p className="font-mono text-2xs text-text-secondary leading-relaxed">
              {penalty.deterministic_summary}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left font-mono text-2xs">
                <thead>
                  <tr className="border-b border-border/50">
                    <th className="py-1 pr-3 text-text-muted font-normal">Category</th>
                    <th className="py-1 pr-3 text-text-muted font-normal">Issues</th>
                    <th className="py-1 pr-3 text-text-muted font-normal">Penalty</th>
                    <th className="py-1 text-text-muted font-normal">Suggested Check</th>
                  </tr>
                </thead>
                <tbody>
                  {(penalty.categories as PenaltyAttributionCategory[]).map((c, i) => (
                    <tr key={i} className="border-b border-border/20 last:border-0">
                      <td className="py-1 pr-3 text-text-secondary">{c.category}</td>
                      <td className="py-1 pr-3 text-text-secondary">{c.issue_count}</td>
                      <td className="py-1 pr-3 text-fidelity-medium">
                        -{c.estimated_score_penalty}pts
                      </td>
                      <td className="py-1 text-text-muted">{c.suggested_check}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </details>
      )}

      {/* Section 4: Improvement Checks */}
      {sortedChecks.length > 0 && (
        <details className="rounded-control border border-border/50 bg-bg-800">
          <summary className="flex cursor-pointer items-center px-3 py-2 list-none">
            <span className="caption">Improvement Checks</span>
            <span className="ml-2 font-mono text-2xs text-text-muted">
              {sortedChecks.length} item{sortedChecks.length !== 1 ? "s" : ""}
            </span>
          </summary>
          <div className="border-t border-border/50 px-3 py-2 space-y-2">
            {sortedChecks.map((c) => (
              <div key={c.check_key} className="flex items-start gap-2">
                <span
                  className={`mt-0.5 shrink-0 rounded border px-1.5 py-0.5 font-mono text-2xs leading-none ${priorityBadgeStyle(c.priority)}`}
                >
                  {c.priority}
                </span>
                <div className="min-w-0">
                  <p className="font-mono text-xs text-text-secondary">{c.title}</p>
                  <p className="font-mono text-2xs text-text-muted leading-relaxed">{c.description}</p>
                  {c.evidence && (
                    <p className="font-mono text-2xs text-text-muted/60 mt-0.5">{c.evidence}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </details>
      )}
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
  snapshotA,
  snapshotB,
  onSnapshotAChange,
  onSnapshotBChange,
  onCompare,
}: {
  versions: StrategyVersion[];
  configSnapshots: StrategyConfigSnapshotRead[];
  onCreateVersion: () => void;
  onLogConfig: () => void;
  snapshotA: string;
  snapshotB: string;
  onSnapshotAChange: (id: string) => void;
  onSnapshotBChange: (id: string) => void;
  onCompare: () => void;
}) {
  // Unlinked snapshots — those with no strategy_version_id
  const unlinked = configSnapshots.filter((s) => s.strategy_version_id === null);

  const selectCls =
    "rounded-control border border-border bg-bg-600 px-2 py-1 font-mono text-2xs text-text-primary focus:border-accent-500 focus:outline-none";

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

        {/* M40: Config Diff selector */}
        <div className="border-t border-border/50 pt-3">
          <p className="caption mb-2 text-text-muted">Compare Config Snapshots</p>
          {configSnapshots.length < 2 ? (
            <p className="font-mono text-2xs text-text-muted/60">
              Need at least two config snapshots to compare.
            </p>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={snapshotA}
                onChange={(e) => onSnapshotAChange(e.target.value)}
                className={selectCls}
              >
                <option value="">— Snapshot A —</option>
                {configSnapshots.map((s) => (
                  <option key={s.id} value={s.id}>{s.label}</option>
                ))}
              </select>
              <span className="font-mono text-2xs text-text-muted">→</span>
              <select
                value={snapshotB}
                onChange={(e) => onSnapshotBChange(e.target.value)}
                className={selectCls}
              >
                <option value="">— Snapshot B —</option>
                {configSnapshots.map((s) => (
                  <option key={s.id} value={s.id}>{s.label}</option>
                ))}
              </select>
              <button
                onClick={onCompare}
                disabled={!snapshotA || !snapshotB || snapshotA === snapshotB}
                className="rounded-control border border-border px-2.5 py-1 font-mono text-2xs text-text-secondary hover:bg-bg-600 hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
              >
                Compare Config
              </button>
            </div>
          )}
        </div>
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

// ---------------------------------------------------------------------------
// M38: Signal Quality Drilldown panel
// ---------------------------------------------------------------------------

function signalStatusColor(status: string): string {
  switch (status) {
    case "clean": return "text-teal-400";
    case "review": return "text-yellow-400";
    case "weak": return "text-orange-400";
    case "unusable": return "text-red-400";
    default: return "text-text-muted";
  }
}

function SignalQualityDrilldownPanel({ drilldown }: { drilldown: SignalQualityDrilldownResponse }) {
  const [distExpanded, setDistExpanded] = useState(false);
  const [symExpanded, setSymExpanded] = useState(false);
  const [rowExpanded, setRowExpanded] = useState(false);
  const s = drilldown.quality_summary;
  const dist = drilldown.signal_distribution;
  const ts = drilldown.timestamp_coverage;

  const rowQualityEntries = (
    Object.entries(drilldown.row_quality) as [string, SignalRowQualitySample[]][]
  ).filter(([, samples]) => samples.length > 0);

  const displayedSymbols = drilldown.symbol_quality.slice(0, 20);
  const extraSymbols = drilldown.symbol_quality.length - 20;

  return (
    <div className="rounded-card border border-border bg-bg-700">
      {/* Header */}
      <div className="border-b border-border px-4 py-2.5 flex items-center justify-between gap-2">
        <p className="caption">
          Signal Quality Drill-Down:{" "}
          <span className="text-accent-300">{drilldown.label}</span>
        </p>
        <div className="flex items-center gap-3">
          {drilldown.signal_name && (
            <span className="font-mono text-2xs text-accent-300/80">{drilldown.signal_name}</span>
          )}
          <span className={`mono-num font-bold text-lg ${scoreColor(drilldown.quality_score)}`}>
            {drilldown.quality_score != null ? drilldown.quality_score : "—"}
            <span className="text-sm font-normal text-text-muted">/100</span>
          </span>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* A. Summary strip */}
        <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-2xs">
          <span className="text-text-muted">
            <span className="text-text-secondary">{s.total_rows.toLocaleString()}</span> rows
          </span>
          <span className="text-text-muted">
            <span className="text-text-secondary">{s.symbol_count}</span> symbols
          </span>
          <span className="text-text-muted">
            <span className="text-text-secondary">{s.signal_value_count.toLocaleString()}</span> values
          </span>
          {s.missing_signal_count > 0 && (
            <span className="text-text-muted">
              <span className="text-yellow-400">{s.missing_signal_count}</span> missing
            </span>
          )}
          {s.non_numeric_signal_count > 0 && (
            <span className="text-text-muted">
              <span className="text-orange-400">{s.non_numeric_signal_count}</span> non-numeric
            </span>
          )}
          {s.outlier_count > 0 && (
            <span className="text-text-muted">
              <span className="text-fidelity-medium">{s.outlier_count}</span> outliers
            </span>
          )}
          {s.duplicate_symbol_timestamp_count > 0 && (
            <span className="text-text-muted">
              <span className="text-fidelity-low">{s.duplicate_symbol_timestamp_count}</span> dup sym/ts
            </span>
          )}
          {s.invalid_timestamp_count > 0 && (
            <span className="text-text-muted">
              <span className="text-fidelity-low">{s.invalid_timestamp_count}</span> bad timestamps
            </span>
          )}
          <span>
            <span className="text-teal-400">{s.clean_symbol_count} clean</span>
            {" · "}
            <span className="text-yellow-400">{s.review_symbol_count} review</span>
            {" · "}
            <span className="text-orange-400">{s.weak_symbol_count} weak</span>
            {" · "}
            <span className="text-red-400">{s.unusable_symbol_count} unusable</span>
          </span>
        </div>

        {/* Timestamp coverage strip */}
        <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-2xs text-text-muted">
          <span>
            ts status: <span className={signalStatusColor(ts.timestamp_status)}>{ts.timestamp_status}</span>
          </span>
          {ts.min_timestamp && (
            <span>{ts.min_timestamp.slice(0, 10)} – {ts.max_timestamp?.slice(0, 10) ?? "?"}</span>
          )}
          {ts.duplicate_symbol_timestamp_count > 0 && (
            <span><span className="text-fidelity-low">{ts.duplicate_symbol_timestamp_count}</span> dup sym/ts</span>
          )}
          {ts.invalid_timestamp_count > 0 && (
            <span><span className="text-fidelity-low">{ts.invalid_timestamp_count}</span> invalid ts</span>
          )}
          {ts.symbols_with_gaps_count != null && ts.symbols_with_gaps_count > 0 && (
            <span><span className="text-yellow-400">{ts.symbols_with_gaps_count}</span> symbols w/ gaps</span>
          )}
        </div>

        {/* B. Signal distribution (collapsible) */}
        <div className="rounded-control border border-border bg-bg-800">
          <button
            className="w-full flex items-center justify-between px-3 py-2 font-mono text-2xs text-text-secondary hover:text-text-primary"
            onClick={() => setDistExpanded((v) => !v)}
          >
            <span>
              Signal Distribution{" "}
              <span className="font-mono text-2xs text-text-muted">({dist.signal_column})</span>
            </span>
            <span className="flex items-center gap-2">
              <span className={signalStatusColor(dist.distribution_status)}>{dist.distribution_status}</span>
              <span className="text-text-muted">{distExpanded ? "▲" : "▼"}</span>
            </span>
          </button>
          {distExpanded && (
            <div className="border-t border-border px-3 pb-3 pt-2 space-y-2">
              {/* Stats grid */}
              <div className="grid grid-cols-2 gap-x-6 gap-y-0.5 font-mono text-2xs sm:grid-cols-4">
                <span className="text-text-muted">mean: <span className="text-text-secondary">{dist.mean_value?.toFixed(4) ?? "—"}</span></span>
                <span className="text-text-muted">median: <span className="text-text-secondary">{dist.median_value?.toFixed(4) ?? "—"}</span></span>
                <span className="text-text-muted">min: <span className="text-text-secondary">{dist.min_value?.toFixed(4) ?? "—"}</span></span>
                <span className="text-text-muted">max: <span className="text-text-secondary">{dist.max_value?.toFixed(4) ?? "—"}</span></span>
                <span className="text-text-muted">stddev: <span className="text-text-secondary">{dist.stddev_value?.toFixed(4) ?? "—"}</span></span>
                <span className="text-text-muted">unique: <span className="text-text-secondary">{dist.unique_value_count.toLocaleString()}</span></span>
                <span className="text-text-muted">values: <span className="text-text-secondary">{dist.value_count.toLocaleString()}</span></span>
                <span className="text-text-muted">missing: <span className="text-yellow-400">{dist.missing_count}</span></span>
              </div>
              {/* Counts */}
              <div className="flex flex-wrap gap-x-4 gap-y-0.5 font-mono text-2xs text-text-muted">
                <span>+: <span className="text-teal-400">{dist.positive_count.toLocaleString()}</span></span>
                <span>zero: <span className="text-text-secondary">{dist.zero_count.toLocaleString()}</span></span>
                <span>-: <span className="text-orange-400">{dist.negative_count.toLocaleString()}</span></span>
                <span>outliers: <span className="text-fidelity-medium">{dist.outlier_count}</span></span>
                <span>extreme+: <span className="text-fidelity-low">{dist.extreme_positive_count}</span></span>
                <span>extreme-: <span className="text-fidelity-low">{dist.extreme_negative_count}</span></span>
                <span>non-numeric: <span className="text-orange-400">{dist.non_numeric_count}</span></span>
              </div>
              {/* Issues */}
              {dist.issues.length > 0 && (
                <ul className="space-y-0.5 pt-1">
                  {dist.issues.map((issue, i) => (
                    <li key={i} className="font-mono text-2xs text-fidelity-medium">• {issue}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {/* C. Symbol quality table (collapsible) */}
        {drilldown.symbol_quality.length > 0 && (
          <div className="rounded-control border border-border bg-bg-800">
            <button
              className="w-full flex items-center justify-between px-3 py-2 font-mono text-2xs text-text-secondary hover:text-text-primary"
              onClick={() => setSymExpanded((v) => !v)}
            >
              <span>Symbol Quality <span className="text-text-muted">({drilldown.symbol_quality.length})</span></span>
              <span className="text-text-muted">{symExpanded ? "▲" : "▼"}</span>
            </button>
            {symExpanded && (
              <div className="border-t border-border overflow-x-auto">
                <table className="w-full text-left font-mono text-2xs">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="px-4 pb-1.5 pt-2.5 text-text-muted font-normal">Symbol</th>
                      <th className="px-3 pb-1.5 pt-2.5 text-right text-text-muted font-normal">Rows</th>
                      <th className="px-3 pb-1.5 pt-2.5 text-right text-text-muted font-normal">Miss%</th>
                      <th className="px-3 pb-1.5 pt-2.5 text-right text-text-muted font-normal">Mean</th>
                      <th className="px-3 pb-1.5 pt-2.5 text-right text-text-muted font-normal">Stddev</th>
                      <th className="px-3 pb-1.5 pt-2.5 text-right text-text-muted font-normal">Outliers</th>
                      <th className="px-3 pb-1.5 pt-2.5 text-right text-text-muted font-normal">DupTS</th>
                      <th className="px-3 pb-1.5 pt-2.5 pr-4 text-text-muted font-normal">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayedSymbols.map((sym: SymbolSignalQuality) => (
                      <tr key={sym.symbol} className="border-b border-border/40 hover:bg-bg-700/50">
                        <td className="px-4 py-1.5 text-text-primary">{sym.symbol}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-text-secondary">{sym.row_count}</td>
                        <td className={`px-3 py-1.5 text-right tabular-nums ${sym.missing_rate > 0.1 ? "text-yellow-400" : "text-text-muted"}`}>
                          {(sym.missing_rate * 100).toFixed(1)}%
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-text-secondary">
                          {sym.mean_value != null ? sym.mean_value.toFixed(4) : "—"}
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-text-muted">
                          {sym.stddev_value != null ? sym.stddev_value.toFixed(4) : "—"}
                        </td>
                        <td className={`px-3 py-1.5 text-right tabular-nums ${sym.outlier_count > 0 ? "text-fidelity-medium" : "text-text-muted"}`}>
                          {sym.outlier_count}
                        </td>
                        <td className={`px-3 py-1.5 text-right tabular-nums ${sym.duplicate_timestamp_count > 0 ? "text-fidelity-low" : "text-text-muted"}`}>
                          {sym.duplicate_timestamp_count}
                        </td>
                        <td className={`px-3 py-1.5 pr-4 ${signalStatusColor(sym.quality_status)}`}>
                          {sym.quality_status}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {extraSymbols > 0 && (
                  <p className="px-4 py-2 font-mono text-2xs text-text-muted/60">
                    and {extraSymbols} more symbol{extraSymbols !== 1 ? "s" : ""}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* D. Row evidence (collapsible) */}
        {rowQualityEntries.length > 0 && (
          <div className="rounded-control border border-border bg-bg-800">
            <button
              className="w-full flex items-center justify-between px-3 py-2 font-mono text-2xs text-text-secondary hover:text-text-primary"
              onClick={() => setRowExpanded((v) => !v)}
            >
              <span>Row Evidence Samples <span className="text-text-muted">({rowQualityEntries.length} type{rowQualityEntries.length !== 1 ? "s" : ""})</span></span>
              <span className="text-text-muted">{rowExpanded ? "▲" : "▼"}</span>
            </button>
            {rowExpanded && (
              <div className="border-t border-border px-3 pb-3 pt-2 space-y-3">
                {rowQualityEntries.map(([key, samples]) => (
                  <div key={key}>
                    <p className="font-mono text-2xs text-text-muted mb-1">{key.replace(/_/g, " ")}</p>
                    <ul className="space-y-0.5">
                      {(samples as SignalRowQualitySample[]).slice(0, 5).map((sample, i) => (
                        <li key={i} className="font-mono text-2xs text-text-secondary flex flex-wrap gap-2">
                          <span className="text-text-muted">row {sample.row_index}</span>
                          {sample.symbol && <span className="text-accent-300">{sample.symbol}</span>}
                          {sample.timestamp && <span className="text-text-muted">{sample.timestamp.slice(0, 10)}</span>}
                          {sample.signal_value && <span className="text-text-secondary">val:{sample.signal_value}</span>}
                          <span className={sample.severity === "error" ? "text-fidelity-low" : "text-fidelity-medium"}>
                            [{sample.severity}]
                          </span>
                          <span className="text-text-muted">{sample.summary}</span>
                        </li>
                      ))}
                      {samples.length > 5 && (
                        <li className="font-mono text-2xs text-text-muted/60">
                          + {samples.length - 5} more
                        </li>
                      )}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* E. Suggested checks */}
        {s.suggested_checks.length > 0 && (
          <div>
            <p className="caption mb-1.5">Suggested Checks</p>
            <ul className="space-y-0.5">
              {s.suggested_checks.map((item, i) => (
                <li key={i} className="font-mono text-2xs text-text-secondary">
                  ☐ {item}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* F. Warnings + disclaimer */}
        {drilldown.warnings.length > 0 && (
          <div className="space-y-1">
            {drilldown.warnings.map((w, i) => (
              <div key={i} className="flex gap-2 rounded-control border border-fidelity-medium/30 bg-fidelity-medium/5 px-3 py-1.5">
                <span className="shrink-0 font-mono text-2xs text-fidelity-medium">!</span>
                <p className="font-mono text-2xs text-fidelity-medium">{w}</p>
              </div>
            ))}
          </div>
        )}

        <p className="font-mono text-2xs text-text-muted/50">
          Signal quality analysis is deterministic. Not investment advice.
        </p>
      </div>
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
// M31: Strategy Evidence Export panel
// ---------------------------------------------------------------------------

function ExportPanel({ strategyId }: { strategyId: string }) {
  const [result, setResult] = useState<StrategyExportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExport(format: string) {
    setLoading(true);
    setError(null);
    try {
      const data = await exportStrategyEvidence(strategyId, { format });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed.");
    } finally {
      setLoading(false);
    }
  }

  function handleDownload() {
    if (!result) return;
    const isJson = result.format === "json";
    const content = isJson ? JSON.stringify(result, null, 2) : result.content ?? "";
    const type = isJson ? "application/json" : "text/markdown";
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = result.filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleCopyMarkdown() {
    if (!result?.content) return;
    navigator.clipboard.writeText(result.content);
  }

  // Severity counts
  const severityCounts: Record<string, number> = {};
  if (result) {
    for (const section of result.sections) {
      if (section.severity) {
        severityCounts[section.severity] = (severityCounts[section.severity] ?? 0) + 1;
      }
    }
  }

  const severityColorClass: Record<string, string> = {
    critical: "text-red-400 bg-red-900/20 border border-red-700/30",
    review: "text-orange-400 bg-orange-900/20 border border-orange-700/30",
    warning: "text-yellow-400 bg-yellow-900/20 border border-yellow-700/30",
  };

  return (
    <div className="rounded-card border border-border bg-bg-700">
      {/* Header */}
      <div className="border-b border-border px-4 py-2.5 flex items-center justify-between gap-2">
        <p className="caption">Strategy Evidence Export</p>
      </div>

      <div className="px-4 py-3 space-y-3">
        {/* Description */}
        <p className="font-mono text-2xs text-text-muted">
          Generate a point-in-time deterministic evidence review.
        </p>

        {/* Export buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleExport("json")}
            disabled={loading}
            className="rounded px-3 py-1.5 font-mono text-xs bg-bg-600 border border-border text-text-secondary hover:bg-bg-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "..." : "Export JSON"}
          </button>
          <button
            onClick={() => handleExport("markdown")}
            disabled={loading}
            className="rounded px-3 py-1.5 font-mono text-xs bg-bg-600 border border-border text-text-secondary hover:bg-bg-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "..." : "Export Markdown"}
          </button>
        </div>

        {/* Error */}
        {error && (
          <p className="font-mono text-2xs text-red-400">{error}</p>
        )}

        {/* Result panel */}
        {result && (
          <div className="rounded border border-border bg-bg-600 p-3 space-y-2">
            <p className="font-mono text-xs text-text-secondary">{result.filename}</p>
            <p className="font-mono text-2xs text-text-muted">
              {result.sections.length} section{result.sections.length !== 1 ? "s" : ""} &middot; {result.format.toUpperCase()}
            </p>
            <p className="font-mono text-2xs text-text-muted">
              Generated {new Date(result.metadata.generated_at).toLocaleString("en-US", {
                month: "short", day: "numeric", year: "numeric",
                hour: "2-digit", minute: "2-digit",
              })}
            </p>

            {/* Action buttons */}
            <div className="flex items-center gap-2 pt-1">
              <button
                onClick={handleDownload}
                className="rounded px-3 py-1.5 font-mono text-xs bg-accent-500 text-white hover:bg-accent-600"
              >
                Download
              </button>
              {result.format === "markdown" && (
                <button
                  onClick={handleCopyMarkdown}
                  className="rounded px-3 py-1.5 font-mono text-xs bg-bg-500 border border-border text-text-secondary hover:bg-bg-400"
                >
                  Copy Markdown
                </button>
              )}
            </div>

            {/* Note */}
            {result.metadata.note && (
              <p className="font-mono text-2xs text-text-muted italic">{result.metadata.note}</p>
            )}

            {/* Severity summary chips */}
            {Object.keys(severityCounts).length > 0 && (
              <div className="flex items-center gap-1.5 flex-wrap pt-1">
                {(["critical", "review", "warning"] as const).map((sev) =>
                  severityCounts[sev] ? (
                    <span
                      key={sev}
                      className={`rounded px-1.5 py-0.5 font-mono text-2xs ${severityColorClass[sev]}`}
                    >
                      {sev}: {severityCounts[sev]}
                    </span>
                  ) : null
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// M35: Version Lineage Panel
// ---------------------------------------------------------------------------

function lineageScoreColor(score: number): string {
  if (score >= 80) return "text-teal-400";
  if (score >= 60) return "text-yellow-400";
  if (score >= 30) return "text-orange-400";
  return "text-red-400";
}

function lineageStatusBadgeClass(status: string): string {
  switch (status) {
    case "well_instrumented":
      return "text-teal-300 bg-teal-900/20 border-teal-700/30";
    case "usable":
      return "text-text-secondary bg-bg-800 border-border";
    case "partial":
      return "text-yellow-300 bg-yellow-900/20 border-yellow-700/30";
    case "under_instrumented":
      return "text-red-300 bg-red-900/20 border-red-700/30";
    default:
      return "text-text-muted bg-bg-800 border-border";
  }
}

function VersionLineagePanel({ lineage }: { lineage: StrategyVersionLineageResponse }) {
  const { summary, versions, transitions } = lineage;
  const avgScore = summary.average_version_evidence_score;

  return (
    <div className="rounded-card border border-border bg-bg-700">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <p className="caption">Version Lineage</p>
        <span className="font-mono text-2xs text-text-muted">
          generated {new Date(summary.generated_at).toLocaleString()}
        </span>
      </div>

      <div className="p-4 space-y-4">
        {/* Summary strip */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded border border-border bg-bg-800 px-2 py-0.5 font-mono text-2xs text-text-secondary">
            {summary.version_count} version{summary.version_count !== 1 ? "s" : ""}
          </span>
          {avgScore !== null && (
            <span className={`rounded border border-border bg-bg-800 px-2 py-0.5 font-mono text-2xs font-semibold ${lineageScoreColor(avgScore)}`}>
              avg score {avgScore.toFixed(1)}
            </span>
          )}
          {summary.most_instrumented_version_id && (
            <span className="rounded border border-border bg-bg-800 px-2 py-0.5 font-mono text-2xs text-text-muted">
              best: {summary.latest_version_label}
            </span>
          )}
          {summary.versions_missing_signal > 0 && (
            <span className="rounded border border-yellow-700/30 bg-yellow-900/20 px-2 py-0.5 font-mono text-2xs text-yellow-300">
              {summary.versions_missing_signal} missing signal
            </span>
          )}
          {summary.versions_without_runs > 0 && (
            <span className="rounded border border-orange-700/30 bg-orange-900/20 px-2 py-0.5 font-mono text-2xs text-orange-300">
              {summary.versions_without_runs} no runs
            </span>
          )}
        </div>

        {/* Deterministic summary */}
        <p className="font-mono text-2xs text-text-muted leading-relaxed">
          {summary.deterministic_summary}
        </p>

        {/* Version rows */}
        <div className="space-y-2">
          {versions.map((v: StrategyVersionLineageItem) => (
            <div
              key={v.version_id}
              className="rounded-control border border-border/50 bg-bg-800 px-3 py-2.5 space-y-1.5"
            >
              {/* Row 1: label + git + branch + score + status */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs font-bold text-text-primary">
                  {v.version_label}
                </span>
                {v.git_commit && (
                  <span className="font-mono text-2xs text-text-muted">
                    {v.git_commit.slice(0, 8)}
                  </span>
                )}
                {v.branch_name && (
                  <span className="font-mono text-2xs text-text-muted">
                    {v.branch_name}
                  </span>
                )}
                {v.signal_name && (
                  <span className="rounded border border-border/50 bg-bg-700 px-1.5 py-0.5 font-mono text-2xs text-text-secondary">
                    {v.signal_name}
                  </span>
                )}
                <span className={`font-mono text-xs font-semibold ${lineageScoreColor(v.version_evidence_score)}`}>
                  {v.version_evidence_score.toFixed(1)}
                </span>
                <span className={`inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-2xs ${lineageStatusBadgeClass(v.lineage_status)}`}>
                  {v.lineage_status.replace(/_/g, " ")}
                </span>
              </div>

              {/* Row 2: evidence chips */}
              <div className="flex flex-wrap items-center gap-1.5">
                {v.run_count > 0 && (
                  <span className="rounded border border-teal-700/30 bg-teal-900/20 px-1.5 py-0.5 font-mono text-2xs text-teal-300">
                    {v.run_count} run{v.run_count !== 1 ? "s" : ""}
                  </span>
                )}
                {v.config_snapshot_count > 0 && (
                  <span className="rounded border border-border/50 bg-bg-700 px-1.5 py-0.5 font-mono text-2xs text-text-secondary">
                    {v.config_snapshot_count} cfg
                  </span>
                )}
                {v.universe_snapshot_count > 0 && (
                  <span className="rounded border border-border/50 bg-bg-700 px-1.5 py-0.5 font-mono text-2xs text-text-secondary">
                    {v.universe_snapshot_count} uni
                  </span>
                )}
                {v.signal_snapshot_count > 0 && (
                  <span className="rounded border border-border/50 bg-bg-700 px-1.5 py-0.5 font-mono text-2xs text-text-secondary">
                    {v.signal_snapshot_count} sig
                  </span>
                )}
                {v.backtest_audit_count > 0 && (
                  <span className="rounded border border-border/50 bg-bg-700 px-1.5 py-0.5 font-mono text-2xs text-text-secondary">
                    {v.backtest_audit_count} audit{v.backtest_audit_count !== 1 ? "s" : ""}
                  </span>
                )}
                {!v.has_config && (
                  <span className="font-mono text-2xs text-text-muted/60">no config</span>
                )}
                {!v.has_signal && (
                  <span className="font-mono text-2xs text-text-muted/60">no signal</span>
                )}
              </div>

              {/* Row 3: mini-scores */}
              <div className="flex items-center gap-3">
                <span className="font-mono text-2xs text-text-muted">
                  BT:{" "}
                  <span className="text-text-secondary">
                    {v.latest_backtest_trust_score !== null ? v.latest_backtest_trust_score.toFixed(1) : "—"}
                  </span>
                </span>
                <span className="font-mono text-2xs text-text-muted">
                  Data:{" "}
                  <span className="text-text-secondary">
                    {v.latest_data_health_score !== null ? v.latest_data_health_score.toFixed(1) : "—"}
                  </span>
                </span>
                <span className="font-mono text-2xs text-text-muted">
                  Sig:{" "}
                  <span className="text-text-secondary">
                    {v.latest_signal_quality_score !== null ? v.latest_signal_quality_score.toFixed(1) : "—"}
                  </span>
                </span>
              </div>

              {/* Row 4: suggested check (first only) */}
              {v.suggested_checks.length > 0 && (
                <p className="font-mono text-2xs italic text-text-muted/70">
                  · {v.suggested_checks[0]}
                </p>
              )}
            </div>
          ))}
        </div>

        {/* Transitions section */}
        {transitions.length > 0 && (
          <div>
            <p className="caption mb-2">Version Changes</p>
            <div className="space-y-1">
              {transitions.map((t: StrategyVersionTransition, i: number) => {
                const changes: string[] = [];
                if (t.git_commit_changed) changes.push("git changed");
                if (t.branch_changed) changes.push("branch changed");
                if (t.signal_name_changed) changes.push("signal name changed");
                if (t.config_hash_changed) changes.push("config hash changed");
                if (t.universe_hash_changed) changes.push("universe hash changed");
                if (t.signal_hash_changed) changes.push("signal hash changed");
                return (
                  <div key={i} className="font-mono text-2xs text-text-muted">
                    <span className="text-text-secondary">
                      {t.from_version_label} → {t.to_version_label}
                    </span>
                    {" "}
                    <span className="text-text-muted/60">
                      ({t.created_at_delta_days}d)
                    </span>
                    {changes.length > 0 && (
                      <span className="text-text-muted/80">
                        {": "}
                        {changes.join(", ")}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// M39: Universe Coverage Analysis Panel
// ---------------------------------------------------------------------------

function coverageStatusColor(status: string): string {
  if (status === "complete") return "text-teal-400";
  if (status === "review") return "text-yellow-400";
  if (status === "weak") return "text-red-400";
  return "text-text-muted";
}

function symbolStatusColor(status: string): string {
  if (status === "clean") return "text-teal-400";
  if (status === "review") return "text-yellow-400";
  if (status === "weak") return "text-red-400";
  return "text-text-muted";
}

function deltaStatusColor(status: string | null): string {
  if (status === "stable") return "text-teal-400";
  if (status === "review") return "text-yellow-400";
  if (status === "high_churn") return "text-red-400";
  if (status === "no_previous_snapshot") return "text-text-muted";
  return "text-text-muted";
}

function fmtRatio(v: number | null): string {
  return v !== null ? (v * 100).toFixed(1) + "%" : "—";
}

function UniverseCoveragePanel({ coverage }: { coverage: UniverseCoverageAnalysisResponse }) {
  const [deltaExpanded, setDeltaExpanded] = useState(false);
  const [metaExpanded, setMetaExpanded] = useState(false);
  const [symExpanded, setSymExpanded] = useState(false);

  const ca = coverage.coverage_analysis;
  const delta = coverage.universe_delta;
  const meta = coverage.metadata_breakdown;
  const qs = coverage.quality_summary;

  const nonCleanSymbols = coverage.symbol_quality.filter((s) => s.quality_status !== "clean");

  function MetaDict({ label, data }: { label: string; data: Record<string, number> }) {
    const entries = Object.entries(data);
    if (entries.length === 0) return null;
    return (
      <div className="mt-1">
        <p className="font-mono text-2xs text-text-muted mb-0.5">{label}:</p>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
          {entries.map(([k, v]) => (
            <span key={k} className="font-mono text-2xs text-text-secondary">
              {k}: <span className="text-accent-300">{v}</span>
            </span>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-card border border-border bg-bg-700">
      <div className="border-b border-border px-4 py-2.5">
        <p className="caption">Universe Coverage Analysis: {coverage.label}</p>
      </div>
      <div className="p-4 space-y-3">

        {/* A. Summary strip */}
        <div className="flex flex-wrap gap-x-5 gap-y-1 font-mono text-2xs">
          <span className="text-text-muted">symbols: <span className="text-text-secondary">{ca.symbol_count}</span></span>
          <span className="text-text-muted">unique: <span className="text-text-secondary">{ca.unique_symbol_count}</span></span>
          {ca.duplicate_symbol_count > 0 && (
            <span className="text-text-muted">duplicates: <span className="text-orange-400">{ca.duplicate_symbol_count}</span></span>
          )}
          {ca.invalid_symbol_count > 0 && (
            <span className="text-text-muted">invalid: <span className="text-red-400">{ca.invalid_symbol_count}</span></span>
          )}
          <span className="text-text-muted">
            status: <span className={coverageStatusColor(ca.coverage_status)}>{ca.coverage_status}</span>
          </span>
          <span className="text-text-muted">linked runs: <span className="text-text-secondary">{ca.linked_run_count}</span></span>
          {ca.version_label && (
            <span className="text-text-muted">version: <span className="text-accent-300">{ca.version_label}</span></span>
          )}
        </div>

        {/* B. Delta section (collapsible) */}
        <div className="rounded-control border border-border bg-bg-800">
          <button
            className="w-full flex items-center justify-between px-3 py-2 font-mono text-2xs text-text-secondary hover:text-text-primary"
            onClick={() => setDeltaExpanded((v) => !v)}
          >
            <span>
              Universe Delta{" "}
              {delta.delta_status && (
                <span className={deltaStatusColor(delta.delta_status)}>{delta.delta_status}</span>
              )}
            </span>
            <span className="text-text-muted">{deltaExpanded ? "▲" : "▼"}</span>
          </button>
          {deltaExpanded && (
            <div className="border-t border-border px-3 pb-3 pt-2 space-y-2">
              {delta.has_previous ? (
                <>
                  <div className="flex flex-wrap gap-x-5 gap-y-0.5 font-mono text-2xs text-text-muted">
                    <span>added: <span className="text-teal-400">{delta.added_count}</span></span>
                    <span>removed: <span className="text-red-400">{delta.removed_count}</span></span>
                    <span>common: <span className="text-text-secondary">{delta.common_symbols_count}</span></span>
                    <span>overlap: <span className="text-text-secondary">{fmtRatio(delta.overlap_ratio)}</span></span>
                    <span>jaccard: <span className="text-text-secondary">{fmtRatio(delta.jaccard_similarity)}</span></span>
                    <span>churn: <span className="text-text-secondary">{fmtRatio(delta.churn_rate)}</span></span>
                  </div>
                  {delta.added_symbols.length > 0 && (
                    <div>
                      <p className="font-mono text-2xs text-text-muted mb-1">Added (up to 10):</p>
                      <div className="flex flex-wrap gap-1">
                        {delta.added_symbols.slice(0, 10).map((sym) => (
                          <span key={sym} className="rounded px-1.5 py-0.5 bg-teal-400/10 font-mono text-2xs text-teal-400 border border-teal-400/20">{sym}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {delta.removed_symbols.length > 0 && (
                    <div>
                      <p className="font-mono text-2xs text-text-muted mb-1">Removed (up to 10):</p>
                      <div className="flex flex-wrap gap-1">
                        {delta.removed_symbols.slice(0, 10).map((sym) => (
                          <span key={sym} className="rounded px-1.5 py-0.5 bg-red-400/10 font-mono text-2xs text-red-400 border border-red-400/20">{sym}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {delta.previous_label && (
                    <p className="font-mono text-2xs text-text-muted/60">vs. {delta.previous_label}</p>
                  )}
                </>
              ) : (
                <p className="font-mono text-2xs text-text-muted">No previous snapshot to compare against.</p>
              )}
            </div>
          )}
        </div>

        {/* C. Metadata breakdown (collapsible) */}
        <div className="rounded-control border border-border bg-bg-800">
          <button
            className="w-full flex items-center justify-between px-3 py-2 font-mono text-2xs text-text-secondary hover:text-text-primary"
            onClick={() => setMetaExpanded((v) => !v)}
          >
            <span>Metadata Breakdown</span>
            <span className="flex items-center gap-2">
              <span className="text-text-muted">{meta.has_symbol_metadata ? "available" : "none"}</span>
              <span className="text-text-muted">{metaExpanded ? "▲" : "▼"}</span>
            </span>
          </button>
          {metaExpanded && (
            <div className="border-t border-border px-3 pb-3 pt-2 space-y-1">
              <div className="flex flex-wrap gap-x-5 gap-y-0.5 font-mono text-2xs text-text-muted">
                <span>coverage: <span className="text-text-secondary">{fmtRatio(meta.metadata_coverage_rate)}</span></span>
                <span>missing metadata: <span className="text-text-secondary">{meta.missing_metadata_symbols}</span></span>
              </div>
              {meta.has_symbol_metadata && (
                <>
                  <MetaDict label="by_sector" data={meta.by_sector} />
                  <MetaDict label="by_country" data={meta.by_country} />
                  <MetaDict label="by_exchange" data={meta.by_exchange} />
                  <MetaDict label="by_liquidity_bucket" data={meta.by_liquidity_bucket} />
                </>
              )}
              {meta.warnings.length > 0 && (
                <ul className="pt-1 space-y-0.5">
                  {meta.warnings.map((w, i) => (
                    <li key={i} className="font-mono text-2xs text-yellow-400">• {w}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {/* D. Symbol quality table (collapsible, top 50 non-clean) */}
        <div className="rounded-control border border-border bg-bg-800">
          <button
            className="w-full flex items-center justify-between px-3 py-2 font-mono text-2xs text-text-secondary hover:text-text-primary"
            onClick={() => setSymExpanded((v) => !v)}
          >
            <span>Symbol Quality ({nonCleanSymbols.length} issues)</span>
            <span className="text-text-muted">{symExpanded ? "▲" : "▼"}</span>
          </button>
          {symExpanded && (
            <div className="border-t border-border px-3 pb-3 pt-2">
              {nonCleanSymbols.length === 0 ? (
                <p className="font-mono text-2xs text-teal-400">All symbols clean.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full font-mono text-2xs border-collapse">
                    <thead>
                      <tr className="text-text-muted border-b border-border">
                        <th className="text-left pb-1 pr-3">Symbol</th>
                        <th className="text-left pb-1 pr-3">Normalized</th>
                        <th className="text-left pb-1 pr-3">Dup</th>
                        <th className="text-left pb-1 pr-3">Status</th>
                        <th className="text-left pb-1">Issues</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/40">
                      {nonCleanSymbols.slice(0, 50).map((sq) => (
                        <tr key={sq.symbol + sq.normalized_symbol} className="align-top">
                          <td className="py-0.5 pr-3 text-text-secondary">{sq.symbol}</td>
                          <td className="py-0.5 pr-3 text-text-muted/70">{sq.normalized_symbol}</td>
                          <td className="py-0.5 pr-3">{sq.is_duplicate ? <span className="text-orange-400">yes</span> : <span className="text-text-muted/40">—</span>}</td>
                          <td className={`py-0.5 pr-3 ${symbolStatusColor(sq.quality_status)}`}>{sq.quality_status}</td>
                          <td className="py-0.5 text-text-muted/70">{sq.issues.join(", ") || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>

        {/* E. Suggested checks */}
        {qs.suggested_checks.length > 0 && (
          <div className="rounded-control border border-amber-400/20 bg-amber-400/5 px-3 py-2 space-y-0.5">
            <p className="font-mono text-2xs text-amber-400/80 font-semibold mb-1">Suggested Checks</p>
            {qs.suggested_checks.map((c, i) => (
              <p key={i} className="font-mono text-2xs text-text-secondary">• {c}</p>
            ))}
          </div>
        )}

        {/* F. Disclaimer */}
        <p className="font-mono text-2xs text-text-muted/50">
          Universe coverage analysis is deterministic. Not investment advice.
        </p>

      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// M40: Config Diff Panel
// ---------------------------------------------------------------------------

function impactColor(impact: string): string {
  switch (impact) {
    case "positive": return "text-teal-400";
    case "review": return "text-yellow-400";
    case "weakening": return "text-red-400";
    default: return "text-text-muted";
  }
}

function changeTypeLabel(ct: string): string {
  switch (ct) {
    case "added": return "Added";
    case "removed": return "Removed";
    case "changed": return "Changed";
    default: return ct;
  }
}

function ConfigFieldRow({ change }: { change: ConfigFieldChange }) {
  return (
    <div className="py-1.5 flex flex-wrap gap-2 items-start">
      <span className={`font-mono text-2xs font-semibold shrink-0 ${impactColor(change.impact_level)}`}>
        [{changeTypeLabel(change.change_type)}]
      </span>
      <span className="font-mono text-2xs text-text-secondary break-all">{change.key_path || change.key}</span>
      {change.impact_reason && (
        <span className="font-mono text-2xs text-text-muted">— {change.impact_reason}</span>
      )}
      {change.suggested_check && (
        <span className="font-mono text-2xs text-accent-300">↳ {change.suggested_check}</span>
      )}
    </div>
  );
}

function ConfigDiffTable({ section, title }: { section: ConfigDiffSection; title: string }) {
  const [open, setOpen] = useState(false);
  if (section.changes.length === 0) return null;
  return (
    <div className="rounded-control border border-border bg-bg-800">
      <button
        className="w-full flex items-center justify-between px-3 py-2 font-mono text-2xs text-text-secondary hover:text-text-primary"
        onClick={() => setOpen((v) => !v)}
      >
        <span>{title} <span className="text-text-muted">({section.changes.length} change{section.changes.length !== 1 ? "s" : ""})</span></span>
        <span className="text-text-muted">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-border overflow-x-auto">
          <table className="w-full text-left font-mono text-2xs">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 pb-1.5 pt-2.5 text-text-muted font-normal">Key</th>
                <th className="px-3 pb-1.5 pt-2.5 text-text-muted font-normal">Old Value</th>
                <th className="px-3 pb-1.5 pt-2.5 text-text-muted font-normal">New Value</th>
                <th className="px-3 pb-1.5 pt-2.5 pr-4 text-text-muted font-normal">Impact</th>
              </tr>
            </thead>
            <tbody>
              {section.changes.map((c, i) => (
                <tr key={i} className="border-b border-border/50 last:border-0">
                  <td className="px-4 py-1.5 text-text-secondary break-all">{c.key_path || c.key}</td>
                  <td className="px-3 py-1.5 text-orange-400">{c.old_value !== undefined && c.old_value !== null ? JSON.stringify(c.old_value) : <span className="text-text-muted/50">—</span>}</td>
                  <td className="px-3 py-1.5 text-teal-400">{c.new_value !== undefined && c.new_value !== null ? JSON.stringify(c.new_value) : <span className="text-text-muted/50">—</span>}</td>
                  <td className={`px-3 py-1.5 pr-4 ${impactColor(c.impact_level)}`}>{c.impact_level}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ConfigDiffChangeGroup({
  changes,
  title,
  headerColor,
}: {
  changes: ConfigFieldChange[];
  title: string;
  headerColor: string;
}) {
  const [open, setOpen] = useState(false);
  if (changes.length === 0) return null;
  return (
    <div className="rounded-control border border-border bg-bg-800">
      <button
        className={`w-full flex items-center justify-between px-3 py-2 font-mono text-2xs ${headerColor} hover:opacity-80`}
        onClick={() => setOpen((v) => !v)}
      >
        <span>{title} <span className="opacity-70">({changes.length})</span></span>
        <span className="opacity-60">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-border px-3 py-2 space-y-0.5">
          {changes.map((c, i) => <ConfigFieldRow key={i} change={c} />)}
        </div>
      )}
    </div>
  );
}

function ConfigDiffPanel({ diff }: { diff: ConfigSnapshotComparisonV2Response }) {
  return (
    <div className="rounded-card border border-border bg-bg-700">
      {/* Header */}
      <div className="border-b border-border px-4 py-2.5">
        <p className="caption">Config Diff</p>
        <p className="mt-0.5 font-mono text-xs text-text-secondary">
          {diff.snapshot_a_label} <span className="text-text-muted">→</span> {diff.snapshot_b_label}
        </p>
      </div>

      <div className="p-4 space-y-3">

        {/* A. Summary strip */}
        <div className="flex flex-wrap gap-4 font-mono text-2xs">
          <span className="text-text-secondary">
            total changes: <span className="font-semibold text-text-primary">{diff.total_changes}</span>
          </span>
          <span className={diff.weakening_changes.length > 0 ? "text-red-400 font-semibold" : "text-text-muted"}>
            weakening: {diff.weakening_changes.length}
          </span>
          <span className={diff.positive_changes.length > 0 ? "text-teal-400 font-semibold" : "text-text-muted"}>
            positive: {diff.positive_changes.length}
          </span>
          <span className={diff.review_changes.length > 0 ? "text-yellow-400 font-semibold" : "text-text-muted"}>
            review: {diff.review_changes.length}
          </span>
          {diff.is_same_config && (
            <span className="text-fidelity-high">identical configs</span>
          )}
        </div>

        {/* B. Deterministic explanation */}
        {diff.deterministic_explanation && (
          <p className="font-mono text-2xs text-text-muted italic leading-relaxed">
            {diff.deterministic_explanation}
          </p>
        )}

        {/* C. Highlighted changes */}
        {diff.highlighted_changes.length > 0 && (
          <div className="rounded-control border border-border/60 bg-bg-800 px-3 py-2">
            <p className="font-mono text-2xs text-text-muted mb-1">Highlighted Changes</p>
            <ul className="space-y-0.5">
              {diff.highlighted_changes.map((h, i) => (
                <li key={i} className="font-mono text-2xs text-text-secondary">• {h}</li>
              ))}
            </ul>
          </div>
        )}

        {/* D. Weakening changes */}
        <ConfigDiffChangeGroup
          changes={diff.weakening_changes}
          title="Weakening Changes"
          headerColor="text-red-400"
        />

        {/* E. Positive changes */}
        <ConfigDiffChangeGroup
          changes={diff.positive_changes}
          title="Positive Changes"
          headerColor="text-teal-400"
        />

        {/* F. Params diff table */}
        <ConfigDiffTable section={diff.params_diff} title="Params Diff" />

        {/* G. Assumptions diff table */}
        <ConfigDiffTable section={diff.assumptions_diff} title="Assumptions Diff" />

        {/* H. Portfolio diff table */}
        <ConfigDiffTable section={diff.portfolio_diff} title="Portfolio Diff" />

        {/* I. Risk diff table */}
        <ConfigDiffTable section={diff.risk_diff} title="Risk Diff" />

        {/* J. Suggested checks */}
        {diff.suggested_checks.length > 0 && (
          <div className="rounded-control border border-border/60 bg-bg-800 px-3 py-2">
            <p className="font-mono text-2xs text-text-muted mb-1">Suggested Checks</p>
            <ul className="space-y-0.5">
              {diff.suggested_checks.map((c, i) => (
                <li key={i} className="font-mono text-2xs text-accent-300">↳ {c}</li>
              ))}
            </ul>
          </div>
        )}

        {/* K. Disclaimer */}
        <p className="font-mono text-2xs text-text-muted/50">
          Deterministic config diff. Not investment advice.
        </p>

      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// M41: Assumption Health Panel
// ---------------------------------------------------------------------------

function assumptionStatusBadgeClass(status: string): string {
  switch (status) {
    case "strong": return "text-teal-400 bg-teal-900/20 border border-teal-700/30";
    case "acceptable": return "text-text-secondary bg-bg-700 border border-border";
    case "review": return "text-yellow-400 bg-yellow-900/20 border border-yellow-700/30";
    case "weak": return "text-red-400 bg-red-900/20 border border-red-700/30";
    default: return "text-text-muted bg-bg-700 border border-border";
  }
}

function assumptionCategoryStatusColor(status: string): string {
  switch (status) {
    case "strong": return "text-teal-400";
    case "acceptable": return "text-text-secondary";
    case "review": return "text-yellow-400";
    case "weak": return "text-red-400";
    default: return "text-text-muted";
  }
}

function assumptionScoreColor(score: number | null): string {
  if (score === null) return "text-text-muted";
  if (score >= 85) return "text-teal-400";
  if (score >= 70) return "text-text-secondary";
  if (score >= 50) return "text-amber-400";
  return "text-red-400";
}

function AssumptionHealthPanel({ health }: { health: StrategyAssumptionHealthResponse }) {
  return (
    <div className="rounded-panel border border-border bg-bg-900 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-mono text-xs font-semibold text-text-primary">Assumption Health</h3>
        <span className="font-mono text-2xs text-text-muted">{fmtDate(health.generated_at)}</span>
      </div>

      {/* A. Overall score + status badge */}
      <div className="flex items-center gap-3">
        <span className={`font-mono text-3xl font-bold ${assumptionScoreColor(health.overall_assumption_score)}`}>
          {health.overall_assumption_score !== null ? health.overall_assumption_score.toFixed(1) : "—"}
        </span>
        <span className={`rounded px-2 py-0.5 font-mono text-2xs ${assumptionStatusBadgeClass(health.status)}`}>
          {health.status}
        </span>
      </div>

      {/* B. Deterministic summary */}
      {health.deterministic_summary && (
        <p className="font-mono text-2xs italic text-text-muted line-clamp-2">
          {health.deterministic_summary}
        </p>
      )}

      {/* C. Category scorecard grid */}
      {health.category_scorecards.length > 0 && (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {health.category_scorecards.map((cat: AssumptionCategoryScorecard) => (
            <div key={cat.category_key} className="rounded-control border border-border bg-bg-800 px-3 py-2 space-y-1">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-2xs text-text-secondary truncate">{cat.title}</span>
                <span className={`font-mono text-2xs ${assumptionCategoryStatusColor(cat.status)}`}>
                  {cat.status}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className={`font-mono text-xs font-semibold ${assumptionScoreColor(cat.score)}`}>
                  {cat.score !== null ? cat.score.toFixed(1) : "—"}
                </span>
                <span className="font-mono text-2xs text-text-muted">
                  {cat.evidence_count} evidence
                </span>
              </div>
              {(cat.score !== null && cat.score < 70 || cat.status !== "strong") && (
                <div className="space-y-0.5 pt-0.5">
                  {cat.review_items[0] && (
                    <p className="font-mono text-2xs text-text-muted truncate">⚠ {cat.review_items[0]}</p>
                  )}
                  {cat.suggested_checks[0] && (
                    <p className="font-mono text-2xs text-text-muted/70 truncate">↳ {cat.suggested_checks[0]}</p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* D. Config assumption changes */}
      {health.latest_config_diff_summary && !health.latest_config_diff_summary.warning && (
        <div className="rounded-control border border-border bg-bg-800 px-3 py-2 space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-2xs text-text-secondary font-semibold">Config Changes</span>
            {health.latest_config_diff_summary.positive_change_count > 0 && (
              <span className="rounded px-1.5 py-0.5 font-mono text-2xs text-teal-400 bg-teal-900/20 border border-teal-700/30">
                +{health.latest_config_diff_summary.positive_change_count} positive
              </span>
            )}
            {health.latest_config_diff_summary.weakening_change_count > 0 && (
              <span className="rounded px-1.5 py-0.5 font-mono text-2xs text-red-400 bg-red-900/20 border border-red-700/30">
                -{health.latest_config_diff_summary.weakening_change_count} weakening
              </span>
            )}
            {health.latest_config_diff_summary.review_change_count > 0 && (
              <span className="rounded px-1.5 py-0.5 font-mono text-2xs text-yellow-400 bg-yellow-900/20 border border-yellow-700/30">
                {health.latest_config_diff_summary.review_change_count} review
              </span>
            )}
          </div>
          {health.latest_config_diff_summary.weakening_change_count > 0 &&
            health.latest_config_diff_summary.key_assumption_changes.slice(0, 5).map((change, i) => {
              const c = change as { key?: string; old_value?: unknown; new_value?: unknown; impact_level?: string };
              return (
                <div key={i} className="flex items-center gap-2 font-mono text-2xs text-text-muted flex-wrap">
                  <span className="text-text-secondary">{c.key ?? "—"}</span>
                  <span>{String(c.old_value ?? "—")}</span>
                  <span className="text-text-muted">→</span>
                  <span>{String(c.new_value ?? "—")}</span>
                  {c.impact_level && (
                    <span className="rounded px-1 py-0.5 text-2xs text-red-400 bg-red-900/20 border border-red-700/30">
                      {c.impact_level}
                    </span>
                  )}
                </div>
              );
            })
          }
        </div>
      )}

      {/* E. Backtest audit synthesis */}
      {health.latest_backtest_audit_summary && (
        <div className="rounded-control border border-border bg-bg-800 px-3 py-2 space-y-2">
          <p className="font-mono text-2xs text-text-secondary font-semibold">Backtest Audit Synthesis</p>
          <div className="flex flex-wrap gap-x-4 gap-y-0.5 font-mono text-2xs text-text-muted">
            <span>Trust: <span className={assumptionScoreColor(health.latest_backtest_audit_summary.trust_score)}>
              {health.latest_backtest_audit_summary.trust_score.toFixed(1)}
            </span></span>
            {health.latest_backtest_audit_summary.fill_realism_level && (
              <span>Fill: <span className="text-text-secondary">{health.latest_backtest_audit_summary.fill_realism_level}</span></span>
            )}
            {health.latest_backtest_audit_summary.cost_fragility_level && (
              <span>Cost fragility: <span className="text-text-secondary">{health.latest_backtest_audit_summary.cost_fragility_level}</span></span>
            )}
            {health.latest_backtest_audit_summary.largest_penalty_category && (
              <span>Largest penalty: <span className="text-text-secondary">{health.latest_backtest_audit_summary.largest_penalty_category}</span></span>
            )}
          </div>
          {health.latest_backtest_audit_summary.top_improvement_checks.length > 0 && (
            <ul className="space-y-0.5">
              {(health.latest_backtest_audit_summary.top_improvement_checks.slice(0, 3) as { check_key?: string; title?: string }[]).map((chk, i) => (
                <li key={i} className="font-mono text-2xs text-text-muted">
                  ↳ <span className="text-accent-300">{chk.check_key ?? "—"}</span>
                  {chk.title ? <span> — {chk.title}</span> : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* F. Suggested checks */}
      {health.suggested_checks.length > 0 && (
        <div className="rounded-control border border-border/60 bg-bg-800 px-3 py-2">
          <p className="font-mono text-2xs text-text-muted mb-1">Suggested Checks</p>
          <ul className="space-y-0.5">
            {health.suggested_checks.slice(0, 8).map((c, i) => (
              <li key={i} className="font-mono text-2xs text-accent-300">↳ {c}</li>
            ))}
          </ul>
        </div>
      )}

      {/* G. Disclaimer */}
      <p className="font-mono text-2xs text-text-muted/50">
        Deterministic summary. Not investment advice.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// M43: TimelineAnalyticsPanel
// ---------------------------------------------------------------------------

function stalenessBadgeClass(status: string): string {
  switch (status) {
    case "active":      return "text-teal-400 bg-teal-900/20 border border-teal-700/30";
    case "watch":       return "text-yellow-400 bg-yellow-900/20 border border-yellow-700/30";
    case "stale":       return "text-red-400 bg-red-900/20 border border-red-700/30";
    case "no_activity": return "text-text-muted bg-bg-700 border border-border";
    default:            return "text-text-muted bg-bg-700 border border-border";
  }
}

function categoryColor(cat: string): string {
  switch (cat) {
    case "run":         return "bg-accent-500/20 text-accent-400 border-accent-500/30";
    case "data":        return "bg-blue-900/20 text-blue-400 border-blue-700/30";
    case "backtest":    return "bg-yellow-900/20 text-yellow-400 border-yellow-700/30";
    case "config":      return "bg-bg-600 text-text-muted border-border";
    case "universe":    return "bg-teal-900/20 text-teal-400 border-teal-700/30";
    case "signal":      return "bg-cyan-900/20 text-cyan-400 border-cyan-700/30";
    case "reliability": return "bg-green-900/20 text-green-400 border-green-700/30";
    case "report":      return "bg-purple-900/20 text-purple-400 border-purple-700/30";
    case "alert":       return "bg-red-900/20 text-red-400 border-red-700/30";
    case "ingestion":   return "bg-orange-900/20 text-orange-400 border-orange-700/30";
    default:            return "bg-bg-600 text-text-secondary border-border";
  }
}

function barColor(count: number): string {
  if (count === 0)  return "bg-bg-600";
  if (count <= 2)   return "bg-teal-700/60";
  if (count <= 5)   return "bg-teal-600/80";
  return "bg-teal-500";
}

function TimelineAnalyticsPanel({ analytics }: { analytics: StrategyTimelineAnalyticsResponse }) {
  // B: limit to last 26 buckets
  const displayBuckets: TimelineAnalyticsBucket[] = analytics.buckets.slice(-26);
  const maxEvents = Math.max(...displayBuckets.map((b) => b.total_events), 1);

  // C: aggregate evidence_category_counts across all buckets
  const categoryTotals: Record<string, number> = {};
  for (const bucket of analytics.buckets) {
    for (const [cat, cnt] of Object.entries(bucket.evidence_category_counts)) {
      categoryTotals[cat] = (categoryTotals[cat] ?? 0) + cnt;
    }
  }
  const topCategories = Object.entries(categoryTotals)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

  // D: gaps with 14+ days
  const displayGaps: TimelineInactivityGap[] = analytics.gaps.slice(0, 5);

  const bucketLabel = analytics.bucket === "weekly" ? "weekly" : analytics.bucket ?? "period";

  return (
    <div className="rounded-panel border border-border bg-bg-900 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-mono text-xs font-semibold text-text-primary">Timeline Analytics</h3>
        <span className="font-mono text-2xs text-text-muted">{analytics.generated_at.slice(0, 10)}</span>
      </div>

      {/* A. Summary strip */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-2xs text-text-muted">
          Total events: <span className="text-text-primary font-semibold">{analytics.total_events}</span>
        </span>
        {analytics.days_since_latest_event != null && (
          <span className="font-mono text-2xs text-text-muted">
            Last event: <span className="text-text-secondary">{analytics.days_since_latest_event}d ago</span>
          </span>
        )}
        <span className={`rounded px-2 py-0.5 font-mono text-2xs ${stalenessBadgeClass(analytics.staleness_status)}`}>
          {analytics.staleness_status.replace("_", " ")}
        </span>
        {analytics.dominant_evidence_category && (
          <span className={`rounded border px-2 py-0.5 font-mono text-2xs ${categoryColor(analytics.dominant_evidence_category)}`}>
            {analytics.dominant_evidence_category}
          </span>
        )}
        {analytics.longest_inactivity_gap_days != null && analytics.longest_inactivity_gap_days > 0 && (
          <span className="font-mono text-2xs text-text-muted">
            Longest gap: <span className="text-text-secondary">{analytics.longest_inactivity_gap_days}d</span>
          </span>
        )}
      </div>

      {/* B. Activity bar chart */}
      {displayBuckets.length > 0 && (
        <div>
          <p className="mb-1.5 font-mono text-2xs font-semibold uppercase tracking-wider text-text-muted/60">
            Event Activity ({bucketLabel})
          </p>
          <div className="flex items-end gap-px" style={{ height: "48px" }}>
            {displayBuckets.map((bucket, i) => {
              const heightPct = bucket.total_events > 0
                ? Math.max(8, Math.round((bucket.total_events / maxEvents) * 100))
                : 4;
              return (
                <div
                  key={i}
                  className="flex flex-col items-center flex-1 min-w-0"
                  style={{ height: "48px", justifyContent: "flex-end" }}
                >
                  <div
                    className={`w-full rounded-sm ${barColor(bucket.total_events)}`}
                    style={{ height: `${heightPct}%` }}
                    title={`${bucket.bucket_start.slice(0, 10)} – ${bucket.bucket_end.slice(0, 10)}: ${bucket.total_events} event${bucket.total_events !== 1 ? "s" : ""}`}
                  />
                </div>
              );
            })}
          </div>
          <div className="flex items-start gap-px mt-0.5">
            {displayBuckets.map((bucket, i) => (
              <div key={i} className="flex-1 min-w-0 text-center">
                {bucket.total_events > 0 && (
                  <span className="font-mono text-2xs text-text-muted/50 leading-none" style={{ fontSize: "9px" }}>
                    {bucket.total_events}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* C. Evidence category mix */}
      {topCategories.length > 0 && (
        <div>
          <p className="mb-1.5 font-mono text-2xs font-semibold uppercase tracking-wider text-text-muted/60">
            Evidence Categories
          </p>
          <div className="flex flex-wrap gap-1.5">
            {topCategories.map(([cat, count]) => (
              <span
                key={cat}
                className={`rounded border px-2 py-0.5 font-mono text-2xs ${categoryColor(cat)}`}
              >
                {cat} <span className="opacity-70">{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* D. Inactivity gaps */}
      {displayGaps.length > 0 && (
        <div>
          <p className="mb-1.5 font-mono text-2xs font-semibold uppercase tracking-wider text-text-muted/60">
            Inactivity Gaps (14+ days)
          </p>
          <ul className="space-y-1">
            {displayGaps.map((gap, i) => (
              <li key={i} className="font-mono text-2xs text-text-secondary">
                <span className="text-text-primary">{gap.gap_days}d</span>
                {" "}
                <span className="text-text-muted">
                  ({gap.gap_start.slice(0, 10)} – {gap.gap_end.slice(0, 10)})
                </span>
                {gap.previous_event_title && (
                  <span className="text-text-muted"> after &ldquo;{gap.previous_event_title}&rdquo;</span>
                )}
                {gap.next_event_title && (
                  <span className="text-text-muted"> before &ldquo;{gap.next_event_title}&rdquo;</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* E. Deterministic summary */}
      {analytics.deterministic_summary && (
        <p className="font-mono text-2xs italic text-text-muted">{analytics.deterministic_summary}</p>
      )}

      {/* F. Suggested checks */}
      {analytics.suggested_checks.length > 0 && (
        <div>
          <p className="mb-1 font-mono text-2xs font-semibold uppercase tracking-wider text-text-muted/60">
            Suggested Checks
          </p>
          <ul className="space-y-0.5">
            {analytics.suggested_checks.map((check, i) => (
              <li key={i} className="font-mono text-2xs text-text-secondary before:content-['–'] before:mr-1.5 before:text-text-muted">
                {check}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* G. Disclaimer */}
      <p className="font-mono text-2xs text-text-muted/40">
        Deterministic timeline analytics. Not investment advice.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// M47: Drift Panel
// ---------------------------------------------------------------------------

function driftStatusClasses(status: string): string {
  switch (status) {
    case "stable": return "text-teal-400 bg-teal-900/20 border-teal-700/30";
    case "watch": return "text-yellow-400 bg-yellow-900/20 border-yellow-700/30";
    case "review": return "text-orange-400 bg-orange-900/20 border-orange-700/30";
    case "severe": return "text-red-400 bg-red-900/20 border-red-700/30";
    default: return "text-text-muted bg-bg-700 border-border";
  }
}

function driftSeverityColor(severity: string): string {
  switch (severity) {
    case "high": return "text-red-400";
    case "medium": return "text-yellow-400";
    case "low": return "text-text-secondary";
    default: return "text-text-muted";
  }
}

function directionIcon(direction: string): string {
  switch (direction) {
    case "improved": return "▲";
    case "deteriorated": return "▼";
    case "changed": return "↔";
    case "unchanged": return "—";
    default: return "?";
  }
}

function impactChipColor(level: string): string {
  switch (level) {
    case "high": return "text-red-400 bg-red-900/20 border-red-700/30";
    case "medium": return "text-yellow-400 bg-yellow-900/20 border-yellow-700/30";
    case "low": return "text-text-secondary bg-bg-700 border-border";
    default: return "text-text-muted bg-bg-700 border-border";
  }
}

function MetricDriftTable({ items }: { items: MetricDriftItem[] }) {
  const [open, setOpen] = useState(false);
  const visible = items.filter((r) => r.severity !== "none");
  if (visible.length === 0) return null;
  return (
    <div className="rounded-control border border-border bg-bg-800">
      <button
        className="w-full flex items-center justify-between px-3 py-2 font-mono text-2xs text-text-secondary hover:text-text-primary"
        onClick={() => setOpen((v) => !v)}
      >
        <span>Metric Drift <span className="text-text-muted">({visible.length} metric{visible.length !== 1 ? "s" : ""})</span></span>
        <span className="text-text-muted">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-border overflow-x-auto">
          <table className="w-full text-left font-mono text-2xs">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 pb-1.5 pt-2.5 text-text-muted font-normal">Metric</th>
                <th className="px-3 pb-1.5 pt-2.5 text-text-muted font-normal">Baseline</th>
                <th className="px-3 pb-1.5 pt-2.5 text-text-muted font-normal">Comparison</th>
                <th className="px-3 pb-1.5 pt-2.5 text-text-muted font-normal">Delta</th>
                <th className="px-3 pb-1.5 pt-2.5 text-text-muted font-normal">Direction</th>
                <th className="px-3 pb-1.5 pt-2.5 pr-4 text-text-muted font-normal">Severity</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r, i) => (
                <tr key={i} className="border-b border-border/50 last:border-0">
                  <td className="px-4 py-1.5 text-text-secondary">{r.metric}</td>
                  <td className="px-3 py-1.5 text-text-muted">{r.baseline_value !== null ? r.baseline_value.toFixed(4) : "—"}</td>
                  <td className="px-3 py-1.5 text-text-muted">{r.comparison_value !== null ? r.comparison_value.toFixed(4) : "—"}</td>
                  <td className="px-3 py-1.5 text-text-muted">{r.absolute_delta !== null ? r.absolute_delta.toFixed(4) : "—"}</td>
                  <td className="px-3 py-1.5 text-text-muted">{directionIcon(r.direction)}</td>
                  <td className={`px-3 py-1.5 pr-4 ${driftSeverityColor(r.severity)}`}>{r.severity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function EvidenceDriftTable({ items }: { items: EvidenceDriftItem[] }) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  return (
    <div className="rounded-control border border-border bg-bg-800">
      <button
        className="w-full flex items-center justify-between px-3 py-2 font-mono text-2xs text-text-secondary hover:text-text-primary"
        onClick={() => setOpen((v) => !v)}
      >
        <span>Evidence Drift <span className="text-text-muted">({items.length} item{items.length !== 1 ? "s" : ""})</span></span>
        <span className="text-text-muted">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-border overflow-x-auto">
          <table className="w-full text-left font-mono text-2xs">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 pb-1.5 pt-2.5 text-text-muted font-normal">Evidence</th>
                <th className="px-3 pb-1.5 pt-2.5 text-text-muted font-normal">Baseline</th>
                <th className="px-3 pb-1.5 pt-2.5 text-text-muted font-normal">Comparison</th>
                <th className="px-3 pb-1.5 pt-2.5 text-text-muted font-normal">Severity</th>
                <th className="px-3 pb-1.5 pt-2.5 pr-4 text-text-muted font-normal">Explanation</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r, i) => (
                <tr key={i} className="border-b border-border/50 last:border-0">
                  <td className="px-4 py-1.5 text-text-secondary">{r.evidence_type}</td>
                  <td className="px-3 py-1.5 text-text-muted">{r.baseline_value !== null ? r.baseline_value.toFixed(4) : "—"}</td>
                  <td className="px-3 py-1.5 text-text-muted">{r.comparison_value !== null ? r.comparison_value.toFixed(4) : "—"}</td>
                  <td className={`px-3 py-1.5 ${driftSeverityColor(r.severity)}`}>{r.severity}</td>
                  <td className="px-3 py-1.5 pr-4 text-text-muted">{r.explanation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AssumptionDriftList({ items }: { items: AssumptionDriftItem[] }) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  return (
    <div className="rounded-control border border-border bg-bg-800">
      <button
        className="w-full flex items-center justify-between px-3 py-2 font-mono text-2xs text-text-secondary hover:text-text-primary"
        onClick={() => setOpen((v) => !v)}
      >
        <span>Assumption Drift <span className="text-text-muted">({items.length} item{items.length !== 1 ? "s" : ""})</span></span>
        <span className="text-text-muted">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-border px-3 pb-3 pt-2 space-y-1.5">
          {items.map((item, i) => (
            <div key={i} className="flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-2xs text-accent-300">{item.key_path}</span>
              <span className="font-mono text-2xs text-text-muted">:</span>
              <span className="font-mono text-2xs text-orange-400">{item.old_value !== null && item.old_value !== undefined ? JSON.stringify(item.old_value) : "—"}</span>
              <span className="font-mono text-2xs text-text-muted">→</span>
              <span className="font-mono text-2xs text-teal-400">{item.new_value !== null && item.new_value !== undefined ? JSON.stringify(item.new_value) : "—"}</span>
              <span className={`rounded border px-1 py-0.5 font-mono text-2xs ${impactChipColor(item.impact_level)}`}>{item.impact_level}</span>
              {item.suggested_check && (
                <span className="font-mono text-2xs text-text-muted/70 w-full">↳ {item.suggested_check}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TrustDriftList({ items }: { items: { dimension: string; severity: string; explanation: string; baseline_value: number | null; comparison_value: number | null; delta: number | null }[] }) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  return (
    <div className="rounded-control border border-border bg-bg-800">
      <button
        className="w-full flex items-center justify-between px-3 py-2 font-mono text-2xs text-text-secondary hover:text-text-primary"
        onClick={() => setOpen((v) => !v)}
      >
        <span>Trust Drift <span className="text-text-muted">({items.length} item{items.length !== 1 ? "s" : ""})</span></span>
        <span className="text-text-muted">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-border overflow-x-auto">
          <table className="w-full text-left font-mono text-2xs">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 pb-1.5 pt-2.5 text-text-muted font-normal">Dimension</th>
                <th className="px-3 pb-1.5 pt-2.5 text-text-muted font-normal">Baseline</th>
                <th className="px-3 pb-1.5 pt-2.5 text-text-muted font-normal">Comparison</th>
                <th className="px-3 pb-1.5 pt-2.5 text-text-muted font-normal">Delta</th>
                <th className="px-3 pb-1.5 pt-2.5 pr-4 text-text-muted font-normal">Severity</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r, i) => (
                <tr key={i} className="border-b border-border/50 last:border-0">
                  <td className="px-4 py-1.5 text-text-secondary">{r.dimension}</td>
                  <td className="px-3 py-1.5 text-text-muted">{r.baseline_value !== null ? r.baseline_value.toFixed(4) : "—"}</td>
                  <td className="px-3 py-1.5 text-text-muted">{r.comparison_value !== null ? r.comparison_value.toFixed(4) : "—"}</td>
                  <td className="px-3 py-1.5 text-text-muted">{r.delta !== null ? r.delta.toFixed(4) : "—"}</td>
                  <td className={`px-3 py-1.5 pr-4 ${driftSeverityColor(r.severity)}`}>{r.severity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function freshnessStatusClasses(status: string): { text: string; bg: string; border: string } {
  switch (status) {
    case "fresh":
      return { text: "text-teal-400", bg: "bg-teal-900/20", border: "border-teal-700/30" };
    case "aging":
      return { text: "text-yellow-400", bg: "bg-yellow-900/20", border: "border-yellow-700/30" };
    case "stale":
      return { text: "text-red-400", bg: "bg-red-900/20", border: "border-red-700/30" };
    case "missing":
    case "missing_evidence":
    default:
      return { text: "text-text-muted", bg: "bg-bg-700", border: "border-border" };
  }
}

function freshnessSeverityColor(severity: string): string {
  switch (severity) {
    case "high":
      return "text-red-400";
    case "medium":
      return "text-yellow-400";
    case "low":
      return "text-text-secondary";
    default:
      return "text-text-muted";
  }
}

function freshnessScoreColor(score: number | null): string {
  if (score === null) return "text-text-muted";
  if (score >= 85) return "text-teal-400";
  if (score >= 65) return "text-yellow-400";
  return "text-red-400";
}

function FreshnessPanel({ freshness }: { freshness: StrategyEvidenceFreshnessResponse }) {
  const [refreshExpanded, setRefreshExpanded] = useState(false);
  const overallClasses = freshnessStatusClasses(freshness.freshness_status);

  return (
    <div className="rounded-card border border-border bg-bg-700">
      {/* Header */}
      <div className="border-b border-border px-4 py-2.5 flex items-center justify-between gap-2">
        <p className="caption">Evidence Freshness</p>
        <span className="font-mono text-2xs text-text-muted">
          {new Date(freshness.generated_at).toLocaleString("en-US", {
            month: "short", day: "numeric", year: "numeric",
            hour: "2-digit", minute: "2-digit",
          })}
        </span>
      </div>

      <div className="p-4 space-y-4">
        {/* A. Summary strip */}
        <div className="flex flex-wrap items-center gap-3">
          <span className={`mono-num text-lg font-bold ${freshnessScoreColor(freshness.overall_freshness_score)}`}>
            {freshness.overall_freshness_score !== null ? freshness.overall_freshness_score : "—"}
          </span>
          <span className={`rounded px-2 py-0.5 font-mono text-2xs border ${overallClasses.text} ${overallClasses.bg} ${overallClasses.border}`}>
            {freshness.freshness_status}
          </span>
          <div className="flex flex-wrap gap-2 font-mono text-2xs">
            {freshness.fresh_count > 0 && (
              <span className="text-teal-400">{freshness.fresh_count} fresh</span>
            )}
            {freshness.aging_count > 0 && (
              <span className="text-yellow-400">{freshness.aging_count} aging</span>
            )}
            {freshness.stale_count > 0 && (
              <span className="text-red-400">{freshness.stale_count} stale</span>
            )}
            {freshness.missing_count > 0 && (
              <span className="text-text-muted">{freshness.missing_count} missing</span>
            )}
          </div>
        </div>

        {/* B. Deterministic summary */}
        {freshness.deterministic_summary && (
          <p className="font-mono text-2xs text-text-muted italic leading-relaxed">
            {freshness.deterministic_summary}
          </p>
        )}

        {/* C. Evidence items table */}
        {freshness.evidence_items.length > 0 && (
          <div className="overflow-x-auto rounded-control border border-border">
            <table className="w-full min-w-[480px] text-left">
              <thead>
                <tr className="border-b border-border bg-bg-600">
                  <th className="px-3 py-1.5 font-mono text-2xs text-text-muted">Evidence Type</th>
                  <th className="px-3 py-1.5 font-mono text-2xs text-text-muted">Latest</th>
                  <th className="px-3 py-1.5 font-mono text-2xs text-text-muted">Days</th>
                  <th className="px-3 py-1.5 font-mono text-2xs text-text-muted">Count</th>
                  <th className="px-3 py-1.5 pr-4 font-mono text-2xs text-text-muted">Status</th>
                </tr>
              </thead>
              <tbody>
                {freshness.evidence_items.map((item: EvidenceFreshnessItem, idx: number) => {
                  const sc = freshnessStatusClasses(item.status);
                  return (
                    <tr key={idx} className="border-b border-border/50 last:border-0 hover:bg-bg-600/40">
                      <td className="px-3 py-1.5 font-mono text-2xs text-text-secondary">{item.label}</td>
                      <td className="px-3 py-1.5 font-mono text-2xs text-text-muted">
                        {item.latest_at ? fmtDate(item.latest_at) : "—"}
                      </td>
                      <td className={`px-3 py-1.5 font-mono text-2xs ${item.days_since_latest !== null ? freshnessSeverityColor(item.severity) : "text-text-muted"}`}>
                        {item.days_since_latest !== null ? item.days_since_latest : "—"}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-2xs text-text-muted">{item.count}</td>
                      <td className="px-3 py-1.5 pr-4">
                        <span className={`rounded px-1.5 py-0.5 font-mono text-2xs border ${sc.text} ${sc.bg} ${sc.border}`}>
                          {item.status}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* D. Suggested refresh order (collapsible) */}
        {freshness.suggested_refresh_order.length > 0 && (
          <div>
            <button
              onClick={() => setRefreshExpanded((v) => !v)}
              className="flex items-center gap-1.5 font-mono text-2xs text-text-secondary hover:text-text-primary transition-colors"
            >
              <span className="text-text-muted">{refreshExpanded ? "▾" : "▸"}</span>
              Refresh Priority
            </button>
            {refreshExpanded && (
              <ul className="mt-2 space-y-0.5 pl-3">
                {freshness.suggested_refresh_order.map((item: string, idx: number) => (
                  <li key={idx} className="font-mono text-2xs text-text-secondary">
                    <span className="text-text-muted mr-1">•</span>{item}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function DriftPanel({
  drift,
  onModeChange,
}: {
  drift: StrategyDriftResponse;
  onModeChange: (mode: string) => void;
}) {
  const statusClasses = driftStatusClasses(drift.drift_status);
  const modes = ["latest_stage_pair", "full_stage_path", "selected_runs"];

  if (drift.drift_status === "insufficient_evidence") {
    return (
      <div className="rounded-card border border-border bg-bg-900 p-4 space-y-3">
        <p className="caption">Research-to-Production Drift</p>
        <div className="rounded-control border border-border bg-bg-800 px-3 py-2">
          <p className="font-mono text-2xs text-text-muted">Need at least 2 runs to compute drift.</p>
        </div>
        {drift.suggested_checks.length > 0 && (
          <div>
            <p className="caption mb-1">Suggested Checks</p>
            <ul className="space-y-0.5">
              {drift.suggested_checks.map((c, i) => (
                <li key={i} className="font-mono text-2xs text-text-secondary">☐ {c}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-card border border-border bg-bg-900 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="caption">Research-to-Production Drift</p>
        <p className="font-mono text-2xs text-text-muted/60">{drift.generated_at.slice(0, 19).replace("T", " ")} UTC</p>
      </div>

      {/* A. Summary strip */}
      <div className="flex items-center flex-wrap gap-3">
        <span className="font-mono text-lg text-text-primary">
          {drift.drift_score !== null ? drift.drift_score.toFixed(1) : "—"}
        </span>
        <span className={`rounded border px-2 py-0.5 font-mono text-2xs ${statusClasses}`}>{drift.drift_status}</span>
        <div className="flex items-center gap-1 ml-auto">
          {modes.map((m) => (
            <button
              key={m}
              onClick={() => onModeChange(m)}
              className={`rounded border px-2 py-0.5 font-mono text-2xs transition-colors ${
                drift.mode === m
                  ? "border-accent-300/50 bg-accent-300/10 text-accent-300"
                  : "border-border bg-bg-800 text-text-muted hover:text-text-secondary"
              }`}
            >
              {m.replace(/_/g, " ")}
            </button>
          ))}
        </div>
      </div>

      {/* Deterministic summary */}
      <p className="font-mono text-2xs text-text-secondary">{drift.deterministic_summary}</p>

      {/* B. Run pair header */}
      {(drift.baseline_run || drift.comparison_run) && (
        <div className="rounded-control border border-border bg-bg-800 px-3 py-2 space-y-1">
          {drift.baseline_run && (
            <p className="font-mono text-2xs text-text-muted">
              <span className="text-text-secondary">Baseline:</span> {drift.baseline_run.run_type} — {drift.baseline_run.run_name}{" "}
              <span className="text-text-muted/60">({drift.baseline_run.created_at.slice(0, 10)})</span>
            </p>
          )}
          {drift.comparison_run && (
            <p className="font-mono text-2xs text-text-muted">
              <span className="text-text-secondary">Comparison:</span> {drift.comparison_run.run_type} — {drift.comparison_run.run_name}{" "}
              <span className="text-text-muted/60">({drift.comparison_run.created_at.slice(0, 10)})</span>
            </p>
          )}
        </div>
      )}

      {/* C. Highlighted drifts */}
      {drift.highlighted_drifts.length > 0 && (
        <div className="space-y-0.5">
          {drift.highlighted_drifts.map((h, i) => (
            <div key={i} className="flex items-start gap-1.5 rounded border border-amber-700/30 bg-amber-900/10 px-2 py-1">
              <span className="font-mono text-2xs text-amber-400">!</span>
              <span className="font-mono text-2xs text-amber-300/80">{h}</span>
            </div>
          ))}
        </div>
      )}

      {/* D. Metric drift table */}
      <MetricDriftTable items={drift.metric_drifts} />

      {/* E. Evidence drift table */}
      <EvidenceDriftTable items={drift.evidence_drifts} />

      {/* F. Assumption drift */}
      <AssumptionDriftList items={drift.assumption_drifts} />

      {/* G. Trust drift */}
      <TrustDriftList items={drift.trust_drifts} />

      {/* H. Suggested checks */}
      {drift.suggested_checks.length > 0 && (
        <div>
          <p className="caption mb-1.5">Suggested Checks</p>
          <ul className="space-y-0.5">
            {drift.suggested_checks.map((c, i) => (
              <li key={i} className="font-mono text-2xs text-text-secondary">☐ {c}</li>
            ))}
          </ul>
        </div>
      )}

      {/* I. Disclaimer */}
      <p className="font-mono text-2xs text-text-muted/40">
        Deterministic drift analysis. Not investment advice.
      </p>
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

// ---------------------------------------------------------------------------
// M49: Strategy Readiness Panel
// ---------------------------------------------------------------------------

function verdictColors(verdict: string): string {
  switch (verdict) {
    case "ready_for_paper_trading_consideration":
      return "text-teal-400 bg-teal-900/25 border-teal-700/40";
    case "ready_for_backtest_review":
      return "text-cyan-400 bg-cyan-900/25 border-cyan-700/40";
    case "requires_review_before_progression":
      return "text-yellow-400 bg-yellow-900/25 border-yellow-700/40";
    case "blocked":
      return "text-red-400 bg-red-900/25 border-red-700/40";
    default: // under_instrumented and fallback
      return "text-text-muted bg-bg-700 border-border";
  }
}

function dimStatusColor(status: string): string {
  switch (status) {
    case "ready": return "text-teal-400";
    case "watch": return "text-yellow-400";
    case "review": return "text-orange-400";
    case "blocked": return "text-red-400";
    default: return "text-text-muted";
  }
}

function readinessScoreColor(score: number | null): string {
  if (score === null) return "text-text-muted";
  if (score >= 85) return "text-teal-400";
  if (score >= 70) return "text-yellow-400";
  if (score >= 50) return "text-orange-400";
  return "text-red-400";
}

function DimensionCard({ dim }: { dim: StrategyReadinessDimension }) {
  const firstBlocker = dim.blockers[0] ?? null;
  const firstWarning = dim.warnings[0] ?? null;

  return (
    <div className="rounded-card border border-border bg-bg-700 px-3 py-2.5 space-y-1">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-text-primary truncate">{dim.title}</p>
        <span className={`font-mono text-xs font-semibold ${readinessScoreColor(dim.score)}`}>
          {dim.score !== null ? dim.score.toFixed(0) : "—"}
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className={`font-mono text-2xs font-semibold uppercase tracking-wide ${dimStatusColor(dim.status)}`}>
          {dim.status}
        </span>
      </div>
      {dim.evidence_summary && (
        <p className="font-mono text-2xs text-text-muted leading-relaxed">{dim.evidence_summary}</p>
      )}
      {firstBlocker && (
        <p className="font-mono text-2xs text-red-400 truncate">✗ {firstBlocker}</p>
      )}
      {!firstBlocker && firstWarning && (
        <p className="font-mono text-2xs text-yellow-400 truncate">⚠ {firstWarning}</p>
      )}
    </div>
  );
}

function ReadinessPanel({ readiness }: { readiness: StrategyReadinessResponse }) {
  const vColors = verdictColors(readiness.readiness_verdict);

  return (
    <div className="rounded-card border border-border bg-bg-800">
      <div className="border-b border-border px-4 py-2.5">
        <p className="caption">Strategy Readiness</p>
      </div>

      <div className="px-4 py-4 space-y-4">
        {/* A: Verdict band */}
        <div className={`rounded-card border px-4 py-3 ${vColors}`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="font-mono text-sm font-bold uppercase tracking-wide">
                {readiness.verdict_label}
              </span>
            </div>
            <span className={`mono-num text-2xl font-bold ${readinessScoreColor(readiness.readiness_score)}`}>
              {readiness.readiness_score !== null ? readiness.readiness_score.toFixed(0) : "—"}
            </span>
          </div>
          <p className="mt-1.5 text-xs italic opacity-80">{readiness.verdict_summary}</p>
          <p className="mt-0.5 font-mono text-2xs opacity-60">{fmtDate(readiness.generated_at)}</p>
        </div>

        {/* B: Progression path */}
        <div className="space-y-1.5">
          <p className="caption">Progression Path</p>
          <p className="font-mono text-xs text-text-secondary">
            Stage: <span className="text-text-primary">{readiness.progression_path.current_stage}</span>
            {" "}&rarr;{" "}
            Next: <span className="text-text-primary">{readiness.progression_path.next_recommended_stage}</span>
          </p>
          {readiness.progression_path.required_before_next_stage.length > 0 && (
            <ul className="space-y-0.5 mt-1">
              {readiness.progression_path.required_before_next_stage.map((req, i) => (
                <li key={i} className="font-mono text-2xs text-text-muted">☐ {req}</li>
              ))}
            </ul>
          )}
        </div>

        {/* C: Dimension grid */}
        {readiness.dimension_scorecards.length > 0 && (
          <div>
            <p className="caption mb-2">Dimension Scorecards</p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {readiness.dimension_scorecards.map((dim) => (
                <DimensionCard key={dim.dimension_key} dim={dim} />
              ))}
            </div>
          </div>
        )}

        {/* D: Blockers */}
        {readiness.blockers.length > 0 && (
          <div className="rounded-card border-l-2 border-l-red-500 border border-red-700/30 bg-red-900/10 px-3 py-2.5 space-y-1.5">
            <p className="font-mono text-xs font-semibold text-red-400">Blocking Issues</p>
            <ul className="space-y-0.5">
              {readiness.blockers.map((b, i) => (
                <li key={i} className="font-mono text-2xs text-red-300">✗ {b}</li>
              ))}
            </ul>
          </div>
        )}

        {/* E: Review items */}
        {readiness.review_items.length > 0 && (
          <div className="rounded-card border-l-2 border-l-yellow-500 border border-yellow-700/30 bg-yellow-900/10 px-3 py-2.5 space-y-1.5">
            <p className="font-mono text-xs font-semibold text-yellow-400">Review Items</p>
            <ul className="space-y-0.5">
              {readiness.review_items.map((r, i) => (
                <li key={i} className="font-mono text-2xs text-yellow-300">⚠ {r}</li>
              ))}
            </ul>
          </div>
        )}

        {/* F: Suggested next actions */}
        {readiness.suggested_next_actions.length > 0 && (
          <div className="space-y-1.5">
            <p className="caption">Suggested Next Actions</p>
            <ul className="space-y-0.5">
              {readiness.suggested_next_actions.map((action, i) => (
                <li key={i} className="font-mono text-2xs text-text-secondary">☐ {action}</li>
              ))}
            </ul>
          </div>
        )}

        {/* G: Disclaimer */}
        <p className="font-mono text-2xs text-text-muted italic">
          Deterministic readiness assessment. Not a trading recommendation.
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// M50: Shadow Production Monitor Panel
// ---------------------------------------------------------------------------

function shadowStatusStyles(status: string): { text: string; bg: string; border: string } {
  switch (status) {
    case "stable":
      return { text: "text-teal-400", bg: "bg-teal-900/20", border: "border-teal-700/30" };
    case "watch":
      return { text: "text-yellow-400", bg: "bg-yellow-900/20", border: "border-yellow-700/30" };
    case "review":
      return { text: "text-orange-400", bg: "bg-orange-900/20", border: "border-orange-700/30" };
    case "severe":
      return { text: "text-red-400", bg: "bg-red-900/20", border: "border-red-700/30" };
    default:
      return { text: "text-text-muted", bg: "bg-bg-700", border: "border-border" };
  }
}

function shadowSeverityColor(severity: string): string {
  switch (severity) {
    case "high": return "text-red-400";
    case "medium": return "text-yellow-400";
    case "low": return "text-text-secondary";
    default: return "text-text-muted";
  }
}

function shadowDirectionIcon(direction: string): string {
  switch (direction) {
    case "improved": return "▲";
    case "deteriorated": return "▼";
    case "changed": return "↔";
    case "unchanged": return "—";
    default: return "?";
  }
}

function ShadowMonitorPanel({ monitor }: { monitor: StrategyShadowMonitorResponse }) {
  const [checksExpanded, setChecksExpanded] = useState(false);
  const [metricsExpanded, setMetricsExpanded] = useState(false);
  const [evidenceExpanded, setEvidenceExpanded] = useState(false);
  const [assumptionsExpanded, setAssumptionsExpanded] = useState(false);

  const statusStyles = shadowStatusStyles(monitor.monitor_status);
  const nonTrivialMetrics = monitor.metric_comparisons.filter(
    (m: ShadowMetricComparison) => m.severity !== "info" && m.severity !== "low",
  );

  return (
    <div className="rounded-card border border-border bg-bg-card p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="font-mono text-xs font-semibold text-text-primary uppercase tracking-wide">
          Shadow Production Monitor
        </h3>
        <span className={`font-mono text-xs font-semibold px-2 py-0.5 rounded border ${statusStyles.text} ${statusStyles.bg} ${statusStyles.border}`}>
          {monitor.monitor_status.replace(/_/g, " ")}
        </span>
      </div>

      {/* A: Status strip */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <div>
          <p className="caption">Stability Score</p>
          <p className="mono-num text-sm font-bold text-text-primary">
            {monitor.shadow_stability_score !== null ? monitor.shadow_stability_score.toFixed(0) : "—"}
          </p>
        </div>
        {monitor.baseline_run && (
          <div>
            <p className="caption">Baseline</p>
            <p className="font-mono text-2xs text-text-secondary">
              [{monitor.baseline_run.run_type}] {monitor.baseline_run.run_name}
            </p>
          </div>
        )}
        {monitor.shadow_run && (
          <div>
            <p className="caption">Shadow</p>
            <p className="font-mono text-2xs text-text-secondary">
              [{monitor.shadow_run.run_type}] {monitor.shadow_run.run_name}
            </p>
          </div>
        )}
        <div className="ml-auto">
          <p className="font-mono text-2xs text-text-muted">{fmtDate(monitor.generated_at)}</p>
        </div>
      </div>

      {/* B: No shadow runs */}
      {monitor.monitor_status === "no_shadow_runs" && (
        <div className="rounded border border-border bg-bg-700 px-4 py-4 space-y-1">
          <p className="font-mono text-xs font-semibold text-text-secondary">No paper or live-like run logged.</p>
          <p className="font-mono text-2xs text-text-muted">
            Log a paper or live-like run through the SDK to enable shadow monitoring.
          </p>
          <p className="mt-2 font-mono text-2xs text-text-muted bg-bg-900 rounded px-2 py-1 inline-block">
            --run-type paper
          </p>
        </div>
      )}

      {/* C: Insufficient baseline */}
      {monitor.monitor_status === "insufficient_baseline" && (
        <div className="rounded border border-border bg-bg-700 px-4 py-3">
          <p className="font-mono text-xs text-text-secondary">No baseline research/backtest run found.</p>
        </div>
      )}

      {/* D: Deterministic summary */}
      {monitor.deterministic_summary && (
        <p className="font-mono text-2xs text-text-muted italic">{monitor.deterministic_summary}</p>
      )}

      {/* E: Production-like checks */}
      {monitor.production_checks.length > 0 && (
        <div>
          <button
            className="flex items-center gap-1.5 font-mono text-2xs text-text-secondary hover:text-text-primary"
            onClick={() => setChecksExpanded((v) => !v)}
          >
            <span>{checksExpanded ? "▾" : "▸"}</span>
            <span>Production Checks ({monitor.production_checks.length})</span>
          </button>
          {checksExpanded && (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full font-mono text-2xs border-collapse">
                <thead>
                  <tr className="border-b border-border text-text-muted">
                    <th className="text-left py-1 pr-3">Check</th>
                    <th className="text-left py-1 pr-3">Passed</th>
                    <th className="text-left py-1 pr-3">Severity</th>
                    <th className="text-left py-1">Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {monitor.production_checks.map((c: ShadowProductionCheck) => (
                    <tr key={c.check_key} className="border-b border-border/40">
                      <td className="py-1 pr-3 text-text-primary">{c.title}</td>
                      <td className="py-1 pr-3">
                        <span className={`px-1.5 py-0.5 rounded text-2xs font-semibold ${c.passed ? "bg-teal-900/30 text-teal-400" : "bg-red-900/30 text-red-400"}`}>
                          {c.passed ? "pass" : "fail"}
                        </span>
                      </td>
                      <td className={`py-1 pr-3 ${shadowSeverityColor(c.severity)}`}>{c.severity}</td>
                      <td className="py-1 text-text-muted">{c.evidence}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* F: Metric comparisons (non-trivial severity only) */}
      {nonTrivialMetrics.length > 0 && (
        <div>
          <button
            className="flex items-center gap-1.5 font-mono text-2xs text-text-secondary hover:text-text-primary"
            onClick={() => setMetricsExpanded((v) => !v)}
          >
            <span>{metricsExpanded ? "▾" : "▸"}</span>
            <span>Metric Comparisons ({nonTrivialMetrics.length})</span>
          </button>
          {metricsExpanded && (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full font-mono text-2xs border-collapse">
                <thead>
                  <tr className="border-b border-border text-text-muted">
                    <th className="text-left py-1 pr-3">Metric</th>
                    <th className="text-right py-1 pr-3">Baseline</th>
                    <th className="text-right py-1 pr-3">Shadow</th>
                    <th className="text-right py-1 pr-3">Delta</th>
                    <th className="text-center py-1 pr-3">Dir</th>
                    <th className="text-left py-1">Severity</th>
                  </tr>
                </thead>
                <tbody>
                  {nonTrivialMetrics.map((m: ShadowMetricComparison) => (
                    <tr key={m.metric_key} className="border-b border-border/40">
                      <td className="py-1 pr-3 text-text-primary">{m.metric_key}</td>
                      <td className="py-1 pr-3 text-right text-text-secondary mono-num">
                        {m.baseline_value !== null ? m.baseline_value.toFixed(4) : "—"}
                      </td>
                      <td className="py-1 pr-3 text-right text-text-secondary mono-num">
                        {m.comparison_value !== null ? m.comparison_value.toFixed(4) : "—"}
                      </td>
                      <td className="py-1 pr-3 text-right mono-num text-text-muted">
                        {m.absolute_delta !== null ? m.absolute_delta.toFixed(4) : "—"}
                      </td>
                      <td className={`py-1 pr-3 text-center font-bold ${shadowSeverityColor(m.severity)}`}>
                        {shadowDirectionIcon(m.direction)}
                      </td>
                      <td className={`py-1 ${shadowSeverityColor(m.severity)}`}>{m.severity}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* G: Evidence comparisons */}
      {monitor.evidence_comparisons.length > 0 && (
        <div>
          <button
            className="flex items-center gap-1.5 font-mono text-2xs text-text-secondary hover:text-text-primary"
            onClick={() => setEvidenceExpanded((v) => !v)}
          >
            <span>{evidenceExpanded ? "▾" : "▸"}</span>
            <span>Evidence Comparisons ({monitor.evidence_comparisons.length})</span>
          </button>
          {evidenceExpanded && (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full font-mono text-2xs border-collapse">
                <thead>
                  <tr className="border-b border-border text-text-muted">
                    <th className="text-left py-1 pr-3">Evidence Type</th>
                    <th className="text-right py-1 pr-3">Baseline</th>
                    <th className="text-right py-1 pr-3">Shadow</th>
                    <th className="text-left py-1 pr-3">Severity</th>
                    <th className="text-left py-1">Explanation</th>
                  </tr>
                </thead>
                <tbody>
                  {monitor.evidence_comparisons.map((e, i) => (
                    <tr key={i} className="border-b border-border/40">
                      <td className="py-1 pr-3 text-text-primary">{e.evidence_type}</td>
                      <td className="py-1 pr-3 text-right mono-num text-text-secondary">
                        {e.baseline_value !== null ? e.baseline_value.toFixed(2) : "—"}
                      </td>
                      <td className="py-1 pr-3 text-right mono-num text-text-secondary">
                        {e.comparison_value !== null ? e.comparison_value.toFixed(2) : "—"}
                      </td>
                      <td className={`py-1 pr-3 ${shadowSeverityColor(e.severity)}`}>{e.severity}</td>
                      <td className="py-1 text-text-muted">{e.explanation}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* H: Assumption changes */}
      {monitor.assumption_changes.length > 0 && (
        <div>
          <button
            className="flex items-center gap-1.5 font-mono text-2xs text-text-secondary hover:text-text-primary"
            onClick={() => setAssumptionsExpanded((v) => !v)}
          >
            <span>{assumptionsExpanded ? "▾" : "▸"}</span>
            <span>Assumption Changes ({monitor.assumption_changes.length})</span>
          </button>
          {assumptionsExpanded && (
            <div className="mt-2 space-y-2">
              {monitor.assumption_changes.map((a, i) => (
                <div key={i} className="rounded border border-border/40 bg-bg-700 px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-2xs text-text-primary">{a.key_path}</span>
                    <span className={`font-mono text-2xs ${shadowSeverityColor(a.impact_level)}`}>[{a.impact_level}]</span>
                    <span className="font-mono text-2xs text-text-muted">{a.change_type}</span>
                  </div>
                  {a.impact_reason && (
                    <p className="mt-0.5 font-mono text-2xs text-text-muted italic">{a.impact_reason}</p>
                  )}
                  {a.suggested_check && (
                    <p className="mt-0.5 font-mono text-2xs text-text-muted">Check: {a.suggested_check}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* I: Blockers and suggested actions */}
      {monitor.blockers.length > 0 && (
        <div>
          <p className="font-mono text-2xs font-semibold text-red-400 mb-1">Blockers</p>
          <ul className="space-y-0.5">
            {monitor.blockers.map((b, i) => (
              <li key={i} className="font-mono text-2xs text-text-secondary flex gap-1.5">
                <span className="text-red-400">•</span>{b}
              </li>
            ))}
          </ul>
        </div>
      )}
      {monitor.suggested_actions.length > 0 && (
        <div>
          <p className="font-mono text-2xs font-semibold text-text-secondary mb-1">Suggested Actions</p>
          <ul className="space-y-0.5">
            {monitor.suggested_actions.map((a, i) => (
              <li key={i} className="font-mono text-2xs text-text-muted flex gap-1.5">
                <span className="text-text-muted">→</span>{a}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* J: Disclaimer */}
      <p className="font-mono text-2xs text-text-muted italic">
        Deterministic shadow analysis. Not a trading recommendation.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// M51: Promotion Gates Panel
// ---------------------------------------------------------------------------

const PROMOTION_TARGETS: { label: string; value: string }[] = [
  { label: "Backtest Review", value: "backtest_review" },
  { label: "Paper Candidate", value: "paper_candidate" },
  { label: "Shadow Production", value: "shadow_production" },
  { label: "Production Candidate", value: "production_candidate" },
];

function verdictStyles(verdict: string): { text: string; bg: string; border: string } {
  switch (verdict) {
    case "pass":
      return { text: "text-teal-400", bg: "bg-teal-900/20", border: "border-teal-700/30" };
    case "conditional_pass":
      return { text: "text-cyan-400", bg: "bg-cyan-900/20", border: "border-cyan-700/30" };
    case "requires_review":
      return { text: "text-yellow-400", bg: "bg-yellow-900/20", border: "border-yellow-700/30" };
    case "blocked":
      return { text: "text-red-400", bg: "bg-red-900/20", border: "border-red-700/30" };
    default: // insufficient_evidence
      return { text: "text-text-muted", bg: "bg-bg-700", border: "border-border" };
  }
}

function gateStatusColor(status: string): string {
  switch (status) {
    case "pass": return "text-teal-400";
    case "watch": return "text-yellow-400";
    case "review": return "text-orange-400";
    case "fail": return "text-red-400";
    default: return "text-text-muted";
  }
}

function GateCheckIcon({ check }: { check: PromotionGateCheck }) {
  if (check.status === "missing" || check.status === "unknown") {
    return <span className="text-text-muted font-mono text-xs">○</span>;
  }
  if (check.passed) {
    return <span className="text-teal-400 font-mono text-xs font-bold">✓</span>;
  }
  return <span className="text-red-400 font-mono text-xs font-bold">✗</span>;
}

function PromotionGatesPanel({
  gates,
  onTargetChange,
}: {
  gates: StrategyPromotionGateResponse;
  onTargetChange: (t: string) => void;
}) {
  const vStyles = verdictStyles(gates.promotion_verdict);
  const requiredChecks = gates.gate_checks.filter((c) => c.required);
  const recommendedChecks = gates.gate_checks.filter((c) => !c.required);

  return (
    <div className="rounded-card border border-border bg-bg-card p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="font-mono text-xs font-semibold text-text-primary uppercase tracking-wide">
          Promotion Gates
        </h3>
        <span className="font-mono text-2xs text-text-muted">{fmtDate(gates.generated_at)}</span>
      </div>

      {/* A: Target stage selector */}
      <div className="flex flex-wrap gap-2">
        {PROMOTION_TARGETS.map((t) => (
          <button
            key={t.value}
            onClick={() => onTargetChange(t.value)}
            className={`font-mono text-2xs px-2.5 py-1 rounded border transition-colors ${
              gates.target_stage === t.value
                ? "border-text-secondary text-text-primary bg-bg-700"
                : "border-border text-text-muted hover:text-text-secondary hover:border-text-muted"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* B: Verdict + score strip */}
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={`font-mono text-xs font-semibold px-2 py-0.5 rounded border ${vStyles.text} ${vStyles.bg} ${vStyles.border}`}
        >
          {gates.promotion_verdict.replace(/_/g, " ")}
        </span>
        {gates.gate_score !== null && (
          <span className="mono-num text-sm font-bold text-text-primary">
            {gates.gate_score.toFixed(0)}
            <span className="font-mono text-2xs text-text-muted font-normal"> / 100</span>
          </span>
        )}
        <span className="font-mono text-2xs text-text-secondary">
          {gates.current_stage.replace(/_/g, " ")}
          <span className="mx-1.5 text-text-muted">→</span>
          {gates.target_stage.replace(/_/g, " ")}
        </span>
        <div className="ml-auto flex gap-3 text-2xs font-mono">
          <span className="text-teal-400">{gates.required_pass_count}P</span>
          <span className="text-red-400">{gates.required_fail_count}F</span>
          {gates.blocker_count > 0 && (
            <span className="text-red-400 font-semibold">{gates.blocker_count} blocker{gates.blocker_count !== 1 ? "s" : ""}</span>
          )}
        </div>
      </div>

      {/* C: Deterministic summary */}
      {gates.deterministic_summary && (
        <p className="font-mono text-2xs text-text-muted italic">{gates.deterministic_summary}</p>
      )}

      {/* D: Gate checks table */}
      {requiredChecks.length > 0 && (
        <div className="space-y-1">
          <p className="font-mono text-2xs font-semibold text-text-secondary uppercase tracking-wide">Required Checks</p>
          <div className="rounded border border-border overflow-x-auto">
            <table className="w-full text-2xs font-mono">
              <thead>
                <tr className="border-b border-border bg-bg-700">
                  <th className="px-2 py-1 text-left text-text-muted font-normal w-6"></th>
                  <th className="px-2 py-1 text-left text-text-muted font-normal">Check</th>
                  <th className="px-2 py-1 text-left text-text-muted font-normal">Category</th>
                  <th className="px-2 py-1 text-left text-text-muted font-normal">Status</th>
                  <th className="px-2 py-1 text-left text-text-muted font-normal">Observed</th>
                  <th className="px-2 py-1 text-left text-text-muted font-normal">Required</th>
                  <th className="px-2 py-1 text-left text-text-muted font-normal">Action</th>
                </tr>
              </thead>
              <tbody>
                {requiredChecks.map((c) => (
                  <tr key={c.gate_key} className="border-b border-border last:border-0 hover:bg-bg-700/50">
                    <td className="px-2 py-1 text-center"><GateCheckIcon check={c} /></td>
                    <td className="px-2 py-1 text-text-primary">{c.title}</td>
                    <td className="px-2 py-1 text-text-muted">{c.category}</td>
                    <td className={`px-2 py-1 font-semibold ${gateStatusColor(c.status)}`}>
                      {c.status}
                    </td>
                    <td className="px-2 py-1 text-text-secondary">{c.observed_value ?? "—"}</td>
                    <td className="px-2 py-1 text-text-muted">{c.required_value ?? "—"}</td>
                    <td className="px-2 py-1 text-text-muted max-w-xs truncate" title={c.suggested_action ?? ""}>
                      {c.suggested_action ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {recommendedChecks.length > 0 && (
        <div className="space-y-1">
          <p className="font-mono text-2xs font-semibold text-text-secondary uppercase tracking-wide opacity-70">Recommended Checks</p>
          <div className="rounded border border-border overflow-x-auto opacity-80">
            <table className="w-full text-2xs font-mono">
              <thead>
                <tr className="border-b border-border bg-bg-700">
                  <th className="px-2 py-1 text-left text-text-muted font-normal w-6"></th>
                  <th className="px-2 py-1 text-left text-text-muted font-normal">Check</th>
                  <th className="px-2 py-1 text-left text-text-muted font-normal">Category</th>
                  <th className="px-2 py-1 text-left text-text-muted font-normal">Status</th>
                  <th className="px-2 py-1 text-left text-text-muted font-normal">Observed</th>
                  <th className="px-2 py-1 text-left text-text-muted font-normal">Required</th>
                  <th className="px-2 py-1 text-left text-text-muted font-normal">Action</th>
                </tr>
              </thead>
              <tbody>
                {recommendedChecks.map((c) => (
                  <tr key={c.gate_key} className="border-b border-border last:border-0 hover:bg-bg-700/50">
                    <td className="px-2 py-1 text-center"><GateCheckIcon check={c} /></td>
                    <td className="px-2 py-1 text-text-primary">{c.title}</td>
                    <td className="px-2 py-1 text-text-muted">{c.category}</td>
                    <td className={`px-2 py-1 font-semibold ${gateStatusColor(c.status)}`}>
                      {c.status}
                    </td>
                    <td className="px-2 py-1 text-text-secondary">{c.observed_value ?? "—"}</td>
                    <td className="px-2 py-1 text-text-muted">{c.required_value ?? "—"}</td>
                    <td className="px-2 py-1 text-text-muted max-w-xs truncate" title={c.suggested_action ?? ""}>
                      {c.suggested_action ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* E: Blockers */}
      {gates.blockers.length > 0 && (
        <div className="rounded border border-red-700/30 bg-red-900/10 px-3 py-2 space-y-1">
          <p className="font-mono text-2xs font-semibold text-red-400 uppercase tracking-wide">Blockers</p>
          <ul className="space-y-0.5">
            {gates.blockers.map((b, i) => (
              <li key={i} className="font-mono text-2xs text-red-400">• {b}</li>
            ))}
          </ul>
        </div>
      )}

      {/* F: Suggested actions */}
      {gates.suggested_actions.length > 0 && (
        <div className="space-y-1">
          <p className="font-mono text-2xs font-semibold text-text-secondary uppercase tracking-wide">Suggested Actions</p>
          <ul className="space-y-0.5">
            {gates.suggested_actions.slice(0, 5).map((a, i) => (
              <li key={i} className="font-mono text-2xs text-text-muted">• {a}</li>
            ))}
          </ul>
        </div>
      )}

      {/* G: Note */}
      {gates.note && (
        <p className="font-mono text-2xs text-text-muted italic">{gates.note}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// M52: Evidence Dependency Graph Panel
// ---------------------------------------------------------------------------

const NODE_STATUS_COLOR: Record<string, string> = {
  healthy: "text-teal-400",
  watch: "text-yellow-400",
  review: "text-orange-400",
  weak: "text-red-400",
  missing: "text-text-muted",
  computed: "text-cyan-400",
  unknown: "text-text-muted",
};

const SEVERITY_COLOR: Record<string, string> = {
  critical: "text-red-500",
  high: "text-red-400",
  medium: "text-yellow-400",
  low: "text-text-secondary",
  info: "text-text-muted",
};

const GRAPH_STATUS_COLOR: Record<string, string> = {
  complete: "bg-teal-900/40 text-teal-400 border-teal-700/50",
  partial: "bg-yellow-900/40 text-yellow-400 border-yellow-700/50",
  review: "bg-orange-900/40 text-orange-400 border-orange-700/50",
  sparse: "bg-surface-2 text-text-muted border-border",
};

const NODE_TYPE_COLUMN: Record<string, string> = {
  strategy: "Strategy",
  strategy_version: "Strategy",
  config_snapshot: "Snapshots",
  universe_snapshot: "Snapshots",
  signal_snapshot: "Snapshots",
  dataset: "Snapshots",
  dataset_snap: "Snapshots",
  strategy_run: "Runs & Audits",
  backtest_audit: "Runs & Audits",
  reliability: "Analysis",
  readiness: "Analysis",
  shadow_monitor: "Analysis",
  promotion: "Analysis",
  report: "Signals",
  alert: "Signals",
  timeline: "Signals",
};

const COLUMN_ORDER = ["Strategy", "Snapshots", "Runs & Audits", "Analysis", "Signals"];

function nodeColumn(nodeType: string): string {
  return NODE_TYPE_COLUMN[nodeType] ?? "Signals";
}

function EvidenceGraphPanel({
  graph,
  strategyId: _strategyId,
  onFocusChange,
}: {
  graph: StrategyEvidenceGraphResponse;
  strategyId: string | undefined;
  onFocusChange: (nid: string, ntype: string) => void;
}) {
  const [tableOpen, setTableOpen] = useState(false);
  const { summary, nodes, edges, blast_radius } = graph;

  const graphStatusClass =
    GRAPH_STATUS_COLOR[summary.graph_status] ?? GRAPH_STATUS_COLOR.sparse;

  // Group nodes by column
  const columns: Record<string, EvidenceGraphNode[]> = {};
  for (const col of COLUMN_ORDER) columns[col] = [];
  for (const node of nodes) {
    const col = nodeColumn(node.node_type);
    if (!columns[col]) columns[col] = [];
    columns[col].push(node);
  }

  function NodeChip({ node }: { node: EvidenceGraphNode }) {
    const statusClass = NODE_STATUS_COLOR[node.status] ?? "text-text-muted";
    const severityClass = SEVERITY_COLOR[node.severity] ?? "text-text-muted";
    return (
      <button
        onClick={() => onFocusChange(node.node_id, node.node_type)}
        className="flex flex-col gap-0.5 rounded border border-border bg-surface-2 px-2 py-1.5 text-left hover:border-border-active hover:bg-surface-3 transition-colors w-full"
      >
        <span className={`font-mono text-2xs font-medium ${statusClass} truncate`}>
          {node.label}
        </span>
        <span className="font-mono text-2xs text-text-muted truncate">{node.node_type}</span>
        {node.score !== null && (
          <span className={`font-mono text-2xs ${severityClass}`}>
            score: {typeof node.score === "number" ? node.score.toFixed(2) : node.score}
          </span>
        )}
        <span className={`font-mono text-3xs ${statusClass}`}>{node.status}</span>
      </button>
    );
  }

  function BlastRadiusPanel({ br }: { br: EvidenceBlastRadius }) {
    const focusShort = br.focus_node_id.split(":").slice(-1)[0];
    const sevClass = SEVERITY_COLOR[br.blast_radius_severity] ?? "text-text-muted";
    return (
      <div className="rounded-card border border-orange-700/40 bg-orange-900/10 p-3 space-y-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-semibold text-orange-400">
            Blast Radius: {focusShort}
          </span>
          <span className={`font-mono text-2xs font-semibold ${sevClass}`}>
            [{br.blast_radius_severity}]
          </span>
        </div>
        <div className="flex flex-wrap gap-3 font-mono text-2xs text-text-secondary">
          <span>upstream: <span className="text-text-primary">{br.upstream_count}</span></span>
          <span>downstream: <span className="text-text-primary">{br.downstream_count}</span></span>
          <span>runs: <span className="text-text-primary">{br.affected_run_count}</span></span>
          <span>audits: <span className="text-text-primary">{br.affected_audit_count}</span></span>
          <span>reports: <span className="text-text-primary">{br.affected_report_count}</span></span>
          <span>alerts: <span className="text-text-primary">{br.affected_alert_count}</span></span>
        </div>
        <div className="flex flex-wrap gap-3 font-mono text-2xs">
          {br.affected_readiness && (
            <span className="text-orange-400">readiness affected</span>
          )}
          {br.affected_shadow_monitor && (
            <span className="text-orange-400">shadow monitor affected</span>
          )}
          {br.affected_promotion_gates && (
            <span className="text-orange-400">promotion gates affected</span>
          )}
        </div>
        {br.affected_nodes.length > 0 && (
          <div className="space-y-1">
            <p className="font-mono text-2xs text-text-muted">Affected nodes (max 10):</p>
            <div className="flex flex-col gap-0.5">
              {br.affected_nodes.slice(0, 10).map((n) => (
                <span key={n.node_id} className="font-mono text-2xs text-text-secondary">
                  <span className={NODE_STATUS_COLOR[n.status] ?? "text-text-muted"}>
                    [{n.node_type}]
                  </span>{" "}
                  {n.label}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-card border border-border bg-surface-1 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-mono text-xs font-semibold text-text-primary">
          Evidence Dependency Graph
        </h3>
        <span
          className={`rounded border px-1.5 py-0.5 font-mono text-2xs font-semibold ${graphStatusClass}`}
        >
          {summary.graph_status}
        </span>
      </div>

      {/* A. Summary strip */}
      <div className="flex flex-wrap gap-3 font-mono text-2xs text-text-secondary">
        <span>
          nodes: <span className="text-text-primary">{summary.node_count}</span>
        </span>
        <span>
          edges: <span className="text-text-primary">{summary.edge_count}</span>
        </span>
        <span>
          weak:{" "}
          <span className={summary.weak_node_count > 0 ? "text-red-400" : "text-text-primary"}>
            {summary.weak_node_count}
          </span>
        </span>
        <span>
          connected runs: <span className="text-text-primary">{summary.connected_run_count}</span>
        </span>
        <span className="text-text-muted">
          {new Date(summary.generated_at).toLocaleString()}
        </span>
      </div>

      {/* B. Deterministic summary */}
      <p className="font-mono text-2xs text-text-muted italic">{summary.deterministic_summary}</p>

      {/* C. Grouped node columns */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {COLUMN_ORDER.map((col) => {
          const colNodes = columns[col] ?? [];
          return (
            <div key={col} className="space-y-1">
              <p className="font-mono text-2xs font-semibold text-text-muted uppercase tracking-wide">
                {col}
              </p>
              {colNodes.length === 0 ? (
                <p className="font-mono text-2xs text-text-muted italic">—</p>
              ) : (
                colNodes.map((node) => <NodeChip key={node.node_id} node={node} />)
              )}
            </div>
          );
        })}
      </div>

      {/* D. Blast radius panel */}
      {blast_radius && <BlastRadiusPanel br={blast_radius} />}

      {/* E. Node table (collapsible) */}
      <div>
        <button
          onClick={() => setTableOpen((v) => !v)}
          className="font-mono text-2xs text-text-muted hover:text-text-secondary"
        >
          {tableOpen ? "▾ Hide node table" : "▸ Show all nodes"} ({nodes.length})
        </button>
        {tableOpen && (
          <div className="mt-2 overflow-x-auto">
            <table className="w-full font-mono text-2xs">
              <thead>
                <tr className="border-b border-border text-text-muted">
                  <th className="pb-1 pr-3 text-left font-semibold">type</th>
                  <th className="pb-1 pr-3 text-left font-semibold">label</th>
                  <th className="pb-1 pr-3 text-left font-semibold">status</th>
                  <th className="pb-1 pr-3 text-left font-semibold">score</th>
                  <th className="pb-1 text-left font-semibold">created_at</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((node) => (
                  <tr key={node.node_id} className="border-b border-border/50">
                    <td className="py-0.5 pr-3 text-text-muted">{node.node_type}</td>
                    <td className="py-0.5 pr-3">
                      <button
                        onClick={() => onFocusChange(node.node_id, node.node_type)}
                        className={`hover:underline ${NODE_STATUS_COLOR[node.status] ?? "text-text-secondary"}`}
                      >
                        {node.label}
                      </button>
                    </td>
                    <td className={`py-0.5 pr-3 ${NODE_STATUS_COLOR[node.status] ?? "text-text-muted"}`}>
                      {node.status}
                    </td>
                    <td className="py-0.5 pr-3 text-text-secondary">
                      {node.score !== null ? node.score.toFixed(2) : "—"}
                    </td>
                    <td className="py-0.5 text-text-muted">
                      {node.created_at ? new Date(node.created_at).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* F. Suggested checks */}
      {summary.suggested_checks.length > 0 && (
        <div className="space-y-1">
          <p className="font-mono text-2xs font-semibold text-text-muted">Suggested checks:</p>
          <ul className="space-y-0.5">
            {summary.suggested_checks.map((check, i) => (
              <li key={i} className="font-mono text-2xs text-text-secondary">
                • {check}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Edge count note */}
      {edges.length > 0 && (
        <p className="font-mono text-2xs text-text-muted">
          {edges.length} edge{edges.length !== 1 ? "s" : ""} in dependency graph
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// M53: Regression Test Panel
// ---------------------------------------------------------------------------

function statusColor(status: string): string {
  switch (status as RegressionTestStatus) {
    case "passed": return "text-teal-400";
    case "warning": return "text-yellow-400";
    case "failed": return "text-red-400";
    case "skipped": return "text-text-muted";
    default: return "text-text-muted";
  }
}

function statusIcon(status: string): string {
  switch (status as RegressionTestStatus | RegressionTestOverallStatus) {
    case "passed": return "✓";
    case "failed": return "✗";
    case "warning": return "⚠";
    case "skipped": return "○";
    case "insufficient_evidence": return "—";
    default: return "—";
  }
}

function overallBgClass(status: string): string {
  switch (status as RegressionTestOverallStatus) {
    case "passed": return "bg-teal-900/20 border-teal-700/30";
    case "warning": return "bg-yellow-900/20 border-yellow-700/30";
    case "failed": return "bg-red-900/20 border-red-700/30";
    default: return "bg-bg-700 border-border";
  }
}

interface RegressionTestPanelProps {
  tests: StrategyRegressionTest[];
  latestRun: StrategyRegressionTestRun | null;
  loading: boolean;
  strategyId: string;
  onSetupDefaults: () => void;
  onRunTests: (mode: string) => void;
}

function RegressionTestPanel({
  tests,
  latestRun,
  loading,
  onSetupDefaults,
  onRunTests,
}: RegressionTestPanelProps) {
  const [mode, setMode] = useState<string>("latest_vs_previous");
  const [defsOpen, setDefsOpen] = useState(false);

  const modes = [
    { key: "latest_vs_previous", label: "Latest vs Previous" },
    { key: "backtest_vs_shadow", label: "Backtest vs Shadow" },
    { key: "selected", label: "Selected" },
  ];

  const nonPassResults =
    latestRun?.results.filter((r) => r.status !== "passed") ?? [];
  const passedResults =
    latestRun?.results.filter((r) => r.status === "passed") ?? [];

  return (
    <div className="rounded border border-border bg-bg-800 p-4">
      <h3 className="mb-3 font-mono text-xs font-semibold text-text-primary">
        Regression Test Suite
      </h3>

      {tests.length === 0 ? (
        <div className="flex items-center gap-3">
          <p className="font-mono text-2xs text-text-muted">No regression tests defined.</p>
          <button
            onClick={onSetupDefaults}
            disabled={loading}
            className="rounded bg-accent px-2 py-1 font-mono text-2xs text-white hover:bg-accent/80 disabled:opacity-50"
          >
            {loading ? "Creating…" : "Create Default Tests"}
          </button>
        </div>
      ) : (
        <>
          {/* Summary row */}
          <p className="mb-3 font-mono text-2xs text-text-muted">
            {tests.length} test{tests.length !== 1 ? "s" : ""} (
            {tests.filter((t) => t.is_required).length} required,{" "}
            {tests.filter((t) => t.is_enabled).length} enabled)
          </p>

          {/* Mode selector + run button */}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {modes.map((m) => (
              <button
                key={m.key}
                onClick={() => setMode(m.key)}
                className={`rounded border px-2 py-0.5 font-mono text-2xs transition-colors ${
                  mode === m.key
                    ? "border-accent bg-accent/20 text-accent"
                    : "border-border text-text-muted hover:border-accent/50 hover:text-text-secondary"
                }`}
              >
                {m.label}
              </button>
            ))}
            <button
              onClick={() => onRunTests(mode)}
              disabled={loading}
              className="rounded bg-accent px-3 py-0.5 font-mono text-2xs text-white hover:bg-accent/80 disabled:opacity-50"
            >
              {loading ? "Running tests…" : "Run Tests"}
            </button>
          </div>

          {/* Latest run results */}
          {loading && (
            <p className="font-mono text-2xs text-text-muted">Running tests…</p>
          )}

          {latestRun && !loading && (
            <div className={`mb-3 rounded border p-3 ${overallBgClass(latestRun.overall_status)}`}>
              {/* Overall status header */}
              <div className="mb-2 flex flex-wrap items-center gap-3">
                <span className={`font-mono text-xs font-semibold ${statusColor(latestRun.overall_status)}`}>
                  {statusIcon(latestRun.overall_status)}{" "}
                  {latestRun.overall_status.replace(/_/g, " ").toUpperCase()}
                </span>
                <span className="font-mono text-2xs text-teal-400">
                  {latestRun.passed_count} passed
                </span>
                <span className="font-mono text-2xs text-red-400">
                  {latestRun.failed_count} failed
                </span>
                <span className="font-mono text-2xs text-yellow-400">
                  {latestRun.warning_count} warning
                </span>
                <span className="font-mono text-2xs text-text-muted">
                  {latestRun.skipped_count} skipped
                </span>
                {latestRun.required_failed_count > 0 && (
                  <span className="font-mono text-2xs font-semibold text-red-400">
                    {latestRun.required_failed_count} required failed
                  </span>
                )}
              </div>

              {latestRun.overall_status === "insufficient_evidence" && (
                <p className="mb-2 font-mono text-2xs text-text-muted">
                  Need at least 2 runs to compare.
                </p>
              )}

              {latestRun.deterministic_summary && (
                <p className="mb-3 font-mono text-2xs italic text-text-muted">
                  {latestRun.deterministic_summary}
                </p>
              )}

              {/* Results table — non-pass first, then passed */}
              {latestRun.results.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full font-mono text-2xs">
                    <thead>
                      <tr className="border-b border-border/30 text-left text-text-muted">
                        <th className="pb-1 pr-3">Test</th>
                        <th className="pb-1 pr-3">Req</th>
                        <th className="pb-1 pr-3">Status</th>
                        <th className="pb-1 pr-3">Observed</th>
                        <th className="pb-1 pr-3">Expected</th>
                        <th className="pb-1">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...nonPassResults, ...passedResults].map((r) => (
                        <tr
                          key={r.id}
                          className="border-b border-border/20 last:border-0"
                        >
                          <td className="py-1 pr-3 text-text-secondary">
                            {r.title}
                          </td>
                          <td className="py-1 pr-3">
                            {r.is_required && (
                              <span className="rounded bg-red-900/30 px-1 text-red-400">
                                req
                              </span>
                            )}
                          </td>
                          <td className={`py-1 pr-3 ${statusColor(r.status)}`}>
                            {statusIcon(r.status)} {r.status}
                          </td>
                          <td className="py-1 pr-3 text-text-muted">
                            {r.observed_value ?? "—"}
                          </td>
                          <td className="py-1 pr-3 text-text-muted">
                            {r.expected_value ?? "—"}
                          </td>
                          <td className="py-1 text-text-muted">
                            {r.suggested_action ?? "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Collapsible test definitions */}
          <button
            onClick={() => setDefsOpen((o) => !o)}
            className="font-mono text-2xs text-text-muted hover:text-text-secondary"
          >
            {defsOpen ? "▾" : "▸"} {tests.length} test definition{tests.length !== 1 ? "s" : ""}
          </button>
          {defsOpen && (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full font-mono text-2xs">
                <thead>
                  <tr className="border-b border-border/30 text-left text-text-muted">
                    <th className="pb-1 pr-3">Name</th>
                    <th className="pb-1 pr-3">Type</th>
                    <th className="pb-1 pr-3">Severity</th>
                    <th className="pb-1 pr-3">Required</th>
                    <th className="pb-1">Enabled</th>
                  </tr>
                </thead>
                <tbody>
                  {tests.map((t) => (
                    <tr
                      key={t.id}
                      className="border-b border-border/20 last:border-0"
                    >
                      <td className="py-1 pr-3 text-text-secondary">{t.name}</td>
                      <td className="py-1 pr-3 text-text-muted">{t.test_type}</td>
                      <td className="py-1 pr-3 text-text-muted">{t.severity}</td>
                      <td className="py-1 pr-3 text-text-muted">
                        {t.is_required ? "yes" : "no"}
                      </td>
                      <td className="py-1 text-text-muted">
                        {t.is_enabled ? "yes" : "no"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// M54: Config Policy Engine panel
// ---------------------------------------------------------------------------
function ConfigPolicyPanel({
  strategyId,
  configPolicies,
  setConfigPolicies,
  latestEvaluation,
  setLatestEvaluation,
  configPolicyEvaluations,
  setConfigPolicyEvaluations,
}: {
  strategyId: string;
  configPolicies: StrategyConfigPolicy[];
  setConfigPolicies: (p: StrategyConfigPolicy[]) => void;
  latestEvaluation: ConfigPolicyEvaluation | null;
  setLatestEvaluation: (e: ConfigPolicyEvaluation | null) => void;
  configPolicyEvaluations: ConfigPolicyEvaluation[];
  setConfigPolicyEvaluations: (e: ConfigPolicyEvaluation[]) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [evalLoading, setEvalLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPolicyId, setSelectedPolicyId] = useState<string>("");

  const handleCreateDefault = async () => {
    setLoading(true);
    setError(null);
    try {
      await createDefaultConfigPolicy(strategyId);
      const updated = await getStrategyConfigPolicies(strategyId);
      setConfigPolicies(updated);
      if (!selectedPolicyId && updated.length > 0) setSelectedPolicyId(updated[0].id);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleEvaluate = async () => {
    const pid = selectedPolicyId || configPolicies[0]?.id;
    if (!pid) return;
    setEvalLoading(true);
    setError(null);
    try {
      const result = await evaluateConfigPolicy(strategyId, pid, {});
      setLatestEvaluation(result);
      const evals = await getConfigPolicyEvaluations(strategyId);
      setConfigPolicyEvaluations(evals.items || []);
    } catch (e) {
      setError(String(e));
    } finally {
      setEvalLoading(false);
    }
  };

  const statusColor = (s: string) => {
    if (s === "passed") return "text-cyan-400";
    if (s === "warning") return "text-amber-400";
    if (s === "failed") return "text-red-400";
    if (s === "skipped") return "text-gray-500";
    return "text-gray-400";
  };

  const severityBadge = (sev: string) => {
    if (sev === "critical" || sev === "high") return "bg-red-900/40 text-red-300";
    if (sev === "medium") return "bg-amber-900/40 text-amber-300";
    if (sev === "low") return "bg-blue-900/40 text-blue-300";
    return "bg-gray-800 text-gray-400";
  };

  return (
    <div className="border border-gray-700 rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-mono font-semibold text-gray-200 tracking-wide uppercase">
          Config Policy Guardrails
        </h3>
        <span className="text-xs text-gray-500 font-mono">
          Evidence gate — not trading approval
        </span>
      </div>

      {/* Setup */}
      {configPolicies.length === 0 ? (
        <div className="space-y-2">
          <p className="text-xs text-gray-400 font-mono">
            No config policies defined. Create default assumption guardrails to evaluate config snapshots.
          </p>
          <button
            onClick={handleCreateDefault}
            disabled={loading}
            className="px-3 py-1.5 text-xs font-mono bg-cyan-900/30 border border-cyan-700 text-cyan-300 rounded hover:bg-cyan-900/50 disabled:opacity-50"
          >
            {loading ? "Creating…" : "Create Default Guardrails"}
          </button>
        </div>
      ) : (
        <div className="space-y-1">
          <div className="flex items-center gap-3 text-xs font-mono text-gray-400">
            <span>
              <span className="text-gray-200">{configPolicies.length}</span>{" "}
              polic{configPolicies.length === 1 ? "y" : "ies"}
            </span>
            <span>
              <span className="text-cyan-400">
                {configPolicies.filter((p) => p.is_active).length}
              </span>{" "}
              active
            </span>
            {configPolicies[0] && (
              <span className="text-gray-500">{configPolicies[0].rule_count} rules</span>
            )}
          </div>
          {/* Policy list */}
          <div className="space-y-1">
            {configPolicies.map((p) => (
              <div
                key={p.id}
                onClick={() => setSelectedPolicyId(p.id)}
                className={
                  "flex items-center justify-between px-2 py-1 rounded border cursor-pointer text-xs font-mono " +
                  (selectedPolicyId === p.id
                    ? "border-cyan-700 bg-cyan-900/20"
                    : "border-gray-700 hover:border-gray-600")
                }
              >
                <span className="text-gray-200">{p.name}</span>
                <span className={p.is_active ? "text-cyan-400" : "text-gray-500"}>
                  {p.is_active ? "active" : "inactive"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Evaluate button */}
      {configPolicies.length > 0 && (
        <button
          onClick={handleEvaluate}
          disabled={evalLoading}
          className="px-3 py-1.5 text-xs font-mono bg-gray-800 border border-gray-600 text-gray-200 rounded hover:bg-gray-700 disabled:opacity-50"
        >
          {evalLoading ? "Evaluating…" : "Evaluate Config Policy"}
        </button>
      )}

      {error && <p className="text-xs text-red-400 font-mono">{error}</p>}

      {/* Latest evaluation */}
      {latestEvaluation && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span
              className={
                "text-xs font-mono font-semibold " +
                statusColor(latestEvaluation.overall_status)
              }
            >
              {latestEvaluation.overall_status.toUpperCase().replace(/_/g, " ")}
            </span>
            <span className="text-xs text-gray-500 font-mono">
              {latestEvaluation.passed_count}✓ {latestEvaluation.failed_count}✗{" "}
              {latestEvaluation.warning_count}⚠ {latestEvaluation.skipped_count}○
            </span>
          </div>
          {latestEvaluation.deterministic_summary && (
            <p className="text-xs text-gray-400 font-mono">
              {latestEvaluation.deterministic_summary}
            </p>
          )}
          {/* Results table */}
          {latestEvaluation.results && latestEvaluation.results.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono border-collapse">
                <thead>
                  <tr className="text-gray-500 text-left border-b border-gray-700">
                    <th className="pb-1 pr-3">Rule</th>
                    <th className="pb-1 pr-3">Status</th>
                    <th className="pb-1 pr-3">Sev</th>
                    <th className="pb-1 pr-3">Req</th>
                    <th className="pb-1 pr-3">Observed</th>
                    <th className="pb-1">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {latestEvaluation.results.map((r) => (
                    <tr key={r.id} className="border-b border-gray-800/50">
                      <td
                        className="py-1 pr-3 text-gray-300 max-w-32 truncate"
                        title={r.title}
                      >
                        {r.title}
                      </td>
                      <td className={"py-1 pr-3 " + statusColor(r.status)}>
                        {r.status}
                      </td>
                      <td className="py-1 pr-3">
                        <span className={"px-1 rounded text-xs " + severityBadge(r.severity)}>
                          {r.severity}
                        </span>
                      </td>
                      <td className="py-1 pr-3 text-gray-500">
                        {r.is_required ? "✓" : "—"}
                      </td>
                      <td
                        className="py-1 pr-3 text-gray-400 max-w-24 truncate"
                        title={r.observed_value || ""}
                      >
                        {r.observed_value || "—"}
                      </td>
                      <td
                        className="py-1 text-gray-500 max-w-40 truncate"
                        title={r.suggested_action || ""}
                      >
                        {r.suggested_action || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Recent evaluations */}
      {configPolicyEvaluations.length > 1 && (
        <details className="text-xs font-mono">
          <summary className="text-gray-500 cursor-pointer hover:text-gray-400">
            Recent evaluations ({configPolicyEvaluations.length})
          </summary>
          <div className="mt-2 space-y-1">
            {configPolicyEvaluations.slice(0, 5).map((e) => (
              <div key={e.id} className="flex items-center gap-3 text-gray-400">
                <span className={statusColor(e.overall_status)}>{e.overall_status}</span>
                <span>
                  {e.passed_count}✓ {e.failed_count}✗
                </span>
                <span className="text-gray-600">
                  {new Date(e.created_at).toLocaleDateString()}
                </span>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// M55: Research Review Cases panel
// ---------------------------------------------------------------------------
function ReviewCasesPanel({
  strategyId,
  reviewCases,
  setReviewCases,
}: {
  strategyId: string;
  reviewCases: ResearchReviewCase[];
  setReviewCases: (c: ResearchReviewCase[]) => void;
}) {
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const result = await generateResearchReviewCases(strategyId);
      setReviewCases(result.cases);
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerating(false);
    }
  };

  const handleAcknowledge = async (caseId: string) => {
    try {
      const updated = await acknowledgeResearchReviewCase(caseId);
      setReviewCases(reviewCases.map((c) => (c.id === caseId ? updated : c)));
    } catch (e) {
      setError(String(e));
    }
  };

  const handleResolve = async (caseId: string) => {
    try {
      const updated = await resolveResearchReviewCase(caseId);
      setReviewCases(reviewCases.map((c) => (c.id === caseId ? updated : c)));
    } catch (e) {
      setError(String(e));
    }
  };

  const severityTextColor = (sev: string) => {
    if (sev === "critical") return "text-red-400";
    if (sev === "high") return "text-orange-400";
    if (sev === "medium") return "text-amber-400";
    if (sev === "low") return "text-blue-400";
    return "text-gray-400";
  };

  const statusBadge = (status: string) => {
    if (status === "open") return "bg-red-900/30 text-red-300";
    if (status === "acknowledged") return "bg-amber-900/30 text-amber-300";
    if (status === "resolved") return "bg-cyan-900/30 text-cyan-300";
    return "bg-gray-800 text-gray-400";
  };

  const openCases = reviewCases.filter((c) => c.status === "open");
  const ackCases = reviewCases.filter((c) => c.status === "acknowledged");
  const resolvedCases = reviewCases.filter((c) => c.status === "resolved");

  return (
    <div className="border border-gray-700 rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-mono font-semibold text-gray-200 tracking-wide uppercase">
          Research Review Cases
        </h3>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="px-3 py-1.5 text-xs font-mono bg-gray-800 border border-gray-600 text-gray-200 rounded hover:bg-gray-700 disabled:opacity-50"
        >
          {generating ? "Generating…" : "Generate Review Cases"}
        </button>
      </div>

      {reviewCases.length > 0 && (
        <div className="flex gap-3 text-xs font-mono">
          {openCases.length > 0 && (
            <span className="text-red-400">{openCases.length} open</span>
          )}
          {ackCases.length > 0 && (
            <span className="text-amber-400">{ackCases.length} acknowledged</span>
          )}
          {resolvedCases.length > 0 && (
            <span className="text-gray-500">{resolvedCases.length} resolved</span>
          )}
        </div>
      )}

      {error && <p className="text-xs text-red-400 font-mono">{error}</p>}

      {reviewCases.length === 0 && !generating && (
        <p className="text-xs text-gray-500 font-mono">
          No review cases. Click &ldquo;Generate&rdquo; to evaluate current evidence state.
        </p>
      )}

      <div className="space-y-2">
        {reviewCases.map((c) => (
          <div
            key={c.id}
            className={
              "border rounded-lg p-3 space-y-2 " +
              (c.status === "resolved" ? "border-gray-700 opacity-60" : "border-gray-600")
            }
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={"text-xs font-mono font-semibold " + severityTextColor(c.severity)}>
                  {c.title}
                </span>
                <span className={"px-1.5 py-0.5 rounded text-xs font-mono " + statusBadge(c.status)}>
                  {c.status}
                </span>
                <span className="text-xs text-gray-600 font-mono">{c.category}</span>
              </div>
              <div className="flex gap-1 shrink-0">
                {c.status === "open" && (
                  <button
                    onClick={() => handleAcknowledge(c.id)}
                    className="px-2 py-0.5 text-xs font-mono border border-amber-700 text-amber-400 rounded hover:bg-amber-900/20"
                  >
                    Ack
                  </button>
                )}
                {(c.status === "open" || c.status === "acknowledged") && (
                  <button
                    onClick={() => handleResolve(c.id)}
                    className="px-2 py-0.5 text-xs font-mono border border-cyan-700 text-cyan-400 rounded hover:bg-cyan-900/20"
                  >
                    Resolve
                  </button>
                )}
              </div>
            </div>

            {c.deterministic_summary && (
              <p className="text-xs text-gray-400 font-mono leading-relaxed">
                {c.deterministic_summary}
              </p>
            )}

            {c.suggested_actions_json && c.suggested_actions_json.length > 0 && (
              <div className="space-y-0.5">
                {c.suggested_actions_json.slice(0, 3).map((a, i) => (
                  <div key={i} className="flex items-start gap-1.5 text-xs font-mono text-gray-500">
                    <span className="text-cyan-600 mt-0.5">›</span>
                    <span>{a}</span>
                  </div>
                ))}
              </div>
            )}

            <button
              onClick={() => setExpandedId(expandedId === c.id ? null : c.id)}
              className="text-xs font-mono text-gray-600 hover:text-gray-400"
            >
              {expandedId === c.id ? "▲ Hide evidence" : "▼ Show evidence"}
            </button>

            {expandedId === c.id && c.evidence_json && (
              <div className="bg-gray-900 rounded p-2 text-xs font-mono text-gray-400 space-y-1">
                {Object.entries(c.evidence_json)
                  .slice(0, 12)
                  .map(([k, v]) => (
                    <div key={k} className="flex gap-2">
                      <span className="text-gray-600 w-40 shrink-0">{k}</span>
                      <span className="text-gray-300">{String(v)}</span>
                    </div>
                  ))}
              </div>
            )}

            <div className="text-xs text-gray-600 font-mono">
              Opened {new Date(c.opened_at).toLocaleDateString()}
              {c.acknowledged_at && (
                <span className="ml-2">
                  · Ack&apos;d {new Date(c.acknowledged_at).toLocaleDateString()}
                </span>
              )}
              {c.resolved_at && (
                <span className="ml-2">
                  · Resolved {new Date(c.resolved_at).toLocaleDateString()}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function EvidenceSLAPanel({
  strategyId,
  slaPolicies,
  setSlaPolicies,
  latestSlaEvaluation,
  setLatestSlaEvaluation,
  slaEvaluations,
  setSlaEvaluations,
}: {
  strategyId: string;
  slaPolicies: EvidenceSLAPolicy[];
  setSlaPolicies: (p: EvidenceSLAPolicy[]) => void;
  latestSlaEvaluation: EvidenceSLAEvaluation | null;
  setLatestSlaEvaluation: (e: EvidenceSLAEvaluation | null) => void;
  slaEvaluations: EvidenceSLAEvaluation[];
  setSlaEvaluations: (e: EvidenceSLAEvaluation[]) => void;
}) {
  const [creating, setCreating] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPolicyId, setSelectedPolicyId] = useState<string>('');

  const handleCreateDefault = async () => {
    setCreating(true);
    setError(null);
    try {
      await createDefaultEvidenceSLAPolicy(strategyId);
      const updated = await getEvidenceSLAPolicies(strategyId);
      setSlaPolicies(updated);
      if (!selectedPolicyId && updated.length > 0) setSelectedPolicyId(updated[0].id);
    } catch (e) {
      setError(String(e));
    } finally {
      setCreating(false);
    }
  };

  const handleEvaluate = async () => {
    const pid = selectedPolicyId || slaPolicies[0]?.id;
    if (!pid) return;
    setEvaluating(true);
    setError(null);
    try {
      const result = await evaluateEvidenceSLAPolicy(strategyId, pid);
      setLatestSlaEvaluation(result);
      const evals = await getEvidenceSLAEvaluations(strategyId);
      setSlaEvaluations(evals.items || []);
    } catch (e) {
      setError(String(e));
    } finally {
      setEvaluating(false);
    }
  };

  const statusColor = (s: string) => {
    if (s === 'passed') return 'text-cyan-400';
    if (s === 'warning') return 'text-amber-400';
    if (s === 'violated') return 'text-red-400';
    if (s === 'skipped') return 'text-gray-500';
    return 'text-gray-400';
  };

  const severityBadge = (sev: string) => {
    if (sev === 'critical' || sev === 'high') return 'bg-red-900/40 text-red-300';
    if (sev === 'medium') return 'bg-amber-900/40 text-amber-300';
    return 'bg-gray-800 text-gray-400';
  };

  const overallStatusColor = (s: string) => {
    if (s === 'passed') return 'text-cyan-400';
    if (s === 'warning') return 'text-amber-400';
    if (s === 'violated') return 'text-red-400';
    return 'text-gray-400';
  };

  return (
    <div className="border border-gray-700 rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-mono font-semibold text-gray-200 tracking-wide uppercase">Evidence SLA Monitor</h3>
        <span className="text-xs text-gray-500 font-mono">Evidence obligations — not trading approval</span>
      </div>

      {slaPolicies.length === 0 ? (
        <div className="space-y-2">
          <p className="text-xs text-gray-400 font-mono">No SLA policies defined. Create the default evidence obligations to track freshness and quality SLAs.</p>
          <button
            onClick={handleCreateDefault}
            disabled={creating}
            className="px-3 py-1.5 text-xs font-mono bg-cyan-900/30 border border-cyan-700 text-cyan-300 rounded hover:bg-cyan-900/50 disabled:opacity-50"
          >
            {creating ? 'Creating…' : 'Create Default Evidence SLA'}
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center gap-3 text-xs font-mono text-gray-400">
            <span><span className="text-gray-200">{slaPolicies.length}</span> polic{slaPolicies.length === 1 ? 'y' : 'ies'}</span>
            <span><span className="text-cyan-400">{slaPolicies.filter(p => p.is_active).length}</span> active</span>
            {slaPolicies[0] && <span className="text-gray-500">{slaPolicies[0].rule_count} rules</span>}
          </div>
          <div className="space-y-1">
            {slaPolicies.map(p => (
              <div
                key={p.id}
                onClick={() => setSelectedPolicyId(p.id)}
                className={"flex items-center justify-between px-2 py-1 rounded border cursor-pointer text-xs font-mono " + (selectedPolicyId === p.id || (!selectedPolicyId && slaPolicies[0]?.id === p.id) ? 'border-cyan-700 bg-cyan-900/20' : 'border-gray-700 hover:border-gray-600')}
              >
                <span className="text-gray-200">{p.name}</span>
                <span className={p.is_active ? 'text-cyan-400' : 'text-gray-500'}>{p.is_active ? 'active' : 'inactive'}</span>
              </div>
            ))}
          </div>
          <button
            onClick={handleEvaluate}
            disabled={evaluating}
            className="px-3 py-1.5 text-xs font-mono bg-gray-800 border border-gray-600 text-gray-200 rounded hover:bg-gray-700 disabled:opacity-50"
          >
            {evaluating ? 'Evaluating…' : 'Evaluate SLA'}
          </button>
        </div>
      )}

      {error && <p className="text-xs text-red-400 font-mono">{error}</p>}

      {latestSlaEvaluation && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span className={"text-xs font-mono font-semibold " + overallStatusColor(latestSlaEvaluation.overall_status)}>
              {latestSlaEvaluation.overall_status.toUpperCase().replace(/_/g, ' ')}
            </span>
            <span className="text-xs text-gray-500 font-mono">
              {latestSlaEvaluation.passed_count}✓&nbsp;
              {latestSlaEvaluation.violated_count > 0 && <span className="text-red-400">{latestSlaEvaluation.violated_count} violated&nbsp;</span>}
              {latestSlaEvaluation.warning_count > 0 && <span className="text-amber-400">{latestSlaEvaluation.warning_count}⚠&nbsp;</span>}
              {latestSlaEvaluation.skipped_count}○
            </span>
          </div>
          {latestSlaEvaluation.deterministic_summary && (
            <p className="text-xs text-gray-400 font-mono">{latestSlaEvaluation.deterministic_summary}</p>
          )}
          {latestSlaEvaluation.results && latestSlaEvaluation.results.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono border-collapse">
                <thead>
                  <tr className="text-gray-500 text-left border-b border-gray-700">
                    <th className="pb-1 pr-3">Rule</th>
                    <th className="pb-1 pr-3">Type</th>
                    <th className="pb-1 pr-3">Status</th>
                    <th className="pb-1 pr-3">Sev</th>
                    <th className="pb-1 pr-3">Observed</th>
                    <th className="pb-1 pr-3">Expected</th>
                    <th className="pb-1">Days</th>
                  </tr>
                </thead>
                <tbody>
                  {latestSlaEvaluation.results.map(r => (
                    <tr key={r.id} className="border-b border-gray-800/50">
                      <td className="py-1 pr-3 text-gray-300 max-w-32 truncate" title={r.title}>{r.title}</td>
                      <td className="py-1 pr-3 text-gray-500">{r.evidence_type || '—'}</td>
                      <td className={"py-1 pr-3 " + statusColor(r.status)}>{r.status}</td>
                      <td className="py-1 pr-3">
                        <span className={"px-1 rounded " + severityBadge(r.severity)}>{r.severity}</span>
                      </td>
                      <td className="py-1 pr-3 text-gray-400">{r.observed_value || '—'}</td>
                      <td className="py-1 pr-3 text-gray-500">{r.expected_value || '—'}</td>
                      <td className="py-1 text-gray-500">{r.days_since_latest != null ? r.days_since_latest.toFixed(0) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {slaEvaluations.length > 1 && (
        <details className="text-xs font-mono">
          <summary className="text-gray-500 cursor-pointer hover:text-gray-400">Recent evaluations ({slaEvaluations.length})</summary>
          <div className="mt-2 space-y-1">
            {slaEvaluations.slice(0, 5).map(e => (
              <div key={e.id} className="flex items-center gap-3 text-gray-400">
                <span className={overallStatusColor(e.overall_status)}>{e.overall_status}</span>
                <span>{e.passed_count}✓ {e.violated_count} violated</span>
                <span className="text-gray-600">{new Date(e.created_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

// M57 - Strategy Change Impact Analysis
function ChangeImpactPanel({ strategyId }: { strategyId: string }) {
  const [impact, setImpact] = useState<StrategyChangeImpactResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState("latest_change");
  const [artifactsOpen, setArtifactsOpen] = useState(false);

  const MODES = [
    { key: "latest_change", label: "Latest Change" },
    { key: "config_change", label: "Config Change" },
    { key: "evidence_change", label: "Evidence Change" },
  ];

  function impactStatusColor(status: string) {
    if (status === "requires_review") return "text-red-400";
    if (status === "high") return "text-red-400";
    if (status === "medium") return "text-amber-400";
    if (status === "low") return "text-cyan-400";
    return "text-zinc-400";
  }

  function impactLevelBadge(level: string) {
    const base = "px-1.5 py-0.5 rounded text-xs font-mono font-semibold";
    if (level === "critical") return `${base} bg-red-900/60 text-red-300`;
    if (level === "high") return `${base} bg-red-900/40 text-red-400`;
    if (level === "medium") return `${base} bg-amber-900/40 text-amber-400`;
    if (level === "low") return `${base} bg-cyan-900/40 text-cyan-400`;
    return `${base} bg-zinc-800 text-zinc-400`;
  }

  function priorityBadge(priority: string) {
    const base = "px-1.5 py-0.5 rounded text-xs font-mono font-semibold";
    if (priority === "critical") return `${base} bg-red-900/60 text-red-300`;
    if (priority === "high") return `${base} bg-orange-900/50 text-orange-400`;
    if (priority === "medium") return `${base} bg-amber-900/40 text-amber-400`;
    return `${base} bg-zinc-800 text-zinc-400`;
  }

  async function handleAnalyze() {
    setLoading(true);
    setError(null);
    setImpact(null);
    try {
      const result = await getStrategyChangeImpact(strategyId, { mode });
      setImpact(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load change impact");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="border border-zinc-800 rounded-lg p-4 font-mono text-sm bg-zinc-950">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-zinc-100 font-semibold text-base tracking-tight">
            M57 — Strategy Change Impact Analysis
          </h3>
          <p className="text-zinc-500 text-xs mt-0.5">
            Downstream effects — not trading approval
          </p>
        </div>
        <button
          onClick={handleAnalyze}
          disabled={loading}
          className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded text-xs font-mono disabled:opacity-50"
        >
          {loading ? "Analyzing..." : "Analyze"}
        </button>
      </div>

      <div className="flex gap-1 mb-3">
        {MODES.map((m) => (
          <button
            key={m.key}
            onClick={() => setMode(m.key)}
            className={`px-2.5 py-1 rounded text-xs font-mono ${
              mode === m.key
                ? "bg-cyan-900/50 text-cyan-300 border border-cyan-700"
                : "bg-zinc-800 text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded p-2 mb-3">
          {error}
        </div>
      )}

      {impact && (
        <div className="space-y-4">
          {/* Header: status + score + summary */}
          <div className="bg-zinc-900 border border-zinc-800 rounded p-3 space-y-1.5">
            <div className="flex items-center gap-3">
              <span className="text-zinc-400 text-xs">Impact Status:</span>
              <span
                className={`font-semibold text-sm uppercase tracking-wide ${impactStatusColor(impact.impact_status)}`}
              >
                {impact.impact_status.replace(/_/g, " ")}
              </span>
              {impact.impact_score !== null && (
                <span className="text-zinc-500 text-xs">
                  score:{" "}
                  <span className="text-zinc-300">
                    {impact.impact_score.toFixed(2)}
                  </span>
                </span>
              )}
            </div>
            {impact.focus_node && (
              <div className="text-zinc-400 text-xs">
                Focus:{" "}
                <span className="text-zinc-200">{impact.focus_node.label}</span>
                <span className="text-zinc-600 ml-1">
                  ({impact.focus_node.node_type})
                </span>
              </div>
            )}
            <div className="text-zinc-300 text-xs leading-relaxed">
              {impact.deterministic_summary}
            </div>
            {impact.downstream_summary && (
              <div className="text-zinc-500 text-xs">
                {impact.downstream_summary}
              </div>
            )}
          </div>

          {/* 3-column grid: assumptions / quality / readiness */}
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-zinc-900 border border-zinc-800 rounded p-3">
              <div className="text-zinc-400 text-xs mb-1 font-semibold">
                Assumption Impacts
              </div>
              <div className="text-zinc-300 text-xs space-y-0.5">
                <div>
                  Weakening:{" "}
                  <span
                    className={
                      impact.assumption_impacts.weakening_change_count > 0
                        ? "text-amber-400 font-semibold"
                        : "text-zinc-400"
                    }
                  >
                    {impact.assumption_impacts.weakening_change_count}
                  </span>
                </div>
                <div>
                  Positive: {impact.assumption_impacts.positive_change_count}
                </div>
                <div className="text-zinc-500 text-xs capitalize">
                  {impact.assumption_impacts.impact_level}
                </div>
              </div>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 rounded p-3">
              <div className="text-zinc-400 text-xs mb-1 font-semibold">
                Quality Impacts
              </div>
              <div className="text-zinc-300 text-xs space-y-0.5">
                <div>
                  Degraded:{" "}
                  <span
                    className={
                      impact.quality_impacts.degraded_quality_count > 0
                        ? "text-amber-400 font-semibold"
                        : "text-zinc-400"
                    }
                  >
                    {impact.quality_impacts.degraded_quality_count}
                  </span>
                </div>
                <div>
                  Missing: {impact.quality_impacts.missing_quality_count}
                </div>
                <div>Total: {impact.quality_impacts.quality_impact_count}</div>
              </div>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 rounded p-3">
              <div className="text-zinc-400 text-xs mb-1 font-semibold">
                Readiness Impacts
              </div>
              <div className="text-zinc-300 text-xs space-y-0.5">
                {impact.readiness_impacts.readiness_verdict && (
                  <div className="text-zinc-200 font-semibold capitalize">
                    {impact.readiness_impacts.readiness_verdict}
                  </div>
                )}
                <div>
                  Promo risks: {impact.readiness_impacts.promotion_risk_count}
                </div>
                <div>
                  Failed regs:{" "}
                  {impact.readiness_impacts.failed_regression_count}
                </div>
                <div className="text-zinc-500 text-xs capitalize">
                  {impact.readiness_impacts.impact_level}
                </div>
              </div>
            </div>
          </div>

          {/* Graph blast radius */}
          {impact.graph_blast_radius?.available && (
            <div className="bg-zinc-900 border border-zinc-800 rounded p-3">
              <div className="text-zinc-400 text-xs font-semibold mb-2">
                Graph Blast Radius —{" "}
                <span className="capitalize">
                  {impact.graph_blast_radius.blast_radius_severity}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-x-4 gap-y-1 text-xs">
                <div className="text-zinc-400">
                  Upstream:{" "}
                  <span className="text-zinc-200">
                    {impact.graph_blast_radius.upstream_count}
                  </span>
                </div>
                <div className="text-zinc-400">
                  Downstream:{" "}
                  <span className="text-zinc-200">
                    {impact.graph_blast_radius.downstream_count}
                  </span>
                </div>
                <div className="text-zinc-400">
                  Affected runs:{" "}
                  <span className="text-zinc-200">
                    {impact.graph_blast_radius.affected_run_count}
                  </span>
                </div>
                <div className="text-zinc-400">
                  Reports:{" "}
                  <span className="text-zinc-200">
                    {impact.graph_blast_radius.affected_report_count}
                  </span>
                </div>
                <div className="text-zinc-400">
                  Audits:{" "}
                  <span className="text-zinc-200">
                    {impact.graph_blast_radius.affected_audit_count}
                  </span>
                </div>
                <div className="text-zinc-400">
                  Alerts:{" "}
                  <span className="text-zinc-200">
                    {impact.graph_blast_radius.affected_alert_count}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Recommended rechecks */}
          {impact.recommended_rechecks.length > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 rounded p-3">
              <div className="text-zinc-400 text-xs font-semibold mb-2">
                Recommended Rechecks
              </div>
              <div className="space-y-1.5">
                {impact.recommended_rechecks.map((r: RecommendedRecheck) => (
                  <div
                    key={r.recheck_key}
                    className={`flex items-start gap-2 text-xs p-1.5 rounded ${
                      r.status === "required"
                        ? "bg-red-900/20 border border-red-900/40"
                        : "bg-zinc-800/50"
                    }`}
                  >
                    <span className={priorityBadge(r.priority)}>
                      {r.priority}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-zinc-200 font-semibold">
                        {r.title}
                      </div>
                      <div className="text-zinc-500 mt-0.5">{r.reason}</div>
                    </div>
                    {r.status === "required" && (
                      <span className="text-red-400 text-xs font-semibold shrink-0">
                        REQUIRED
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Impacted artifacts (collapsible) */}
          {impact.impacted_artifacts.length > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 rounded p-3">
              <button
                onClick={() => setArtifactsOpen((v) => !v)}
                className="flex items-center gap-2 w-full text-left text-xs text-zinc-400 font-semibold"
              >
                <span>{artifactsOpen ? "▾" : "▸"}</span>
                Impacted Artifacts ({impact.impacted_artifacts.length})
              </button>
              {artifactsOpen && (
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-zinc-500 border-b border-zinc-800">
                        <th className="text-left py-1 pr-3 font-normal">
                          Type
                        </th>
                        <th className="text-left py-1 pr-3 font-normal">
                          Label
                        </th>
                        <th className="text-left py-1 pr-3 font-normal">
                          Impact
                        </th>
                        <th className="text-left py-1 font-normal">Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {impact.impacted_artifacts.map((a: ImpactedArtifact) => (
                        <tr
                          key={a.artifact_id}
                          className="border-b border-zinc-800/50"
                        >
                          <td className="py-1 pr-3 text-zinc-500">
                            {a.artifact_type}
                          </td>
                          <td className="py-1 pr-3 text-zinc-200">
                            {a.label}
                          </td>
                          <td className="py-1 pr-3">
                            <span className={impactLevelBadge(a.impact_level)}>
                              {a.impact_level}
                            </span>
                          </td>
                          <td className="py-1 text-zinc-400">{a.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Suggested actions */}
          {impact.suggested_actions.length > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 rounded p-3">
              <div className="text-zinc-400 text-xs font-semibold mb-2">
                Suggested Actions
              </div>
              <ul className="space-y-1">
                {impact.suggested_actions.map((action, i) => (
                  <li key={i} className="text-zinc-300 text-xs flex gap-2">
                    <span className="text-zinc-600 shrink-0">{i + 1}.</span>
                    {action}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="text-zinc-600 text-xs text-right">
            Generated: {new Date(impact.generated_at).toLocaleString()} · mode:{" "}
            {impact.mode}
          </div>
        </div>
      )}
    </div>
  );
}

// M58 - Run Replay Pack
function replayStatusColor(status: RunReplayStatus): string {
  if (status === "complete") return "text-cyan-400";
  if (status === "review") return "text-amber-400";
  return "text-red-400";
}

function replayStatusBg(status: RunReplayStatus): string {
  if (status === "complete") return "bg-cyan-900/40 border-cyan-700/50";
  if (status === "review") return "bg-amber-900/40 border-amber-700/50";
  return "bg-red-900/40 border-red-700/50";
}

function severityChipClass(severity: string): string {
  if (severity === "high") return "bg-red-900/40 text-red-300 border border-red-700/50";
  if (severity === "medium") return "bg-amber-900/40 text-amber-300 border border-amber-700/50";
  return "bg-zinc-800 text-zinc-400 border border-zinc-700";
}

function RunReplayPanel({
  strategyId,
  runs,
}: {
  strategyId: string;
  runs: StrategyRun[];
}) {
  const [selectedRunId, setSelectedRunId] = useState<string>(
    runs.length > 0 ? runs[0].id : "",
  );
  const [replayData, setReplayData] = useState<RunReplayResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [format, setFormat] = useState<"json" | "markdown">("json");
  const [includeRaw, setIncludeRaw] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());

  function toggleSection(key: string) {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function handleGenerate() {
    if (!selectedRunId) return;
    setLoading(true);
    setError(null);
    setReplayData(null);
    getRunReplayPack(strategyId, selectedRunId, {
      format,
      include_raw_json: includeRaw,
    })
      .then((data) => setReplayData(data))
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Failed to generate replay pack"),
      )
      .finally(() => setLoading(false));
  }

  function handleDownload() {
    if (!replayData) return;
    const isJson = format === "json";
    const content = isJson
      ? JSON.stringify(replayData, null, 2)
      : replayData.content ?? JSON.stringify(replayData, null, 2);
    const type = isJson ? "application/json" : "text/markdown";
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = replayData.metadata.filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleCopyMarkdown() {
    if (!replayData?.content) return;
    navigator.clipboard.writeText(replayData.content);
  }

  return (
    <div className="mt-8 rounded-lg border border-border bg-bg-700 p-4">
      <h2 className="font-mono text-sm font-semibold text-text-primary mb-1">
        M58 · Run Replay Pack
      </h2>
      <p className="font-mono text-2xs text-text-muted mb-4">
        Reconstruct what was known at run time from logged evidence only. Not execution
        replay or investment advice.
      </p>

      {runs.length === 0 ? (
        <p className="font-mono text-2xs text-text-muted">No runs logged yet.</p>
      ) : (
        <div className="space-y-4">
          {/* Controls */}
          <div className="flex flex-wrap items-end gap-3">
            {/* Run selector */}
            <div className="flex flex-col gap-1">
              <label className="font-mono text-2xs text-text-muted">Run</label>
              <select
                className="font-mono text-xs bg-bg-600 border border-border text-text-primary rounded px-2 py-1 focus:outline-none focus:border-accent-500"
                value={selectedRunId}
                onChange={(e) => {
                  setSelectedRunId(e.target.value);
                  setReplayData(null);
                  setError(null);
                }}
              >
                {runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.run_tag ?? r.id.slice(0, 8)} · {r.stage}
                  </option>
                ))}
              </select>
            </div>

            {/* Format toggle */}
            <div className="flex flex-col gap-1">
              <label className="font-mono text-2xs text-text-muted">Format</label>
              <div className="flex rounded overflow-hidden border border-border">
                <button
                  className={`font-mono text-2xs px-3 py-1 ${format === "json" ? "bg-accent-500 text-white" : "bg-bg-600 text-text-secondary hover:bg-bg-500"}`}
                  onClick={() => setFormat("json")}
                >
                  JSON
                </button>
                <button
                  className={`font-mono text-2xs px-3 py-1 ${format === "markdown" ? "bg-accent-500 text-white" : "bg-bg-600 text-text-secondary hover:bg-bg-500"}`}
                  onClick={() => setFormat("markdown")}
                >
                  Markdown
                </button>
              </div>
            </div>

            {/* Include raw checkbox */}
            <label className="flex items-center gap-2 cursor-pointer font-mono text-2xs text-text-secondary pb-1">
              <input
                type="checkbox"
                checked={includeRaw}
                onChange={(e) => setIncludeRaw(e.target.checked)}
                className="accent-accent-500"
              />
              Include raw evidence
            </label>

            {/* Generate button */}
            <button
              className="font-mono text-xs bg-accent-500 text-white hover:bg-accent-600 px-4 py-1.5 rounded disabled:opacity-50 disabled:cursor-not-allowed"
              onClick={handleGenerate}
              disabled={loading || !selectedRunId}
            >
              {loading ? "Generating…" : "Generate Replay Pack"}
            </button>
          </div>

          {/* Error */}
          {error && (
            <p className="font-mono text-2xs text-red-400 border border-red-800 rounded px-3 py-2 bg-red-900/20">
              {error}
            </p>
          )}

          {/* Result */}
          {replayData && (
            <div className="space-y-4">
              {/* Header summary row */}
              <div
                className={`rounded border px-4 py-3 flex flex-wrap items-center gap-4 ${replayStatusBg(replayData.replay_status)}`}
              >
                <span
                  className={`font-mono text-xs font-bold uppercase tracking-widest ${replayStatusColor(replayData.replay_status)}`}
                >
                  {replayData.replay_status}
                </span>
                <span className="font-mono text-2xs text-text-secondary">
                  completeness{" "}
                  <span className="text-text-primary font-semibold">
                    {(replayData.replay_completeness_score * 100).toFixed(0)}%
                  </span>
                </span>
                <span className="font-mono text-2xs text-text-muted truncate max-w-xs">
                  {replayData.metadata.filename}
                </span>
                <span className="font-mono text-2xs text-text-muted">
                  {replayData.sections.length} section
                  {replayData.sections.length !== 1 ? "s" : ""}
                </span>
                {replayData.missing_evidence.length > 0 && (
                  <span className="font-mono text-2xs text-red-400">
                    {replayData.missing_evidence.length} missing evidence item
                    {replayData.missing_evidence.length !== 1 ? "s" : ""}
                  </span>
                )}

                {/* Download / copy buttons */}
                <div className="ml-auto flex gap-2">
                  <button
                    className="font-mono text-2xs bg-accent-500 text-white hover:bg-accent-600 px-3 py-1 rounded"
                    onClick={handleDownload}
                  >
                    Download
                  </button>
                  {format === "markdown" && replayData.content && (
                    <button
                      className="font-mono text-2xs bg-bg-500 border border-border text-text-secondary hover:bg-bg-400 px-3 py-1 rounded"
                      onClick={handleCopyMarkdown}
                    >
                      Copy Markdown
                    </button>
                  )}
                </div>
              </div>

              {/* Sections */}
              {replayData.sections.length > 0 && (
                <div>
                  <p className="font-mono text-2xs text-text-muted mb-2 uppercase tracking-wider">
                    Sections
                  </p>
                  <div className="space-y-1">
                    {replayData.sections.map((sec) => (
                      <div
                        key={sec.section_key}
                        className="rounded border border-border bg-bg-600"
                      >
                        <button
                          className="w-full flex items-center gap-3 px-3 py-2 text-left"
                          onClick={() => toggleSection(sec.section_key)}
                        >
                          <span className="font-mono text-xs text-text-primary flex-1">
                            {sec.title}
                          </span>
                          {sec.severity && (
                            <span
                              className={`font-mono text-2xs px-2 py-0.5 rounded ${severityChipClass(sec.severity)}`}
                            >
                              {sec.severity}
                            </span>
                          )}
                          <span className="font-mono text-2xs text-text-muted">
                            {expandedSections.has(sec.section_key) ? "▲" : "▼"}
                          </span>
                        </button>
                        {expandedSections.has(sec.section_key) && (
                          <div className="px-3 pb-3 border-t border-border">
                            <p className="font-mono text-2xs text-text-secondary mt-2">
                              {sec.summary}
                            </p>
                            {Object.keys(sec.evidence_json).length > 0 && (
                              <pre className="font-mono text-2xs text-text-muted mt-2 overflow-x-auto bg-bg-700 rounded p-2 max-h-40">
                                {JSON.stringify(sec.evidence_json, null, 2)}
                              </pre>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Missing evidence */}
              {replayData.missing_evidence.length > 0 && (
                <div>
                  <p className="font-mono text-2xs text-text-muted mb-2 uppercase tracking-wider">
                    Missing Evidence
                  </p>
                  <div className="space-y-1">
                    {replayData.missing_evidence.map((me, i) => (
                      <div
                        key={i}
                        className="flex flex-wrap items-start gap-3 rounded border border-border bg-bg-600 px-3 py-2"
                      >
                        <span
                          className={`font-mono text-2xs px-2 py-0.5 rounded shrink-0 ${severityChipClass(me.severity)}`}
                        >
                          {me.severity}
                        </span>
                        <span className="font-mono text-xs text-text-primary shrink-0">
                          {me.evidence_type}
                        </span>
                        <span className="font-mono text-2xs text-text-secondary">
                          {me.suggested_action}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Suggested review checks */}
              {replayData.suggested_review_checks.length > 0 && (
                <div>
                  <p className="font-mono text-2xs text-text-muted mb-2 uppercase tracking-wider">
                    Suggested Review Checks
                  </p>
                  <ul className="space-y-1">
                    {replayData.suggested_review_checks.map((check, i) => (
                      <li
                        key={i}
                        className="font-mono text-2xs text-text-secondary flex gap-2"
                      >
                        <span className="text-accent-500 shrink-0">·</span>
                        {check}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Deterministic / disclaimer note */}
              <p className="font-mono text-2xs text-text-muted border-t border-border pt-3">
                {replayData.metadata.no_execution_replay_note}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
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

  // M35: version lineage
  const [versionLineage, setVersionLineage] = useState<StrategyVersionLineageResponse | null>(null);

  // M38: signal quality drilldown
  const [signalDrilldown, setSignalDrilldown] = useState<SignalQualityDrilldownResponse | null>(null);
  const [signalDrilldownId, setSignalDrilldownId] = useState<string | null>(null);
  const [signalDrilldownLoading, setSignalDrilldownLoading] = useState(false);

  // M39: universe coverage analysis
  const [universeCoverage, setUniverseCoverage] = useState<UniverseCoverageAnalysisResponse | null>(null);
  const [universeCoverageId, setUniverseCoverageId] = useState<string | null>(null);
  const [universeCoverageLoading, setUniverseCoverageLoading] = useState(false);

  // M40: config diff
  const [configDiff, setConfigDiff] = useState<ConfigSnapshotComparisonV2Response | null>(null);
  const [configDiffLoading, setConfigDiffLoading] = useState(false);
  const [configDiffSnapshotA, setConfigDiffSnapshotA] = useState<string>("");
  const [configDiffSnapshotB, setConfigDiffSnapshotB] = useState<string>("");

  // M41: assumption health
  const [assumptionHealth, setAssumptionHealth] = useState<StrategyAssumptionHealthResponse | null>(null);

  // M43: timeline analytics
  const [timelineAnalytics, setTimelineAnalytics] = useState<StrategyTimelineAnalyticsResponse | null>(null);

  // M47: drift
  const [driftData, setDriftData] = useState<StrategyDriftResponse | null>(null);
  const [freshness, setFreshness] = useState<StrategyEvidenceFreshnessResponse | null>(null);

  // M49: readiness
  const [readiness, setReadiness] = useState<StrategyReadinessResponse | null>(null);

  // M50: shadow monitor
  const [shadowMonitor, setShadowMonitor] = useState<StrategyShadowMonitorResponse | null>(null);

  // M51: promotion gates
  const [promotionGates, setPromotionGates] = useState<StrategyPromotionGateResponse | null>(null);
  // promotionTarget tracks the currently-selected target stage for the promotion gates panel
  const [_promotionTarget, setPromotionTarget] = useState<string>("paper_candidate");

  // M52: evidence graph
  const [evidenceGraph, setEvidenceGraph] = useState<StrategyEvidenceGraphResponse | null>(null);
  const [_graphFocusNode, setGraphFocusNode] = useState<string>("");

  // M53: regression tests
  const [regressionTests, setRegressionTests] = useState<StrategyRegressionTest[]>([]);
  const [regressionRun, setRegressionRun] = useState<StrategyRegressionTestRun | null>(null);
  const [regressionLoading, setRegressionLoading] = useState(false);

  // M54: config policy engine
  const [configPolicies, setConfigPolicies] = useState<StrategyConfigPolicy[]>([]);
  const [configPolicyEvaluations, setConfigPolicyEvaluations] = useState<ConfigPolicyEvaluation[]>([]);
  const [latestEvaluation, setLatestEvaluation] = useState<ConfigPolicyEvaluation | null>(null);

  // M55: research review cases
  const [reviewCases, setReviewCases] = useState<ResearchReviewCase[]>([]);

  // M56: evidence SLA monitor
  const [slaEvaluations, setSlaEvaluations] = useState<EvidenceSLAEvaluation[]>([]);
  const [slaPolicies, setSlaPolicies] = useState<EvidenceSLAPolicy[]>([]);
  const [latestSlaEvaluation, setLatestSlaEvaluation] = useState<EvidenceSLAEvaluation | null>(null);

  async function handleCompareConfig() {
    if (!id || !configDiffSnapshotA || !configDiffSnapshotB) return;
    setConfigDiffLoading(true);
    setConfigDiff(null);
    try {
      const result = await compareConfigSnapshotsV2(id, configDiffSnapshotA, configDiffSnapshotB);
      setConfigDiff(result);
    } catch {
      // silently fail — could add error state later
    } finally {
      setConfigDiffLoading(false);
    }
  }

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
    // M35: load version lineage in parallel
    getStrategyVersionLineage(id).then(setVersionLineage).catch(() => setVersionLineage(null));
    // M41: load assumption health in parallel
    getStrategyAssumptionHealth(id).then(setAssumptionHealth).catch(() => setAssumptionHealth(null));
    // M43: load timeline analytics in parallel
    getStrategyTimelineAnalytics(id).then(setTimelineAnalytics).catch(() => setTimelineAnalytics(null));
    // M47: load drift in parallel
    getStrategyDrift(id).then(setDriftData).catch(() => setDriftData(null));
    // M48: load evidence freshness in parallel
    getStrategyEvidenceFreshness(id).then(setFreshness).catch(() => setFreshness(null));
    // M49: load readiness in parallel
    getStrategyReadiness(id).then(setReadiness).catch(() => setReadiness(null));
    // M50: load shadow monitor in parallel
    getStrategyShadowMonitor(id).then(setShadowMonitor).catch(() => setShadowMonitor(null));
    // M51: load promotion gates in parallel
    getStrategyPromotionGates(id, "paper_candidate").then(setPromotionGates).catch(() => setPromotionGates(null));
    // M52: load evidence graph in parallel
    getStrategyEvidenceGraph(id).then(setEvidenceGraph).catch(() => setEvidenceGraph(null));
    // M53: load regression tests in parallel
    getStrategyRegressionTests(id).then(setRegressionTests).catch(() => {});
    // M54: load config policies and evaluations in parallel
    getStrategyConfigPolicies(id).then(setConfigPolicies).catch(() => {});
    getConfigPolicyEvaluations(id)
      .then((r) => {
        setConfigPolicyEvaluations(r.items || []);
        if (r.items && r.items.length > 0) setLatestEvaluation(r.items[0]);
      })
      .catch(() => {});
    // M55: load review cases in parallel
    getStrategyReviewCases(id)
      .then((r) => setReviewCases(r.items || []))
      .catch(() => {});
    // M56: load evidence SLA policies and evaluations in parallel
    getEvidenceSLAPolicies(id).then(setSlaPolicies).catch(() => {});
    getEvidenceSLAEvaluations(id)
      .then((r) => {
        const items = r.items || [];
        setSlaEvaluations(items);
        if (items.length > 0) setLatestSlaEvaluation(items[0]);
      })
      .catch(() => {});
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

      {/* M49: Strategy Readiness panel */}
      {readiness && <ReadinessPanel readiness={readiness} />}

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
        onInspectCoverage={(snapId) => {
          setUniverseCoverageId(snapId);
          setUniverseCoverageLoading(true);
          getUniverseSnapshotCoverageAnalysis(snapId)
            .then((d) => { setUniverseCoverage(d); setUniverseCoverageLoading(false); })
            .catch(() => setUniverseCoverageLoading(false));
        }}
      />

      {/* M17: Signal Evidence panel */}
      <SignalEvidencePanel
        signalSnapshots={strategy.signal_snapshots}
        onLogSignal={() => setSignalSnapshotDrawerOpen(true)}
        onInspectQuality={(snapId) => {
          setSignalDrilldownId(snapId);
          setSignalDrilldownLoading(true);
          getSignalSnapshotQualityDrilldown(snapId)
            .then((d) => { setSignalDrilldown(d); setSignalDrilldownLoading(false); })
            .catch(() => setSignalDrilldownLoading(false));
        }}
      />

      {/* M15: Version & Config Evidence */}
      <VersionConfigSection
        versions={strategy.versions}
        configSnapshots={strategy.config_snapshots}
        onCreateVersion={() => setVersionDrawerOpen(true)}
        onLogConfig={() => setConfigSnapshotDrawerOpen(true)}
        snapshotA={configDiffSnapshotA}
        snapshotB={configDiffSnapshotB}
        onSnapshotAChange={setConfigDiffSnapshotA}
        onSnapshotBChange={setConfigDiffSnapshotB}
        onCompare={handleCompareConfig}
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
                          <BacktestV3Panel audit={audits[r.id]} />
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

      {/* M31: Strategy Evidence Export */}
      <ExportPanel strategyId={id!} />

      {/* M35: Version Lineage */}
      {versionLineage && <VersionLineagePanel lineage={versionLineage} />}

      {/* M38: Signal Quality Drilldown */}
      {signalDrilldown && signalDrilldownId && (
        <SignalQualityDrilldownPanel drilldown={signalDrilldown} />
      )}
      {signalDrilldownLoading && (
        <p className="font-mono text-2xs text-text-muted">Loading signal quality…</p>
      )}

      {/* M39: Universe Coverage Analysis */}
      {universeCoverage && universeCoverageId && (
        <UniverseCoveragePanel coverage={universeCoverage} />
      )}
      {universeCoverageLoading && (
        <p className="font-mono text-2xs text-text-muted">Loading universe coverage…</p>
      )}

      {/* M40: Config Diff */}
      {configDiff && <ConfigDiffPanel diff={configDiff} />}
      {configDiffLoading && (
        <p className="font-mono text-2xs text-text-muted">Comparing configs…</p>
      )}

      {/* M41: Assumption Health */}
      {assumptionHealth && <AssumptionHealthPanel health={assumptionHealth} />}

      {/* M43: Timeline Analytics */}
      {timelineAnalytics && <TimelineAnalyticsPanel analytics={timelineAnalytics} />}

      {/* M47: Drift Panel */}
      {driftData && (
        <DriftPanel
          drift={driftData}
          onModeChange={(m) => {
            getStrategyDrift(id!, { mode: m }).then(setDriftData).catch(() => {});
          }}
        />
      )}

      {/* M48: Evidence Freshness */}
      {freshness && <FreshnessPanel freshness={freshness} />}

      {/* M50: Shadow Production Monitor */}
      {shadowMonitor && <ShadowMonitorPanel monitor={shadowMonitor} />}

      {/* M51: Promotion Gates */}
      {promotionGates && (
        <PromotionGatesPanel
          gates={promotionGates}
          onTargetChange={(t) => {
            setPromotionTarget(t);
            getStrategyPromotionGates(id!, t).then(setPromotionGates).catch(() => {});
          }}
        />
      )}

      {/* M52: Evidence Dependency Graph */}
      {evidenceGraph && (
        <EvidenceGraphPanel
          graph={evidenceGraph}
          strategyId={id}
          onFocusChange={(nid, ntype) => {
            setGraphFocusNode(nid);
            getStrategyEvidenceGraph(id!, { focus_node_id: nid, focus_node_type: ntype })
              .then(setEvidenceGraph)
              .catch(() => {});
          }}
        />
      )}

      {/* M53: Regression Test Suite */}
      {(regressionTests.length > 0 || true) && (
        <RegressionTestPanel
          tests={regressionTests}
          latestRun={regressionRun}
          loading={regressionLoading}
          strategyId={id!}
          onSetupDefaults={() => {
            setRegressionLoading(true);
            createDefaultRegressionTests(id!)
              .then(setRegressionTests)
              .catch(() => {})
              .finally(() => setRegressionLoading(false));
          }}
          onRunTests={(mode) => {
            setRegressionLoading(true);
            runStrategyRegressionTests(id!, { mode })
              .then((run) => {
                setRegressionRun(run);
              })
              .catch(() => {})
              .finally(() => setRegressionLoading(false));
          }}
        />
      )}

      {/* M54: Config Policy Engine */}
      <ConfigPolicyPanel
        strategyId={id!}
        configPolicies={configPolicies}
        setConfigPolicies={setConfigPolicies}
        latestEvaluation={latestEvaluation}
        setLatestEvaluation={setLatestEvaluation}
        configPolicyEvaluations={configPolicyEvaluations}
        setConfigPolicyEvaluations={setConfigPolicyEvaluations}
      />

      {/* M55: Research Review Cases */}
      <ReviewCasesPanel
        strategyId={id!}
        reviewCases={reviewCases}
        setReviewCases={setReviewCases}
      />

      {/* M56: Evidence SLA Monitor */}
      <EvidenceSLAPanel
        strategyId={strategy.id}
        slaPolicies={slaPolicies}
        setSlaPolicies={setSlaPolicies}
        latestSlaEvaluation={latestSlaEvaluation}
        setLatestSlaEvaluation={setLatestSlaEvaluation}
        slaEvaluations={slaEvaluations}
        setSlaEvaluations={setSlaEvaluations}
      />

      {/* M57: Strategy Change Impact Analysis */}
      <ChangeImpactPanel strategyId={strategy.id} />

      {/* M58: Run Replay Pack */}
      <RunReplayPanel strategyId={strategy.id} runs={strategy.runs} />
    </div>
  );
}
