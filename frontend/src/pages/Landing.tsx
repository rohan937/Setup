import { useCallback } from "react";
import { appHref } from "@/lib/domain";

// ---------------------------------------------------------------------------
// Public marketing landing page (quantfidelity.com / www).
// Standalone — does NOT use the app shell (no sidebar / topbar). Pure static
// content + cross-subdomain CTAs to app.quantfidelity.com. No API calls.
// Dark premium quant-infrastructure aesthetic using the M101-M108 tokens.
// ---------------------------------------------------------------------------

const VIDEO_SRC = "/videos/quantfidelity-ai-product-walkthrough.mp4";

interface Feature {
  title: string;
  blurb: string;
  icon: JSX.Element;
}

// Minimal, tasteful line-icons (stroke style, currentColor).
const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const FEATURES: Feature[] = [
  {
    title: "Research Command Center",
    blurb:
      "Portfolio-level view of strategy health, alerts, reviews, and pending actions.",
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
    blurb:
      "One place to inspect a strategy's lifecycle, evidence, runs, reality checks, governance, and reports.",
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
    blurb:
      "Verify whether datasets, signals, assumptions, and run evidence form a trustworthy chain.",
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
    ),
  },
  {
    title: "Backtest Reality Check",
    blurb:
      "Flag unrealistic backtests, fragile assumptions, cost/fill gaps, and suspicious performance.",
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
    blurb:
      "See what blocks a strategy from moving from research to paper, shadow, or production candidate.",
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
    blurb:
      "Generate research-governance summaries that explain strengths, risks, blockers, and next actions.",
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <path d="M5 4h11l3 3v13H5z" />
        <path d="M8 9h7M8 13h7M8 17h4" />
      </svg>
    ),
  },
];

const PIPELINE: { stage: string; desc: string }[] = [
  {
    stage: "Evidence",
    desc: "Collect datasets, signals, assumptions, configs, universes, and run metadata.",
  },
  {
    stage: "Reality",
    desc: "Check whether the backtest is believable under costs, fills, fragility, and drift.",
  },
  {
    stage: "Verification",
    desc: "Validate evidence chains, links, hashes, and consistency.",
  },
  {
    stage: "Governance",
    desc: "Surface blockers, review queues, alerts, and promotion gates.",
  },
  {
    stage: "Promotion",
    desc: "Move only research that is explainable, reviewed, and ready.",
  },
];

const PROBLEM_POINTS = [
  "Strategy results can look strong while evidence is incomplete.",
  "Data issues and assumptions often live outside the backtest chart.",
  "Promotion decisions need a traceable research record.",
  "Teams need a way to see what changed, what broke, and what is missing.",
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
        {/* Ambient glow */}
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

        <div className="mx-auto max-w-5xl px-6 pb-20 pt-24 text-center sm:pt-32">
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

      {/* ── 2. Feature cards ────────────────────────────────────────── */}
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

      {/* ── 3. Demo video ───────────────────────────────────────────── */}
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

      {/* ── 4. Problem / why it matters ─────────────────────────────── */}
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

      {/* ── 5. How it works pipeline ────────────────────────────────── */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <div className="text-center">
          <p className="caption text-research-300">How it works</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight">
            Evidence → Reality → Verification → Governance → Promotion
          </h2>
        </div>
        <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {PIPELINE.map((p, i) => (
            <div
              key={p.stage}
              className="relative rounded-card border border-border bg-bg-700 p-5 shadow-card"
            >
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

      {/* ── 6. Founder / About ──────────────────────────────────────── */}
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

      {/* ── 7. Final CTA ────────────────────────────────────────────── */}
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
