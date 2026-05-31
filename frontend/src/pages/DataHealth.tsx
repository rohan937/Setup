/**
 * DataHealth — Dataset Snapshot Upload + Basic Data Health (M6)
 *
 * Lists datasets, creates new ones, uploads snapshots via JSON textarea,
 * and displays deterministic health scores + quality issues.
 * No AI, no live market data, no causal claims.
 */

import { useEffect, useState } from "react";
import PageHeader from "@/components/PageHeader";
import type {
  Dataset,
  DatasetSnapshotDetail,
  DataQualityIssue,
} from "@/types";
import {
  createDataset,
  createDatasetSnapshot,
  getDataset,
  getDatasets,
  getProjects,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function healthColor(score: number): string {
  if (score >= 90) return "text-fidelity-high";
  if (score >= 60) return "text-fidelity-medium";
  return "text-fidelity-low";
}

function healthBarColor(score: number): string {
  if (score >= 90) return "bg-fidelity-high";
  if (score >= 60) return "bg-fidelity-medium";
  return "bg-fidelity-low";
}

function severityColor(s: string): string {
  switch (s) {
    case "critical": return "text-fidelity-low border-fidelity-low/30 bg-fidelity-low/10";
    case "high":     return "text-fidelity-low border-fidelity-low/20 bg-fidelity-low/5";
    case "medium":   return "text-fidelity-medium border-fidelity-medium/30 bg-fidelity-medium/10";
    case "low":      return "text-text-muted border-border bg-bg-600";
    default:         return "text-text-muted border-border bg-bg-600";
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const inputCls =
  "w-full rounded-control border border-border bg-bg-600 px-2.5 py-1.5 font-mono text-xs text-text-primary placeholder:text-text-muted focus:border-accent-500 focus:outline-none";

const selectCls =
  "w-full rounded-control border border-border bg-bg-600 px-2.5 py-1.5 font-mono text-xs text-text-primary focus:border-accent-500 focus:outline-none";

const textareaCls =
  "w-full rounded-control border border-border bg-bg-600 px-2.5 py-1.5 font-mono text-2xs text-text-primary placeholder:text-text-muted focus:border-accent-500 focus:outline-none resize-y";

function IssueRow({ issue }: { issue: DataQualityIssue }) {
  return (
    <div className="flex items-start gap-3 border-b border-border/60 px-3 py-2.5 last:border-0">
      <span
        className={`shrink-0 rounded-chip border px-1.5 py-0.5 font-mono text-2xs uppercase tracking-widest ${severityColor(issue.severity)}`}
      >
        {issue.severity}
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-mono text-2xs text-text-secondary">{issue.issue_type}</p>
        {issue.detail && (
          <p className="mt-0.5 font-mono text-2xs text-text-muted">{issue.detail}</p>
        )}
      </div>
      {issue.row_index !== null && (
        <span className="shrink-0 font-mono text-2xs text-text-muted">
          row {issue.row_index}
        </span>
      )}
    </div>
  );
}

function HealthScore({ score }: { score: number }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <span className="caption">Health Score</span>
        <span className={`mono-num text-xl font-bold ${healthColor(score)}`}>
          {score}
          <span className="text-sm font-normal text-text-muted">/100</span>
        </span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-bg-600">
        <div
          className={`h-1.5 rounded-full transition-all ${healthBarColor(score)}`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  );
}

function SnapshotResult({ snap }: { snap: DatasetSnapshotDetail }) {
  const criticalCount = snap.issues.filter((i) => i.severity === "critical").length;
  const highCount = snap.issues.filter((i) => i.severity === "high").length;
  const medCount = snap.issues.filter((i) => i.severity === "medium").length;

  return (
    <div className="space-y-4">
      <div className="rounded-card border border-border bg-bg-700 p-4">
        <HealthScore score={snap.health_score} />
        <div className="mt-3 flex flex-wrap gap-4 font-mono text-2xs text-text-muted">
          <span>
            {snap.row_count} row{snap.row_count !== 1 ? "s" : ""}
          </span>
          <span>version: {snap.version_label}</span>
          {snap.issues.length > 0 && (
            <>
              {criticalCount > 0 && (
                <span className="text-fidelity-low">{criticalCount} critical</span>
              )}
              {highCount > 0 && (
                <span className="text-fidelity-low">{highCount} high</span>
              )}
              {medCount > 0 && (
                <span className="text-fidelity-medium">{medCount} medium</span>
              )}
            </>
          )}
          {snap.issues.length === 0 && (
            <span className="text-fidelity-high">no issues detected</span>
          )}
        </div>
      </div>

      {snap.issues.length > 0 && (
        <div className="rounded-card border border-border bg-bg-700">
          <div className="border-b border-border px-4 py-2.5">
            <p className="caption">
              Quality Issues{" "}
              <span className="text-text-muted">({snap.issues.length})</span>
            </p>
          </div>
          <div>
            {snap.issues.map((iss) => (
              <IssueRow key={iss.id} issue={iss} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create dataset form
// ---------------------------------------------------------------------------

interface CreateDatasetFormProps {
  projectId: string;
  onCreated: (d: Dataset) => void;
}

function CreateDatasetForm({ projectId, onCreated }: CreateDatasetFormProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [datasetType, setDatasetType] = useState("ohlcv");
  const [sourceType, setSourceType] = useState("manual");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const d = await createDataset({
        project_id: projectId,
        name: name.trim(),
        description: description.trim() || undefined,
        dataset_type: datasetType,
        source_type: sourceType,
      });
      setName("");
      setDescription("");
      onCreated(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create dataset.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label className="caption mb-1 block">Dataset Name *</label>
        <input
          className={inputCls}
          placeholder="e.g. AAPL Daily OHLCV 2024"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </div>
      <div>
        <label className="caption mb-1 block">Description</label>
        <input
          className={inputCls}
          placeholder="Optional"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="caption mb-1 block">Type</label>
          <select
            className={selectCls}
            value={datasetType}
            onChange={(e) => setDatasetType(e.target.value)}
          >
            {["ohlcv", "factors", "fundamentals", "returns", "custom"].map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="caption mb-1 block">Source</label>
          <select
            className={selectCls}
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value)}
          >
            {["manual", "vendor", "computed", "sdk"].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      </div>
      {error && (
        <p className="rounded-control border border-fidelity-low/30 bg-fidelity-low/10 px-3 py-2 font-mono text-2xs text-fidelity-low">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={loading || !name.trim()}
        className="rounded-control bg-accent-500 px-3.5 py-1.5 font-mono text-xs font-medium text-text-inverse hover:bg-accent-600 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? "Creating…" : "Create Dataset"}
      </button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Upload snapshot form
// ---------------------------------------------------------------------------

interface UploadSnapshotFormProps {
  datasetId: string;
  onUploaded: (snap: DatasetSnapshotDetail) => void;
}

const EXAMPLE_ROWS = `[
  {"symbol":"AAPL","timestamp":"2024-01-02","open":185.3,"high":188.5,"low":184.9,"close":187.1,"volume":52000000},
  {"symbol":"AAPL","timestamp":"2024-01-03","open":187.2,"high":190.0,"low":186.5,"close":189.4,"volume":48000000}
]`;

function UploadSnapshotForm({ datasetId, onUploaded }: UploadSnapshotFormProps) {
  const [versionLabel, setVersionLabel] = useState("");
  const [rowsText, setRowsText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    let rows: Record<string, unknown>[];
    try {
      const parsed = JSON.parse(rowsText.trim());
      if (!Array.isArray(parsed)) {
        throw new Error("Rows must be a JSON array.");
      }
      rows = parsed as Record<string, unknown>[];
    } catch (parseErr) {
      setError(
        parseErr instanceof Error
          ? parseErr.message
          : "Invalid JSON — enter a JSON array of row objects.",
      );
      return;
    }

    setLoading(true);
    try {
      const snap = await createDatasetSnapshot(datasetId, {
        version_label: versionLabel.trim(),
        rows,
      });
      setVersionLabel("");
      setRowsText("");
      onUploaded(snap);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label className="caption mb-1 block">Version Label *</label>
        <input
          className={inputCls}
          placeholder="e.g. v2024-01"
          value={versionLabel}
          onChange={(e) => setVersionLabel(e.target.value)}
          required
        />
      </div>
      <div>
        <label className="caption mb-1 block">
          Rows · JSON array of row objects
        </label>
        <textarea
          className={textareaCls}
          rows={8}
          placeholder={EXAMPLE_ROWS}
          value={rowsText}
          onChange={(e) => setRowsText(e.target.value)}
          required
        />
      </div>
      {error && (
        <p className="rounded-control border border-fidelity-low/30 bg-fidelity-low/10 px-3 py-2 font-mono text-2xs text-fidelity-low">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={loading || !versionLabel.trim() || !rowsText.trim()}
        className="rounded-control bg-accent-500 px-3.5 py-1.5 font-mono text-xs font-medium text-text-inverse hover:bg-accent-600 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? "Analysing…" : "Upload & Analyse →"}
      </button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DataHealth() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [latestSnap, setLatestSnap] = useState<DatasetSnapshotDetail | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  // Load project ID + datasets on mount.
  useEffect(() => {
    async function init() {
      try {
        const [projects, ds] = await Promise.all([getProjects(), getDatasets()]);
        if (projects.length > 0) setProjectId(projects[0].id);
        setDatasets(ds);
        if (ds.length > 0) setSelectedId(ds[0].id);
      } catch (err) {
        setListError(err instanceof Error ? err.message : "Failed to load.");
      } finally {
        setLoadingList(false);
      }
    }
    void init();
  }, []);

  // Reload dataset list (after create).
  async function refreshList() {
    const ds = await getDatasets();
    setDatasets(ds);
  }

  function handleDatasetCreated(d: Dataset) {
    setDatasets((prev) => [d, ...prev]);
    setSelectedId(d.id);
    setLatestSnap(null);
    setShowCreate(false);
  }

  function handleSnapshotUploaded(snap: DatasetSnapshotDetail) {
    setLatestSnap(snap);
    void refreshList(); // update snapshot_count
  }

  const selectedDataset = datasets.find((d) => d.id === selectedId) ?? null;

  return (
    <>
      <PageHeader
        tag="Analysis"
        title="Data Health"
        subtitle="Upload dataset snapshots and run deterministic data quality checks before a run."
      />

      {loadingList ? (
        <p className="font-mono text-2xs text-text-muted">Loading…</p>
      ) : listError ? (
        <div className="rounded-card border border-fidelity-low/30 bg-fidelity-low/10 px-4 py-3">
          <p className="font-mono text-xs text-fidelity-low">{listError}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[260px_1fr]">
          {/* Left column — dataset list + create */}
          <div className="space-y-4">
            {/* Dataset list */}
            <div className="rounded-card border border-border bg-bg-700">
              <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
                <p className="caption">Datasets</p>
                <button
                  onClick={() => setShowCreate((v) => !v)}
                  className="font-mono text-2xs text-accent-300 hover:text-accent-200"
                >
                  {showCreate ? "cancel" : "+ new"}
                </button>
              </div>

              {showCreate && projectId && (
                <div className="border-b border-border p-4">
                  <CreateDatasetForm
                    projectId={projectId}
                    onCreated={handleDatasetCreated}
                  />
                </div>
              )}

              <div>
                {datasets.length === 0 ? (
                  <p className="px-4 py-3 font-mono text-2xs text-text-muted">
                    No datasets yet. Create one above.
                  </p>
                ) : (
                  <div className="divide-y divide-border">
                    {datasets.map((d) => (
                      <button
                        key={d.id}
                        onClick={() => {
                          setSelectedId(d.id);
                          setLatestSnap(null);
                        }}
                        className={`w-full px-4 py-3 text-left transition-colors hover:bg-bg-600 ${
                          selectedId === d.id
                            ? "border-l-2 border-accent-500 bg-bg-600/50"
                            : "border-l-2 border-transparent"
                        }`}
                      >
                        <p className="text-xs font-medium text-text-primary">
                          {d.name}
                        </p>
                        <p className="mt-0.5 font-mono text-2xs text-text-muted">
                          {d.dataset_type} · {d.snapshot_count} snapshot
                          {d.snapshot_count !== 1 ? "s" : ""}
                        </p>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Right column — selected dataset detail */}
          <div className="space-y-5">
            {selectedDataset ? (
              <>
                {/* Dataset header */}
                <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-text-primary">
                        {selectedDataset.name}
                      </p>
                      {selectedDataset.description && (
                        <p className="mt-0.5 text-xs text-text-secondary">
                          {selectedDataset.description}
                        </p>
                      )}
                    </div>
                    <div className="flex gap-2 font-mono text-2xs text-text-muted">
                      <span className="rounded-chip border border-border px-1.5 py-0.5">
                        {selectedDataset.dataset_type}
                      </span>
                      <span className="rounded-chip border border-border px-1.5 py-0.5">
                        {selectedDataset.source_type}
                      </span>
                    </div>
                  </div>
                  <p className="mt-2 font-mono text-2xs text-text-muted">
                    {selectedDataset.snapshot_count} snapshot
                    {selectedDataset.snapshot_count !== 1 ? "s" : ""} · registered{" "}
                    {fmtDate(selectedDataset.created_at)}
                  </p>
                </div>

                {/* Upload snapshot */}
                <div className="rounded-card border border-border bg-bg-700">
                  <div className="border-b border-border px-4 py-2.5">
                    <p className="caption">Upload Snapshot</p>
                  </div>
                  <div className="p-4">
                    <UploadSnapshotForm
                      datasetId={selectedDataset.id}
                      onUploaded={handleSnapshotUploaded}
                    />
                  </div>
                </div>

                {/* Latest analysis result */}
                {latestSnap && (
                  <div>
                    <p className="caption mb-2">Latest Analysis</p>
                    <SnapshotResult snap={latestSnap} />
                  </div>
                )}

                {/* Previous snapshots */}
                <SnapshotHistory
                  datasetId={selectedDataset.id}
                  key={selectedDataset.id + selectedDataset.snapshot_count}
                />
              </>
            ) : (
              <div className="flex h-40 items-center justify-center rounded-card border border-border bg-bg-700">
                <p className="font-mono text-2xs text-text-muted">
                  {datasets.length === 0
                    ? "Create a dataset to get started."
                    : "Select a dataset to view details."}
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Snapshot history panel (loads from API)
// ---------------------------------------------------------------------------

function SnapshotHistory({ datasetId }: { datasetId: string }) {
  const [detail, setDetail] = useState<
    import("@/types").DatasetDetail | null
  >(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getDataset(datasetId)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [datasetId]);

  if (loading) return null;
  if (!detail || detail.snapshots.length === 0) return null;

  return (
    <div className="rounded-card border border-border bg-bg-700">
      <div className="border-b border-border px-4 py-2.5">
        <p className="caption">
          Snapshot History{" "}
          <span className="text-text-muted">({detail.snapshots.length})</span>
        </p>
      </div>
      <div className="divide-y divide-border">
        {detail.snapshots.map((s) => (
          <div
            key={s.id}
            className="flex items-center justify-between gap-4 px-4 py-3"
          >
            <div>
              <p className="font-mono text-xs font-medium text-text-primary">
                {s.version_label}
              </p>
              <p className="mt-0.5 font-mono text-2xs text-text-muted">
                {s.row_count} rows · {fmtDate(s.created_at)}
              </p>
            </div>
            <span
              className={`mono-num text-sm font-semibold ${healthColor(s.health_score)}`}
            >
              {s.health_score}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
