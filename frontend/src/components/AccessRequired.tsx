import RoleAwareAccess from "@/components/RoleAwareAccess";

interface AccessRequiredProps {
  tag?: string;
  title: string;
  /** Short requirement line, e.g. "Owner/Admin only". */
  requirement?: string;
  /** M77: what this page lets you do, e.g. "seed demo data". */
  permissionLabel?: string;
  /** M77: what the user can still do without access. */
  whatYouCanDo?: string[];
}

/**
 * M69/M77 — "access required" panel shown when the signed-in user's workspace
 * role is insufficient. Delegates to the calm, role-aware RoleAwareAccess
 * component (current role + required role + constructive next step).
 */
export default function AccessRequired({
  title,
  requirement = "Owner or Admin",
  permissionLabel,
  whatYouCanDo,
}: AccessRequiredProps) {
  return (
    <RoleAwareAccess
      title={title}
      requiredLabel={requirement}
      permissionLabel={permissionLabel ?? `open ${title}`}
      whatYouCanDo={whatYouCanDo}
    />
  );
}
