import { Link } from "react-router-dom";
import PageHeader from "@/components/PageHeader";

// ---------------------------------------------------------------------------
// Capability row
// ---------------------------------------------------------------------------

interface CapabilityRowProps {
  label: string;
  description: string;
}

function CapabilityRow({ label, description }: CapabilityRowProps) {
  return (
    <div className="flex items-start gap-3 py-2 border-b border-border last:border-b-0">
      <span className="font-mono text-2xs text-cyan-400 mt-0.5 shrink-0 w-28 truncate">
        {label}
      </span>
      <span className="font-mono text-2xs text-text-secondary">{description}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ReviewCases() {
  return (
    <div className="flex flex-col gap-4 px-6 py-6 max-w-3xl mx-auto">
      <PageHeader
        title="Research Review Cases"
        subtitle="Grouped research evidence issues requiring attention"
      />

      {/* Description */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-xs text-text-secondary">
          Review Cases group related alerts, drift findings, and regression failures into
          actionable research governance review packets. Each case aggregates related evidence
          issues for structured acknowledgment and resolution — keeping research governance
          organized and traceable.
        </p>
      </div>

      {/* Access note */}
      <div className="rounded-card border border-amber-700/40 bg-amber-900/10 px-4 py-3 flex items-center justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <p className="font-mono text-2xs text-amber-400 uppercase tracking-wider">Access</p>
          <p className="font-mono text-xs text-text-secondary">
            Generate review cases from Strategy Detail → Research Review Cases.
          </p>
        </div>
        <Link
          to="/strategies"
          className="shrink-0 font-mono text-2xs text-accent-500 hover:text-accent-300 transition-colors"
        >
          Open Strategies →
        </Link>
      </div>

      {/* Capabilities */}
      <div className="rounded-card border border-border bg-bg-700">
        <div className="border-b border-border px-4 py-2.5">
          <p className="font-mono text-2xs text-text-muted uppercase tracking-wider">
            Capabilities
          </p>
        </div>
        <div className="px-4">
          <CapabilityRow
            label="Generate Cases"
            description="Automatically group related alerts, drift findings, and regression failures into review packets for a given strategy."
          />
          <CapabilityRow
            label="Acknowledge"
            description="Mark a review case as acknowledged — logging the acknowledgment to the audit trail."
          />
          <CapabilityRow
            label="Resolve"
            description="Mark a review case as resolved once the underlying evidence issue has been addressed."
          />
          <CapabilityRow
            label="Evidence Grouping"
            description="View all related evidence issues grouped under a single case, including contributing alerts, drift findings, and failed regression checks."
          />
        </div>
      </div>

      {/* Quick links */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-2xs text-text-muted uppercase tracking-wider mb-2">
          Related Pages
        </p>
        <div className="flex flex-wrap gap-4">
          <Link to="/strategies" className="font-mono text-2xs text-accent-500 hover:text-accent-300">
            Strategies →
          </Link>
          <Link to="/alerts" className="font-mono text-2xs text-accent-500 hover:text-accent-300">
            Alerts →
          </Link>
          <Link to="/regression-tests" className="font-mono text-2xs text-accent-500 hover:text-accent-300">
            Regression Tests →
          </Link>
        </div>
      </div>

      {/* Milestone note */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-2xs text-text-muted uppercase tracking-wider mb-1.5">
          Milestone Context
        </p>
        <p className="font-mono text-2xs text-text-secondary">
          Research Review Cases (M55) introduced evidence grouping and structured case
          management for research governance. Cases are generated deterministically from
          existing alerts and findings — no manual categorization required.
        </p>
      </div>

      {/* Footer note */}
      <p className="font-mono text-2xs text-text-muted pb-2">
        This is not an incident system. These are research governance review items.
      </p>
    </div>
  );
}
