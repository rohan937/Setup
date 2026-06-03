import PageHeader from "@/components/PageHeader";
import { useAuth } from "@/context/AuthContext";
import { roleBadgeClasses } from "@/lib/permissions";

interface AccessRequiredProps {
  tag?: string;
  title: string;
  /** Short requirement line, e.g. "Owner/Admin only". */
  requirement?: string;
}

/**
 * M69 — full-page "access required" panel shown when the signed-in user's
 * workspace role is insufficient. Uses the dark quant-terminal palette with a
 * red access-denied accent.
 */
export default function AccessRequired({
  tag = "ADMIN",
  title,
  requirement = "Owner/Admin only",
}: AccessRequiredProps) {
  const auth = useAuth();
  return (
    <div className="min-h-screen bg-gray-950 px-6 py-6 text-gray-200">
      <PageHeader tag={tag} title={title} subtitle="Access restricted" />
      <div className="rounded-lg border border-red-800/50 bg-red-900/15 p-6">
        <p className="mb-2 font-mono text-sm font-semibold uppercase tracking-wider text-red-400">
          Admin access required
        </p>
        <p className="font-mono text-xs text-gray-400">
          This page requires {requirement}. Your workspace role does not have access.
        </p>
        {auth.isAuthenticated && (
          <div className="mt-4 flex items-center gap-2 font-mono text-xs">
            <span className="uppercase tracking-wider text-gray-500">Your role</span>
            <span className={`rounded border px-1.5 py-0.5 font-semibold ${roleBadgeClasses(auth.role)}`}>
              {auth.role ?? "—"}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
