import { useState } from "react";
import type { StrategyVersion, StrategyVersionCreateRequest } from "@/types";
import { createStrategyVersion } from "@/lib/api";

const inputCls =
  "w-full rounded-control border border-border bg-bg-600 px-3 py-2 font-mono text-sm text-text-primary placeholder:text-text-muted focus:border-accent-500 focus:outline-none";

interface Props {
  open: boolean;
  strategyId: string;
  onClose: () => void;
  onCreated: (version: StrategyVersion) => void;
}

export default function VersionCreateDrawer({ open, strategyId, onClose, onCreated }: Props) {
  const [versionLabel, setVersionLabel] = useState("");
  const [gitCommit, setGitCommit] = useState("");
  const [branchName, setBranchName] = useState("");
  const [codePath, setCodePath] = useState("");
  const [signalName, setSignalName] = useState("");
  const [signalDescription, setSignalDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setVersionLabel(""); setGitCommit(""); setBranchName("");
    setCodePath(""); setSignalName(""); setSignalDescription("");
    setError(null); setSubmitting(false);
  }

  function handleClose() { reset(); onClose(); }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!versionLabel.trim()) { setError("Version label is required."); return; }
    setSubmitting(true); setError(null);

    const payload: StrategyVersionCreateRequest = {
      version_label: versionLabel.trim(),
    };
    if (gitCommit.trim()) payload.git_commit = gitCommit.trim();
    if (branchName.trim()) payload.branch_name = branchName.trim();
    if (codePath.trim()) payload.code_path = codePath.trim();
    if (signalName.trim()) payload.signal_name = signalName.trim();
    if (signalDescription.trim()) payload.signal_description = signalDescription.trim();

    try {
      const version = await createStrategyVersion(strategyId, payload);
      reset(); onCreated(version); onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create version.");
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
            <p className="caption">Strategy Version</p>
            <p className="mt-0.5 text-sm font-medium text-text-primary">
              Create a new version
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
          {/* Version label */}
          <div>
            <label className="caption mb-1.5 block">
              Version Label <span className="text-fidelity-low">*</span>
            </label>
            <input
              type="text"
              value={versionLabel}
              onChange={(e) => setVersionLabel(e.target.value)}
              placeholder="e.g. v1.2.0 or 2024-Q1"
              className={inputCls}
              autoFocus
            />
          </div>

          {/* Git commit */}
          <div>
            <label className="caption mb-1.5 block">Git Commit (optional)</label>
            <input
              type="text"
              value={gitCommit}
              onChange={(e) => setGitCommit(e.target.value)}
              placeholder="e.g. abc123def456"
              className={inputCls}
            />
          </div>

          {/* Branch name */}
          <div>
            <label className="caption mb-1.5 block">Branch Name (optional)</label>
            <input
              type="text"
              value={branchName}
              onChange={(e) => setBranchName(e.target.value)}
              placeholder="e.g. feature/ma-crossover"
              className={inputCls}
            />
          </div>

          {/* Code path */}
          <div>
            <label className="caption mb-1.5 block">Code Path (optional)</label>
            <input
              type="text"
              value={codePath}
              onChange={(e) => setCodePath(e.target.value)}
              placeholder="e.g. strategies/mean_reversion.py"
              className={inputCls}
            />
          </div>

          {/* Signal name */}
          <div>
            <label className="caption mb-1.5 block">Signal Name (optional)</label>
            <input
              type="text"
              value={signalName}
              onChange={(e) => setSignalName(e.target.value)}
              placeholder="e.g. 50/200 SMA Crossover"
              className={inputCls}
            />
          </div>

          {/* Signal description */}
          <div>
            <label className="caption mb-1.5 block">Signal Description (optional)</label>
            <textarea
              value={signalDescription}
              onChange={(e) => setSignalDescription(e.target.value)}
              rows={3}
              placeholder="Brief description of the signal logic or hypothesis"
              className={`${inputCls} resize-none`}
            />
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
              {submitting ? "Creating…" : "Create Version"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
