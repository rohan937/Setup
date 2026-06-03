import { Link } from "react-router-dom";
import PageHeader from "@/components/PageHeader";

// ---------------------------------------------------------------------------
// Bundle section data
// ---------------------------------------------------------------------------

const BUNDLE_SECTIONS = [
  {
    key: "strategy_version",
    label: "strategy_version",
    description: "Pins the strategy version this bundle targets. Creates a new StrategyVersion record if version_tag is new.",
  },
  {
    key: "config_snapshot",
    label: "config_snapshot",
    description: "Captures the full strategy configuration at the time of the run: parameters, constraints, and universe filters.",
  },
  {
    key: "universe_snapshot",
    label: "universe_snapshot",
    description: "Describes the asset universe used: tickers, benchmark, date range, and selection criteria.",
  },
  {
    key: "signal_snapshot",
    label: "signal_snapshot",
    description: "Records signal definitions, factor weights, and turnover constraints active during the run.",
  },
  {
    key: "dataset",
    label: "dataset",
    description: "Registers the dataset used (name, source, vendor). Creates the dataset record if not already present.",
  },
  {
    key: "dataset_snapshot",
    label: "dataset_snapshot",
    description: "Captures the dataset state at ingestion time: row count, checksum, and date range.",
  },
  {
    key: "strategy_run",
    label: "strategy_run",
    description: "The primary run artifact: run name, run type (backtest/live/paper), and metrics JSON (sharpe, drawdown, etc.).",
  },
] as const;

const ACTIONS = [
  {
    key: "run_backtest_audit",
    label: "run_backtest_audit",
    description: "Generates a BacktestAudit record from the strategy run. Checks for look-ahead bias, overfitting signals, and data leakage.",
  },
  {
    key: "compute_reliability_score",
    label: "compute_reliability_score",
    description: "Computes the StrategyReliabilityScore from evidence coverage, data health, and backtest quality signals.",
  },
  {
    key: "generate_strategy_report",
    label: "generate_strategy_report",
    description: "Generates a strategy report PDF/snapshot based on all current evidence.",
  },
] as const;

const BUNDLE_JSON_EXAMPLE = `{
  "strategy_run": {
    "run_name": "backtest-q1",
    "run_type": "backtest",
    "metrics_json": {
      "sharpe": 1.4,
      "max_drawdown": -0.12
    }
  },
  "actions": {
    "compute_reliability_score": true
  }
}`;

// ---------------------------------------------------------------------------
// EvidenceBundles
// ---------------------------------------------------------------------------

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-cyan-400">
      {children}
    </h2>
  );
}

export default function EvidenceBundles() {
  return (
    <div className="min-h-screen bg-gray-950 px-6 py-6 text-gray-200">
      <PageHeader
        tag="DEVELOPER"
        title="Evidence Bundle Ingestion"
        subtitle="Submit evidence from research pipelines, notebooks, and CI"
      />

      {/* Endpoint */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <SectionHeader>Endpoint</SectionHeader>
        <div className="flex items-center gap-3 rounded border border-gray-700 bg-gray-950 px-4 py-3">
          <span className="rounded bg-cyan-900/40 px-2 py-0.5 text-xs font-semibold text-cyan-400">POST</span>
          <span className="font-mono text-sm text-gray-300">/api/strategies/{"{id}"}/evidence-bundles</span>
        </div>
        <p className="mt-3 text-sm text-gray-400">
          Implemented in <span className="font-mono text-cyan-400">M22</span>. Accepts a composite
          evidence bundle and atomically creates all referenced records before triggering the
          requested post-ingestion actions.
        </p>
      </div>

      {/* Bundle sections */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <SectionHeader>Bundle Sections</SectionHeader>
        <p className="mb-4 text-sm text-gray-400">
          All sections are optional. Include only the sections relevant to your run. The bundle is
          processed atomically — if any section fails validation, no records are created.
        </p>
        <div className="space-y-2">
          {BUNDLE_SECTIONS.map(({ key, label, description }) => (
            <div key={key} className="rounded border border-gray-800 bg-gray-950 p-3">
              <span className="font-mono text-sm text-cyan-400">{label}</span>
              <p className="mt-1 text-xs text-gray-500">{description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Post-ingestion actions */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <SectionHeader>Post-Ingestion Actions</SectionHeader>
        <p className="mb-4 text-sm text-gray-400">
          Pass action flags in the <span className="font-mono text-gray-300">actions</span> object
          to trigger automated follow-up after ingestion:
        </p>
        <div className="space-y-2">
          {ACTIONS.map(({ key, label, description }) => (
            <div key={key} className="rounded border border-gray-800 bg-gray-950 p-3">
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm text-amber-400">{label}</span>
                <span className="rounded bg-amber-900/30 px-1.5 py-0.5 text-xs text-amber-400 border border-amber-700/40">
                  boolean
                </span>
              </div>
              <p className="mt-1 text-xs text-gray-500">{description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Minimal example */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <SectionHeader>Minimal Bundle Example</SectionHeader>
        <pre className="overflow-x-auto rounded border border-gray-700 bg-gray-950 p-4 text-xs font-mono text-gray-300 leading-relaxed">
          <code>{BUNDLE_JSON_EXAMPLE}</code>
        </pre>
      </div>

      {/* Idempotency */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <SectionHeader>Idempotency</SectionHeader>
        <p className="text-sm text-gray-400">
          Pass an <span className="font-mono text-gray-300">Idempotency-Key</span> header or set{" "}
          <span className="font-mono text-gray-300">QUANTFIDELITY_IDEMPOTENCY_KEY</span> to safely
          retry failed ingestion requests. Duplicate bundles with the same key return the original
          response without creating duplicate records.
        </p>
      </div>

      {/* Note */}
      <div className="mb-6 rounded-lg border border-amber-700/30 bg-amber-900/10 p-4 text-sm text-amber-300">
        For the interactive ingestion panel, open{" "}
        <strong>Strategy Detail → Evidence Bundle Ingestion</strong> in any strategy. The panel
        provides a form-based interface for all bundle sections and actions.
      </div>

      {/* Links */}
      <div className="flex flex-wrap gap-3">
        <Link
          to="/developer/sdk"
          className="rounded border border-gray-700 bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:border-cyan-700 hover:text-cyan-400"
        >
          SDK & CI Integration
        </Link>
        <Link
          to="/strategies"
          className="rounded border border-gray-700 bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:border-cyan-700 hover:text-cyan-400"
        >
          Strategy Lab
        </Link>
      </div>
    </div>
  );
}
