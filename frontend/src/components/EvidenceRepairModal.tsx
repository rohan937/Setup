import { useEffect, useMemo, useState } from "react";
import type {
  RepairOptionItem,
  RepairOptionsResponse,
  RunLinkUpdateRequest,
} from "@/types";
import { getStrategyRepairOptions, linkRunEvidence } from "@/lib/api";

const selectCls =
  "w-full rounded-control border border-border bg-bg-600 px-3 py-2 text-sm text-text-primary focus:border-accent-500 focus:outline-none";

type LinkKey = "dataset" | "signal" | "universe" | "version";

const LINK_META: Record<
  LinkKey,
  { label: string; field: keyof RunLinkUpdateRequest; optionsKey: keyof RepairOptionsResponse; emptyHint: string }
> = {
  dataset: {
    label: "Dataset snapshot",
    field: "dataset_snapshot_id",
    optionsKey: "dataset_snapshots",
    emptyHint:
      "No compatible dataset snapshots found. Upload an evidence bundle or create a dataset snapshot first.",
  },
  signal: {
    label: "Signal snapshot",
    field: "signal_snapshot_id",
    optionsKey: "signal_snapshots",
    emptyHint:
      "No compatible signal snapshots found. Upload a bundle or create a signal snapshot first.",
  },
  universe: {
    label: "Universe snapshot",
    field: "universe_snapshot_id",
    optionsKey: "universe_snapshots",
    emptyHint:
      "No compatible universe snapshots found. Upload a bundle or create a universe snapshot first.",
  },
  version: {
    label: "Strategy version",
    field: "strategy_version_id",
    optionsKey: "strategy_versions",
    emptyHint: "No strategy versions found. Create a version first.",
  },
};

interface Props {
  open: boolean;
  strategyId: string;
  runId: string | null;
  onClose: () => void;
  onLinked: () => void;
}

export default function EvidenceRepairModal({
  open,
  strategyId,
  runId,
  onClose,
  onLinked,
}: Props) {
  const [options, setOptions] = useState<RepairOptionsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<LinkKey, string>>({
    dataset: "",
    signal: "",
    universe: "",
    version: "",
  });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open || !runId) return;
    setLoading(true);
    setError(null);
    setSelected({ dataset: "", signal: "", universe: "", version: "" });
    getStrategyRepairOptions(strategyId)
      .then((o) => {
        setOptions(o);
        setLoading(false);
      })
      .catch(() => {
        setError("Could not load evidence options.");
        setLoading(false);
      });
  }, [open, runId, strategyId]);

  const run = useMemo(
    () => options?.runs_missing_links.find((r) => r.run_id === runId) ?? null,
    [options, runId],
  );

  // Which link types are missing on this run (fall back to all four if the run
  // is no longer in the missing list but the caller still opened the modal).
  const missingKeys: LinkKey[] = useMemo(() => {
    if (!run) return [];
    return run.missing as LinkKey[];
  }, [run]);

  if (!open || !runId) return null;

  function optionLabel(opt: RepairOptionItem): string {
    const bits = [opt.label];
    if (opt.detail) bits.push(opt.detail);
    if (opt.recommended) bits.push("· recommended");
    return bits.join("  ");
  }

  async function handleSubmit() {
    const payload: RunLinkUpdateRequest = {};
    (Object.keys(LINK_META) as LinkKey[]).forEach((k) => {
      if (selected[k]) payload[LINK_META[k].field] = selected[k];
    });
    if (Object.keys(payload).length === 0) {
      setError("Select at least one evidence object to link.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await linkRunEvidence(strategyId, runId!, payload);
      setSubmitting(false);
      onLinked();
      onClose();
    } catch (e) {
      setSubmitting(false);
      setError(e instanceof Error ? e.message : "Failed to link evidence.");
    }
  }

  const hasSelection = Object.values(selected).some((v) => v);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-bg-950/85" aria-hidden="true" onClick={onClose} />

      <div
        role="dialog"
        aria-modal="true"
        className="relative w-full max-w-lg rounded-card border border-border bg-bg-800 shadow-panel"
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-border px-5 py-3.5">
          <div>
            <p className="caption">Repair evidence</p>
            <p className="mt-0.5 text-sm font-medium text-text-primary">
              Link evidence to this run
            </p>
            {run && (
              <p className="mt-0.5 text-2xs text-text-muted">
                {run.run_name} · {run.run_type}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-control p-1.5 text-text-muted hover:bg-bg-600 hover:text-text-primary"
            aria-label="Close"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M11 3L3 11M3 3l8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex max-h-[60vh] flex-col gap-4 overflow-y-auto px-5 py-5">
          <p className="text-xs leading-relaxed text-text-secondary">
            Linking evidence lets QuantFidelity verify data quality and compare drift
            correctly across runs.
          </p>

          {loading && (
            <p className="text-sm text-text-muted animate-pulse">Loading evidence options…</p>
          )}

          {!loading && run === null && (
            <p className="text-sm text-fidelity-high">
              This run has no missing evidence links.
            </p>
          )}

          {!loading && run && missingKeys.length === 0 && (
            <p className="text-sm text-fidelity-high">
              This run is fully linked.
            </p>
          )}

          {!loading &&
            run &&
            missingKeys.map((key) => {
              const meta = LINK_META[key];
              const opts = (options?.[meta.optionsKey] ?? []) as RepairOptionItem[];
              return (
                <div key={key}>
                  <label className="caption mb-1.5 block">
                    {meta.label}{" "}
                    <span className="text-fidelity-medium">· not linked</span>
                  </label>
                  {opts.length === 0 ? (
                    <p className="text-2xs text-text-muted">{meta.emptyHint}</p>
                  ) : (
                    <select
                      value={selected[key]}
                      onChange={(e) =>
                        setSelected((s) => ({ ...s, [key]: e.target.value }))
                      }
                      className={selectCls}
                    >
                      <option value="">Leave unlinked</option>
                      {opts.map((o) => (
                        <option key={o.id} value={o.id}>
                          {optionLabel(o)}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              );
            })}

          {error && <p className="text-sm text-fidelity-low">{error}</p>}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3.5">
          <button
            onClick={onClose}
            className="rounded-control border border-border px-3 py-1.5 text-sm text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !hasSelection}
            className="rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-1.5 text-sm text-accent-200 hover:bg-accent-500/25 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {submitting ? "Linking…" : "Link Evidence"}
          </button>
        </div>
      </div>
    </div>
  );
}
