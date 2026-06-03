import type { PermissionSet } from "@/types";

/**
 * M69 — Frontend permission helpers.
 *
 * Mirrors the backend RBAC foundation. When the user is NOT authenticated
 * (no bearer token / local dev), the backend treats the caller as a permissive
 * pseudo-owner, so these helpers return `true` to keep the local-dev UI usable.
 * Once a user IS signed in, the resolved `permissions` set is enforced.
 */
export interface PermissionContext {
  isAuthenticated: boolean;
  role?: string | null;
  permissions?: PermissionSet | null;
}

function allow(ctx: PermissionContext, key: keyof PermissionSet): boolean {
  // Unauthenticated local-dev → permissive (matches backend pseudo-owner).
  if (!ctx.isAuthenticated) return true;
  return !!ctx.permissions?.[key];
}

export function canManageWorkspace(ctx: PermissionContext): boolean {
  return allow(ctx, "can_manage_workspace");
}

export function canManageMembers(ctx: PermissionContext): boolean {
  return allow(ctx, "can_manage_members");
}

export function canManageApiKeys(ctx: PermissionContext): boolean {
  return allow(ctx, "can_manage_api_keys");
}

export function canSeedDemo(ctx: PermissionContext): boolean {
  return allow(ctx, "can_seed_demo");
}

export function canWriteResearch(ctx: PermissionContext): boolean {
  return allow(ctx, "can_write_research");
}

export function canReadResearch(ctx: PermissionContext): boolean {
  return allow(ctx, "can_read_research");
}

/** True only when a signed-in user holds the read-only viewer role. */
export function isViewer(ctx: PermissionContext): boolean {
  return ctx.isAuthenticated && ctx.role === "viewer";
}

const ROLE_BADGE_STYLES: Record<string, string> = {
  owner: "border-cyan-700/40 bg-cyan-900/20 text-cyan-300",
  admin: "border-teal-700/40 bg-teal-900/20 text-teal-300",
  member: "border-amber-700/40 bg-amber-900/20 text-amber-300",
  viewer: "border-gray-600/40 bg-gray-800/50 text-gray-400",
};

/** Tailwind classes for a monospaced role chip (quant-terminal palette). */
export function roleBadgeClasses(role: string | null | undefined): string {
  return ROLE_BADGE_STYLES[role ?? ""] ?? ROLE_BADGE_STYLES.viewer;
}
