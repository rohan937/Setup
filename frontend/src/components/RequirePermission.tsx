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
    return <AccessRequired title={title} requirement={requirement} />;
  }
  return <>{children}</>;
}
