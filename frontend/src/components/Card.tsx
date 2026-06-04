import type { ReactNode } from "react";

interface CardProps {
  label?: string;
  children: ReactNode;
  className?: string;
  /** Draws a 2px top accent bar in the primary accent color */
  accent?: boolean;
}

export default function Card({ label, children, className = "", accent = false }: CardProps) {
  return (
    <div
      className={[
        "rounded-card border border-border bg-bg-700 shadow-card",
        accent ? "border-t-accent-500 border-t-2" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {label ? (
        <div className="border-b border-border px-5 py-3">
          <p className="caption">{label}</p>
        </div>
      ) : null}
      <div className="p-5">{children}</div>
    </div>
  );
}
