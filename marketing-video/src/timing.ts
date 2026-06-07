// Centralized timing + script + palette.
// Edit copy, durations, and colors here in ONE place.

export const FPS = 30;
export const VIDEO_DURATION_SECONDS = 45;
export const DURATION = FPS * VIDEO_DURATION_SECONDS;

const sec = (s: number) => Math.round(s * FPS);

export type SceneId =
  | "hook"
  | "tension"
  | "backtest"
  | "reveal"
  | "reality"
  | "workflow"
  | "screenshots"
  | "final";

export interface SceneDef {
  id: SceneId;
  from: number;
  durationInFrames: number;
}

export const SCENES: SceneDef[] = [
  {id: "hook", from: sec(0), durationInFrames: sec(4)},
  {id: "tension", from: sec(4), durationInFrames: sec(4)},
  {id: "backtest", from: sec(8), durationInFrames: sec(7)},
  {id: "reveal", from: sec(15), durationInFrames: sec(5)},
  {id: "reality", from: sec(20), durationInFrames: sec(8)},
  {id: "workflow", from: sec(28), durationInFrames: sec(6)},
  {id: "screenshots", from: sec(34), durationInFrames: sec(6)},
  {id: "final", from: sec(40), durationInFrames: sec(5)},
];

// Color palette — light premium SaaS aesthetic.
export const COLORS = {
  bg: "#F8FAFC",
  textPrimary: "#0F172A",
  textSecondary: "#475569",
  blue: "#4F8CFF",
  purple: "#8B5CF6",
  cyan: "#06B6D4",
  success: "#00B894",
  warning: "#F59E0B",
  danger: "#EF4444",
  cardBg: "rgba(255, 255, 255, 0.78)",
  cardBorder: "rgba(15, 23, 42, 0.06)",
} as const;

export const FONT_STACK =
  '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';

export type MetricTone = "neutral" | "warning" | "danger" | "success";

export interface ScriptMetric {
  label: string;
  value: string;
  tone: MetricTone;
}

export interface WorkflowStep {
  label: string;
  caption: string;
  color: string;
}

// All on-screen copy lives here.
export const SCRIPT = {
  hook: {
    text: "[ backtests look clean ]",
  },
  tension: {
    text: "[ until production disagrees ]",
  },
  backtest: {
    title: "SPY Trend Backtest v1",
    metrics: [
      {label: "Sharpe", value: "1.42", tone: "success"},
      {label: "Turnover", value: "1.8x", tone: "warning"},
      {label: "Transaction costs", value: "0 bps", tone: "warning"},
      {label: "Paper run", value: "Missing", tone: "danger"},
    ] as ScriptMetric[],
    badge: "Reality Check: Review",
    caption:
      "Looks promising. But the assumptions are doing too much work.",
  },
  reveal: {
    title: "QuantFidelity checks what research teams usually miss.",
    subtitle: "Evidence. Assumptions. Drift. Governance.",
  },
  reality: {
    title: "Research Reality Check",
    bullets: [
      "Zero transaction costs with high turnover",
      "Missing paper/shadow validation",
      "Evidence chain incomplete",
      "Promotion gates blocked",
    ],
    conclusion: "Not ready for promotion.",
  },
  workflow: {
    steps: [
      {
        label: "Evidence",
        caption: "linked research artifacts",
        color: COLORS.blue,
      },
      {
        label: "Reality",
        caption: "believable backtests",
        color: COLORS.cyan,
      },
      {
        label: "Verification",
        caption: "trusted evidence chain",
        color: COLORS.purple,
      },
      {
        label: "Governance",
        caption: "review-ready decisions",
        color: COLORS.warning,
      },
      {
        label: "Promotion",
        caption: "controlled lifecycle movement",
        color: COLORS.success,
      },
    ] as WorkflowStep[],
  },
  screenshots: {
    shots: [
      {src: "screenshots/home.png", label: "Research Command Center"},
      {src: "screenshots/executive-demo.png", label: "Executive Demo"},
      {src: "screenshots/strategy-overview.png", label: "Strategy Workspace"},
    ],
    caption: "From raw research evidence to promotion-ready decisions.",
  },
  final: {
    title: "A reliability layer for quant research.",
    subtitle: "Evidence. Backtests. Drift. Governance.",
    brand: "QuantFidelity",
    disclaimer: "Research governance summary. Not trading advice.",
  },
} as const;
