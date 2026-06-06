import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import PageHeader from "@/components/PageHeader";
import Button from "@/components/Button";
import EvidenceBundleUploader from "@/components/EvidenceBundleUploader";
import { getStrategies } from "@/lib/api";
import type { Strategy } from "@/types";

// ---------------------------------------------------------------------------
// Bundle section data
// ---------------------------------------------------------------------------

const BUNDLE_SECTIONS = [
  {
    key: "strategy_version",
    label: "strategy_version",
    description:
      "Pins the strategy version this bundle targets. Creates a new StrategyVersion record if version_tag is new.",
  },
  {
    key: "config_snapshot",
    label: "config_snapshot",
    description:
      "Captures the full strategy configuration at the time of the run: parameters, constraints, and universe filters.",
  },
  {
    key: "universe_snapshot",
    label: "universe_snapshot",
    description:
      "Describes the asset universe used: tickers, benchmark, date range, and selection criteria.",
  },
  {
    key: "signal_snapshot",
    label: "signal_snapshot",
    description:
      "Records signal definitions, factor weights, and turnover constraints active during the run.",
  },
  {
    key: "dataset",
    label: "dataset",
    description:
      "Registers the dataset used (name, source, vendor). Creates the dataset record if not already present.",
  },
  {
    key: "dataset_snapshot",
    label: "dataset_snapshot",
    description:
      "Captures the dataset state at ingestion time: row count, checksum, and date range.",
  },
  {
    key: "strategy_run",
    label: "strategy_run",
    description:
      "The primary run artifact: run name, run type (backtest/live/paper), and metrics JSON (sharpe, drawdown, etc.).",
  },
] as const;

const ACTIONS = [
  {
    key: "run_backtest_audit",
    label: "run_backtest_audit",
    description:
      "Generates a BacktestAudit record from the strategy run. Checks for look-ahead bias, overfitting signals, and data leakage.",
  },
  {
    key: "compute_reliability_score",
    label: "compute_reliability_score",
    description:
      "Computes the StrategyReliabilityScore from evidence coverage, data health, and backtest quality signals.",
  },
  {
    key: "generate_strategy_report",
    label: "generate_strategy_report",
    description:
      "Generates a strategy report PDF/snapshot based on all current evidence.",
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

const SDK_SNIPPET = `import quantfidelity as qf

client = qf.Client(api_key=os.environ["QF_API_KEY"])
client.strategies.ingest_bundle(
    strategy_id="<id>",
    bundle=bundle_dict,
    idempotency_key=run_id,
)`;

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 text-sm font-semibold tracking-tight text-text-primary">
      {children}
    </h2>
  );
}

function RefCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-border bg-bg-800 p-5 shadow-card">
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// EvidenceBundles
// ---------------------------------------------------------------------------

export default function EvidenceBundles() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);

  useEffect(() => {
    getStrategies()
      .then(setStrategies)
      .catch(() => {
        // non-fatal: uploader still renders, just with an empty selector
      });
  }, []);

  return (
    <div className="min-h-screen bg-bg-950 px-6 py-6 text-text-primary">
      <PageHeader
        tag="Developer"
        title="Evidence Bundle Ingestion"
        subtitle="Submit evidence from research pipelines, notebooks, and CI. Use the web uploader for manual runs and demos; use the SDK or REST API for automated pipelines."
      />

      {/* ------------------------------------------------------------------ */}
      {/* Dual-path callout                                                   */}
      {/* ------------------------------------------------------------------ */}
      <div className="mb-8 grid gap-3 sm:grid-cols-3">
        {/* Path A: web */}
        <div className="rounded-card border border-border bg-bg-800 p-4">
          <p className="mb-1 text-xs font-semibold tracking-tight text-text-primary">
            Web upload
          </p>
          <p className="text-xs leading-relaxed text-text-secondary">
            Manual ingestion for research, notebooks, and demos. Select a
            strategy, paste or drag in a JSON bundle, preview sections, then
            ingest in one click.
          </p>
        </div>
        {/* Path B: SDK / CI */}
        <div className="rounded-card border border-border bg-bg-800 p-4">
          <p className="mb-1 text-xs font-semibold tracking-tight text-text-primary">
            Terminal / SDK / CI
          </p>
          <p className="text-xs leading-relaxed text-text-secondary">
            Automated ingestion from your pipeline. Use the Python SDK or
            call the REST endpoint directly. Pass an{" "}
            <span className="font-mono text-text-primary">
              Idempotency-Key
            </span>{" "}
            header for safe retries.
          </p>
        </div>
        {/* Path C: No-code Builder */}
        <div className="rounded-card border border-border bg-bg-800 p-4">
          <p className="mb-1 text-xs font-semibold tracking-tight text-text-primary">
            No-code Builder
          </p>
          <p className="text-xs leading-relaxed text-text-secondary mb-3">
            Build a complete evidence bundle step-by-step without writing JSON. Select strategy,
            enter metrics, upload CSVs, preview, and ingest in one flow.
          </p>
          <Link
            to="/developer/evidence-builder"
            className="inline-flex items-center gap-1.5 rounded-control border border-accent-500/40 bg-accent-500/10 px-3 py-1.5 text-xs font-semibold text-accent-500 hover:bg-accent-500/20 transition-colors"
          >
            Open Builder →
          </Link>
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Web uploader                                                         */}
      {/* ------------------------------------------------------------------ */}
      <div className="mb-10 rounded-card border border-border bg-bg-800 p-6 shadow-card">
        <div className="mb-5">
          <h2 className="text-base font-semibold tracking-tight text-text-primary">
            Web Upload
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-text-secondary">
            Select a strategy, load or paste your bundle JSON, validate, then
            ingest. All sections are optional — include only what your run
            produced.
          </p>
        </div>
        <EvidenceBundleUploader
          strategies={strategies.map((s) => ({ id: s.id, name: s.name }))}
          onIngested={() => {
            // page-level refetch: re-fetch strategies list so selector stays fresh
            getStrategies().then(setStrategies).catch(() => {});
          }}
        />
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Reference documentation                                              */}
      {/* ------------------------------------------------------------------ */}
      <div className="space-y-5">

        {/* Endpoint */}
        <RefCard>
          <SectionTitle>REST Endpoint</SectionTitle>
          <div className="flex items-center gap-3 rounded-control border border-border bg-bg-900 px-4 py-3">
            <span className="rounded-chip border border-brand/50 bg-brand/10 px-2 py-0.5 font-mono text-2xs font-semibold text-brand">
              POST
            </span>
            <span className="font-mono text-sm text-text-primary">
              /api/strategies/{"{id}"}/evidence-bundles
            </span>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-text-secondary">
            Accepts a composite evidence bundle and atomically creates all
            referenced records before triggering the requested post-ingestion
            actions.
          </p>
        </RefCard>

        {/* SDK snippet */}
        <RefCard>
          <SectionTitle>SDK Usage (Python)</SectionTitle>
          <pre className="overflow-x-auto rounded-control border border-border bg-bg-900 p-4 font-mono text-xs leading-relaxed text-text-secondary">
            <code>{SDK_SNIPPET}</code>
          </pre>
          <p className="mt-3 text-xs text-text-muted">
            Full SDK reference and CI integration guide in{" "}
            <Link
              to="/developer/sdk"
              className="text-text-secondary underline underline-offset-2 hover:text-text-primary"
            >
              SDK &amp; CI Integration
            </Link>
            .
          </p>
        </RefCard>

        {/* Bundle sections */}
        <RefCard>
          <SectionTitle>Bundle Sections</SectionTitle>
          <p className="mb-4 text-xs leading-relaxed text-text-secondary">
            All sections are optional. Include only the sections relevant to
            your run. The bundle is processed atomically — if any section fails
            validation, no records are created.
          </p>
          <div className="space-y-2">
            {BUNDLE_SECTIONS.map(({ key, label, description }) => (
              <div
                key={key}
                className="rounded-control border border-border bg-bg-900 px-3 py-2.5"
              >
                <span className="font-mono text-xs text-text-primary">
                  {label}
                </span>
                <p className="mt-0.5 text-xs leading-relaxed text-text-muted">
                  {description}
                </p>
              </div>
            ))}
          </div>
        </RefCard>

        {/* Post-ingestion actions */}
        <RefCard>
          <SectionTitle>Post-Ingestion Actions</SectionTitle>
          <p className="mb-4 text-xs leading-relaxed text-text-secondary">
            Pass action flags in the{" "}
            <span className="font-mono text-text-primary">actions</span> object
            to trigger automated follow-up after ingestion:
          </p>
          <div className="space-y-2">
            {ACTIONS.map(({ key, label, description }) => (
              <div
                key={key}
                className="rounded-control border border-border bg-bg-900 px-3 py-2.5"
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-text-primary">
                    {label}
                  </span>
                  <span className="rounded-chip border border-border px-1.5 py-0.5 font-mono text-2xs text-text-muted">
                    boolean
                  </span>
                </div>
                <p className="mt-0.5 text-xs leading-relaxed text-text-muted">
                  {description}
                </p>
              </div>
            ))}
          </div>
        </RefCard>

        {/* Minimal example */}
        <RefCard>
          <SectionTitle>Minimal Bundle Example</SectionTitle>
          <pre className="overflow-x-auto rounded-control border border-border bg-bg-900 p-4 font-mono text-xs leading-relaxed text-text-secondary">
            <code>{BUNDLE_JSON_EXAMPLE}</code>
          </pre>
        </RefCard>

        {/* Idempotency */}
        <RefCard>
          <SectionTitle>Idempotency</SectionTitle>
          <p className="text-xs leading-relaxed text-text-secondary">
            Pass an{" "}
            <span className="font-mono text-text-primary">
              Idempotency-Key
            </span>{" "}
            header or set{" "}
            <span className="font-mono text-text-primary">
              QUANTFIDELITY_IDEMPOTENCY_KEY
            </span>{" "}
            to safely retry failed ingestion requests. Duplicate bundles with
            the same key return the original response without creating duplicate
            records.
          </p>
        </RefCard>

        {/* Security note */}
        <div className="rounded-card border border-border bg-bg-800 px-4 py-3">
          <p className="text-xs leading-relaxed text-text-secondary">
            <span className="font-medium text-text-primary">Security note.</span>{" "}
            All ingestion requests are authenticated and subject to workspace
            RBAC. API keys with{" "}
            <span className="font-mono text-text-primary">ingest:write</span>{" "}
            permission are required for programmatic access. Bundle JSON is
            parsed as data only — never evaluated.
          </p>
        </div>

      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Footer links                                                         */}
      {/* ------------------------------------------------------------------ */}
      <div className="mt-8 flex flex-wrap gap-2">
        <Link to="/developer/sdk">
          <Button variant="secondary" size="sm">
            SDK &amp; CI Integration
          </Button>
        </Link>
        <Link to="/developer/evidence-builder">
          <Button variant="secondary" size="sm">Bundle Builder</Button>
        </Link>
        <Link to="/strategies">
          <Button variant="ghost" size="sm">
            Strategy Lab
          </Button>
        </Link>
        <Link to="/audit-trail">
          <Button variant="ghost" size="sm">
            Audit Trail
          </Button>
        </Link>
      </div>
    </div>
  );
}
