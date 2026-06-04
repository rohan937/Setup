// Finance-terminal badge — near-square chip with border-only color treatment.
// Rounded chip = 2px (rounded-chip) — sharper than generic SaaS pills.

const STATUS_COLORS: Record<string, string> = {
  active:   "border-fidelity-high   text-fidelity-high",
  paused:   "border-fidelity-medium text-fidelity-medium",
  archived: "border-border-strong   text-text-muted",
  draft:    "border-border-strong   text-text-muted",
};

const ASSET_CLASS_COLORS: Record<string, string> = {
  equity:    "border-accent-500   text-accent-300",
  etf:       "border-accent-500   text-accent-300",
  future:    "border-teal-500     text-teal-300",
  option:    "border-teal-500     text-teal-300",
  fx:        "border-fidelity-medium text-fidelity-medium",
  crypto:    "border-fidelity-medium text-fidelity-medium",
  rate:      "border-border-strong   text-text-secondary",
  commodity: "border-severity-high   text-severity-high",
  other:     "border-border-strong   text-text-secondary",
};

const RUN_TYPE_COLORS: Record<string, string> = {
  backtest: "border-accent-500   text-accent-300",
  paper:    "border-teal-500     text-teal-300",
  live:     "border-fidelity-high text-fidelity-high",
  research: "border-border-strong text-text-secondary",
};

const RUN_STATUS_COLORS: Record<string, string> = {
  completed: "border-fidelity-high   text-fidelity-high",
  running:   "border-accent-500      text-accent-300",
  failed:    "border-fidelity-low    text-fidelity-low",
  pending:   "border-border-strong   text-text-muted",
  canceled:  "border-border-strong   text-text-muted",
};

const DEFAULT = "border-border-strong text-text-secondary";

type BadgeVariant = "status" | "asset_class" | "run_type" | "run_status";

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
