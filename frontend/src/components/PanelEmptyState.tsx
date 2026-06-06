import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { canWriteResearch } from "@/lib/permissions";

export interface EmptyStateAction {
  label: string;
  /** Click handler for an in-page action (e.g. create defaults). */
  onClick?: () => void;
  /** Or a route to navigate to instead. */
  to?: string;
  primary?: boolean;
  loading?: boolean;
}

interface PanelEmptyStateProps {
  title: string;
  description: string;
  /** Optional secondary explanatory line. */
  note?: string;
  actions?: EmptyStateAction[];
  /**
   * When true, the actions require write-research permission. If the signed-in
   * user lacks it, the actions render disabled with a calm role-aware note.
   */
  needsWrite?: boolean;
}

/**
 * M77 — shared, calm empty-state used across panels so a missing artifact is
 * never a dead end: it explains what's missing and offers the next action.
 * Product language only — no debug/raw wording, no AI, no trading advice.
 */
export default function PanelEmptyState({
  title,
  description,
  note,
  actions = [],
  needsWrite = false,
}: PanelEmptyStateProps) {
  const auth = useAuth();
  const blocked = needsWrite && !canWriteResearch(auth);

  return (
    <div className="rounded-card border border-border bg-bg-800/40 px-5 py-5">
      <p className="text-sm font-semibold tracking-tight text-text-primary">{title}</p>
      <p className="mt-1.5 text-xs leading-relaxed text-text-secondary">{description}</p>
      {note && <p className="mt-2 text-2xs text-text-muted">{note}</p>}

      {actions.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {actions.map((a) => {
            const cls = a.primary
              ? "rounded-control bg-brand px-3 py-1.5 text-xs font-medium text-text-inverse transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-40"
              : "rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary transition-colors hover:bg-bg-600 hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40";
            if (a.to && !blocked) {
              return (
                <Link key={a.label} to={a.to} className={cls}>
                  {a.label}
                </Link>
              );
            }
            return (
              <button
                key={a.label}
                type="button"
                onClick={a.onClick}
                disabled={blocked || a.loading}
                className={cls}
              >
                {a.loading ? "Working…" : a.label}
              </button>
            );
          })}
        </div>
      )}

      {blocked && (
        <p className="mt-2 text-2xs text-fidelity-medium">
          This action needs write-research access (your role: {auth.role ?? "viewer"}). Ask a
          workspace owner to upgrade your role.
        </p>
      )}
    </div>
  );
}
