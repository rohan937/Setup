import PageHeader from "@/components/PageHeader";

// ---------------------------------------------------------------------------
// Planned feature data
// ---------------------------------------------------------------------------

const PLANNED_FEATURES = [
  "Workspace name and slug editing",
  "Workspace description",
  "Default project assignment",
  "Workspace-level notification preferences",
];

// ---------------------------------------------------------------------------
// WorkspaceSettings
// ---------------------------------------------------------------------------

export default function WorkspaceSettings() {
  return (
    <div className="min-h-screen bg-gray-950 px-6 py-6 text-gray-200">
      <PageHeader
        tag="ADMIN"
        title="Workspace Settings"
        subtitle="Foundation — full workspace management arrives in M67"
      />

      {/* Current state */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-cyan-400">
          Current Workspace
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded border border-gray-800 bg-gray-950 p-4">
            <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Workspace</p>
            <p className="font-mono text-sm text-gray-200">Local Demo Workspace</p>
          </div>
          <div className="rounded border border-gray-800 bg-gray-950 p-4">
            <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Environment</p>
            <p className="font-mono text-sm text-gray-200">Local Development</p>
          </div>
          <div className="rounded border border-gray-800 bg-gray-950 p-4">
            <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Status</p>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-cyan-400" />
              <span className="font-mono text-sm text-cyan-400">Running</span>
            </div>
          </div>
        </div>
      </div>

      {/* Planned features */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <div className="mb-4 flex items-center gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-cyan-400">
            Planned Features
          </h2>
          <span className="rounded border border-amber-700/40 bg-amber-900/20 px-2 py-0.5 text-xs font-semibold text-amber-400">
            M67
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

      {/* Note */}
      <div className="rounded-lg border border-gray-700 bg-gray-900 p-5 text-sm text-gray-400">
        <p>
          Workspace settings will be editable in <strong className="text-gray-300">M67</strong>.
          No configuration is required for local development — the demo workspace is pre-configured
          and ready to use.
        </p>
      </div>
    </div>
  );
}
