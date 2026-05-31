/**
 * RunComparisonPanel — deterministic run diff UI (M5)
 *
 * Shows a structured diff of params, assumptions, metrics, and metadata
 * between two selected runs.  No AI, no causal claims — only observed diffs.
 */

import { useEffect, useState } from "react";
import type {
  ComparisonSection,
  FieldChange,
  RunComparisonResponse,
  StrategyRun,
} from "@/types";
import { compareStrategyRuns } from "@/lib/api";

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

function fmtVal(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return String(v);
  if (typeof v === "string") return v;
  if (typeof v === "boolean") return v ? "true" : "false";
  return JSON.stringify(v);
}

function fmtDelta(delta: number): string {
  const prefix = delta >= 0 ? "+" : "";
  const abs = Math.abs(delta);
  if (abs === 0) return "0";
  if (abs >= 100) return `${prefix}${Math.round(delta)}`;
  if (abs >= 1) return `${prefix}${parseFloat(delta.toFixed(2))}`;
  if (abs >= 0.01) return `${prefix}${parseFloat(delta.toFixed(3))}`;
  return `${prefix}${parseFloat(delta.toFixed(4))}`;
}

function fmtPct(pct: number): string {
  const prefix = pct >= 0 ? "+" : "";
  return `${prefix}${parseFloat(pct.toFixed(1))}%`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const selectCls =
  "w-full rounded-control border border-border bg-bg-600 px-2.5 py-1.5 font-mono text-xs text-text-primary focus:border-accent-500 focus:outline-none";

function ChangeBadge({ n }: { n: number }) {
  if (n === 0) {
    return (
      <span className="font-mono text-2xs text-text-muted">no changes</span>
    );
  }
  return (
    <span className="rounded-chip border border-accent-500/30 bg-accent-500/10 px-1.5 py-0.5 font-mono text-2xs text-accent-300">
      {n} change{n !== 1 ? "s" : ""}
    </span>
  );
}

function FieldRow({ fc }: { fc: FieldChange }) {
  const isAdded = fc.change_type === "added";
  const isRemoved = fc.change_type === "removed";

  let deltaText = "changed";
  let deltaColor = "text-fidelity-medium";

  if (isAdded) {
    deltaText = "added";
    deltaColor = "text-fidelity-high";
  } else if (isRemoved) {
    deltaText = "removed";
    deltaColor = "text-fidelity-low";
  } else if (fc.delta !== null) {
    deltaColor = fc.delta > 0 ? "text-fidelity-high" : fc.delta < 0 ? "text-fidelity-low" : "text-text-muted";
    deltaText = fmtDelta(fc.delta);
    if (fc.pct_delta !== null) {
      deltaText += ` (${fmtPct(fc.pct_delta)})`;
    }
  }

  return (
    <div className="grid grid-cols-[2fr_1fr_1fr_1.2fr] gap-x-3 border-b border-border/60 px-3 py-2 last:border-0">
      <span className="font-mono text-xs text-text-secondary">{fc.field}</span>
      <span
        className={`mono-num text-xs ${isAdded ? "text-text-muted italic" : "text-text-muted"}`}
      >
        {isAdded ? "—" : fmtVal(fc.old_value)}
      </span>
      <span
        className={`mono-num text-xs ${isRemoved ? "text-text-muted italic" : "text-text-primary"}`}
      >
        {isRemoved ? "—" : fmtVal(fc.new_value)}
      </span>
      <span className={`font-mono text-xs ${deltaColor}`}>{deltaText}</span>
    </div>
  );
}

function SectionBlock({
  title,
  section,
}: {
  title: string;
  section: ComparisonSection;
}) {
  const allChanges: FieldChange[] = [
    ...section.changed,
    ...section.added,
    ...section.removed,
  ];

  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <p className="caption">{title}</p>
        <ChangeBadge n={section.total_changes} />
      </div>
      {section.total_changes > 0 && (
        <div className="overflow-hidden rounded-control border border-border">
          {/* Column headers */}
          <div className="grid grid-cols-[2fr_1fr_1fr_1.2fr] gap-x-3 border-b border-border bg-bg-600/60 px-3 py-1.5">
            <span className="caption">Field</span>
            <span className="caption">Run A</span>
            <span className="caption">Run B</span>
            <span className="caption">Δ</span>
          </div>
          {allChanges.map((fc) => (
            <FieldRow key={fc.field} fc={fc} />
          ))}
        </div>
      )}
    </div>
  );
}

function ComparisonResult({ result }: { result: RunComparisonResponse }) {
  const hasChanges = result.total_changes > 0;

  return (
    <div className="space-y-5">
      {/* Explanation box */}
      <div className="rounded-control border border-border bg-bg-600 px-4 py-3">
        <p className="caption mb-1.5">Deterministic Analysis</p>
        <p className="text-sm leading-relaxed text-text-secondary">
          {result.deterministic_explanation}
        </p>
      </div>

      {/* Highlighted changes */}
      {result.highlighted_changes.length > 0 && (
        <div>
          <p className="caption mb-2">Key Changes</p>
          <div className="space-y-1.5">
            {result.highlighted_changes.map((ch, i) => (
              <div
                key={i}
                className="flex items-start gap-2 font-mono text-xs text-text-secondary"
              >
                <span className="mt-0.5 shrink-0 text-accent-500">→</span>
                <span>{ch}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sections — only show if there's something to display */}
      {hasChanges && (
        <div className="space-y-5">
          <SectionBlock title="Metrics" section={result.metrics} />
          <SectionBlock title="Params" section={result.params} />
          <SectionBlock title="Assumptions" section={result.assumptions} />
          <SectionBlock title="Metadata" section={result.metadata} />
        </div>
      )}

      {/* Warnings */}
      {result.warnings.length > 0 && (
        <div className="space-y-1">
          {result.warnings.map((w, i) => (
            <p key={i} className="font-mono text-2xs text-fidelity-medium">
              ⚠ {w}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

interface Props {
  strategyId: string;
  /** Runs list — newest-first (as returned by the API). */
  runs: StrategyRun[];
}

export default function RunComparisonPanel({ strategyId, runs }: Props) {
  // Default: Run A = second-newest (baseline), Run B = newest (latest)
  const [runAId, setRunAId] = useState<string>("");
  const [runBId, setRunBId] = useState<string>("");
  const [result, setResult] = useState<RunComparisonResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Initialise / update selectors when the runs list changes
  useEffect(() => {
    if (runs.length >= 2) {
      setRunAId(runs[1].id); // second-newest = baseline
      setRunBId(runs[0].id); // newest = compare
    } else if (runs.length === 1) {
      setRunAId(runs[0].id);
      setRunBId(runs[0].id);
    }
    setResult(null);
  }, [runs]);

  async function handleCompare() {
    if (!runAId || !runBId) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const cmp = await compareStrategyRuns(strategyId, runAId, runBId);
      setResult(cmp);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Comparison failed.");
    } finally {
      setLoading(false);
    }
  }

  // ── Empty state ──────────────────────────────────────────────────────────

  const panel = (
    <div className="rounded-card border border-border bg-bg-700">
      <div className="border-b border-border px-4 py-2.5">
        <p className="caption">Run Comparison</p>
      </div>
      <div className="p-4">
        {runs.length < 2 ? (
          <p className="font-mono text-2xs text-text-muted">
            Log at least two runs to compare strategy behavior.
          </p>
        ) : (
          <div className="space-y-5">
            {/* Run selectors */}
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="caption mb-1.5 block">Run A · baseline</label>
                <select
                  value={runAId}
                  onChange={(e) => {
                    setRunAId(e.target.value);
                    setResult(null);
                  }}
                  className={selectCls}
                >
                  {runs.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.run_name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="shrink-0 pb-2 font-mono text-xs text-text-muted">
                vs
              </div>

              <div className="flex-1">
                <label className="caption mb-1.5 block">Run B · compare</label>
                <select
                  value={runBId}
                  onChange={(e) => {
                    setRunBId(e.target.value);
                    setResult(null);
                  }}
                  className={selectCls}
                >
                  {runs.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.run_name}
                    </option>
                  ))}
                </select>
              </div>

              <button
                onClick={handleCompare}
                disabled={loading || !runAId || !runBId}
                className="shrink-0 rounded-control border border-accent-500/50 bg-accent-500/10 px-3.5 py-1.5 font-mono text-xs text-accent-300 hover:bg-accent-500/20 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? "Comparing…" : "Compare →"}
              </button>
            </div>

            {/* Run date context strip */}
            <div className="flex gap-6 font-mono text-2xs text-text-muted">
              {runAId && (() => {
                const r = runs.find((x) => x.id === runAId);
                return r ? (
                  <span>
                    A: <span className="text-text-secondary">{r.run_name}</span>{" "}
                    · {fmtDate(r.created_at)}
                  </span>
                ) : null;
              })()}
              {runBId && (() => {
                const r = runs.find((x) => x.id === runBId);
                return r ? (
                  <span>
                    B: <span className="text-text-secondary">{r.run_name}</span>{" "}
                    · {fmtDate(r.created_at)}
                  </span>
                ) : null;
              })()}
            </div>

            {/* Error */}
            {error && (
              <p className="rounded-control border border-fidelity-low/30 bg-fidelity-low/10 px-3 py-2 font-mono text-2xs text-fidelity-low">
                {error}
              </p>
            )}

            {/* Result */}
            {result && <ComparisonResult result={result} />}
          </div>
        )}
      </div>
    </div>
  );

  return panel;
}
