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

// Hover-only state glow keyed to the score band. Cards stay calm at rest and
// reveal a subtle band-colored ring on hover (never a constant glow).
function hoverGlowForScore(score: number): string {
  if (score >= 85) return "hover:shadow-glow-success";
  if (score >= 70) return "hover:shadow-glow-primary";
  if (score >= 50) return "hover:shadow-glow-warning";
  return "hover:shadow-glow-danger";
}

export default function ScoreCard({
  label,
  description,
  score,
  verdict,
  accentColor,
}: ScoreCardProps) {
  const hasScore = score !== undefined && score !== null;
  const valueColor = hasScore ? accentColor ?? colorForScore(score as number) : "text-text-muted";
  const hoverGlow = hasScore ? hoverGlowForScore(score as number) : "";

  // Very subtle static border tint for a critical verdict (blocked/critical/failed)
  // at a failing score. No constant pulse — score cards stay calm.
  const verdictLc = (verdict ?? "").toLowerCase();
  const isCritical =
    hasScore &&
    (score as number) < 50 &&
    /blocked|critical|failed/.test(verdictLc);
  const criticalBorder = isCritical ? "border-fidelity-low/30" : "border-border";

  return (
    <div
      className={[
        "rounded-card border bg-bg-700 p-6 shadow-card",
        criticalBorder,
        "card-hover-lift animate-fade-in",
        hoverGlow,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <p className="caption mb-3">{label}</p>

      <div className="flex items-baseline gap-2">
        <p className={`metric-value text-metric-sm ${valueColor}`}>
          {hasScore ? Math.round(score as number) : "—"}
        </p>
        {hasScore && <p className="font-mono text-xs text-text-muted">/100</p>}
      </div>

      {verdict && hasScore ? (
        <p className={`caption mt-2 ${valueColor}`}>{verdict}</p>
      ) : null}

      <div className="my-4 h-px w-full bg-border" />

      <p className="text-2xs leading-relaxed text-text-secondary">
        {description ?? (hasScore ? "" : "No runs measured")}
      </p>
    </div>
  );
}
