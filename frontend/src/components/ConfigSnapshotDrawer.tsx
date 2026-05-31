import { useState } from "react";
import type {
  StrategyConfigSnapshotCreateRequest,
  StrategyConfigSnapshotRead,
  StrategyVersion,
} from "@/types";
import { createConfigSnapshot } from "@/lib/api";

const SOURCE_TYPES = ["manual_json", "file_upload", "code_gen", "other"];

const inputCls =
  "w-full rounded-control border border-border bg-bg-600 px-3 py-2 font-mono text-sm text-text-primary placeholder:text-text-muted focus:border-accent-500 focus:outline-none";

const selectCls =
  "w-full rounded-control border border-border bg-bg-600 px-3 py-2 font-mono text-sm text-text-primary focus:border-accent-500 focus:outline-none";

interface Props {
  open: boolean;
  strategyId: string;
  versions: StrategyVersion[];
  onClose: () => void;
  onCreated: (snapshot: StrategyConfigSnapshotRead) => void;
}

export default function ConfigSnapshotDrawer({
  open,
  strategyId,
  versions,
  onClose,
  onCreated,
}: Props) {
  const [label, setLabel] = useState("");
  const [versionId, setVersionId] = useState("");
  const [sourceType, setSourceType] = useState("manual_json");
  const [sourceFilename, setSourceFilename] = useState("");
  const [configRaw, setConfigRaw] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setLabel(""); setVersionId(""); setSourceType("manual_json");
    setSourceFilename(""); setConfigRaw("");
    setError(null); setSubmitting(false);
  }

  function handleClose() { reset(); onClose(); }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!label.trim()) { setError("Label is required."); return; }
    if (!configRaw.trim()) { setError("Config JSON is required."); return; }

    let configJson: Record<string, unknown>;
    try {
      const parsed: unknown = JSON.parse(configRaw);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        setError("Config JSON must be a JSON object ({}), not an array or primitive.");
        return;
      }
      configJson = parsed as Record<string, unknown>;
    } catch {
      setError("Invalid JSON — please fix the syntax and try again.");
      return;
    }

    setSubmitting(true); setError(null);

    const payload: StrategyConfigSnapshotCreateRequest = {
      label: label.trim(),
      source_type: sourceType,
      config_json: configJson,
    };
    if (versionId) payload.strategy_version_id = versionId;
    if (sourceFilename.trim()) payload.source_filename = sourceFilename.trim();

    try {
      const snapshot = await createConfigSnapshot(strategyId, payload);
      reset(); onCreated(snapshot); onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create config snapshot.");
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
            <p className="caption">Config Snapshot</p>
            <p className="mt-0.5 text-sm font-medium text-text-primary">
              Log a config snapshot
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
          {/* Label */}
          <div>
            <label className="caption mb-1.5 block">
              Label <span className="text-fidelity-low">*</span>
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. prod-config-2024-Q1"
              className={inputCls}
              autoFocus
            />
          </div>

          {/* Strategy version */}
          <div>
            <label className="caption mb-1.5 block">Strategy Version (optional)</label>
            <select
              value={versionId}
              onChange={(e) => setVersionId(e.target.value)}
              className={selectCls}
            >
              <option value="">— not linked to a version —</option>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.version_label}
                  {v.branch_name ? ` (${v.branch_name})` : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Source type + filename side-by-side */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="caption mb-1.5 block">Source Type</label>
              <select
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value)}
                className={selectCls}
              >
                {SOURCE_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="caption mb-1.5 block">Source Filename</label>
              <input
                type="text"
                value={sourceFilename}
                onChange={(e) => setSourceFilename(e.target.value)}
                placeholder="config.json"
                className={inputCls}
              />
            </div>
          </div>

          {/* Config JSON */}
          <div className="flex flex-1 flex-col">
            <label className="caption mb-1.5 block">
              Config JSON <span className="text-fidelity-low">*</span>
            </label>
            <textarea
              value={configRaw}
              onChange={(e) => setConfigRaw(e.target.value)}
              rows={10}
              placeholder={`{\n  "params": {\n    "lookback": 20,\n    "threshold": 0.5\n  },\n  "assumptions": {\n    "slippage": 0.001\n  }\n}`}
              className={`${inputCls} flex-1 resize-none font-mono text-xs leading-relaxed`}
              spellCheck={false}
            />
            <p className="mt-1 font-mono text-2xs text-text-muted">
              Must be a JSON object. Keys under "params" and "assumptions" are counted automatically.
            </p>
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
              {submitting ? "Logging…" : "Log Snapshot"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
