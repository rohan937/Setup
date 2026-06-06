/**
 * StrategyAlertsCard — M85.
 *
 * Self-contained Overview-tab card that surfaces the strategy's open
 * reliability alerts. Loads getStrategyAlerts(id, "open") +
 * getStrategyAlertSummary(id) and shows the open count, by-severity chips,
 * promotion-blocking count, and up to ~5 open alerts with a quick
 * Acknowledge / Resolve action each.
 *
 * Alerts are research reliability signals, not trading recommendations.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  acknowledgeAlert,
  getStrategyAlertSummary,
  getStrategyAlerts,
  resolveAlert,
} from "@/lib/api";
import type { Alert, StrategyAlertSummary } from "@/types";

const SEVERITY_DOT: Record<string, string> = {
  info: "bg-bg-600 border border-border",
  low: "bg-blue-400",
  medium: "bg-yellow-400",
  high: "bg-orange-400",
  critical: "bg-red-500",
};

const SEVERITY_CHIP: Record<string, string> = {
  critical: "border-red-700/40 bg-red-900/20 text-red-300",
  high: "border-orange-700/40 bg-orange-900/20 text-orange-300",
  medium: "border-yellow-700/40 bg-yellow-900/20 text-yellow-300",
  low: "border-blue-700/40 bg-blue-900/20 text-blue-300",
};

const MAX_ROWS = 5;

export default function StrategyAlertsCard({ strategyId }: { strategyId: string }) {
  const [summary, setSummary] = useState<StrategyAlertSummary | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    Promise.all([
      getStrategyAlerts(strategyId, "open"),
      getStrategyAlertSummary(strategyId),
    ])
      .then(([list, sum]) => {
        setAlerts(list.items);
        setSummary(sum);
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Failed to load alerts"),
      )
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategyId]);

  async function act(alertId: string, kind: "ack" | "resolve") {
    setBusyId(alertId);
    setActionError(null);
    try {
      if (kind === "ack") await acknowledgeAlert(alertId);
      else await resolveAlert(alertId);
      load();
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="rounded-card border border-border bg-bg-700">
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-2">
          <p className="caption">Open Alerts</p>
          {summary && (
            <span className="rounded-chip border border-border-strong bg-bg-800 px-2 py-0.5 font-mono text-2xs text-text-secondary">
              {summary.open} open
            </span>
          )}
          {summary && summary.blocking_promotion > 0 && (
            <span className="rounded-chip border border-red-700/40 bg-red-900/20 px-2 py-0.5 font-mono text-2xs text-red-300">
              {summary.blocking_promotion} blocking promotion
            </span>
          )}
        </div>
        <Link
          to={`/alerts?strategy_id=${strategyId}`}
          className="font-mono text-2xs text-accent-500 hover:text-accent-300"
        >
          View all →
        </Link>
      </div>

      {/* Severity chips */}
      {summary && (
        <div className="flex flex-wrap gap-1.5 border-b border-border px-4 py-2">
          {(["critical", "high", "medium", "low"] as const).map((sev) => (
            <span
              key={sev}
              className={`rounded-chip border px-1.5 py-0.5 font-mono text-2xs capitalize ${SEVERITY_CHIP[sev]}`}
            >
              {sev} {summary.by_severity[sev]}
            </span>
          ))}
        </div>
      )}

      <div className="px-4 py-2">
        {error && (
          <p className="py-3 font-mono text-2xs text-red-300">{error}</p>
        )}
        {actionError && (
          <p className="mb-1 font-mono text-2xs text-red-300">{actionError}</p>
        )}
        {loading ? (
          <p className="py-4 font-mono text-2xs text-text-muted">Loading…</p>
        ) : !error && alerts.length === 0 ? (
          <p className="py-4 font-mono text-2xs text-fidelity-high">
            No open alerts — reliability signals are clear.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {alerts.slice(0, MAX_ROWS).map((a) => (
              <li key={a.id} className="flex items-start gap-2.5 py-2">
                <span
                  className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                    SEVERITY_DOT[a.severity] ?? "bg-bg-600"
                  }`}
                />
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-text-primary leading-snug">{a.title}</p>
                  <span className="font-mono text-2xs text-text-muted capitalize">
                    {a.severity}
                  </span>
                </div>
                <div className="flex shrink-0 gap-1.5">
                  <button
                    onClick={() => act(a.id, "ack")}
                    disabled={busyId === a.id}
                    className="rounded border border-border bg-bg-600 px-2 py-0.5 font-mono text-2xs text-text-muted hover:border-yellow-600 hover:text-yellow-300 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Ack
                  </button>
                  <button
                    onClick={() => act(a.id, "resolve")}
                    disabled={busyId === a.id}
                    className="rounded border border-border bg-bg-600 px-2 py-0.5 font-mono text-2xs text-text-muted hover:border-teal-600 hover:text-teal-300 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Resolve
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {!loading && alerts.length > MAX_ROWS && (
          <p className="pb-1 pt-1 font-mono text-2xs text-text-muted">
            +{alerts.length - MAX_ROWS} more open alert
            {alerts.length - MAX_ROWS !== 1 ? "s" : ""}
          </p>
        )}
      </div>
    </div>
  );
}
