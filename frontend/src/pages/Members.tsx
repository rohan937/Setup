import PageHeader from "@/components/PageHeader";

// ---------------------------------------------------------------------------
// Role data
// ---------------------------------------------------------------------------

const ROLES = [
  {
    role: "Owner",
    permissions: "Full access, billing, delete workspace",
    description: "Typically one per workspace. Can transfer ownership.",
  },
  {
    role: "Admin",
    permissions: "Manage members, projects, settings",
    description: "Can invite/remove members and configure workspace-level settings.",
  },
  {
    role: "Member",
    permissions: "Create/edit strategies, run evidence ingestion",
    description: "Standard research access. Cannot manage workspace configuration.",
  },
  {
    role: "Viewer",
    permissions: "Read-only access to strategies and reports",
    description: "Can browse all data but cannot create or modify records.",
  },
] as const;

const PLANNED_FEATURES = [
  "Invite members by email",
  "Role assignment per member",
  "Remove members from workspace",
  "Pending invitation management",
  "Per-project role overrides",
];

// ---------------------------------------------------------------------------
// Members
// ---------------------------------------------------------------------------

export default function Members() {
  return (
    <div className="min-h-screen bg-gray-950 px-6 py-6 text-gray-200">
      <PageHeader
        tag="ADMIN"
        title="Members"
        subtitle="Workspace membership — available in M68/M69"
      />

      {/* Local dev notice */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 font-mono text-lg leading-none text-amber-400">!</span>
          <div>
            <p className="mb-1 text-sm font-semibold text-gray-200">Local Development Mode</p>
            <p className="text-sm text-gray-400">
              Authentication and membership management require{" "}
              <strong className="text-gray-300">M68 User Accounts</strong> and{" "}
              <strong className="text-gray-300">M69 RBAC</strong>. No authentication is required for
              local development — all endpoints are open.
            </p>
          </div>
        </div>
      </div>

      {/* Roles table */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <div className="mb-4 flex items-center gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-cyan-400">
            Planned Roles
          </h2>
          <span className="rounded border border-amber-700/40 bg-amber-900/20 px-2 py-0.5 text-xs font-semibold text-amber-400">
            M69
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 text-left">
                <th className="pb-2 pr-6 text-xs font-semibold uppercase tracking-wider text-gray-500">Role</th>
                <th className="pb-2 pr-6 text-xs font-semibold uppercase tracking-wider text-gray-500">Permissions</th>
                <th className="pb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">Notes</th>
              </tr>
            </thead>
            <tbody>
              {ROLES.map(({ role, permissions, description }) => (
                <tr key={role} className="border-b border-gray-800">
                  <td className="py-3 pr-6">
                    <div className="flex items-center gap-2">
                      <span className="rounded border border-amber-700/40 bg-amber-900/20 px-1.5 py-0.5 text-xs text-amber-400">
                        Planned
                      </span>
                      <span className="font-mono text-sm text-gray-200">{role}</span>
                    </div>
                  </td>
                  <td className="py-3 pr-6 text-sm text-gray-400">{permissions}</td>
                  <td className="py-3 text-sm text-gray-500">{description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Planned features */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <div className="mb-4 flex items-center gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-cyan-400">
            Planned Features
          </h2>
          <span className="rounded border border-amber-700/40 bg-amber-900/20 px-2 py-0.5 text-xs font-semibold text-amber-400">
            M68 / M69
          </span>
        </div>
        <div className="space-y-2">
          {PLANNED_FEATURES.map((feature) => (
            <div
              key={feature}
              className="flex items-center gap-3 rounded border border-gray-800 bg-gray-950 px-4 py-3"
            >
              <span className="rounded border border-amber-700/40 bg-amber-900/20 px-1.5 py-0.5 text-xs text-amber-400">
                Planned
              </span>
              <span className="text-sm text-gray-400">{feature}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Current members placeholder */}
      <div className="rounded-lg border border-gray-700 bg-gray-900 p-5">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-cyan-400">
          Current Members
        </h2>
        <div className="flex items-center justify-center rounded border border-dashed border-gray-700 py-8 text-sm text-gray-600">
          No members yet — authentication required (M68)
        </div>
      </div>
    </div>
  );
}
