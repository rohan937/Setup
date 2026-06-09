import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
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
  checks: string;
  why: string;
  example: string;
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
    checks: "Portfolio-level strategy health, open alerts, pending reviews, lifecycle counts, and high-priority actions.",
    why: "A research lead should be able to see where attention is needed without opening every strategy manually.",
    example: "A strategy is blocked in backtest review while high-severity evidence alerts remain unresolved.",
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
    checks: "Strategy lifecycle, evidence, runs, reality checks, governance state, reports, and developer inputs.",
    why: "A strategy needs one source of truth across research, validation, review, and promotion.",
    example: "A strategy has strong headline metrics but unresolved promotion blockers and weak evidence health.",
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
    checks: "Datasets, signals, assumptions, configs, universes, links, hashes, and evidence-chain consistency.",
    why: "Research decisions become fragile when the underlying evidence cannot be traced or verified.",
    example: "A backtest references stale or low-health data while the signal evidence looks clean.",
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
    checks: "Costs, fills, turnover, fragility, data quality, drift, and suspicious assumptions.",
    why: "A backtest can look profitable in a chart but fail once execution and data assumptions become realistic.",
    example: "High Sharpe with low data health and missing cost assumptions gets flagged before promotion.",
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
    checks: "Review status, lifecycle stage, promotion gates, blockers, alerts, and required evidence.",
    why: "Moving a strategy forward should be based on traceable readiness, not intuition.",
    example: "A strategy cannot move to paper candidate because required gates are incomplete.",
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
    checks: "Reliability score, evidence quality, blockers, backtest reality, verification status, and next actions.",
    why: "Teams need a concise explanation of why a strategy is strong, fragile, blocked, or ready.",
    example: "A generated narrative explains that the strategy has decent performance but unresolved data-health and governance risks.",
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

const NAV: { id: string; label: string }[] = [
  { id: "product", label: "Product" },
  { id: "features", label: "Features" },
  { id: "demo", label: "Demo" },
  { id: "how-it-works", label: "How it works" },
  { id: "use-cases", label: "Use cases" },
  { id: "founder", label: "Founder" },
];

function MockChip({ label, tone }: { label: string; tone: "primary" | "success" | "warning" | "danger" | "muted" }) {
  const tones: Record<string, string> = {
    primary: "border-brand/40 bg-brand/10 text-accent-200",
    success: "border-fidelity-high/40 bg-fidelity-high/10 text-fidelity-high",
    warning: "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
    danger: "border-fidelity-low/40 bg-fidelity-low/10 text-fidelity-low",
    muted: "border-border bg-bg-800 text-text-muted",
  };
  return <span className={`rounded-chip border px-2 py-0.5 font-mono text-2xs ${tones[tone]}`}>{label}</span>;
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

// ── Reusable dark-glass modal ───────────────────────────────────────────────
interface ModalProps {
  open: boolean;
  onClose: () => void;
  labelledBy: string;
  widthClass?: string;
  children: ReactNode;
}

function Modal({ open, onClose, labelledBy, widthClass = "max-w-lg", children }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const prevActive = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      prevActive?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div
        className="animate-fade-in absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        className={`animate-slide-up gradient-border gradient-border-research relative z-10 max-h-[85vh] w-full overflow-y-auto rounded-card p-6 shadow-card shadow-glow-research outline-none sm:p-7 ${widthClass}`}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-4 top-4 flex h-8 w-8 items-center justify-center rounded-control border border-border text-text-secondary transition-colors hover:bg-bg-600 hover:text-text-primary"
        >
          ✕
        </button>
        {children}
      </div>
    </div>
  );
}

export default function Landing() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [activeFeature, setActiveFeature] = useState<Feature | null>(null);
  const [activeSection, setActiveSection] = useState<string>("product");
  const [showTop, setShowTop] = useState(false);

  const scrollToId = useCallback((id: string) => {
    setMobileOpen(false);
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const watchDemoFromModal = useCallback(() => {
    setAboutOpen(false);
    setActiveFeature(null);
    // Defer so the modal unmounts (body scroll unlocks) before scrolling.
    window.setTimeout(() => {
      const el = document.getElementById("demo");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 0);
  }, []);

  // Active-section highlight for the navbar (subtle underline/glow).
  useEffect(() => {
    const els = NAV.map((n) => document.getElementById(n.id)).filter(Boolean) as HTMLElement[];
    if (els.length === 0) return;
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) setActiveSection(e.target.id);
        });
      },
      { rootMargin: "-45% 0px -50% 0px", threshold: 0 },
    );
    els.forEach((el) => obs.observe(el));
    return () => obs.disconnect();
  }, []);

  // Back-to-top visibility.
  useEffect(() => {
    const onScroll = () => setShowTop(window.scrollY > 700);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="min-h-screen bg-bg-900 font-sans text-text-primary">
      {/* ── Sticky navbar ───────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 border-b border-border/70 bg-bg-900/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3.5">
          <button
            type="button"
            onClick={() => scrollToId("product")}
            className="flex items-center gap-2.5"
            aria-label="QuantFidelity — back to top"
          >
            <span className="h-3 w-3 rounded-[5px] bg-gradient-to-br from-brand to-research shadow-glow-primary" />
            <span className="text-sm font-bold tracking-tight">QuantFidelity</span>
          </button>

          {/* Desktop nav */}
          <nav className="hidden items-center gap-1 md:flex" aria-label="Section navigation">
            {NAV.map((n) => {
              const active = activeSection === n.id;
              return (
                <button
                  key={n.id}
                  type="button"
                  onClick={() => scrollToId(n.id)}
                  className={`relative rounded-control px-3 py-1.5 text-sm transition-colors ${
                    active ? "text-text-primary" : "text-text-secondary hover:text-text-primary"
                  }`}
                >
                  {n.label}
                  <span
                    className={`absolute inset-x-3 -bottom-0.5 h-0.5 rounded-full bg-gradient-to-r from-brand to-research transition-opacity ${
                      active ? "opacity-100 shadow-glow-primary" : "opacity-0"
                    }`}
                    aria-hidden="true"
                  />
                </button>
              );
            })}
          </nav>

          {/* Desktop right actions */}
          <div className="hidden items-center gap-2 md:flex">
            <button
              type="button"
              onClick={() => setAboutOpen(true)}
              className="rounded-control border border-border-strong px-3 py-1.5 text-sm text-text-secondary transition-colors hover:bg-bg-700 hover:text-text-primary"
            >
              What is this?
            </button>
            <a
              href={appHref("/login")}
              className="px-2.5 py-1.5 text-sm text-text-secondary transition-colors hover:text-text-primary"
            >
              Sign In
            </a>
            <a
              href={appHref("")}
              className="cta-glow rounded-control bg-brand px-4 py-1.5 text-sm font-semibold text-white hover:bg-brand-600"
            >
              Open App
            </a>
          </div>

          {/* Mobile toggle */}
          <button
            type="button"
            onClick={() => setMobileOpen((v) => !v)}
            aria-expanded={mobileOpen}
            aria-label={mobileOpen ? "Close menu" : "Open menu"}
            className="flex h-9 w-9 items-center justify-center rounded-control border border-border-strong text-text-secondary hover:text-text-primary md:hidden"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" {...stroke}>
              {mobileOpen ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
          </button>
        </div>

        {/* Mobile drawer */}
        {mobileOpen && (
          <div className="animate-fade-in border-t border-border/70 bg-bg-900/95 backdrop-blur-md md:hidden">
            <nav className="mx-auto flex max-w-6xl flex-col gap-1 px-6 py-4" aria-label="Section navigation">
              {NAV.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  onClick={() => scrollToId(n.id)}
                  className={`rounded-control px-3 py-2 text-left text-sm transition-colors ${
                    activeSection === n.id
                      ? "bg-bg-700 text-text-primary"
                      : "text-text-secondary hover:bg-bg-800 hover:text-text-primary"
                  }`}
                >
                  {n.label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => {
                  setMobileOpen(false);
                  setAboutOpen(true);
                }}
                className="rounded-control px-3 py-2 text-left text-sm text-text-secondary hover:bg-bg-800 hover:text-text-primary"
              >
                What is QuantFidelity?
              </button>
              <div className="mt-2 flex items-center gap-2">
                <a
                  href={appHref("/login")}
                  className="flex-1 rounded-control border border-border-strong px-3 py-2 text-center text-sm text-text-secondary hover:text-text-primary"
                >
                  Sign In
                </a>
                <a
                  href={appHref("")}
                  className="flex-1 rounded-control bg-brand px-3 py-2 text-center text-sm font-semibold text-white hover:bg-brand-600"
                >
                  Open App
                </a>
              </div>
            </nav>
          </div>
        )}
      </header>

      {/* ── 1. Hero (product / overview) ────────────────────────────── */}
      <section id="product" className="relative scroll-mt-24 overflow-hidden">
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

        <div className="mx-auto max-w-5xl px-6 pb-16 pt-20 text-center sm:pt-28">
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
              onClick={() => scrollToId("demo")}
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
          <button
            type="button"
            onClick={() => setAboutOpen(true)}
            className="mt-6 text-sm text-text-muted underline-offset-4 transition-colors hover:text-research-300 hover:underline"
          >
            New here? What is QuantFidelity?
          </button>
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
      <section id="features" className="mx-auto max-w-6xl scroll-mt-24 px-6 py-16">
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <button
              key={f.title}
              type="button"
              onClick={() => setActiveFeature(f)}
              aria-haspopup="dialog"
              className="card-hover-lift gradient-border gradient-border-primary group rounded-card p-6 text-left shadow-card transition-shadow hover:shadow-glow-primary-lg"
            >
              <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-[10px] border border-border-strong bg-bg-800 text-brand shadow-glow-primary transition-colors group-hover:text-research-300">
                <span className="h-6 w-6">{f.icon}</span>
              </div>
              <h3 className="text-lg font-semibold text-text-primary">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-text-secondary">{f.blurb}</p>
              <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-research-300 transition-transform group-hover:translate-x-0.5">
                View details <span aria-hidden="true">→</span>
              </span>
            </button>
          ))}
        </div>
      </section>

      {/* ── 4. Demo video ───────────────────────────────────────────── */}
      <section id="demo" className="relative scroll-mt-24 overflow-hidden py-16">
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
      <section id="how-it-works" className="mx-auto max-w-6xl scroll-mt-24 px-6 py-16">
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
      <section id="use-cases" className="mx-auto max-w-6xl scroll-mt-24 px-6 py-16">
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
      <section id="founder" className="mx-auto max-w-3xl scroll-mt-24 px-6 py-16">
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
              onClick={() => scrollToId("demo")}
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

      {/* ── Back-to-top ─────────────────────────────────────────────── */}
      {showTop && (
        <button
          type="button"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          aria-label="Back to top"
          className="animate-fade-in cta-glow fixed bottom-6 right-6 z-40 flex h-11 w-11 items-center justify-center rounded-full border border-border-strong bg-bg-800/90 text-text-secondary backdrop-blur-md hover:text-text-primary hover:shadow-glow-primary"
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5" {...stroke}>
            <path d="M12 19V5M5 12l7-7 7 7" />
          </svg>
        </button>
      )}

      {/* ── "What is QuantFidelity?" modal ──────────────────────────── */}
      <Modal open={aboutOpen} onClose={() => setAboutOpen(false)} labelledBy="about-modal-title">
        <p className="caption text-research-300">Overview</p>
        <h2 id="about-modal-title" className="mt-1 text-2xl font-bold tracking-tight">
          What is QuantFidelity?
        </h2>
        <p className="mt-4 text-sm leading-relaxed text-text-secondary">
          QuantFidelity is research reliability infrastructure for quant strategies. It helps teams
          evaluate evidence quality, backtest realism, verification chains, governance blockers, and
          promotion readiness before a strategy moves forward.
        </p>
        <div className="mt-4 rounded-card border border-border bg-bg-900/60 p-4">
          <p className="text-sm leading-relaxed text-text-secondary">
            <span className="font-semibold text-text-primary">Important: </span>
            It does not generate trading signals, give investment advice, or execute trades. It helps
            make research decisions more auditable and defensible.
          </p>
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={watchDemoFromModal}
            className="cta-glow rounded-control bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600"
          >
            Watch Demo
          </button>
          <a
            href={appHref("")}
            className="rounded-control border border-border-strong bg-bg-800 px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-bg-700 hover:text-text-primary"
          >
            Open App
          </a>
        </div>
      </Modal>

      {/* ── Feature detail modal ────────────────────────────────────── */}
      <Modal
        open={activeFeature !== null}
        onClose={() => setActiveFeature(null)}
        labelledBy="feature-modal-title"
        widthClass="max-w-xl"
      >
        {activeFeature && (
          <>
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-[10px] border border-border-strong bg-bg-800 text-brand shadow-glow-primary">
                <span className="h-6 w-6">{activeFeature.icon}</span>
              </div>
              <div>
                <p className="caption text-research-300">Feature</p>
                <h2 id="feature-modal-title" className="text-xl font-bold tracking-tight">
                  {activeFeature.title}
                </h2>
              </div>
            </div>
            <div className="mt-6 space-y-5">
              <div>
                <h3 className="text-xs font-bold uppercase tracking-eyebrow text-research-300">What it checks</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-text-secondary">{activeFeature.checks}</p>
              </div>
              <div>
                <h3 className="text-xs font-bold uppercase tracking-eyebrow text-research-300">Why it matters</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-text-secondary">{activeFeature.why}</p>
              </div>
              <div className="rounded-card border border-border bg-bg-900/60 p-4">
                <h3 className="text-xs font-bold uppercase tracking-eyebrow text-fidelity-medium">Example issue</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-text-secondary">{activeFeature.example}</p>
              </div>
            </div>
            <div className="mt-6 flex flex-wrap gap-3">
              <a
                href={appHref("")}
                className="cta-glow rounded-control bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600"
              >
                Open App
              </a>
              <button
                type="button"
                onClick={watchDemoFromModal}
                className="rounded-control border border-border-strong bg-bg-800 px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-bg-700 hover:text-text-primary"
              >
                Watch Demo
              </button>
            </div>
          </>
        )}
      </Modal>
    </div>
  );
}
