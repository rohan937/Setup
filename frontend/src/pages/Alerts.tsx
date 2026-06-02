import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { Alert, AlertFilters, AlertListResponse } from "@/types";
import { generateAlerts, getAlerts, updateAlert } from "@/lib/api";

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

const STATUS_BADGE: Record<string, string> = {
  open: "bg-red-900/40 text-red-300 border-red-700/40",
  acknowledged: "bg-yellow-900/40 text-yellow-300 border-yellow-700/40",
  resolved: "bg-teal-900/40 text-teal-300 border-teal-700/40",
  snoozed: "bg-bg-600 text-text-muted border-border",
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

const M33_RULE_TYPES = new Set([
  "evidence_coverage_below_threshold",
  "strategy_health_review_or_critical",
  "reliability_score_deteriorating",
  "data_health_deteriorating",
  "signal_quality_deteriorating",
  "backtest_trust_deteriorating",
  "stale_strategy_run",
  "repeated_failed_ingestion",
  "missing_signal_evidence",
  "missing_universe_evidence",
  "missing_config_evidence",
]);

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
    <span className={`inline-block rounded border px-1.5 py-0.5 font-mono text-2xs leading-none ${style}`}>
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
// Alert row
// ---------------------------------------------------------------------------

function AlertRow({
  alert,
  onStatusChange,
}: {
  alert: Alert;
  onStatusChange: (id: string, newStatus: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [transitioning, setTransitioning] = useState(false);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const suggestedCheck = (alert.metadata_json as any)?.suggested_check as string | undefined;

  async function handleTransition(newStatus: string) {
    setTransitioning(true);
    try {
      await updateAlert(alert.id, { status: newStatus });
      onStatusChange(alert.id, newStatus);
    } catch {
      // silent — UI stays unchanged
    } finally {
      setTransitioning(false);
    }
  }

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
          {alert.source_type && (
            <span className="font-mono text-2xs text-text-muted">
              {alert.source_type.replace(/_/g, " ")}
            </span>
          )}
          {alert.description && !expanded && (
            <button
              onClick={() => setExpanded(true)}
              className="font-mono text-2xs text-text-muted/60 hover:text-text-muted"
            >
              details ▼
            </button>
          )}
          {expanded && (
            <button
              onClick={() => setExpanded(false)}
              className="font-mono text-2xs text-text-muted/60 hover:text-text-muted"
            >
              ▲
            </button>
          )}
        </div>

        {/* Expanded description */}
        {expanded && alert.description && (
          <p className="mt-1.5 text-xs text-text-secondary leading-relaxed">
            {alert.description}
          </p>
        )}

        {/* Suggested check from metadata */}
        {suggestedCheck && (
          <p className="font-mono text-2xs text-accent-500/70 mt-0.5 italic">
            {suggestedCheck}
          </p>
        )}

        {/* Action buttons — only for non-resolved */}
        {alert.status !== "resolved" && (
          <div className="mt-2 flex flex-wrap gap-2">
            {alert.status === "open" && (
              <button
                onClick={() => handleTransition("acknowledged")}
                disabled={transitioning}
                className="rounded border border-border bg-bg-600 px-2 py-0.5 font-mono text-2xs text-text-muted hover:border-yellow-600 hover:text-yellow-300 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Acknowledge
              </button>
            )}
            <button
              onClick={() => handleTransition("resolved")}
              disabled={transitioning}
              className="rounded border border-border bg-bg-600 px-2 py-0.5 font-mono text-2xs text-text-muted hover:border-teal-600 hover:text-teal-300 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Resolve
            </button>
          </div>
        )}
      </div>
    </div>
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
// Main page
// ---------------------------------------------------------------------------

const PAGE_SIZE = 50;

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "open", label: "Open" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "resolved", label: "Resolved" },
  { value: "snoozed", label: "Snoozed" },
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
  { value: "data_health_below_threshold", label: "Data Health" },
  { value: "backtest_trust_below_threshold", label: "Backtest Trust" },
  { value: "data_quality_issue_high_or_critical", label: "Data Quality" },
  { value: "backtest_issue_high_or_critical", label: "Backtest Issue" },
  { value: "strategy_run_missing_dataset_evidence", label: "Missing Evidence" },
  { value: "evidence_coverage_below_threshold", label: "Evidence Coverage" },
  { value: "strategy_health_review_or_critical", label: "Strategy Health" },
  { value: "reliability_score_deteriorating", label: "Reliability Trend" },
  { value: "data_health_deteriorating", label: "Data Health Trend" },
  { value: "signal_quality_deteriorating", label: "Signal Quality Trend" },
  { value: "backtest_trust_deteriorating", label: "Backtest Trust Trend" },
  { value: "stale_strategy_run", label: "Stale Run" },
  { value: "repeated_failed_ingestion", label: "Ingestion Failures" },
  { value: "missing_signal_evidence", label: "Missing Signal" },
  { value: "missing_universe_evidence", label: "Missing Universe" },
  { value: "missing_config_evidence", label: "Missing Config" },
];

export default function Alerts() {
  const [searchParams] = useSearchParams();

  const [status, setStatus] = useState(searchParams.get("status") ?? "");
  const [severity, setSeverity] = useState(searchParams.get("severity") ?? "");
  const [ruleType, setRuleType] = useState(searchParams.get("rule_type") ?? "");

  const [response, setResponse] = useState<AlertListResponse | null>(null);
  const [items, setItems] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generateResult, setGenerateResult] = useState<{
    created: number;
    skipped: number;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const filtersRef = useRef({ status, severity, ruleType });
  filtersRef.current = { status, severity, ruleType };

  function buildFilters(offset = 0): AlertFilters {
    const f: AlertFilters = { limit: PAGE_SIZE, offset };
    if (status) f.status = status;
    if (severity) f.severity = severity;
    if (ruleType) f.rule_type = ruleType;
    return f;
  }

  useEffect(() => {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, severity, ruleType]);

  function handleLoadMore() {
    if (!response) return;
    const nextOffset = items.length;
    setLoadingMore(true);
    getAlerts(buildFilters(nextOffset))
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
    try {
      const result = await generateAlerts();
      setGenerateResult({
        created: result.alerts_created,
        skipped: result.alerts_skipped_duplicate,
      });
      // Reload the list
      const resp = await getAlerts(buildFilters(0));
      setResponse(resp);
      setItems(resp.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Generate failed");
    } finally {
      setGenerating(false);
    }
  }

  function handleStatusChange(id: string, newStatus: string) {
    setItems((prev) =>
      prev.map((a) => (a.id === id ? { ...a, status: newStatus as Alert["status"] } : a)),
    );
    // Also refresh total counts
    getAlerts(buildFilters(0)).then((resp) => {
      setResponse(resp);
    }).catch(() => {});
  }

  const hasMore = response !== null && items.length < response.total;

  // Count evidence quality alerts (M33 rule types) when no rule_type filter is active
  const evidenceQualityCount =
    !ruleType ? items.filter((a) => M33_RULE_TYPES.has(a.rule_type)).length : 0;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="caption mb-1">Reliability Signals</p>
          <h1 className="text-xl font-semibold text-text-primary">Alerts</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Deterministic alerts raised by the evidence engine — threshold
            breaches, data quality issues, and missing instrumentation.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {generateResult && (
            <span className="font-mono text-2xs text-text-muted">
              +{generateResult.created} created · {generateResult.skipped} skipped
            </span>
          )}
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="rounded border border-accent-600 bg-accent-900/30 px-3 py-1.5 font-mono text-xs text-accent-300 hover:bg-accent-900/50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {generating ? "Generating…" : "Run alert check"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded border border-red-800 bg-red-900/20 px-4 py-3 font-mono text-xs text-red-300">
          {error}
        </div>
      )}

      {/* Evidence quality banner */}
      {!loading && evidenceQualityCount > 0 && (
        <div className="rounded border border-accent-700/40 bg-accent-900/20 px-4 py-2 font-mono text-2xs text-accent-400">
          {evidenceQualityCount} evidence quality alert{evidenceQualityCount !== 1 ? "s" : ""}. Run evidence checks on Strategy Detail pages.
        </div>
      )}

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-4 rounded-card border border-border bg-bg-700 px-4 py-3">
        <FilterSelect
          label="Status"
          value={status}
          options={STATUS_OPTIONS}
          onChange={(v) => setStatus(v)}
        />
        <FilterSelect
          label="Severity"
          value={severity}
          options={SEVERITY_OPTIONS}
          onChange={(v) => setSeverity(v)}
        />
        <FilterSelect
          label="Rule"
          value={ruleType}
          options={RULE_TYPE_OPTIONS}
          onChange={(v) => setRuleType(v)}
        />
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
            {!status && !severity && !ruleType && (
              <p className="mt-2 font-mono text-2xs text-text-muted/60">
                Run an alert check to generate alerts from existing evidence.
              </p>
            )}
          </div>
        ) : (
          <div className="px-4">
            {items.map((alert) => (
              <AlertRow
                key={alert.id}
                alert={alert}
                onStatusChange={handleStatusChange}
              />
            ))}
          </div>
        )}

        {/* Load more footer */}
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
    </div>
  );
}
