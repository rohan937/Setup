/**
 * StrategyReviewWorkflow (M87)
 *
 * Self-contained Governance section that drives a strategy's promotion review.
 *
 * Renders:
 *   - a Submit-for-review control (target-stage dropdown + Submit, write-gated)
 *   - the active review's evidence CHECKLIST (pass/warn/fail/missing) with the
 *     approval gate (can_approve) and blockers surfaced prominently
 *   - a comments list + add-comment box
 *   - a reviewer DECISION panel (Approve / Reject / Request changes). Approve is
 *     disabled with a reason when !can_approve, and an HTTP 400 surfaces the
 *     returned blockers inline — never a fake success.
 *   - the immutable DECISION LOG (events)
 *   - a Generate review packet button (download JSON / Markdown)
 *
 * Language policy: deterministic research-evidence governance only — not a
 * trading or investment recommendation, and not a trading approval.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { canWriteResearch } from "@/lib/permissions";
import {
  ReviewBlockedError,
  addReviewComment,
  approveReview,
  createStrategyReview,
  downloadTextFile,
  getReviewPacket,
  getReviewPromotionPacket,
  getStrategyReview,
  getStrategyReviews,
  rejectReview,
  requestReviewChanges,
  submitReview,
} from "@/lib/api";
import type {
  ReviewBlocker,
  ReviewChecklistItemStatus,
  StrategyReview,
  StrategyReviewDetail,
  StrategyReviewStatus,
} from "@/types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** The six promotion stages, in lifecycle order. */
const STAGE_OPTIONS: { value: string; label: string }[] = [
  { value: "research", label: "Research" },
  { value: "backtest", label: "Backtest" },
  { value: "backtest_review", label: "Backtest Review" },
  { value: "paper_candidate", label: "Paper Candidate" },
  { value: "shadow", label: "Shadow" },
  { value: "production_candidate", label: "Production Candidate" },
];

const ITEM_STATUS_CHIP: Record<ReviewChecklistItemStatus, string> = {
  pass: "border-teal-800/50 bg-teal-950/50 text-teal-300",
  warn: "border-amber-800/50 bg-amber-950/50 text-amber-300",
  fail: "border-red-800/50 bg-red-950/50 text-red-300",
  missing: "border-border bg-bg-700 text-text-muted",
};

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

function stageLabel(stage: string): string {
  const found = STAGE_OPTIONS.find((s) => s.value === stage);
  return found ? found.label : stage.replace(/_/g, " ");
}

function statusLabel(status: string): string {
  return status.replace(/_/g, " ");
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function shortActor(id: string | null): string {
  if (!id) return "system";
  return id.length > 8 ? id.slice(0, 8) : id;
}

function errMessage(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback;
}

/** Pick the active/most-recent review: prefer non-terminal, else newest. */
function pickActiveReview(items: StrategyReview[]): StrategyReview | null {
  if (items.length === 0) return null;
  const sorted = [...items].sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
  const open = sorted.find((r) => !TERMINAL_STATUSES.includes(r.status));
  return open ?? sorted[0];
}

// ---------------------------------------------------------------------------
// Small presentational pieces
// ---------------------------------------------------------------------------

function SectionHeader({
  title,
  count,
  right,
}: {
  title: string;
  count?: number;
  right?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between border-b border-border/70 px-4 py-2.5">
      <div className="flex items-center gap-2">
        <p className="text-sm font-medium text-text-primary">{title}</p>
        {count != null && (
          <span className="font-mono text-2xs text-text-muted">{count}</span>
        )}
      </div>
      {right}
    </div>
  );
}

function ReviewStatusChip({ status }: { status: StrategyReviewStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-chip border px-2 py-0.5 font-mono text-2xs ${REVIEW_STATUS_CHIP[status]}`}
    >
      {statusLabel(status)}
    </span>
  );
}

function Notice({
  notice,
}: {
  notice: { msg: string; isError: boolean } | null;
}) {
  if (!notice) return null;
  return (
    <div
      className={`rounded border px-4 py-2 font-mono text-2xs ${
        notice.isError
          ? "border-red-800 bg-red-900/20 text-red-300"
          : "border-teal-700/40 bg-teal-900/20 text-teal-300"
      }`}
    >
      {notice.msg}
    </div>
  );
}

function BlockerList({
  blockers,
  tone = "red",
}: {
  blockers: ReviewBlocker[];
  tone?: "red" | "amber";
}) {
  const wrap =
    tone === "red"
      ? "border-red-800/60 bg-red-950/30"
      : "border-amber-800/60 bg-amber-950/30";
  const title = tone === "red" ? "text-red-300" : "text-amber-300";
  return (
    <div className={`rounded-control border px-4 py-3 ${wrap}`}>
      <p className={`text-xs font-medium ${title}`}>
        {blockers.length} blocker{blockers.length === 1 ? "" : "s"} must be
        resolved before approval
      </p>
      <ul className="mt-2 space-y-2">
        {blockers.map((b, i) => (
          <li key={`${b.title}-${i}`} className="text-xs leading-snug">
            <p className="font-medium text-text-primary">{b.title}</p>
            <p className="mt-0.5 text-text-secondary">{b.reason}</p>
            {b.suggested_action && (
              <p className="mt-0.5 text-2xs text-text-muted">
                → {b.suggested_action}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function StrategyReviewWorkflow({
  strategyId,
}: {
  strategyId: string;
}) {
  const auth = useAuth();
  const canWrite = canWriteResearch(auth);

  const [detail, setDetail] = useState<StrategyReviewDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [targetStage, setTargetStage] = useState<string>("backtest_review");
  const [commentDraft, setCommentDraft] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ msg: string; isError: boolean } | null>(
    null,
  );
  // Blockers surfaced from a 400 on approve (distinct from checklist blockers).
  const [approveBlockers, setApproveBlockers] = useState<ReviewBlocker[] | null>(
    null,
  );

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getStrategyReviews(strategyId)
      .then(async (res) => {
        const items = res.items ?? [];
        const active = pickActiveReview(items);
        if (active) {
          const d = await getStrategyReview(active.id);
          setDetail(d);
        } else {
          setDetail(null);
        }
      })
      .catch((e: unknown) =>
        setError(errMessage(e, "Failed to load strategy reviews")),
      )
      .finally(() => setLoading(false));
  }, [strategyId]);

  useEffect(() => {
    load();
  }, [load]);

  // Reload only the active review detail (after a mutation on it).
  const reloadDetail = useCallback(async (reviewId: string) => {
    const d = await getStrategyReview(reviewId);
    setDetail(d);
  }, []);

  async function runAction(
    key: string,
    fn: () => Promise<void>,
    successMsg?: string,
  ) {
    setBusyAction(key);
    setNotice(null);
    try {
      await fn();
      if (successMsg) setNotice({ msg: successMsg, isError: false });
    } catch (e: unknown) {
      setNotice({ msg: errMessage(e, "Action failed"), isError: true });
    } finally {
      setBusyAction(null);
    }
  }

  const review = detail?.review ?? null;
  const checklist = detail?.checklist ?? null;
  const comments = detail?.comments ?? [];
  const events = detail?.events ?? [];

  const reviewIsOpen =
    review != null && !TERMINAL_STATUSES.includes(review.status);
  const reviewIsDraft = review?.status === "draft";
  const reviewIsSubmitted = review?.status === "submitted";

  const itemSummary = useMemo(() => {
    const items = checklist?.items ?? [];
    return {
      pass: items.filter((i) => i.status === "pass").length,
      warn: items.filter((i) => i.status === "warn").length,
      fail: items.filter((i) => i.status === "fail").length,
      missing: items.filter((i) => i.status === "missing").length,
    };
  }, [checklist]);

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------

  function handleSubmitForReview(asDraft: boolean) {
    void runAction(
      asDraft ? "create-draft" : "create-submit",
      async () => {
        const created = await createStrategyReview(strategyId, {
          target_stage: targetStage,
          as_draft: asDraft,
        });
        setApproveBlockers(null);
        await reloadDetail(created.id);
      },
      asDraft
        ? "Draft review created."
        : `Review submitted for ${stageLabel(targetStage)}.`,
    );
  }

  function handleSubmitDraft() {
    if (!review) return;
    void runAction(
      "submit",
      async () => {
        await submitReview(review.id);
        await reloadDetail(review.id);
      },
      "Review submitted for decision.",
    );
  }

  function handleApprove() {
    if (!review) return;
    setBusyAction("approve");
    setNotice(null);
    setApproveBlockers(null);
    approveReview(review.id)
      .then(async () => {
        await reloadDetail(review.id);
        setNotice({ msg: "Review approved.", isError: false });
      })
      .catch((e: unknown) => {
        if (e instanceof ReviewBlockedError) {
          setApproveBlockers(e.blockers);
          setNotice({ msg: e.message, isError: true });
        } else {
          setNotice({ msg: errMessage(e, "Approval failed"), isError: true });
        }
      })
      .finally(() => setBusyAction(null));
  }

  function handleReject() {
    if (!review) return;
    const note = window.prompt("Reason for rejecting this review:");
    if (note == null || note.trim() === "") return;
    void runAction(
      "reject",
      async () => {
        await rejectReview(review.id, note.trim());
        await reloadDetail(review.id);
      },
      "Review rejected.",
    );
  }

  function handleRequestChanges() {
    if (!review) return;
    const note = window.prompt("What changes are required?");
    if (note == null || note.trim() === "") return;
    void runAction(
      "request-changes",
      async () => {
        await requestReviewChanges(review.id, note.trim());
        await reloadDetail(review.id);
      },
      "Changes requested.",
    );
  }

  function handleAddComment() {
    if (!review || commentDraft.trim() === "") return;
    void runAction(
      "comment",
      async () => {
        await addReviewComment(review.id, commentDraft.trim());
        setCommentDraft("");
        await reloadDetail(review.id);
      },
      "Comment added.",
    );
  }

  function handlePacket(format: "json" | "markdown") {
    if (!review) return;
    void runAction(`packet-${format}`, async () => {
      const packet = await getReviewPacket(review.id, format);
      const mime = format === "json" ? "application/json" : "text/markdown";
      downloadTextFile(packet.filename, packet.content, mime);
    });
  }

  function handlePromoPacket(format: "json" | "markdown") {
    if (!review) return;
    void runAction(`promo-packet-${format}`, async () => {
      if (format === "markdown") {
        const content = await getReviewPromotionPacket(review.id, "markdown") as string;
        downloadTextFile(`promotion-packet-${review.id.slice(0, 8)}.md`, content, "text/markdown");
      } else {
        const packet = await getReviewPromotionPacket(review.id, "json") as import("@/types").PromotionPacketExportResponse;
        downloadTextFile(packet.filename, packet.content, "application/json");
      }
    });
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="rounded-card border border-border bg-bg-700 px-4 py-6 shadow-card">
        <p className="text-xs text-text-muted">Loading strategy review…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-card border border-red-800/60 bg-red-950/30 px-4 py-4 shadow-card">
        <p className="text-sm text-red-300">{error}</p>
        <button
          onClick={load}
          className="mt-2 rounded border border-red-700/50 bg-red-900/30 px-2.5 py-1 font-mono text-2xs text-red-200 hover:bg-red-900/50"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-card border border-border bg-bg-700 shadow-card">
        <SectionHeader
          title="Strategy Review Workflow"
          right={
            review && <ReviewStatusChip status={review.status} />
          }
        />
        <div className="space-y-4 px-4 py-4">
          <p className="text-2xs text-text-muted">
            Research-evidence governance for stage promotion. This is a research
            readiness review — not a trading approval or investment
            recommendation.
          </p>

          <Notice notice={notice} />

          {/* Submit-for-review control */}
          <div className="rounded-control border border-border bg-bg-800/60 px-4 py-3">
            <p className="text-xs font-medium text-text-primary">
              {reviewIsOpen
                ? "An active review is in progress"
                : "Submit this strategy for stage-promotion review"}
            </p>
            <div className="mt-3 flex flex-wrap items-end gap-2">
              <label className="flex flex-col gap-1">
                <span className="font-mono text-2xs uppercase tracking-wider text-text-muted">
                  Target stage
                </span>
                <select
                  value={targetStage}
                  onChange={(e) => setTargetStage(e.target.value)}
                  disabled={!canWrite || reviewIsOpen}
                  className="rounded border border-border bg-bg-800 px-2 py-1.5 font-mono text-xs text-text-secondary focus:outline-none focus:ring-1 focus:ring-accent-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {STAGE_OPTIONS.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                onClick={() => handleSubmitForReview(false)}
                disabled={!canWrite || reviewIsOpen || busyAction != null}
                className="rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-1.5 text-xs text-accent-200 hover:bg-accent-500/25 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {busyAction === "create-submit" ? "Working…" : "Submit for review"}
              </button>
              <button
                onClick={() => handleSubmitForReview(true)}
                disabled={!canWrite || reviewIsOpen || busyAction != null}
                className="rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
              >
                {busyAction === "create-draft" ? "Working…" : "Save as draft"}
              </button>
            </div>
            {!canWrite && (
              <p className="mt-2 text-2xs text-fidelity-medium">
                Submitting a review needs write-research access (your role:{" "}
                {auth.role ?? "viewer"}).
              </p>
            )}
            {reviewIsOpen && (
              <p className="mt-2 text-2xs text-text-muted">
                Resolve or decide the active review before starting a new one.
              </p>
            )}
          </div>

          {!review && (
            <div className="rounded-control border border-border bg-bg-800/60 px-4 py-4 text-center">
              <p className="text-sm text-text-secondary">
                No reviews yet for this strategy.
              </p>
              <p className="mt-1 text-2xs text-text-muted">
                Choose a target stage above and submit to open the first review.
              </p>
            </div>
          )}

          {review && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-2xs text-text-muted">
              <span>
                Target:{" "}
                <span className="text-text-secondary">
                  {stageLabel(review.target_stage)}
                </span>
              </span>
              {checklist && (
                <span>
                  Current stage:{" "}
                  <span className="text-text-secondary">
                    {stageLabel(checklist.current_stage)}
                  </span>
                </span>
              )}
              <span>Submitted: {fmtDateTime(review.submitted_at)}</span>
              {review.decided_at && (
                <span>Decided: {fmtDateTime(review.decided_at)}</span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Evidence checklist + approval gate */}
      {checklist && (
        <div className="rounded-card border border-border bg-bg-700 shadow-card">
          <SectionHeader
            title="Evidence Checklist"
            count={checklist.items.length}
            right={
              <div className="flex items-center gap-2 font-mono text-2xs">
                <span className="text-teal-300">{itemSummary.pass} pass</span>
                <span className="text-amber-300">{itemSummary.warn} warn</span>
                <span className="text-red-300">{itemSummary.fail} fail</span>
                <span className="text-text-muted">
                  {itemSummary.missing} missing
                </span>
              </div>
            }
          />
          <div className="space-y-3 px-4 py-4">
            {/* Approval gate banner */}
            {checklist.can_approve ? (
              <div className="rounded-control border border-teal-800/50 bg-teal-950/30 px-4 py-2.5">
                <p className="text-xs font-medium text-teal-300">
                  All required evidence is satisfied — this review can be
                  approved.
                </p>
              </div>
            ) : (
              <BlockerList blockers={checklist.blockers} tone="red" />
            )}

            {/* Items */}
            <div className="divide-y divide-border/60">
              {checklist.items.map((item) => (
                <div key={item.key} className="flex items-start gap-3 py-2.5">
                  <span
                    className={`mt-0.5 inline-flex w-16 shrink-0 items-center justify-center rounded-chip border px-1.5 py-0.5 font-mono text-2xs ${ITEM_STATUS_CHIP[item.status]}`}
                  >
                    {item.status}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-text-primary">
                      {item.title}
                      {item.required && (
                        <span className="ml-1.5 font-mono text-2xs text-text-muted">
                          required
                        </span>
                      )}
                      <span className="ml-1.5 font-mono text-2xs text-text-muted">
                        {statusLabel(item.category)}
                      </span>
                    </p>
                    {item.detail && (
                      <p className="mt-0.5 text-2xs text-text-secondary leading-snug">
                        {item.detail}
                      </p>
                    )}
                    {item.suggested_action &&
                      (item.status === "fail" || item.status === "missing") && (
                        <p className="mt-0.5 text-2xs text-text-muted leading-snug">
                          → {item.suggested_action}
                        </p>
                      )}
                  </div>
                </div>
              ))}
            </div>

            <p className="text-2xs text-text-muted">{checklist.disclaimer}</p>
          </div>
        </div>
      )}

      {/* Reviewer decision panel */}
      {review && (
        <div className="rounded-card border border-border bg-bg-700 shadow-card">
          <SectionHeader title="Reviewer Decision" />
          <div className="space-y-3 px-4 py-4">
            {!reviewIsOpen ? (
              <div className="rounded-control border border-border bg-bg-800/60 px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-text-secondary">
                    This review is closed.
                  </span>
                  <ReviewStatusChip status={review.status} />
                </div>
                {review.decision_note && (
                  <p className="mt-1.5 text-2xs text-text-muted">
                    Decision note: {review.decision_note}
                  </p>
                )}
              </div>
            ) : (
              <>
                {reviewIsDraft && (
                  <p className="text-2xs text-text-muted">
                    This review is a draft. Submit it before a decision can be
                    recorded.
                  </p>
                )}

                {/* Blockers surfaced from a 400 on approve */}
                {approveBlockers && approveBlockers.length > 0 && (
                  <BlockerList blockers={approveBlockers} tone="red" />
                )}

                <div className="flex flex-wrap items-center gap-2">
                  {reviewIsDraft && (
                    <button
                      onClick={handleSubmitDraft}
                      disabled={!canWrite || busyAction != null}
                      className="rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-1.5 text-xs text-accent-200 hover:bg-accent-500/25 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {busyAction === "submit" ? "Working…" : "Submit for decision"}
                    </button>
                  )}

                  {reviewIsSubmitted && (
                    <>
                      <span
                        title={
                          checklist && !checklist.can_approve
                            ? "Approval is blocked — resolve the outstanding blockers above."
                            : undefined
                        }
                      >
                        <button
                          onClick={handleApprove}
                          disabled={
                            !canWrite ||
                            busyAction != null ||
                            (checklist ? !checklist.can_approve : false)
                          }
                          className="rounded-control border border-teal-700/50 bg-teal-900/30 px-3 py-1.5 text-xs text-teal-200 hover:bg-teal-900/50 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          {busyAction === "approve" ? "Working…" : "Approve"}
                        </button>
                      </span>
                      <button
                        onClick={handleRequestChanges}
                        disabled={!canWrite || busyAction != null}
                        className="rounded-control border border-amber-700/50 bg-amber-900/30 px-3 py-1.5 text-xs text-amber-200 hover:bg-amber-900/50 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {busyAction === "request-changes"
                          ? "Working…"
                          : "Request changes"}
                      </button>
                      <button
                        onClick={handleReject}
                        disabled={!canWrite || busyAction != null}
                        className="rounded-control border border-red-700/50 bg-red-900/30 px-3 py-1.5 text-xs text-red-200 hover:bg-red-900/50 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {busyAction === "reject" ? "Working…" : "Reject"}
                      </button>
                    </>
                  )}
                </div>

                {reviewIsSubmitted && checklist && !checklist.can_approve && (
                  <p className="text-2xs text-fidelity-medium">
                    Approve is disabled until the {checklist.blockers.length}{" "}
                    blocker{checklist.blockers.length === 1 ? "" : "s"} above are
                    resolved.
                  </p>
                )}
                {!canWrite && (
                  <p className="text-2xs text-fidelity-medium">
                    Recording a decision needs write-research access (your role:{" "}
                    {auth.role ?? "viewer"}).
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* Comments */}
      {review && (
        <div className="rounded-card border border-border bg-bg-700 shadow-card">
          <SectionHeader title="Comments" count={comments.length} />
          <div className="space-y-3 px-4 py-4">
            {comments.length === 0 ? (
              <p className="text-2xs text-text-muted">No comments yet.</p>
            ) : (
              <ul className="space-y-2.5">
                {comments.map((c) => (
                  <li
                    key={c.id}
                    className="rounded-control border border-border bg-bg-800/60 px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-2xs text-text-secondary">
                        {shortActor(c.author_user_id)}
                      </span>
                      <span className="font-mono text-2xs text-text-muted">
                        {fmtDateTime(c.created_at)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-text-primary leading-snug">
                      {c.comment}
                    </p>
                  </li>
                ))}
              </ul>
            )}

            <div className="flex flex-col gap-2">
              <textarea
                value={commentDraft}
                onChange={(e) => setCommentDraft(e.target.value)}
                placeholder={
                  canWrite
                    ? "Add a comment…"
                    : "Write-research access is required to comment."
                }
                disabled={!canWrite || busyAction != null}
                rows={2}
                className="w-full rounded border border-border bg-bg-800 px-3 py-2 text-xs text-text-secondary placeholder:text-text-muted/50 focus:outline-none focus:ring-1 focus:ring-accent-500 disabled:cursor-not-allowed disabled:opacity-50"
              />
              <div className="flex justify-end">
                <button
                  onClick={handleAddComment}
                  disabled={
                    !canWrite || busyAction != null || commentDraft.trim() === ""
                  }
                  className="rounded-control border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-600 hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {busyAction === "comment" ? "Working…" : "Add comment"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Decision log (immutable events) */}
      {review && (
        <div className="rounded-card border border-border bg-bg-700 shadow-card">
          <SectionHeader
            title="Decision Log"
            count={events.length}
            right={
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handlePacket("json")}
                  disabled={busyAction != null}
                  className="rounded border border-border bg-bg-600 px-2.5 py-1 font-mono text-2xs text-text-secondary hover:border-border-strong hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busyAction === "packet-json" ? "Working…" : "Packet JSON"}
                </button>
                <button
                  onClick={() => handlePacket("markdown")}
                  disabled={busyAction != null}
                  className="rounded border border-border bg-bg-600 px-2.5 py-1 font-mono text-2xs text-text-secondary hover:border-border-strong hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busyAction === "packet-markdown" ? "Working…" : "Packet MD"}
                </button>
                <button
                  onClick={() => handlePromoPacket("json")}
                  disabled={busyAction != null}
                  className="rounded border border-border bg-bg-600 px-2.5 py-1 font-mono text-2xs text-text-secondary hover:border-border-strong hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busyAction === "promo-packet-json" ? "Working…" : "Promo Packet JSON"}
                </button>
                <button
                  onClick={() => handlePromoPacket("markdown")}
                  disabled={busyAction != null}
                  className="rounded border border-border bg-bg-600 px-2.5 py-1 font-mono text-2xs text-text-secondary hover:border-border-strong hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busyAction === "promo-packet-markdown" ? "Working…" : "Promo Packet MD"}
                </button>
              </div>
            }
          />
          <div className="px-4 py-4">
            {events.length === 0 ? (
              <p className="text-2xs text-text-muted">
                No decision events recorded yet.
              </p>
            ) : (
              <ol className="space-y-2.5">
                {events.map((ev) => (
                  <li key={ev.id} className="flex items-start gap-3">
                    <span className="mt-0.5 font-mono text-2xs text-text-muted whitespace-nowrap tabular-nums">
                      {fmtDateTime(ev.created_at)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs text-text-primary">
                        <span className="font-medium">
                          {statusLabel(ev.action)}
                        </span>{" "}
                        <span className="font-mono text-2xs text-text-muted">
                          by {shortActor(ev.actor_user_id)}
                        </span>
                      </p>
                      {ev.note && (
                        <p className="mt-0.5 text-2xs text-text-secondary leading-snug">
                          {ev.note}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
