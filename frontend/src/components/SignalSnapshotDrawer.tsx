import { useState } from "react";
import type {
  SignalSnapshotCreateRequest,
  SignalSnapshotRead,
  StrategyVersion,
  UniverseSnapshotRead,
} from "@/types";
import { createSignalSnapshot } from "@/lib/api";

const SOURCE_TYPES = ["manual_json", "csv_import", "file_upload", "code_gen", "other"];

const inputCls =
  "w-full rounded-control border border-border bg-bg-600 px-3 py-2 font-mono text-sm text-text-primary placeholder:text-text-muted focus:border-accent-500 focus:outline-none";

const selectCls =
  "w-full rounded-control border border-border bg-bg-600 px-3 py-2 font-mono text-sm text-text-primary focus:border-accent-500 focus:outline-none";

interface Props {
  open: boolean;
  strategyId: string;
  versions: StrategyVersion[];
  universeSnapshots?: UniverseSnapshotRead[];
  onClose: () => void;
  onCreated: (snapshot: SignalSnapshotRead) => void;
}

export default function SignalSnapshotDrawer({
  open,
  strategyId,
  versions,
  universeSnapshots = [],
  onClose,
  onCreated,
}: Props) {
  const [label, setLabel] = useState("");
  const [versionId, setVersionId] = useState("");
  const [universeSnapshotId, setUniverseSnapshotId] = useState("");
  const [signalName, setSignalName] = useState("");
  const [sourceType, setSourceType] = useState("manual_json");
  const [sourceFilename, setSourceFilename] = useState("");
  const [signalColumn, setSignalColumn] = useState("signal");
  const [rowsRaw, setRowsRaw] = useState("");
  const [metaRaw, setMetaRaw] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setLabel("");
    setVersionId("");
    setUniverseSnapshotId("");
    setSignalName("");
    setSourceType("manual_json");
    setSourceFilename("");
    setSignalColumn("signal");
    setRowsRaw("");
    setMetaRaw("");
    setError(null);
    setSubmitting(false);
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (!label.trim()) {
      setError("Label is required.");
      return;
    }

    // Parse rows JSON
    const trimmedRows = rowsRaw.trim();
    if (!trimmedRows) {
      setError("Rows JSON is required.");
      return;
    }

    let parsedRows: Record<string, unknown>[];
    try {
      const parsed: unknown = JSON.parse(trimmedRows);
      if (!Array.isArray(parsed)) {
        setError("Rows must be a JSON array — e.g. [{\"symbol\": \"AAPL\", \"signal\": 0.5}, ...]");
        return;
      }
      if (parsed.length === 0) {
        setError("Rows must have at least one element.");
        return;
      }
      parsedRows = parsed as Record<string, unknown>[];
    } catch {
      setError("Rows JSON is invalid — please fix the syntax and try again.");
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

    setSubmitting(true);
    setError(null);

    const payload: SignalSnapshotCreateRequest = {
      label: label.trim(),
      source_type: sourceType,
      rows: parsedRows,
    };
    if (versionId) payload.strategy_version_id = versionId;
    if (universeSnapshotId) payload.universe_snapshot_id = universeSnapshotId;
    if (signalName.trim()) payload.signal_name = signalName.trim();
    if (sourceFilename.trim()) payload.source_filename = sourceFilename.trim();
    if (signalColumn.trim() && signalColumn.trim() !== "signal") {
      payload.signal_column = signalColumn.trim();
    }
    if (metaJson) payload.metadata_json = metaJson;

    try {
      const snapshot = await createSignalSnapshot(strategyId, payload);
      reset();
      onCreated(snapshot);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create signal snapshot.");
      setSubmitting(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-bg-950/85"
        aria-hidden="true"
        onClick={handleClose}
      />

      {/* Drawer panel */}
      <div className="fixed right-0 top-0 flex h-full w-full max-w-sm flex-col border-l border-border bg-bg-800 shadow-panel">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
          <div>
            <p className="caption">Signal Snapshot</p>
            <p className="mt-0.5 text-sm font-medium text-text-primary">
              Log a signal snapshot
            </p>
          </div>
          <button
            onClick={handleClose}
            className="rounded-control p-1.5 text-text-muted hover:bg-bg-600 hover:text-text-primary"
            aria-label="Close"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path
                d="M11 3L3 11M3 3l8 8"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>

        {/* Form */}
        <form
          onSubmit={handleSubmit}
          className="flex flex-1 flex-col overflow-y-auto px-5 py-5 gap-4"
        >
          {/* Label */}
          <div>
            <label className="caption mb-1.5 block">
              Label <span className="text-fidelity-low">*</span>
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. momentum-12m-2024-Q1"
              className={inputCls}
              autoFocus
            />
          </div>

          {/* Signal Name */}
          <div>
            <label className="caption mb-1.5 block">Signal Name (optional)</label>
            <input
              type="text"
              value={signalName}
              onChange={(e) => setSignalName(e.target.value)}
              placeholder="e.g. momentum_12m"
              className={inputCls}
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

          {/* Universe snapshot */}
          {universeSnapshots.length > 0 && (
            <div>
              <label className="caption mb-1.5 block">Universe Snapshot (optional)</label>
              <select
                value={universeSnapshotId}
                onChange={(e) => setUniverseSnapshotId(e.target.value)}
                className={selectCls}
              >
                <option value="">— not linked to a universe snapshot —</option>
                {universeSnapshots.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.label} · {u.symbol_count} symbols
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Source type + filename */}
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
                placeholder="signal.csv"
                className={inputCls}
              />
            </div>
          </div>

          {/* Signal column name */}
          <div>
            <label className="caption mb-1.5 block">Signal Column Name</label>
            <input
              type="text"
              value={signalColumn}
              onChange={(e) => setSignalColumn(e.target.value)}
              placeholder="signal"
              className={inputCls}
            />
            <p className="mt-1 font-mono text-2xs text-text-muted">
              Column key that holds the signal value in each row object. Defaults to "signal".
            </p>
          </div>

          {/* Rows JSON */}
          <div className="flex flex-1 flex-col">
            <label className="caption mb-1.5 block">
              Rows JSON <span className="text-fidelity-low">*</span>
            </label>
            <textarea
              value={rowsRaw}
              onChange={(e) => setRowsRaw(e.target.value)}
              rows={10}
              placeholder={`[
  {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.52},
  {"symbol": "MSFT", "timestamp": "2024-01-01", "signal": 0.78},
  {"symbol": "GOOG", "timestamp": "2024-01-01", "signal": 0.34}
]`}
              className={`${inputCls} flex-1 resize-none font-mono text-xs leading-relaxed`}
              spellCheck={false}
            />
            <p className="mt-1 font-mono text-2xs text-text-muted">
              JSON array of objects. Must have at least one row. Statistics and quality score
              are computed from the signal column.
            </p>
          </div>

          {/* Optional metadata JSON */}
          <div>
            <label className="caption mb-1.5 block">Metadata JSON (optional)</label>
            <textarea
              value={metaRaw}
              onChange={(e) => setMetaRaw(e.target.value)}
              rows={3}
              placeholder={'{"alpha_type": "momentum", "lookback_months": 12}'}
              className={`${inputCls} resize-none font-mono text-xs`}
              spellCheck={false}
            />
            <p className="mt-1 font-mono text-2xs text-text-muted">
              Optional JSON object. Included in the signal hash.
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
