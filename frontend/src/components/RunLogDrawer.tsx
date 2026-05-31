import { useEffect, useState } from "react";
import type { Dataset, DatasetSnapshotRead, StrategyRunCreateRequest } from "@/types";
import { createStrategyRun, getDatasets, getDatasetSnapshots } from "@/lib/api";

const RUN_TYPES = ["backtest", "research", "paper", "live"] as const;
const RUN_STATUSES = ["completed", "running", "failed", "pending", "canceled"] as const;

const inputCls =
  "w-full rounded-control border border-border bg-bg-600 px-3 py-2 font-mono text-sm text-text-primary placeholder:text-text-muted focus:border-accent-500 focus:outline-none";

const selectCls =
  "w-full rounded-control border border-border bg-bg-600 px-3 py-2 font-mono text-sm text-text-primary focus:border-accent-500 focus:outline-none";

const textareaCls =
  "w-full rounded-control border border-border bg-bg-600 px-3 py-2 font-mono text-xs text-text-primary placeholder:text-text-muted focus:border-accent-500 focus:outline-none resize-none";

interface Props {
  open: boolean;
  strategyId: string;
  onClose: () => void;
  onLogged: () => void;
}

/** Parse a JSON textarea value.
 *  Returns the parsed dict, null (empty field), or throws an Error with a user-readable message.
 */
function parseJsonField(
  text: string,
  fieldName: string,
): Record<string, unknown> | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new Error(`${fieldName} contains invalid JSON.`);
  }
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    Array.isArray(parsed)
  ) {
    throw new Error(
      `${fieldName} must be a JSON object — e.g. {"key": "value"} — not an array or scalar.`,
    );
  }
  return parsed as Record<string, unknown>;
}

function healthColor(score: number): string {
  if (score >= 90) return "text-fidelity-high";
  if (score >= 60) return "text-fidelity-medium";
  return "text-fidelity-low";
}

export default function RunLogDrawer({ open, strategyId, onClose, onLogged }: Props) {
  const [runName, setRunName] = useState("");
  const [runType, setRunType] = useState<string>("backtest");
  const [status, setStatus] = useState<string>("completed");
  const [universeName, setUniverseName] = useState("");
  const [datasetVersion, setDatasetVersion] = useState("");
  const [notes, setNotes] = useState("");
  const [metricsText, setMetricsText] = useState("");
  const [paramsText, setParamsText] = useState("");
  const [assumptionsText, setAssumptionsText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // M7: dataset snapshot selector state
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("");
  const [snapshots, setSnapshots] = useState<DatasetSnapshotRead[]>([]);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string>("");
  const [loadingDatasets, setLoadingDatasets] = useState(false);
  const [loadingSnapshots, setLoadingSnapshots] = useState(false);

  // Load datasets when drawer opens.
  useEffect(() => {
    if (!open) return;
    setLoadingDatasets(true);
    getDatasets()
      .then(setDatasets)
      .catch(() => setDatasets([]))
      .finally(() => setLoadingDatasets(false));
  }, [open]);

  // Load snapshots when a dataset is selected.
  useEffect(() => {
    if (!selectedDatasetId) {
      setSnapshots([]);
      setSelectedSnapshotId("");
      return;
    }
    setLoadingSnapshots(true);
    getDatasetSnapshots(selectedDatasetId)
      .then(setSnapshots)
      .catch(() => setSnapshots([]))
      .finally(() => setLoadingSnapshots(false));
  }, [selectedDatasetId]);

  function reset() {
    setRunName("");
    setRunType("backtest");
    setStatus("completed");
    setUniverseName("");
    setDatasetVersion("");
    setNotes("");
    setMetricsText("");
    setParamsText("");
    setAssumptionsText("");
    setSelectedDatasetId("");
    setSelectedSnapshotId("");
    setSnapshots([]);
    setError(null);
    setSubmitting(false);
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!runName.trim()) {
      setError("Run name is required.");
      return;
    }
    setError(null);

    let metricsJson: Record<string, unknown> | null = null;
    let paramsJson: Record<string, unknown> | null = null;
    let assumptionsJson: Record<string, unknown> | null = null;

    try {
      metricsJson = parseJsonField(metricsText, "Metrics JSON");
      paramsJson = parseJsonField(paramsText, "Params JSON");
      assumptionsJson = parseJsonField(assumptionsText, "Assumptions JSON");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid JSON.");
      return;
    }

    setSubmitting(true);

    const payload: StrategyRunCreateRequest = {
      run_name: runName.trim(),
      run_type: runType,
      status,
      ...(universeName.trim() && { universe_name: universeName.trim() }),
      ...(datasetVersion.trim() && { dataset_version: datasetVersion.trim() }),
      ...(notes.trim() && { notes: notes.trim() }),
      ...(metricsJson !== null && { metrics_json: metricsJson }),
      ...(paramsJson !== null && { params_json: paramsJson }),
      ...(assumptionsJson !== null && { assumptions_json: assumptionsJson }),
      // M7: include linked snapshot id when selected
      ...(selectedSnapshotId && { dataset_snapshot_id: selectedSnapshotId }),
    };

    try {
      await createStrategyRun(strategyId, payload);
      reset();
      onLogged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to log run.");
      setSubmitting(false);
    }
  }

  if (!open) return null;

  const selectedSnap = snapshots.find((s) => s.id === selectedSnapshotId);

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
            <p className="caption">Run Evidence</p>
            <p className="mt-0.5 text-sm font-medium text-text-primary">
              Log a run
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
          className="flex flex-1 flex-col gap-4 overflow-y-auto px-5 py-5"
        >
          {/* Run Name */}
          <div>
            <label className="caption mb-1.5 block">
              Run Name <span className="text-fidelity-low">*</span>
            </label>
            <input
              type="text"
              value={runName}
              onChange={(e) => setRunName(e.target.value)}
              placeholder="e.g. Baseline Backtest 2024-Q1"
              className={inputCls}
            />
          </div>

          {/* Run Type + Status */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="caption mb-1.5 block">
                Run Type <span className="text-fidelity-low">*</span>
              </label>
              <select
                value={runType}
                onChange={(e) => setRunType(e.target.value)}
                className={selectCls}
              >
                {RUN_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="caption mb-1.5 block">Status</label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className={selectCls}
              >
                {RUN_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* M7: Dataset Snapshot selector */}
          <div className="space-y-2 rounded-control border border-border/60 bg-bg-700 p-3">
            <p className="caption text-text-secondary">Data Evidence (optional)</p>

            {/* Dataset select */}
            <div>
              <label className="caption mb-1 block">Dataset</label>
              <select
                value={selectedDatasetId}
                onChange={(e) => {
                  setSelectedDatasetId(e.target.value);
                  setSelectedSnapshotId("");
                }}
                className={selectCls}
                disabled={loadingDatasets}
              >
                <option value="">
                  {loadingDatasets ? "Loading…" : "— no dataset linked —"}
                </option>
                {datasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.dataset_type})
                  </option>
                ))}
              </select>
            </div>

            {/* Snapshot select — shown once a dataset is chosen */}
            {selectedDatasetId && (
              <div>
                <label className="caption mb-1 block">Snapshot</label>
                <select
                  value={selectedSnapshotId}
                  onChange={(e) => setSelectedSnapshotId(e.target.value)}
                  className={selectCls}
                  disabled={loadingSnapshots}
                >
                  <option value="">
                    {loadingSnapshots ? "Loading…" : "— select snapshot —"}
                  </option>
                  {snapshots.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.version_label} · {s.row_count} rows · ⬤{" "}
                      {s.health_score}/100
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Health score preview for selected snapshot */}
            {selectedSnap && (
              <div className="flex items-center gap-2 pt-1">
                <span className="font-mono text-2xs text-text-muted">
                  health
                </span>
                <span
                  className={`mono-num text-sm font-semibold ${healthColor(selectedSnap.health_score)}`}
                >
                  {selectedSnap.health_score}/100
                </span>
                <span className="font-mono text-2xs text-text-muted">
                  · {selectedSnap.row_count} rows
                </span>
              </div>
            )}
          </div>

          {/* Universe + Dataset Version */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="caption mb-1.5 block">Universe (optional)</label>
              <input
                type="text"
                value={universeName}
                onChange={(e) => setUniverseName(e.target.value)}
                placeholder="SP500"
                className={inputCls}
              />
            </div>
            <div>
              <label className="caption mb-1.5 block">Dataset Ver. (optional)</label>
              <input
                type="text"
                value={datasetVersion}
                onChange={(e) => setDatasetVersion(e.target.value)}
                placeholder="v2024-01"
                className={inputCls}
              />
            </div>
          </div>

          {/* Metrics JSON */}
          <div>
            <label className="caption mb-1.5 block">Metrics JSON (optional)</label>
            <textarea
              value={metricsText}
              onChange={(e) => setMetricsText(e.target.value)}
              rows={3}
              placeholder={'{"sharpe": 1.4, "max_drawdown": -0.12, "annual_return": 0.18}'}
              className={textareaCls}
            />
          </div>

          {/* Params JSON */}
          <div>
            <label className="caption mb-1.5 block">Params JSON (optional)</label>
            <textarea
              value={paramsText}
              onChange={(e) => setParamsText(e.target.value)}
              rows={3}
              placeholder={'{"lookback": 20, "threshold": 0.5, "rebal_freq": "weekly"}'}
              className={textareaCls}
            />
          </div>

          {/* Assumptions JSON */}
          <div>
            <label className="caption mb-1.5 block">Assumptions JSON (optional)</label>
            <textarea
              value={assumptionsText}
              onChange={(e) => setAssumptionsText(e.target.value)}
              rows={3}
              placeholder={'{"transaction_cost_bps": 5, "fill_model": "close", "borrow_rate": 0.005}'}
              className={textareaCls}
            />
          </div>

          {/* Notes */}
          <div>
            <label className="caption mb-1.5 block">Notes (optional)</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="Context, observations, hypothesis changes"
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
              {submitting ? "Logging…" : "Log Run"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
