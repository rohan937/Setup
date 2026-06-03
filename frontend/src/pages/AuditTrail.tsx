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
    <div className="min-h-screen bg-gray-950 px-6 py-6 text-gray-200">
      <PageHeader
        tag="GOVERNANCE"
        title="Quant Research Audit Trail"
        subtitle="Deterministic evidence ledger for strategy lifecycle events"
      />

      {/* Overview card */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-cyan-400">
          About the Evidence Ledger
        </h2>
        <p className="mb-3 text-sm text-gray-400">
          The Audit Trail is a deterministic, append-only evidence ledger that records every
          significant event in a strategy's lifecycle. Each entry is enriched with category,
          importance, research phase, status transitions, and downstream context — providing a
          complete reconstruction of research decisions.
        </p>
        <p className="text-sm text-gray-400">
          Implemented in <span className="font-mono text-cyan-400">M63</span>: enriches{" "}
          <span className="font-mono text-gray-300">AuditTimelineEvent</span> with category,
          importance, research phase, status transitions, and downstream context fields.
        </p>
      </div>

      {/* Research phases */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-cyan-400">
          Research Phases
        </h2>
        <div className="space-y-3">
          {RESEARCH_PHASES.map(({ phase, label, description }, idx) => (
            <div key={phase} className="flex gap-4">
              <div className="flex flex-col items-center">
                <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full border border-gray-600 bg-gray-800 text-xs font-mono text-cyan-400">
                  {idx + 1}
                </div>
                {idx < RESEARCH_PHASES.length - 1 && (
                  <div className="mt-1 w-px flex-1 bg-gray-700" style={{ minHeight: "1rem" }} />
                )}
              </div>
              <div className="pb-3">
                <span className="font-mono text-sm text-gray-200">{label}</span>
                <p className="mt-0.5 text-xs text-gray-500">{description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Enriched fields */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-cyan-400">
          Enriched Event Fields (M63)
        </h2>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {[
            ["category",           "Classification: setup, ingestion, validation, audit, report, governance"],
            ["importance",         "Signal strength: info, low, medium, high, critical"],
            ["research_phase",     "One of the 7 lifecycle phases above"],
            ["status_transition",  "prev_status → new_status for state-changing events"],
            ["downstream_context", "IDs of related artifacts created by this event"],
            ["event_source",       "Origin: api, ci_ingestion, scheduled, manual"],
          ].map(([field, desc]) => (
            <div key={field} className="flex flex-col rounded border border-gray-800 bg-gray-950 p-3">
              <span className="font-mono text-xs text-cyan-400">{field}</span>
              <span className="mt-1 text-xs text-gray-500">{desc}</span>
            </div>
          ))}
        </div>
      </div>

      {/* How to access */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-cyan-400">
          How to Access
        </h2>
        <ul className="space-y-2 text-sm text-gray-400">
          <li className="flex items-start gap-2">
            <span className="mt-0.5 font-mono text-cyan-400">→</span>
            <span>
              Open any strategy in{" "}
              <Link to="/strategies" className="text-cyan-400 underline underline-offset-2 hover:text-cyan-300">
                Strategy Lab
              </Link>{" "}
              and navigate to the <strong className="text-gray-300">Research Audit Trail</strong> tab
              within the Strategy Detail view.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 font-mono text-cyan-400">→</span>
            <span>
              The cross-strategy event feed is available on the{" "}
              <Link to="/timeline" className="text-cyan-400 underline underline-offset-2 hover:text-cyan-300">
                Timeline
              </Link>{" "}
              page (filterable by phase, category, and importance).
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 font-mono text-cyan-400">→</span>
            <span>
              API: <span className="font-mono text-gray-300">GET /api/strategies/{"{id}"}/timeline</span> with{" "}
              <span className="font-mono text-gray-300">research_phase</span>,{" "}
              <span className="font-mono text-gray-300">category</span>, and{" "}
              <span className="font-mono text-gray-300">importance</span> filter params.
            </span>
          </li>
        </ul>
      </div>

      {/* Footer note */}
      <p className="text-xs text-gray-600">
        Audit entries are immutable. Each event is assigned a deterministic ID based on strategy, timestamp, and event type.
        The ledger is not an incident log — it is a complete research evidence record.
      </p>
    </div>
  );
}
