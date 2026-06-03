import { Link } from "react-router-dom";
import PageHeader from "@/components/PageHeader";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusBadgeCls(status: string): string {
  switch (status) {
    case "passed": return "bg-cyan-900/30 text-cyan-400 border-cyan-700/40";
    case "warning": return "bg-amber-900/30 text-amber-400 border-amber-700/40";
    case "violated": return "bg-red-900/30 text-red-400 border-red-700/40";
    case "skipped": return "bg-bg-600 text-text-muted border-border";
    default: return "bg-bg-600 text-text-muted border-border";
  }
}

// ---------------------------------------------------------------------------
// SLA rule row
// ---------------------------------------------------------------------------

interface SLARuleRowProps {
  label: string;
  threshold: string;
  description: string;
  exampleStatus: string;
}

function SLARuleRow({ label, threshold, description, exampleStatus }: SLARuleRowProps) {
  return (
    <div className="flex flex-col gap-1 py-2.5 border-b border-border last:border-b-0">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <span className="font-mono text-xs text-text-primary font-semibold truncate">{label}</span>
          <span className="font-mono text-2xs border border-border bg-bg-600 text-text-muted rounded px-1.5 py-0.5 shrink-0">
            {threshold}
          </span>
        </div>
        <span className={`shrink-0 font-mono text-2xs border rounded px-1.5 py-0.5 ${statusBadgeCls(exampleStatus)}`}>
          {exampleStatus}
        </span>
      </div>
      <p className="font-mono text-2xs text-text-secondary">{description}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SLA rules
// ---------------------------------------------------------------------------

const SLA_RULES: SLARuleRowProps[] = [
  {
    label: "Signal Snapshot Freshness",
    threshold: "≤30 days",
    description: "The most recent signal snapshot must be no older than 30 days to ensure signal evidence is current.",
    exampleStatus: "passed",
  },
  {
    label: "Dataset Health Score",
    threshold: "≥75",
    description: "The dataset health score must meet the minimum threshold. Scores below this indicate data quality obligations are not met.",
    exampleStatus: "warning",
  },
  {
    label: "Backtest Trust Score",
    threshold: "≥70",
    description: "The backtest audit trust score must meet the minimum for evidence to be considered reliable.",
    exampleStatus: "passed",
  },
  {
    label: "No High / Critical Alerts",
    threshold: "0 open",
    description: "No open alerts of high or critical severity. Open high/critical alerts constitute an evidence obligation violation.",
    exampleStatus: "violated",
  },
];

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function SLAMonitor() {
  return (
    <div className="flex flex-col gap-4 px-6 py-6 max-w-3xl mx-auto">
      <PageHeader
        title="Evidence SLA Monitor"
        subtitle="Track evidence freshness and quality obligations"
      />

      {/* Description */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-xs text-text-secondary">
          SLA policies define evidence freshness and quality obligations that a strategy
          must maintain. An SLA violation means an evidence obligation has not been met —
          the signal snapshot is stale, the dataset health has degraded, or blocking alerts
          are unresolved. SLA violations require review, not automatic disqualification.
        </p>
      </div>

      {/* Status reference */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-2xs text-text-muted uppercase tracking-wider mb-2">
          Status Values
        </p>
        <div className="flex flex-wrap gap-2">
          {["passed", "warning", "violated", "skipped"].map((s) => (
            <span key={s} className={`font-mono text-2xs border rounded px-1.5 py-0.5 ${statusBadgeCls(s)}`}>
              {s}
            </span>
          ))}
        </div>
      </div>

      {/* Default SLA rules */}
      <div className="rounded-card border border-border bg-bg-700">
        <div className="border-b border-border px-4 py-2.5">
          <p className="font-mono text-2xs text-text-muted uppercase tracking-wider">
            Default SLA Rules
          </p>
        </div>
        <div className="px-4">
          {SLA_RULES.map((rule) => (
            <SLARuleRow key={rule.label} {...rule} />
          ))}
        </div>
      </div>

      {/* Access note */}
      <div className="rounded-card border border-amber-700/40 bg-amber-900/10 px-4 py-3 flex items-center justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <p className="font-mono text-2xs text-amber-400 uppercase tracking-wider">Access</p>
          <p className="font-mono text-xs text-text-secondary">
            Access from Strategy Detail → Evidence SLA Monitor.
          </p>
        </div>
        <Link
          to="/strategies"
          className="shrink-0 font-mono text-2xs text-accent-500 hover:text-accent-300 transition-colors"
        >
          Open Strategies →
        </Link>
      </div>

      {/* Language note */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-2xs text-text-muted uppercase tracking-wider mb-1.5">
          Terminology
        </p>
        <ul className="space-y-1">
          <li className="flex items-start gap-2">
            <span className="font-mono text-2xs text-cyan-400 mt-0.5 shrink-0">·</span>
            <span className="font-mono text-2xs text-text-secondary">
              An SLA violation means an evidence obligation has not been met — not a system
              incident or trading failure.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="font-mono text-2xs text-cyan-400 mt-0.5 shrink-0">·</span>
            <span className="font-mono text-2xs text-text-secondary">
              Skipped SLAs indicate the required evidence artifact is missing — the check
              could not be evaluated.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="font-mono text-2xs text-cyan-400 mt-0.5 shrink-0">·</span>
            <span className="font-mono text-2xs text-text-secondary">
              Custom SLA policies can be configured per-strategy in Strategy Detail.
            </span>
          </li>
        </ul>
      </div>

      {/* Related pages */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-2xs text-text-muted uppercase tracking-wider mb-2">
          Related Pages
        </p>
        <div className="flex flex-wrap gap-4">
          <Link to="/alerts" className="font-mono text-2xs text-accent-500 hover:text-accent-300">
            Alerts →
          </Link>
          <Link to="/data-health" className="font-mono text-2xs text-accent-500 hover:text-accent-300">
            Data Health →
          </Link>
          <Link to="/evidence/coverage" className="font-mono text-2xs text-accent-500 hover:text-accent-300">
            Evidence Matrix →
          </Link>
        </div>
      </div>

      {/* Milestone note */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-2xs text-text-muted uppercase tracking-wider mb-1.5">
          Milestone Context
        </p>
        <p className="font-mono text-2xs text-text-secondary">
          Evidence SLA Monitor (M56) introduced freshness and quality obligation tracking.
          SLA evaluations are computed against the current evidence snapshot — signal
          freshness, dataset health, backtest trust, and open alert state.
        </p>
      </div>

      {/* Footer note */}
      <p className="font-mono text-2xs text-text-muted pb-2">
        Evidence obligations only. Not an incident monitoring system.
      </p>
    </div>
  );
}
