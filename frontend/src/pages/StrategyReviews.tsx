/**
 * Strategy Reviews (M87)
 *
 * Governance manager page listing:
 *   - Pending Reviews (awaiting a reviewer decision)
 *   - the Decision Log (approved / rejected / changes-requested history)
 *
 * Each row links to the owning strategy's Governance tab.
 *
 * Route: /governance/strategy-reviews
 *
 * Research-evidence governance only — not a trading approval.
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { getPendingReviews, getReviewDecisions } from "@/lib/api";
import type { StrategyReview, StrategyReviewStatus } from "@/types";

const REVIEW_STATUS_CHIP: Record<StrategyReviewStatus, string> = {
  draft: "border-border bg-bg-700 text-text-muted",
  submitted: "border-blue-800/50 bg-blue-950/50 text-blue-300",
  approved: "border-teal-800/50 bg-teal-950/50 text-teal-300",
  rejected: "border-red-800/50 bg-red-950/50 text-red-300",
  changes_requested: "border-amber-800/50 bg-amber-950/50 text-amber-300",
  cancelled: "border-border bg-bg-700 text-text-muted",
};

function statusChipClass(s: string): string {
  return (
    REVIEW_STATUS_CHIP[s as StrategyReviewStatus] ??
    "border-border bg-bg-700 text-text-muted"
  );
}

function titleCase(v: string): string {
  return v.replace(/_/g, " ");
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function shortId(id: string | null): string {
  if (!id) return "—";
  return id.length > 8 ? id.slice(0, 8) : id;
}

const TH =
  "px-3 py-2.5 text-left text-2xs font-medium text-text-muted tracking-eyebrow whitespace-nowrap";
const TD = "px-3 py-3 align-top";

export default function StrategyReviews() {
  const navigate = useNavigate();

  const [pending, setPending] = useState<StrategyReview[]>([]);
  const [decisions, setDecisions] = useState<StrategyReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([getPendingReviews(), getReviewDecisions()])
      .then(([p, d]) => {
        setPending(p.items ?? []);
        setDecisions(d.items ?? []);
      })
      .catch((e: unknown) =>
        setError(
          e instanceof Error ? e.message : "Failed to load strategy reviews",
        ),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  function openReview(strategyId: string) {
    navigate(`/strategies/${strategyId}?tab=governance`);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        tag="Governance"
        title="Strategy Reviews"
        subtitle="Pending stage-promotion reviews and the immutable decision log across the portfolio."
      />

      {error && (
        <div className="rounded-control border border-red-800/60 bg-red-950/30 px-4 py-3 text-sm text-red-300">
          <p>{error}</p>
          <button
            onClick={reload}
            className="mt-2 rounded border border-red-700/50 bg-red-900/30 px-2.5 py-1 font-mono text-2xs text-red-200 hover:bg-red-900/50"
          >
            Retry
          </button>
        </div>
      )}

      {loading && (
        <p className="text-xs text-text-muted">Loading strategy reviews…</p>
      )}

      {!loading && !error && (
        <>
          {/* Pending reviews */}
          <div className="rounded-card border border-border bg-bg-700 shadow-card">
            <div className="flex items-center justify-between border-b border-border/70 px-5 py-3">
              <p className="text-sm font-medium text-text-primary">
                Pending Reviews
              </p>
              <span className="font-mono text-2xs text-text-muted">
                {pending.length}
              </span>
            </div>
            {pending.length === 0 ? (
              <div className="px-5 py-10">
                <EmptyState
                  title="No pending reviews"
                  description="Reviews awaiting a decision will appear here. Submit a strategy for review from its Governance tab."
                />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border/60 bg-bg-800/60">
                      <th className={TH}>Strategy</th>
                      <th className={TH}>Target stage</th>
                      <th className={TH}>Status</th>
                      <th className={TH}>Reviewer</th>
                      <th className={TH}>Submitted</th>
                      <th className={TH}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pending.map((r) => (
                      <tr
                        key={r.id}
                        className="border-b border-border/60 last:border-0 transition-colors hover:bg-bg-600/50"
                      >
                        <td className={`${TD} font-mono text-2xs text-text-secondary`}>
                          {shortId(r.strategy_id)}
                        </td>
                        <td className={`${TD} text-xs text-text-secondary whitespace-nowrap`}>
                          {titleCase(r.target_stage)}
                        </td>
                        <td className={TD}>
                          <span
                            className={`inline-flex items-center rounded-chip border px-2 py-0.5 font-mono text-2xs ${statusChipClass(r.status)}`}
                          >
                            {titleCase(r.status)}
                          </span>
                        </td>
                        <td className={`${TD} font-mono text-2xs text-text-muted`}>
                          {shortId(r.reviewer_user_id)}
                        </td>
                        <td className={`${TD} font-mono text-2xs text-text-muted whitespace-nowrap tabular-nums`}>
                          {fmtDate(r.submitted_at)}
                        </td>
                        <td className={TD}>
                          <button
                            onClick={() => openReview(r.strategy_id)}
                            className="font-mono text-2xs text-accent-500 hover:text-accent-300 whitespace-nowrap"
                          >
                            Open →
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Decision log */}
          <div className="rounded-card border border-border bg-bg-700 shadow-card">
            <div className="flex items-center justify-between border-b border-border/70 px-5 py-3">
              <p className="text-sm font-medium text-text-primary">
                Decision Log
              </p>
              <span className="font-mono text-2xs text-text-muted">
                {decisions.length}
              </span>
            </div>
            {decisions.length === 0 ? (
              <div className="px-5 py-10">
                <EmptyState
                  title="No decisions recorded"
                  description="Approved, rejected, and change-requested reviews will appear here once decisions are made."
                />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border/60 bg-bg-800/60">
                      <th className={TH}>Strategy</th>
                      <th className={TH}>Target stage</th>
                      <th className={TH}>Status</th>
                      <th className={TH}>Reviewer</th>
                      <th className={TH}>Decision</th>
                      <th className={TH}>Decided</th>
                      <th className={TH}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {decisions.map((r) => (
                      <tr
                        key={r.id}
                        className="border-b border-border/60 last:border-0 transition-colors hover:bg-bg-600/50"
                      >
                        <td className={`${TD} font-mono text-2xs text-text-secondary`}>
                          {shortId(r.strategy_id)}
                        </td>
                        <td className={`${TD} text-xs text-text-secondary whitespace-nowrap`}>
                          {titleCase(r.target_stage)}
                        </td>
                        <td className={TD}>
                          <span
                            className={`inline-flex items-center rounded-chip border px-2 py-0.5 font-mono text-2xs ${statusChipClass(r.status)}`}
                          >
                            {titleCase(r.status)}
                          </span>
                        </td>
                        <td className={`${TD} font-mono text-2xs text-text-muted`}>
                          {shortId(r.reviewer_user_id)}
                        </td>
                        <td className={`${TD} max-w-[260px]`}>
                          <div className="flex flex-col gap-0.5">
                            <span className="text-xs text-text-secondary">
                              {r.decision ? titleCase(r.decision) : "—"}
                            </span>
                            {r.decision_note && (
                              <span className="text-2xs text-text-muted leading-snug">
                                {r.decision_note}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className={`${TD} font-mono text-2xs text-text-muted whitespace-nowrap tabular-nums`}>
                          {fmtDate(r.decided_at)}
                        </td>
                        <td className={TD}>
                          <button
                            onClick={() => openReview(r.strategy_id)}
                            className="font-mono text-2xs text-accent-500 hover:text-accent-300 whitespace-nowrap"
                          >
                            Open →
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <p className="pb-2 text-center text-2xs text-text-muted">
            Research-evidence governance signals only — not a trading approval or
            investment recommendation.
          </p>
        </>
      )}
    </div>
  );
}
