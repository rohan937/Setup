import { Link } from "react-router-dom";
import PageHeader from "@/components/PageHeader";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusColor(status: string): string {
  switch (status) {
    case "passed":               return "text-teal-300";
    case "warning":              return "text-amber-400";
    case "failed":               return "text-red-400";
    case "insufficient_evidence":return "text-text-muted";
    default:                     return "text-text-muted";
  }
}

function statusBadgeCls(status: string): string {
  switch (status) {
    case "passed":               return "bg-teal-900/30 text-teal-300 border-teal-700/40";
    case "warning":              return "bg-amber-900/30 text-amber-400 border-amber-700/40";
    case "failed":               return "bg-red-900/30 text-red-400 border-red-700/40";
    case "insufficient_evidence":return "bg-bg-600 text-text-muted border-border";
    default:                     return "bg-bg-600 text-text-muted border-border";
  }
}

// ---------------------------------------------------------------------------
// Default test row
// ---------------------------------------------------------------------------

interface DefaultTestRowProps {
  key_: string;
  label: string;
  description: string;
  exampleStatus: string;
}

function DefaultTestRow({ key_, label, description, exampleStatus }: DefaultTestRowProps) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-border last:border-b-0">
      <div className="flex flex-col gap-0.5 flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm text-text-primary font-medium">{label}</span>
          <span className="font-mono text-2xs text-text-muted">({key_})</span>
        </div>
        <p className="text-sm text-text-secondary">{description}</p>
      </div>
      <span className={`shrink-0 text-xs border rounded-chip px-1.5 py-0.5 ${statusBadgeCls(exampleStatus)}`}>
        {exampleStatus.replace(/_/g, " ")}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const DEFAULT_TESTS: Array<{ key_: string; label: string; description: string; exampleStatus: string }> = [
  {
    key_: "sharpe_drop_limit",
    label: "Sharpe Drop Limit",
    description: "Flags if Sharpe ratio has dropped by more than the configured limit relative to the baseline run.",
    exampleStatus: "passed",
  },
  {
    key_: "drawdown_worsening_limit",
    label: "Drawdown Worsening Limit",
    description: "Flags if max drawdown has worsened beyond the configured threshold relative to the baseline run.",
    exampleStatus: "warning",
  },
  {
    key_: "signal_quality_minimum",
    label: "Signal Quality Minimum",
    description: "Checks that the latest signal snapshot quality score meets the minimum threshold.",
    exampleStatus: "passed",
  },
  {
    key_: "backtest_trust_minimum",
    label: "Backtest Trust Minimum",
    description: "Checks that the backtest audit trust score meets the minimum required for the current stage.",
    exampleStatus: "insufficient_evidence",
  },
  {
    key_: "evidence_coverage_minimum",
    label: "Evidence Coverage Minimum",
    description: "Checks that the evidence coverage percentage meets the minimum coverage threshold.",
    exampleStatus: "passed",
  },
  {
    key_: "no_high_critical_alerts",
    label: "No High / Critical Alerts",
    description: "Fails if there are any open high or critical severity alerts on this strategy.",
    exampleStatus: "failed",
  },
  {
    key_: "readiness_not_blocked",
    label: "Readiness Not Blocked",
    description: "Checks that the strategy readiness status is not in a blocked state.",
    exampleStatus: "passed",
  },
];

export default function RegressionTests() {
  return (
    <div className="flex flex-col gap-4 px-6 py-6 max-w-3xl mx-auto">
      <PageHeader
        title="Regression Test Suite"
        subtitle="Deterministic reliability regression checks"
      />

      {/* Description */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="text-sm text-text-secondary">
          The Regression Test Suite runs deterministic checks on strategy evidence quality
          and reliability signals. A regression is detected when evidence metrics fall below
          configured thresholds or degrade relative to a baseline run. Regressions require
          review — they do not indicate the strategy has failed.
        </p>
      </div>

      {/* Status reference */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="caption mb-2">Status values</p>
        <div className="flex flex-wrap gap-2">
          {["passed", "warning", "failed", "insufficient_evidence"].map((s) => (
            <span key={s} className={`text-xs border rounded-chip px-1.5 py-0.5 ${statusBadgeCls(s)}`}>
              {s.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      </div>

      {/* Default tests */}
      <div className="rounded-card border border-border bg-bg-700">
        <div className="border-b border-border px-4 py-2.5">
          <p className="caption">Default test checks</p>
        </div>
        <div className="px-4">
          {DEFAULT_TESTS.map((t) => (
            <DefaultTestRow
              key={t.key_}
              key_={t.key_}
              label={t.label}
              description={t.description}
              exampleStatus={t.exampleStatus}
            />
          ))}
        </div>
      </div>

      {/* Access note */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3 flex items-center justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <p className="caption mb-0.5">How to access</p>
          <p className="text-sm text-text-secondary">
            Available from Strategy Detail — Regression Test Suite.
          </p>
        </div>
        <Link
          to="/strategies"
          className="shrink-0 text-sm text-accent-500 hover:text-accent-300 transition-colors"
        >
          Open Strategies →
        </Link>
      </div>

      {/* Language note */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="caption mb-2">Terminology</p>
        <ul className="space-y-1.5">
          <li className="flex items-start gap-2">
            <span className="text-text-muted mt-0.5 shrink-0">·</span>
            <span className="text-sm text-text-secondary">
              A test result of <span className={statusColor("failed")}>failed</span> means
              a regression was detected — not that the strategy is unsuitable.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-text-muted mt-0.5 shrink-0">·</span>
            <span className="text-sm text-text-secondary">
              <span className={statusColor("insufficient_evidence")}>Insufficient evidence</span>{" "}
              means the check could not run due to missing data — not a failure.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-text-muted mt-0.5 shrink-0">·</span>
            <span className="text-sm text-text-secondary">
              Regressions require review and may indicate data quality changes, parameter
              instability, or environment drift.
            </span>
          </li>
        </ul>
      </div>

      {/* Footer note */}
      <p className="text-xs text-text-muted pb-2">
        Deterministic research governance only. Not trading approval.
      </p>
    </div>
  );
}
