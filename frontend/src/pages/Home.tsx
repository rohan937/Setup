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
import PageHeader from "@/components/PageHeader";
import Card from "@/components/Card";
import EmptyState from "@/components/EmptyState";
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

  function metricColor(value: number, tone: string): string {
    if (value <= 0) return "text-text-primary";
    switch (tone) {
      case "low":
        return "text-fidelity-low";
      case "medium":
        return "text-fidelity-medium";
      case "high":
        return "text-fidelity-high";
      case "accent":
        return "text-accent-300";
      default:
        return "text-text-primary";
    }
  }

  return (
    <div className="space-y-10">
      <NoWorkspaceNotice />

      {/* 1. Command-center header */}
      <PageHeader
        tag="Research Command Center"
        title={`Welcome back, ${userName}`}
        subtitle="Your research reliability workspace — monitor evidence health, triage the highest-priority actions, and keep every strategy promotion-ready."
      >
        <div className="flex flex-col items-end gap-2 text-xs text-text-muted">
          <span className="flex items-center gap-1.5">
            <span className="caption">Workspace</span>
            <span className="text-text-secondary">{workspaceName}</span>
          </span>
          <div className="flex items-center gap-2">
            <span
              className={`rounded border px-1.5 py-0.5 font-mono font-semibold ${roleBadgeClasses(auth.role)}`}
            >
              {auth.role ?? (auth.isAuthenticated ? "—" : "local")}
            </span>
            <span className="rounded-chip border border-border-strong bg-bg-800 px-2 py-0.5 font-mono uppercase tracking-eyebrow text-text-secondary">
              {env}
            </span>
          </div>
        </div>
      </PageHeader>

      {/* 2. Workspace snapshot — hero metrics */}
      <section className="space-y-4">
        <h2 className="section-title">Workspace snapshot</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {snapshot.map((c) => (
            <div
              key={c.label}
              className="card-interactive rounded-card border border-border bg-bg-700 p-5 shadow-card"
            >
              <p className={`metric-value text-metric-sm ${metricColor(c.value, c.tone)}`}>
                {loading ? "…" : c.value}
              </p>
              <p className="caption mt-2">{c.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 3. Today — recommended actions + guided demo */}
      <section className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <h2 className="section-title">Today</h2>
          <Link to="/command-center" className="text-sm text-accent-500 hover:text-accent-300">
            Command Center →
          </Link>
        </div>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Recommended actions */}
          <div className="lg:col-span-2 card-interactive flex flex-col rounded-card border border-border bg-bg-700 shadow-card">
            <div className="border-b border-border px-6 py-4">
              <p className="card-title">Recommended actions</p>
              <p className="mt-1 text-sm text-text-secondary">
                Prioritized by severity across your active strategies.
              </p>
            </div>
            <div className="flex-1 divide-y divide-border">
              {loading ? (
                <p className="px-6 py-8 text-sm text-text-muted animate-pulse">Loading actions…</p>
              ) : actions.length === 0 ? (
                <div className="px-6 py-8">
                  <EmptyState
                    title="All clear"
                    description="Nothing urgent — the core evidence looks healthy across your strategies."
                  />
                </div>
              ) : (
                actions.map((a) => (
                  <button
                    key={`${a.strategyId}:${a.item.id}`}
                    onClick={() => openStrategy(a.strategyId, a.item.target_tab)}
                    className="flex w-full items-start gap-3 px-6 py-3.5 text-left transition-colors hover:bg-bg-700/50"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm text-text-primary">{a.item.title}</span>
                        <span
                          className={`rounded-chip border px-1.5 py-px text-2xs ${SEV_CHIP[a.item.severity] ?? SEV_CHIP.info}`}
                        >
                          {a.item.severity}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-text-secondary">{a.item.why_it_matters}</p>
                      <p className="mt-1 text-2xs text-text-muted">{a.strategyName}</p>
                    </div>
                    <span className="shrink-0 text-2xs text-text-muted">{a.item.action_label} →</span>
                  </button>
                ))
              )}
            </div>
            <p className="border-t border-border px-6 py-3 text-2xs text-text-muted">
              Recommended actions prioritize research evidence tasks. They are not trading
              recommendations.
            </p>
          </div>

          {/* Guided demo card */}
          <div className="card-interactive flex flex-col rounded-card border border-accent-500/30 bg-accent-500/5 shadow-card">
            <div className="border-b border-border px-6 py-4">
              <p className="caption mb-1">Guided demo</p>
              <p className="card-title">Learn the product in 6 steps</p>
            </div>
            <div className="flex-1 space-y-3 px-6 py-5">
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
                  <p className="text-sm text-text-secondary">
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
      </section>

      {/* 4. Strategy status summary */}
      <section className="space-y-4">
        <h2 className="section-title">Strategies</h2>
        <div className="card-interactive rounded-card border border-border bg-bg-700 shadow-card">
          <div className="border-b border-border px-6 py-4">
            <p className="card-title">Status summary</p>
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
                    className="flex w-full items-center gap-3 px-6 py-3 text-left transition-colors hover:bg-bg-700/50 disabled:cursor-default disabled:hover:bg-transparent"
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
            <div className="px-6 py-6">
              {strategies.length === 0 ? (
                <EmptyState
                  title="No strategies yet"
                  description="Create your first strategy or load the clean realistic demo to get started."
                  action={{ label: "Create Strategy", to: "/strategies" }}
                />
              ) : (
                <p className="text-sm text-text-secondary">
                  {portfolio?.deterministic_summary ??
                    `${strategies.length} strateg${strategies.length === 1 ? "y" : "ies"} in this workspace.`}
                </p>
              )}
            </div>
          )}
        </div>
      </section>

      {/* 5. Quick actions */}
      <section className="space-y-4">
        <h2 className="section-title">Quick actions</h2>
        <Card>
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
        </Card>
      </section>
    </div>
  );
}
