import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { bootstrapFirstOwner } from "@/lib/api";

/**
 * Shown when a signed-in user has no workspace membership (e.g. a fresh
 * deployment whose first user was created before the bootstrap fix, or a user
 * who has not been invited yet). Offers a one-click first-owner bootstrap, which
 * the backend only allows while no owner exists anywhere.
 *
 * Renders nothing unless the user is authenticated AND has zero memberships, so
 * it is safe to drop into any page.
 */
export default function NoWorkspaceNotice() {
  const auth = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  // Local dev (no auth token) is a permissive pseudo-owner — never show this.
  if (!auth.isAuthenticated || auth.loading) return null;
  if (auth.memberships.length > 0) return null;

  async function handleBootstrap() {
    setBusy(true);
    setError(null);
    try {
      await bootstrapFirstOwner();
      await auth.refreshCurrentUser();
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bootstrap failed.");
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="rounded-card border border-fidelity-high/30 bg-fidelity-high/5 px-5 py-4">
        <p className="text-sm text-fidelity-high">
          You are now the workspace owner. Reload the page if menus do not update.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-card border border-fidelity-medium/30 bg-fidelity-medium/5 px-5 py-4">
      <p className="text-sm font-medium text-text-primary">
        You are signed in, but you are not a member of any workspace.
      </p>
      <p className="mt-1.5 text-xs leading-relaxed text-text-secondary">
        Ask a workspace owner to add you, or — if this is a brand-new deployment
        with no owner yet — run the first-owner bootstrap to claim this workspace.
        Once an owner exists, this option is disabled automatically.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          onClick={handleBootstrap}
          disabled={busy}
          className="rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-1.5 text-xs text-accent-200 hover:bg-accent-500/25 disabled:opacity-40"
        >
          {busy ? "Working…" : "Run first-owner bootstrap"}
        </button>
        <Link
          to="/workspace/members"
          className="rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
        >
          Workspace Members
        </Link>
      </div>
      {error && (
        <p className="mt-2 text-2xs text-fidelity-low">
          {error}
          {/^an owner already exists/i.test(error) || /disabled/i.test(error)
            ? " — ask an existing owner to add you."
            : ""}
        </p>
      )}
    </div>
  );
}
