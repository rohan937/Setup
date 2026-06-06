import type { ReactNode } from "react";

type CardGradient = "primary" | "success" | "warning" | "danger" | "research";

interface CardProps {
  label?: string;
  children: ReactNode;
  className?: string;
  /** Draws a 2px top accent bar in the research/brand accent color */
  accent?: boolean;
  /**
   * Opt-in premium treatment for high-value cards. Applies a matching gradient
   * edge plus a soft matching glow on hover. When unset, the card renders as a
   * standard bordered surface (backward compatible).
   */
  gradient?: CardGradient;
}

// Static gradient edge per variant. gradient-border sets its own transparent
// border + bg-700 padding fill, so the default border/bg is dropped when used.
const GRADIENT_BORDER: Record<CardGradient, string> = {
  primary: "gradient-border gradient-border-primary",
  success: "gradient-border gradient-border-success",
  warning: "gradient-border gradient-border-warning",
  danger: "gradient-border gradient-border-danger",
  research: "gradient-border gradient-border-research",
};

// Soft matching glow revealed on hover only (cards stay calm at rest).
const HOVER_GLOW: Record<CardGradient, string> = {
  primary: "hover:shadow-glow-primary",
  success: "hover:shadow-glow-success",
  warning: "hover:shadow-glow-warning",
  danger: "hover:shadow-glow-danger",
  research: "hover:shadow-glow-research",
};

export default function Card({
  label,
  children,
  className = "",
  accent = false,
  gradient,
}: CardProps) {
  const surface = gradient
    ? "rounded-card shadow-card"
    : "rounded-card border border-border bg-bg-700 shadow-card";

  return (
    <div
      className={[
        "card-hover-lift animate-fade-in",
        surface,
        gradient ? GRADIENT_BORDER[gradient] : "",
        gradient ? HOVER_GLOW[gradient] : "",
        accent ? "border-t-2 border-t-brand" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {label ? (
        <div className="border-b border-border px-6 py-4">
          <p className="caption">{label}</p>
        </div>
      ) : null}
      <div className="p-6">{children}</div>
    </div>
  );
}
