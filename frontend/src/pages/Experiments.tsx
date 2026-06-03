import { Link } from "react-router-dom";
import PageHeader from "@/components/PageHeader";

// ---------------------------------------------------------------------------
// Feature card component
// ---------------------------------------------------------------------------

interface FeatureCardProps {
  title: string;
  description: string;
  tag?: string;
}

function FeatureCard({ title, description, tag }: FeatureCardProps) {
  return (
    <div className="rounded-card border border-amber-700/40 bg-amber-900/10 px-4 py-3 flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <p className="font-mono text-xs text-text-primary font-semibold">{title}</p>
        {tag && (
          <span className="font-mono text-2xs border border-amber-700/50 bg-amber-900/20 text-amber-400 rounded px-1.5 py-0.5">
            {tag}
          </span>
        )}
      </div>
      <p className="font-mono text-2xs text-text-secondary">{description}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Experiments() {
  return (
    <div className="flex flex-col gap-4 px-6 py-6 max-w-3xl mx-auto">
      <PageHeader
        title="Experiment Registry"
        subtitle="Parameter sweeps, variant comparison, evidence-quality rankings"
      />

      {/* Description */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-xs text-text-secondary">
          Experiments group related strategy runs for structured comparison. Parameter sweep
          analysis identifies stable and fragile parameter regions across a run set. Variant
          comparison ranks runs by evidence quality, not performance.
        </p>
      </div>

      {/* Access note */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3 flex items-center justify-between gap-4">
        <p className="font-mono text-xs text-text-secondary">
          Open Strategy Detail to access the Experiment Registry for a specific strategy.
        </p>
        <Link
          to="/strategies"
          className="shrink-0 font-mono text-2xs text-accent-500 hover:text-accent-300 transition-colors"
        >
          Open Strategies →
        </Link>
      </div>

      {/* Feature cards */}
      <div className="flex flex-col gap-2">
        <p className="font-mono text-2xs text-text-muted uppercase tracking-wider">
          Available from Strategy Detail
        </p>

        <FeatureCard
          title="Experiment Registry"
          tag="via Strategy Detail"
          description="Create named experiments and add strategy runs as variants. Group related parameter sweeps, variant tests, or configuration comparisons into a single experiment for structured review."
        />

        <FeatureCard
          title="Parameter Sweep Analysis"
          tag="via Strategy Detail"
          description="Analyze parameter sweep results to identify stable regions (consistent evidence quality across parameter range) and fragile regions (evidence quality highly sensitive to parameter values). Not a performance optimizer."
        />

        <FeatureCard
          title="Variant Comparison"
          tag="via Strategy Detail"
          description="Rank experiment variants by evidence-quality signals: signal quality, backtest trust, dataset health, and alert severity. Evidence-based comparison only — not a performance ranking."
        />
      </div>

      {/* M59/M60 milestone note */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-2xs text-text-muted uppercase tracking-wider mb-1.5">
          Milestone Context
        </p>
        <p className="font-mono text-2xs text-text-secondary">
          Experiment Registry (M59) introduced structured experiment grouping. Parameter Sweep
          Analysis (M60) added stability and fragility analysis over parameter ranges. Both
          features are accessible from Strategy Detail pages.
        </p>
      </div>

      {/* Footer note */}
      <p className="font-mono text-2xs text-text-muted pb-2">
        Evidence-based comparison only. Not investment advice.
      </p>
    </div>
  );
}
