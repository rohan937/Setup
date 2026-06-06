import type { ReactNode } from "react";
import { Link } from "react-router-dom";

interface EmptyStateAction {
  label: string;
  onClick?: () => void;
  to?: string;
}

interface EmptyStateProps {
  title: string;
  description: string;
  icon?: ReactNode;
  action?: EmptyStateAction;
}

export default function EmptyState({
  title,
  description,
  icon,
  action,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-card border border-dashed border-border bg-bg-800/60 px-6 py-16 text-center">
      {/* Icon area — subtle rounded square with brand/research tint */}
      <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-card bg-bg-600 text-research-300 shadow-panel ring-1 ring-research/20">
        {icon ?? (
          <span className="flex items-center gap-1 font-mono text-sm text-research-300">
            <span>$</span>
            <span className="opacity-50">_</span>
          </span>
        )}
      </div>

      <p className="card-title">{title}</p>
      <p className="mt-2 max-w-sm text-sm leading-relaxed text-text-secondary">
        {description}
      </p>

      {action &&
        (action.to ? (
          <Link
            to={action.to}
            className="mt-6 inline-flex items-center rounded-control bg-brand px-4 py-2 text-sm font-medium text-text-inverse transition-colors hover:bg-brand-600"
          >
            {action.label}
          </Link>
        ) : (
          <button
            type="button"
            onClick={action.onClick}
            className="mt-6 inline-flex items-center rounded-control bg-brand px-4 py-2 text-sm font-medium text-text-inverse transition-colors hover:bg-brand-600"
          >
            {action.label}
          </button>
        ))}
    </div>
  );
}
