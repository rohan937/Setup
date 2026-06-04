import { useEffect, useState } from "react";
import { updateStrategy, archiveStrategy } from "@/lib/api";

const ASSET_CLASSES = [
  "equity", "etf", "future", "option", "fx", "crypto", "rate", "commodity", "other",
];
const STATUSES = ["active", "draft", "paused", "archived"];

const inputCls =
  "w-full rounded-control border border-border bg-bg-600 px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-accent-500 focus:outline-none";
const selectCls = inputCls;

const overlay =
  "fixed inset-0 z-50 flex items-center justify-center p-4";
const backdrop = "fixed inset-0 bg-bg-950/85";
const panel =
  "relative w-full max-w-md rounded-card border border-border bg-bg-800 shadow-panel";

// ---------------------------------------------------------------------------
// Edit modal
// ---------------------------------------------------------------------------

export function StrategyEditModal({
  open,
  strategyId,
  initial,
  onClose,
  onSaved,
}: {
  open: boolean;
  strategyId: string;
  initial: {
    name: string;
    description?: string | null;
    asset_class: string;
    status: string;
  };
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(initial.name);
  const [description, setDescription] = useState(initial.description ?? "");
  const [assetClass, setAssetClass] = useState(initial.asset_class);
  const [status, setStatus] = useState(initial.status);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName(initial.name);
      setDescription(initial.description ?? "");
      setAssetClass(initial.asset_class);
      setStatus(initial.status);
      setError(null);
    }
  }, [open, initial]);

  if (!open) return null;

  async function handleSave() {
    if (!name.trim()) {
      setError("Name is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateStrategy(strategyId, {
        name: name.trim(),
        description,
        asset_class: assetClass,
        status,
      });
      setSaving(false);
      onSaved();
      onClose();
    } catch (e) {
      setSaving(false);
      setError(e instanceof Error ? e.message : "Update failed.");
    }
  }

  return (
    <div className={overlay}>
      <div className={backdrop} aria-hidden="true" onClick={onClose} />
      <div role="dialog" aria-modal="true" className={panel}>
        <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
          <div>
            <p className="caption">Manage strategy</p>
            <p className="mt-0.5 text-sm font-medium text-text-primary">Edit details</p>
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

        <div className="flex flex-col gap-4 px-5 py-5">
          <div>
            <label className="caption mb-1.5 block">Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className="caption mb-1.5 block">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className={inputCls}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="caption mb-1.5 block">Asset class</label>
              <select value={assetClass} onChange={(e) => setAssetClass(e.target.value)} className={selectCls}>
                {ASSET_CLASSES.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="caption mb-1.5 block">Status</label>
              <select value={status} onChange={(e) => setStatus(e.target.value)} className={selectCls}>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          </div>
          {error && <p className="text-sm text-fidelity-low">{error}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3.5">
          <button
            onClick={onClose}
            className="rounded-control border border-border px-3 py-1.5 text-sm text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-1.5 text-sm text-accent-200 hover:bg-accent-500/25 disabled:opacity-40"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Archive confirmation modal
// ---------------------------------------------------------------------------

export function StrategyArchiveModal({
  open,
  strategyId,
  strategyName,
  onClose,
  onArchived,
}: {
  open: boolean;
  strategyId: string;
  strategyName: string;
  onClose: () => void;
  onArchived: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setConfirmed(false);
      setError(null);
    }
  }, [open]);

  if (!open) return null;

  async function handleArchive() {
    setBusy(true);
    setError(null);
    try {
      await archiveStrategy(strategyId);
      setBusy(false);
      onArchived();
      onClose();
    } catch (e) {
      setBusy(false);
      setError(e instanceof Error ? e.message : "Archive failed.");
    }
  }

  return (
    <div className={overlay}>
      <div className={backdrop} aria-hidden="true" onClick={onClose} />
      <div role="dialog" aria-modal="true" className={panel}>
        <div className="border-b border-border px-5 py-3.5">
          <p className="caption">Manage strategy</p>
          <p className="mt-0.5 text-sm font-medium text-text-primary">Archive strategy</p>
        </div>

        <div className="flex flex-col gap-3 px-5 py-5">
          <p className="text-sm text-text-secondary">
            Archiving moves <span className="text-text-primary">{strategyName}</span> out of the
            active list. This is a local product-management action — the evidence trail
            (runs, snapshots, reports, timeline) is preserved and nothing is permanently
            deleted.
          </p>
          <label className="flex items-start gap-2 text-sm text-text-secondary">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              className="mt-0.5"
            />
            I understand this will archive the strategy.
          </label>
          {error && <p className="text-sm text-fidelity-low">{error}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3.5">
          <button
            onClick={onClose}
            className="rounded-control border border-border px-3 py-1.5 text-sm text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            Cancel
          </button>
          <button
            onClick={handleArchive}
            disabled={!confirmed || busy}
            className="rounded-control border border-fidelity-medium/40 bg-fidelity-medium/15 px-3 py-1.5 text-sm text-fidelity-medium hover:bg-fidelity-medium/25 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "Archiving…" : "Archive Strategy"}
          </button>
        </div>
      </div>
    </div>
  );
}
