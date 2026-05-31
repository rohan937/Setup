import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type {
  BacktestAuditListItem,
  BacktestIssue,
  BacktestStatus,
  CostSensitivityScenario,
} from "@/types";
import { getBacktestAudits } from "@/lib/api";

// ---------------------------------------------------------------------------
// Colour helpers
// ---------------------------------------------------------------------------

function trustColor(score: number): string {
  if (score >= 75) return "text-fidelity-high";
  if (score >= 50) return "text-fidelity-medium";
  return "text-fidelity-low";
}

function statusStyle(status: BacktestStatus): string {
  switch (status) {
    case "excellent":
      return "border-fidelity-high/30 bg-fidelity-high/10 text-fidelity-high";
    case "good":
      return "border-fidelity-high/20 bg-fidelity-high/5 text-fidelity-high";
    case "review":
      return "border-fidelity-medium/30 bg-fidelity-medium/10 text-fidelity-medium";
    case "weak":
      return "border-fidelity-low/30 bg-fidelity-low/10 text-fidelity-low";
    case "unreliable":
      return "border-fidelity-low/50 bg-fidelity-low/20 text-fidelity-low";
  }
}

function severityColor(severity: string): string {
  switch (severity) {
    case "critical":
    case "high":
      return "text-fidelity-low";
    case "medium":
      return "text-fidelity-medium";
    default:
      return "text-text-muted";
  }
}

function severityDot(severity: string): string {
  switch (severity) {
    case "critical":
    case "high":
      return "bg-fidelity-low";
    case "medium":
      return "bg-fidelity-medium";
    default:
      return "bg-text-muted";
  }
}

/** Compact label badge for fragility levels. */
function fragilityBadgeStyle(level: string | null): string {
  switch (level) {
    case "high":
    case "weak":
      return "border-fidelity-low/30 bg-fidelity-low/10 text-fidelity-low";
    case "medium":
    case "review":
      return "border-fidelity-medium/30 bg-fidelity-medium/10 text-fidelity-medium";
    case "low":
    case "strong":
    case "acceptable":
      return "border-fidelity-high/30 bg-fidelity-high/10 text-fidelity-high";
    default:
      return "border-border bg-bg-600 text-text-muted";
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TrustScoreBar({ score }: { score: number }) {
  const bar =
    score >= 75
      ? "bg-fidelity-high"
      : score >= 50
        ? "bg-fidelity-medium"
        : "bg-fidelity-low";
  return (
    <div className="h-1 w-full rounded-full bg-bg-600">
      <div
        className={`h-1 rounded-full transition-all ${bar}`}
        style={{ width: `${score}%` }}
      />
    </div>
  );
}

function IssueChip({ issue }: { issue: BacktestIssue }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-chip border border-border px-2 py-0.5">
      <span className={`h-1.5 w-1.5 rounded-full ${severityDot(issue.severity)}`} />
      <span className={`font-mono text-2xs ${severityColor(issue.severity)}`}>
        {issue.title}
      </span>
    </span>
  );
}

/** Compact cost sensitivity strip: shows 5/10/25/50 bps adjusted Sharpe inline. */
function CostSensitivityStrip({
  scenarios,
  baseSharpe,
}: {
  scenarios: CostSensitivityScenario[];
  baseSharpe: number | null;
}) {
  const tiers = [5, 10, 25, 50];
  const bySharpe: Record<number, number | null> = {};
  for (const s of scenarios) {
    if (tiers.includes(s.cost_bps)) {
      bySharpe[s.cost_bps] = s.adjusted_sharpe;
    }
  }

  const sharpeColor = (v: number | null) => {
    if (v === null) return "text-text-muted";
    if (v < 0) return "text-fidelity-low";
    if (v < 1.0) return "text-fidelity-medium";
    return "text-fidelity-high";
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      {baseSharpe !== null && (
        <span className="font-mono text-2xs text-text-muted">
          base SR{" "}
          <span className="text-text-secondary">{baseSharpe.toFixed(2)}</span>
        </span>
      )}
      {tiers.map((bps) => {
        const v = bySharpe[bps] ?? null;
        return (
          <span key={bps} className="font-mono text-2xs">
            <span className="text-text-muted">{bps}bps→</span>
            <span className={sharpeColor(v)}>
              {v !== null ? v.toFixed(2) : "—"}
            </span>
          </span>
        );
      })}
    </div>
  );
}

function AuditCard({ audit }: { audit: BacktestAuditListItem }) {
  const cs = audit.cost_sensitivity_json;
  const fr = audit.fill_realism_json;
  const hasCsScenarios =
    cs !== null && cs.scenarios.length > 0 && cs.base_sharpe !== null;

  return (
    <div className="rounded-card border border-border bg-bg-700 p-4 space-y-3">
      {/* Header row */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to={`/strategies/${audit.strategy_id}`}
              className="text-sm font-semibold text-text-primary hover:text-accent-300 truncate"
            >
              {audit.strategy_name}
            </Link>
            <span className="text-text-muted font-mono text-2xs">›</span>
            <span className="font-mono text-xs text-text-secondary truncate">
              {audit.run_name}
            </span>
            <span className="rounded-chip border border-border px-1.5 py-0.5 font-mono text-2xs text-text-muted">
              {audit.run_type}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {/* Trust score */}
          <div className="text-right">
            <p className="caption mb-0.5">Trust</p>
            <p className={`mono-num text-xl font-bold leading-none ${trustColor(audit.trust_score)}`}>
              {audit.trust_score}
              <span className="text-xs font-normal text-text-muted">/100</span>
            </p>
          </div>
          {/* Status chip */}
          <span
            className={`rounded-chip border px-2 py-1 font-mono text-xs font-medium ${statusStyle(audit.overall_status)}`}
          >
            {audit.overall_status}
          </span>
        </div>
      </div>

      {/* Trust score bar */}
      <TrustScoreBar score={audit.trust_score} />

      {/* Summary */}
      <p className="text-xs text-text-secondary leading-relaxed">{audit.summary}</p>

      {/* M13: Fragility level chips */}
      {(audit.cost_fragility_level !== null || audit.fill_realism_level !== null) && (
        <div className="flex flex-wrap items-center gap-2">
          {audit.cost_fragility_level !== null && (
            <span
              className={`rounded-chip border px-2 py-0.5 font-mono text-2xs font-medium ${fragilityBadgeStyle(audit.cost_fragility_level)}`}
            >
              cost fragility: {audit.cost_fragility_level}
            </span>
          )}
          {audit.fill_realism_level !== null && (
            <span
              className={`rounded-chip border px-2 py-0.5 font-mono text-2xs font-medium ${fragilityBadgeStyle(audit.fill_realism_level)}`}
            >
              fill: {audit.fill_realism_level}
            </span>
          )}
        </div>
      )}

      {/* M13: Cost sensitivity scenario strip */}
      {hasCsScenarios && (
        <div className="rounded border border-border/50 bg-bg-600/50 px-3 py-2">
          <p className="caption mb-1.5">
            Estimated Sharpe at cost scenarios
            <span className="ml-1 text-text-muted normal-case">(approximate — not a full re-backtest)</span>
          </p>
          <CostSensitivityStrip
            scenarios={cs!.scenarios}
            baseSharpe={cs!.base_sharpe}
          />
        </div>
      )}

      {/* M13: Top fill realism findings */}
      {fr !== null &&
        fr.findings.filter((f) => f.severity !== "low" && f.code !== "missing_slippage").length > 0 && (
          <div className="space-y-1">
            <p className="caption">Fill realism findings</p>
            {fr.findings
              .filter((f) => f.severity !== "low" && f.code !== "missing_slippage")
              .slice(0, 2)
              .map((f, idx) => (
                <div key={idx} className="flex items-start gap-2">
                  <span className={`mt-0.5 h-1.5 w-1.5 flex-shrink-0 rounded-full ${severityDot(f.severity)}`} />
                  <p className={`font-mono text-2xs leading-relaxed ${severityColor(f.severity)}`}>
                    {f.message}
                  </p>
                </div>
              ))}
          </div>
        )}

      {/* Top issues */}
      {audit.top_issues.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {audit.top_issues.map((issue) => (
            <IssueChip key={issue.id} issue={issue} />
          ))}
          {audit.issue_count > 3 && (
            <span className="inline-flex items-center rounded-chip border border-border px-2 py-0.5 font-mono text-2xs text-text-muted">
              +{audit.issue_count - 3} more
            </span>
          )}
        </div>
      )}

      {audit.issue_count === 0 && (
        <p className="font-mono text-2xs text-fidelity-high">✓ No realism concerns detected</p>
      )}

      {/* Subscores */}
      <div className="grid grid-cols-5 gap-2 pt-1 border-t border-border/50">
        {[
          { label: "Cost", value: audit.cost_realism_score },
          { label: "Fill", value: audit.fill_realism_score },
          { label: "Liquidity", value: audit.liquidity_realism_score },
          { label: "Borrow", value: audit.borrow_realism_score },
          { label: "Data", value: audit.data_quality_score },
        ].map(({ label, value }) => (
          <div key={label} className="text-center">
            <p className="caption mb-0.5 truncate">{label}</p>
            <p className={`mono-num text-sm font-semibold ${trustColor(value)}`}>{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function Backtests() {
  const [audits, setAudits] = useState<BacktestAuditListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getBacktestAudits()
      .then(setAudits)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load audits.")
      )
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-text-primary">
          Backtest Audits
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          Deterministic realism checks — cost sensitivity, fill model, borrow
          costs, liquidity assumptions, data quality, and metric plausibility.
          Estimates are approximate and not a substitute for a full re-backtest.
        </p>
      </div>

      {loading && (
        <p className="font-mono text-2xs text-text-muted">Loading audits…</p>
      )}

      {error && (
        <div className="rounded-card border border-fidelity-low/30 bg-fidelity-low/10 px-4 py-3">
          <p className="font-mono text-xs text-fidelity-low">{error}</p>
        </div>
      )}

      {!loading && !error && audits.length === 0 && (
        <div className="rounded-card border border-border bg-bg-700 px-6 py-12 text-center">
          <p className="text-sm font-medium text-text-primary">No audits yet</p>
          <p className="mt-1.5 text-xs text-text-muted max-w-sm mx-auto">
            Open a backtest or research run on the{" "}
            <Link to="/strategies" className="text-accent-300 hover:underline">
              Strategy Lab
            </Link>{" "}
            page and click{" "}
            <span className="font-mono text-2xs text-text-secondary">
              Run Backtest Audit
            </span>{" "}
            to check it for realism.
          </p>
        </div>
      )}

      {!loading && !error && audits.length > 0 && (
        <div className="space-y-4">
          {audits.map((audit) => (
            <AuditCard key={audit.id} audit={audit} />
          ))}
        </div>
      )}
    </div>
  );
}
