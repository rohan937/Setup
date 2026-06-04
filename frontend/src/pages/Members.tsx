import { useEffect, useState } from "react";
import PageHeader from "@/components/PageHeader";
import NoWorkspaceNotice from "@/components/NoWorkspaceNotice";
import {
  getWorkspaceMembers,
  createWorkspaceMember,
  updateWorkspaceMember,
  removeWorkspaceMember,
} from "@/lib/api";
import type {
  WorkspaceMember,
  WorkspaceMemberCreate,
  WorkspaceMemberUpdate,
} from "@/types";
import { useAuth } from "@/context/AuthContext";
import { canManageMembers, roleBadgeClasses } from "@/lib/permissions";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
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

function RoleBadge({ role }: { role: WorkspaceMember["role"] }) {
  const styles: Record<WorkspaceMember["role"], string> = {
    owner: "border-red-700/40 bg-red-900/20 text-red-400",
    admin: "border-amber-700/40 bg-amber-900/20 text-amber-400",
    member: "border-cyan-700/40 bg-cyan-900/20 text-cyan-400",
    viewer: "border-gray-600/40 bg-gray-800/50 text-gray-400",
  };
  return (
    <span className={`rounded border px-1.5 py-0.5 text-xs font-semibold ${styles[role]}`}>
      {role}
    </span>
  );
}

function StatusBadge({ status }: { status: WorkspaceMember["status"] }) {
  const styles: Record<WorkspaceMember["status"], string> = {
    active: "border-cyan-700/40 bg-cyan-900/20 text-cyan-400",
    invited: "border-amber-700/40 bg-amber-900/20 text-amber-400",
    disabled: "border-gray-600/40 bg-gray-800/50 text-gray-500",
  };
  return (
    <span className={`rounded border px-1.5 py-0.5 text-xs ${styles[status]}`}>
      {status}
    </span>
  );
}

const ROLE_OPTIONS = ["owner", "admin", "member", "viewer"] as const;
const STATUS_OPTIONS = ["active", "invited", "disabled"] as const;

// ---------------------------------------------------------------------------
// Members
// ---------------------------------------------------------------------------

const EMPTY_ADD: WorkspaceMemberCreate = {
  display_name: "",
  email: "",
  role: "member",
  status: "active",
  title: "",
  notes: "",
};

export default function Members() {
  const auth = useAuth();
  const canManage = canManageMembers(auth);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add form
  const [showAddForm, setShowAddForm] = useState(false);
  const [addValues, setAddValues] = useState<WorkspaceMemberCreate>({ ...EMPTY_ADD });
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Inline edit
  const [editingMemberId, setEditingMemberId] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<WorkspaceMemberUpdate>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  function loadMembers() {
    setLoading(true);
    setError(null);
    getWorkspaceMembers()
      .then((data) => setMembers(data.items))
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load members");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadMembers();
  }, []);

  // ---------------------------------------------------------------------------
  // Computed counts
  // ---------------------------------------------------------------------------

  const total = members.length;
  const activeCount = members.filter((m) => m.status === "active").length;
  const invitedCount = members.filter((m) => m.status === "invited").length;
  const disabledCount = members.filter((m) => m.status === "disabled").length;

  const ownerCount = members.filter((m) => m.role === "owner").length;
  const adminCount = members.filter((m) => m.role === "admin").length;
  const memberCount = members.filter((m) => m.role === "member").length;
  const viewerCount = members.filter((m) => m.role === "viewer").length;

  // ---------------------------------------------------------------------------
  // Add member
  // ---------------------------------------------------------------------------

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!addValues.display_name.trim() || !addValues.email.trim()) {
      setAddError("Display name and email are required.");
      return;
    }
    setAdding(true);
    setAddError(null);
    try {
      await createWorkspaceMember({
        ...addValues,
        display_name: addValues.display_name.trim(),
        email: addValues.email.trim(),
        title: addValues.title?.trim() || undefined,
        notes: addValues.notes?.trim() || undefined,
      });
      setAddValues({ ...EMPTY_ADD });
      setShowAddForm(false);
      loadMembers();
    } catch (err: unknown) {
      setAddError(err instanceof Error ? err.message : "Failed to add member");
    } finally {
      setAdding(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Edit member
  // ---------------------------------------------------------------------------

  function startEdit(member: WorkspaceMember) {
    setEditingMemberId(member.id);
    setEditValues({
      role: member.role,
      status: member.status,
      title: member.title ?? "",
    });
    setSaveError(null);
  }

  function cancelEdit() {
    setEditingMemberId(null);
    setEditValues({});
    setSaveError(null);
  }

  async function handleSaveEdit(memberId: string) {
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await updateWorkspaceMember(memberId, {
        role: editValues.role,
        status: editValues.status,
        title: (editValues.title as string | undefined)?.trim() || undefined,
      });
      setMembers((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
      setEditingMemberId(null);
      setEditValues({});
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Failed to save changes");
    } finally {
      setSaving(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Disable member
  // ---------------------------------------------------------------------------

  async function handleDisable(memberId: string) {
    try {
      await removeWorkspaceMember(memberId);
      // Reload to reflect backend state
      loadMembers();
    } catch (err: unknown) {
      // Surface as inline error
      setError(err instanceof Error ? err.message : "Failed to disable member");
    }
  }

  // ---------------------------------------------------------------------------
  // Loading / error
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 px-6 py-6 text-gray-200">
        <PageHeader tag="ADMIN" title="Members" subtitle="Loading..." />
        <div className="flex items-center justify-center py-24 text-sm text-gray-500">
          Loading members...
        </div>
      </div>
    );
  }

  if (error && members.length === 0) {
    return (
      <div className="min-h-screen bg-gray-950 px-6 py-6 text-gray-200">
        <PageHeader tag="ADMIN" title="Members" subtitle="Error loading data" />
        <div className="mb-4">
          <NoWorkspaceNotice />
        </div>
        <div className="rounded-lg border border-red-800/50 bg-red-900/20 p-5 text-sm text-red-400">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 px-6 py-6 text-gray-200">
      <PageHeader
        tag="ADMIN"
        title="Members"
        subtitle="Workspace membership — local metadata foundation"
      />

      <div className="mb-4">
        <NoWorkspaceNotice />
      </div>

      {/* Non-fatal error */}
      {error && (
        <div className="mb-4 rounded-lg border border-red-800/50 bg-red-900/20 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Section A: Members Summary                                           */}
      {/* ------------------------------------------------------------------ */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-cyan-400">
          Members Summary
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          {/* Totals */}
          <div className="rounded border border-gray-800 bg-gray-950 p-4">
            <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Total</p>
            <p className="font-mono text-2xl text-gray-200">{total}</p>
          </div>
          <div className="rounded border border-gray-800 bg-gray-950 p-4">
            <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Active</p>
            <p className="font-mono text-2xl text-cyan-400">{activeCount}</p>
          </div>
          <div className="rounded border border-gray-800 bg-gray-950 p-4">
            <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Invited</p>
            <p className="font-mono text-2xl text-amber-400">{invitedCount}</p>
          </div>
          <div className="rounded border border-gray-800 bg-gray-950 p-4">
            <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Disabled</p>
            <p className="font-mono text-2xl text-gray-500">{disabledCount}</p>
          </div>
          {/* Role breakdown */}
          <div className="rounded border border-gray-800 bg-gray-950 p-4">
            <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Owners</p>
            <p className="font-mono text-2xl text-red-400">{ownerCount}</p>
          </div>
          <div className="rounded border border-gray-800 bg-gray-950 p-4">
            <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Admins</p>
            <p className="font-mono text-2xl text-amber-400">{adminCount}</p>
          </div>
          <div className="rounded border border-gray-800 bg-gray-950 p-4">
            <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Members</p>
            <p className="font-mono text-2xl text-cyan-400">
              {memberCount}
              <span className="ml-1 text-sm text-gray-500">+{viewerCount}v</span>
            </p>
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Section B: Add Member Form (Owner/Admin only)                        */}
      {/* ------------------------------------------------------------------ */}
      {canManage ? (
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-cyan-400">
            Add Member
          </h2>
          <button
            onClick={() => {
              setShowAddForm((v) => !v);
              setAddError(null);
            }}
            className="rounded border border-gray-600 bg-gray-800 px-3 py-1.5 text-xs font-semibold text-gray-300 transition hover:border-cyan-600 hover:text-cyan-300"
          >
            {showAddForm ? "Collapse" : "Add Member"}
          </button>
        </div>

        {showAddForm && (
          <form onSubmit={handleAdd} className="mt-4 space-y-4">
            {addError && (
              <div className="rounded border border-red-800/50 bg-red-900/20 px-4 py-3 text-sm text-red-400">
                {addError}
              </div>
            )}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wider text-gray-400">
                  Display Name <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={addValues.display_name}
                  onChange={(e) =>
                    setAddValues((v) => ({ ...v, display_name: e.target.value }))
                  }
                  placeholder="Jane Smith"
                  className="w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-cyan-600 focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wider text-gray-400">
                  Email <span className="text-red-400">*</span>
                </label>
                <input
                  type="email"
                  required
                  value={addValues.email}
                  onChange={(e) =>
                    setAddValues((v) => ({ ...v, email: e.target.value }))
                  }
                  placeholder="jane@example.com"
                  className="w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-cyan-600 focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wider text-gray-400">
                  Role
                </label>
                <select
                  value={addValues.role}
                  onChange={(e) =>
                    setAddValues((v) => ({ ...v, role: e.target.value }))
                  }
                  className="w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 focus:border-cyan-600 focus:outline-none"
                >
                  {ROLE_OPTIONS.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wider text-gray-400">
                  Status
                </label>
                <select
                  value={addValues.status}
                  onChange={(e) =>
                    setAddValues((v) => ({ ...v, status: e.target.value }))
                  }
                  className="w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 focus:border-cyan-600 focus:outline-none"
                >
                  {STATUS_OPTIONS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wider text-gray-400">
                  Title <span className="text-gray-600">(optional)</span>
                </label>
                <input
                  type="text"
                  value={addValues.title ?? ""}
                  onChange={(e) =>
                    setAddValues((v) => ({ ...v, title: e.target.value }))
                  }
                  placeholder="Quant Researcher"
                  className="w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-cyan-600 focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wider text-gray-400">
                  Notes <span className="text-gray-600">(optional)</span>
                </label>
                <input
                  type="text"
                  value={addValues.notes ?? ""}
                  onChange={(e) =>
                    setAddValues((v) => ({ ...v, notes: e.target.value }))
                  }
                  placeholder="Internal notes..."
                  className="w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-cyan-600 focus:outline-none"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={adding}
              className="rounded border border-cyan-700 bg-cyan-900/30 px-4 py-1.5 text-xs font-semibold text-cyan-300 transition hover:bg-cyan-900/60 disabled:opacity-50"
            >
              {adding ? "Adding..." : "Add Member"}
            </button>
          </form>
        )}
      </div>
      ) : (
        <div className="mb-6 rounded-lg border border-gray-700 bg-gray-950/60 px-5 py-4 font-mono text-xs text-gray-400">
          Read-only access. Only owners/admins can add, edit, or remove members.
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Section C: Members Table                                             */}
      {/* ------------------------------------------------------------------ */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-cyan-400">
          Current Members
        </h2>

        {members.length === 0 ? (
          <div className="flex items-center justify-center rounded border border-dashed border-gray-700 py-10 text-sm text-gray-500">
            No members yet. Use "Add Member" to create the first workspace member.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 text-left">
                  <th className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wider text-gray-500">Name</th>
                  <th className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wider text-gray-500">Email</th>
                  <th className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wider text-gray-500">Role</th>
                  <th className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wider text-gray-500">Status</th>
                  <th className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wider text-gray-500">Title</th>
                  <th className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wider text-gray-500">Added</th>
                  <th className="pb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">Actions</th>
                </tr>
              </thead>
              <tbody>
                {members.map((member) => {
                  const isEditing = editingMemberId === member.id;
                  return (
                    <tr key={member.id} className="border-b border-gray-800 last:border-0">
                      <td className="py-3 pr-4 font-mono text-sm text-gray-200">
                        {member.display_name}
                      </td>
                      <td className="py-3 pr-4 text-sm text-gray-400">{member.email}</td>
                      <td className="py-3 pr-4">
                        {isEditing ? (
                          <select
                            value={editValues.role ?? member.role}
                            onChange={(e) =>
                              setEditValues((v) => ({ ...v, role: e.target.value }))
                            }
                            className="rounded border border-gray-700 bg-gray-950 px-2 py-1 text-xs text-gray-200 focus:border-cyan-600 focus:outline-none"
                          >
                            {ROLE_OPTIONS.map((r) => (
                              <option key={r} value={r}>
                                {r}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <RoleBadge role={member.role} />
                        )}
                      </td>
                      <td className="py-3 pr-4">
                        {isEditing ? (
                          <select
                            value={editValues.status ?? member.status}
                            onChange={(e) =>
                              setEditValues((v) => ({ ...v, status: e.target.value }))
                            }
                            className="rounded border border-gray-700 bg-gray-950 px-2 py-1 text-xs text-gray-200 focus:border-cyan-600 focus:outline-none"
                          >
                            {STATUS_OPTIONS.map((s) => (
                              <option key={s} value={s}>
                                {s}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <StatusBadge status={member.status} />
                        )}
                      </td>
                      <td className="py-3 pr-4">
                        {isEditing ? (
                          <input
                            type="text"
                            value={(editValues.title as string | undefined) ?? member.title ?? ""}
                            onChange={(e) =>
                              setEditValues((v) => ({ ...v, title: e.target.value }))
                            }
                            placeholder="Title..."
                            className="rounded border border-gray-700 bg-gray-950 px-2 py-1 text-xs text-gray-200 focus:border-cyan-600 focus:outline-none"
                          />
                        ) : (
                          <span className="text-sm text-gray-500">{member.title ?? "—"}</span>
                        )}
                      </td>
                      <td className="py-3 pr-4 text-sm text-gray-500">
                        {formatDate(member.created_at)}
                      </td>
                      <td className="py-3">
                        {isEditing ? (
                          <div className="flex flex-col gap-1">
                            {saveError && (
                              <p className="text-xs text-red-400">{saveError}</p>
                            )}
                            <div className="flex gap-2">
                              <button
                                onClick={() => handleSaveEdit(member.id)}
                                disabled={saving}
                                className="rounded border border-cyan-700 bg-cyan-900/30 px-2 py-1 text-xs text-cyan-300 hover:bg-cyan-900/60 disabled:opacity-50"
                              >
                                {saving ? "..." : "Save"}
                              </button>
                              <button
                                onClick={cancelEdit}
                                disabled={saving}
                                className="rounded border border-gray-600 bg-gray-800 px-2 py-1 text-xs text-gray-400 hover:text-gray-200 disabled:opacity-50"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : canManage ? (
                          <div className="flex gap-2">
                            <button
                              onClick={() => startEdit(member)}
                              className="rounded border border-gray-600 bg-gray-800 px-2 py-1 text-xs text-gray-400 transition hover:border-cyan-600 hover:text-cyan-300"
                            >
                              Edit
                            </button>
                            {(member.status === "active" || member.status === "invited") && (
                              <button
                                onClick={() => handleDisable(member.id)}
                                className="rounded border border-gray-700 bg-gray-800/50 px-2 py-1 text-xs text-gray-500 transition hover:border-red-700/50 hover:text-red-400"
                              >
                                Disable
                              </button>
                            )}
                          </div>
                        ) : (
                          <span className="font-mono text-xs text-gray-600">read-only</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Section D: Role Explanation Card                                     */}
      {/* ------------------------------------------------------------------ */}
      <div className="rounded-lg border border-gray-700 bg-gray-900 p-5">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-cyan-400">
          Role Reference
        </h2>
        <div className="space-y-2">
          {[
            {
              role: "owner" as const,
              desc: "Workspace control, future billing and admin access. Typically one per workspace.",
            },
            {
              role: "admin" as const,
              desc: "Manage workspace data, projects, and settings. Can invite/remove members.",
            },
            {
              role: "member" as const,
              desc: "Create and edit research data, run evidence ingestion. Standard research access.",
            },
            {
              role: "viewer" as const,
              desc: "Read-only access to strategies and reports. Cannot create or modify records.",
            },
          ].map(({ role, desc }) => (
            <div
              key={role}
              className="flex items-start gap-3 rounded border border-gray-800 bg-gray-950 px-4 py-3"
            >
              <RoleBadge role={role} />
              <p className="text-sm text-gray-400">{desc}</p>
            </div>
          ))}
        </div>
        <div className="mt-4 flex items-center justify-between rounded border border-gray-800 bg-gray-950 px-4 py-3 text-xs text-gray-400">
          <span>
            Role-based access (RBAC foundation) is active. Member management is{" "}
            <strong className="text-gray-200">Owner/Admin only</strong>.
          </span>
          {auth.isAuthenticated && (
            <span className="flex items-center gap-2 font-mono">
              <span className="uppercase tracking-wider text-gray-500">Your role</span>
              <span className={`rounded border px-1.5 py-0.5 font-semibold ${roleBadgeClasses(auth.role)}`}>
                {auth.role ?? "—"}
              </span>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
