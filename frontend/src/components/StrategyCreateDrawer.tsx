import { useEffect, useState } from "react";
import type { Project, StrategyCreateRequest } from "@/types";
import { createProject, createStrategy, getProjects } from "@/lib/api";

const ASSET_CLASSES = [
  "equity", "etf", "future", "option", "fx", "crypto", "rate", "commodity", "other",
];
const STATUSES = ["active", "draft", "paused", "archived"];

const inputCls =
  "w-full rounded-control border border-border bg-bg-600 px-3 py-2 font-mono text-sm text-text-primary placeholder:text-text-muted focus:border-accent-500 focus:outline-none";

const selectCls =
  "w-full rounded-control border border-border bg-bg-600 px-3 py-2 font-mono text-sm text-text-primary focus:border-accent-500 focus:outline-none";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export default function StrategyCreateDrawer({ open, onClose, onCreated }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [projectsError, setProjectsError] = useState<string | null>(null);
  const [creatingProject, setCreatingProject] = useState(false);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [assetClass, setAssetClass] = useState("equity");
  const [status, setStatus] = useState("active");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function loadProjects() {
    setLoadingProjects(true);
    setProjectsError(null);
    getProjects()
      .then((ps) => {
        setProjects(ps);
        if (ps.length > 0) setProjectId((cur) => cur || ps[0].id);
      })
      .catch(() => setProjectsError("Failed to load projects."))
      .finally(() => setLoadingProjects(false));
  }

  useEffect(() => {
    if (!open) return;
    loadProjects();
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleCreateDefaultProject() {
    setCreatingProject(true);
    setProjectsError(null);
    try {
      const p = await createProject({ name: "Default Project" });
      setProjects((prev) => [...prev, p]);
      setProjectId(p.id);
    } catch (err) {
      setProjectsError(
        err instanceof Error ? err.message : "Failed to create project.",
      );
    } finally {
      setCreatingProject(false);
    }
  }

  function reset() {
    setName(""); setSlug(""); setDescription("");
    setAssetClass("equity"); setStatus("active");
    setError(null); setSubmitting(false);
  }

  function handleClose() { reset(); onClose(); }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) { setError("Name is required."); return; }
    if (!projectId)   { setError("Select a project."); return; }
    setSubmitting(true); setError(null);

    const payload: StrategyCreateRequest = {
      project_id: projectId,
      name: name.trim(),
      asset_class: assetClass,
      status,
    };
    if (slug.trim()) payload.slug = slug.trim();
    if (description.trim()) payload.description = description.trim();

    try {
      await createStrategy(payload);
      reset(); onCreated(); onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create strategy.");
      setSubmitting(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-bg-950/85" aria-hidden="true" onClick={handleClose} />

      {/* Drawer panel */}
      <div className="fixed right-0 top-0 flex h-full w-full max-w-sm flex-col border-l border-border bg-bg-800 shadow-panel">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
          <div>
            <p className="caption">New Strategy</p>
            <p className="mt-0.5 text-sm font-medium text-text-primary">
              Register a strategy
            </p>
          </div>
          <button
            onClick={handleClose}
            className="rounded-control p-1.5 text-text-muted hover:bg-bg-600 hover:text-text-primary"
            aria-label="Close"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M11 3L3 11M3 3l8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex flex-1 flex-col overflow-y-auto px-5 py-5 gap-4">
          {/* Project */}
          <div>
            <label className="caption mb-1.5 block">Project</label>
            {loadingProjects ? (
              <div className={`${selectCls} text-text-muted`}>Loading projects…</div>
            ) : projects.length > 0 ? (
              <select value={projectId} onChange={(e) => setProjectId(e.target.value)} className={selectCls}>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            ) : (
              <div className="rounded-control border border-border bg-bg-600 px-3 py-2.5">
                <p className="font-mono text-2xs text-text-muted">
                  {projectsError
                    ? projectsError
                    : "No projects found. Create one to register a strategy."}
                </p>
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={handleCreateDefaultProject}
                    disabled={creatingProject}
                    className="rounded-control bg-accent-500 px-3 py-1.5 text-2xs font-medium text-text-inverse hover:bg-accent-600 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {creatingProject ? "Creating…" : "Create default project"}
                  </button>
                  {projectsError && (
                    <button
                      type="button"
                      onClick={loadProjects}
                      disabled={creatingProject}
                      className="rounded-control border border-border px-3 py-1.5 text-2xs font-medium text-text-secondary hover:bg-bg-500 hover:text-text-primary disabled:opacity-50"
                    >
                      Retry
                    </button>
                  )}
                </div>
              </div>
            )}
            {projectsError && projects.length > 0 && (
              <p className="mt-1 font-mono text-2xs text-fidelity-low">{projectsError}</p>
            )}
          </div>

          {/* Name */}
          <div>
            <label className="caption mb-1.5 block">
              Name <span className="text-fidelity-low">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. AAPL Mean Reversion v2"
              className={inputCls}
            />
          </div>

          {/* Slug */}
          <div>
            <label className="caption mb-1.5 block">Slug (optional)</label>
            <input
              type="text"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="auto-generated from name"
              className={inputCls}
            />
          </div>

          {/* Description */}
          <div>
            <label className="caption mb-1.5 block">Description (optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Signal hypothesis, universe, edge thesis"
              className={`${inputCls} resize-none`}
            />
          </div>

          {/* Asset Class + Status side-by-side */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="caption mb-1.5 block">Asset Class</label>
              <select value={assetClass} onChange={(e) => setAssetClass(e.target.value)} className={selectCls}>
                {ASSET_CLASSES.map((ac) => <option key={ac} value={ac}>{ac}</option>)}
              </select>
            </div>
            <div>
              <label className="caption mb-1.5 block">Status</label>
              <select value={status} onChange={(e) => setStatus(e.target.value)} className={selectCls}>
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>

          {error && (
            <p className="rounded-control border border-fidelity-low/30 bg-fidelity-low/10 px-3 py-2 font-mono text-2xs text-fidelity-low">
              {error}
            </p>
          )}

          <div className="mt-auto flex gap-2.5 pt-3">
            <button
              type="button"
              onClick={handleClose}
              className="flex-1 rounded-control border border-border px-4 py-2 text-xs font-medium text-text-secondary hover:bg-bg-600 hover:text-text-primary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 rounded-control bg-accent-500 px-4 py-2 text-xs font-medium text-text-inverse hover:bg-accent-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? "Registering…" : "Register Strategy"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
