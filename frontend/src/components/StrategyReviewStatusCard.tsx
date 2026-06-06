/**
 * StrategyReviewStatusCard (M87)
 *
 * Compact Overview card summarising the strategy's promotion-review status:
 *   - current lifecycle stage
 *   - whether a pending review exists (target stage, reviewer, status, top
 *     blockers)
 *   - a primary action: "Submit for review" (no pending) / "Open review"
 *     (jumps to the Governance tab)
 *
 * Research-evidence governance only — not a trading approval.
 */

import { useEffect, useState } from "react";
import { getStrategyLifecycle, getStrategyReview, getStrategyReviews } from "@/lib/api";
import type {
  ReviewBlocker,
  StrategyReview,
  StrategyReviewStatus,
} from "@/types";

const REVIEW_STATUS_CHIP: Record<StrategyReviewStatus, string> = {
  draft: "border-border bg-bg-700 text-text-muted",
  submitted: "border-blue-800/50 bg-blue-950/50 text-blue-300",
  approved: "border-teal-800/50 bg-teal-950/50 text-teal-300",
  rejected: "border-red-800/50 bg-red-950/50 text-red-300",
  changes_requested: "border-amber-800/50 bg-amber-950/50 text-amber-300",
  cancelled: "border-border bg-bg-700 text-text-muted",
};

const TERMINAL_STATUSES: StrategyReviewStatus[] = [
  "approved",
  "rejected",
  "cancelled",
];

function titleCase(v: string): string {
  return v.replace(/_/g, " ");
}

function shortActor(id: string | null): string {
  if (!id) return "unassigned";
  return id.length > 8 ? id.slice(0, 8) : id;
}

export default function StrategyReviewStatusCard({
  strategyId,
  onOpenReview,
}: {
  strategyId: string;
  /** Navigate to the Governance tab to open the review workflow. */
  onOpenReview: () => void;
}) {
  const [currentStage, setCurrentStage] = useState<string | null>(null);
  const [pending, setPending] = useState<StrategyReview | null>(null);
  const [blockers, setBlockers] = useState<ReviewBlocker[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    // Current lifecycle stage (best-effort).
    getStrategyLifecycle(strategyId)
      .then((lc) => {
        if (!cancelled) setCurrentStage(lc.current_stage);
      })
      .catch(() => {
        /* best-effort */
      });

    getStrategyReviews(strategyId)
      .then(async (res) => {
        const items = res.items ?? [];
        const open = [...items]
          .sort(
            (a, b) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime(),
          )
          .find((r) => !TERMINAL_STATUSES.includes(r.status));
        if (cancelled) return;
        setPending(open ?? null);
        if (open) {
          try {
            const d = await getStrategyReview(open.id);
            if (!cancelled) setBlockers(d.checklist.blockers ?? []);
          } catch {
            /* best-effort */
          }
        }
      })
      .catch(() => {
        if (!cancelled) setPending(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [strategyId]);

  return (
    <div className="rounded-card border border-border bg-bg-700 shadow-card">
      <div className="flex items-center justify-between border-b border-border/70 px-4 py-2.5">
        <p className="text-sm font-medium text-text-primary">Promotion Review</p>
        {pending && (
          <span
            className={`inline-flex items-center rounded-chip border px-2 py-0.5 font-mono text-2xs ${REVIEW_STATUS_CHIP[pending.status]}`}
          >
            {titleCase(pending.status)}
          </span>
        )}
      </div>

      <div className="space-y-3 px-4 py-4">
        {loading ? (
          <p className="text-2xs text-text-muted">Loading review status…</p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-2xs">
              <span className="text-text-muted">
                Current stage:{" "}
                <span className="text-text-secondary">
                  {currentStage ? titleCase(currentStage) : "—"}
                </span>
              </span>
              {pending && (
                <>
                  <span className="text-text-muted">
                    Target:{" "}
                    <span className="text-text-secondary">
                      {titleCase(pending.target_stage)}
                    </span>
                  </span>
                  <span className="text-text-muted">
                    Reviewer:{" "}
                    <span className="text-text-secondary">
                      {shortActor(pending.reviewer_user_id)}
                    </span>
                  </span>
                </>
              )}
            </div>

            {pending ? (
              blockers.length > 0 ? (
                <div className="rounded-control border border-red-800/50 bg-red-950/30 px-3 py-2">
                  <p className="text-2xs font-medium text-red-300">
                    {blockers.length} blocker
                    {blockers.length === 1 ? "" : "s"} outstanding
                  </p>
                  <ul className="mt-1 space-y-0.5">
                    {blockers.slice(0, 3).map((b, i) => (
                      <li
                        key={`${b.title}-${i}`}
                        className="truncate text-2xs text-text-secondary"
                      >
                        • {b.title}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="text-2xs text-teal-300">
                  No outstanding blockers on the active review.
                </p>
              )
            ) : (
              <p className="text-2xs text-text-muted">
                No pending review. Submit this strategy for stage-promotion
                review when its evidence is ready.
              </p>
            )}

            <div className="flex justify-end">
              <button
                onClick={onOpenReview}
                className="rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-1.5 text-xs text-accent-200 hover:bg-accent-500/25"
              >
                {pending ? "Open review" : "Submit for review"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
