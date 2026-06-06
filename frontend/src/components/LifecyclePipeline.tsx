// M104 — Reusable lifecycle pipeline UI.
// Premium institutional stepper built on M101/M102 tokens (no hardcoded colors,
// no game-progress-bar look). Reduced-motion safe via the global guard.
//
// Backend tracks 6 lifecycle stages (research, backtest, backtest_review,
// paper_candidate, shadow, production_candidate) but the DISPLAY pipeline is 5:
// "backtest" is collapsed into "Backtest Review".

import type { StrategyLifecycleResponse, LifecycleBlocker } from "@/types";

export interface LifecyclePipelineProps {
  lifecycle: StrategyLifecycleResponse | null;
  compact?: boolean;
  onBlockerAction?: (blocker: LifecycleBlocker) => void;
  onOpenGovernance?: () => void;
}

// ---------------------------------------------------------------------------
// Stage normalization — 6 backend stages -> 5 display nodes.
// ---------------------------------------------------------------------------

type DisplayKey =
  | "research"
  | "backtest_review"
  | "paper_candidate"
  | "shadow"
  | "production_candidate";

type NodeStatus = "complete" | "current" | "next" | "blocked" | "locked";

interface DisplayNode {
  key: DisplayKey;
  label: string;
  index: number;
  status: NodeStatus;
}

const DISPLAY_STAGES: { key: DisplayKey; label: string }[] = [
  { key: "research", label: "Research" },
  { key: "backtest_review", label: "Backtest Review" },
  { key: "paper_candidate", label: "Paper Candidate" },
  { key: "shadow", label: "Shadow" },
  { key: "production_candidate", label: "Production Candidate" },
];

// Collapse "backtest" into the "Backtest Review" display node; everything else
// maps 1:1. Unknown / null values fall back to "research" so we never crash.
function normalizeKey(raw: string | null | undefined): DisplayKey {
  switch (raw) {
    case "backtest":
    case "backtest_review":
      return "backtest_review";
    case "paper_candidate":
      return "paper_candidate";
    case "shadow":
      return "shadow";
    case "production_candidate":
      return "production_candidate";
    case "research":
    default:
      return "research";
  }
}

function displayIndex(key: DisplayKey): number {
  return DISPLAY_STAGES.findIndex((s) => s.key === key);
}

function deriveNodes(lifecycle: StrategyLifecycleResponse): DisplayNode[] {
  const currentKey = normalizeKey(lifecycle.current_stage);
  const currentIdx = displayIndex(currentKey);
  const nextKey = lifecycle.next_stage ? normalizeKey(lifecycle.next_stage) : null;

  return DISPLAY_STAGES.map((stage, i) => {
    let status: NodeStatus;
    const isNext = nextKey !== null && stage.key === nextKey;

    if (i < currentIdx) {
      status = "complete";
    } else if (i === currentIdx) {
      status = "current";
    } else if (isNext && lifecycle.blocked) {
      status = "blocked";
    } else if (isNext) {
      status = "next";
    } else {
      status = "locked";
    }
    return { key: stage.key, label: stage.label, index: i, status };
  });
}

// ---------------------------------------------------------------------------
// Token-only visual treatments.
// ---------------------------------------------------------------------------

// A blocker is a "hard" (red) block when its primary blocker is critical/high
// severity; otherwise it's a reachable-but-gated amber warning.
function isHardBlock(lifecycle: StrategyLifecycleResponse): boolean {
  const primary = lifecycle.blockers[0];
  if (!primary) return false;
  const sev = primary.severity.toLowerCase();
  return sev === "critical" || sev === "high";
}

const GLYPH: Record<NodeStatus, string> = {
  complete: "✓", // ✓
  current: "●", // ●
  next: "○", // ○
  blocked: "⚠", // ⚠
  locked: "🔒", // 🔒
};

function nodeClasses(status: NodeStatus, hardBlock: boolean): string {
  switch (status) {
    case "complete":
      return "border-fidelity-high/40 bg-fidelity-high/10 text-fidelity-high state-glow-success";
    case "current":
      return "border-brand bg-brand/15 text-accent-200 state-glow-primary ring-2 ring-brand/30 animate-soft-pulse";
    case "next":
      return "border-research/40 bg-research/10 text-research-300";
    case "blocked":
      return hardBlock
        ? "border-fidelity-low/60 bg-fidelity-low/10 text-fidelity-low state-glow-danger"
        : "border-fidelity-medium/60 bg-fidelity-medium/10 text-fidelity-medium state-glow-warning";
    case "locked":
    default:
      return "border-border bg-bg-800 text-text-muted opacity-60";
  }
}

function labelClasses(status: NodeStatus, hardBlock: boolean): string {
  switch (status) {
    case "complete":
      return "text-text-secondary";
    case "current":
      return "text-accent-200";
    case "next":
      return "text-research-300";
    case "blocked":
      return hardBlock ? "text-fidelity-low" : "text-fidelity-medium";
    case "locked":
    default:
      return "text-text-muted";
  }
}

export default function LifecyclePipeline({
  lifecycle,
  compact = false,
  onBlockerAction,
  onOpenGovernance,
}: LifecyclePipelineProps) {
  // Null handling — calm muted placeholder, never crash.
  if (!lifecycle) {
    return (
      <div className="rounded-card border border-border bg-bg-700 px-4 py-6 text-center shadow-card animate-fade-in">
        <p className="text-sm text-text-muted">Lifecycle data unavailable.</p>
      </div>
    );
  }

  const nodes = deriveNodes(lifecycle);
  const hardBlock = isHardBlock(lifecycle);
  const currentNode = nodes.find((n) => n.status === "current");
  const currentIdx = currentNode ? currentNode.index : -1;
  const primaryBlocker = lifecycle.blockers[0] ?? null;

  const nextLabel =
    nodes.find((n) => n.status === "next" || n.status === "blocked")?.label ??
    "—";

  return (
    <div className="rounded-card border border-border bg-bg-700 shadow-card animate-fade-in">
      {/* Stepper */}
      <div className={compact ? "px-3 py-3" : "px-4 py-4"}>
        <div className="overflow-x-auto">
          <div className="flex min-w-max items-start">
            {nodes.map((node, idx) => {
              const isLast = idx === nodes.length - 1;
              // Connector BEFORE current (idx < currentIdx) is "filled".
              const connectorFilled = idx < currentIdx;
              // The active connector — the one leading out of the current node —
              // gets a tasteful animated sheen.
              const connectorActive = idx === currentIdx && currentIdx >= 0;

              return (
                <div key={node.key} className="flex items-start">
                  <div className="flex w-20 flex-col items-center">
                    <div
                      className={
                        "flex h-8 w-8 items-center justify-center rounded-full border text-sm font-semibold transition-all duration-200 " +
                        nodeClasses(node.status, hardBlock)
                      }
                      aria-current={node.status === "current" ? "step" : undefined}
                    >
                      <span aria-hidden="true">{GLYPH[node.status]}</span>
                    </div>
                    <span
                      className={
                        "mt-1.5 text-center text-2xs leading-tight " +
                        labelClasses(node.status, hardBlock)
                      }
                    >
                      {node.label}
                    </span>
                  </div>

                  {!isLast ? (
                    <div className="mt-4 h-px w-8 shrink-0 overflow-hidden rounded-full">
                      {connectorActive ? (
                        // Tasteful slow shimmer on the active connector.
                        <div
                          className="h-full w-full animate-shimmer bg-[length:200%_100%]"
                          style={{
                            backgroundImage:
                              "linear-gradient(90deg, rgb(79 140 255 / 0.5), rgb(139 92 246 / 0.5), rgb(79 140 255 / 0.5))",
                          }}
                        />
                      ) : (
                        <div
                          className={
                            "h-full w-full " +
                            (connectorFilled
                              ? "bg-fidelity-high/40"
                              : "bg-border")
                          }
                        />
                      )}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>

        {/* Caption — compact mode shows a single Current -> Next line. */}
        {compact ? (
          <p className="mt-3 text-2xs text-text-secondary">
            <span className="text-text-primary">
              {lifecycle.current_stage_label}
            </span>{" "}
            &rarr; {lifecycle.next_stage_label ?? "—"}
          </p>
        ) : null}
      </div>

      {/* FULL mode detail block */}
      {!compact ? (
        <>
          <div className="border-t border-border px-4 py-3">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
              <span className="text-text-secondary">Current:</span>
              <span className="text-text-primary">
                {lifecycle.current_stage_label}
              </span>
              <span className="text-text-muted">&rarr;</span>
              <span className="text-text-secondary">Next:</span>
              <span className="text-text-primary">{nextLabel}</span>
            </div>

            {lifecycle.blocked && primaryBlocker ? (
              <div
                className={
                  "mt-3 flex items-start gap-3 rounded-control border px-3 py-2 " +
                  (hardBlock
                    ? "border-fidelity-low/40 bg-fidelity-low/10"
                    : "border-fidelity-medium/40 bg-fidelity-medium/10")
                }
              >
                <span
                  aria-hidden="true"
                  className={
                    "mt-0.5 shrink-0 " +
                    (hardBlock ? "text-fidelity-low" : "text-fidelity-medium")
                  }
                >
                  {"⚠"}
                </span>
                <div className="min-w-0 flex-1">
                  <div
                    className={
                      "text-2xs font-medium uppercase tracking-eyebrow " +
                      (hardBlock ? "text-fidelity-low" : "text-fidelity-medium")
                    }
                  >
                    Blocked by
                  </div>
                  <div className="mt-0.5 text-sm text-text-primary">
                    {primaryBlocker.reason}
                  </div>
                  {primaryBlocker.detail ? (
                    <div className="text-xs text-text-secondary">
                      {primaryBlocker.detail}
                    </div>
                  ) : null}
                </div>
                {onBlockerAction ? (
                  <button
                    type="button"
                    onClick={() => onBlockerAction(primaryBlocker)}
                    className="shrink-0 rounded-control border border-border px-2.5 py-1 text-2xs text-text-secondary transition-colors hover:bg-bg-600 hover:text-text-primary"
                  >
                    {primaryBlocker.action_label}
                  </button>
                ) : null}
              </div>
            ) : null}

            {onOpenGovernance ? (
              <button
                type="button"
                onClick={onOpenGovernance}
                className="mt-3 text-2xs text-accent-300 underline-offset-2 transition-colors hover:text-accent-200 hover:underline"
              >
                Open Governance &rarr;
              </button>
            ) : null}
          </div>

          <div className="border-t border-border px-4 py-2">
            <p className="text-2xs italic text-text-muted">
              {lifecycle.disclaimer}
            </p>
          </div>
        </>
      ) : null}
    </div>
  );
}
