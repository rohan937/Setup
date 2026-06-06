// M76 Guided Demo Walkthrough — step definitions + helpers.
//
// Pure data + small helpers. No React, no API calls. The DemoWalkthrough
// component consumes these. Demo strategies are matched by name from the clean
// realistic demo seed.

import type { Strategy } from "@/types";

export const WALKTHROUGH_LS_KEY = "qf_demo_walkthrough_v2";

/** Names of the clean-realistic-demo strategies, used to resolve "Go there" links. */
export const DEMO_STRATEGY_NAMES = {
  aapl: "AAPL Mean Reversion v1",
  fxCarry: "FX Carry Strategy Q1",
  crypto: "Crypto Momentum Intraday",
  mayaKoPep: "KO/PEP Pairs Trade (Maya Test)",
} as const;

/** How a step's "Go there" button should navigate. */
export type WalkthroughTarget =
  | { kind: "route"; path: string }
  | { kind: "strategy"; nameKey: keyof typeof DEMO_STRATEGY_NAMES }
  | { kind: "best-strategy"; tab?: string };

export interface WalkthroughStep {
  /** 1-based step number. */
  step: number;
  title: string;
  /** Short plain-English explanation of what this view is. */
  explanation: string;
  /** Concrete "what to look for" bullet points. */
  lookFor: string[];
  /** Label for the navigation button. */
  goLabel: string;
  /** Where the button goes. */
  target: WalkthroughTarget;
}

export const WALKTHROUGH_STEPS: WalkthroughStep[] = [
  {
    step: 1,
    title: "Strategy Reliability Workspace",
    explanation:
      "QuantFidelity is research reliability infrastructure. It tracks evidence quality, governance, and readiness across every strategy — so risk doesn't live in spreadsheets or unreviewed notebooks. This workspace surfaces the health of your entire research portfolio.",
    lookFor: [
      "Workspace-level strategy count, alert count, and reliability trend",
      "Top Priority Actions: the most urgent evidence and governance gaps",
      "Recent timeline events across all strategies",
    ],
    goLabel: "Go to Home",
    target: { kind: "route", path: "/" },
  },
  {
    step: 2,
    title: "Portfolio Reliability View",
    explanation:
      "A PM or head of research needs to see risk across all strategies simultaneously — not one at a time. Portfolio Reliability ranks strategies by readiness, not by returns, and surfaces which are blocked, under review, or healthy enough to advance.",
    lookFor: [
      "Health classification per strategy: blocked / review / healthy",
      "Reliability score, evidence freshness, and lifecycle stage",
      "Strategies with open critical alerts appear at the top",
    ],
    goLabel: "Open Portfolio Reliability",
    target: { kind: "route", path: "/portfolio/reliability" },
  },
  {
    step: 3,
    title: "Reading a Strategy Row",
    explanation:
      "Each row in Portfolio Reliability surfaces the research risk profile without opening the strategy: lifecycle stage, top blocker, days since last run, missing report, open alerts, and pending review — everything a manager needs to make a triage decision.",
    lookFor: [
      "Lifecycle stage: research → backtest → paper candidate → shadow → production candidate",
      "Top blocker: the single most urgent problem preventing progression",
      "Pending review badge if a formal review workflow is in progress",
    ],
    goLabel: "Return to Portfolio Reliability",
    target: { kind: "route", path: "/portfolio/reliability" },
  },
  {
    step: 4,
    title: "Strategy Overview",
    explanation:
      "The Strategy Overview answers: is this strategy ready to progress, and if not, what is blocking it? It shows readiness verdict, lifecycle position, action queue, and reliability score history — all derived from the evidence the research team has logged.",
    lookFor: [
      "Readiness verdict: ready / watch / under-instrumented / blocked",
      "Lifecycle bar: current stage and the gates to reach the next",
      "Action Queue: the prioritized, deterministic list of what to address next",
    ],
    goLabel: "Open Strategy Overview",
    target: { kind: "best-strategy", tab: "overview" },
  },
  {
    step: 5,
    title: "Research Evidence",
    explanation:
      "Every strategy claim must be backed by logged evidence: version, config snapshot, universe, signals, datasets, and run history. QuantFidelity stores the evidence chain and measures its quality — coverage, freshness, and data health — so there are no invisible assumptions.",
    lookFor: [
      "Evidence coverage: which sections are linked and which are missing",
      "Data health score and signal quality score",
      "Evidence graph: how artifacts connect across the research pipeline",
    ],
    goLabel: "Open Evidence Tab",
    target: { kind: "best-strategy", tab: "evidence" },
  },
  {
    step: 6,
    title: "Runs & Shadow Monitor",
    explanation:
      "Backtests can look compelling but fail in paper or live-like operation. The Shadow Monitor compares backtest behavior against a paper or live-like run to detect research-to-reality drift: turnover spikes, drawdown deterioration, Sharpe degradation, and trade-count anomalies.",
    lookFor: [
      "Backtest vs. paper run metric comparison table",
      "Drift verdict: stable / watch / drifted / insufficient data",
      "Primary concern and suggested actions if drift is detected",
    ],
    goLabel: "Open Runs Tab",
    target: { kind: "best-strategy", tab: "runs" },
  },
  {
    step: 7,
    title: "Governance & Promotion Gates",
    explanation:
      "Before a strategy advances from backtest to paper to shadow, it must pass deterministic governance gates: regression tests, config guardrails, SLA policies, assumption reviews, and formal promotion checklists. QuantFidelity makes these gates explicit, version-controlled, and auditable.",
    lookFor: [
      "Promotion gate verdicts for the target lifecycle stage",
      "Regression test failures and config policy violations",
      "Strategy review workflow status if a review is pending",
    ],
    goLabel: "Open Governance Tab",
    target: { kind: "best-strategy", tab: "governance" },
  },
  {
    step: 8,
    title: "Reports & Exports",
    explanation:
      "A reliability report packages the strategy's evidence state, governance summary, score history, and risk flags into a reviewable artifact — for PMs, investment committees, or external reviewers. Reports are generated on demand and stored for audit trail purposes.",
    lookFor: [
      "Generate Reliability Report button",
      "Report sections: evidence coverage, backtest audit, score trend, config check",
      "Export options for offline review and sharing",
    ],
    goLabel: "Open Exports Tab",
    target: { kind: "best-strategy", tab: "exports" },
  },
  {
    step: 9,
    title: "Research Reliability Alerts",
    explanation:
      "These are not trading signals. Research Reliability Alerts fire when the evidence degrades: a regression test fails, evidence becomes stale, a report is missing, or backtest-vs-paper drift crosses a threshold. They give the research team an explicit, auditable signal that a strategy needs attention before it can progress.",
    lookFor: [
      "Alert severity: info / medium / high / critical",
      "Rule types: stale evidence, failed regression, drift detected, missing report, promotion blocked",
      "Alert status: open / acknowledged / snoozed / resolved",
    ],
    goLabel: "Open Alerts",
    target: { kind: "route", path: "/alerts" },
  },
  {
    step: 10,
    title: "Research Reliability, End to End",
    explanation:
      "QuantFidelity turns scattered research artifacts into an auditable strategy reliability workflow — from first backtest to production candidate. Evidence, governance, drift detection, reporting, and portfolio-level oversight all in one place.",
    lookFor: [
      "Use the Evidence Bundle Builder to log research artifacts without hand-writing JSON",
      "Use the Python SDK to ingest evidence from notebooks and CI pipelines",
      "Use the Action Queue on any strategy to see exactly what to address next",
    ],
    goLabel: "Back to Home",
    target: { kind: "route", path: "/" },
  },
];

/** Find a demo strategy id by its seeded name (case-insensitive). */
export function findDemoStrategyId(
  strategies: Strategy[],
  nameKey: keyof typeof DEMO_STRATEGY_NAMES,
): string | null {
  const want = DEMO_STRATEGY_NAMES[nameKey].toLowerCase();
  const match = strategies.find((s) => s.name.toLowerCase() === want);
  return match ? match.id : null;
}

/**
 * Find the best strategy to feature in the guided demo.
 * Priority:
 *   1. Active strategy with a reliability score (most evidence)
 *   2. Active strategy with the most runs
 *   3. First non-archived strategy
 *   4. null (no strategies)
 */
export function findBestStrategy(strategies: Strategy[]): Strategy | null {
  const active = strategies.filter((s) => s.status !== "archived");
  if (active.length === 0) return strategies[0] ?? null;

  // Prefer scored strategies
  const scored = active.filter((s) => s.latest_reliability_score !== null);
  if (scored.length > 0) {
    // Pick highest overall_score
    return scored.reduce((best, s) => {
      const bs = best.latest_reliability_score?.overall_score ?? 0;
      const ss = s.latest_reliability_score?.overall_score ?? 0;
      return ss > bs ? s : best;
    });
  }

  // Fallback: most runs
  const withRuns = active.filter((s) => s.run_count > 0);
  if (withRuns.length > 0) {
    return withRuns.reduce((best, s) => (s.run_count > best.run_count ? s : best));
  }

  return active[0];
}

/** True if at least the three core demo strategies are present. */
export function hasDemoStrategies(strategies: Strategy[]): boolean {
  const names = new Set(strategies.map((s) => s.name.toLowerCase()));
  return (
    names.has(DEMO_STRATEGY_NAMES.aapl.toLowerCase()) &&
    names.has(DEMO_STRATEGY_NAMES.fxCarry.toLowerCase()) &&
    names.has(DEMO_STRATEGY_NAMES.crypto.toLowerCase())
  );
}

// --- localStorage state ----------------------------------------------------

export interface WalkthroughState {
  dismissed: boolean;
  completed: boolean;
  lastStep: number;
}

export function loadWalkthroughState(): WalkthroughState {
  try {
    const raw = localStorage.getItem(WALKTHROUGH_LS_KEY);
    if (raw) return JSON.parse(raw) as WalkthroughState;
  } catch {
    /* ignore */
  }
  return { dismissed: false, completed: false, lastStep: 1 };
}

export function saveWalkthroughState(state: WalkthroughState): void {
  try {
    localStorage.setItem(WALKTHROUGH_LS_KEY, JSON.stringify(state));
  } catch {
    /* ignore */
  }
}

export function resetWalkthroughState(): void {
  try {
    localStorage.removeItem(WALKTHROUGH_LS_KEY);
  } catch {
    /* ignore */
  }
}

// --- Cross-component trigger (the panel is mounted once in AppShell) --------

const WALKTHROUGH_EVENT = "qf-walkthrough-start";

/** Trigger the guided walkthrough panel (mounted in AppShell). */
export function startWalkthrough(restart = false): void {
  if (restart) resetWalkthroughState();
  saveWalkthroughState({ dismissed: false, completed: false, lastStep: 1 });
  try {
    window.dispatchEvent(new CustomEvent(WALKTHROUGH_EVENT));
  } catch {
    /* ignore */
  }
}

/** Subscribe to walkthrough-start events. Returns an unsubscribe fn. */
export function onWalkthroughStart(handler: () => void): () => void {
  window.addEventListener(WALKTHROUGH_EVENT, handler);
  return () => window.removeEventListener(WALKTHROUGH_EVENT, handler);
}
