// Centralized timing + script + palette.
// Edit copy, durations, and colors here in ONE place.
//
// DARK premium AI-style product walkthrough (QuantFidelity M101-M108 aesthetic).
// 9-scene, ~72s structure.

export const FPS = 30;
export const VIDEO_DURATION_SECONDS = 72;
export const DURATION = FPS * VIDEO_DURATION_SECONDS;

const sec = (s: number) => Math.round(s * FPS);

export type SceneId =
  | "hook"
  | "hidden"
  | "commandCenter"
  | "workspace"
  | "reality"
  | "evidence"
  | "governance"
  | "system"
  | "final";

export interface SceneDef {
  id: SceneId;
  from: number;
  durationInFrames: number;
}

// 9 scenes, total 72s.
//   hook           0  -> 5   (5s)
//   hidden         5  -> 10  (5s)
//   commandCenter  10 -> 18  (8s)
//   workspace      18 -> 28  (10s)
//   reality        28 -> 39  (11s)
//   evidence       39 -> 49  (10s)
//   governance     49 -> 60  (11s)
//   system         60 -> 66  (6s)  ← Research Governance System (no screenshots)
//   final          66 -> 72  (6s)
export const SCENES: SceneDef[] = [
  {id: "hook", from: sec(0), durationInFrames: sec(5)},
  {id: "hidden", from: sec(5), durationInFrames: sec(5)},
  {id: "commandCenter", from: sec(10), durationInFrames: sec(8)},
  {id: "workspace", from: sec(18), durationInFrames: sec(10)},
  {id: "reality", from: sec(28), durationInFrames: sec(11)},
  {id: "evidence", from: sec(39), durationInFrames: sec(10)},
  {id: "governance", from: sec(49), durationInFrames: sec(11)},
  {id: "system", from: sec(60), durationInFrames: sec(6)},
  {id: "final", from: sec(66), durationInFrames: sec(6)},
];

// ---------------------------------------------------------------------------
// DARK color palette.
// New semantic keys (bg / surface / elevated / border / text*) plus
// back-compat aliases (cardBg / cardBorder) kept so legacy light-era
// components still compile and render (dark-tinted) until phase 2 rewrites
// the scenes.
// ---------------------------------------------------------------------------
export const COLORS = {
  // Surfaces
  bg: "#0B1020",
  surface: "#111827",
  elevated: "#162033",
  border: "rgba(255, 255, 255, 0.08)",

  // Text
  textPrimary: "#F8FAFC",
  textSecondary: "#94A3B8",
  textMuted: "#64748B",

  // Brand accents
  blue: "#4F8CFF",
  purple: "#8B5CF6",
  cyan: "#06B6D4",

  // Semantic
  success: "#00D492",
  warning: "#FFB547",
  danger: "#FF6B6B",

  // Back-compat aliases (legacy components reference these).
  cardBg: "#111827",
  cardBorder: "rgba(255, 255, 255, 0.08)",
} as const;

export const FONT_STACK =
  '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';

export type MetricTone = "neutral" | "primary" | "warning" | "danger" | "success";

export interface ScriptMetric {
  label: string;
  value: string;
  tone: MetricTone;
}

// ---------------------------------------------------------------------------
// Lifecycle stages (single source of truth for the pipeline component).
// ---------------------------------------------------------------------------
export interface StageDef {
  key: string;
  label: string;
}

export const STAGES: StageDef[] = [
  {key: "research", label: "Research"},
  {key: "backtestReview", label: "Backtest Review"},
  {key: "paperCandidate", label: "Paper Candidate"},
  {key: "shadow", label: "Shadow"},
  {key: "productionCandidate", label: "Production Candidate"},
];

// ---------------------------------------------------------------------------
// 404-safe screenshot allow-list.
// List ONLY filenames that actually exist in public/screenshots/.
// When a name is present here, SafeScreenshotFrame renders the real <Img>;
// otherwise it renders a polished dark mock (and never calls staticFile,
// so there are no 404 logs / decode errors).
//
// To use real screenshots: drop the PNG into public/screenshots/ and add its
// filename (e.g. "home.png") to this array.
// ---------------------------------------------------------------------------
export const AVAILABLE_SCREENSHOTS: string[] = [
  "home.png",
  "executive-demo.png",
  "strategy-overview.png",
  "reality-tab.png",
  "governance-tab.png",
];
// ---------------------------------------------------------------------------
// All on-screen copy + mock UI data lives here.
// ---------------------------------------------------------------------------
export const SCRIPT = {
  // Scene 1 — hook
  hook: {
    caption: "Your backtest says it's ready.",
    sub: "The evidence usually says otherwise.",
    // The clean-looking backtest card.
    card: {
      title: "SPY Trend Following v3",
      assetClass: "US Equities",
      metrics: [
        {label: "Sharpe", value: "1.42", tone: "success"},
        {label: "CAGR", value: "18.6%", tone: "success"},
        {label: "Max Drawdown", value: "-9.1%", tone: "success"},
        {label: "Win Rate", value: "61%", tone: "success"},
      ] as ScriptMetric[],
      badge: "Looks production-ready",
    },
  },

  // Scene 2 — hidden problems
  hidden: {
    caption: "But the assumptions are doing all the work.",
    sub: "QuantFidelity surfaces what reviews miss.",
    warnings: [
      {label: "Transaction costs", value: "0 bps assumed", tone: "danger"},
      {label: "Turnover", value: "1.8x — frictionless", tone: "warning"},
      {label: "Paper / shadow run", value: "Missing", tone: "danger"},
      {label: "Evidence chain", value: "Incomplete", tone: "warning"},
    ] as ScriptMetric[],
  },

  // Scene 3 — research command center
  commandCenter: {
    caption: "One command center for every strategy.",
    sub: "Reliability, readiness, and risk — at a glance.",
    summary: [
      {label: "Strategies tracked", value: "42", tone: "primary"},
      {label: "Avg reliability", value: "74.3", tone: "warning"},
      {label: "Promotion-ready", value: "9", tone: "success"},
      {label: "Blocked on gates", value: "11", tone: "danger"},
    ] as ScriptMetric[],
    strategies: [
      {name: "SPY Trend Following v3", stage: "Backtest Review", score: 72},
      {name: "Cross-Asset Carry", stage: "Paper Candidate", score: 81},
      {name: "EM FX Momentum", stage: "Research", score: 58},
      {name: "Vol Risk Premium", stage: "Shadow", score: 88},
    ],
  },

  // Scene 4 — strategy workspace
  workspace: {
    caption: "Open a strategy. The whole story is in one place.",
    sub: "Reliability, reality, evidence — scored and reviewable.",
    strategyName: "SPY Trend Following v3",
    scoreCards: [
      {label: "Reliability", value: "88.8", verdict: undefined, tone: "success"},
      {label: "Readiness", value: undefined, verdict: "Review", tone: "warning"},
      {label: "Backtest Reality", value: "72", verdict: undefined, tone: "warning"},
      {label: "Evidence", value: undefined, verdict: "Verified", tone: "success"},
    ],
    tabs: ["Overview", "Evidence", "Reality", "Lineage", "Governance", "Reports"],
    currentStageKey: "backtestReview",
  },

  // Scene 5 — backtest reality check
  reality: {
    caption: "Backtest Reality Check pressure-tests the assumptions.",
    sub: "A believable backtest — or a flattering one?",
    panel: {
      score: 72,
      max: 100,
      verdict: "Review",
      primaryConcern:
        "High turnover combined with zero modeled transaction costs.",
      checks: [
        {label: "Out-of-sample window present", tone: "success"},
        {label: "Drawdown profile plausible", tone: "success"},
        {label: "Turnover priced with realistic costs", tone: "warning"},
        {label: "Slippage / market impact modeled", tone: "warning"},
        {label: "Paper / shadow confirmation", tone: "danger"},
      ] as {label: string; tone: MetricTone}[],
      tooltip: {
        title: "Turnover 1.8x",
        body: "At 0 bps, ~140 bps/yr of realistic cost is hidden. Sharpe likely overstated.",
      },
    },
  },

  // Scene 6 — evidence verification
  evidence: {
    caption: "Every result is anchored to verifiable evidence.",
    sub: "Snapshots, configs, and a tamper-evident root hash.",
    panel: {
      score: 91,
      max: 100,
      status: "Verified",
      rows: [
        {label: "Dataset snapshot linked", tone: "success"},
        {label: "Signal definition linked", tone: "success"},
        {label: "Config snapshot linked", tone: "success"},
        {label: "Universe snapshot linked", tone: "success"},
        {label: "Root hash generated", tone: "success"},
      ] as {label: string; tone: MetricTone}[],
      warning: "Paper / shadow evidence not yet attached.",
      rootHash: "0x9f3a…c7e1",
    },
  },

  // Scene 7 — governance / promotion readiness
  governance: {
    caption: "Promotion is a governed decision — not a hunch.",
    sub: "Gates, evidence, and an auto-generated risk narrative.",
    panel: {
      title: "Promotion Readiness",
      target: "Paper Candidate",
      gates: [
        {label: "Reliability ≥ 70", tone: "success"},
        {label: "Reality check passed", tone: "warning"},
        {label: "Evidence chain verified", tone: "success"},
        {label: "Cost assumptions justified", tone: "warning"},
        {label: "Reviewer sign-off", tone: "danger"},
      ] as {label: string; tone: MetricTone}[],
      buttonLabel: "Generate Research Risk Narrative",
      narrative:
        "SPY Trend Following v3 shows strong reliability (88.8) and a verified evidence chain, but reality scoring (72) flags unrealistic cost assumptions at 1.8x turnover. Promotion to Paper Candidate is recommended only after transaction costs are modeled and a paper run is attached. Residual risk: live performance may underperform backtest Sharpe by an estimated 0.3–0.5.",
    },
  },

  // Scene 8 — Research Governance System (screenshot-free system diagram)
  system: {
    caption: "From raw research to a decision you can defend.",
    kicker: "Research Governance System",
    // The governed workflow, end to end.
    pipeline: ["Evidence", "Reality", "Verification", "Governance", "Promotion"],
    // The six QuantFidelity modules that light up beneath the pipeline.
    modules: [
      "Reliability Score",
      "Backtest Reality",
      "Evidence Verification",
      "Shadow Drift",
      "Risk Narrative",
      "Promotion Packet",
    ],
  },

  // Scene 9 — final / brand
  final: {
    title: "A reliability layer for quant research.",
    subtitle: "Evidence. Reality. Verification. Governance.",
    brand: "QuantFidelity",
    systemMap: ["Evidence", "Reality", "Verification", "Governance", "Promotion"],
    disclaimer: "Research governance summary. Not trading advice.",
  },
} as const;
