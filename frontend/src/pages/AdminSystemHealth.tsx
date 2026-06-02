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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusColor(status: string): string {
  switch (status) {
    case "healthy": return "text-teal-400";
    case "watch": return "text-yellow-400";
    case "review": return "text-orange-400";
    case "degraded": return "text-red-400";
    case "no_batches":
    case "no_activity":
      return "text-text-muted";
    default: return "text-text-muted";
  }
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-text-muted";
  if (score >= 80) return "text-teal-400";
  if (score >= 60) return "text-yellow-400";
  if (score >= 40) return "text-orange-400";
  return "text-red-400";
}

function statusBadgeCls(status: string): string {
  switch (status) {
    case "healthy": return "bg-teal-900/40 text-teal-300 border-teal-700/40";
    case "watch": return "bg-yellow-900/40 text-yellow-200 border-yellow-700/40";
    case "review": return "bg-orange-900/40 text-orange-300 border-orange-700/40";
    case "degraded": return "bg-red-900/40 text-red-300 border-red-700/40";
    default: return "bg-bg-600 text-text-muted border-border";
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
    <div className="rounded border border-border bg-bg-700 px-3 py-2.5">
      <p className="font-mono text-2xs text-text-muted uppercase tracking-wider truncate">{label}</p>
      <p className="mono-num mt-1 text-lg font-bold text-text-primary">{primary}</p>
      {secondary && (
        <p className="font-mono text-2xs text-text-muted mt-0.5">{secondary}</p>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center rounded border px-2 py-0.5 font-mono text-2xs ${statusBadgeCls(status)}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function HealthPanel({
  title, status, rows,
}: { title: string; status: string; rows: Array<{ label: string; value: string | number; color?: string }> }) {
  return (
    <div className="rounded-card border border-border bg-bg-700 flex-1 min-w-0">
      <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
        <p className="caption">{title}</p>
        <StatusBadge status={status} />
      </div>
      <div className="divide-y divide-border">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between px-4 py-2">
            <span className="font-mono text-xs text-text-secondary">{row.label}</span>
            <span className={`font-mono text-xs font-semibold ${row.color ?? "text-text-primary"}`}>
              {row.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ActivityIcon({ type }: { type: string }) {
  const icons: Record<string, string> = {
    ingestion: "↓",
    alert: "!",
    timeline: "◎",
    api_key: "⚿",
    strategy: "◈",
    report: "≡",
  };
  return (
    <span className="shrink-0 w-5 h-5 flex items-center justify-center rounded bg-bg-600 font-mono text-xs text-text-muted">
      {icons[type] ?? "·"}
    </span>
  );
}

function ActivityItem({ item }: { item: SystemOperationalActivityItem }) {
  return (
    <div className="flex items-start gap-2.5 py-2">
      <ActivityIcon type={item.item_type} />
      <div className="min-w-0 flex-1">
        <p className="font-mono text-xs text-text-primary truncate">{item.title}</p>
        {item.detail && (
          <p className="font-mono text-2xs text-text-muted truncate mt-0.5">{item.detail}</p>
        )}
      </div>
      {item.timestamp && (
        <span className="shrink-0 font-mono text-2xs text-text-muted">
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
  healthy: "bg-teal-900/40 text-teal-300 border-teal-700/40",
  watch: "bg-yellow-900/40 text-yellow-200 border-yellow-700/40",
  review: "bg-orange-900/40 text-orange-300 border-orange-700/40",
  critical: "bg-red-900/40 text-red-300 border-red-700/40",
  insufficient_evidence: "bg-bg-600 text-text-muted border-border",
};

function StatusCountChips({ counts }: { counts: Record<string, number> }) {
  return (
    <div className="flex flex-wrap gap-2 px-4 py-3">
      {Object.entries(counts).map(([status, count]) => (
        <span
          key={status}
          className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-2xs ${STATUS_CHIP_MAP[status] ?? "bg-bg-600 text-text-muted border-border"}`}
        >
          {status.replace(/_/g, " ")}
          <span className="font-bold">{count}</span>
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
    <div className="rounded-card border border-border bg-bg-700">
      {/* Header */}
      <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
        <p className="caption">Demo Mode</p>
        <span
          className={`inline-flex items-center rounded border px-2 py-0.5 font-mono text-2xs ${
            active
              ? "bg-teal-900/40 text-teal-300 border-teal-700/40"
              : "bg-bg-600 text-text-muted border-border"
          }`}
        >
          {active ? "Demo Active" : "No Demo Data"}
        </span>
      </div>

      <div className="px-4 py-3 space-y-3">
        {/* Status rows */}
        {demoStatus && (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-x-6 gap-y-1">
              <div className="flex items-center gap-1.5">
                <span className="font-mono text-2xs text-text-muted">Org</span>
                <span
                  className={`font-mono text-2xs font-semibold ${
                    demoStatus.demo_org_exists ? "text-teal-400" : "text-text-muted"
                  }`}
                >
                  {demoStatus.demo_org_exists ? "exists" : "none"}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="font-mono text-2xs text-text-muted">Project</span>
                <span
                  className={`font-mono text-2xs font-semibold ${
                    demoStatus.demo_project_exists ? "text-teal-400" : "text-text-muted"
                  }`}
                >
                  {demoStatus.demo_project_exists ? "exists" : "none"}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="font-mono text-2xs text-text-muted">Strategies</span>
                <span className="font-mono text-2xs font-semibold text-text-primary">
                  {demoStatus.strategy_count}
                </span>
              </div>
              {demoStatus.last_seeded_at && (
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-2xs text-text-muted">Last seeded</span>
                  <span className="font-mono text-2xs text-text-secondary">
                    {formatShortDate(demoStatus.last_seeded_at)}
                  </span>
                </div>
              )}
            </div>

            {demoStatus.demo_strategy_names.length > 0 && (
              <div>
                <p className="font-mono text-2xs text-text-muted mb-1">Demo strategies:</p>
                <div className="flex flex-wrap gap-1.5">
                  {demoStatus.demo_strategy_names.map((name, i) => (
                    <span
                      key={i}
                      className="rounded bg-bg-600 border border-border px-2 py-0.5 font-mono text-2xs text-text-secondary"
                    >
                      {name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {demoStatus.summary && (
              <p className="font-mono text-2xs text-text-muted italic">{demoStatus.summary}</p>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <button
            onClick={onSeedDemo}
            disabled={demoSeedLoading}
            className="rounded border border-border bg-bg-600 hover:bg-bg-500 disabled:opacity-50 px-3 py-1.5 font-mono text-xs text-text-primary transition-colors"
          >
            {demoSeedLoading ? "Seeding..." : "Seed / Extend Demo Data"}
          </button>

          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={confirmReset}
                onChange={(e) => onConfirmResetChange(e.target.checked)}
                className="accent-red-500"
              />
              <span className="font-mono text-2xs text-text-muted">
                I understand this only resets demo data
              </span>
            </label>
            <button
              onClick={onResetDemo}
              disabled={demoSeedLoading || !confirmReset}
              className="rounded border border-red-800/60 bg-red-900/20 hover:bg-red-900/40 disabled:opacity-40 px-3 py-1.5 font-mono text-xs text-red-300 transition-colors"
            >
              Reset Demo Data
            </button>
          </div>
        </div>

        {demoSeedError && (
          <p className="font-mono text-xs text-red-400">{demoSeedError}</p>
        )}

        {/* Seed result */}
        {demoSeedResult && (
          <div className="rounded border border-border bg-bg-600 px-3 py-2.5 space-y-2">
            <p className="font-mono text-xs text-text-primary font-semibold">
              {demoSeedResult.summary}
            </p>

            <div className="flex flex-wrap gap-x-6 gap-y-1">
              {Object.entries(demoSeedResult.created_counts).map(([k, v]) => (
                <div key={k} className="flex items-center gap-1">
                  <span className="font-mono text-2xs text-text-muted">created {k}</span>
                  <span className="font-mono text-2xs font-bold text-teal-400">{v}</span>
                </div>
              ))}
              {Object.entries(demoSeedResult.reused_counts).map(([k, v]) => (
                <div key={k} className="flex items-center gap-1">
                  <span className="font-mono text-2xs text-text-muted">reused {k}</span>
                  <span className="font-mono text-2xs font-bold text-text-secondary">{v}</span>
                </div>
              ))}
            </div>

            {demoSeedResult.generated_artifacts.length > 0 && (
              <div>
                <p className="font-mono text-2xs text-text-muted mb-1">Generated artifacts:</p>
                <ul className="space-y-0.5">
                  {demoSeedResult.generated_artifacts.map((a, i) => (
                    <li key={i} className="font-mono text-2xs text-text-secondary">· {a}</li>
                  ))}
                </ul>
              </div>
            )}

            {demoSeedResult.warnings.length > 0 && (
              <div>
                <p className="font-mono text-2xs text-yellow-400 mb-1">Warnings:</p>
                <ul className="space-y-0.5">
                  {demoSeedResult.warnings.map((w, i) => (
                    <li key={i} className="font-mono text-2xs text-yellow-300">· {w}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="pt-1 flex flex-wrap gap-3">
              <span className="font-mono text-2xs text-text-muted">Quick links:</span>
              <Link to="/" className="font-mono text-2xs text-accent-500 hover:text-accent-300">Dashboard</Link>
              <Link to="/portfolio" className="font-mono text-2xs text-accent-500 hover:text-accent-300">Portfolio</Link>
              <Link to="/strategies" className="font-mono text-2xs text-accent-500 hover:text-accent-300">Strategies</Link>
              <Link to="/evidence/coverage" className="font-mono text-2xs text-accent-500 hover:text-accent-300">Evidence Coverage</Link>
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
        <p className="font-mono text-sm text-text-muted">Loading system health...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div>
        <PageHeader tag="Admin" title="System Health" subtitle="Operations overview for this QuantFidelity instance." />
        <p className="font-mono text-sm text-red-400">{error ?? "No data available."}</p>
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
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="font-mono text-2xs text-text-muted uppercase tracking-wider">Status</span>
          <StatusBadge status={data.system_status} />
        </div>
        {data.system_score !== null && (
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-2xs text-text-muted uppercase tracking-wider">Score</span>
            <span className={`mono-num text-lg font-bold ${scoreColor(data.system_score)}`}>
              {data.system_score.toFixed(1)}
            </span>
          </div>
        )}
        <div className="flex items-center gap-1.5">
          <span className="rounded bg-bg-600 border border-border px-2 py-0.5 font-mono text-2xs text-text-secondary">
            {data.environment}
          </span>
          <span className="rounded bg-bg-600 border border-border px-2 py-0.5 font-mono text-2xs text-text-secondary">
            {data.db_type}
          </span>
        </div>
        <span className="font-mono text-2xs text-text-muted">
          Generated {formatDate(data.generated_at)}
        </span>
        {data.note && (
          <span className="font-mono text-2xs text-text-muted italic">{data.note}</span>
        )}
      </div>

      {/* Entity count grid */}
      <div>
        <p className="caption mb-2">Entity Counts</p>
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
        <p className="caption mb-2">Subsystem Health</p>
        <div className="flex flex-col sm:flex-row gap-4">
          <HealthPanel
            title="Ingestion"
            status={data.ingestion_health.ingestion_status}
            rows={[
              { label: "Total Batches", value: data.ingestion_health.total_batches },
              { label: "Completed", value: data.ingestion_health.completed_batches, color: "text-teal-400" },
              { label: "Failed", value: data.ingestion_health.failed_batches, color: data.ingestion_health.failed_batches > 0 ? "text-red-400" : "text-text-primary" },
              { label: "Failure Rate", value: `${(data.ingestion_health.failure_rate * 100).toFixed(1)}%`, color: data.ingestion_health.failure_rate > 0.1 ? "text-orange-400" : "text-text-primary" },
              { label: "Recent Failed", value: data.ingestion_health.recent_failed_batches_count },
              { label: "Latest Batch", value: formatShortDate(data.ingestion_health.latest_batch_at) },
            ]}
          />
          <HealthPanel
            title="API Keys"
            status={data.api_key_health.api_key_status}
            rows={[
              { label: "Active", value: data.api_key_health.active_api_keys, color: "text-teal-400" },
              { label: "Revoked", value: data.api_key_health.revoked_api_keys },
              { label: "Used Last 7d", value: data.api_key_health.keys_used_last_7d },
              { label: "Never Used", value: data.api_key_health.keys_never_used, color: data.api_key_health.keys_never_used > 0 ? "text-yellow-400" : "text-text-primary" },
              { label: "Stale Keys", value: data.api_key_health.stale_keys_count, color: data.api_key_health.stale_keys_count > 0 ? "text-orange-400" : "text-text-primary" },
            ]}
          />
          <HealthPanel
            title="Evidence Activity"
            status={data.evidence_activity.activity_status}
            rows={[
              { label: "Last 24h", value: data.evidence_activity.events_last_24h },
              { label: "Last 7d", value: data.evidence_activity.events_last_7d },
              { label: "Last 30d", value: data.evidence_activity.events_last_30d },
              { label: "Latest Event", value: formatShortDate(data.evidence_activity.latest_event_at) },
            ]}
          />
        </div>
      </div>

      {/* Strategy Health Rollup */}
      <div className="rounded-card border border-border bg-bg-700">
        <div className="border-b border-border px-4 py-2.5 flex items-center justify-between">
          <p className="caption">Strategy Health Rollup</p>
          <Link to="/strategies" className="font-mono text-2xs text-accent-500 hover:text-accent-300">
            all strategies →
          </Link>
        </div>
        <StatusCountChips counts={data.strategy_health_rollup.strategy_count_by_health_status} />
        {data.strategy_health_rollup.strategies_requiring_review.length > 0 && (
          <div className="border-t border-border px-4 py-2">
            <p className="font-mono text-2xs text-text-muted mb-1.5">Requiring review:</p>
            <div className="space-y-1">
              {data.strategy_health_rollup.strategies_requiring_review.map((s, i) => {
                const name = String(s.name ?? s.strategy_name ?? "Unknown");
                const status = String(s.health_status ?? "");
                const id = String(s.strategy_id ?? s.id ?? "");
                return (
                  <div key={i} className="flex items-center gap-2">
                    {id ? (
                      <Link
                        to={`/strategies/${id}`}
                        className="font-mono text-xs text-accent-500 hover:text-accent-300 truncate"
                      >
                        {name}
                      </Link>
                    ) : (
                      <span className="font-mono text-xs text-text-primary truncate">{name}</span>
                    )}
                    {status && (
                      <span className={`font-mono text-2xs ${statusColor(status)}`}>
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
      <div className="rounded-card border border-border bg-bg-700">
        <div className="border-b border-border px-4 py-2.5">
          <p className="caption">Project Health Rollup</p>
        </div>
        <StatusCountChips counts={data.project_health_rollup.project_count_by_health_status} />
        {data.project_health_rollup.projects_requiring_review.length > 0 && (
          <div className="border-t border-border px-4 py-2">
            <p className="font-mono text-2xs text-text-muted mb-1.5">Requiring review:</p>
            <div className="space-y-1">
              {data.project_health_rollup.projects_requiring_review.map((p, i) => {
                const name = String(p.project_name ?? p.name ?? "Unknown");
                const status = String(p.health_status ?? "");
                return (
                  <div key={i} className="flex items-center gap-2">
                    <span className="font-mono text-xs text-text-primary truncate">{name}</span>
                    {status && (
                      <span className={`font-mono text-2xs ${statusColor(status)}`}>
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
        <div className="rounded-card border border-border bg-bg-700">
          <div className="border-b border-border px-4 py-2.5">
            <p className="caption">Recent Operational Activity</p>
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
        <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
          <p className="caption mb-2">Suggested Operational Checks</p>
          <ul className="space-y-1.5">
            {data.suggested_operational_checks.map((check, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="font-mono text-xs text-accent-500 mt-0.5">·</span>
                <span className="font-mono text-xs text-text-secondary">{check}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Footer note */}
      <p className="font-mono text-2xs text-text-muted pb-2">
        This is a deterministic system overview. Not for external reporting.
      </p>
    </div>
  );
}
