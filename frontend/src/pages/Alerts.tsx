import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type {
  Alert,
  AlertFilters,
  AlertHistory,
  AlertListResponse,
  AlertSummary,
} from "@/types";
import {
  acknowledgeAlert,
  generateAlerts,
  getAlertHistory,
  getAlerts,
  getAlertsSummary,
  resolveAlert,
  snoozeAlert,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Visual helpers
// ---------------------------------------------------------------------------

const SEVERITY_DOT: Record<string, string> = {
  info: "bg-bg-600 border border-border",
  low: "bg-blue-400",
  medium: "bg-yellow-400",
  high: "bg-orange-400",
  critical: "bg-red-500",
};

const SEVERITY_CARD: Record<string, string> = {
  critical: "border-red-700/40 bg-red-900/15",
  high: "border-orange-700/40 bg-orange-900/15",
  medium: "border-yellow-700/40 bg-yellow-900/15",
  low: "border-blue-700/40 bg-blue-900/15",
};

const SEVERITY_TEXT: Record<string, string> = {
  critical: "text-red-300",
  high: "text-orange-300",
  medium: "text-yellow-300",
  low: "text-blue-300",
};

const STATUS_BADGE: Record<string, string> = {
  open: "bg-red-900/40 text-red-300 border-red-700/40",
  acknowledged: "bg-yellow-900/40 text-yellow-300 border-yellow-700/40",
  resolved: "bg-teal-900/40 text-teal-300 border-teal-700/40",
  snoozed: "bg-bg-600 text-text-muted border-border",
  dismissed: "bg-bg-600 text-text-muted border-border",
};

const RULE_LABEL: Record<string, string> = {
  data_health_below_threshold: "Data Health",
  backtest_trust_below_threshold: "Backtest Trust",
  data_quality_issue_high_or_critical: "Data Quality",
  backtest_issue_high_or_critical: "Backtest Issue",
  strategy_run_missing_dataset_evidence: "Missing Evidence",
  evidence_coverage_below_threshold: "Evidence Coverage",
  strategy_health_review_or_critical: "Strategy Health",
  reliability_score_deteriorating: "Reliability Trend",
  data_health_deteriorating: "Data Health Trend",
  signal_quality_deteriorating: "Signal Quality Trend",
  backtest_trust_deteriorating: "Backtest Trust Trend",
  stale_strategy_run: "Stale Run",
  repeated_failed_ingestion: "Ingestion Failures",
  missing_signal_evidence: "Missing Signal",
  missing_universe_evidence: "Missing Universe",
  missing_config_evidence: "Missing Config",
};

function SeverityDot({ severity }: { severity: string }) {
  return (
    <span
      className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${SEVERITY_DOT[severity] ?? "bg-bg-600"}`}
    />
  );
}

function StatusBadge({ status }: { status: string }) {
  const style = STATUS_BADGE[status] ?? "bg-bg-600 text-text-muted border-border";
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 font-mono text-2xs leading-none ${style}`}
    >
      {status}
    </span>
  );
}

function RuleChip({ ruleType }: { ruleType: string }) {
  return (
    <span className="inline-block rounded border border-border bg-bg-600 px-1.5 py-0.5 font-mono text-2xs text-text-muted leading-none">
      {RULE_LABEL[ruleType] ?? ruleType.replace(/_/g, " ")}
    </span>
  );
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

// ---------------------------------------------------------------------------
// History drawer
// ---------------------------------------------------------------------------

function HistoryDrawer({
  alert,
  onClose,
}: {
  alert: Alert;
  onClose: () => void;
}) {
  const [items, setItems] = useState<AlertHistory[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAlertHistory(alert.id)
      .then((r) => setItems(r.items))
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Failed to load history"),
      );
  }, [alert.id]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div className="relative z-10 flex h-full w-full max-w-md flex-col border-l border-border bg-bg-800 shadow-panel">
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0">
            <p className="caption">Alert History</p>
            <p className="mt-0.5 truncate text-sm text-text-primary">{alert.title}</p>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 font-mono text-xs text-text-muted hover:text-text-primary"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {error && (
            <p className="font-mono text-2xs text-red-300">{error}</p>
          )}
          {!error && items === null && (
            <p className="font-mono text-2xs text-text-muted">Loading…</p>
          )}
          {items && items.length === 0 && (
            <p className="font-mono text-2xs text-text-muted">
              No history recorded for this alert.
            </p>
          )}
          {items && items.length > 0 && (
            <ul className="space-y-3">
              {items.map((h) => (
                <li key={h.id} className="border-b border-border pb-3 last:border-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-2xs uppercase tracking-wider text-accent-400">
                      {h.action.replace(/_/g, " ")}
                    </span>
                    <span className="font-mono text-2xs text-text-muted">
                      {fmtTime(h.created_at)}
                    </span>
                  </div>
                  {h.note && (
                    <p className="mt-1 text-xs text-text-secondary leading-relaxed">
                      {h.note}
                    </p>
                  )}
                  <p className="mt-1 font-mono text-2xs text-text-muted/70">
                    {h.actor_user_id ? `actor ${h.actor_user_id.slice(0, 8)}` : "system"}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Alert row
// ---------------------------------------------------------------------------

function AlertRow({
  alert,
  onChanged,
  onOpenHistory,
}: {
  alert: Alert;
  onChanged: (msg: string, isError: boolean) => void;
  onOpenHistory: (alert: Alert) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const suggestedCheck = (alert.metadata_json as any)?.suggested_check as
    | string
    | undefined;
  const evidenceType = alert.evidence_type ?? alert.source_type;
  const evidenceId = alert.evidence_id ?? alert.source_id;

  async function act(
    kind: "acknowledge" | "resolve" | "snooze",
    fn: () => Promise<unknown>,
  ) {
    setBusy(true);
    try {
      await fn();
      const verb =
        kind === "acknowledge"
          ? "acknowledged"
          : kind === "resolve"
            ? "resolved"
            : "snoozed for 24h";
      onChanged(`Alert ${verb}.`, false);
    } catch (e: unknown) {
      onChanged(e instanceof Error ? e.message : "Action failed", true);
    } finally {
      setBusy(false);
    }
  }

  const canAck = alert.status === "open";
  const canSnooze = alert.status === "open" || alert.status === "acknowledged";
  const canResolve =
    alert.status === "open" ||
    alert.status === "acknowledged" ||
    alert.status === "snoozed";

  return (
    <div className="group flex gap-3 border-b border-border py-3 last:border-0">
      <SeverityDot severity={alert.severity} />

      <div className="min-w-0 flex-1">
        {/* Primary line */}
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
          <div className="flex flex-wrap items-center gap-2 min-w-0">
            <StatusBadge status={alert.status} />
            <RuleChip ruleType={alert.rule_type} />
            <span className="text-sm text-text-primary leading-snug min-w-0">
              {alert.title}
            </span>
          </div>
          <span className="shrink-0 font-mono text-2xs text-text-muted whitespace-nowrap">
            {fmtTime(alert.triggered_at)}
          </span>
        </div>

        {/* Secondary line */}
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5">
          {alert.strategy_id && (
            <Link
              to={`/strategies/${alert.strategy_id}`}
              className="font-mono text-2xs text-accent-500/80 hover:text-accent-300"
            >
              strategy {alert.strategy_id.slice(0, 8)}
            </Link>
          )}
          {evidenceType && (
            <span className="font-mono text-2xs text-text-muted">
              {evidenceType.replace(/_/g, " ")}
            </span>
          )}
          <button
            onClick={() => setExpanded((v) => !v)}
            className="font-mono text-2xs text-text-muted/60 hover:text-text-muted"
          >
            {expanded ? "▲ less" : "details ▼"}
          </button>
        </div>

        {/* Expanded detail */}
        {expanded && (
          <div className="mt-1.5 space-y-1.5">
            {alert.description && (
              <p className="text-xs text-text-secondary leading-relaxed">
                {alert.description}
              </p>
            )}
            {alert.recommended_fix && (
              <div className="rounded border border-accent-700/30 bg-accent-900/15 px-2.5 py-1.5">
                <p className="font-mono text-2xs uppercase tracking-wider text-accent-400">
                  Recommended fix
                </p>
                <p className="mt-0.5 text-xs text-text-secondary leading-relaxed">
                  {alert.recommended_fix}
                </p>
              </div>
            )}
            {(evidenceType || evidenceId) && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-2xs text-text-muted">
                  Evidence: {evidenceType ?? "—"}
                  {evidenceId ? ` · ${evidenceId.slice(0, 8)}` : ""}
                </span>
                {alert.strategy_id && (
                  <Link
                    to={`/strategies/${alert.strategy_id}`}
                    className="font-mono text-2xs text-accent-500 hover:text-accent-300"
                  >
                    Open evidence →
                  </Link>
                )}
              </div>
            )}
            {suggestedCheck && (
              <p className="font-mono text-2xs italic text-accent-500/70">
                {suggestedCheck}
              </p>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="mt-2 flex flex-wrap gap-2">
          {canAck && (
            <button
              onClick={() => act("acknowledge", () => acknowledgeAlert(alert.id))}
              disabled={busy}
              className="rounded border border-border bg-bg-600 px-2 py-0.5 font-mono text-2xs text-text-muted hover:border-yellow-600 hover:text-yellow-300 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Acknowledge
            </button>
          )}
          {canSnooze && (
            <button
              onClick={() => act("snooze", () => snoozeAlert(alert.id, { hours: 24 }))}
              disabled={busy}
              className="rounded border border-border bg-bg-600 px-2 py-0.5 font-mono text-2xs text-text-muted hover:border-accent-600 hover:text-accent-300 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Snooze 24h
            </button>
          )}
          {canResolve && (
            <button
              onClick={() => act("resolve", () => resolveAlert(alert.id))}
              disabled={busy}
              className="rounded border border-border bg-bg-600 px-2 py-0.5 font-mono text-2xs text-text-muted hover:border-teal-600 hover:text-teal-300 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Resolve
            </button>
          )}
          <button
            onClick={() => onOpenHistory(alert)}
            className="rounded border border-border bg-bg-600 px-2 py-0.5 font-mono text-2xs text-text-muted hover:border-border-strong hover:text-text-secondary"
          >
            History
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary cards + filters
// ---------------------------------------------------------------------------

function SummaryCard({
  severity,
  count,
}: {
  severity: string;
  count: number;
}) {
  return (
    <div
      className={`rounded-card border px-3 py-2.5 ${SEVERITY_CARD[severity] ?? "border-border bg-bg-700"}`}
    >
      <p
        className={`font-mono text-2xs uppercase tracking-wider ${SEVERITY_TEXT[severity] ?? "text-text-muted"}`}
      >
        {severity}
      </p>
      <p className="mt-0.5 text-lg font-semibold text-text-primary">{count}</p>
    </div>
  );
}

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
      <span className="font-mono text-2xs text-text-muted uppercase tracking-wider">
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
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 50;

const STATUS_TABS = [
  { value: "open", label: "Open" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "snoozed", label: "Snoozed" },
  { value: "resolved", label: "Resolved" },
  { value: "", label: "All" },
];

const SEVERITY_OPTIONS = [
  { value: "", label: "All severities" },
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

const RULE_TYPE_OPTIONS = [
  { value: "", label: "All rule types" },
  ...Object.entries(RULE_LABEL).map(([value, label]) => ({ value, label })),
];

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Alerts() {
  const [searchParams] = useSearchParams();

  const [status, setStatus] = useState(searchParams.get("status") ?? "open");
  const [severity, setSeverity] = useState(searchParams.get("severity") ?? "");
  const [ruleType, setRuleType] = useState(searchParams.get("rule_type") ?? "");
  const [strategyId, setStrategyId] = useState(searchParams.get("strategy_id") ?? "");

  const [response, setResponse] = useState<AlertListResponse | null>(null);
  const [items, setItems] = useState<Alert[]>([]);
  const [summary, setSummary] = useState<AlertSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generateResult, setGenerateResult] = useState<{
    created: number;
    resolved: number;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ msg: string; isError: boolean } | null>(null);
  const [historyAlert, setHistoryAlert] = useState<Alert | null>(null);

  const buildFilters = useCallback(
    (offset = 0): AlertFilters => {
      const f: AlertFilters = { limit: PAGE_SIZE, offset };
      if (status) f.status = status;
      if (severity) f.severity = severity;
      if (ruleType) f.rule_type = ruleType;
      if (strategyId.trim()) f.strategy_id = strategyId.trim();
      return f;
    },
    [status, severity, ruleType, strategyId],
  );

  const refreshSummary = useCallback(() => {
    getAlertsSummary()
      .then(setSummary)
      .catch(() => {});
  }, []);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    getAlerts(buildFilters(0))
      .then((resp) => {
        setResponse(resp);
        setItems(resp.items);
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Failed to load alerts"),
      )
      .finally(() => setLoading(false));
  }, [buildFilters]);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    refreshSummary();
  }, [refreshSummary]);

  function handleLoadMore() {
    if (!response) return;
    setLoadingMore(true);
    getAlerts(buildFilters(items.length))
      .then((resp) => {
        setResponse(resp);
        setItems((prev) => [...prev, ...resp.items]);
      })
      .catch(() => {})
      .finally(() => setLoadingMore(false));
  }

  async function handleGenerate() {
    setGenerating(true);
    setGenerateResult(null);
    setError(null);
    try {
      const result = await generateAlerts();
      setGenerateResult({
        created: result.alerts_created,
        resolved: result.alerts_auto_resolved,
      });
      reload();
      refreshSummary();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Generate failed");
    } finally {
      setGenerating(false);
    }
  }

  function handleChanged(msg: string, isError: boolean) {
    setNotice({ msg, isError });
    if (!isError) {
      reload();
      refreshSummary();
    }
  }

  const hasMore = response !== null && items.length < response.total;
  const totalOpen = summary
    ? summary.by_severity.critical +
      summary.by_severity.high +
      summary.by_severity.medium +
      summary.by_severity.low
    : null;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="caption mb-1">Reliability Signals</p>
          <h1 className="text-xl font-semibold text-text-primary">Alerts</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Deterministic reliability alerts raised by the evidence engine —
            threshold breaches, data quality issues, and missing instrumentation.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {generateResult && (
            <span className="font-mono text-2xs text-text-muted">
              +{generateResult.created} created · {generateResult.resolved} auto-resolved
            </span>
          )}
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="rounded border border-accent-600 bg-accent-900/30 px-3 py-1.5 font-mono text-xs text-accent-300 hover:bg-accent-900/50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {generating ? "Generating…" : "Generate alerts"}
          </button>
        </div>
      </div>

      {/* Severity summary cards */}
      {summary && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <SummaryCard severity="critical" count={summary.by_severity.critical} />
          <SummaryCard severity="high" count={summary.by_severity.high} />
          <SummaryCard severity="medium" count={summary.by_severity.medium} />
          <SummaryCard severity="low" count={summary.by_severity.low} />
          <div className="rounded-card border border-border bg-bg-700 px-3 py-2.5">
            <p className="font-mono text-2xs uppercase tracking-wider text-text-muted">
              Total open
            </p>
            <p className="mt-0.5 text-lg font-semibold text-text-primary">
              {totalOpen ?? summary.open}
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="rounded border border-red-800 bg-red-900/20 px-4 py-3 font-mono text-xs text-red-300">
          {error}
        </div>
      )}

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

      {/* Status tabs */}
      <div className="flex flex-wrap gap-1 border-b border-border">
        {STATUS_TABS.map((t) => {
          const active = status === t.value;
          return (
            <button
              key={t.value || "all"}
              onClick={() => setStatus(t.value)}
              className={`border-b-2 px-3 py-1.5 font-mono text-xs transition-colors ${
                active
                  ? "border-accent-500 text-text-primary"
                  : "border-transparent text-text-muted hover:text-text-secondary"
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-4 rounded-card border border-border bg-bg-700 px-4 py-3">
        <FilterSelect
          label="Severity"
          value={severity}
          options={SEVERITY_OPTIONS}
          onChange={setSeverity}
        />
        <FilterSelect
          label="Rule"
          value={ruleType}
          options={RULE_TYPE_OPTIONS}
          onChange={setRuleType}
        />
        <label className="flex items-center gap-1.5">
          <span className="font-mono text-2xs text-text-muted uppercase tracking-wider">
            Strategy
          </span>
          <input
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
            placeholder="strategy_id"
            className="w-48 rounded border border-border bg-bg-800 px-2 py-1 font-mono text-2xs text-text-secondary placeholder:text-text-muted/50 focus:outline-none focus:ring-1 focus:ring-accent-500"
          />
        </label>
        <span className="ml-auto font-mono text-2xs text-text-muted">
          {response
            ? `${response.total.toLocaleString()} alert${response.total !== 1 ? "s" : ""}`
            : "…"}
        </span>
      </div>

      {/* Alert list */}
      <div className="rounded-card border border-border bg-bg-700">
        {loading ? (
          <div className="px-4 py-10 text-center">
            <p className="font-mono text-2xs text-text-muted">Loading…</p>
          </div>
        ) : items.length === 0 ? (
          <div className="px-4 py-10 text-center">
            <p className="font-mono text-2xs text-text-muted">
              No alerts match the selected filters.
            </p>
            <p className="mt-2 font-mono text-2xs text-text-muted/60">
              Generate alerts to surface reliability signals from existing evidence.
            </p>
          </div>
        ) : (
          <div className="px-4">
            {items.map((alert) => (
              <AlertRow
                key={alert.id}
                alert={alert}
                onChanged={handleChanged}
                onOpenHistory={setHistoryAlert}
              />
            ))}
          </div>
        )}

        {hasMore && !loading && (
          <div className="border-t border-border px-4 py-3 text-center">
            <button
              onClick={handleLoadMore}
              disabled={loadingMore}
              className="font-mono text-2xs text-accent-500 hover:text-accent-300 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loadingMore
                ? "Loading…"
                : `Load more (${response!.total - items.length} remaining)`}
            </button>
          </div>
        )}
      </div>

      {/* Footer disclaimer */}
      <p className="pb-2 font-mono text-2xs text-text-muted">
        Alerts are research reliability signals, not trading recommendations.
      </p>

      {historyAlert && (
        <HistoryDrawer alert={historyAlert} onClose={() => setHistoryAlert(null)} />
      )}
    </div>
  );
}
