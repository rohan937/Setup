import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { ActionItem, PortfolioOverview, Strategy } from "@/types";
import {
  getPortfolioOverview,
  getStrategies,
  getStrategyActionQueue,
  getFrontendEnvironment,
} from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import NoWorkspaceNotice from "@/components/NoWorkspaceNotice";
import { canSeedDemo, roleBadgeClasses } from "@/lib/permissions";
import {
  startWalkthrough,
  hasDemoStrategies,
  findDemoStrategyId,
  loadWalkthroughState,
  DEMO_STRATEGY_NAMES,
} from "@/lib/demoWalkthrough";

// ---------------------------------------------------------------------------
// Severity helpers
// ---------------------------------------------------------------------------

const SEV_RANK: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

const SEV_CHIP: Record<string, string> = {
  critical: "border-fidelity-low/40 bg-fidelity-low/10 text-fidelity-low",
  high: "border-fidelity-low/30 bg-fidelity-low/5 text-fidelity-low",
  medium: "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
  low: "border-border-strong bg-bg-800 text-text-secondary",
  info: "border-border bg-bg-800 text-text-muted",
};

interface HomeAction {
  strategyId: string;
  strategyName: string;
  item: ActionItem;
}

const DEMO_ROLES: { key: keyof typeof DEMO_STRATEGY_NAMES; role: string; meaning: string }[] = [
  { key: "aapl", role: "Healthy", meaning: "well-instrumented; high coverage and trust" },
  { key: "fxCarry", role: "Review", meaning: "decent research but stale / incomplete evidence" },
  { key: "crypto", role: "Blocked", meaning: "attractive headline metrics, weak assumptions" },
  { key: "mayaKoPep", role: "Improving", meaning: "better than v1, but not promotion-clean yet" },
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function Home() {
  const auth = useAuth();
  const navigate = useNavigate();

  const [portfolio, setPortfolio] = useState<PortfolioOverview | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [actions, setActions] = useState<HomeAction[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [loading, setLoading] = useState(true);

  const env = getFrontendEnvironment();
  const workspaceName =
    auth.memberships.find((m) => m.organization_id === auth.organizationId)?.workspace_name ??
    auth.memberships[0]?.workspace_name ??
    "Your workspace";
  const userName = auth.user?.display_name ?? auth.user?.email ?? "Researcher";
  const demoReady = hasDemoStrategies(strategies);
  const walkState = loadWalkthroughState();
  const canDemoReset = canSeedDemo(auth);

  useEffect(() => {
    getPortfolioOverview({ limit_per_section: 10 }).then(setPortfolio).catch(() => setPortfolio(null));
    getStrategies("active")
      .then((list) => {
        setStrategies(list);
        // Aggregate top action-queue items across a capped sample of strategies.
        const sample = list.slice(0, 6);
        return Promise.all(
          sample.map((s) =>
            getStrategyActionQueue(s.id, 5)
              .then((q) => ({ s, q }))
              .catch(() => null),
          ),
        );
      })
      .then((results) => {
        if (!results) return;
        const acts: HomeAction[] = [];
        let pending = 0;
        for (const r of results) {
          if (!r) continue;
          pending += r.q.pending_count + r.q.blocked_count;
          for (const item of r.q.items) {
            acts.push({ strategyId: r.s.id, strategyName: r.s.name, item });
          }
        }
        acts.sort(
          (a, b) =>
            (SEV_RANK[a.item.severity] ?? 9) - (SEV_RANK[b.item.severity] ?? 9) ||
            a.item.priority_rank - b.item.priority_rank,
        );
        setActions(acts.slice(0, 6));
        setPendingCount(pending);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const health = portfolio?.strategies_by_health_status ?? {};
  const snapshot = useMemo(
    () => [
      { label: "Strategies", value: portfolio?.strategy_count ?? strategies.length, tone: "" },
      { label: "Healthy", value: health.healthy ?? 0, tone: "high" },
      { label: "Review", value: (health.review ?? 0) + (health.watch ?? 0), tone: "medium" },
      { label: "Blocked / Critical", value: health.critical ?? 0, tone: "low" },
      { label: "Open alerts", value: portfolio?.open_alert_count ?? 0, tone: "medium" },
      { label: "Pending actions", value: pendingCount, tone: "accent" },
    ],
    [portfolio, strategies.length, health, pendingCount],
  );

  function openStrategy(strategyId: string, tab?: string | null) {
    navigate(`/strategies/${strategyId}${tab ? `?tab=${tab}` : ""}`);
  }

  return (
    <div className="flex flex-col gap-5">
      <NoWorkspaceNotice />
      {/* 1. Welcome header */}
      <div className="rounded-card border border-border bg-bg-700 px-5 py-5 shadow-card">
        <p className="caption mb-1">Workbench</p>
        <h1 className="text-xl font-semibold text-text-primary">Welcome to QuantFidelity</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Your research reliability workspace is ready.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-text-muted">
          <span>
            Workspace: <span className="text-text-secondary">{workspaceName}</span>
          </span>
          <span>
            Signed in as: <span className="text-text-secondary">{userName}</span>
          </span>
          <span className="flex items-center gap-1.5">
            Role:
            <span
              className={`rounded border px-1.5 py-0.5 font-mono font-semibold ${roleBadgeClasses(auth.role)}`}
            >
              {auth.role ?? (auth.isAuthenticated ? "—" : "local")}
            </span>
          </span>
          <span className="rounded-chip border border-border-strong bg-bg-800 px-2 py-0.5 font-mono uppercase tracking-eyebrow text-text-secondary">
            {env}
          </span>
        </div>
      </div>

      {/* 2. Workspace snapshot */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {snapshot.map((c) => (
          <div key={c.label} className="rounded-card border border-border bg-bg-700 px-3 py-2.5">
            <p className="caption mb-0.5">{c.label}</p>
            <p
              className={`text-lg font-semibold ${
                c.value > 0 && c.tone === "low"
                  ? "text-fidelity-low"
                  : c.value > 0 && c.tone === "medium"
                    ? "text-fidelity-medium"
                    : c.value > 0 && c.tone === "high"
                      ? "text-fidelity-high"
                      : c.value > 0 && c.tone === "accent"
                        ? "text-accent-300"
                        : "text-text-primary"
              }`}
            >
              {loading ? "…" : c.value}
            </p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* 3. Today's recommended actions */}
        <div className="lg:col-span-2 rounded-card border border-border bg-bg-700 shadow-card">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div>
              <p className="caption mb-0.5">Today</p>
              <p className="text-sm font-medium text-text-primary">Recommended actions</p>
            </div>
            <Link to="/command-center" className="text-xs text-accent-500 hover:text-accent-300">
              Command Center →
            </Link>
          </div>
          <div className="divide-y divide-border">
            {loading ? (
              <p className="px-4 py-6 text-sm text-text-muted animate-pulse">Loading actions…</p>
            ) : actions.length === 0 ? (
              <p className="px-4 py-6 text-sm text-fidelity-high">
                Nothing urgent — the core evidence looks healthy across your strategies.
              </p>
            ) : (
              actions.map((a) => (
                <button
                  key={`${a.strategyId}:${a.item.id}`}
                  onClick={() => openStrategy(a.strategyId, a.item.target_tab)}
                  className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-bg-600/30 transition-colors"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-sm text-text-primary">{a.item.title}</span>
                      <span
                        className={`rounded-chip border px-1.5 py-px text-2xs ${SEV_CHIP[a.item.severity] ?? SEV_CHIP.info}`}
                      >
                        {a.item.severity}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-text-secondary">{a.item.why_it_matters}</p>
                    <p className="mt-1 text-2xs text-text-muted">{a.strategyName}</p>
                  </div>
                  <span className="shrink-0 text-2xs text-text-muted">{a.item.action_label} →</span>
                </button>
              ))
            )}
          </div>
          <p className="border-t border-border px-4 py-2 text-2xs text-text-muted">
            Recommended actions prioritize research evidence tasks. They are not trading
            recommendations.
          </p>
        </div>

        {/* 4. Guided demo card */}
        <div className="rounded-card border border-accent-500/30 bg-accent-500/5 shadow-card">
          <div className="border-b border-border px-4 py-3">
            <p className="caption mb-0.5">Guided demo</p>
            <p className="text-sm font-medium text-text-primary">Learn the product in 6 steps</p>
          </div>
          <div className="space-y-2 px-4 py-4">
            {demoReady ? (
              <>
                <button
                  onClick={() => startWalkthrough(true)}
                  className="w-full rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-2 text-sm text-accent-200 hover:bg-accent-500/25"
                >
                  {walkState.lastStep > 1 && !walkState.completed
                    ? "Continue walkthrough"
                    : "Start guided demo"}
                </button>
                <button
                  onClick={() => startWalkthrough(true)}
                  className="w-full rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
                >
                  Restart walkthrough
                </button>
                <p className="text-2xs text-text-muted">
                  A tour of the clean realistic demo: Dashboard → Portfolio → the strategies.
                </p>
              </>
            ) : (
              <>
                <p className="text-xs text-text-secondary">
                  The guided demo needs the clean realistic demo data.
                </p>
                <Link
                  to="/admin/demo-controls"
                  className="inline-block rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-1.5 text-xs text-accent-200 hover:bg-accent-500/25"
                >
                  Open Demo Controls
                </Link>
              </>
            )}
          </div>
        </div>
      </div>

      {/* 5. Strategy status summary */}
      <div className="rounded-card border border-border bg-bg-700 shadow-card">
        <div className="border-b border-border px-4 py-3">
          <p className="caption mb-0.5">Strategies</p>
          <p className="text-sm font-medium text-text-primary">Status summary</p>
        </div>
        {demoReady ? (
          <div className="divide-y divide-border">
            {DEMO_ROLES.map((d) => {
              const sid = findDemoStrategyId(strategies, d.key);
              const name = DEMO_STRATEGY_NAMES[d.key];
              return (
                <button
                  key={d.key}
                  onClick={() => sid && openStrategy(sid)}
                  disabled={!sid}
                  className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-bg-600/30 transition-colors disabled:cursor-default"
                >
                  <span className="w-20 shrink-0 text-2xs uppercase tracking-eyebrow text-text-muted">
                    {d.role}
                  </span>
                  <span className="shrink-0 text-sm text-text-primary">{name}</span>
                  <span className="min-w-0 flex-1 truncate text-xs text-text-secondary">
                    {d.meaning}
                  </span>
                  {sid && <span className="shrink-0 text-2xs text-text-muted">Open →</span>}
                </button>
              );
            })}
          </div>
        ) : (
          <div className="px-4 py-4">
            {strategies.length === 0 ? (
              <p className="text-sm text-text-secondary">
                No strategies yet. Create your first strategy or load the clean realistic demo to
                get started.
              </p>
            ) : (
              <p className="text-sm text-text-secondary">
                {portfolio?.deterministic_summary ??
                  `${strategies.length} strateg${strategies.length === 1 ? "y" : "ies"} in this workspace.`}
              </p>
            )}
          </div>
        )}
      </div>

      {/* 6. Quick actions */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-4 shadow-card">
        <p className="caption mb-2">Quick actions</p>
        <div className="flex flex-wrap gap-2">
          <Link
            to="/strategies"
            className="rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-1.5 text-xs text-accent-200 hover:bg-accent-500/25"
          >
            Create Strategy
          </Link>
          <Link
            to="/developer/evidence-bundles"
            className="rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            Upload Evidence Bundle
          </Link>
          <Link
            to="/command-center"
            className="rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            Open Command Center
          </Link>
          <button
            onClick={() => startWalkthrough(true)}
            className="rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            Start Guided Demo
          </button>
          {canDemoReset && (
            <Link
              to="/admin/demo-controls"
              className="rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
            >
              Run Demo Reset
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
