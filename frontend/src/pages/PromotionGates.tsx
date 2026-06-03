import { Link } from "react-router-dom";
import PageHeader from "@/components/PageHeader";

// ---------------------------------------------------------------------------
// Stage item
// ---------------------------------------------------------------------------

interface StageItemProps {
  index: number;
  label: string;
  description: string;
  isLast?: boolean;
}

function StageItem({ index, label, description, isLast }: StageItemProps) {
  return (
    <div className="flex items-start gap-3">
      <div className="flex flex-col items-center shrink-0">
        <div className="w-6 h-6 rounded-full border border-cyan-700/60 bg-cyan-900/20 flex items-center justify-center">
          <span className="font-mono text-2xs text-cyan-400 font-bold">{index}</span>
        </div>
        {!isLast && (
          <div className="w-px flex-1 min-h-6 bg-border mt-1" />
        )}
      </div>
      <div className="flex flex-col gap-0.5 pb-4 flex-1 min-w-0">
        <p className="font-mono text-xs text-text-primary font-semibold">{label}</p>
        <p className="font-mono text-2xs text-text-secondary">{description}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function PromotionGates() {
  return (
    <div className="flex flex-col gap-4 px-6 py-6 max-w-3xl mx-auto">
      <PageHeader
        title="Promotion Gates"
        subtitle="Stage progression gate checks — research governance, not trading approval"
      />

      {/* Description */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-xs text-text-secondary">
          Promotion Gates run deterministic gate checks before advancing a strategy between
          research stages. Each gate evaluates evidence readiness, reliability scores, and
          governance requirements for the target stage — not trading suitability.
        </p>
      </div>

      {/* Stage progression */}
      <div className="rounded-card border border-border bg-bg-700">
        <div className="border-b border-border px-4 py-2.5">
          <p className="font-mono text-2xs text-text-muted uppercase tracking-wider">
            Stage Progression
          </p>
        </div>
        <div className="px-4 pt-4 pb-2">
          <StageItem
            index={1}
            label="Backtest Review"
            description="Evidence meets minimum quality thresholds: signal quality, dataset health, backtest trust, no blocking alerts."
          />
          <StageItem
            index={2}
            label="Paper Candidate"
            description="Reliability score meets paper candidate minimum, freeze recommendations addressed, regression tests passing."
          />
          <StageItem
            index={3}
            label="Shadow Production"
            description="Config policy guardrails pass, SLA obligations met, evidence coverage sufficient for shadow run."
          />
          <StageItem
            index={4}
            label="Production Candidate"
            description="All prior gates passed, audit trail complete, review cases resolved, readiness status confirmed."
            isLast
          />
        </div>
      </div>

      {/* Access note */}
      <div className="rounded-card border border-amber-700/40 bg-amber-900/10 px-4 py-3 flex items-center justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <p className="font-mono text-2xs text-amber-400 uppercase tracking-wider">Access</p>
          <p className="font-mono text-xs text-text-secondary">
            Evaluate promotion gates from Strategy Detail → Promotion Gates.
          </p>
        </div>
        <Link
          to="/strategies"
          className="shrink-0 font-mono text-2xs text-accent-500 hover:text-accent-300 transition-colors"
        >
          Open Strategies →
        </Link>
      </div>

      {/* Milestone note */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-2xs text-text-muted uppercase tracking-wider mb-1.5">
          Milestone Context
        </p>
        <p className="font-mono text-2xs text-text-secondary">
          Promotion Gates (M51) introduced deterministic stage gate evaluation. Gate checks
          are computed from existing evidence signals — signal quality, reliability scores,
          config policy results, and SLA evaluations. No subjective assessment.
        </p>
      </div>

      {/* Footer note */}
      <p className="font-mono text-2xs text-text-muted pb-2">
        This is evidence-based research governance. Not trading approval.
      </p>
    </div>
  );
}
