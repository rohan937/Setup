import { useState } from "react";
import type {
  UniverseSnapshotCreateRequest,
  UniverseSnapshotRead,
  StrategyVersion,
} from "@/types";
import { createUniverseSnapshot } from "@/lib/api";

const SOURCE_TYPES = ["manual_json", "csv_import", "file_upload", "code_gen", "other"];

const inputCls =
  "w-full rounded-control border border-border bg-bg-600 px-3 py-2 font-mono text-sm text-text-primary placeholder:text-text-muted focus:border-accent-500 focus:outline-none";

const selectCls =
  "w-full rounded-control border border-border bg-bg-600 px-3 py-2 font-mono text-sm text-text-primary focus:border-accent-500 focus:outline-none";

interface Props {
  open: boolean;
  strategyId: string;
  versions: StrategyVersion[];
  onClose: () => void;
  onCreated: (snapshot: UniverseSnapshotRead) => void;
}

export default function UniverseSnapshotDrawer({
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
  const [symbolsRaw, setSymbolsRaw] = useState("");
  const [metaRaw, setMetaRaw] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setLabel(""); setVersionId(""); setSourceType("manual_json");
    setSourceFilename(""); setSymbolsRaw(""); setMetaRaw("");
    setError(null); setSubmitting(false);
  }

  function handleClose() { reset(); onClose(); }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!label.trim()) { setError("Label is required."); return; }

    // Parse symbols — one per line, commas also accepted
    const rawSymbols = symbolsRaw
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean);

    if (rawSymbols.length === 0) {
      setError("At least one symbol is required.");
      return;
    }

    // Parse optional metadata JSON
    let metaJson: Record<string, unknown> | undefined;
    if (metaRaw.trim()) {
      try {
        const parsed: unknown = JSON.parse(metaRaw.trim());
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          setError("Metadata JSON must be a JSON object ({}).");
          return;
        }
        metaJson = parsed as Record<string, unknown>;
      } catch {
        setError("Metadata JSON is invalid — please fix the syntax and try again.");
        return;
      }
    }

    setSubmitting(true); setError(null);

    const payload: UniverseSnapshotCreateRequest = {
      label: label.trim(),
      source_type: sourceType,
      symbols: rawSymbols,
    };
    if (versionId) payload.strategy_version_id = versionId;
    if (sourceFilename.trim()) payload.source_filename = sourceFilename.trim();
    if (metaJson) payload.metadata_json = metaJson;

    try {
      const snapshot = await createUniverseSnapshot(strategyId, payload);
      reset(); onCreated(snapshot); onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create universe snapshot.");
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
            <p className="caption">Universe Snapshot</p>
            <p className="mt-0.5 text-sm font-medium text-text-primary">
              Log a universe snapshot
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
              placeholder="e.g. SP500-2024-Q1"
              className={inputCls}
              autoFocus
            />
          </div>

          {/* Strategy version */}
          {versions.length > 0 && (
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
          )}

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
                placeholder="universe.csv"
                className={inputCls}
              />
            </div>
          </div>

          {/* Symbols */}
          <div className="flex flex-1 flex-col">
            <label className="caption mb-1.5 block">
              Symbols <span className="text-fidelity-low">*</span>
            </label>
            <textarea
              value={symbolsRaw}
              onChange={(e) => setSymbolsRaw(e.target.value)}
              rows={10}
              placeholder={"AAPL\nMSFT\nGOOG\nAMZN\nTSLA"}
              className={`${inputCls} flex-1 resize-none font-mono text-xs leading-relaxed`}
              spellCheck={false}
            />
            <p className="mt-1 font-mono text-2xs text-text-muted">
              One symbol per line (or comma-separated). Symbols are normalized:
              trimmed, uppercased, deduplicated, sorted.
            </p>
          </div>

          {/* Optional metadata JSON */}
          <div>
            <label className="caption mb-1.5 block">Metadata JSON (optional)</label>
            <textarea
              value={metaRaw}
              onChange={(e) => setMetaRaw(e.target.value)}
              rows={3}
              placeholder={'{"exchange": "NASDAQ", "as_of_date": "2024-01-01"}'}
              className={`${inputCls} resize-none font-mono text-xs`}
              spellCheck={false}
            />
            <p className="mt-1 font-mono text-2xs text-text-muted">
              Optional JSON object. Included in the universe hash.
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
