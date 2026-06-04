// M76 Guided Demo Walkthrough — step definitions + helpers.
//
// Pure data + small helpers. No React, no API calls. The DemoWalkthrough
// component consumes these. Demo strategies are matched by name from the clean
// realistic demo seed.

import type { Strategy } from "@/types";

export const WALKTHROUGH_LS_KEY = "qf_demo_walkthrough_v1";

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
  | { kind: "strategy"; nameKey: keyof typeof DEMO_STRATEGY_NAMES };

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
    title: "Start at the Dashboard",
    explanation:
      "This is the workspace-level health view — strategy counts, reliability, alerts, and the top priority actions across the research portfolio.",
    lookFor: [
      "Total strategies and total runs",
      "Open alerts and reliability pillars",
      "The Top Priority Actions card — what needs attention first",
    ],
    goLabel: "Open Dashboard",
    target: { kind: "route", path: "/" },
  },
  {
    step: 2,
    title: "Compare strategies in Portfolio",
    explanation:
      "The Portfolio answers: which strategies are ready, which require review, and which are unsafe to progress? Each row shows health and lifecycle stage.",
    lookFor: [
      "AAPL Mean Reversion — healthy, well-instrumented",
      "FX Carry Strategy — review, stale evidence and trust issues",
      "Crypto Momentum — blocked, under-instrumented",
    ],
    goLabel: "Open Portfolio",
    target: { kind: "route", path: "/portfolio" },
  },
  {
    step: 3,
    title: "Open the healthy example — AAPL",
    explanation:
      "AAPL Mean Reversion is the mature, well-instrumented strategy. It demonstrates what good evidence looks like.",
    lookFor: [
      "High evidence coverage and high trust",
      "Low / no open alerts",
      "A lifecycle bar that has advanced furthest",
    ],
    goLabel: "Open AAPL Mean Reversion",
    target: { kind: "strategy", nameKey: "aapl" },
  },
  {
    step: 4,
    title: "Open the review example — FX Carry",
    explanation:
      "FX Carry has decent research but stale / incomplete evidence. It demonstrates how QuantFidelity catches maintenance problems.",
    lookFor: [
      "Evidence freshness / SLA warnings",
      "An open review case",
      "Lifecycle blocked on evidence freshness",
    ],
    goLabel: "Open FX Carry Strategy",
    target: { kind: "strategy", nameKey: "fxCarry" },
  },
  {
    step: 5,
    title: "Open the blocked example — Crypto Momentum",
    explanation:
      "Crypto Momentum may show attractive headline metrics but weak assumptions and evidence. It demonstrates why QuantFidelity does not trust Sharpe alone.",
    lookFor: [
      "Config policy failures (zero costs, same-close fill)",
      "Low trust score despite a high Sharpe",
      "Lifecycle blocked by assumptions / governance",
    ],
    goLabel: "Open Crypto Momentum",
    target: { kind: "strategy", nameKey: "crypto" },
  },
  {
    step: 6,
    title: "Open the improving example — KO/PEP (Maya)",
    explanation:
      "KO/PEP v2 improved trust, turnover, and reliability — but it still needs evidence linkage and assumption review. It shows the difference between “improved” and “ready to progress.”",
    lookFor: [
      "Current lifecycle stage: Backtest; next: Backtest Review",
      "Blockers: assumption review, missing evidence links, no paper run",
      "Use the Action Queue to fix evidence links and review assumptions",
    ],
    goLabel: "Open KO/PEP Pairs Trade",
    target: { kind: "strategy", nameKey: "mayaKoPep" },
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
