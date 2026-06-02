/**
 * DataHealth — Dataset Snapshot Upload + Data Health + Snapshot Comparison (M6/M12)
 *
 * Lists datasets, creates new ones, uploads snapshots via JSON textarea,
 * displays deterministic health scores + quality issues, and compares
 * two snapshots side-by-side (schema, coverage, health, row-level revisions).
 * No AI, no live market data, no causal claims.
 */

import { useEffect, useState } from "react";
import PageHeader from "@/components/PageHeader";
import type {
  Dataset,
  DatasetDetail,
  DatasetSnapshotRead,
  DatasetSnapshotDetail,
  DataQualityIssue,
  DatasetSnapshotComparisonResponse,
  DatasetQualityDrilldownResponse,
  ColumnQuality,
  RowQualitySample,
} from "@/types";
import {
  compareDatasetSnapshots,
  createDataset,
  createDatasetSnapshot,
  getDataset,
  getDatasets,
  getDatasetSnapshotQualityDrilldown,
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

function deltaColor(delta: number): string {
  if (delta > 0) return "text-fidelity-high";
  if (delta < 0) return "text-fidelity-low";
  return "text-text-muted";
}

function fmtDelta(delta: number, prefix = ""): string {
  if (delta > 0) return `${prefix}+${delta}`;
  if (delta < 0) return `${prefix}${delta}`;
  return `${prefix}0`;
}

// ---------------------------------------------------------------------------
// Style constants
// ---------------------------------------------------------------------------

const inputCls =
  "w-full rounded-control border border-border bg-bg-600 px-2.5 py-1.5 font-mono text-xs text-text-primary placeholder:text-text-muted focus:border-accent-500 focus:outline-none";

const selectCls =
  "w-full rounded-control border border-border bg-bg-600 px-2.5 py-1.5 font-mono text-xs text-text-primary focus:border-accent-500 focus:outline-none";

const textareaCls =
  "w-full rounded-control border border-border bg-bg-600 px-2.5 py-1.5 font-mono text-2xs text-text-primary placeholder:text-text-muted focus:border-accent-500 focus:outline-none resize-y";

// ---------------------------------------------------------------------------
// Sub-components (shared)
// ---------------------------------------------------------------------------

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
// Comparison result display
// ---------------------------------------------------------------------------

function SectionCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-card border border-border bg-bg-700">
      <div className="border-b border-border px-4 py-2.5">
        <p className="caption">{title}</p>
      </div>
      <div className="px-4 py-3">{children}</div>
    </div>
  );
}

function CompareRow({
  label,
  a,
  b,
  delta,
}: {
  label: string;
  a: React.ReactNode;
  b: React.ReactNode;
  delta?: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2 border-b border-border/50 py-1.5 last:border-0">
      <span className="w-32 shrink-0 font-mono text-2xs text-text-muted">{label}</span>
      <span className="w-24 font-mono text-2xs text-text-secondary">{a}</span>
      <span className="w-24 font-mono text-2xs text-text-secondary">{b}</span>
      {delta !== undefined && (
        <span className="font-mono text-2xs">{delta}</span>
      )}
    </div>
  );
}

function PillList({
  items,
  color,
  cap = 10,
}: {
  items: string[];
  color: string;
  cap?: number;
}) {
  if (items.length === 0) return <span className="font-mono text-2xs text-text-muted">—</span>;
  const shown = items.slice(0, cap);
  const rest = items.length - shown.length;
  return (
    <div className="flex flex-wrap gap-1">
      {shown.map((item) => (
        <span
          key={item}
          className={`rounded-chip border px-1.5 py-0.5 font-mono text-2xs ${color}`}
        >
          {item}
        </span>
      ))}
      {rest > 0 && (
        <span className="font-mono text-2xs text-text-muted">+{rest} more</span>
      )}
    </div>
  );
}

function CompareResultView({
  result,
}: {
  result: DatasetSnapshotComparisonResponse;
}) {
  const { metadata, schema_diff, symbol_coverage, timestamp_coverage, data_health, value_revisions } = result;

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-xs text-text-primary">{result.summary}</p>
        <p className="mt-0.5 font-mono text-2xs text-text-muted">
          Comparing{" "}
          <span className="text-text-secondary">{result.snapshot_a_label}</span>
          {" → "}
          <span className="text-text-secondary">{result.snapshot_b_label}</span>
          {result.is_same_snapshot && (
            <span className="ml-2 rounded-chip border border-border px-1.5 py-0.5 text-text-muted">
              same snapshot
            </span>
          )}
        </p>
      </div>

      {/* Warnings */}
      {result.warnings.length > 0 && (
        <div className="space-y-1.5">
          {result.warnings.map((w, i) => (
            <div
              key={i}
              className="flex gap-2 rounded-control border border-fidelity-medium/30 bg-fidelity-medium/5 px-3 py-2"
            >
              <span className="shrink-0 font-mono text-2xs text-fidelity-medium">⚠</span>
              <p className="font-mono text-2xs text-fidelity-medium">{w}</p>
            </div>
          ))}
        </div>
      )}

      {/* Highlighted changes */}
      {result.highlighted_changes.length > 0 && (
        <SectionCard title="Notable Changes">
          <ul className="space-y-1">
            {result.highlighted_changes.map((c, i) => (
              <li key={i} className="flex gap-2">
                <span className="shrink-0 font-mono text-2xs text-accent-300">•</span>
                <span className="font-mono text-2xs text-text-secondary">{c}</span>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      {/* Deterministic explanation */}
      {result.deterministic_explanation && (
        <SectionCard title="Deterministic Explanation">
          <p className="font-mono text-2xs leading-relaxed text-text-secondary">
            {result.deterministic_explanation}
          </p>
        </SectionCard>
      )}

      {/* Column headers for compare rows */}
      <div className="flex items-center gap-2 px-1">
        <span className="w-32 shrink-0" />
        <span className="w-24 caption text-text-muted">{result.snapshot_a_label}</span>
        <span className="w-24 caption text-text-muted">{result.snapshot_b_label}</span>
        <span className="caption text-text-muted">Δ</span>
      </div>

      {/* Metadata */}
      <SectionCard title="Metadata">
        <CompareRow
          label="Rows"
          a={metadata.row_count_a.toLocaleString()}
          b={metadata.row_count_b.toLocaleString()}
          delta={
            <span className={deltaColor(metadata.row_count_delta)}>
              {fmtDelta(metadata.row_count_delta)}
            </span>
          }
        />
      </SectionCard>

      {/* Schema */}
      <SectionCard title="Schema">
        <CompareRow
          label="Columns"
          a={schema_diff.columns_a.length}
          b={schema_diff.columns_b.length}
          delta={
            <span className={deltaColor(schema_diff.columns_b.length - schema_diff.columns_a.length)}>
              {fmtDelta(schema_diff.columns_b.length - schema_diff.columns_a.length)}
            </span>
          }
        />
        <CompareRow label="Unchanged" a={schema_diff.unchanged_columns_count} b={schema_diff.unchanged_columns_count} />
        {schema_diff.added_columns.length > 0 && (
          <div className="mt-2 space-y-1">
            <p className="font-mono text-2xs text-text-muted">Added columns</p>
            <PillList
              items={schema_diff.added_columns}
              color="text-fidelity-high border-fidelity-high/30 bg-fidelity-high/10"
            />
          </div>
        )}
        {schema_diff.removed_columns.length > 0 && (
          <div className="mt-2 space-y-1">
            <p className="font-mono text-2xs text-text-muted">Removed columns</p>
            <PillList
              items={schema_diff.removed_columns}
              color="text-fidelity-low border-fidelity-low/30 bg-fidelity-low/10"
            />
          </div>
        )}
        {schema_diff.type_changes.length > 0 && (
          <div className="mt-2 space-y-1">
            <p className="font-mono text-2xs text-text-muted">Type changes</p>
            {schema_diff.type_changes.map((tc) => (
              <div key={tc.column} className="flex items-center gap-2 font-mono text-2xs">
                <span className="text-text-secondary">{tc.column}</span>
                <span className="text-text-muted">{tc.type_a}</span>
                <span className="text-text-muted">→</span>
                <span className="text-fidelity-medium">{tc.type_b}</span>
              </div>
            ))}
          </div>
        )}
        {schema_diff.total_changes === 0 && (
          <p className="mt-1 font-mono text-2xs text-text-muted">No schema changes.</p>
        )}
      </SectionCard>

      {/* Symbol Coverage */}
      <SectionCard title="Symbol Coverage">
        {symbol_coverage.keyed_by_symbol ? (
          <>
            <CompareRow
              label="Symbols"
              a={symbol_coverage.symbol_count_a}
              b={symbol_coverage.symbol_count_b}
              delta={
                <span className={deltaColor(symbol_coverage.symbol_count_delta)}>
                  {fmtDelta(symbol_coverage.symbol_count_delta)}
                </span>
              }
            />
            <CompareRow label="Common" a={symbol_coverage.common_symbols_count} b={symbol_coverage.common_symbols_count} />
            {symbol_coverage.added_symbols.length > 0 && (
              <div className="mt-2 space-y-1">
                <p className="font-mono text-2xs text-text-muted">Added symbols</p>
                <PillList
                  items={symbol_coverage.added_symbols}
                  color="text-fidelity-high border-fidelity-high/30 bg-fidelity-high/10"
                />
              </div>
            )}
            {symbol_coverage.removed_symbols.length > 0 && (
              <div className="mt-2 space-y-1">
                <p className="font-mono text-2xs text-text-muted">Removed symbols</p>
                <PillList
                  items={symbol_coverage.removed_symbols}
                  color="text-fidelity-low border-fidelity-low/30 bg-fidelity-low/10"
                />
              </div>
            )}
            {symbol_coverage.symbol_count_delta === 0 &&
              symbol_coverage.added_symbols.length === 0 &&
              symbol_coverage.removed_symbols.length === 0 && (
                <p className="mt-1 font-mono text-2xs text-text-muted">No symbol changes.</p>
              )}
          </>
        ) : (
          <p className="font-mono text-2xs text-text-muted">
            No 'symbol' column detected — symbol comparison not available.
          </p>
        )}
      </SectionCard>

      {/* Timestamp Coverage */}
      <SectionCard title="Timestamp Coverage">
        <CompareRow
          label="Min date"
          a={timestamp_coverage.min_timestamp_a ?? "—"}
          b={timestamp_coverage.min_timestamp_b ?? "—"}
          delta={
            timestamp_coverage.min_changed ? (
              <span className="text-fidelity-medium">changed</span>
            ) : (
              <span className="text-text-muted">—</span>
            )
          }
        />
        <CompareRow
          label="Max date"
          a={timestamp_coverage.max_timestamp_a ?? "—"}
          b={timestamp_coverage.max_timestamp_b ?? "—"}
          delta={
            timestamp_coverage.max_changed ? (
              <span className="text-fidelity-medium">changed</span>
            ) : (
              <span className="text-text-muted">—</span>
            )
          }
        />
        <CompareRow
          label="Range (days)"
          a={timestamp_coverage.date_range_days_a ?? "—"}
          b={timestamp_coverage.date_range_days_b ?? "—"}
          delta={
            timestamp_coverage.date_range_days_delta != null ? (
              <span className={deltaColor(timestamp_coverage.date_range_days_delta)}>
                {fmtDelta(timestamp_coverage.date_range_days_delta, "")} days
              </span>
            ) : (
              <span className="text-text-muted">—</span>
            )
          }
        />
      </SectionCard>

      {/* Data Health */}
      <SectionCard title="Data Health">
        <CompareRow
          label="Health score"
          a={<span className={healthColor(data_health.health_score_a)}>{data_health.health_score_a}/100</span>}
          b={<span className={healthColor(data_health.health_score_b)}>{data_health.health_score_b}/100</span>}
          delta={
            <span className={deltaColor(data_health.health_score_delta)}>
              {fmtDelta(data_health.health_score_delta)}
            </span>
          }
        />
        <CompareRow
          label="Issues"
          a={data_health.issue_count_a}
          b={data_health.issue_count_b}
          delta={
            <span className={deltaColor(-data_health.issue_count_delta)}>
              {fmtDelta(data_health.issue_count_delta)}
            </span>
          }
        />
        <CompareRow
          label="Worst severity"
          a={data_health.worst_severity_a ?? "none"}
          b={data_health.worst_severity_b ?? "none"}
        />
        {data_health.issue_types_added.length > 0 && (
          <div className="mt-2 space-y-1">
            <p className="font-mono text-2xs text-text-muted">New issue types</p>
            <PillList
              items={data_health.issue_types_added}
              color="text-fidelity-low border-fidelity-low/30 bg-fidelity-low/10"
            />
          </div>
        )}
        {data_health.issue_types_removed.length > 0 && (
          <div className="mt-2 space-y-1">
            <p className="font-mono text-2xs text-text-muted">Resolved issue types</p>
            <PillList
              items={data_health.issue_types_removed}
              color="text-fidelity-high border-fidelity-high/30 bg-fidelity-high/10"
            />
          </div>
        )}
      </SectionCard>

      {/* Value Revisions */}
      <SectionCard title="Value Revisions">
        {value_revisions.keyed_comparison_available ? (
          <>
            <div className="mb-3 flex flex-wrap gap-4 font-mono text-2xs">
              <span>
                <span className="text-fidelity-high">+{value_revisions.added_rows_count}</span>{" "}
                <span className="text-text-muted">added</span>
              </span>
              <span>
                <span className="text-fidelity-low">−{value_revisions.removed_rows_count}</span>{" "}
                <span className="text-text-muted">removed</span>
              </span>
              <span>
                <span className="text-fidelity-medium">~{value_revisions.changed_rows_count}</span>{" "}
                <span className="text-text-muted">revised</span>
              </span>
            </div>

            {value_revisions.examples.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-left font-mono text-2xs">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="pb-1.5 pr-3 text-text-muted font-normal">Symbol</th>
                      <th className="pb-1.5 pr-3 text-text-muted font-normal">Timestamp</th>
                      <th className="pb-1.5 pr-3 text-text-muted font-normal">Type</th>
                      <th className="pb-1.5 pr-3 text-text-muted font-normal">Changed Fields</th>
                      <th className="pb-1.5 text-text-muted font-normal">Deltas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {value_revisions.examples.map((ex, i) => (
                      <tr key={i} className="border-b border-border/40 last:border-0">
                        <td className="py-1.5 pr-3 text-text-secondary">{ex.symbol ?? "—"}</td>
                        <td className="py-1.5 pr-3 text-text-secondary">{ex.timestamp ?? "—"}</td>
                        <td className="py-1.5 pr-3">
                          <span
                            className={
                              ex.change_type === "added"
                                ? "text-fidelity-high"
                                : ex.change_type === "removed"
                                ? "text-fidelity-low"
                                : "text-fidelity-medium"
                            }
                          >
                            {ex.change_type}
                          </span>
                        </td>
                        <td className="py-1.5 pr-3 text-text-muted">
                          {ex.changed_fields.length > 0
                            ? ex.changed_fields.join(", ")
                            : "—"}
                        </td>
                        <td className="py-1.5 text-text-muted">
                          {Object.keys(ex.field_deltas).length > 0
                            ? Object.entries(ex.field_deltas)
                                .map(([f, d]) => `${f}: ${d > 0 ? "+" : ""}${d.toFixed(4)}`)
                                .join("; ")
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {value_revisions.total_examples_capped && (
                  <p className="mt-2 font-mono text-2xs text-text-muted">
                    Showing first {value_revisions.max_examples} examples.
                  </p>
                )}
              </div>
            )}

            {value_revisions.added_rows_count === 0 &&
              value_revisions.removed_rows_count === 0 &&
              value_revisions.changed_rows_count === 0 && (
                <p className="font-mono text-2xs text-text-muted">
                  No row-level differences detected.
                </p>
              )}
          </>
        ) : (
          <p className="font-mono text-2xs text-text-muted">
            {!value_revisions.rows_available_a && !value_revisions.rows_available_b
              ? "Row data not available for either snapshot."
              : "Rows could not be keyed by (symbol, timestamp) — hash-based comparison only."}
          </p>
        )}
      </SectionCard>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Compare panel (selector + trigger + result)
// ---------------------------------------------------------------------------

interface ComparePanelProps {
  datasetId: string;
  snapshots: DatasetSnapshotRead[];
}

function ComparePanel({ datasetId, snapshots }: ComparePanelProps) {
  // Default: A = second-newest (index 1), B = newest (index 0)
  // snapshots are ordered newest-first from the API.
  const [snapAId, setSnapAId] = useState<string>(
    snapshots.length >= 2 ? snapshots[1].id : snapshots[0].id,
  );
  const [snapBId, setSnapBId] = useState<string>(snapshots[0].id);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DatasetSnapshotComparisonResponse | null>(null);

  async function handleCompare() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await compareDatasetSnapshots(datasetId, snapAId, snapBId);
      setResult(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Comparison failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-card border border-border bg-bg-700">
        <div className="border-b border-border px-4 py-2.5">
          <p className="caption">Compare Snapshots</p>
        </div>
        <div className="p-4">
          <div className="grid grid-cols-[1fr_auto_1fr_auto] items-end gap-3">
            <div>
              <label className="caption mb-1 block">Snapshot A (baseline)</label>
              <select
                className={selectCls}
                value={snapAId}
                onChange={(e) => {
                  setSnapAId(e.target.value);
                  setResult(null);
                  setError(null);
                }}
              >
                {snapshots.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.version_label} · {s.row_count} rows
                  </option>
                ))}
              </select>
            </div>
            <div className="mb-1.5 font-mono text-xs text-text-muted">→</div>
            <div>
              <label className="caption mb-1 block">Snapshot B (target)</label>
              <select
                className={selectCls}
                value={snapBId}
                onChange={(e) => {
                  setSnapBId(e.target.value);
                  setResult(null);
                  setError(null);
                }}
              >
                {snapshots.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.version_label} · {s.row_count} rows
                  </option>
                ))}
              </select>
            </div>
            <button
              onClick={() => void handleCompare()}
              disabled={loading}
              className="mb-0 rounded-control bg-accent-500 px-3.5 py-1.5 font-mono text-xs font-medium text-text-inverse hover:bg-accent-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Comparing…" : "Compare →"}
            </button>
          </div>
          {error && (
            <p className="mt-3 rounded-control border border-fidelity-low/30 bg-fidelity-low/10 px-3 py-2 font-mono text-2xs text-fidelity-low">
              {error}
            </p>
          )}
        </div>
      </div>

      {result && <CompareResultView result={result} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Combined dataset sections: snapshot history + compare panel
// ---------------------------------------------------------------------------

interface DatasetSectionsProps {
  datasetId: string;
  onInspect: (snapshotId: string) => void;
  selectedSnapshotId: string | null;
  drilldownLoading: boolean;
}

function DatasetSections({
  datasetId,
  onInspect,
  selectedSnapshotId,
  drilldownLoading,
}: DatasetSectionsProps) {
  const [detail, setDetail] = useState<DatasetDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getDataset(datasetId)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [datasetId]);

  if (loading) return null;
  if (!detail) return null;

  const snapshots = detail.snapshots; // newest-first from API

  return (
    <div className="space-y-5">
      {/* Snapshot history */}
      {snapshots.length > 0 && (
        <div className="rounded-card border border-border bg-bg-700">
          <div className="border-b border-border px-4 py-2.5">
            <p className="caption">
              Snapshot History{" "}
              <span className="text-text-muted">({snapshots.length})</span>
            </p>
          </div>
          <div className="divide-y divide-border">
            {snapshots.map((s) => (
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
                <div className="flex items-center gap-3">
                  <span
                    className={`mono-num text-sm font-semibold ${healthColor(s.health_score)}`}
                  >
                    {s.health_score}
                  </span>
                  <button
                    onClick={() => onInspect(s.id)}
                    disabled={drilldownLoading && selectedSnapshotId === s.id}
                    className={`rounded-control border px-2 py-1 font-mono text-2xs transition-colors hover:border-accent-500 hover:text-accent-300 disabled:cursor-not-allowed disabled:opacity-50 ${
                      selectedSnapshotId === s.id
                        ? "border-accent-500 text-accent-300"
                        : "border-border text-text-muted"
                    }`}
                  >
                    {drilldownLoading && selectedSnapshotId === s.id
                      ? "Loading…"
                      : "Inspect Quality"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Compare panel — only when ≥2 snapshots */}
      {snapshots.length >= 2 ? (
        <ComparePanel datasetId={datasetId} snapshots={snapshots} />
      ) : (
        <div className="rounded-card border border-border bg-bg-700 px-4 py-5">
          <p className="font-mono text-2xs text-text-muted">
            Upload at least two snapshots to compare dataset drift.
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// M37: Quality Drill-Down Panel
// ---------------------------------------------------------------------------

function drilldownScoreColor(score: number): string {
  if (score >= 80) return "text-teal-400";
  if (score >= 60) return "text-yellow-400";
  if (score >= 40) return "text-orange-400";
  return "text-red-400";
}

function columnStatusColor(status: string): string {
  switch (status) {
    case "clean":    return "text-teal-400";
    case "review":   return "text-yellow-400";
    case "weak":     return "text-orange-400";
    case "unusable": return "text-red-400";
    default:         return "text-text-muted";
  }
}

function rowSeverityDot(severity: string): string {
  switch (severity) {
    case "high":   return "bg-red-400";
    case "medium": return "bg-yellow-400";
    default:       return "bg-text-muted";
  }
}

const ROW_QUALITY_LABELS: Record<string, string> = {
  duplicate_rows: "Duplicate Rows",
  duplicate_symbol_timestamp: "Duplicate Symbol/Timestamp",
  invalid_timestamp_rows: "Invalid Timestamp Rows",
  invalid_ohlc_rows: "Invalid OHLC Rows",
  suspicious_return_rows: "Suspicious Return Rows",
  missing_value_rows: "Missing Value Rows",
  outlier_rows: "Outlier Rows",
};

function QualityDrilldownPanel({
  drilldown,
}: {
  drilldown: DatasetQualityDrilldownResponse;
}) {
  const s = drilldown.quality_summary;

  const rowQualityEntries = (
    Object.entries(drilldown.row_quality) as [string, RowQualitySample[]][]
  ).filter(([, samples]) => samples.length > 0);

  return (
    <div className="space-y-4">
      {/* Card header */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="font-mono text-xs font-semibold text-text-primary">
              Quality Drill-Down:{" "}
              <span className="text-accent-300">{drilldown.snapshot_label}</span>
            </p>
            <p className="mt-0.5 font-mono text-2xs text-text-muted">
              generated {fmtDate(drilldown.generated_at)}
            </p>
          </div>
          <span
            className={`mono-num text-xl font-bold ${drilldownScoreColor(drilldown.health_score)}`}
          >
            {drilldown.health_score}
            <span className="text-sm font-normal text-text-muted">/100</span>
          </span>
        </div>

        {/* Summary strip */}
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-2xs">
          <span className="text-text-muted">
            <span className="text-text-secondary">{s.total_rows.toLocaleString()}</span> rows
          </span>
          <span className="text-text-muted">
            <span className="text-text-secondary">{s.total_columns}</span> columns
          </span>
          <span>
            <span className="text-teal-400">{s.clean_column_count} clean</span>
            {" · "}
            <span className="text-yellow-400">{s.review_column_count} review</span>
            {" · "}
            <span className="text-orange-400">{s.weak_column_count} weak</span>
            {" · "}
            <span className="text-red-400">{s.unusable_column_count} unusable</span>
          </span>
          {s.total_missing_values > 0 && (
            <span className="text-text-muted">
              <span className="text-fidelity-medium">{s.total_missing_values}</span> missing
            </span>
          )}
          {s.total_outliers > 0 && (
            <span className="text-text-muted">
              <span className="text-fidelity-medium">{s.total_outliers}</span> outliers
            </span>
          )}
          {s.total_duplicate_rows > 0 && (
            <span className="text-text-muted">
              <span className="text-fidelity-low">{s.total_duplicate_rows}</span> dup rows
            </span>
          )}
        </div>

        {/* Suggested checks */}
        {s.suggested_checks.length > 0 && (
          <div className="mt-3 rounded-control border border-border bg-bg-600 px-3 py-2">
            <p className="mb-1 font-mono text-2xs text-text-muted">Suggested checks</p>
            <ul className="space-y-0.5">
              {s.suggested_checks.map((c, i) => (
                <li key={i} className="flex gap-2 font-mono text-2xs text-text-secondary">
                  <span className="shrink-0 text-accent-300">•</span>
                  {c}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Warnings */}
        {drilldown.warnings.length > 0 && (
          <div className="mt-3 space-y-1.5">
            {drilldown.warnings.map((w, i) => (
              <div
                key={i}
                className="flex gap-2 rounded-control border border-fidelity-medium/30 bg-fidelity-medium/5 px-3 py-2"
              >
                <span className="shrink-0 font-mono text-2xs text-fidelity-medium">!</span>
                <p className="font-mono text-2xs text-fidelity-medium">{w}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Column Quality table */}
      {drilldown.column_quality.length > 0 && (
        <div className="rounded-card border border-border bg-bg-700">
          <div className="border-b border-border px-4 py-2.5">
            <p className="caption">
              Column Quality{" "}
              <span className="text-text-muted">({drilldown.column_quality.length})</span>
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-2xs">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-4 pb-1.5 pt-2.5 text-text-muted font-normal">Column</th>
                  <th className="px-3 pb-1.5 pt-2.5 text-text-muted font-normal">Type</th>
                  <th className="px-3 pb-1.5 pt-2.5 text-right text-text-muted font-normal">Null%</th>
                  <th className="px-3 pb-1.5 pt-2.5 text-right text-text-muted font-normal">Unique</th>
                  <th className="px-3 pb-1.5 pt-2.5 text-right text-text-muted font-normal">Outliers</th>
                  <th className="px-3 pb-1.5 pt-2.5 text-text-muted font-normal">Status</th>
                  <th className="px-4 pb-1.5 pt-2.5 text-text-muted font-normal">Issues</th>
                </tr>
              </thead>
              <tbody>
                {drilldown.column_quality.map((col: ColumnQuality) => (
                  <tr
                    key={col.column_name}
                    className="border-b border-border/40 last:border-0 hover:bg-bg-600/30"
                  >
                    <td className="px-4 py-1.5 text-text-primary">{col.column_name}</td>
                    <td className="px-3 py-1.5 text-text-muted">{col.inferred_type}</td>
                    <td className="px-3 py-1.5 text-right text-text-secondary">
                      {(col.null_rate * 100).toFixed(1)}%
                    </td>
                    <td className="px-3 py-1.5 text-right text-text-secondary">
                      {col.unique_count.toLocaleString()}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      <span className={col.outlier_count > 0 ? "text-fidelity-medium" : "text-text-muted"}>
                        {col.outlier_count}
                      </span>
                    </td>
                    <td className="px-3 py-1.5">
                      <span className={`font-medium ${columnStatusColor(col.quality_status)}`}>
                        {col.quality_status}
                      </span>
                    </td>
                    <td className="px-4 py-1.5">
                      {col.issues.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {col.issues.map((iss, i) => (
                            <span
                              key={i}
                              className="rounded-chip border border-border bg-bg-600 px-1.5 py-0.5 text-text-muted"
                            >
                              {iss}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-text-muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Row Evidence */}
      {rowQualityEntries.length > 0 && (
        <div className="rounded-card border border-border bg-bg-700">
          <div className="border-b border-border px-4 py-2.5">
            <p className="caption">Row Evidence</p>
          </div>
          <div className="divide-y divide-border">
            {rowQualityEntries.map(([key, samples]) => (
              <div key={key} className="px-4 py-3">
                <div className="mb-2 flex items-center gap-2">
                  <p className="font-mono text-xs font-medium text-text-primary">
                    {ROW_QUALITY_LABELS[key] ?? key}
                  </p>
                  <span className="rounded-chip border border-border bg-bg-600 px-1.5 py-0.5 font-mono text-2xs text-text-muted">
                    {samples.length}
                  </span>
                </div>
                <div className="space-y-1.5">
                  {samples.slice(0, 5).map((sample: RowQualitySample, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span
                        className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${rowSeverityDot(sample.severity)}`}
                      />
                      <p className="font-mono text-2xs text-text-secondary">
                        Row {sample.row_index}: {sample.summary}
                      </p>
                    </div>
                  ))}
                  {samples.length > 5 && (
                    <p className="font-mono text-2xs text-text-muted">
                      +{samples.length - 5} more
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
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
  // sectionsKey forces DatasetSections to remount after a snapshot upload
  const [sectionsKey, setSectionsKey] = useState(0);
  // M37: quality drilldown
  const [drilldown, setDrilldown] = useState<DatasetQualityDrilldownResponse | null>(null);
  const [drilldownLoading, setDrilldownLoading] = useState(false);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string | null>(null);

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

  async function loadDrilldown(snapshotId: string) {
    setDrilldownLoading(true);
    setSelectedSnapshotId(snapshotId);
    setDrilldown(null);
    try {
      const result = await getDatasetSnapshotQualityDrilldown(snapshotId);
      setDrilldown(result);
    } catch {
      // silently clear on error — user can retry
      setDrilldown(null);
    } finally {
      setDrilldownLoading(false);
    }
  }

  function handleDatasetCreated(d: Dataset) {
    setDatasets((prev) => [d, ...prev]);
    setSelectedId(d.id);
    setLatestSnap(null);
    setDrilldown(null);
    setSelectedSnapshotId(null);
    setShowCreate(false);
    setSectionsKey((k) => k + 1);
  }

  function handleSnapshotUploaded(snap: DatasetSnapshotDetail) {
    setLatestSnap(snap);
    setSectionsKey((k) => k + 1); // reload snapshot history + compare panel
    void refreshList(); // update snapshot_count in sidebar
  }

  const selectedDataset = datasets.find((d) => d.id === selectedId) ?? null;

  return (
    <>
      <PageHeader
        tag="Analysis"
        title="Data Health"
        subtitle="Upload dataset snapshots, run deterministic data quality checks, and compare versions for drift."
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
                          setDrilldown(null);
                          setSelectedSnapshotId(null);
                          setSectionsKey((k) => k + 1);
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

                {/* Snapshot history + compare panel */}
                <DatasetSections
                  key={`${selectedDataset.id}-${sectionsKey}`}
                  datasetId={selectedDataset.id}
                  onInspect={(snapshotId) => void loadDrilldown(snapshotId)}
                  selectedSnapshotId={selectedSnapshotId}
                  drilldownLoading={drilldownLoading}
                />

                {/* M37: Quality drill-down panel */}
                {drilldown && <QualityDrilldownPanel drilldown={drilldown} />}
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
