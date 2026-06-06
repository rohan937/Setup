// Finance-terminal badge — tinted chip with bg + border + text for a filled feel.
// M101 institutional treatment: subtle color tint, calm uppercase tracking.

const STATUS_COLORS: Record<string, string> = {
  active:   "border-fidelity-high/40   bg-fidelity-high/10   text-fidelity-high",
  paused:   "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
  archived: "border-border-strong      bg-bg-600/60          text-text-muted",
  draft:    "border-border-strong      bg-bg-600/60          text-text-muted",
};

const ASSET_CLASS_COLORS: Record<string, string> = {
  equity:    "border-brand/40          bg-brand/10          text-accent-300",
  etf:       "border-brand/40          bg-brand/10          text-accent-300",
  future:    "border-teal-500/40       bg-teal-500/10       text-teal-300",
  option:    "border-teal-500/40       bg-teal-500/10       text-teal-300",
  fx:        "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
  crypto:    "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
  rate:      "border-border-strong     bg-bg-600/60         text-text-secondary",
  commodity: "border-severity-high/40  bg-severity-high/10  text-severity-high",
  other:     "border-border-strong     bg-bg-600/60         text-text-secondary",
};

const RUN_TYPE_COLORS: Record<string, string> = {
  backtest: "border-brand/40        bg-brand/10        text-accent-300",
  paper:    "border-teal-500/40     bg-teal-500/10     text-teal-300",
  live:     "border-fidelity-high/40 bg-fidelity-high/10 text-fidelity-high",
  research: "border-research/40     bg-research/10     text-research-300",
};

const RUN_STATUS_COLORS: Record<string, string> = {
  completed: "border-fidelity-high/40 bg-fidelity-high/10 text-fidelity-high",
  running:   "border-brand/40         bg-brand/10         text-accent-300",
  failed:    "border-fidelity-low/40  bg-fidelity-low/10  text-fidelity-low",
  pending:   "border-border-strong    bg-bg-600/60        text-text-muted",
  canceled:  "border-border-strong    bg-bg-600/60        text-text-muted",
};

// Governance / health badge system (M101).
const HEALTH_COLORS: Record<string, string> = {
  healthy:         "border-fidelity-high/40   bg-fidelity-high/10   text-fidelity-high",
  ready:           "border-fidelity-high/40   bg-fidelity-high/10   text-fidelity-high",
  stable:          "border-fidelity-high/40   bg-fidelity-high/10   text-fidelity-high",
  verified:        "border-fidelity-high/40   bg-fidelity-high/10   text-fidelity-high",
  review:          "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
  watch:           "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
  paper_candidate: "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
  blocked:         "border-fidelity-low/40    bg-fidelity-low/10    text-fidelity-low",
  critical:        "border-fidelity-low/40    bg-fidelity-low/10    text-fidelity-low",
  failed:          "border-fidelity-low/40    bg-fidelity-low/10    text-fidelity-low",
  drifted:         "border-fidelity-low/40    bg-fidelity-low/10    text-fidelity-low",
  shadow:          "border-research/40        bg-research/10        text-research-300",
  production:      "border-research/40        bg-research/10        text-research-300",
};

const DEFAULT = "border-border-strong bg-bg-600/60 text-text-secondary";

type BadgeVariant = "status" | "asset_class" | "run_type" | "run_status" | "health";

interface BadgeProps {
  value: string;
  variant?: BadgeVariant;
}

function colorFor(value: string, variant?: BadgeVariant): string {
  switch (variant) {
    case "status":      return STATUS_COLORS[value]      ?? DEFAULT;
    case "asset_class": return ASSET_CLASS_COLORS[value] ?? DEFAULT;
    case "run_type":    return RUN_TYPE_COLORS[value]    ?? DEFAULT;
    case "run_status":  return RUN_STATUS_COLORS[value]  ?? DEFAULT;
    case "health":      return HEALTH_COLORS[value]      ?? DEFAULT;
    default:            return DEFAULT;
  }
}

export default function Badge({ value, variant }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-chip border px-2 py-0.5 font-mono text-2xs font-medium uppercase tracking-eyebrow ${colorFor(value, variant)}`}
    >
      {value}
    </span>
  );
}
