import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { TimelineEvent, TimelineFilters, TimelineListResponse } from "@/types";
import { getTimeline } from "@/lib/api";

// ---------------------------------------------------------------------------
// Visual helpers
// ---------------------------------------------------------------------------

/** Coloured dot reflecting event severity. */
function SeverityDot({ severity }: { severity: string }) {
  const palette: Record<string, string> = {
    info: "bg-bg-600 border border-border",
    low: "bg-blue-400",
    medium: "bg-yellow-400",
    high: "bg-orange-400",
    critical: "bg-red-500",
  };
  return (
    <span
      className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${palette[severity] ?? "bg-bg-600"}`}
    />
  );
}

/** Badge for event_type — each type gets a distinct accent. */
function EventTypeBadge({ type }: { type: string }) {
  const palette: Record<string, string> = {
    strategy_created:
      "bg-teal-900/40 text-teal-300 border-teal-700/40",
    strategy_run_logged:
      "bg-blue-900/40 text-blue-300 border-blue-700/40",
    backtest_run_logged:
      "bg-blue-900/40 text-blue-300 border-blue-700/40",
    dataset_snapshot_uploaded:
      "bg-violet-900/40 text-violet-300 border-violet-700/40",
    backtest_audited:
      "bg-orange-900/40 text-orange-300 border-orange-700/40",
  };
  const style =
    palette[type] ?? "bg-bg-600 text-text-muted border-border";
  const label = type.replace(/_/g, " ");
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 font-mono text-2xs leading-none ${style}`}
    >
      {label}
    </span>
  );
}

/** Human-readable source type chip. */
function SourceChip({ sourceType }: { sourceType: string | null }) {
  if (!sourceType) return null;
  const labels: Record<string, string> = {
    strategy: "Strategy",
    strategy_run: "Run",
    dataset_snapshot: "Data Snapshot",
    backtest_audit: "Backtest Audit",
  };
  return (
    <span className="font-mono text-2xs text-text-muted">
      {labels[sourceType] ?? sourceType}
    </span>
  );
}

/** Format an ISO timestamp as a short readable string. */
function fmtEventTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** Extract a short score string from metadata if available. */
function metadataScore(ev: TimelineEvent): string | null {
  const m = ev.metadata_json;
  if (!m) return null;
  if (typeof m.trust_score === "number") return `trust ${m.trust_score}/100`;
  if (typeof m.health_score === "number") return `health ${m.health_score}/100`;
  if (typeof m.sharpe === "number") return `Sharpe ${m.sharpe}`;
  return null;
}

// ---------------------------------------------------------------------------
// One event row
// ---------------------------------------------------------------------------

function EventRow({ ev }: { ev: TimelineEvent }) {
  const [expanded, setExpanded] = useState(false);
  const score = metadataScore(ev);

  return (
    <div className="group flex gap-3 border-b border-border py-3 last:border-0">
      {/* Severity dot */}
      <SeverityDot severity={ev.severity} />

      {/* Content */}
      <div className="min-w-0 flex-1">
        {/* Primary line */}
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
          <div className="flex flex-wrap items-center gap-2 min-w-0">
            <EventTypeBadge type={ev.event_type} />
            <span className="text-sm text-text-primary leading-snug">
              {ev.title}
            </span>
          </div>
          <span className="shrink-0 font-mono text-2xs text-text-muted whitespace-nowrap">
            {fmtEventTime(ev.event_time)}
          </span>
        </div>

        {/* Secondary line */}
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5">
          <SourceChip sourceType={ev.source_type} />
          {score && (
            <span className="font-mono text-2xs text-text-secondary">{score}</span>
          )}
          {ev.description && !expanded && (
            <button
              onClick={() => setExpanded(true)}
              className="font-mono text-2xs text-text-muted/60 hover:text-text-muted"
            >
              details ▼
            </button>
          )}
          {ev.description && expanded && (
            <button
              onClick={() => setExpanded(false)}
              className="font-mono text-2xs text-text-muted/60 hover:text-text-muted"
            >
              ▲
            </button>
          )}
        </div>

        {/* Expanded description */}
        {expanded && ev.description && (
          <p className="mt-1.5 text-xs text-text-secondary leading-relaxed">
            {ev.description}
          </p>
        )}

        {/* Source id in mono — compact, only shown when expanded */}
        {expanded && ev.source_id && (
          <p className="mt-1 font-mono text-2xs text-text-muted/50 truncate">
            src: {ev.source_id}
          </p>
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

const SOURCE_TYPE_OPTIONS = [
  { value: "", label: "All sources" },
  { value: "strategy", label: "Strategy" },
  { value: "strategy_run", label: "Run" },
  { value: "dataset_snapshot", label: "Data Snapshot" },
  { value: "backtest_audit", label: "Backtest Audit" },
];

const SEVERITY_OPTIONS = [
  { value: "", label: "All severities" },
  { value: "info", label: "Info" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "critical", label: "Critical" },
];

const EVENT_TYPE_OPTIONS = [
  { value: "", label: "All types" },
  { value: "strategy_created", label: "strategy_created" },
  { value: "strategy_run_logged", label: "strategy_run_logged" },
  { value: "dataset_snapshot_uploaded", label: "dataset_snapshot_uploaded" },
  { value: "backtest_audited", label: "backtest_audited" },
];

export default function Timeline() {
  const [searchParams] = useSearchParams();

  // Initialise filters from URL query params (e.g. linked from StrategyDetail).
  const [sourceType, setSourceType] = useState(
    searchParams.get("source_type") ?? "",
  );
  const [severity, setSeverity] = useState(
    searchParams.get("severity") ?? "",
  );
  const [eventType, setEventType] = useState(
    searchParams.get("event_type") ?? "",
  );

  const [response, setResponse] = useState<TimelineListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Keep a stable list of items that survives "load more" appends.
  const [items, setItems] = useState<TimelineEvent[]>([]);

  // When any filter changes, reset and reload from offset 0.
  const filtersRef = useRef({ sourceType, severity, eventType });
  filtersRef.current = { sourceType, severity, eventType };

  function buildFilters(offset = 0): TimelineFilters {
    const f: TimelineFilters = { limit: PAGE_SIZE, offset };
    if (sourceType) f.source_type = sourceType;
    if (severity) f.severity = severity;
    if (eventType) f.event_type = eventType;
    return f;
  }

  useEffect(() => {
    setLoading(true);
    setError(null);
    getTimeline(buildFilters(0))
      .then((resp) => {
        setResponse(resp);
        setItems(resp.items);
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Failed to load"),
      )
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceType, severity, eventType]);

  function handleLoadMore() {
    if (!response) return;
    const nextOffset = items.length;
    setLoadingMore(true);
    getTimeline(buildFilters(nextOffset))
      .then((resp) => {
        setResponse(resp);
        setItems((prev) => [...prev, ...resp.items]);
      })
      .catch(() => {})
      .finally(() => setLoadingMore(false));
  }

  const hasMore =
    response !== null && items.length < response.total;

  return (
    <div className="space-y-5">
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                              */}
      {/* ------------------------------------------------------------------ */}
      <div>
        <p className="caption mb-1">Evidence Stream</p>
        <h1 className="text-xl font-semibold text-text-primary">Audit Trail</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Chronological evidence log of every strategy registration, run, data
          snapshot, and backtest audit.
        </p>
      </div>

      {error && (
        <div className="rounded border border-red-800 bg-red-900/20 px-4 py-3 font-mono text-xs text-red-300">
          {error}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Filter bar                                                          */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex flex-wrap items-center gap-4 rounded-card border border-border bg-bg-700 px-4 py-3">
        <FilterSelect
          label="Source"
          value={sourceType}
          options={SOURCE_TYPE_OPTIONS}
          onChange={(v) => setSourceType(v)}
        />
        <FilterSelect
          label="Severity"
          value={severity}
          options={SEVERITY_OPTIONS}
          onChange={(v) => setSeverity(v)}
        />
        <FilterSelect
          label="Type"
          value={eventType}
          options={EVENT_TYPE_OPTIONS}
          onChange={(v) => setEventType(v)}
        />
        <span className="ml-auto font-mono text-2xs text-text-muted">
          {response ? `${response.total.toLocaleString()} event${response.total !== 1 ? "s" : ""}` : "…"}
        </span>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Event stream                                                        */}
      {/* ------------------------------------------------------------------ */}
      <div className="rounded-card border border-border bg-bg-700">
        {loading ? (
          <div className="px-4 py-10 text-center">
            <p className="font-mono text-2xs text-text-muted">Loading…</p>
          </div>
        ) : items.length === 0 ? (
          <div className="px-4 py-10 text-center">
            <p className="font-mono text-2xs text-text-muted">
              No events match the selected filters.
            </p>
          </div>
        ) : (
          <div className="px-4">
            {items.map((ev) => (
              <EventRow key={ev.id} ev={ev} />
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
