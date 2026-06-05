/**
 * StrategyRowMenu — fixed-position actions dropdown for each strategy table row.
 *
 * Root cause of the previous "nothing appears" bug:
 *   The Strategies table wrapper has `overflow-hidden` on the card <div>.  CSS
 *   overflow clipping is applied BEFORE compositing, so even a z-index:9999
 *   `position:absolute` child is silently clipped at the element boundary.
 *   The fix: calculate the button's viewport position with getBoundingClientRect()
 *   and render the dropdown with `position:fixed` so it escapes the overflow
 *   context entirely.
 *
 * Implemented actions (with live endpoints):
 *   - View details       → navigate /strategies/:id
 *   - Upload evidence    → navigate /strategies/:id?tab=developer
 *   - Promotion gates    → navigate /strategies/:id?tab=governance
 *   - Refresh score      → POST /api/strategies/:id/reliability-score
 *   - Generate report    → POST /api/reports/strategy/:id
 *   - Edit               → opens StrategyEditModal (parent callback)
 *   - Archive            → opens StrategyArchiveModal (parent callback)
 *
 * NOT implemented (no backend endpoint):
 *   - Run audit   (runBacktestAudit requires a run ID, no strategy-level trigger)
 *   - Hard delete (archiveStrategy is the only DELETE; it soft-archives)
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Strategy } from "@/types";
import { computeStrategyReliabilityScore, generateStrategyReport } from "@/lib/api";
import { canWriteResearch } from "@/lib/permissions";
import type { PermissionContext } from "@/lib/permissions";

interface Props {
  strategy: Strategy;
  /** Auth context – satisfies PermissionContext (isAuthenticated, role, permissions). */
  auth: PermissionContext;
  /** Controlled open state – parent tracks which row menu is open. */
  isOpen: boolean;
  onOpen: () => void;
  onClose: () => void;
  /** Callback to open the StrategyEditModal in the parent. */
  onEdit: () => void;
  /** Callback to open the StrategyArchiveModal in the parent. */
  onArchive: () => void;
  /** Called with a human-readable result message (success or error) for the parent banner. */
  onFeedback: (message: string, isError?: boolean) => void;
  /** Called after a mutating action succeeds so the parent can reload the table. */
  onRefreshed: () => void;
}

export default function StrategyRowMenu({
  strategy,
  auth,
  isOpen,
  onOpen,
  onClose,
  onEdit,
  onArchive,
  onFeedback,
  onRefreshed,
}: Props) {
  const navigate = useNavigate();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [dropdownPos, setDropdownPos] = useState({ top: 0, right: 0 });
  // Loading key: "refresh" | "report" | null
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const canWrite = canWriteResearch(auth);

  /** Calculate the fixed-position coordinates from the trigger button rect. */
  function handleOpen() {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownPos({
        top: rect.bottom + 4,
        // align right edge of dropdown with right edge of button
        right: window.innerWidth - rect.right,
      });
    }
    onOpen();
  }

  // Close on Escape or page scroll
  useEffect(() => {
    if (!isOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    function onScroll() {
      onClose();
    }
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, { passive: true, capture: true });
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [isOpen, onClose]);

  // -------------------------------------------------------------------------
  // Async action handlers
  // -------------------------------------------------------------------------

  async function handleRefreshScore() {
    onClose();
    setActionLoading("refresh");
    try {
      await computeStrategyReliabilityScore(strategy.id);
      onFeedback(`Reliability score refreshed for "${strategy.name}".`);
      onRefreshed();
    } catch (err) {
      onFeedback(
        `Refresh score failed: ${err instanceof Error ? err.message : "unknown error"}`,
        true,
      );
    } finally {
      setActionLoading(null);
    }
  }

  async function handleGenerateReport() {
    onClose();
    setActionLoading("report");
    try {
      await generateStrategyReport(strategy.id);
      onFeedback(
        `Report generated for "${strategy.name}". View it in the strategy's Exports tab.`,
      );
    } catch (err) {
      onFeedback(
        `Generate report failed: ${err instanceof Error ? err.message : "unknown error"}`,
        true,
      );
    } finally {
      setActionLoading(null);
    }
  }

  // -------------------------------------------------------------------------
  // Style helpers
  // -------------------------------------------------------------------------

  const itemCls =
    "block w-full px-3 py-1.5 text-left text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary transition-colors";
  const disabledItemCls =
    "block w-full px-3 py-1.5 text-left text-xs text-text-muted/40 cursor-not-allowed select-none";
  const destructiveCls =
    "block w-full px-3 py-1.5 text-left text-xs text-fidelity-medium hover:bg-bg-600 transition-colors";

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  const isBusy = actionLoading !== null;

  return (
    <div className="relative inline-block text-left">
      {/* Trigger button — always rendered so buttonRef is stable */}
      <button
        ref={buttonRef}
        onClick={isOpen ? onClose : handleOpen}
        disabled={isBusy}
        className={`rounded-control border border-border px-2 py-1 text-2xs transition-colors ${
          isOpen
            ? "bg-bg-600 text-text-primary"
            : "text-text-secondary hover:bg-bg-600 hover:text-text-primary"
        } disabled:cursor-wait disabled:opacity-50`}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label={`Actions for ${strategy.name}`}
      >
        {isBusy ? "…" : "⋯"}
      </button>

      {isOpen && (
        <>
          {/* Full-screen backdrop to capture outside clicks */}
          <div
            className="fixed inset-0 z-40"
            aria-hidden="true"
            onClick={onClose}
          />

          {/*
           * Fixed dropdown — escapes the table's `overflow-hidden` container.
           * `top` and `right` are calculated in handleOpen() from the button's
           * getBoundingClientRect() so they align correctly regardless of scroll.
           */}
          <div
            style={{ position: "fixed", top: dropdownPos.top, right: dropdownPos.right }}
            className="z-50 w-48 rounded-card border border-border bg-bg-800 py-1 shadow-panel"
            role="menu"
            aria-label={`Strategy actions for ${strategy.name}`}
          >
            {/* ── Navigation ── */}
            <button
              className={itemCls}
              onClick={() => { onClose(); navigate(`/strategies/${strategy.id}`); }}
              role="menuitem"
            >
              View details
            </button>
            <button
              className={itemCls}
              onClick={() => {
                onClose();
                navigate(`/strategies/${strategy.id}?tab=developer`);
              }}
              role="menuitem"
            >
              Upload evidence
            </button>
            <button
              className={itemCls}
              onClick={() => {
                onClose();
                navigate(`/strategies/${strategy.id}?tab=governance`);
              }}
              role="menuitem"
            >
              Promotion gates
            </button>

            <div className="my-1 border-t border-border" />

            {/* ── Async actions (write-gated) ── */}
            {canWrite ? (
              <button className={itemCls} onClick={handleRefreshScore} role="menuitem">
                Refresh score
              </button>
            ) : (
              <span className={disabledItemCls} title="Requires write access">
                Refresh score
              </span>
            )}
            {canWrite ? (
              <button className={itemCls} onClick={handleGenerateReport} role="menuitem">
                Generate report
              </button>
            ) : (
              <span className={disabledItemCls} title="Requires write access">
                Generate report
              </span>
            )}

            <div className="my-1 border-t border-border" />

            {/* ── Modal-opening actions (write-gated) ── */}
            {canWrite ? (
              <button
                className={itemCls}
                onClick={() => { onClose(); onEdit(); }}
                role="menuitem"
              >
                Edit
              </button>
            ) : (
              <span className={disabledItemCls} title="Requires write access">
                Edit
              </span>
            )}
            {strategy.status !== "archived" &&
              (canWrite ? (
                <button
                  className={destructiveCls}
                  onClick={() => { onClose(); onArchive(); }}
                  role="menuitem"
                >
                  Archive
                </button>
              ) : (
                <span className={disabledItemCls} title="Requires write access">
                  Archive
                </span>
              ))}
          </div>
        </>
      )}
    </div>
  );
}
