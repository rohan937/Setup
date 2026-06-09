import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type {
  CommandCenterResponse,
  CommandCenterTopAction,
  CommandCenterAttentionStrategy,
  CommandCenterLifecycleStage,
  CommandCenterWorkspaceSummary,
  CommandCenterPendingReview,
  RiskNarrativeResponse,
  BacktestRealityResponse,
  EvidenceVerificationResponse,
} from "@/types";
import {
  getCommandCenter,
  getStrategyRiskNarrative,
  getStrategyBacktestReality,
  getStrategyEvidenceVerification,
} from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Card from "@/components/Card";
import EmptyState from "@/components/EmptyState";
import LifecycleStageBadge from "@/components/LifecycleStageBadge";
import { Skeleton } from "@/components/Skeleton";
import { canSeedDemo } from "@/lib/permissions";
import { startWalkthrough } from "@/lib/demoWalkthrough";

// ---------------------------------------------------------------------------
// M107 — Executive Demo View
// A spacious, presentation-friendly narrative page composed entirely from
// EXISTING endpoints. Frontend-only. M101/M102 design system.
// ---------------------------------------------------------------------------

// Health classification → tinted chip + card accent (M102 tokens).
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

const HEALTH_ACCENT: Record<string, string> = {
  healthy: "border-l-fidelity-high",
  review: "border-l-fidelity-medium",
  watch: "border-l-fidelity-medium",
  blocked: "border-l-fidelity-low",
  critical: "border-l-fidelity-low",
};

function healthAccent(classification: string | null | undefined): string {
  const key = (classification ?? "").toLowerCase();
  return HEALTH_ACCENT[key] ?? "border-l-border-strong";
}

// Health classification → gradient-border variant + matching hover glow (M108).
// Healthy = success, review/watch = warning, blocked/critical = danger,
// everything else (unscored) = research tint.
const HEALTH_GRADIENT: Record<string, string> = {
  healthy: "gradient-border gradient-border-success hover:shadow-glow-success-lg",
  review: "gradient-border gradient-border-warning hover:shadow-glow-warning-lg",
  watch: "gradient-border gradient-border-warning hover:shadow-glow-warning-lg",
  blocked: "gradient-border gradient-border-danger hover:shadow-glow-danger-lg",
  critical: "gradient-border gradient-border-danger hover:shadow-glow-danger-lg",
};

function healthGradient(classification: string | null | undefined): string {
  const key = (classification ?? "").toLowerCase();
  return (
    HEALTH_GRADIENT[key] ??
    "gradient-border gradient-border-research hover:shadow-glow-research-lg"
  );
}

// Big-metric tone → gradient-border variant + matching large hover glow (M108).
const METRIC_GRADIENT: Record<NonNullable<BigMetric["tone"]>, string> = {
  "": "gradient-border gradient-border-primary hover:shadow-glow-primary-lg",
  high: "gradient-border gradient-border-success hover:shadow-glow-success-lg",
  medium: "gradient-border gradient-border-warning hover:shadow-glow-warning-lg",
  low: "gradient-border gradient-border-danger hover:shadow-glow-danger-lg",
  accent: "gradient-border gradient-border-primary hover:shadow-glow-primary-lg",
};

// Lifecycle stage key → soft background tint behind the count (per-stage energy).
const STAGE_TINT: Record<string, string> = {
  research: "bg-bg-600/40",
  backtest: "bg-accent-500/10",
  backtest_review: "bg-accent-500/10",
  paper_candidate: "bg-research/10",
  shadow: "bg-research/10",
  production_candidate: "bg-fidelity-high/10",
};

// Static product copy per lifecycle stage key.
const STAGE_MEANING: Record<string, string> = {
  research: "Early signal research & ideation",
  backtest: "Backtest logged, under evidence review",
  backtest_review: "Backtest logged, under evidence review",
  paper_candidate: "Ready for paper/live-like validation",
  shadow: "Running shadow/paper, monitored for drift",
  production_candidate: "Promotion-ready, governance cleared",
};

const STAGE_METRIC_COLOR: Record<string, string> = {
  research: "text-text-secondary",
  backtest: "text-accent-300",
  backtest_review: "text-accent-300",
  paper_candidate: "text-research-300",
  shadow: "text-research-300",
  production_candidate: "text-fidelity-high",
};

// Verdict / status chip tinting reused across the trust + reality layers.
const VERDICT_CHIP: Record<string, string> = {
  verified: "border-fidelity-high/40 bg-fidelity-high/10 text-fidelity-high",
  realistic: "border-fidelity-high/40 bg-fidelity-high/10 text-fidelity-high",
  ready: "border-fidelity-high/40 bg-fidelity-high/10 text-fidelity-high",
  acceptable: "border-fidelity-high/40 bg-fidelity-high/10 text-fidelity-high",
  intact: "border-fidelity-high/40 bg-fidelity-high/10 text-fidelity-high",
  review: "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
  warning: "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
  weak: "border-fidelity-low/40 bg-fidelity-low/10 text-fidelity-low",
  failed: "border-fidelity-low/40 bg-fidelity-low/10 text-fidelity-low",
  blocked: "border-fidelity-low/40 bg-fidelity-low/10 text-fidelity-low",
  broken: "border-fidelity-low/40 bg-fidelity-low/10 text-fidelity-low",
  insufficient_data: "border-border-strong bg-bg-800 text-text-muted",
};

function verdictChip(verdict: string | null | undefined): string {
  const key = (verdict ?? "").toLowerCase();
  return VERDICT_CHIP[key] ?? "border-border-strong bg-bg-800 text-text-secondary";
}

const NARRATIVE_SEV_CHIP: Record<string, string> = {
  critical: "border-fidelity-low/40 bg-fidelity-low/10 text-fidelity-low",
  high: "border-fidelity-low/30 bg-fidelity-low/5 text-fidelity-low",
  medium: "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
  low: "border-border-strong bg-bg-800 text-text-secondary",
};

function narrativeSevChip(severity: string | null | undefined): string {
  const key = (severity ?? "").toLowerCase();
  return NARRATIVE_SEV_CHIP[key] ?? "border-border bg-bg-800 text-text-muted";
}

// ---------------------------------------------------------------------------
// Big metric card (presentation scale)
// ---------------------------------------------------------------------------

interface BigMetric {
  label: string;
  value: number;
  tone: "" | "high" | "medium" | "low" | "accent";
  to?: string;
}

function metricColor(value: number, tone: BigMetric["tone"]): string {
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

function BigMetricCard({ spec, loading }: { spec: BigMetric; loading: boolean }) {
  const inner = (
    <>
      {loading ? (
        <Skeleton className="h-10 w-16" />
      ) : (
        <p className={`metric-value text-metric ${metricColor(spec.value, spec.tone)}`}>
          {spec.value}
        </p>
      )}
      {loading ? (
        <Skeleton className="mt-3 h-3 w-24" />
      ) : (
        <p className="caption mt-3 flex items-center gap-1">
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
  // Loading skeletons stay calm (plain border); resolved cards get a tone-keyed
  // gradient edge + matching large glow on hover (M108 cinematic treatment).
  const base = loading
    ? "rounded-card border border-border bg-bg-700 p-8 shadow-card"
    : `card-interactive rounded-card p-8 shadow-card ${METRIC_GRADIENT[spec.tone]}`;
  if (spec.to && !loading) {
    return (
      <Link to={spec.to} className={`card-hover-lift block ${base}`}>
        {inner}
      </Link>
    );
  }
  return <div className={base}>{inner}</div>;
}

// ---------------------------------------------------------------------------
// Small section heading helper
// ---------------------------------------------------------------------------

function SectionHeading({
  eyebrow,
  title,
  blurb,
  accent = "primary",
}: {
  eyebrow: string;
  title: string;
  blurb?: string;
  /** Tint of the thin gradient accent bar above the eyebrow (M108). */
  accent?: "primary" | "success" | "warning" | "research";
}) {
  const ACCENT_BAR: Record<NonNullable<typeof accent>, string> = {
    primary: "bg-grad-primary",
    success: "bg-grad-success",
    warning: "bg-grad-warning",
    research: "bg-grad-research",
  };
  return (
    <div className="max-w-3xl">
      {/* Thin gradient accent bar — cinematic section separation (M108). */}
      <div
        aria-hidden="true"
        className={`mb-3 h-1 w-12 rounded-full ${ACCENT_BAR[accent]}`}
      />
      <p className="caption mb-2">{eyebrow}</p>
      <h2 className="section-title text-xl">{title}</h2>
      {blurb && <p className="mt-2 text-sm leading-relaxed text-text-secondary">{blurb}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Static demo-story cards
// ---------------------------------------------------------------------------

const DEMO_STORY: { title: string; body: string }[] = [
  {
    title: "Research evidence is ingested",
    body: "Configs, universes, signals, datasets, runs, and backtests land as a structured evidence bundle for every strategy.",
  },
  {
    title: "QuantFidelity verifies the evidence chain",
    body: "Hashes, timestamps, and links are checked so the evidence behind a claim is intact and tamper-evident — not just stored.",
  },
  {
    title: "Backtest reality checks flag unrealistic assumptions",
    body: "Costs, fills, look-ahead, and liquidity are stress-tested against the research claim so fragile backtests surface early.",
  },
  {
    title: "Paper / shadow monitoring catches research-to-reality drift",
    body: "Shadow and paper behavior is compared to the backtest so divergence between research and reality is detected, not assumed away.",
  },
  {
    title: "Promotion gates decide if a strategy is ready",
    body: "Readiness is gated on evidence coverage, trust, and drift — a strategy is promotion-ready only when governance criteria are met.",
  },
  {
    title: "Review packets & narratives make the decision auditable",
    body: "Raw evidence is converted into a readable governance narrative and review packet so every promotion decision is defensible.",
  },
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ExecutiveDemo() {
  const auth = useAuth();

  const [cc, setCc] = useState<CommandCenterResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Best-effort enrichment for the TOP attention strategy (bounded: 1 strategy,
  // 3 calls). Each is non-blocking and isolated in its own try/catch.
  const [narrative, setNarrative] = useState<RiskNarrativeResponse | null>(null);
  const [reality, setReality] = useState<BacktestRealityResponse | null>(null);
  const [verification, setVerification] = useState<EvidenceVerificationResponse | null>(null);

  const workspaceName =
    auth.memberships.find((m) => m.organization_id === auth.organizationId)?.workspace_name ??
    auth.memberships[0]?.workspace_name ??
    "Your workspace";
  const canDemo = canSeedDemo(auth);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getCommandCenter()
      .then((res) => {
        if (cancelled) return;
        setCc(res);

        // Enrich from the top attention strategy only — bounded, non-blocking.
        const top = res.strategies_needing_attention?.[0];
        if (!top) return;
        const id = top.strategy_id;

        getStrategyRiskNarrative(id)
          .then((n) => {
            if (!cancelled) setNarrative(n);
          })
          .catch(() => {
            /* explanatory copy fallback */
          });
        getStrategyBacktestReality(id)
          .then((r) => {
            if (!cancelled) setReality(r);
          })
          .catch(() => {
            /* explanatory copy fallback */
          });
        getStrategyEvidenceVerification(id)
          .then((v) => {
            if (!cancelled) setVerification(v);
          })
          .catch(() => {
            /* explanatory copy fallback */
          });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setCc(null);
        setError(e instanceof Error ? e.message : "Unable to load command center.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const summary: CommandCenterWorkspaceSummary | null = cc?.workspace_summary ?? null;
  const lifecycle: CommandCenterLifecycleStage[] = cc?.lifecycle_summary ?? [];
  const topActions: CommandCenterTopAction[] = cc?.top_actions ?? [];
  const attention: CommandCenterAttentionStrategy[] = cc?.strategies_needing_attention ?? [];
  const pendingReviews: CommandCenterPendingReview[] = cc?.pending_reviews ?? [];

  const isEmpty = !loading && !error && (summary?.strategy_count ?? 0) === 0;

  // Deterministic overall workspace state word.
  const workspaceState = useMemo(() => {
    if (!summary) return null;
    if (summary.blocked_count > 0) return "Needs attention";
    if (summary.review_count > 0) return "In review";
    return "Healthy";
  }, [summary]);

  const stateTone =
    workspaceState === "Needs attention"
      ? "text-fidelity-low"
      : workspaceState === "In review"
        ? "text-fidelity-medium"
        : "text-fidelity-high";

  // Big metric specs (Portfolio Health Snapshot).
  const metrics: BigMetric[] = useMemo(() => {
    if (!summary) return [];
    return [
      { label: "Total Strategies", value: summary.strategy_count, tone: "", to: "/strategies" },
      { label: "Healthy", value: summary.healthy_count, tone: "high" },
      { label: "In Review", value: summary.review_count, tone: "medium" },
      { label: "Blocked / Critical", value: summary.blocked_count, tone: "low" },
      { label: "Open Alerts", value: summary.open_alert_count, tone: "medium", to: "/alerts" },
      { label: "Pending Actions", value: summary.pending_action_count, tone: "accent" },
      {
        label: "Pending Reviews",
        value: summary.pending_review_count,
        tone: "accent",
        to: "/governance/strategy-reviews",
      },
      { label: "Production Candidate", value: summary.production_ready_count, tone: "high" },
    ];
  }, [summary]);

  // Hero stat tiles.
  const heroStats = useMemo(() => {
    if (!summary) return [];
    return [
      { label: "Strategies", value: summary.strategy_count },
      { label: "Open alerts", value: summary.open_alert_count },
      { label: "Pending reviews", value: summary.pending_review_count },
      { label: "Production candidate", value: summary.production_ready_count },
    ];
  }, [summary]);

  // Verification concerns across the attention list (portfolio-level signal).
  const verificationConcernCount = useMemo(
    () =>
      attention.filter(
        (s) =>
          (s.health_classification ?? "").toLowerCase() === "blocked" ||
          (s.health_classification ?? "").toLowerCase() === "critical" ||
          (s.health_classification ?? "").toLowerCase() === "review",
      ).length,
    [attention],
  );

  const topBlockers = useMemo(() => {
    const fromActions = topActions
      .map((a) => a.title)
      .filter((t): t is string => Boolean(t));
    if (fromActions.length > 0) return fromActions.slice(0, 4);
    return attention
      .map((s) => s.primary_concern ?? s.top_blocker_title)
      .filter((t): t is string => Boolean(t))
      .slice(0, 4);
  }, [topActions, attention]);

  return (
    <div className="relative mx-auto max-w-6xl space-y-24 pb-10">
      {/* Ambient hero glow — cinematic but classy (M108): larger, low-opacity
          blue/purple/cyan/teal orbs drifting slowly behind the hero. */}
      <div
        className="pointer-events-none absolute left-0 right-0 top-0 -z-10 h-[28rem] overflow-hidden"
        aria-hidden="true"
      >
        <div className="animate-hero-drift absolute -top-32 left-1/4 h-96 w-96 rounded-full bg-brand/12 blur-3xl" />
        <div
          className="animate-hero-drift absolute -top-24 left-1/2 h-[26rem] w-[26rem] rounded-full bg-research/12 blur-3xl"
          style={{ animationDelay: "-8s" }}
        />
        <div
          className="animate-hero-drift absolute -top-28 right-1/4 h-80 w-80 rounded-full bg-accent-500/10 blur-3xl"
          style={{ animationDelay: "-4s" }}
        />
        <div
          className="animate-hero-drift absolute -top-16 right-1/3 h-72 w-72 rounded-full bg-teal-500/8 blur-3xl"
          style={{ animationDelay: "-12s" }}
        />
      </div>

      {/* ---------------------------------------------------------------- */}
      {/* 1. HERO */}
      {/* ---------------------------------------------------------------- */}
      <section className="animate-fade-in pt-2">
        {/* Hero gradient panel — strongest treatment on the page. bg-grad-hero
            wash + slow drift behind the header content. Visual only. */}
        <div className="relative overflow-hidden rounded-card">
          <div
            aria-hidden="true"
            className="animate-hero-drift pointer-events-none absolute inset-0 -z-10 bg-grad-hero"
          />
          <div className="relative px-6 pb-6 pt-7 sm:px-8">
            <div className="mb-8 flex items-start justify-between gap-4">
              <div>
                <p className="caption mb-2">Executive Overview</p>
                <h1 className="page-title">
                  <span className="text-gradient-primary">QuantFidelity</span>
                  {" — Research Governance Overview"}
                </h1>
                <p className="mt-2 max-w-2xl text-base leading-relaxed text-text-secondary">
                  QuantFidelity gives quant research teams a reliability layer for strategy
                  evidence, backtests, promotion readiness, and research-to-production drift.
                </p>
              </div>
              <div className="shrink-0 pt-1">
                <div className="flex flex-col items-end gap-2 text-xs text-text-muted">
                  <span className="flex items-center gap-1.5">
                    <span className="caption">Workspace</span>
                    <span className="text-text-secondary">{workspaceName}</span>
                  </span>
                  {workspaceState && !loading && (
                    <span className={`metric-value text-sm font-semibold ${stateTone}`}>
                      {workspaceState}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Inline hero stats */}
        <div className="mt-2 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {(loading
            ? Array.from({ length: 4 }).map((_, i) => ({ label: `__s${i}`, value: 0 }))
            : heroStats
          ).map((s, i) => (
            <div
              key={s.label + i}
              className={`rounded-card px-5 py-4 shadow-card ${
                loading
                  ? "border border-border bg-bg-700/60"
                  : "gradient-border-hover card-hover-lift"
              }`}
            >
              {loading ? (
                <Skeleton className="h-7 w-12" />
              ) : (
                <p className="metric-value text-metric-sm text-text-primary">{s.value}</p>
              )}
              {loading ? (
                <Skeleton className="mt-2 h-3 w-20" />
              ) : (
                <p className="caption mt-1.5">{s.label}</p>
              )}
            </div>
          ))}
        </div>

        <p className="mt-4 text-2xs text-text-muted">
          Research governance — not trading advice.
        </p>
      </section>

      {/* Command-center load failure: isolate to a banner, keep page usable. */}
      {error && !loading && (
        <Card>
          <div className="flex flex-col gap-1">
            <p className="card-title text-fidelity-low">Couldn’t load workspace data</p>
            <p className="text-sm text-text-secondary">{error}</p>
            <p className="mt-1 text-2xs text-text-muted">
              Live portfolio sections are temporarily unavailable. The product story and quick
              actions below still work.
            </p>
          </div>
        </Card>
      )}

      {/* Empty-state: no strategies — still show story + CTAs below. */}
      {isEmpty && (
        <Card>
          <EmptyState
            title="No strategies yet"
            description="Create or seed demo strategies to see the Executive Demo View with live portfolio health, evidence verification, and governance signals."
            action={
              canDemo
                ? { label: "Run Demo Controls", to: "/admin/demo-controls" }
                : { label: "Create Strategy", to: "/strategies" }
            }
          />
          <div className="mt-4 flex flex-wrap gap-2">
            <Link
              to="/strategies"
              className="cta-glow rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary hover:shadow-glow-primary"
            >
              Create Strategy
            </Link>
            <Link
              to="/developer/evidence-builder"
              className="cta-glow rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary hover:shadow-glow-primary"
            >
              Upload Evidence Bundle
            </Link>
          </div>
        </Card>
      )}

      {/* ------------------------------------------------------------ */}
      {/* PRODUCT WALKTHROUGH VIDEO — always shown, near the top */}
      {/* ------------------------------------------------------------ */}
      <section className="animate-fade-in space-y-6">
        <SectionHeading
          eyebrow="Walkthrough"
          title="QuantFidelity AI Product Walkthrough"
          blurb="A 70-second walkthrough of how QuantFidelity moves from backtest evidence to research governance decisions."
          accent="research"
        />
        <div className="gradient-border gradient-border-research overflow-hidden rounded-card bg-bg-700 p-2 shadow-card">
          <video
            controls
            playsInline
            preload="metadata"
            className="block w-full rounded-[10px] bg-bg-900"
            src="/videos/quantfidelity-ai-product-walkthrough.mp4"
          >
            Your browser does not support the video tag.
          </video>
        </div>
        <p className="font-mono text-2xs italic text-text-muted">
          Research governance summary. Not trading advice.
        </p>
      </section>

      {/* The live data sections render only when we have strategies. */}
      {!error && !isEmpty && (
        <>
          {/* ------------------------------------------------------------ */}
          {/* 2. PORTFOLIO HEALTH SNAPSHOT */}
          {/* ------------------------------------------------------------ */}
          <section className="animate-fade-in space-y-6">
            <SectionHeading
              eyebrow="Portfolio health"
              title="The whole research book at a glance"
              blurb="Every strategy is classified by reliability so a head of research can see what is healthy, what needs review, and what is blocked — in one screen."
            />
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {(loading
                ? Array.from({ length: 8 }).map(
                    (_, i): BigMetric => ({ label: `__m${i}`, value: 0, tone: "" }),
                  )
                : metrics
              ).map((m, i) => (
                <BigMetricCard key={m.label + i} spec={m} loading={loading} />
              ))}
            </div>
          </section>

          {/* ------------------------------------------------------------ */}
          {/* 3. LIFECYCLE PIPELINE OVERVIEW */}
          {/* ------------------------------------------------------------ */}
          <section className="animate-fade-in space-y-6">
            <SectionHeading
              eyebrow="Workflow"
              title="The research-to-production lifecycle"
              blurb="Strategies move through five governed stages. QuantFidelity tracks where each one sits and what is blocking it from advancing."
            />
            {loading ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="rounded-card border border-border bg-bg-700 p-5 shadow-card">
                    <Skeleton className="h-9 w-12" />
                    <Skeleton className="mt-3 h-3 w-24" />
                    <Skeleton className="mt-3 h-3 w-32" />
                  </div>
                ))}
              </div>
            ) : lifecycle.length === 0 ? (
              <Card>
                <p className="text-sm text-text-secondary">No lifecycle data available yet.</p>
              </Card>
            ) : (
              <div className="relative grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
                {lifecycle.map((stage, idx) => (
                  <div
                    key={stage.key}
                    className="card-hover-lift relative flex flex-col overflow-hidden rounded-card border border-border bg-bg-700 p-5 shadow-card"
                  >
                    {/* Per-stage energy: animated connector-flow sheen along the
                        top edge ties the stages together into a pipeline (M108). */}
                    {idx < lifecycle.length - 1 && (
                      <div
                        aria-hidden="true"
                        className="connector-flow absolute inset-x-0 top-0 h-0.5"
                      />
                    )}
                    {/* Soft per-stage tint behind the count. */}
                    <div
                      aria-hidden="true"
                      className={`pointer-events-none absolute -right-6 -top-6 h-20 w-20 rounded-full blur-2xl ${
                        stage.count > 0 ? STAGE_TINT[stage.key] ?? "bg-bg-600/40" : "bg-transparent"
                      }`}
                    />
                    <p
                      className={`metric-value text-metric-sm ${
                        stage.count > 0
                          ? STAGE_METRIC_COLOR[stage.key] ?? "text-text-primary"
                          : "text-text-muted"
                      }`}
                    >
                      {stage.count}
                    </p>
                    <p className="mt-2 text-sm font-medium text-text-primary">{stage.label}</p>
                    <p className="mt-2 text-xs leading-relaxed text-text-secondary">
                      {STAGE_MEANING[stage.key] ?? "Lifecycle stage"}
                    </p>
                    {stage.blocked_count > 0 && (
                      <span className="mt-3 inline-flex w-fit items-center gap-1 text-2xs text-fidelity-medium">
                        <span
                          aria-hidden="true"
                          className="status-dot-pulse inline-block h-1.5 w-1.5 rounded-full bg-fidelity-medium"
                        />
                        {stage.blocked_count} blocked
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* ------------------------------------------------------------ */}
          {/* 4. STRATEGY COMPARISON CARDS */}
          {/* ------------------------------------------------------------ */}
          <section className="animate-fade-in space-y-6">
            <SectionHeading
              eyebrow="Strategies"
              title="Healthy vs. review vs. blocked — made obvious"
              blurb="Each strategy carries its lifecycle stage, health classification, reliability score, and primary concern so triage is instant."
            />
            {loading ? (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="rounded-card border border-border bg-bg-700 p-6 shadow-card">
                    <Skeleton className="h-5 w-1/3" />
                    <Skeleton className="mt-4 h-3 w-2/3" />
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
                    All strategies are currently healthy — nothing needs attention right now.
                  </p>
                </div>
              </Card>
            ) : (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                {attention.map((s) => (
                  <Link
                    key={s.strategy_id}
                    to={`/strategies/${s.strategy_id}`}
                    className={`card-hover-lift flex flex-col gap-3 rounded-card border-l-4 p-6 shadow-card ${healthAccent(
                      s.health_classification,
                    )} ${healthGradient(s.health_classification)}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="card-title truncate text-base">{s.name ?? "Untitled strategy"}</p>
                      {s.reliability_score !== null && (
                        <span className="metric-value shrink-0 font-mono text-base text-text-secondary">
                          {Math.round(s.reliability_score)}
                          <span className="text-2xs text-text-muted">/100</span>
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <LifecycleStageBadge stage={s.lifecycle_stage} />
                      {s.health_classification && (
                        <span
                          className={`rounded-chip border px-2 py-0.5 text-2xs font-medium uppercase tracking-eyebrow ${healthChip(
                            s.health_classification,
                          )}`}
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
                    {(s.primary_concern || s.top_blocker_title) && (
                      <p className="text-xs leading-relaxed text-text-secondary">
                        {s.primary_concern ?? s.top_blocker_title}
                      </p>
                    )}
                    <span className="text-2xs text-text-muted">Open Strategy →</span>
                  </Link>
                ))}
              </div>
            )}
          </section>

          {/* ------------------------------------------------------------ */}
          {/* 5. EVIDENCE & TRUST LAYER */}
          {/* ------------------------------------------------------------ */}
          <section className="animate-fade-in space-y-6">
            <SectionHeading
              eyebrow="Evidence & trust"
              title="Verifying the chain behind a strategy"
              accent="success"
            />
            <Card gradient="success">
              <p className="text-sm leading-relaxed text-text-secondary">
                QuantFidelity does not just store research artifacts — it verifies the evidence chain
                behind a strategy.
              </p>
              {verification ? (
                <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <div>
                    <p className="metric-value text-metric-sm text-text-primary">
                      {Math.round(verification.verification_score)}
                      <span className="text-2xs text-text-muted">/100</span>
                    </p>
                    <p className="caption mt-1.5">Verification score</p>
                  </div>
                  <div>
                    <span
                      className={`inline-flex rounded-chip border px-2 py-0.5 text-2xs font-medium uppercase tracking-eyebrow ${verdictChip(
                        verification.verdict,
                      )}`}
                    >
                      {verification.verdict.replace(/_/g, " ")}
                    </span>
                    <p className="caption mt-2">Verdict</p>
                  </div>
                  <div>
                    <span
                      className={`inline-flex rounded-chip border px-2 py-0.5 text-2xs font-medium uppercase tracking-eyebrow ${verdictChip(
                        verification.chain_status,
                      )}`}
                    >
                      {verification.chain_status.replace(/_/g, " ")}
                    </span>
                    <p className="caption mt-2">Chain status</p>
                  </div>
                  <div>
                    <p className="font-mono text-sm text-text-secondary">
                      {verification.root_hash ? verification.root_hash.slice(0, 12) : "—"}
                    </p>
                    <p className="caption mt-1.5">Root hash</p>
                  </div>
                  <div className="col-span-2 sm:col-span-4">
                    <p className="text-2xs text-text-muted">
                      {verification.tamper_warnings.length} tamper ·{" "}
                      {verification.time_consistency_warnings.length} time-consistency ·{" "}
                      {verification.link_consistency_warnings.length} link-consistency warning(s) on{" "}
                      {verification.strategy_name}.
                    </p>
                  </div>
                </div>
              ) : (
                <p className="mt-4 text-xs leading-relaxed text-text-muted">
                  {verificationConcernCount > 0
                    ? `${verificationConcernCount} ${
                        verificationConcernCount === 1 ? "strategy has" : "strategies have"
                      } evidence or reliability concerns flagged for verification across this workspace.`
                    : "Per-strategy verification detail loads on the strategy view — open a strategy to see its full evidence-chain check."}
                </p>
              )}
            </Card>
          </section>

          {/* ------------------------------------------------------------ */}
          {/* 6. BACKTEST REALITY / DRIFT LAYER */}
          {/* ------------------------------------------------------------ */}
          <section className="animate-fade-in space-y-6">
            <SectionHeading
              eyebrow="Backtest reality & drift"
              title="Does the evidence support the claim?"
              accent="warning"
            />
            <Card gradient="warning">
              <p className="text-sm leading-relaxed text-text-secondary">
                Backtests are not enough. QuantFidelity checks whether assumptions, costs, fills,
                evidence, and paper/shadow behavior support the research claim.
              </p>
              {reality ? (
                <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <div>
                    <p className="metric-value text-metric-sm text-text-primary">
                      {Math.round(reality.backtest_reality_score)}
                      <span className="text-2xs text-text-muted">/100</span>
                    </p>
                    <p className="caption mt-1.5">Backtest reality score</p>
                  </div>
                  <div>
                    <span
                      className={`inline-flex rounded-chip border px-2 py-0.5 text-2xs font-medium uppercase tracking-eyebrow ${verdictChip(
                        reality.verdict,
                      )}`}
                    >
                      {reality.verdict.replace(/_/g, " ")}
                    </span>
                    <p className="caption mt-2">Verdict</p>
                  </div>
                  <div className="sm:col-span-1">
                    <p className="text-xs leading-relaxed text-text-secondary">
                      {reality.primary_concern ?? "No single dominant concern detected."}
                    </p>
                    <p className="caption mt-2">Primary concern</p>
                  </div>
                </div>
              ) : null}
              <p className="mt-4 text-2xs leading-relaxed text-text-muted">
                Paper and shadow runs are monitored against the backtest to catch research-to-reality
                drift. These are evidence checks, not trading advice.
              </p>
            </Card>
          </section>

          {/* ------------------------------------------------------------ */}
          {/* 7. GOVERNANCE & PROMOTION READINESS */}
          {/* ------------------------------------------------------------ */}
          <section className="animate-fade-in space-y-6">
            <SectionHeading
              eyebrow="Governance"
              title="Promotion readiness for PMs & heads of research"
              blurb="Reviews and promotion gates turn evidence into a defensible go / no-go decision for moving a strategy toward production."
              accent="research"
            />
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div className="card-hover-lift gradient-border gradient-border-danger rounded-card p-6 shadow-card hover:shadow-glow-danger-lg">
                <p className="metric-value text-metric-sm text-fidelity-low">
                  {summary?.blocked_count ?? 0}
                </p>
                <p className="caption mt-2">Blocked / critical</p>
              </div>
              <div className="card-hover-lift gradient-border gradient-border-primary rounded-card p-6 shadow-card hover:shadow-glow-primary-lg">
                <p className="metric-value text-metric-sm text-accent-300">
                  {summary?.pending_review_count ?? pendingReviews.length}
                </p>
                <p className="caption mt-2">Pending reviews</p>
              </div>
              <div className="card-hover-lift gradient-border gradient-border-success rounded-card p-6 shadow-card hover:shadow-glow-success-lg">
                <p className="metric-value text-metric-sm text-fidelity-high">
                  {summary?.production_ready_count ?? 0}
                </p>
                <p className="caption mt-2">Production candidate</p>
              </div>
            </div>
            {topBlockers.length > 0 && (
              <div className="gradient-border gradient-border-research rounded-card p-6 shadow-card">
                <p className="caption mb-3">Top blockers in the book</p>
                <ul className="space-y-2">
                  {topBlockers.map((b, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                      <span
                        aria-hidden="true"
                        className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-fidelity-medium"
                      />
                      <span>{b}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="flex flex-wrap gap-3">
              <Link
                to="/governance/strategy-reviews"
                className="cta-glow rounded-control border border-accent-500/40 bg-accent-500/15 px-4 py-2 text-sm text-accent-200 hover:bg-accent-500/25"
              >
                Open Reviews
              </Link>
              <Link
                to="/promotion-gates"
                className="cta-glow rounded-control border border-border px-4 py-2 text-sm text-text-secondary hover:bg-bg-600 hover:text-text-primary hover:shadow-glow-primary"
              >
                Open Promotion
              </Link>
            </div>
          </section>

          {/* ------------------------------------------------------------ */}
          {/* 8. RESEARCH RISK NARRATIVE */}
          {/* ------------------------------------------------------------ */}
          <section className="animate-fade-in space-y-6">
            <SectionHeading
              eyebrow="Narrative"
              title="Evidence translated into a readable verdict"
              accent="research"
            />
            {narrative ? (
              <Card>
                <div className="flex flex-wrap items-center gap-3">
                  <p className="card-title text-base">{narrative.headline}</p>
                  <span
                    className={`inline-flex rounded-chip border px-2 py-0.5 text-2xs font-medium uppercase tracking-eyebrow ${verdictChip(
                      narrative.verdict,
                    )}`}
                  >
                    {narrative.verdict.replace(/_/g, " ")}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-text-secondary">
                  {narrative.narrative}
                </p>
                {narrative.primary_risks.length > 0 && (
                  <div className="mt-5 space-y-3">
                    <p className="caption">Primary risks</p>
                    {narrative.primary_risks.slice(0, 4).map((r) => (
                      <div key={r.key} className="flex items-start gap-3">
                        <span
                          className={`mt-0.5 shrink-0 rounded-chip border px-1.5 py-px text-2xs uppercase tracking-eyebrow ${narrativeSevChip(
                            r.severity,
                          )}`}
                        >
                          {r.severity}
                        </span>
                        <div className="min-w-0">
                          <p className="text-sm text-text-primary">{r.label}</p>
                          {r.evidence && (
                            <p className="mt-0.5 text-xs text-text-secondary">{r.evidence}</p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <p className="mt-5 text-2xs text-text-muted">{narrative.disclaimer}</p>
              </Card>
            ) : (
              <Card>
                <p className="text-sm leading-relaxed text-text-secondary">
                  QuantFidelity converts raw evidence, backtest checks, readiness gates, alerts, and
                  drift into a readable research governance narrative.
                </p>
                {topBlockers.length > 0 && (
                  <div className="mt-4 space-y-2">
                    <p className="caption">Top portfolio blockers right now</p>
                    {topBlockers.map((b, i) => (
                      <p key={i} className="text-xs text-text-secondary">
                        • {b}
                      </p>
                    ))}
                  </div>
                )}
              </Card>
            )}
          </section>
        </>
      )}

      {/* ---------------------------------------------------------------- */}
      {/* 9. DEMO STORY / TALKING POINTS (always shown — static copy) */}
      {/* ---------------------------------------------------------------- */}
      <section className="animate-fade-in space-y-6">
        <SectionHeading
          eyebrow="How it works"
          title="The QuantFidelity story in six steps"
          blurb="A product walkthrough of the research governance pipeline — from raw evidence to an auditable promotion decision."
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {DEMO_STORY.map((step, i) => (
            <div
              key={step.title}
              className="card-hover-lift gradient-border-hover flex flex-col rounded-card p-6 shadow-card hover:shadow-glow-primary"
            >
              <span className="metric-value text-gradient-primary text-metric-sm">{i + 1}</span>
              <p className="mt-2 text-sm font-medium text-text-primary">{step.title}</p>
              <p className="mt-2 text-xs leading-relaxed text-text-secondary">{step.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* 10. CALL TO ACTIONS (always shown) */}
      {/* ---------------------------------------------------------------- */}
      <section className="animate-fade-in space-y-6">
        <SectionHeading eyebrow="Explore" title="Where to go next" />
        <div className="flex flex-wrap gap-3">
          <Link
            to="/"
            className="cta-glow rounded-control border border-accent-500/40 bg-accent-500/15 px-4 py-2 text-sm text-accent-200 hover:bg-accent-500/25 hover:shadow-glow-primary-lg"
          >
            Open Research Command Center
          </Link>
          <Link
            to="/strategies"
            className="cta-glow rounded-control border border-border px-4 py-2 text-sm text-text-secondary hover:bg-bg-600 hover:text-text-primary hover:shadow-glow-primary"
          >
            View Strategies
          </Link>
          <Link
            to="/portfolio/reliability"
            className="cta-glow rounded-control border border-border px-4 py-2 text-sm text-text-secondary hover:bg-bg-600 hover:text-text-primary hover:shadow-glow-primary"
          >
            Open Portfolio Reliability
          </Link>
          <Link
            to="/governance/strategy-reviews"
            className="cta-glow rounded-control border border-border px-4 py-2 text-sm text-text-secondary hover:bg-bg-600 hover:text-text-primary hover:shadow-glow-primary"
          >
            Open Strategy Reviews
          </Link>
          <Link
            to="/developer/evidence-builder"
            className="cta-glow rounded-control border border-border px-4 py-2 text-sm text-text-secondary hover:bg-bg-600 hover:text-text-primary hover:shadow-glow-primary"
          >
            Upload Evidence Bundle
          </Link>
          <button
            type="button"
            onClick={() => startWalkthrough(true)}
            className="cta-glow rounded-control border border-border px-4 py-2 text-sm text-text-secondary hover:bg-bg-600 hover:text-text-primary hover:shadow-glow-primary"
          >
            Start Guided Demo
          </button>
          {canDemo && (
            <Link
              to="/admin/demo-controls"
              className="cta-glow rounded-control border border-border px-4 py-2 text-sm text-text-secondary hover:bg-bg-600 hover:text-text-primary hover:shadow-glow-primary"
            >
              Run Demo Controls
            </Link>
          )}
        </div>
      </section>

      {/* Page-level disclaimer */}
      {cc?.disclaimer && <p className="text-2xs text-text-muted">{cc.disclaimer}</p>}
    </div>
  );
}
