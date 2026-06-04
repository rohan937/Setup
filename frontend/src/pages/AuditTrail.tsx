import { Link } from "react-router-dom";
import PageHeader from "@/components/PageHeader";

// ---------------------------------------------------------------------------
// Research phases
// ---------------------------------------------------------------------------

const RESEARCH_PHASES = [
  { phase: "setup",              label: "Setup",              description: "Strategy creation, initial configuration, and project assignment." },
  { phase: "evidence_logging",   label: "Evidence Logging",   description: "Ingestion of datasets, signal snapshots, config snapshots, and universe snapshots." },
  { phase: "backtest_review",    label: "Backtest Review",    description: "Strategy run ingestion, backtest audit generation, and metric validation." },
  { phase: "quality_review",     label: "Quality Review",     description: "Data health checks, assumption validation, and evidence coverage scoring." },
  { phase: "progression_review", label: "Progression Review", description: "Reliability score computation, freeze recommendations, and gate evaluation." },
  { phase: "governance_review",  label: "Governance Review",  description: "Promotion gate decisions, policy compliance, and review case resolution." },
  { phase: "reporting",          label: "Reporting",          description: "Strategy report generation, export, and audit snapshot finalization." },
] as const;

// ---------------------------------------------------------------------------
// AuditTrail
// ---------------------------------------------------------------------------

export default function AuditTrail() {
  return (
    <div className="flex flex-col gap-4 px-6 py-6 max-w-3xl mx-auto">
      <PageHeader
        tag="GOVERNANCE"
        title="Quant Research Audit Trail"
        subtitle="Deterministic evidence ledger for strategy lifecycle events"
      />

      {/* Overview card */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-4">
        <h2 className="text-sm font-semibold text-text-primary mb-2">About the evidence ledger</h2>
        <p className="text-sm text-text-secondary mb-2">
          The Audit Trail is a deterministic, append-only evidence ledger that records every
          significant event in a strategy's lifecycle. Each entry is enriched with category,
          importance, research phase, status transitions, and downstream context — providing a
          complete reconstruction of research decisions.
        </p>
        <p className="text-sm text-text-secondary">
          Implemented in M63: enriches{" "}
          <span className="font-mono text-text-primary">AuditTimelineEvent</span> with category,
          importance, research phase, status transitions, and downstream context fields.
        </p>
      </div>

      {/* Research phases */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-4">
        <h2 className="text-sm font-semibold text-text-primary mb-4">Research phases</h2>
        <div className="space-y-0">
          {RESEARCH_PHASES.map(({ phase, label, description }, idx) => (
            <div key={phase} className="flex gap-4">
              <div className="flex flex-col items-center">
                <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full border border-border bg-bg-600 font-mono text-2xs text-text-secondary">
                  {idx + 1}
                </div>
                {idx < RESEARCH_PHASES.length - 1 && (
                  <div className="mt-1 w-px flex-1 bg-border" style={{ minHeight: "1rem" }} />
                )}
              </div>
              <div className="pb-3 min-w-0">
                <span className="text-sm font-medium text-text-primary">{label}</span>
                <p className="mt-0.5 text-sm text-text-muted">{description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Enriched fields */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-4">
        <h2 className="text-sm font-semibold text-text-primary mb-3">Enriched event fields (M63)</h2>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {[
            ["category",           "Classification: setup, ingestion, validation, audit, report, governance"],
            ["importance",         "Signal strength: info, low, medium, high, critical"],
            ["research_phase",     "One of the 7 lifecycle phases above"],
            ["status_transition",  "prev_status → new_status for state-changing events"],
            ["downstream_context", "IDs of related artifacts created by this event"],
            ["event_source",       "Origin: api, ci_ingestion, scheduled, manual"],
          ].map(([field, desc]) => (
            <div key={field} className="flex flex-col rounded-control border border-border bg-bg-800 p-3">
              <span className="font-mono text-xs text-accent-500">{field}</span>
              <span className="mt-1 text-sm text-text-muted">{desc}</span>
            </div>
          ))}
        </div>
      </div>

      {/* How to access */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-4">
        <h2 className="text-sm font-semibold text-text-primary mb-3">How to access</h2>
        <ul className="space-y-2.5">
          <li className="flex items-start gap-2">
            <span className="mt-0.5 text-text-muted shrink-0">→</span>
            <span className="text-sm text-text-secondary">
              Open any strategy in{" "}
              <Link to="/strategies" className="text-accent-500 hover:text-accent-300 underline underline-offset-2">
                Strategy Lab
              </Link>{" "}
              and navigate to the <strong className="text-text-primary font-medium">Research Audit Trail</strong> tab
              within the Strategy Detail view.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 text-text-muted shrink-0">→</span>
            <span className="text-sm text-text-secondary">
              The cross-strategy event feed is available on the{" "}
              <Link to="/timeline" className="text-accent-500 hover:text-accent-300 underline underline-offset-2">
                Timeline
              </Link>{" "}
              page (filterable by phase, category, and importance).
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 text-text-muted shrink-0">→</span>
            <span className="text-sm text-text-secondary">
              API:{" "}
              <span className="font-mono text-text-primary text-xs">GET /api/strategies/{"{id}"}/timeline</span>
              {" "}with{" "}
              <span className="font-mono text-text-primary text-xs">research_phase</span>,{" "}
              <span className="font-mono text-text-primary text-xs">category</span>, and{" "}
              <span className="font-mono text-text-primary text-xs">importance</span> filter params.
            </span>
          </li>
        </ul>
      </div>

      {/* Footer note */}
      <p className="text-xs text-text-muted pb-2">
        Audit entries are immutable. Each event is assigned a deterministic ID based on strategy, timestamp, and event type.
        The ledger is not an incident log — it is a complete research evidence record.
      </p>
    </div>
  );
}
