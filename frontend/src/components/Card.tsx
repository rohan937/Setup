import type { ReactNode } from "react";

interface CardProps {
  label?: string;
  children: ReactNode;
  className?: string;
}

export default function Card({ label, children, className = "" }: CardProps) {
  return (
    <div
      className={`rounded-card border border-border bg-bg-700 p-5 ${className}`}
    >
      {label ? <p className="caption mb-2">{label}</p> : null}
      {children}
    </div>
  );
}
