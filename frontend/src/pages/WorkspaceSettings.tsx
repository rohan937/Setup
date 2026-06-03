import { useEffect, useState } from "react";
import PageHeader from "@/components/PageHeader";
import {
  getWorkspaceSummary,
  updateWorkspaceSettings,
} from "@/lib/api";
import type { WorkspaceSummary, WorkspaceProjectSummary } from "@/types";
import { useAuth } from "@/context/AuthContext";
import { canManageWorkspace, roleBadgeClasses } from "@/lib/permissions";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------------------
// WorkspaceSettings
// ---------------------------------------------------------------------------

export default function WorkspaceSettings() {
  const auth = useAuth();
  const canEdit = canManageWorkspace(auth);
  const [summary, setSummary] = useState<WorkspaceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit state
  const [editMode, setEditMode] = useState(false);
  const [editValues, setEditValues] = useState({
    display_name: "",
    description: "",
    website: "",
  });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getWorkspaceSummary()
      .then((data) => {
        setSummary(data);
        setEditValues({
          display_name: data.display_name ?? "",
          description: data.description ?? "",
          website: data.website ?? "",
        });
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load workspace settings");
      })
      .finally(() => setLoading(false));
  }, []);

  function handleEditToggle() {
    if (!editMode && summary) {
      setEditValues({
        display_name: summary.display_name ?? "",
        description: summary.description ?? "",
        website: summary.website ?? "",
      });
    }
    setSaveError(null);
    setSaveSuccess(false);
    setEditMode((v) => !v);
  }

  function handleCancel() {
    if (summary) {
      setEditValues({
        display_name: summary.display_name ?? "",
        description: summary.description ?? "",
        website: summary.website ?? "",
      });
    }
    setSaveError(null);
    setSaveSuccess(false);
    setEditMode(false);
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(false);
    try {
      const updated = await updateWorkspaceSettings({
        display_name: editValues.display_name || undefined,
        description: editValues.description || undefined,
        website: editValues.website || undefined,
      });
      setSummary(updated);
      setSaveSuccess(true);
      setEditMode(false);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Loading / error states
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 px-6 py-6 text-gray-200">
        <PageHeader tag="ADMIN" title="Workspace Settings" subtitle="Loading..." />
        <div className="flex items-center justify-center py-24 text-sm text-gray-500">
          Loading workspace settings...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-950 px-6 py-6 text-gray-200">
        <PageHeader tag="ADMIN" title="Workspace Settings" subtitle="Error loading data" />
        <div className="rounded-lg border border-red-800/50 bg-red-900/20 p-5 text-sm text-red-400">
          {error}
        </div>
      </div>
    );
  }

  const displayedName = summary?.display_name ?? summary?.workspace_name ?? "—";

  return (
    <div className="min-h-screen bg-gray-950 px-6 py-6 text-gray-200">
      <PageHeader
        tag="ADMIN"
        title="Workspace Settings"
        subtitle="Overview and editable workspace metadata"
      />

      {/* Success banner */}
      {saveSuccess && (
        <div className="mb-4 rounded-lg border border-cyan-700/40 bg-cyan-900/20 px-4 py-3 text-sm text-cyan-300">
          Settings saved successfully.
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Section A: Workspace Overview                                        */}
      {/* ------------------------------------------------------------------ */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-cyan-400">
          Workspace Overview
        </h2>

        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {/* Name */}
          <div className="rounded border border-gray-800 bg-gray-950 p-4 sm:col-span-2 lg:col-span-2">
            <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Workspace Name</p>
            <p className="font-mono text-sm text-gray-200 break-all">{displayedName}</p>
          </div>
          {/* Projects */}
          <div className="rounded border border-gray-800 bg-gray-950 p-4">
            <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Projects</p>
            <p className="font-mono text-xl text-cyan-400">{summary?.project_count ?? 0}</p>
          </div>
          {/* Strategies */}
          <div className="rounded border border-gray-800 bg-gray-950 p-4">
            <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Strategies</p>
            <p className="font-mono text-xl text-cyan-400">{summary?.strategy_count ?? 0}</p>
          </div>
          {/* Members */}
          <div className="rounded border border-gray-800 bg-gray-950 p-4">
            <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Members</p>
            <p className="font-mono text-xl text-cyan-400">
              {summary?.active_member_count ?? 0}
              <span className="text-sm text-gray-500">/{summary?.member_count ?? 0}</span>
            </p>
          </div>
          {/* API Keys */}
          <div className="rounded border border-gray-800 bg-gray-950 p-4">
            <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">API Keys</p>
            <p className="font-mono text-xl text-cyan-400">{summary?.api_key_count ?? 0}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded border border-gray-800 bg-gray-950 px-4 py-3">
            <span className="text-xs uppercase tracking-wider text-gray-500">Created: </span>
            <span className="font-mono text-sm text-gray-300">{formatDate(summary?.created_at ?? null)}</span>
          </div>
          <div className="rounded border border-gray-800 bg-gray-950 px-4 py-3">
            <span className="text-xs uppercase tracking-wider text-gray-500">Updated: </span>
            <span className="font-mono text-sm text-gray-300">{formatDate(summary?.updated_at ?? null)}</span>
          </div>
        </div>

        {/* Readiness note */}
        {summary?.readiness_note && (
          <div className="mt-4 rounded border border-gray-700 bg-gray-950/60 px-4 py-3 text-xs text-gray-400">
            {summary.readiness_note}
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Section B: Editable Settings                                         */}
      {/* ------------------------------------------------------------------ */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-cyan-400">
            Editable Settings
          </h2>
          {!editMode && canEdit && (
            <button
              onClick={handleEditToggle}
              className="rounded border border-gray-600 bg-gray-800 px-3 py-1.5 text-xs font-semibold text-gray-300 transition hover:border-cyan-600 hover:text-cyan-300"
            >
              Edit
            </button>
          )}
        </div>

        {!canEdit && (
          <div className="mb-4 rounded border border-gray-700 bg-gray-950/60 px-4 py-3 font-mono text-xs text-gray-400">
            Read-only access. Only owners/admins can edit workspace settings.
          </div>
        )}

        {!editMode ? (
          <div className="space-y-3">
            <div className="rounded border border-gray-800 bg-gray-950 px-4 py-3">
              <p className="mb-0.5 text-xs uppercase tracking-wider text-gray-500">Display Name</p>
              <p className="text-sm text-gray-300">{summary?.display_name || <span className="text-gray-600">Not set</span>}</p>
            </div>
            <div className="rounded border border-gray-800 bg-gray-950 px-4 py-3">
              <p className="mb-0.5 text-xs uppercase tracking-wider text-gray-500">Description</p>
              <p className="text-sm text-gray-300">{summary?.description || <span className="text-gray-600">Not set</span>}</p>
            </div>
            <div className="rounded border border-gray-800 bg-gray-950 px-4 py-3">
              <p className="mb-0.5 text-xs uppercase tracking-wider text-gray-500">Website</p>
              <p className="text-sm text-gray-300">{summary?.website || <span className="text-gray-600">Not set</span>}</p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {saveError && (
              <div className="rounded border border-red-800/50 bg-red-900/20 px-4 py-3 text-sm text-red-400">
                {saveError}
              </div>
            )}
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wider text-gray-400">
                Display Name
              </label>
              <input
                type="text"
                value={editValues.display_name}
                onChange={(e) =>
                  setEditValues((v) => ({ ...v, display_name: e.target.value }))
                }
                placeholder="e.g. Acme Research"
                className="w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-cyan-600 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wider text-gray-400">
                Description
              </label>
              <textarea
                rows={3}
                value={editValues.description}
                onChange={(e) =>
                  setEditValues((v) => ({ ...v, description: e.target.value }))
                }
                placeholder="Brief description of this workspace..."
                className="w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-cyan-600 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wider text-gray-400">
                Website
              </label>
              <input
                type="url"
                value={editValues.website}
                onChange={(e) =>
                  setEditValues((v) => ({ ...v, website: e.target.value }))
                }
                placeholder="https://example.com"
                className="w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-cyan-600 focus:outline-none"
              />
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={handleSave}
                disabled={saving}
                className="rounded border border-cyan-700 bg-cyan-900/30 px-4 py-1.5 text-xs font-semibold text-cyan-300 transition hover:bg-cyan-900/60 disabled:opacity-50"
              >
                {saving ? "Saving..." : "Save"}
              </button>
              <button
                onClick={handleCancel}
                disabled={saving}
                className="rounded border border-gray-600 bg-gray-800 px-4 py-1.5 text-xs font-semibold text-gray-400 transition hover:text-gray-200 disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Section C: Projects in Workspace                                     */}
      {/* ------------------------------------------------------------------ */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-cyan-400">
          Projects in Workspace
        </h2>

        {!summary?.projects?.length ? (
          <div className="flex flex-col items-center justify-center gap-3 rounded border border-dashed border-gray-700 py-10 text-sm text-gray-500">
            <p>No projects found. Run demo seed to create a workspace with projects.</p>
            <div className="flex gap-3">
              <a
                href="/portfolio"
                className="rounded border border-gray-600 px-3 py-1.5 text-xs text-gray-400 hover:text-cyan-300 hover:border-cyan-600 transition"
              >
                View Portfolio
              </a>
              <a
                href="/strategies"
                className="rounded border border-gray-600 px-3 py-1.5 text-xs text-gray-400 hover:text-cyan-300 hover:border-cyan-600 transition"
              >
                View Strategies
              </a>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 text-left">
                  <th className="pb-2 pr-6 text-xs font-semibold uppercase tracking-wider text-gray-500">Name</th>
                  <th className="pb-2 pr-6 text-xs font-semibold uppercase tracking-wider text-gray-500">Strategies</th>
                  <th className="pb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">Created</th>
                </tr>
              </thead>
              <tbody>
                {summary.projects.map((proj: WorkspaceProjectSummary) => (
                  <tr key={proj.project_id} className="border-b border-gray-800 last:border-0">
                    <td className="py-3 pr-6 font-mono text-sm text-gray-200">{proj.name}</td>
                    <td className="py-3 pr-6">
                      <span className="font-mono text-cyan-400">{proj.strategy_count}</span>
                    </td>
                    <td className="py-3 text-sm text-gray-400">{formatDate(proj.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Section D: RBAC status                                               */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-900 px-5 py-4 text-sm text-gray-400">
        <span>
          Role-based access (RBAC foundation): workspace settings are{" "}
          <strong className="text-gray-200">Owner/Admin only</strong>.
        </span>
        {auth.isAuthenticated && (
          <span className="flex items-center gap-2 font-mono text-xs">
            <span className="uppercase tracking-wider text-gray-500">Your role</span>
            <span className={`rounded border px-1.5 py-0.5 font-semibold ${roleBadgeClasses(auth.role)}`}>
              {auth.role ?? "—"}
            </span>
          </span>
        )}
      </div>
    </div>
  );
}
