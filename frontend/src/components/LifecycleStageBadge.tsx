// M104 — Compact lifecycle stage chip for list rows.
// M102 Badge styling (rounded-chip, uppercase, tracking-eyebrow, tinted),
// colored by stage band. Tokens only — no hardcoded colors.

interface LifecycleStageBadgeProps {
  stage: string | null | undefined;
  blocked?: boolean;
}

// Normalize raw backend stage value to a clean Title-Case display label.
// "backtest" collapses into "Backtest Review".
const STAGE_LABELS: Record<string, string> = {
  research: "Research",
  backtest: "Backtest Review",
  backtest_review: "Backtest Review",
  paper_candidate: "Paper Candidate",
  shadow: "Shadow",
  production_candidate: "Production Candidate",
};

// Color by stage band (M102 tinted chip — border-X/40 bg-X/10 text-X).
const STAGE_COLORS: Record<string, string> = {
  research: "border-border-strong bg-bg-600/60 text-text-secondary",
  backtest: "border-brand/40 bg-brand/10 text-accent-300",
  backtest_review: "border-brand/40 bg-brand/10 text-accent-300",
  paper_candidate: "border-research/40 bg-research/10 text-research-300",
  shadow: "border-research/40 bg-research/10 text-research-300",
  production_candidate:
    "border-fidelity-high/40 bg-fidelity-high/10 text-fidelity-high",
};

const EMPTY = "border-border-strong bg-bg-600/60 text-text-muted";

export default function LifecycleStageBadge({
  stage,
  blocked = false,
}: LifecycleStageBadgeProps) {
  const key = stage ? stage.trim() : "";
  const label = key ? STAGE_LABELS[key] ?? "No stage" : "No stage";
  const isEmpty = !key || !(key in STAGE_LABELS);
  const colors = isEmpty ? EMPTY : STAGE_COLORS[key];

  return (
    <span
      className={`inline-flex items-center rounded-chip border px-2 py-0.5 text-2xs font-medium uppercase tracking-eyebrow ${colors}`}
    >
      {blocked && !isEmpty ? (
        <span
          aria-hidden="true"
          className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-fidelity-medium status-dot-pulse"
        />
      ) : null}
      {isEmpty ? "—" : label}
    </span>
  );
}
