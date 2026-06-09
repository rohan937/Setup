import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type {
  CommandCenterResponse,
  CommandCenterTopAction,
  CommandCenterAttentionStrategy,
  CommandCenterPendingReview,
  CommandCenterAlert,
  CommandCenterLifecycleStage,
  Strategy,
} from "@/types";
import {
  getCommandCenter,
  getStrategies,
  getFrontendEnvironment,
} from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import NoWorkspaceNotice from "@/components/NoWorkspaceNotice";
import PageHeader from "@/components/PageHeader";
import Card from "@/components/Card";
import EmptyState from "@/components/EmptyState";
import LifecycleStageBadge from "@/components/LifecycleStageBadge";
import { Skeleton, SkeletonText } from "@/components/Skeleton";
import { canSeedDemo, roleBadgeClasses } from "@/lib/permissions";
import {
  startWalkthrough,
  hasDemoStrategies,
  findDemoStrategyId,
  loadWalkthroughState,
  DEMO_STRATEGY_NAMES,
} from "@/lib/demoWalkthrough";

// ---------------------------------------------------------------------------
// Severity / health helpers (M102 tokens)
// ---------------------------------------------------------------------------

const SEV_CHIP: Record<string, string> = {
  critical: "border-fidelity-low/40 bg-fidelity-low/10 text-fidelity-low",
  high: "border-fidelity-low/30 bg-fidelity-low/5 text-fidelity-low",
  medium: "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
  low: "border-border-strong bg-bg-800 text-text-secondary",
  info: "border-border bg-bg-800 text-text-muted",
};

function sevChip(severity: string | null | undefined): string {
  const key = (severity ?? "").toLowerCase();
  return SEV_CHIP[key] ?? SEV_CHIP.info;
}

// Subtle severity-colored left edge for action rows (M108). Calm by default;
// red/amber edge only for the rows that actually carry urgency.
const SEV_EDGE: Record<string, string> = {
  critical: "border-l-2 border-l-fidelity-low",
  high: "border-l-2 border-l-fidelity-low",
  medium: "border-l-2 border-l-fidelity-medium",
  low: "border-l-2 border-l-border-strong",
  info: "border-l-2 border-l-transparent",
};

function sevEdge(severity: string | null | undefined): string {
  const key = (severity ?? "").toLowerCase();
  return SEV_EDGE[key] ?? "border-l-2 border-l-transparent";
}

// Health classification → tinted badge (M102).
const HEALTH_CHIP: Record<string, string> = {
  healthy: "border-fidelity-high/40 bg-fidelity-high/10 text-fidelity-high",
  review: "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
  watch: "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
  blocked: "border-fidelity-low/40 bg-fidelity-low/10 text-fidelity-low",
  critical: "border-fidelity-low/40 bg-fidelity-low/10 text-fidelity-low",
};

function healthChip(classification: string | null | undefined): string {
  const key = (classification ?? "").toLowerCase();
  return HEALTH_CHIP[key] ?? "border-border-strong bg-bg-800 text-text-secondary";
}

// Health classification → premium gradient edge for the attention cards (M108),
// so blocked / review / healthy read at a glance and feel clickable. Falls back
// to a plain bordered surface for unknown classifications.
const HEALTH_GRADIENT: Record<string, string> = {
  healthy: "gradient-border gradient-border-success hover:shadow-glow-success-lg",
  review: "gradient-border gradient-border-warning hover:shadow-glow-warning-lg",
  watch: "gradient-border gradient-border-warning hover:shadow-glow-warning-lg",
  blocked: "gradient-border gradient-border-danger hover:shadow-glow-danger-lg",
  critical: "gradient-border gradient-border-danger hover:shadow-glow-danger-lg",
};

function healthGradient(classification: string | null | undefined): string | null {
  const key = (classification ?? "").toLowerCase();
  return HEALTH_GRADIENT[key] ?? null;
}

// Stage band color for the lifecycle pipeline metric numbers (M102 tokens).
const STAGE_METRIC_COLOR: Record<string, string> = {
  research: "text-text-secondary",
  backtest: "text-accent-300",
  backtest_review: "text-accent-300",
  paper_candidate: "text-research-300",
  shadow: "text-research-300",
  production_candidate: "text-fidelity-high",
};

// Subtle per-stage surface tint for the lifecycle snapshot cards (M108). Keeps
// the row calm at rest while giving each stage a faint sense of "energy band".
const STAGE_TINT: Record<string, string> = {
  research: "border-border",
  backtest: "border-accent-500/25",
  backtest_review: "border-accent-500/25",
  paper_candidate: "border-research/25",
  shadow: "border-research/25",
  production_candidate: "border-fidelity-high/30",
};

function stageTint(key: string): string {
  return STAGE_TINT[key] ?? "border-border";
}

// Map a command-center action target_tab to a strategy route. Falls back to the
// strategy detail page when no tab maps.
function actionRoute(a: CommandCenterTopAction): string {
  const tab = a.target_tab?.trim();
  return `/strategies/${a.strategy_id}${tab ? `?tab=${tab}` : ""}`;
}

const DEMO_ROLES: { key: keyof typeof DEMO_STRATEGY_NAMES; role: string; meaning: string }[] = [
  { key: "aapl", role: "Healthy", meaning: "well-instrumented; high coverage and trust" },
  { key: "fxCarry", role: "Review", meaning: "solid backtests, but missing paper/shadow validation" },
  { key: "crypto", role: "Blocked", meaning: "attractive headline metrics, weak assumptions" },
];

// ---------------------------------------------------------------------------
// Research-health summary metric card
// ---------------------------------------------------------------------------

interface MetricSpec {
  label: string;
  value: number;
  tone: "" | "high" | "medium" | "low" | "accent";
  to?: string;
  /** Premium gradient edge for PRIMARY health cards only (M108). */
  gradient?: "success" | "warning" | "danger" | "primary";
}

// Tone → gradient-border variant for the primary health cards. Only applied
// when the metric carries a non-zero value so calm/empty states stay plain.
const METRIC_GRADIENT: Record<NonNullable<MetricSpec["gradient"]>, string> = {
  success: "gradient-border gradient-border-success hover:shadow-glow-success-lg",
  warning: "gradient-border gradient-border-warning hover:shadow-glow-warning-lg",
  danger: "gradient-border gradient-border-danger hover:shadow-glow-danger-lg",
  primary: "gradient-border gradient-border-primary hover:shadow-glow-primary-lg",
};

function metricColor(value: number, tone: MetricSpec["tone"]): string {
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

function MetricCard({ spec, loading }: { spec: MetricSpec; loading: boolean }) {
  const inner = (
    <>
      {loading ? (
        <Skeleton className="h-8 w-12" />
      ) : (
        <p className={`metric-value text-metric-sm ${metricColor(spec.value, spec.tone)}`}>
          {spec.value}
        </p>
      )}
      {loading ? (
        <Skeleton className="mt-3 h-3 w-20" />
      ) : (
        <p className="caption mt-2 flex items-center gap-1">
          {spec.label}
          {spec.to && (
            <span aria-hidden="true" className="text-text-muted">
              →
            </span>
          )}
        </p>
      )}
    </>
  );

  // PRIMARY health cards get a tone-matched gradient edge — but only when they
  // actually carry a value (a "0 blocked" card stays calm, not alarming red).
  const useGradient = !loading && spec.gradient && spec.value > 0;
  const base = useGradient
    ? `card-interactive rounded-card p-5 shadow-card ${METRIC_GRADIENT[spec.gradient!]}`
    : "card-interactive rounded-card border border-border bg-bg-700 p-5 shadow-card";

  if (spec.to && !loading) {
    return (
      <Link to={spec.to} className={`card-hover-lift block ${base}`}>
        {inner}
      </Link>
    );
  }
  return <div className={`card-hover-lift ${base}`}>{inner}</div>;
}

// ---------------------------------------------------------------------------
// Section-level error banner
// ---------------------------------------------------------------------------

function SectionError({ message }: { message: string }) {
  return (
    <Card>
      <div className="flex flex-col gap-1">
        <p className="card-title text-fidelity-low">Couldn’t load command center</p>
        <p className="text-sm text-text-secondary">{message}</p>
        <p className="mt-1 text-2xs text-text-muted">
          Workspace triage data is temporarily unavailable. You can still navigate using the
          quick actions below.
        </p>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function Home() {
  const auth = useAuth();

  // Single command-center call drives most sections. Strategies are fetched
  // separately only to power the guided-demo panel (demo detection + linking).
  const [data, setData] = useState<CommandCenterResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);

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
    let cancelled = false;
    setLoading(true);
    setError(null);
    getCommandCenter()
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setData(null);
        setError(e instanceof Error ? e.message : "Unable to load command center.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    // Lightweight strategies fetch for the guided-demo panel only. Failure here
    // must not affect the command-center sections.
    getStrategies("active")
      .then((list) => {
        if (!cancelled) setStrategies(list);
      })
      .catch(() => {
        if (!cancelled) setStrategies([]);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const summary = data?.workspace_summary ?? null;
  const lifecycle: CommandCenterLifecycleStage[] = data?.lifecycle_summary ?? [];
  const topActions: CommandCenterTopAction[] = data?.top_actions ?? [];
  const attention: CommandCenterAttentionStrategy[] = data?.strategies_needing_attention ?? [];
  const pendingReviews: CommandCenterPendingReview[] = data?.pending_reviews ?? [];
  const topAlerts: CommandCenterAlert[] = data?.top_alerts ?? [];

  const hasStrategies = (summary?.strategy_count ?? 0) > 0 || strategies.length > 0;

  // 1. Hero health sentence — built from workspace_summary, omitting null/0 parts.
  const healthSentence = useMemo(() => {
    if (!summary) return null;
    const parts: string[] = [];
    if (summary.review_count > 0)
      parts.push(`${summary.review_count} strateg${summary.review_count === 1 ? "y needs" : "ies need"} review`);
    if (summary.open_alert_count > 0)
      parts.push(`${summary.open_alert_count} open alert${summary.open_alert_count === 1 ? "" : "s"}`);
    if (summary.pending_action_count > 0)
      parts.push(`${summary.pending_action_count} pending action${summary.pending_action_count === 1 ? "" : "s"}`);
    if (summary.production_ready_count > 0)
      parts.push(`${summary.production_ready_count} production-ready`);
    if (parts.length === 0) return null;
    return parts.join(" · ");
  }, [summary]);

  // 2. Research-health summary metric cards.
  const metrics: MetricSpec[] = useMemo(() => {
    if (!summary) return [];
    return [
      { label: "Strategies", value: summary.strategy_count, tone: "", to: "/strategies" },
      { label: "Healthy", value: summary.healthy_count, tone: "high", gradient: "success" },
      { label: "Review", value: summary.review_count, tone: "medium", gradient: "warning" },
      {
        label: "Blocked / Critical",
        value: summary.blocked_count,
        tone: "low",
        gradient: "danger",
      },
      { label: "Open alerts", value: summary.open_alert_count, tone: "medium", to: "/alerts" },
      { label: "Pending actions", value: summary.pending_action_count, tone: "accent" },
      {
        label: "Pending reviews",
        value: summary.pending_review_count,
        tone: "accent",
        to: "/governance/strategy-reviews",
      },
    ];
  }, [summary]);

  return (
    <div className="relative space-y-10">
      {/* Ambient hero glow — premium, institutional, behind content (M102 / M108) */}
      <div
        className="pointer-events-none absolute left-0 right-0 top-0 -z-10 h-72 overflow-hidden"
        aria-hidden="true"
      >
        {/* Base wash: low-opacity hero gradient drifting slowly behind everything */}
        <div className="animate-hero-drift absolute -top-16 left-0 right-0 h-72 bg-grad-hero opacity-70 blur-2xl" />
        {/* Color orbs — slightly stronger than M102, still subtle (blur-3xl) */}
        <div className="animate-hero-drift absolute -top-24 left-1/4 h-72 w-72 rounded-full bg-brand/15 blur-3xl" />
        <div
          className="animate-hero-drift absolute -top-16 left-1/2 h-64 w-64 rounded-full bg-research/15 blur-3xl"
          style={{ animationDelay: "-8s" }}
        />
        <div
          className="animate-hero-drift absolute -top-20 right-1/4 h-56 w-56 rounded-full bg-teal-500/12 blur-3xl"
          style={{ animationDelay: "-4s" }}
        />
      </div>

      <NoWorkspaceNotice />

      {/* 1. Hero — Research Command Center + workspace-health sentence */}
      <PageHeader
        className="animate-fade-in"
        tag="Research Command Center"
        title={`Welcome back, ${userName}`}
        subtitle={
          healthSentence ??
          "Your research reliability workspace — monitor evidence health, triage the highest-priority actions, and keep every strategy promotion-ready."
        }
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

      {/* Command-center load failure: isolate to a banner, keep page usable. */}
      {error && !loading && <SectionError message={error} />}

      {/* Demo Mode — seed/reset quick actions, surfaced near the top so a
          first-time visitor immediately sees how to run or reset the demo. */}
      <section className="animate-fade-in">
        <div className="gradient-border gradient-border-primary card-hover-lift rounded-card p-5 shadow-card hover:shadow-glow-primary-lg">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span
                  className="h-2 w-2 rounded-full bg-gradient-to-r from-brand to-research"
                  aria-hidden="true"
                />
                <p className="card-title">Demo Mode</p>
              </div>
              <p className="text-sm text-text-secondary">
                Seed or reset the sample research workspace.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => startWalkthrough(true)}
                className="cta-glow rounded-control bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600"
              >
                Run Demo
              </button>
              {canDemoReset && (
                <Link
                  to="/admin/demo-controls"
                  className="rounded-control border border-border bg-bg-800 px-4 py-2 text-sm text-text-secondary hover:bg-bg-600 hover:text-text-primary"
                >
                  Run Demo Reset
                </Link>
              )}
              {canDemoReset && (
                <Link
                  to="/admin/demo-controls"
                  className="rounded-control border border-border bg-bg-800 px-4 py-2 text-sm text-text-secondary hover:bg-bg-600 hover:text-text-primary"
                >
                  Open Demo Controls
                </Link>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* 2. Research health summary — metric cards */}
      <section className="animate-slide-up space-y-4">
        <h2 className="section-title">Research health</h2>
        {error && !loading ? (
          <p className="text-sm text-text-muted">Health metrics unavailable.</p>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7">
            {(loading
              ? Array.from({ length: 7 }).map(
                  (_, i): MetricSpec => ({ label: `__skeleton_${i}`, value: 0, tone: "" }),
                )
              : metrics
            ).map((m) => (
              <MetricCard key={m.label} spec={m} loading={loading} />
            ))}
          </div>
        )}
      </section>

      {/* 3. Lifecycle pipeline snapshot — compact horizontal stage row */}
      <section className="animate-fade-in space-y-4">
        <div className="flex items-center justify-between gap-4">
          <h2 className="section-title">Lifecycle pipeline</h2>
          {!loading && !error && lifecycle.length > 0 && (
            <Link to="/strategies" className="text-sm text-accent-500 hover:text-accent-300">
              View Strategies →
            </Link>
          )}
        </div>
        {error && !loading ? (
          <p className="text-sm text-text-muted">Lifecycle snapshot unavailable.</p>
        ) : loading ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="rounded-card border border-border bg-bg-700 p-4 shadow-card">
                <Skeleton className="h-8 w-10" />
                <Skeleton className="mt-3 h-3 w-20" />
              </div>
            ))}
          </div>
        ) : lifecycle.length === 0 ? (
          <Card>
            <EmptyState
              title="No strategies yet"
              description="Create your first strategy to start tracking it through the research lifecycle."
              action={{ label: "View Strategies", to: "/strategies" }}
            />
          </Card>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {lifecycle.map((stage) => (
              <Link
                key={stage.key}
                to="/strategies"
                className={`card-hover-lift card-interactive group flex flex-col rounded-card border bg-bg-700 p-4 shadow-card ${
                  stage.blocked_count > 0
                    ? "border-fidelity-medium/40 hover:shadow-glow-warning"
                    : stageTint(stage.key)
                }`}
              >
                <p
                  className={`metric-value text-metric-sm ${
                    stage.count > 0
                      ? STAGE_METRIC_COLOR[stage.key] ?? "text-text-primary"
                      : "text-text-muted"
                  }`}
                >
                  {stage.count}
                </p>
                <p className="caption mt-2 truncate group-hover:text-text-secondary">
                  {stage.label}
                </p>
                {stage.blocked_count > 0 && (
                  <span className="mt-2 inline-flex w-fit items-center gap-1 text-2xs text-fidelity-medium">
                    <span
                      aria-hidden="true"
                      className="status-dot-pulse inline-block h-1.5 w-1.5 rounded-full bg-fidelity-medium"
                    />
                    {stage.blocked_count} blocked
                  </span>
                )}
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* 4. Highest-priority actions — "Today" */}
      <section className="animate-fade-in space-y-4">
        <div className="flex items-center justify-between gap-4">
          <h2 className="section-title">Today — highest-priority actions</h2>
          <Link to="/command-center" className="text-sm text-accent-500 hover:text-accent-300">
            Command Center →
          </Link>
        </div>
        <div className="card-interactive flex flex-col rounded-card border border-border bg-bg-700 shadow-card">
          <div className="flex-1 divide-y divide-border">
            {error && !loading ? (
              <p className="px-6 py-6 text-sm text-text-muted">Priority actions unavailable.</p>
            ) : loading ? (
              <div className="space-y-4 px-6 py-5">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="flex items-start gap-3">
                    <div className="min-w-0 flex-1 space-y-2">
                      <Skeleton className="h-3.5 w-2/5" />
                      <SkeletonText lines={1} />
                    </div>
                    <Skeleton className="h-3 w-12 shrink-0" />
                  </div>
                ))}
              </div>
            ) : topActions.length === 0 ? (
              <div className="px-6 py-8">
                <EmptyState
                  title="No urgent research actions"
                  description="Your workspace is currently clean."
                />
              </div>
            ) : (
              topActions.slice(0, 5).map((a, i) => (
                <Link
                  key={`${a.strategy_id}:${a.title ?? i}`}
                  to={actionRoute(a)}
                  className={`flex w-full items-start gap-3 px-6 py-3.5 text-left transition-colors hover:bg-bg-700/50 ${sevEdge(a.severity)}`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm text-text-primary">
                        {a.title ?? "Untitled action"}
                      </span>
                      {a.severity && (
                        <span
                          className={`rounded-chip border px-1.5 py-px text-2xs ${sevChip(a.severity)}`}
                        >
                          {a.severity}
                        </span>
                      )}
                    </div>
                    {a.recommended_action && (
                      <p className="mt-1 text-xs text-text-secondary">{a.recommended_action}</p>
                    )}
                    {a.strategy_name && (
                      <p className="mt-1 text-2xs text-text-muted">{a.strategy_name}</p>
                    )}
                  </div>
                  <span className="shrink-0 text-2xs text-text-muted">Open →</span>
                </Link>
              ))
            )}
          </div>
          <p className="border-t border-border px-6 py-3 text-2xs text-text-muted">
            Recommended actions prioritize research evidence tasks. They are not trading
            recommendations.
          </p>
        </div>
      </section>

      {/* 5. Strategies needing attention */}
      <section className="animate-fade-in space-y-4">
        <h2 className="section-title">Strategies needing attention</h2>
        {error && !loading ? (
          <p className="text-sm text-text-muted">Attention list unavailable.</p>
        ) : loading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="rounded-card border border-border bg-bg-700 p-5 shadow-card">
                <Skeleton className="h-4 w-1/3" />
                <SkeletonText className="mt-3" lines={1} />
              </div>
            ))}
          </div>
        ) : attention.length === 0 ? (
          <Card>
            <div className="flex items-center gap-3 px-1 py-2">
              <span
                aria-hidden="true"
                className="inline-block h-2 w-2 rounded-full bg-fidelity-high"
              />
              <p className="text-sm text-text-secondary">
                All strategies are healthy — nothing needs attention right now.
              </p>
            </div>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {attention.map((s) => {
              const grad = healthGradient(s.health_classification);
              return (
              <Link
                key={s.strategy_id}
                to={`/strategies/${s.strategy_id}`}
                className={`card-hover-lift card-interactive flex flex-col gap-3 rounded-card p-5 shadow-card ${
                  grad ? grad : "border border-border bg-bg-700"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="card-title truncate">{s.name ?? "Untitled strategy"}</p>
                  {s.reliability_score !== null && (
                    <span className="metric-value shrink-0 font-mono text-sm text-text-secondary">
                      {Math.round(s.reliability_score)}
                      <span className="text-2xs text-text-muted">/100</span>
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <LifecycleStageBadge stage={s.lifecycle_stage} />
                  {s.health_classification && (
                    <span
                      className={`rounded-chip border px-2 py-0.5 text-2xs font-medium uppercase tracking-eyebrow ${healthChip(s.health_classification)}`}
                    >
                      {s.health_classification}
                    </span>
                  )}
                  {s.open_alert_count > 0 && (
                    <span className="rounded-chip border border-fidelity-medium/40 bg-fidelity-medium/10 px-2 py-0.5 text-2xs text-fidelity-medium">
                      {s.open_alert_count} alert{s.open_alert_count === 1 ? "" : "s"}
                    </span>
                  )}
                </div>
                {s.primary_concern && (
                  <p className="text-xs text-text-secondary">{s.primary_concern}</p>
                )}
                <span className="text-2xs text-text-muted">Open strategy →</span>
              </Link>
              );
            })}
          </div>
        )}
      </section>

      {/* 6. Promotion / review queue */}
      <section className="animate-fade-in space-y-4">
        <div className="flex items-center justify-between gap-4">
          <h2 className="section-title">Promotion &amp; review queue</h2>
          <Link
            to="/governance/strategy-reviews"
            className="text-sm text-accent-500 hover:text-accent-300"
          >
            Open reviews →
          </Link>
        </div>
        {error && !loading ? (
          <p className="text-sm text-text-muted">Review queue unavailable.</p>
        ) : loading ? (
          <div className="rounded-card border border-border bg-bg-700 p-5 shadow-card">
            <Skeleton className="h-4 w-1/4" />
            <SkeletonText className="mt-3" lines={2} />
          </div>
        ) : pendingReviews.length === 0 ? (
          <Card>
            <p className="text-sm text-text-secondary">No pending reviews.</p>
          </Card>
        ) : (
          <div className="card-interactive rounded-card border border-border bg-bg-700 shadow-card">
            <div className="border-b border-border px-6 py-4">
              <p className="card-title">
                {pendingReviews.length} pending review{pendingReviews.length === 1 ? "" : "s"}
              </p>
            </div>
            <div className="divide-y divide-border">
              {pendingReviews.slice(0, 5).map((r) => (
                <Link
                  key={r.review_id}
                  to="/governance/strategy-reviews"
                  className="flex w-full items-center gap-3 px-6 py-3 text-left transition-colors hover:bg-bg-700/50"
                >
                  <span className="min-w-0 flex-1 truncate text-sm text-text-primary">
                    {r.strategy_name ?? "Strategy"}
                  </span>
                  {r.target_stage && <LifecycleStageBadge stage={r.target_stage} />}
                  {r.status && (
                    <span className="shrink-0 text-2xs uppercase tracking-eyebrow text-text-muted">
                      {r.status}
                    </span>
                  )}
                  <span className="shrink-0 text-2xs text-text-muted">Open →</span>
                </Link>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* 7. Alerts & blockers — triage only */}
      <section className="animate-fade-in space-y-4">
        <div className="flex items-center justify-between gap-4">
          <h2 className="section-title">Alerts &amp; blockers</h2>
          <Link to="/alerts" className="text-sm text-accent-500 hover:text-accent-300">
            Open Alerts →
          </Link>
        </div>
        {error && !loading ? (
          <p className="text-sm text-text-muted">Alerts unavailable.</p>
        ) : loading ? (
          <div className="rounded-card border border-border bg-bg-700 p-5 shadow-card">
            <SkeletonText lines={2} />
          </div>
        ) : topAlerts.length === 0 ? (
          <Card>
            <p className="text-sm text-text-secondary">No open alerts to triage.</p>
          </Card>
        ) : (
          <div className="card-interactive rounded-card border border-border bg-bg-700 shadow-card">
            <div className="divide-y divide-border">
              {topAlerts.slice(0, 3).map((alert) => {
                const inner = (
                  <>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm text-text-primary">
                          {alert.title ?? "Untitled alert"}
                        </span>
                        {alert.severity && (
                          <span
                            className={`rounded-chip border px-1.5 py-px text-2xs ${sevChip(alert.severity)}`}
                          >
                            {alert.severity}
                          </span>
                        )}
                      </div>
                      {alert.rule_type && (
                        <p className="mt-1 text-2xs text-text-muted">{alert.rule_type}</p>
                      )}
                    </div>
                    <span className="shrink-0 text-2xs text-text-muted">
                      {alert.strategy_id ? "View →" : ""}
                    </span>
                  </>
                );
                return alert.strategy_id ? (
                  <Link
                    key={alert.id}
                    to={`/strategies/${alert.strategy_id}`}
                    className="flex w-full items-start gap-3 px-6 py-3.5 transition-colors hover:bg-bg-700/50"
                  >
                    {inner}
                  </Link>
                ) : (
                  <div key={alert.id} className="flex w-full items-start gap-3 px-6 py-3.5">
                    {inner}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </section>

      {/* 8. Demo / onboarding — prominent when empty, secondary when populated */}
      {hasStrategies ? (
        <section className="space-y-4">
          <h2 className="section-title">Get oriented</h2>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {/* Guided demo — compact */}
            <div className="card-interactive flex flex-col rounded-card border border-border bg-bg-700 shadow-card">
              <div className="border-b border-border px-6 py-4">
                <p className="caption mb-1">Guided demo</p>
                <p className="card-title">Learn the product in 6 steps</p>
              </div>
              <div className="flex flex-1 flex-wrap items-center gap-2 px-6 py-4">
                {demoReady ? (
                  <>
                    <button
                      onClick={() => startWalkthrough(true)}
                      className="rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-1.5 text-xs text-accent-200 hover:bg-accent-500/25"
                    >
                      {walkState.lastStep > 1 && !walkState.completed
                        ? "Continue walkthrough"
                        : "Start guided demo"}
                    </button>
                    <button
                      onClick={() => startWalkthrough(true)}
                      className="rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
                    >
                      Restart
                    </button>
                  </>
                ) : (
                  <Link
                    to="/admin/demo-controls"
                    className="rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-1.5 text-xs text-accent-200 hover:bg-accent-500/25"
                  >
                    Open Demo Controls
                  </Link>
                )}
              </div>
            </div>

            {/* Quick actions — compact */}
            <div className="card-interactive flex flex-col rounded-card border border-border bg-bg-700 shadow-card lg:col-span-2">
              <div className="border-b border-border px-6 py-4">
                <p className="card-title">Quick actions</p>
              </div>
              <div className="flex flex-1 flex-wrap items-center gap-2 px-6 py-4">
                <Link
                  to="/strategies"
                  className="rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-1.5 text-xs text-accent-200 hover:bg-accent-500/25"
                >
                  View Strategies
                </Link>
                <Link
                  to="/developer/evidence-builder"
                  className="rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
                >
                  Upload Evidence
                </Link>
                <Link
                  to="/alerts"
                  className="rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
                >
                  Review Alerts
                </Link>
                <Link
                  to="/promotion-gates"
                  className="rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
                >
                  Open Promotion Review
                </Link>
                <button
                  onClick={() => startWalkthrough(true)}
                  className="rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
                >
                  Run Demo
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
        </section>
      ) : (
        <section className="space-y-4">
          <h2 className="section-title">Get started</h2>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Prominent guided demo */}
            <div className="card-interactive flex flex-col rounded-card border border-accent-500/30 bg-accent-500/5 shadow-card lg:col-span-2">
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
                      The guided demo needs the clean realistic demo data. Load it, then explore the
                      example strategies below.
                    </p>
                    <Link
                      to="/admin/demo-controls"
                      className="inline-block rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-1.5 text-xs text-accent-200 hover:bg-accent-500/25"
                    >
                      Open Demo Controls
                    </Link>
                  </>
                )}
                {demoReady && (
                  <div className="mt-4 divide-y divide-border border-t border-border pt-2">
                    {DEMO_ROLES.map((d) => {
                      const sid = findDemoStrategyId(strategies, d.key);
                      const name = DEMO_STRATEGY_NAMES[d.key];
                      const row = (
                        <>
                          <span className="w-20 shrink-0 text-2xs uppercase tracking-eyebrow text-text-muted">
                            {d.role}
                          </span>
                          <span className="shrink-0 text-sm text-text-primary">{name}</span>
                          <span className="min-w-0 flex-1 truncate text-xs text-text-secondary">
                            {d.meaning}
                          </span>
                          {sid && <span className="shrink-0 text-2xs text-text-muted">Open →</span>}
                        </>
                      );
                      return sid ? (
                        <Link
                          key={d.key}
                          to={`/strategies/${sid}`}
                          className="flex items-center gap-3 py-2.5 transition-colors hover:bg-bg-700/50"
                        >
                          {row}
                        </Link>
                      ) : (
                        <div key={d.key} className="flex items-center gap-3 py-2.5">
                          {row}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* Quick actions */}
            <div className="card-interactive flex flex-col rounded-card border border-border bg-bg-700 shadow-card">
              <div className="border-b border-border px-6 py-4">
                <p className="card-title">Quick actions</p>
              </div>
              <div className="flex flex-1 flex-col gap-2 px-6 py-4">
                <Link
                  to="/strategies"
                  className="rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-1.5 text-center text-xs text-accent-200 hover:bg-accent-500/25"
                >
                  View Strategies
                </Link>
                <Link
                  to="/developer/evidence-builder"
                  className="rounded-control border border-border px-3 py-1.5 text-center text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
                >
                  Upload Evidence
                </Link>
                <Link
                  to="/alerts"
                  className="rounded-control border border-border px-3 py-1.5 text-center text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
                >
                  Review Alerts
                </Link>
                <Link
                  to="/promotion-gates"
                  className="rounded-control border border-border px-3 py-1.5 text-center text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
                >
                  Open Promotion Review
                </Link>
                {canDemoReset && (
                  <Link
                    to="/admin/demo-controls"
                    className="rounded-control border border-border px-3 py-1.5 text-center text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
                  >
                    Run Demo Reset
                  </Link>
                )}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Page-level disclaimer */}
      {data?.disclaimer && (
        <p className="text-2xs text-text-muted">{data.disclaimer}</p>
      )}
    </div>
  );
}
