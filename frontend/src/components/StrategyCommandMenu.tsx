/**
 * StrategyCommandMenu — full strategy-level command palette behind "Manage ▾".
 *
 * Replaces the old 3-item Manage dropdown with a sectioned command menu covering
 * Reliability, Evidence, Governance, Navigate, Exports, and Edit (Danger Zone).
 *
 * Positioning: uses position:fixed anchored to the trigger button's
 * getBoundingClientRect() so it escapes any overflow:hidden ancestor.
 *
 * Async actions handled here:
 *   - Refresh / force-refresh reliability snapshot
 *   - Run backtest audit on latest run
 *   - Export JSON / Markdown (with browser download)
 *   - Create default regression tests
 *   - Create default config-policy guardrails
 *   - Create default evidence SLA
 *   - Generate review cases
 *   - Run regression tests (latest mode)
 *
 * Async actions delegated to parent (already have parent-level loading states):
 *   - Compute / refresh reliability score  → onComputeScore
 *   - Generate reliability report          → onGenerateReport
 *
 * Actions intentionally omitted:
 *   - Hard delete — no safe backend hard-delete endpoint; only soft archive exists
 *   - Run audit all runs — runBacktestAudit requires a single run_id; no
 *     batch-audit endpoint exists
 */
import { useEffect, useRef, useState } from "react";
import {
  createDefaultConfigPolicy,
  createDefaultEvidenceSLAPolicy,
  createDefaultRegressionTests,
  exportStrategyEvidence,
  generateResearchReviewCases,
  generateStrategyAlerts,
  refreshStrategyReliabilitySnapshot,
  runBacktestAudit,
  runStrategyRegressionTests,
} from "@/lib/api";
import { canWriteResearch } from "@/lib/permissions";
import type { PermissionContext } from "@/lib/permissions";

type StrategyTab =
  | "overview"
  | "evidence"
  | "runs"
  | "governance"
  | "lineage"
  | "exports"
  | "developer";

export interface StrategyCommandMenuProps {
  strategyId: string;
  /** Strategy's current status — needed to hide Archive for already-archived. */
  strategyStatus: string;
  /** ID of the most recent run (runs[0].id), or null when no runs exist. */
  latestRunId: string | null;
  auth: PermissionContext;
  isOpen: boolean;
  onOpen: () => void;
  onClose: () => void;
  /** Already-wired parent handlers — have their own loading states displayed in the header. */
  onComputeScore: () => void;
  onGenerateReport: () => void;
  computingScore: boolean;
  generatingReport: boolean;
  /** Switch to a different tab on the Strategy Detail page. */
  onSwitchTab: (tab: StrategyTab) => void;
  /** Open the respective drawer/modal in the parent. */
  onOpenRunDrawer: () => void;
  onOpenVersionDrawer: () => void;
  onOpenConfigDrawer: () => void;
  onOpenUniverseDrawer: () => void;
  onOpenSignalDrawer: () => void;
  onOpenEditModal: () => void;
  onOpenArchiveModal: () => void;
  /** Open the evidence repair modal for a specific run. */
  onOpenRepairModal: (runId: string) => void;
  /** Show a temporary banner in the parent page (success or error). */
  onFeedback: (msg: string, isError?: boolean) => void;
  /** Reload all strategy data from the server. */
  onRefreshed: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-3 pb-1 pt-2.5">
      <span className="font-mono text-2xs uppercase tracking-wider text-text-muted/60">
        {children}
      </span>
    </div>
  );
}

function Divider() {
  return <div className="my-1 border-t border-border" />;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function StrategyCommandMenu({
  strategyId,
  strategyStatus,
  latestRunId,
  auth,
  isOpen,
  onOpen,
  onClose,
  onComputeScore,
  onGenerateReport,
  computingScore,
  generatingReport,
  onSwitchTab,
  onOpenRunDrawer,
  onOpenVersionDrawer,
  onOpenConfigDrawer,
  onOpenUniverseDrawer,
  onOpenSignalDrawer,
  onOpenEditModal,
  onOpenArchiveModal,
  onOpenRepairModal,
  onFeedback,
  onRefreshed,
}: StrategyCommandMenuProps) {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [pos, setPos] = useState({ top: 0, right: 0 });
  /** Key of the currently-running async action, or null. */
  const [loadingKey, setLoadingKey] = useState<string | null>(null);
  /** True for 2 s after a successful "Copy ID". */
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const canWrite = canWriteResearch(auth);

  // ── Calculate dropdown position ──────────────────────────────────────────
  function handleOpen() {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      // Flip upward if close to the bottom of the viewport
      const menuEstHeight = 560;
      const fitsBelow = rect.bottom + menuEstHeight < window.innerHeight;
      setPos({
        top: fitsBelow ? rect.bottom + 4 : rect.top - menuEstHeight - 4,
        right: window.innerWidth - rect.right,
      });
    }
    onOpen();
  }

  // ── Close on Escape / scroll ─────────────────────────────────────────────
  useEffect(() => {
    if (!isOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    function onScroll() {
      onClose();
    }
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, { capture: true, passive: true });
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [isOpen, onClose]);

  // ── Generic async runner ──────────────────────────────────────────────────
  async function run(key: string, fn: () => Promise<void>) {
    setLoadingKey(key);
    try {
      await fn();
    } catch (err) {
      onFeedback(
        err instanceof Error ? err.message : `"${key}" action failed.`,
        true,
      );
    } finally {
      setLoadingKey(null);
    }
  }

  function nav(tab: StrategyTab) {
    onClose();
    onSwitchTab(tab);
  }

  function opener(fn: () => void) {
    return () => { onClose(); fn(); };
  }

  // ── Specific handlers ─────────────────────────────────────────────────────

  function handleCopyId() {
    if (copyTimer.current) clearTimeout(copyTimer.current);
    navigator.clipboard
      .writeText(strategyId)
      .then(() => {
        setCopied(true);
        copyTimer.current = setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => onFeedback("Failed to copy strategy ID.", true));
  }

  async function handleRefreshSnapshot(force: boolean) {
    await run(force ? "snap-force" : "snap-refresh", async () => {
      await refreshStrategyReliabilitySnapshot(strategyId, force);
      onFeedback(
        force
          ? "Reliability snapshot force-refreshed."
          : "Reliability snapshot refreshed.",
      );
      onRefreshed();
    });
  }

  async function handleGenerateAlerts() {
    await run("gen-alerts", async () => {
      const r = await generateStrategyAlerts(strategyId);
      onFeedback(
        `Alert check complete — ${r.alerts_created} created, ` +
          `${r.alerts_auto_resolved} auto-resolved, ` +
          `${r.total_alerts_open} open.`,
      );
      onRefreshed();
    });
  }

  async function handleAuditLatest() {
    if (!latestRunId) return;
    await run("audit", async () => {
      await runBacktestAudit(latestRunId);
      onFeedback("Backtest audit complete. Check the Runs tab for the result.");
      onRefreshed();
    });
  }

  async function handleExport(format: "json" | "markdown") {
    await run(`export-${format}`, async () => {
      const data = await exportStrategyEvidence(strategyId, { format });
      const isJson = format === "json";
      const content = isJson ? JSON.stringify(data, null, 2) : (data.content ?? "");
      const type = isJson ? "application/json" : "text/markdown";
      const blob = new Blob([content], { type });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = data.filename;
      a.click();
      URL.revokeObjectURL(url);
      onFeedback(`${isJson ? "JSON" : "Markdown"} export downloaded.`);
    });
  }

  async function handleDefaultTests() {
    await run("default-tests", async () => {
      await createDefaultRegressionTests(strategyId);
      onFeedback("Default regression tests created.");
      onRefreshed();
    });
  }

  async function handleDefaultGuardrails() {
    await run("default-guardrails", async () => {
      await createDefaultConfigPolicy(strategyId);
      onFeedback("Default config-policy guardrails created.");
      onRefreshed();
    });
  }

  async function handleDefaultSLA() {
    await run("default-sla", async () => {
      await createDefaultEvidenceSLAPolicy(strategyId);
      onFeedback("Default evidence SLA policy created.");
      onRefreshed();
    });
  }

  async function handleGenerateReviewCases() {
    await run("review-cases", async () => {
      await generateResearchReviewCases(strategyId);
      onFeedback("Review cases generated. Check the Governance tab.");
      onRefreshed();
    });
  }

  async function handleRunTests() {
    await run("run-tests", async () => {
      await runStrategyRegressionTests(strategyId, { mode: "full" });
      onFeedback("Regression tests complete. Check the Governance tab for results.");
      onRefreshed();
    });
  }

  // ── Style helpers ─────────────────────────────────────────────────────────

  const iCls =
    "flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary transition-colors disabled:cursor-not-allowed";
  const dCls =
    "flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-xs text-text-muted/40 cursor-not-allowed select-none";
  const dangerCls =
    "flex w-full items-center px-3 py-1.5 text-left text-xs text-fidelity-medium hover:bg-bg-600 transition-colors";

  function label(key: string, text: string) {
    return loadingKey === key ? `${text.split(" ")[0]}…` : text;
  }

  function WriteBtn({
    actionKey,
    text,
    onClick,
    title,
  }: {
    actionKey: string;
    text: string;
    onClick: () => void;
    title?: string;
  }) {
    const busy = loadingKey === actionKey;
    if (!canWrite) {
      return (
        <span className={dCls} title="Requires write access">
          {text}
          <span className="shrink-0 text-text-muted/30 text-2xs">—</span>
        </span>
      );
    }
    return (
      <button
        className={iCls}
        onClick={onClick}
        disabled={busy || loadingKey !== null}
        title={title}
        role="menuitem"
      >
        <span>{busy ? `${text.split(" ")[0]}…` : text}</span>
      </button>
    );
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="relative inline-block text-left">
      {/* Trigger */}
      <button
        ref={buttonRef}
        onClick={isOpen ? onClose : handleOpen}
        disabled={loadingKey !== null}
        className={`rounded-control border border-border px-3 py-2 font-mono text-xs transition-colors ${
          isOpen
            ? "bg-bg-600 text-text-primary"
            : "text-text-secondary hover:bg-bg-600 hover:text-text-primary"
        } disabled:cursor-wait disabled:opacity-60`}
        aria-haspopup="menu"
        aria-expanded={isOpen}
      >
        {loadingKey ? "…" : "Manage ▾"}
      </button>

      {isOpen && (
        <>
          {/* Backdrop */}
          <div className="fixed inset-0 z-40" aria-hidden="true" onClick={onClose} />

          {/* Fixed dropdown */}
          <div
            style={{ position: "fixed", top: pos.top, right: pos.right, maxHeight: "80vh" }}
            className="z-50 w-64 overflow-y-auto rounded-card border border-border bg-bg-800 py-1 shadow-panel"
            role="menu"
          >

            {/* ── 1. RELIABILITY ─────────────────────────────────────── */}
            <SectionLabel>Reliability</SectionLabel>

            <button
              className={iCls}
              onClick={() => { onClose(); onComputeScore(); }}
              disabled={computingScore}
              role="menuitem"
            >
              {computingScore ? "Computing…" : "Refresh score"}
            </button>

            <button
              className={iCls}
              onClick={() => { onClose(); onGenerateReport(); }}
              disabled={generatingReport}
              role="menuitem"
            >
              {generatingReport ? "Generating…" : "Generate report"}
            </button>

            <WriteBtn
              actionKey="snap-refresh"
              text="Refresh snapshot"
              onClick={() => handleRefreshSnapshot(false)}
            />
            <WriteBtn
              actionKey="snap-force"
              text="Force refresh snapshot"
              onClick={() => handleRefreshSnapshot(true)}
              title="Bypass source-hash check and force a full recompute"
            />
            {latestRunId ? (
              <WriteBtn
                actionKey="audit"
                text="Run latest backtest audit"
                onClick={handleAuditLatest}
              />
            ) : (
              <span className={dCls} title="No runs exist yet">
                Run latest backtest audit
                <span className="shrink-0 text-text-muted/30 text-2xs">no runs</span>
              </span>
            )}
            <WriteBtn
              actionKey="gen-alerts"
              text="Generate alerts for this strategy"
              onClick={handleGenerateAlerts}
              title="Run the reliability alert check scoped to this strategy"
            />

            <Divider />

            {/* ── 2. EVIDENCE ────────────────────────────────────────── */}
            <SectionLabel>Evidence</SectionLabel>

            <button
              className={iCls}
              onClick={() => { onClose(); onOpenRunDrawer(); }}
              role="menuitem"
            >
              + Log run
            </button>
            <button
              className={iCls}
              onClick={() => nav("developer")}
              role="menuitem"
            >
              Upload evidence bundle
            </button>
            {latestRunId ? (
              <button
                className={iCls}
                onClick={() => { onClose(); onOpenRepairModal(latestRunId); }}
                role="menuitem"
              >
                Fix evidence links
              </button>
            ) : (
              <span className={dCls} title="No runs to repair">
                Fix evidence links
                <span className="shrink-0 text-text-muted/30 text-2xs">no runs</span>
              </span>
            )}
            <button
              className={iCls}
              onClick={() => { onClose(); onOpenVersionDrawer(); }}
              role="menuitem"
            >
              + Create version
            </button>
            <button
              className={iCls}
              onClick={() => { onClose(); onOpenConfigDrawer(); }}
              role="menuitem"
            >
              + Log config
            </button>
            <button
              className={iCls}
              onClick={() => { onClose(); onOpenUniverseDrawer(); }}
              role="menuitem"
            >
              + Log universe
            </button>
            <button
              className={iCls}
              onClick={() => { onClose(); onOpenSignalDrawer(); }}
              role="menuitem"
            >
              + Log signal
            </button>

            <Divider />

            {/* ── 3. GOVERNANCE ──────────────────────────────────────── */}
            <SectionLabel>Governance</SectionLabel>

            <button
              className={iCls}
              onClick={() => nav("governance")}
              role="menuitem"
            >
              → Promotion gates
            </button>
            <WriteBtn
              actionKey="default-guardrails"
              text="Create default guardrails"
              onClick={handleDefaultGuardrails}
            />
            <WriteBtn
              actionKey="default-tests"
              text="Create default regression tests"
              onClick={handleDefaultTests}
            />
            <WriteBtn
              actionKey="default-sla"
              text="Create default SLA policy"
              onClick={handleDefaultSLA}
            />
            <WriteBtn
              actionKey="review-cases"
              text="Generate review cases"
              onClick={handleGenerateReviewCases}
            />
            {latestRunId ? (
              <WriteBtn
                actionKey="run-tests"
                text="Run regression tests"
                onClick={handleRunTests}
              />
            ) : (
              <span className={dCls} title="No runs to test against">
                Run regression tests
                <span className="shrink-0 text-text-muted/30 text-2xs">no runs</span>
              </span>
            )}

            <Divider />

            {/* ── 4. NAVIGATE ────────────────────────────────────────── */}
            <SectionLabel>Navigate</SectionLabel>

            {(
              [
                ["evidence", "→ Evidence tab"],
                ["runs", "→ Runs tab"],
                ["exports", "→ Exports tab"],
                ["lineage", "→ Lineage / Audit Trail tab"],
                ["developer", "→ Developer tab"],
              ] as [StrategyTab, string][]
            ).map(([tab, text]) => (
              <button
                key={tab}
                className={iCls}
                onClick={() => nav(tab)}
                role="menuitem"
              >
                {text}
              </button>
            ))}

            <Divider />

            {/* ── 5. EXPORTS ─────────────────────────────────────────── */}
            <SectionLabel>Exports &amp; Other</SectionLabel>

            <button
              className={iCls}
              onClick={() => { onClose(); handleExport("json"); }}
              disabled={loadingKey === "export-json"}
              role="menuitem"
            >
              {label("export-json", "Export JSON ↓")}
            </button>
            <button
              className={iCls}
              onClick={() => { onClose(); handleExport("markdown"); }}
              disabled={loadingKey === "export-markdown"}
              role="menuitem"
            >
              {label("export-markdown", "Export Markdown ↓")}
            </button>
            <button
              className={iCls}
              onClick={handleCopyId}
              role="menuitem"
            >
              {copied ? "✓ Copied!" : "Copy strategy ID"}
            </button>

            <Divider />

            {/* ── 6. DANGER ZONE ─────────────────────────────────────── */}
            <SectionLabel>Edit</SectionLabel>

            <button
              className={iCls}
              onClick={opener(onOpenEditModal)}
              role="menuitem"
            >
              Edit strategy details
            </button>

            {strategyStatus !== "archived" && (
              canWrite ? (
                <button
                  className={dangerCls}
                  onClick={opener(onOpenArchiveModal)}
                  role="menuitem"
                >
                  Archive strategy
                </button>
              ) : (
                <span className={dCls} title="Requires write access">
                  Archive strategy
                  <span className="shrink-0 text-text-muted/30 text-2xs">—</span>
                </span>
              )
            )}
          </div>
        </>
      )}
    </div>
  );
}
