import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getSystemHealth, seedDemoData, getDemoStatus } from "@/lib/api";
import type {
  SystemHealthResponse,
  SystemOperationalActivityItem,
  DemoSeedResponse,
  DemoStatusResponse,
} from "@/types";
import PageHeader from "@/components/PageHeader";
import Button from "@/components/Button";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusColor(status: string): string {
  switch (status) {
    case "healthy":   return "text-teal-300";
    case "watch":     return "text-yellow-300";
    case "review":    return "text-orange-300";
    case "degraded":  return "text-red-300";
    case "no_batches":
    case "no_activity":
      return "text-text-muted";
    default:          return "text-text-muted";
  }
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-text-muted";
  if (score >= 80) return "text-teal-300";
  if (score >= 60) return "text-yellow-300";
  if (score >= 40) return "text-orange-300";
  return "text-red-300";
}

/** Dot color for status indicator */
function statusDotColor(status: string): string {
  switch (status) {
    case "healthy":   return "bg-teal-400";
    case "watch":     return "bg-yellow-400";
    case "review":    return "bg-orange-400";
    case "degraded":  return "bg-red-400";
    default:          return "bg-text-muted";
  }
}

function statusBadgeCls(status: string): string {
  switch (status) {
    case "healthy":  return "bg-teal-900/30 text-teal-300 border-teal-700/30";
    case "watch":    return "bg-yellow-900/30 text-yellow-300 border-yellow-700/30";
    case "review":   return "bg-orange-900/30 text-orange-300 border-orange-700/30";
    case "degraded": return "bg-red-900/30 text-red-300 border-red-700/30";
    default:         return "bg-bg-600 text-text-muted border-border";
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function formatShortDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function CountCard({
  label, primary, secondary,
}: { label: string; primary: string | number; secondary?: string }) {
  return (
    <div className="rounded-card border border-border bg-bg-700 shadow-card px-4 py-3">
      <p className="text-2xs font-medium tracking-eyebrow text-text-muted truncate">{label}</p>
      <p className="mono-num mt-1.5 text-xl font-bold text-text-primary">{primary}</p>
      {secondary && (
        <p className="font-mono text-2xs text-text-muted mt-0.5">{secondary}</p>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-chip border px-2 py-0.5 text-xs font-medium ${statusBadgeCls(status)}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${statusDotColor(status)}`} />
      {status.replace(/_/g, " ")}
    </span>
  );
}

function HealthPanel({
  title, status, rows,
}: { title: string; status: string; rows: Array<{ label: string; value: string | number; color?: string }> }) {
  return (
    <div className="rounded-card border border-border bg-bg-700 shadow-card flex-1 min-w-0">
      <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
        <p className="text-xs font-semibold text-text-primary">{title}</p>
        <StatusBadge status={status} />
      </div>
      <div className="divide-y divide-border">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between px-4 py-2.5">
            <span className="text-xs text-text-secondary">{row.label}</span>
            <span className={`font-mono text-xs font-semibold ${row.color ?? "text-text-primary"}`}>
              {row.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

const ACTIVITY_ICONS: Record<string, string> = {
  ingestion: "↓",
  alert:     "!",
  timeline:  "◎",
  api_key:   "⚿",
  strategy:  "◈",
  report:    "≡",
};

function ActivityItem({ item }: { item: SystemOperationalActivityItem }) {
  return (
    <div className="flex items-start gap-3 py-2.5">
      <span className="shrink-0 w-6 h-6 flex items-center justify-center rounded bg-bg-600 border border-border font-mono text-xs text-text-muted">
        {ACTIVITY_ICONS[item.item_type] ?? "·"}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-text-primary truncate">{item.title}</p>
        {item.detail && (
          <p className="font-mono text-2xs text-text-muted truncate mt-0.5">{item.detail}</p>
        )}
      </div>
      {item.timestamp && (
        <span className="shrink-0 text-2xs text-text-muted pt-px">
          {formatShortDate(item.timestamp)}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Health status count chips
// ---------------------------------------------------------------------------

const STATUS_CHIP_MAP: Record<string, string> = {
  healthy:              "bg-teal-900/30 text-teal-300 border-teal-700/30",
  watch:                "bg-yellow-900/30 text-yellow-300 border-yellow-700/30",
  review:               "bg-orange-900/30 text-orange-300 border-orange-700/30",
  critical:             "bg-red-900/30 text-red-300 border-red-700/30",
  insufficient_evidence:"bg-bg-600 text-text-muted border-border",
};

function StatusCountChips({ counts }: { counts: Record<string, number> }) {
  return (
    <div className="flex flex-wrap gap-2 px-4 py-3">
      {Object.entries(counts).map(([status, count]) => (
        <span
          key={status}
          className={`inline-flex items-center gap-1.5 rounded-chip border px-2.5 py-1 text-xs font-medium ${STATUS_CHIP_MAP[status] ?? "bg-bg-600 text-text-muted border-border"}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${statusDotColor(status)}`} />
          {status.replace(/_/g, " ")}
          <span className="font-mono font-bold ml-0.5">{count}</span>
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Demo Mode panel
// ---------------------------------------------------------------------------

interface DemoModePanelProps {
  demoStatus: DemoStatusResponse | null;
  demoSeedResult: DemoSeedResponse | null;
  demoSeedLoading: boolean;
  demoSeedError: string | null;
  confirmReset: boolean;
  onConfirmResetChange: (v: boolean) => void;
  onSeedDemo: () => void;
  onResetDemo: () => void;
}

function DemoModePanel({
  demoStatus,
  demoSeedResult,
  demoSeedLoading,
  demoSeedError,
  confirmReset,
  onConfirmResetChange,
  onSeedDemo,
  onResetDemo,
}: DemoModePanelProps) {
  const active = demoStatus?.demo_org_exists ?? false;

  return (
    <div className="rounded-card border border-border bg-bg-700 shadow-card">
      {/* Header */}
      <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
        <p className="text-xs font-semibold text-text-primary">Demo Mode</p>
        <span
          className={`inline-flex items-center gap-1.5 rounded-chip border px-2 py-0.5 text-xs font-medium ${
            active
              ? "bg-teal-900/30 text-teal-300 border-teal-700/30"
              : "bg-bg-600 text-text-muted border-border"
          }`}
        >
          {active && <span className="h-1.5 w-1.5 rounded-full bg-teal-400 shrink-0" />}
          {active ? "Demo Active" : "No Demo Data"}
        </span>
      </div>

      <div className="px-4 py-3 space-y-4">
        {/* Status rows */}
        {demoStatus && (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-x-6 gap-y-2">
              <div className="flex items-center gap-1.5">
                <span className="text-2xs text-text-muted">Org</span>
                <span
                  className={`font-mono text-2xs font-semibold ${
                    demoStatus.demo_org_exists ? "text-teal-300" : "text-text-muted"
                  }`}
                >
                  {demoStatus.demo_org_exists ? "exists" : "none"}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-2xs text-text-muted">Project</span>
                <span
                  className={`font-mono text-2xs font-semibold ${
                    demoStatus.demo_project_exists ? "text-teal-300" : "text-text-muted"
                  }`}
                >
                  {demoStatus.demo_project_exists ? "exists" : "none"}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-2xs text-text-muted">Strategies</span>
                <span className="font-mono text-2xs font-semibold text-text-primary">
                  {demoStatus.strategy_count}
                </span>
              </div>
              {demoStatus.last_seeded_at && (
                <div className="flex items-center gap-1.5">
                  <span className="text-2xs text-text-muted">Last seeded</span>
                  <span className="font-mono text-2xs text-text-secondary">
                    {formatShortDate(demoStatus.last_seeded_at)}
                  </span>
                </div>
              )}
            </div>

            {demoStatus.demo_strategy_names.length > 0 && (
              <div>
                <p className="text-2xs text-text-muted mb-1.5">Demo strategies</p>
                <div className="flex flex-wrap gap-1.5">
                  {demoStatus.demo_strategy_names.map((name, i) => (
                    <span
                      key={i}
                      className="rounded-chip bg-bg-600 border border-border px-2 py-0.5 text-xs text-text-secondary"
                    >
                      {name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {demoStatus.summary && (
              <p className="text-2xs text-text-muted italic">{demoStatus.summary}</p>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="secondary"
            size="sm"
            loading={demoSeedLoading}
            onClick={onSeedDemo}
          >
            {demoSeedLoading ? "Seeding…" : "Seed / Extend Demo Data"}
          </Button>

          <div className="flex items-center gap-2.5">
            <label className="flex items-center gap-1.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={confirmReset}
                onChange={(e) => onConfirmResetChange(e.target.checked)}
                className="accent-red-500"
              />
              <span className="text-2xs text-text-muted">
                I understand this only resets demo data
              </span>
            </label>
            <Button
              variant="danger"
              size="sm"
              disabled={demoSeedLoading || !confirmReset}
              onClick={onResetDemo}
            >
              Reset Demo Data
            </Button>
          </div>
        </div>

        {demoSeedError && (
          <p className="text-xs text-red-300">{demoSeedError}</p>
        )}

        {/* Seed result */}
        {demoSeedResult && (
          <div className="rounded-card border border-border bg-bg-600 px-4 py-3 space-y-3">
            <p className="text-xs font-semibold text-text-primary">
              {demoSeedResult.summary}
            </p>

            <div className="flex flex-wrap gap-x-6 gap-y-1.5">
              {Object.entries(demoSeedResult.created_counts).map(([k, v]) => (
                <div key={k} className="flex items-center gap-1.5">
                  <span className="text-2xs text-text-muted">created {k}</span>
                  <span className="font-mono text-2xs font-bold text-teal-300">{v}</span>
                </div>
              ))}
              {Object.entries(demoSeedResult.reused_counts).map(([k, v]) => (
                <div key={k} className="flex items-center gap-1.5">
                  <span className="text-2xs text-text-muted">reused {k}</span>
                  <span className="font-mono text-2xs font-bold text-text-secondary">{v}</span>
                </div>
              ))}
            </div>

            {demoSeedResult.generated_artifacts.length > 0 && (
              <div>
                <p className="text-2xs text-text-muted mb-1.5">Generated artifacts</p>
                <ul className="space-y-1">
                  {demoSeedResult.generated_artifacts.map((a, i) => (
                    <li key={i} className="text-2xs text-text-secondary flex gap-1.5">
                      <span className="text-text-muted shrink-0">·</span>{a}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {demoSeedResult.warnings.length > 0 && (
              <div>
                <p className="text-2xs text-yellow-300 mb-1.5">Warnings</p>
                <ul className="space-y-1">
                  {demoSeedResult.warnings.map((w, i) => (
                    <li key={i} className="text-2xs text-yellow-300/80 flex gap-1.5">
                      <span className="shrink-0">·</span>{w}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="pt-1 flex flex-wrap gap-3 items-center">
              <span className="text-2xs text-text-muted">Quick links</span>
              <Link to="/" className="text-2xs text-accent-500 hover:text-accent-300 transition-colors">Dashboard</Link>
              <Link to="/portfolio" className="text-2xs text-accent-500 hover:text-accent-300 transition-colors">Portfolio</Link>
              <Link to="/strategies" className="text-2xs text-accent-500 hover:text-accent-300 transition-colors">Strategies</Link>
              <Link to="/evidence/coverage" className="text-2xs text-accent-500 hover:text-accent-300 transition-colors">Evidence Coverage</Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AdminSystemHealth() {
  const [data, setData] = useState<SystemHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Demo Mode state
  const [demoStatus, setDemoStatus] = useState<DemoStatusResponse | null>(null);
  const [demoSeedResult, setDemoSeedResult] = useState<DemoSeedResponse | null>(null);
  const [demoSeedLoading, setDemoSeedLoading] = useState(false);
  const [demoSeedError, setDemoSeedError] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  useEffect(() => {
    getSystemHealth()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load system health"))
      .finally(() => setLoading(false));

    getDemoStatus().then(setDemoStatus).catch(() => {});
  }, []);

  const handleSeedDemo = useCallback(() => {
    setDemoSeedLoading(true);
    setDemoSeedError(null);
    seedDemoData({ mode: "extend" })
      .then((res) => {
        setDemoSeedResult(res);
        getDemoStatus().then(setDemoStatus).catch(() => {});
      })
      .catch((e: unknown) => {
        setDemoSeedError(e instanceof Error ? e.message : "Failed to seed demo data");
      })
      .finally(() => setDemoSeedLoading(false));
  }, []);

  const handleResetDemo = useCallback(() => {
    setDemoSeedLoading(true);
    setDemoSeedError(null);
    seedDemoData({ mode: "reset_demo_only", confirm_reset: true })
      .then((res) => {
        setDemoSeedResult(res);
        setConfirmReset(false);
        getDemoStatus().then(setDemoStatus).catch(() => {});
      })
      .catch((e: unknown) => {
        setDemoSeedError(e instanceof Error ? e.message : "Failed to reset demo data");
      })
      .finally(() => setDemoSeedLoading(false));
  }, []);

  if (loading) {
    return (
      <div>
        <PageHeader tag="Admin" title="System Health" subtitle="Operations overview for this QuantFidelity instance." />
        <p className="text-sm text-text-muted">Loading system health…</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div>
        <PageHeader tag="Admin" title="System Health" subtitle="Operations overview for this QuantFidelity instance." />
        <p className="text-sm text-red-300">{error ?? "No data available."}</p>
      </div>
    );
  }

  const ec = data.entity_counts;
  const totalSnapshots =
    ec.total_dataset_snapshots +
    ec.total_signal_snapshots +
    ec.total_universe_snapshots +
    ec.total_config_snapshots;

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader tag="Admin" title="System Health" subtitle="Operations overview for this QuantFidelity instance." />

      {/* Status banner */}
      <div className="rounded-card border border-border bg-bg-700 shadow-card px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          {/* Score */}
          {data.system_score !== null && (
            <div className="flex items-baseline gap-2">
              <span className={`mono-num text-3xl font-bold leading-none ${scoreColor(data.system_score)}`}>
                {data.system_score.toFixed(1)}
              </span>
              <span className="text-xs text-text-muted">ops score</span>
            </div>
          )}

          {/* Status badge */}
          <div className="flex items-center gap-2">
            <span className="text-2xs text-text-muted">Status</span>
            <StatusBadge status={data.system_status} />
          </div>

          {/* Environment / DB chips */}
          <div className="flex items-center gap-1.5">
            <span className="rounded-chip bg-bg-600 border border-border px-2 py-0.5 font-mono text-2xs text-text-secondary">
              {data.environment}
            </span>
            <span className="rounded-chip bg-bg-600 border border-border px-2 py-0.5 font-mono text-2xs text-text-secondary">
              {data.db_type}
            </span>
          </div>

          {/* Timestamp — pushed right */}
          <div className="ml-auto flex flex-col items-end gap-0.5">
            <span className="text-2xs text-text-muted">Generated</span>
            <span className="font-mono text-2xs text-text-secondary">{formatDate(data.generated_at)}</span>
          </div>
        </div>

        {data.note && (
          <p className="mt-3 text-xs text-text-muted italic border-t border-border pt-3">{data.note}</p>
        )}
      </div>

      {/* Entity count grid */}
      <div>
        <p className="caption mb-3">Entity Counts</p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <CountCard label="Strategies" primary={ec.total_strategies} secondary={`${ec.active_strategies} active`} />
          <CountCard label="Runs" primary={ec.total_runs} />
          <CountCard label="Datasets" primary={ec.total_datasets} />
          <CountCard label="Snapshots" primary={totalSnapshots} secondary={`ds:${ec.total_dataset_snapshots} sig:${ec.total_signal_snapshots}`} />
          <CountCard label="Backtest Audits" primary={ec.total_backtest_audits} />
          <CountCard label="Alerts" primary={ec.open_alerts} secondary={`${ec.total_alerts} total`} />
          <CountCard label="Reports" primary={ec.total_reports} />
          <CountCard label="API Keys" primary={ec.active_api_keys} secondary={`${ec.total_api_keys} total`} />
          <CountCard label="Ingestion Batches" primary={ec.total_ingestion_batches} />
          <CountCard label="Timeline Events" primary={ec.total_timeline_events} />
        </div>
      </div>

      {/* Three health panels */}
      <div>
        <p className="caption mb-3">Subsystem Health</p>
        <div className="flex flex-col sm:flex-row gap-4">
          <HealthPanel
            title="Ingestion"
            status={data.ingestion_health.ingestion_status}
            rows={[
              { label: "Total Batches",  value: data.ingestion_health.total_batches },
              { label: "Completed",      value: data.ingestion_health.completed_batches, color: "text-teal-300" },
              { label: "Failed",         value: data.ingestion_health.failed_batches, color: data.ingestion_health.failed_batches > 0 ? "text-red-300" : "text-text-primary" },
              { label: "Failure Rate",   value: `${(data.ingestion_health.failure_rate * 100).toFixed(1)}%`, color: data.ingestion_health.failure_rate > 0.1 ? "text-orange-300" : "text-text-primary" },
              { label: "Recent Failed",  value: data.ingestion_health.recent_failed_batches_count },
              { label: "Latest Batch",   value: formatShortDate(data.ingestion_health.latest_batch_at) },
            ]}
          />
          <HealthPanel
            title="API Keys"
            status={data.api_key_health.api_key_status}
            rows={[
              { label: "Active",      value: data.api_key_health.active_api_keys, color: "text-teal-300" },
              { label: "Revoked",     value: data.api_key_health.revoked_api_keys },
              { label: "Used Last 7d",value: data.api_key_health.keys_used_last_7d },
              { label: "Never Used",  value: data.api_key_health.keys_never_used, color: data.api_key_health.keys_never_used > 0 ? "text-yellow-300" : "text-text-primary" },
              { label: "Stale Keys",  value: data.api_key_health.stale_keys_count, color: data.api_key_health.stale_keys_count > 0 ? "text-orange-300" : "text-text-primary" },
            ]}
          />
          <HealthPanel
            title="Evidence Activity"
            status={data.evidence_activity.activity_status}
            rows={[
              { label: "Last 24h",    value: data.evidence_activity.events_last_24h },
              { label: "Last 7d",     value: data.evidence_activity.events_last_7d },
              { label: "Last 30d",    value: data.evidence_activity.events_last_30d },
              { label: "Latest Event",value: formatShortDate(data.evidence_activity.latest_event_at) },
            ]}
          />
        </div>
      </div>

      {/* Strategy Health Rollup */}
      <div className="rounded-card border border-border bg-bg-700 shadow-card">
        <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
          <p className="text-xs font-semibold text-text-primary">Strategy Health Rollup</p>
          <Link to="/strategies" className="text-2xs text-accent-500 hover:text-accent-300 transition-colors">
            All strategies →
          </Link>
        </div>
        <StatusCountChips counts={data.strategy_health_rollup.strategy_count_by_health_status} />
        {data.strategy_health_rollup.strategies_requiring_review.length > 0 && (
          <div className="border-t border-border px-4 py-3">
            <p className="text-2xs text-text-muted mb-2">Requiring review</p>
            <div className="space-y-1.5">
              {data.strategy_health_rollup.strategies_requiring_review.map((s, i) => {
                const name   = String(s.name ?? s.strategy_name ?? "Unknown");
                const status = String(s.health_status ?? "");
                const id     = String(s.strategy_id ?? s.id ?? "");
                return (
                  <div key={i} className="flex items-center gap-2.5">
                    {id ? (
                      <Link
                        to={`/strategies/${id}`}
                        className="text-xs text-accent-500 hover:text-accent-300 transition-colors truncate"
                      >
                        {name}
                      </Link>
                    ) : (
                      <span className="text-xs text-text-primary truncate">{name}</span>
                    )}
                    {status && (
                      <span className={`text-2xs ${statusColor(status)} shrink-0`}>
                        {status.replace(/_/g, " ")}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Project Health Rollup */}
      <div className="rounded-card border border-border bg-bg-700 shadow-card">
        <div className="border-b border-border px-4 py-2.5">
          <p className="text-xs font-semibold text-text-primary">Project Health Rollup</p>
        </div>
        <StatusCountChips counts={data.project_health_rollup.project_count_by_health_status} />
        {data.project_health_rollup.projects_requiring_review.length > 0 && (
          <div className="border-t border-border px-4 py-3">
            <p className="text-2xs text-text-muted mb-2">Requiring review</p>
            <div className="space-y-1.5">
              {data.project_health_rollup.projects_requiring_review.map((p, i) => {
                const name   = String(p.project_name ?? p.name ?? "Unknown");
                const status = String(p.health_status ?? "");
                return (
                  <div key={i} className="flex items-center gap-2.5">
                    <span className="text-xs text-text-primary truncate">{name}</span>
                    {status && (
                      <span className={`text-2xs ${statusColor(status)} shrink-0`}>
                        {status.replace(/_/g, " ")}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Recent Operational Activity */}
      {data.recent_activity.length > 0 && (
        <div className="rounded-card border border-border bg-bg-700 shadow-card">
          <div className="border-b border-border px-4 py-2.5">
            <p className="text-xs font-semibold text-text-primary">Recent Operational Activity</p>
          </div>
          <div className="px-4 divide-y divide-border">
            {data.recent_activity.slice(0, 10).map((item, i) => (
              <ActivityItem key={i} item={item} />
            ))}
          </div>
        </div>
      )}

      {/* Demo Mode */}
      <DemoModePanel
        demoStatus={demoStatus}
        demoSeedResult={demoSeedResult}
        demoSeedLoading={demoSeedLoading}
        demoSeedError={demoSeedError}
        confirmReset={confirmReset}
        onConfirmResetChange={setConfirmReset}
        onSeedDemo={handleSeedDemo}
        onResetDemo={handleResetDemo}
      />

      {/* Suggested Operational Checks */}
      {data.suggested_operational_checks.length > 0 && (
        <div className="rounded-card border border-border bg-bg-700 shadow-card px-4 py-4">
          <p className="text-xs font-semibold text-text-primary mb-3">Suggested Operational Checks</p>
          <ul className="space-y-2">
            {data.suggested_operational_checks.map((check, i) => (
              <li key={i} className="flex items-start gap-2.5">
                <span className="text-accent-500 mt-px shrink-0">·</span>
                <span className="text-xs text-text-secondary">{check}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Deployment Readiness */}
      <div className="rounded-card border border-border bg-bg-700 shadow-card px-5 py-4 flex items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <p className="text-xs font-semibold text-text-primary">Deployment Readiness</p>
          <p className="text-2xs text-text-muted">M66 backend deployment prep begins next</p>
        </div>
        <Link
          to="/admin/deployment-readiness"
          className="text-xs text-accent-500 hover:text-accent-300 transition-colors shrink-0"
        >
          View checks →
        </Link>
      </div>

      {/* Footer note */}
      <p className="text-2xs text-text-muted pb-2">
        Deterministic system overview — not for external reporting.
      </p>
    </div>
  );
}
