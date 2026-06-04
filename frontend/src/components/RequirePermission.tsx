import type { ReactNode } from "react";
import { useAuth } from "@/context/AuthContext";
import {
  canManageApiKeys,
  canManageMembers,
  canManageWorkspace,
  canSeedDemo,
  type PermissionContext,
} from "@/lib/permissions";
import AccessRequired from "@/components/AccessRequired";

type PermKey =
  | "manage_workspace"
  | "manage_members"
  | "manage_api_keys"
  | "seed_demo";

const CHECKS: Record<PermKey, (ctx: PermissionContext) => boolean> = {
  manage_workspace: canManageWorkspace,
  manage_members: canManageMembers,
  manage_api_keys: canManageApiKeys,
  seed_demo: canSeedDemo,
};

// M77: friendly per-permission copy for the role-aware access panel.
const PERM_COPY: Record<PermKey, { label: string; canDo: string[] }> = {
  manage_workspace: {
    label: "manage workspace settings",
    canDo: ["Browse strategies, evidence, and reports", "Review the Action Queue and lifecycle"],
  },
  manage_members: {
    label: "manage workspace members",
    canDo: ["View the current members list", "Continue working with research evidence"],
  },
  manage_api_keys: {
    label: "manage API keys",
    canDo: ["View existing API key metadata", "Use the web app and SDK as normal"],
  },
  seed_demo: {
    label: "seed demo data",
    canDo: [
      "Explore the existing strategies and evidence",
      "Start the guided demo from Home if demo data already exists",
    ],
  },
};

interface RequirePermissionProps {
  perm: PermKey;
  title: string;
  requirement?: string;
  children: ReactNode;
}

/**
 * M69 — route-level RBAC guard. Renders an "Admin access required" panel when
 * the signed-in user's role is insufficient; otherwise renders the page.
 *
 * Unauthenticated local-dev callers are treated as permissive (see
 * lib/permissions), matching the backend pseudo-owner behaviour.
 */
export default function RequirePermission({
  perm,
  title,
  requirement,
  children,
}: RequirePermissionProps) {
  const auth = useAuth();
  // Wait for the initial /auth/me round-trip before deciding.
  if (auth.loading) return null;
  if (!CHECKS[perm](auth)) {
    const copy = PERM_COPY[perm];
    return (
      <AccessRequired
        title={title}
        requirement={requirement}
        permissionLabel={copy.label}
        whatYouCanDo={copy.canDo}
      />
    );
  }
  return <>{children}</>;
}
