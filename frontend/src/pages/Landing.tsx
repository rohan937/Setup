import { useCallback } from "react";
import { appHref } from "@/lib/domain";

// ---------------------------------------------------------------------------
// Public marketing landing page (quantfidelity.com / www).
// Standalone — does NOT use the app shell (no sidebar / topbar). Pure static
// content + cross-subdomain CTAs to app.quantfidelity.com. No API calls.
// Dark premium quant-infrastructure aesthetic using the M101-M108 tokens.
// All motion is subtle and reduced-motion friendly (global prefers-reduced
// -motion guard neutralizes animation durations).
// ---------------------------------------------------------------------------

const VIDEO_SRC = "/videos/quantfidelity-ai-product-walkthrough.mp4";

// Minimal, tasteful line-icons (stroke style, currentColor).
const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

interface Feature {
  title: string;
  blurb: string;
  icon: JSX.Element;
}

const FEATURES: Feature[] = [
  {
    title: "Research Command Center",
    blurb: "Portfolio-level view of strategy health, alerts, reviews, and pending actions.",
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
      </svg>
    ),
  },
  {
    title: "Strategy Workspace",
    blurb: "Inspect a strategy's lifecycle, evidence, runs, reality checks, governance, and reports in one place.",
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <path d="M4 7l8-4 8 4-8 4-8-4z" />
        <path d="M4 12l8 4 8-4" />
        <path d="M4 17l8 4 8-4" />
      </svg>
    ),
  },
  {
    title: "Evidence Verification",
    blurb: "Verify whether datasets, signals, assumptions, and run evidence form a trustworthy chain.",
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
    ),
  },
  {
    title: "Backtest Reality Check",
    blurb: "Flag unrealistic backtests, fragile assumptions, cost/fill gaps, and suspicious performance.",
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <path d="M3 12a9 9 0 1 1 18 0" />
        <path d="M12 12l4-3" />
        <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
      </svg>
    ),
  },
  {
    title: "Promotion Readiness",
    blurb: "See what blocks a strategy from moving from research to paper, shadow, or production candidate.",
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <path d="M12 3c3 2.5 5 6 5 9a5 5 0 0 1-10 0c0-3 2-6.5 5-9z" />
        <path d="M9 21h6" />
        <circle cx="12" cy="11" r="1.6" />
      </svg>
    ),
  },
  {
    title: "Risk Narrative",
    blurb: "Generate research-governance summaries that explain strengths, risks, blockers, and next actions.",
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <path d="M5 4h11l3 3v13H5z" />
        <path d="M8 9h7M8 13h7M8 17h4" />
      </svg>
    ),
  },
];

const PIPELINE: { stage: string; desc: string }[] = [
  { stage: "Evidence", desc: "Collect datasets, signals, assumptions, configs, universes, and run metadata." },
  { stage: "Reality", desc: "Check whether the backtest is believable under costs, fills, fragility, and drift." },
  { stage: "Verification", desc: "Validate evidence chains, links, hashes, and consistency." },
  { stage: "Governance", desc: "Surface blockers, review queues, alerts, and promotion gates." },
  { stage: "Promotion", desc: "Move only research that is explainable, reviewed, and ready." },
];

const PROBLEM_POINTS = [
  "Strong-looking results can hide weak or incomplete evidence.",
  "Assumptions and data issues often live outside the backtest chart.",
  "Promotion decisions need a traceable review history.",
  "Teams need to know what changed, what broke, and what is missing.",
];

const BEFORE = [
  "Research evidence scattered across files, notebooks, dashboards, and memory",
  "Unclear whether a strategy is actually ready",
  "Weak assumptions hidden behind clean performance charts",
  "Promotion blockers discovered late",
  "No single research audit trail",
];

const AFTER = [
  "Evidence quality is visible",
  "Reality checks surface fragile backtests",
  "Verification chains show what is trusted",
  "Governance blockers are explicit",
  "Promotion decisions become defensible",
];

const AUDIENCE = [
  { title: "Quant researchers", blurb: "Keep evidence, assumptions, and runs auditable as research evolves." },
  { title: "Portfolio managers", blurb: "See which strategies are ready, blocked, or under review at a glance." },
  { title: "Research engineers", blurb: "Wire evidence and reality checks into the research-to-production pipeline." },
  { title: "Risk / governance teams", blurb: "Enforce promotion gates and keep a defensible review trail." },
  { title: "Student teams & small funds", blurb: "Run rigorous, promotion-ready research without heavyweight tooling." },
];

const USE_CASES = [
  "Review a strategy before paper trading",
  "Detect missing evidence before promotion",
  "Explain why a backtest is fragile",
  "Track paper / shadow drift",
  "Generate a research risk narrative",
  "Prepare a promotion packet",
];

const IS_NOT = [
  "A trading signal provider",
  "Investment advice",
  "A broker or execution platform",
  "A black-box strategy generator",
];

const IS = [
  "Research reliability infrastructure",
  "Evidence tracking",
  "Governance workflow",
  "Promotion-readiness monitoring",
];

// Stylized, illustrative product-surface mock cards (no screenshots → no broken
// image refs; mirrors the in-app demo, not a performance claim).
function MockChip({ label, tone }: { label: string; tone: "primary" | "success" | "warning" | "danger" | "muted" }) {
  const tones: Record<string, string> = {
    primary: "border-brand/40 bg-brand/10 text-accent-200",
    success: "border-fidelity-high/40 bg-fidelity-high/10 text-fidelity-high",
    warning: "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
    danger: "border-fidelity-low/40 bg-fidelity-low/10 text-fidelity-low",
    muted: "border-border bg-bg-800 text-text-muted",
  };
  return (
    <span className={`rounded-chip border px-2 py-0.5 font-mono text-2xs ${tones[tone]}`}>{label}</span>
  );
}

interface Surface {
  label: string;
  title: string;
  body: JSX.Element;
}

const SURFACES: Surface[] = [
  {
    label: "Research Command Center",
    title: "Portfolio health",
    body: (
      <div className="space-y-2">
        <div className="flex flex-wrap gap-1.5">
          <MockChip label="42 strategies" tone="primary" />
          <MockChip label="9 ready" tone="success" />
          <MockChip label="11 blocked" tone="danger" />
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-800">
          <div className="h-full w-2/3 rounded-full bg-gradient-to-r from-brand to-research" />
        </div>
        <p className="text-2xs text-text-muted">Avg reliability 74.3 · 5 open alerts</p>
      </div>
    ),
  },
  {
    label: "Strategy Workspace",
    title: "Global Futures Trend Model",
    body: (
      <div className="space-y-2">
        <div className="flex flex-wrap gap-1.5">
          <MockChip label="Reliability 70" tone="warning" />
          <MockChip label="Backtest Review" tone="muted" />
        </div>
        <div className="flex flex-wrap gap-1.5">
          <MockChip label="Evidence: verified" tone="success" />
          <MockChip label="Paper/shadow: missing" tone="danger" />
        </div>
        <p className="text-2xs text-text-muted">Lifecycle · evidence · runs · governance</p>
      </div>
    ),
  },
  {
    label: "Reality Check",
    title: "Backtest believability",
    body: (
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-2xs text-text-secondary">
          <span>Out-of-sample window</span>
          <MockChip label="ok" tone="success" />
        </div>
        <div className="flex items-center justify-between text-2xs text-text-secondary">
          <span>Costs modeled vs turnover</span>
          <MockChip label="review" tone="warning" />
        </div>
        <div className="flex items-center justify-between text-2xs text-text-secondary">
          <span>Paper / shadow confirmation</span>
          <MockChip label="missing" tone="danger" />
        </div>
      </div>
    ),
  },
  {
    label: "Governance Queue",
    title: "Promotion readiness",
    body: (
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-2xs text-text-secondary">
          <span>Reliability ≥ 70</span>
          <MockChip label="pass" tone="success" />
        </div>
        <div className="flex items-center justify-between text-2xs text-text-secondary">
          <span>Reality check passed</span>
          <MockChip label="review" tone="warning" />
        </div>
        <div className="flex items-center justify-between text-2xs text-text-secondary">
          <span>Reviewer sign-off</span>
          <MockChip label="blocked" tone="danger" />
        </div>
      </div>
    ),
  },
];

export default function Landing() {
  const scrollToDemo = useCallback(() => {
    const el = document.getElementById("demo");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  return (
    <div className="min-h-screen bg-bg-900 font-sans text-text-primary">
      {/* ── Slim header ─────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b border-border/70 bg-bg-900/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2.5">
            <span className="h-3 w-3 rounded-[5px] bg-gradient-to-br from-brand to-research shadow-glow-primary" />
            <span className="text-sm font-bold tracking-tight">QuantFidelity</span>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <a
              href={appHref("/login")}
              className="hidden text-text-secondary transition-colors hover:text-text-primary sm:inline"
            >
              Sign In
            </a>
            <a
              href={appHref("")}
              className="cta-glow rounded-control bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600"
            >
              Open App
            </a>
          </div>
        </div>
      </header>

      {/* ── 1. Hero ─────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 -z-10" aria-hidden="true">
          <div className="animate-hero-drift absolute -top-24 left-0 right-0 h-[28rem] bg-grad-hero opacity-70 blur-2xl" />
          <div className="animate-hero-drift absolute -top-32 left-1/4 h-80 w-80 rounded-full bg-brand/15 blur-3xl" />
          <div
            className="animate-hero-drift absolute -top-20 left-1/2 h-72 w-72 rounded-full bg-research/15 blur-3xl"
            style={{ animationDelay: "-8s" }}
          />
          <div
            className="animate-hero-drift absolute -top-24 right-1/4 h-64 w-64 rounded-full bg-teal-500/12 blur-3xl"
            style={{ animationDelay: "-4s" }}
          />
        </div>

        <div className="mx-auto max-w-5xl px-6 pb-16 pt-24 text-center sm:pt-32">
          <div className="animate-fade-in">
            <span className="caption inline-block rounded-chip border border-border-strong bg-bg-800/70 px-3 py-1 text-research-300">
              Research reliability infrastructure
            </span>
          </div>
          <h1 className="animate-slide-up mt-6 text-5xl font-extrabold tracking-tight sm:text-7xl">
            Quant<span className="bg-gradient-to-r from-brand to-research bg-clip-text text-transparent">Fidelity</span>
          </h1>
          <p className="animate-slide-up mt-5 text-2xl font-semibold text-text-primary sm:text-3xl">
            A reliability layer for quant research.
          </p>
          <p className="mt-4 font-mono text-sm uppercase tracking-eyebrow text-research-300">
            Know what changed. Know what is missing. Know what is ready.
          </p>
          <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-text-secondary">
            QuantFidelity helps research teams evaluate strategy evidence, backtest reality,
            verification quality, paper/shadow drift, and promotion readiness before a strategy
            moves forward.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <a
              href={appHref("")}
              className="cta-glow rounded-control bg-brand px-6 py-3 text-base font-semibold text-white hover:bg-brand-600 hover:shadow-glow-primary-lg"
            >
              Open App
            </a>
            <button
              type="button"
              onClick={scrollToDemo}
              className="rounded-control border border-border-strong bg-bg-800 px-6 py-3 text-base font-medium text-text-secondary transition-colors hover:bg-bg-700 hover:text-text-primary"
            >
              Watch Demo
            </button>
            <a
              href={appHref("/login")}
              className="px-3 py-3 text-base font-medium text-text-muted transition-colors hover:text-text-primary"
            >
              Sign In
            </a>
          </div>
        </div>
      </section>

      {/* ── 2. Trust / live product strip ───────────────────────────── */}
      <section className="mx-auto max-w-5xl px-6 pb-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: "Live demo workspace", live: false },
            { label: "API online", live: true },
            { label: "Research governance infrastructure", live: false },
            { label: "Not trading advice", live: false },
          ].map((b) => (
            <div
              key={b.label}
              className="flex items-center gap-2 rounded-card border border-border bg-bg-800/60 px-3 py-2.5 shadow-card"
            >
              <span
                className={`h-2 w-2 flex-shrink-0 rounded-full ${
                  b.live
                    ? "animate-soft-pulse bg-fidelity-high shadow-glow-success"
                    : "bg-gradient-to-r from-brand to-research"
                }`}
                aria-hidden="true"
              />
              <span className="text-2xs font-medium leading-tight text-text-secondary">{b.label}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ── 3. Feature cards ────────────────────────────────────────── */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="card-hover-lift gradient-border gradient-border-primary group rounded-card p-6 shadow-card transition-shadow hover:shadow-glow-primary-lg"
            >
              <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-[10px] border border-border-strong bg-bg-800 text-brand shadow-glow-primary transition-colors group-hover:text-research-300">
                <span className="h-6 w-6">{f.icon}</span>
              </div>
              <h3 className="text-lg font-semibold text-text-primary">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-text-secondary">{f.blurb}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── 4. Demo video ───────────────────────────────────────────── */}
      <section id="demo" className="relative scroll-mt-20 overflow-hidden py-16">
        <div
          className="pointer-events-none absolute left-1/2 top-1/2 -z-10 h-96 w-[42rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-research/10 blur-3xl"
          aria-hidden="true"
        />
        <div className="mx-auto max-w-5xl px-6 text-center">
          <p className="caption text-research-300">Product walkthrough</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
            From raw research evidence to a decision you can defend
          </h2>
          <div className="mx-auto mt-8 gradient-border gradient-border-research overflow-hidden rounded-card bg-bg-700 p-2 shadow-card shadow-glow-research">
            <video
              controls
              playsInline
              preload="metadata"
              className="block w-full rounded-[10px] bg-bg-900"
              src={VIDEO_SRC}
            >
              Your browser does not support the video tag.
            </video>
          </div>
          <p className="mx-auto mt-4 max-w-2xl font-mono text-2xs italic text-text-muted">
            A 70-second walkthrough from raw research evidence to a promotion decision you can defend.
          </p>
          <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
            <a
              href={appHref("")}
              className="cta-glow rounded-control bg-brand px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-600"
            >
              Open App
            </a>
            <a
              href={appHref("/executive-demo")}
              className="rounded-control border border-border-strong bg-bg-800 px-5 py-2.5 text-sm font-medium text-text-secondary transition-colors hover:bg-bg-700 hover:text-text-primary"
            >
              Explore Executive Demo
            </a>
          </div>
        </div>
      </section>

      {/* ── 5. Problem / why it matters ─────────────────────────────── */}
      <section className="mx-auto max-w-5xl px-6 py-16">
        <div className="rounded-card border border-border bg-bg-800/60 p-8 sm:p-10">
          <h2 className="text-3xl font-bold tracking-tight">
            Backtests are easy to show. Research reliability is harder to prove.
          </h2>
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
            {PROBLEM_POINTS.map((p) => (
              <div key={p} className="flex gap-3">
                <span
                  className="mt-2 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-gradient-to-r from-brand to-research"
                  aria-hidden="true"
                />
                <p className="text-base leading-relaxed text-text-secondary">{p}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── 6. Before vs After ──────────────────────────────────────── */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <div className="text-center">
          <p className="caption text-research-300">Before / after</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight">From scattered evidence to defensible decisions</h2>
        </div>
        <div className="mt-10 grid grid-cols-1 gap-5 lg:grid-cols-2">
          {/* Before */}
          <div className="rounded-card border border-fidelity-low/30 bg-fidelity-low/[0.04] p-7 shadow-card">
            <div className="mb-4 flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-fidelity-low/80" aria-hidden="true" />
              <h3 className="text-sm font-bold uppercase tracking-eyebrow text-fidelity-low">Before QuantFidelity</h3>
            </div>
            <ul className="space-y-3">
              {BEFORE.map((b) => (
                <li key={b} className="flex gap-2.5 text-sm leading-relaxed text-text-secondary">
                  <span className="mt-0.5 text-fidelity-low" aria-hidden="true">✕</span>
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          </div>
          {/* After */}
          <div className="gradient-border gradient-border-success rounded-card p-7 shadow-card shadow-glow-success">
            <div className="mb-4 flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-fidelity-high shadow-glow-success" aria-hidden="true" />
              <h3 className="text-sm font-bold uppercase tracking-eyebrow text-fidelity-high">After QuantFidelity</h3>
            </div>
            <ul className="space-y-3">
              {AFTER.map((a) => (
                <li key={a} className="flex gap-2.5 text-sm leading-relaxed text-text-primary">
                  <span className="mt-0.5 text-fidelity-high" aria-hidden="true">✓</span>
                  <span>{a}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* ── 7. How it works pipeline ────────────────────────────────── */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <div className="text-center">
          <p className="caption text-research-300">How it works</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight">
            Evidence → Reality → Verification → Governance → Promotion
          </h2>
        </div>
        <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {PIPELINE.map((p, i) => (
            <div key={p.stage} className="relative rounded-card border border-border bg-bg-700 p-5 shadow-card">
              <div className="flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-brand to-research text-xs font-bold text-white">
                  {i + 1}
                </span>
                <h3 className="text-sm font-bold text-text-primary">{p.stage}</h3>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-text-secondary">{p.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── 8. Interface preview / product surfaces ─────────────────── */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <div className="text-center">
          <p className="caption text-research-300">Inside the product</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight">Product surfaces built for research reliability</h2>
        </div>
        <div className="mt-10 grid grid-cols-1 gap-5 sm:grid-cols-2">
          {SURFACES.map((s) => (
            <div
              key={s.label}
              className="card-hover-lift gradient-border gradient-border-research overflow-hidden rounded-card shadow-card hover:shadow-glow-research"
            >
              {/* window chrome */}
              <div className="flex items-center gap-1.5 border-b border-border/70 bg-bg-800/80 px-4 py-2.5">
                <span className="h-2.5 w-2.5 rounded-full bg-fidelity-low/60" />
                <span className="h-2.5 w-2.5 rounded-full bg-fidelity-medium/60" />
                <span className="h-2.5 w-2.5 rounded-full bg-fidelity-high/60" />
                <span className="ml-2 font-mono text-2xs uppercase tracking-eyebrow text-text-muted">{s.label}</span>
              </div>
              <div className="space-y-3 p-5">
                <p className="text-sm font-semibold text-text-primary">{s.title}</p>
                {s.body}
              </div>
            </div>
          ))}
        </div>
        <p className="mt-4 text-center font-mono text-2xs italic text-text-muted">
          Illustrative product surfaces from the demo workspace. Not a performance claim.
        </p>
      </section>

      {/* ── 9. Who it is for ────────────────────────────────────────── */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <div className="text-center">
          <p className="caption text-research-300">Who it is for</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight">
            Built for teams that need research decisions to be explainable
          </h2>
        </div>
        <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {AUDIENCE.map((a) => (
            <div key={a.title} className="card-hover-lift rounded-card border border-border bg-bg-700 p-6 shadow-card">
              <div className="mb-3 h-1 w-10 rounded-full bg-gradient-to-r from-brand to-research" />
              <h3 className="text-base font-semibold text-text-primary">{a.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-text-secondary">{a.blurb}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── 10. Example workflows / use cases ───────────────────────── */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <div className="text-center">
          <p className="caption text-research-300">Example workflows</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight">What teams do with QuantFidelity</h2>
        </div>
        <div className="mt-10 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {USE_CASES.map((u, i) => (
            <div
              key={u}
              className="flex items-center gap-3 rounded-card border border-border bg-bg-800/60 px-5 py-4 shadow-card transition-colors hover:border-border-strong"
            >
              <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[8px] border border-border-strong bg-bg-900 font-mono text-2xs text-research-300">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="text-sm font-medium text-text-secondary">{u}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ── 11. What QuantFidelity is / is not ──────────────────────── */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <div className="text-center">
          <p className="caption text-research-300">Honest scope</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight">What QuantFidelity is — and is not</h2>
        </div>
        <div className="mt-10 grid grid-cols-1 gap-5 lg:grid-cols-2">
          <div className="rounded-card border border-border bg-bg-800/50 p-7 shadow-card">
            <h3 className="mb-4 text-sm font-bold uppercase tracking-eyebrow text-text-muted">Not</h3>
            <ul className="space-y-3">
              {IS_NOT.map((x) => (
                <li key={x} className="flex gap-2.5 text-sm leading-relaxed text-text-secondary">
                  <span className="mt-0.5 text-fidelity-low" aria-hidden="true">✕</span>
                  <span>{x}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="gradient-border gradient-border-primary rounded-card p-7 shadow-card hover:shadow-glow-primary-lg">
            <h3 className="mb-4 text-sm font-bold uppercase tracking-eyebrow text-research-300">Is</h3>
            <ul className="space-y-3">
              {IS.map((x) => (
                <li key={x} className="flex gap-2.5 text-sm leading-relaxed text-text-primary">
                  <span className="mt-0.5 text-fidelity-high" aria-hidden="true">✓</span>
                  <span>{x}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* ── 12. Founder / About ─────────────────────────────────────── */}
      <section className="mx-auto max-w-3xl px-6 py-16">
        <div className="gradient-border gradient-border-research rounded-card p-8 text-center shadow-card sm:p-10">
          <p className="caption text-research-300">Built by</p>
          <h2 className="mt-2 text-2xl font-bold tracking-tight">Rohan Shah</h2>
          <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-text-secondary">
            Rohan Shah is a student at UMass Amherst building QuantFidelity to make quant research
            more reliable, auditable, and promotion-ready.
          </p>
          <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-text-muted">
            The product is focused on the infrastructure layer between research results and real
            deployment decisions.
          </p>
        </div>
      </section>

      {/* ── 13. Final CTA ───────────────────────────────────────────── */}
      <section className="relative overflow-hidden py-20">
        <div
          className="animate-hero-drift pointer-events-none absolute inset-0 -z-10 bg-grad-hero opacity-50 blur-2xl"
          aria-hidden="true"
        />
        <div className="mx-auto max-w-4xl px-6 text-center">
          <h2 className="text-3xl font-extrabold tracking-tight sm:text-5xl">
            Know what changed. Know what is missing. Know what is ready.
          </h2>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <a
              href={appHref("")}
              className="cta-glow rounded-control bg-brand px-6 py-3 text-base font-semibold text-white hover:bg-brand-600 hover:shadow-glow-primary-lg"
            >
              Open App
            </a>
            <button
              type="button"
              onClick={scrollToDemo}
              className="rounded-control border border-border-strong bg-bg-800 px-6 py-3 text-base font-medium text-text-secondary transition-colors hover:bg-bg-700 hover:text-text-primary"
            >
              Watch Demo
            </button>
            <a
              href={appHref("/login")}
              className="px-3 py-3 text-base font-medium text-text-muted transition-colors hover:text-text-primary"
            >
              Sign In
            </a>
          </div>
        </div>
      </section>

      {/* ── Footer ──────────────────────────────────────────────────── */}
      <footer className="border-t border-border/70">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 py-8 sm:flex-row">
          <div className="flex items-center gap-2.5">
            <span className="h-2.5 w-2.5 rounded-[4px] bg-gradient-to-br from-brand to-research" />
            <span className="text-sm font-semibold">QuantFidelity</span>
          </div>
          <p className="font-mono text-2xs text-text-muted">
            A reliability layer for quant research. Not trading advice.
          </p>
        </div>
      </footer>
    </div>
  );
}
