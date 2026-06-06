interface ScoreCardProps {
  label: string;
  description?: string;
  /** Numeric score 0-100. When provided, renders the hero metric. */
  score?: number | null;
  /** Verdict word shown as an uppercase caption (e.g. "PASS", "REVIEW"). */
  verdict?: string;
  /** Override the metric color (Tailwind text-* class). Otherwise derived from score. */
  accentColor?: string;
}

function colorForScore(score: number): string {
  if (score >= 85) return "text-fidelity-high";
  if (score >= 70) return "text-brand";
  if (score >= 50) return "text-fidelity-medium";
  return "text-fidelity-low";
}

type ScoreBand = "success" | "primary" | "warning" | "danger" | "neutral";

// Map a numeric score to a state band. No score -> neutral (calm styling).
function bandForScore(score: number | null | undefined): ScoreBand {
  if (score === undefined || score === null) return "neutral";
  if (score >= 85) return "success";
  if (score >= 70) return "primary";
  if (score >= 50) return "warning";
  return "danger";
}

// Hover-only LARGE state glow keyed to the score band. Cards stay calm at rest
// and reveal a band-colored ring + halo on hover (never a constant glow).
const HOVER_GLOW_LG: Record<ScoreBand, string> = {
  success: "hover:shadow-glow-success-lg",
  primary: "hover:shadow-glow-primary-lg",
  warning: "hover:shadow-glow-warning-lg",
  danger: "hover:shadow-glow-danger-lg",
  neutral: "",
};

// Static premium gradient edge per band. Pairs gradient-border (sets its own
// transparent border + bg-700 padding fill) with a color variant.
const GRADIENT_BORDER: Record<ScoreBand, string> = {
  success: "gradient-border gradient-border-success",
  primary: "gradient-border gradient-border-primary",
  warning: "gradient-border gradient-border-warning",
  danger: "gradient-border gradient-border-danger",
  neutral: "",
};

// Gradient text for the hero number — healthy/good scores ONLY. Amber/red stay
// solid colored to preserve readability.
const NUMBER_GRADIENT: Partial<Record<ScoreBand, string>> = {
  success: "text-gradient-success",
  primary: "text-gradient-primary",
};

export default function ScoreCard({
  label,
  description,
  score,
  verdict,
  accentColor,
}: ScoreCardProps) {
  const hasScore = score !== undefined && score !== null;
  const band = bandForScore(score);
  const solidValueColor = hasScore
    ? accentColor ?? colorForScore(score as number)
    : "text-text-muted";

  // Use a gradient number for healthy/good bands only, and never when the caller
  // overrode the color. Otherwise fall back to solid colored text.
  const numberGradient = !accentColor ? NUMBER_GRADIENT[band] : undefined;
  const numberClass = numberGradient ?? solidValueColor;

  const hoverGlow = HOVER_GLOW_LG[band];

  // Banded gradient edge for scored cards; neutral cards keep a plain border.
  // A failing-score critical verdict (blocked/critical/failed) is already
  // covered by the danger gradient edge — no extra constant pulse.
  const gradientBorder = hasScore ? GRADIENT_BORDER[band] : "";
  const baseSurface = gradientBorder
    ? "rounded-card p-6 shadow-card"
    : "rounded-card border border-border bg-bg-700 p-6 shadow-card";

  return (
    <div
      className={[
        baseSurface,
        gradientBorder,
        "card-hover-lift animate-fade-in",
        hoverGlow,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <p className="caption mb-3">{label}</p>

      <div className="flex items-baseline gap-2">
        <p className={`metric-value text-metric-sm ${numberClass}`}>
          {hasScore ? Math.round(score as number) : "—"}
        </p>
        {hasScore && <p className="font-mono text-xs text-text-muted">/100</p>}
      </div>

      {verdict && hasScore ? (
        <p className={`caption mt-2 ${solidValueColor}`}>{verdict}</p>
      ) : null}

      <div className="my-4 h-px w-full bg-border" />

      <p className="text-2xs leading-relaxed text-text-secondary">
        {description ?? (hasScore ? "" : "No runs measured")}
      </p>
    </div>
  );
}
