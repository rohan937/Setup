import type { ReactNode } from "react";

interface CardProps {
  label?: string;
  children: ReactNode;
  className?: string;
  /** Draws a 2px top accent bar in the research/brand accent color */
  accent?: boolean;
}

export default function Card({ label, children, className = "", accent = false }: CardProps) {
  return (
    <div
      className={[
        "card-interactive rounded-card border border-border bg-bg-700 shadow-card",
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
