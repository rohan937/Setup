import { Link } from "react-router-dom";
import PageHeader from "@/components/PageHeader";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusBadgeCls(status: string): string {
  switch (status) {
    case "passed": return "bg-cyan-900/30 text-cyan-400 border-cyan-700/40";
    case "warning": return "bg-amber-900/30 text-amber-400 border-amber-700/40";
    case "failed": return "bg-red-900/30 text-red-400 border-red-700/40";
    case "skipped": return "bg-bg-600 text-text-muted border-border";
    default: return "bg-bg-600 text-text-muted border-border";
  }
}

// ---------------------------------------------------------------------------
// Policy rule row
// ---------------------------------------------------------------------------

interface PolicyRuleRowProps {
  label: string;
  description: string;
  exampleStatus: string;
  rationale: string;
}

function PolicyRuleRow({ label, description, exampleStatus, rationale }: PolicyRuleRowProps) {
  return (
    <div className="flex flex-col gap-1 py-2.5 border-b border-border last:border-b-0">
      <div className="flex items-start justify-between gap-3">
        <span className="font-mono text-xs text-text-primary font-semibold">{label}</span>
        <span className={`shrink-0 font-mono text-2xs border rounded px-1.5 py-0.5 ${statusBadgeCls(exampleStatus)}`}>
          {exampleStatus}
        </span>
      </div>
      <p className="font-mono text-2xs text-text-secondary">{description}</p>
      <p className="font-mono text-2xs text-text-muted italic">{rationale}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Policy rules
// ---------------------------------------------------------------------------

const POLICY_RULES: PolicyRuleRowProps[] = [
  {
    label: "Transaction Cost Required",
    description: "Strategy configuration must include a non-zero transaction cost assumption.",
    exampleStatus: "passed",
    rationale: "Prevents unrealistic cost-free backtest assumptions.",
  },
  {
    label: "Fill Model: No Same-Close Execution",
    description: "Fill model must not use same-close or lookahead execution that is not achievable live.",
    exampleStatus: "warning",
    rationale: "Same-close fills introduce forward-looking bias in backtests.",
  },
  {
    label: "Borrow Cost Required When Shorting",
    description: "When shorting is enabled, a borrow cost rate must be specified in the config.",
    exampleStatus: "passed",
    rationale: "Short strategies without borrow cost understate funding costs.",
  },
  {
    label: "Max Leverage Limit",
    description: "Configured leverage must not exceed 2x. Strategies requiring higher leverage trigger this guardrail.",
    exampleStatus: "failed",
    rationale: "Leverage above 2x increases tail risk; requires explicit review.",
  },
  {
    label: "Liquidity Filter Recommended",
    description: "Strategy configuration is expected to include a liquidity filter or universe constraint.",
    exampleStatus: "warning",
    rationale: "Trading illiquid instruments without a filter degrades fill assumptions.",
  },
];

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Policies() {
  return (
    <div className="flex flex-col gap-4 px-6 py-6 max-w-3xl mx-auto">
      <PageHeader
        title="Config Policy Guardrails"
        subtitle="Deterministic assumption guardrails for strategy configs"
      />

      {/* Description */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-xs text-text-secondary">
          Config Policy Guardrails enforce deterministic assumption checks on strategy
          configuration. Policies identify assumption violations — incorrect cost models,
          fill assumptions, leverage limits, and liquidity constraints — before they
          propagate into backtest results. A policy violation requires review, not
          automatic rejection.
        </p>
      </div>

      {/* Status reference */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-2xs text-text-muted uppercase tracking-wider mb-2">
          Status Values
        </p>
        <div className="flex flex-wrap gap-2">
          {["passed", "warning", "failed", "skipped"].map((s) => (
            <span key={s} className={`font-mono text-2xs border rounded px-1.5 py-0.5 ${statusBadgeCls(s)}`}>
              {s}
            </span>
          ))}
        </div>
      </div>

      {/* Default policy rules */}
      <div className="rounded-card border border-border bg-bg-700">
        <div className="border-b border-border px-4 py-2.5">
          <p className="font-mono text-2xs text-text-muted uppercase tracking-wider">
            Default Policy Rules
          </p>
        </div>
        <div className="px-4">
          {POLICY_RULES.map((rule) => (
            <PolicyRuleRow key={rule.label} {...rule} />
          ))}
        </div>
      </div>

      {/* Access note */}
      <div className="rounded-card border border-amber-700/40 bg-amber-900/10 px-4 py-3 flex items-center justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <p className="font-mono text-2xs text-amber-400 uppercase tracking-wider">Access</p>
          <p className="font-mono text-xs text-text-secondary">
            Access from Strategy Detail → Config Policy Guardrails.
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
              A policy violation means an assumption guardrail was breached — not that the
              strategy is incorrect.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="font-mono text-2xs text-cyan-400 mt-0.5 shrink-0">·</span>
            <span className="font-mono text-2xs text-text-secondary">
              Skipped policies indicate missing config fields — the check could not be
              evaluated, not that the policy passed.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="font-mono text-2xs text-cyan-400 mt-0.5 shrink-0">·</span>
            <span className="font-mono text-2xs text-text-secondary">
              Custom policies can be added per-strategy in Strategy Detail.
            </span>
          </li>
        </ul>
      </div>

      {/* Milestone note */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
        <p className="font-mono text-2xs text-text-muted uppercase tracking-wider mb-1.5">
          Milestone Context
        </p>
        <p className="font-mono text-2xs text-text-secondary">
          Config Policy Guardrails (M54) introduced deterministic enforcement of cost, fill,
          leverage, borrow, and liquidity assumptions. Policies evaluate against the strategy
          config snapshot — no external data required.
        </p>
      </div>

      {/* Footer note */}
      <p className="font-mono text-2xs text-text-muted pb-2">
        Assumption guardrails only. Not investment compliance or regulatory review.
      </p>
    </div>
  );
}
