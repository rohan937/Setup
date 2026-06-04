import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import PageHeader from "@/components/PageHeader";
import StrategyLifecycleBar from "@/components/StrategyLifecycleBar";
import { getStrategies, getStrategyActionQueue, getStrategyLifecycle } from "@/lib/api";
import type {
  ActionItem,
  ActionQueueResponse,
  LifecycleBlocker,
  StrategyLifecycleResponse,
  Strategy,
} from "@/types";

// ---------------------------------------------------------------------------
// Action presentation helpers
// ---------------------------------------------------------------------------

const SEV_CHIP: Record<string, string> = {
  critical: "border-fidelity-low/40 bg-fidelity-low/10 text-fidelity-low",
  high: "border-fidelity-low/30 bg-fidelity-low/5 text-fidelity-low",
  medium: "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
  low: "border-border-strong bg-bg-800 text-text-secondary",
  info: "border-border bg-bg-800 text-text-muted",
};

const SEV_LABEL: Record<string, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  info: "Info",
};

const STATUS_CHIP: Record<string, string> = {
  blocked: "border-fidelity-low/40 bg-fidelity-low/10 text-fidelity-low",
  pending: "border-accent-500/30 bg-accent-500/10 text-accent-300",
  optional: "border-border bg-bg-800 text-text-muted",
  done: "border-fidelity-high/30 bg-fidelity-high/10 text-fidelity-high",
};

function prettify(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ---------------------------------------------------------------------------
// Grouping — operating console view
// ---------------------------------------------------------------------------

type GroupKey = "blockers" | "evidence" | "governance" | "reporting";

const GROUP_META: { key: GroupKey; label: string; hint: string }[] = [
  { key: "blockers", label: "Immediate blockers", hint: "Resolve these to unblock progression" },
  { key: "evidence", label: "Evidence fixes", hint: "Strengthen the underlying evidence" },
  { key: "governance", label: "Governance setup", hint: "Guardrails, tests, and readiness" },
  { key: "reporting", label: "Reporting & export", hint: "Package evidence for review" },
];

function groupOf(item: ActionItem): GroupKey {
  if (item.status === "blocked" || item.severity === "critical" || item.severity === "high") {
    return "blockers";
  }
  if (item.category === "reporting") return "reporting";
  if (item.category === "governance" || item.category === "readiness") return "governance";
  return "evidence";
}

function groupItems(items: ActionItem[]): Record<GroupKey, ActionItem[]> {
  const out: Record<GroupKey, ActionItem[]> = {
    blockers: [],
    evidence: [],
    governance: [],
    reporting: [],
  };
  for (const item of items) out[groupOf(item)].push(item);
  return out;
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function CommandCenter() {
  const [strategies, setStrategies] = useState<Strategy[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [queue, setQueue] = useState<ActionQueueResponse | null>(null);
  const [queueLoading, setQueueLoading] = useState(false);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [lifecycle, setLifecycle] = useState<StrategyLifecycleResponse | null>(null);

  useEffect(() => {
    getStrategies()
      .then((data) => {
        setStrategies(data);
        if (data.length > 0) setSelectedId(data[0].id);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setQueue(null);
      setLifecycle(null);
      return;
    }
    setQueueLoading(true);
    setQueueError(null);
    getStrategyActionQueue(selectedId, 25)
      .then((q) => {
        setQueue(q);
        setQueueLoading(false);
      })
      .catch((err) => {
        setQueueError(err instanceof Error ? err.message : String(err));
        setQueue(null);
        setQueueLoading(false);
      });
    // M76: lifecycle visual for the selected strategy (best-effort).
    getStrategyLifecycle(selectedId).then(setLifecycle).catch(() => setLifecycle(null));
  }, [selectedId]);

  const grouped = useMemo(
    () => (queue ? groupItems(queue.items) : null),
    [queue],
  );

  const navigate = useNavigate();

  // M76: a lifecycle blocker deep-links into the strategy (repair flows live there).
  function handleLifecycleBlocker(b: LifecycleBlocker) {
    if (!selectedId) return;
    const tab = b.target_tab ? `?tab=${b.target_tab}` : "";
    navigate(`/strategies/${selectedId}${tab}`);
  }

  return (
    <div className="flex flex-col gap-4 px-6 py-6 max-w-4xl mx-auto">
      <PageHeader
        title="Reliability Command Center"
        subtitle="The operating console for what to fix next, across every strategy"
      />

      {/* Strategy selector */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3 flex flex-wrap items-center gap-3">
        <label className="caption" htmlFor="cc-strategy">
          Strategy
        </label>
        {loading ? (
          <span className="text-sm text-text-muted animate-pulse">Loading strategies…</span>
        ) : error ? (
          <span className="text-sm text-amber-400">Could not load strategies: {error}</span>
        ) : strategies && strategies.length > 0 ? (
          <>
            <select
              id="cc-strategy"
              value={selectedId ?? ""}
              onChange={(e) => setSelectedId(e.target.value)}
              className="rounded-control border border-border bg-bg-800 px-2.5 py-1 text-sm text-text-primary focus:border-accent-500/50 focus:outline-none"
            >
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            {selectedId && (
              <Link
                to={`/strategies/${selectedId}`}
                className="ml-auto text-xs border border-border bg-bg-600 text-text-secondary hover:text-accent-500 hover:border-accent-500/40 rounded-control px-2.5 py-1 transition-colors"
              >
                Open strategy →
              </Link>
            )}
          </>
        ) : (
          <span className="text-sm text-text-secondary">
            No strategies yet.{" "}
            <Link to="/strategies" className="text-accent-500 hover:text-accent-300">
              Create your first strategy →
            </Link>
          </span>
        )}
      </div>

      {/* M76: lifecycle visual for the selected strategy */}
      {lifecycle && (
        <StrategyLifecycleBar
          data={lifecycle}
          onBlockerAction={handleLifecycleBlocker}
          compact
        />
      )}

      {/* Summary strip */}
      {queue && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <SummaryStat label="Total actions" value={queue.total_action_count} />
          <SummaryStat label="Blocking" value={queue.blocked_count} tone="danger" />
          <SummaryStat label="Pending" value={queue.pending_count} tone="accent" />
          <SummaryStat label="Optional" value={queue.optional_count} />
        </div>
      )}

      {queue && (
        <p className="text-sm text-text-secondary">{queue.deterministic_summary}</p>
      )}

      {/* Queue states */}
      {queueLoading && (
        <div className="rounded-card border border-border bg-bg-700 px-4 py-6">
          <p className="text-sm text-text-muted animate-pulse">Loading action queue…</p>
        </div>
      )}

      {queueError && !queueLoading && (
        <div className="rounded-card border border-border bg-bg-700 px-4 py-4">
          <p className="text-sm text-amber-400">
            Could not load the action queue: {queueError}
          </p>
        </div>
      )}

      {grouped && !queueLoading && queue && queue.items.length === 0 && (
        <div className="rounded-card border border-border bg-bg-700 px-4 py-6">
          <p className="text-sm text-fidelity-high">
            No outstanding actions — the core evidence looks complete.
          </p>
        </div>
      )}

      {/* Grouped queue */}
      {grouped && !queueLoading && queue && queue.items.length > 0 && (
        <div className="flex flex-col gap-3">
          {GROUP_META.map((g) => {
            const items = grouped[g.key];
            if (items.length === 0) return null;
            return (
              <div key={g.key} className="rounded-card border border-border bg-bg-700">
                <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
                  <div>
                    <p className="text-sm font-medium text-text-primary">{g.label}</p>
                    <p className="text-2xs text-text-muted">{g.hint}</p>
                  </div>
                  <span className="rounded-chip border border-border-strong bg-bg-800 px-2 py-0.5 font-mono text-2xs text-text-secondary">
                    {items.length}
                  </span>
                </div>
                <div className="divide-y divide-border">
                  {items.map((item) => (
                    <ActionRow
                      key={item.id}
                      item={item}
                      strategyId={selectedId}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Disclaimer */}
      {queue && (
        <p className="text-2xs text-text-muted pb-2">{queue.disclaimer}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SummaryStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "danger" | "accent";
}) {
  const valueColor =
    tone === "danger" && value > 0
      ? "text-fidelity-low"
      : tone === "accent" && value > 0
        ? "text-accent-300"
        : "text-text-primary";
  return (
    <div className="rounded-card border border-border bg-bg-700 px-3 py-2.5">
      <p className="caption mb-0.5">{label}</p>
      <p className={`text-lg font-semibold ${valueColor}`}>{value}</p>
    </div>
  );
}

function ActionRow({
  item,
  strategyId,
}: {
  item: ActionItem;
  strategyId: string | null;
}) {
  return (
    <div className="flex items-start gap-3 px-4 py-3">
      <span className="mt-0.5 w-5 shrink-0 text-right font-mono text-2xs text-text-muted">
        {item.priority_rank}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-sm text-text-primary">{item.title}</span>
          <span
            className={`rounded-chip border px-1.5 py-px text-2xs ${SEV_CHIP[item.severity] ?? SEV_CHIP.info}`}
          >
            {SEV_LABEL[item.severity] ?? item.severity}
          </span>
          <span
            className={`rounded-chip border px-1.5 py-px text-2xs ${STATUS_CHIP[item.status] ?? STATUS_CHIP.pending}`}
          >
            {prettify(item.status)}
          </span>
        </div>
        <p className="mt-0.5 text-xs leading-relaxed text-text-secondary">
          {item.why_it_matters}
        </p>
        <p className="mt-1 text-2xs text-text-muted">
          {prettify(item.category)} · {prettify(item.source)}
        </p>
      </div>
      {strategyId && (
        <Link
          to={`/strategies/${strategyId}${item.target_tab ? `?tab=${item.target_tab}` : ""}`}
          className="shrink-0 rounded-control border border-border px-2.5 py-1 text-2xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
        >
          {item.action_label}
        </Link>
      )}
    </div>
  );
}
