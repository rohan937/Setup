import { Link } from "react-router-dom";
import PageHeader from "@/components/PageHeader";
import NoWorkspaceNotice from "@/components/NoWorkspaceNotice";
import { useAuth } from "@/context/AuthContext";
import { roleBadgeClasses } from "@/lib/permissions";

interface RoleAwareAccessProps {
  /** Page title, e.g. "Demo Controls". */
  title: string;
  /** What this page lets you do, e.g. "seed demo data". */
  permissionLabel: string;
  /** Required role description, e.g. "Owner or Admin". */
  requiredLabel?: string;
  /** Optional longer description of the page's purpose. */
  description?: string;
  /** What the user can still do without this permission. */
  whatYouCanDo?: string[];
  /** Show the "sign in as an owner/admin" hint (default true). */
  showLoginHint?: boolean;
}

/**
 * M77 — calm, role-aware access panel. Replaces blunt "Admin access required"
 * messaging with: current role, required role/permission, what the user can
 * still do, and a constructive next step. Never exposes secrets and never
 * suggests manual database edits.
 */
export default function RoleAwareAccess({
  title,
  permissionLabel,
  requiredLabel = "Owner or Admin",
  description,
  whatYouCanDo,
  showLoginHint = true,
}: RoleAwareAccessProps) {
  const auth = useAuth();
  const role = auth.role ?? (auth.isAuthenticated ? "—" : "not signed in");

  return (
    <div className="px-1 py-1">
      <PageHeader tag="Access" title={title} subtitle="Restricted to higher access" />

      {/* When the user has no workspace membership at all, offer the first-owner
          bootstrap (renders nothing if they already belong to a workspace). */}
      <div className="mt-4 max-w-2xl">
        <NoWorkspaceNotice />
      </div>

      <div className="mt-4 max-w-2xl rounded-card border border-fidelity-medium/30 bg-fidelity-medium/5 p-6">
        <p className="text-sm font-medium text-text-primary">
          You need {requiredLabel} access to {permissionLabel}.
        </p>
        {description && (
          <p className="mt-1.5 text-xs leading-relaxed text-text-secondary">{description}</p>
        )}

        {/* Current vs required */}
        <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs">
          <div className="flex items-center gap-2">
            <span className="caption">Current role</span>
            <span
              className={`rounded border px-1.5 py-0.5 font-mono font-semibold ${roleBadgeClasses(auth.role)}`}
            >
              {role}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="caption">Required</span>
            <span className="rounded border border-border-strong bg-bg-800 px-1.5 py-0.5 font-mono text-text-secondary">
              {requiredLabel}
            </span>
          </div>
        </div>

        {/* Suggested action */}
        <div className="mt-5 space-y-1.5 text-xs text-text-secondary">
          <p>
            Ask a workspace owner to upgrade your role
            {showLoginHint ? ", or sign in as an owner/admin account." : "."}
          </p>
          <p className="text-2xs text-text-muted">
            For a local demo, sign in as the workspace owner account. Roles are managed
            in Workspace → Members — never by editing the database directly.
          </p>
        </div>

        {/* What you can still do */}
        {whatYouCanDo && whatYouCanDo.length > 0 && (
          <div className="mt-5">
            <p className="caption mb-1.5">What you can still do</p>
            <ul className="space-y-1">
              {whatYouCanDo.map((item, i) => (
                <li key={i} className="flex gap-1.5 text-xs text-text-secondary">
                  <span aria-hidden="true">•</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Links */}
        <div className="mt-5 flex flex-wrap gap-2">
          <Link
            to="/workspace/members"
            className="rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            Workspace Members
          </Link>
          {showLoginHint && (
            <Link
              to="/login"
              className="rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-1.5 text-xs text-accent-200 hover:bg-accent-500/25"
            >
              Sign in
            </Link>
          )}
          <Link
            to="/home"
            className="rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            Back to Home
          </Link>
        </div>
      </div>
    </div>
  );
}
