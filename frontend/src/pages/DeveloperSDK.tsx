import { Link } from "react-router-dom";
import PageHeader from "@/components/PageHeader";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function CodeBlock({ children, lang = "bash" }: { children: string; lang?: string }) {
  return (
    <pre className="overflow-x-auto rounded-control border border-border bg-bg-800 p-4 text-xs font-mono text-text-secondary leading-relaxed">
      <code data-lang={lang}>{children}</code>
    </pre>
  );
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 text-sm font-semibold text-text-primary">{children}</h2>
  );
}

// ---------------------------------------------------------------------------
// Env vars table data
// ---------------------------------------------------------------------------

const ENV_VARS = [
  {
    name: "QUANTFIDELITY_BASE_URL",
    default: "http://localhost:8000",
    description: "Base URL of the QuantFidelity API server.",
  },
  {
    name: "QUANTFIDELITY_API_KEY",
    default: "(none)",
    description: "API key for authenticated endpoints. Create one in Settings.",
  },
  {
    name: "QF_API_KEY",
    default: "(none)",
    description: "Short alias for QUANTFIDELITY_API_KEY. Both are supported.",
  },
  {
    name: "QF_BASE_URL",
    default: "(none)",
    description: "Short alias for QUANTFIDELITY_BASE_URL. Both are supported.",
  },
  {
    name: "QUANTFIDELITY_STRATEGY_ID",
    default: "(none)",
    description: "Default strategy UUID used by the CLI when --strategy-id is omitted.",
  },
  {
    name: "QUANTFIDELITY_IDEMPOTENCY_KEY",
    default: "(auto)",
    description: "Idempotency key for evidence bundle ingestion. Auto-generated if unset.",
  },
];

// ---------------------------------------------------------------------------
// DeveloperSDK
// ---------------------------------------------------------------------------

export default function DeveloperSDK() {
  return (
    <div className="flex flex-col gap-4 px-6 py-6 max-w-3xl mx-auto">
      <PageHeader
        tag="DEVELOPER"
        title="SDK & CI Integration"
        subtitle="Python SDK, CLI, and CI ingestion for evidence bundles"
      />

      {/* Notice */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3 text-sm text-text-secondary">
        No external APIs required. This is a local development SDK — all ingestion goes directly to your
        running QuantFidelity server at{" "}
        <span className="font-mono text-text-primary text-xs">localhost:8000</span>.
      </div>

      {/* Installation */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-4">
        <SectionHeader>Installation</SectionHeader>
        <CodeBlock lang="bash">{`cd sdk/python
pip install -e .`}</CodeBlock>
        <p className="mt-3 text-sm text-text-muted">
          The SDK ships with the repo under{" "}
          <span className="font-mono text-text-secondary text-xs">sdk/python/</span>.
          Install in editable mode during development.
        </p>
      </div>

      {/* Quick Start */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-4">
        <SectionHeader>Quick start</SectionHeader>
        {/* Show BOTH styles */}
        <div className="flex flex-col gap-4 sm:flex-row">
          <div className="flex-1">
            <p className="mb-2 text-xs font-medium text-text-secondary">Module API (recommended)</p>
            <CodeBlock lang="python">{`import quantfidelity as qf

# reads QF_API_KEY and QF_BASE_URL from env
qf.init()

# get a strategy handle by slug
strategy = qf.strategy("spy-trend")

# log a backtest run
strategy.log_run(
    "Backtest v1",
    run_type="backtest",
    metrics={
        "sharpe": 1.4,
        "annual_return": 0.15,
        "max_drawdown": -0.12,
        "volatility": 0.14,
        "turnover": 0.35,
    },
)

# check shadow drift vs paper run
result = strategy.shadow_monitor()
print(result["verdict"])`}</CodeBlock>
          </div>
          <div className="flex-1">
            <p className="mb-2 text-xs font-medium text-text-secondary">Direct client (advanced)</p>
            <CodeBlock lang="python">{`from quantfidelity import QuantFidelityClient, EvidenceBundle

client = QuantFidelityClient()  # reads env vars

bundle = (
    EvidenceBundle()
    .with_backtest_run("Backtest v1", metrics={"sharpe": 1.4})
    .with_paper_run("Paper v1", metrics={"sharpe": 0.65})
    .with_actions(compute_reliability_score=True)
)
result = client.ingest_bundle("<strategy-uuid>", bundle)
print(result["summary"])`}</CodeBlock>
          </div>
        </div>
        <p className="mt-3 text-sm text-text-muted">
          Both{" "}
          <span className="font-mono text-text-secondary text-xs">QUANTFIDELITY_BASE_URL</span>{" "}
          and{" "}
          <span className="font-mono text-text-secondary text-xs">QF_BASE_URL</span>{" "}
          are supported, as are{" "}
          <span className="font-mono text-text-secondary text-xs">QUANTFIDELITY_API_KEY</span>{" "}
          and{" "}
          <span className="font-mono text-text-secondary text-xs">QF_API_KEY</span>.
        </p>
      </div>

      {/* Paper run & shadow monitor */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-4">
        <SectionHeader>Paper run &amp; shadow monitor (M88)</SectionHeader>
        <p className="mb-3 text-sm text-text-muted">
          Shadow monitoring compares a paper/live-like run against the backtest baseline to detect research-to-reality drift.
        </p>
        <CodeBlock lang="python">{`# Upload a paper run to detect drift vs backtest
strategy.log_paper_run(
    "Paper Run v1",
    metrics={
        "sharpe": 0.65,
        "annual_return": 0.068,
        "volatility": 0.22,
        "max_drawdown": -0.23,
        "turnover": 0.95,
        "trade_count": 890,
    },
)

# Compare paper vs backtest baseline
monitor = strategy.shadow_monitor()
print(f"Verdict:  {monitor['verdict']}")
print(f"Drift:    {monitor.get('drift_score')}/100")
print(f"Concern:  {monitor.get('primary_concern')}")`}</CodeBlock>
      </div>

      {/* Environment variables */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-4">
        <SectionHeader>Environment variables</SectionHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="pb-2 pr-6 caption font-medium">Variable</th>
                <th className="pb-2 pr-6 caption font-medium">Default</th>
                <th className="pb-2 caption font-medium">Description</th>
              </tr>
            </thead>
            <tbody>
              {ENV_VARS.map((v) => (
                <tr key={v.name} className="border-b border-border last:border-b-0">
                  <td className="py-2 pr-6 font-mono text-accent-500 text-xs">{v.name}</td>
                  <td className="py-2 pr-6 font-mono text-text-muted text-xs">{v.default}</td>
                  <td className="py-2 text-sm text-text-secondary">{v.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-sm text-text-muted">
          API keys are created and managed in{" "}
          <Link to="/settings" className="text-accent-500 hover:text-accent-300 underline underline-offset-2">
            Settings — API Keys
          </Link>
          .
        </p>
      </div>

      {/* CLI commands */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-4">
        <SectionHeader>CLI commands</SectionHeader>
        <CodeBlock lang="bash">{`# Ingest an evidence bundle from a JSON file
qf ingest --strategy-id <uuid> --file bundle.json

# Validate a bundle file without ingesting
qf validate --file bundle.json

# List buffered (pending) bundles
qf buffer list

# Flush all buffered bundles to the server
qf buffer flush`}</CodeBlock>
        <p className="mt-3 text-sm text-text-muted">
          Run <span className="font-mono text-text-secondary text-xs">qf --help</span> for full command reference.
          Use <span className="font-mono text-text-secondary text-xs">qf validate</span> in CI before ingesting to
          catch schema errors early.
        </p>
      </div>

      {/* CI example */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-4">
        <SectionHeader>CI integration example (GitHub Actions)</SectionHeader>
        <CodeBlock lang="yaml">{`- name: Ingest evidence bundle
  env:
    QUANTFIDELITY_BASE_URL: \${{ secrets.QF_BASE_URL }}
    QUANTFIDELITY_API_KEY:  \${{ secrets.QF_API_KEY }}
    QUANTFIDELITY_STRATEGY_ID: \${{ vars.QF_STRATEGY_ID }}
  run: |
    qf validate --file artifacts/bundle.json
    qf ingest   --file artifacts/bundle.json`}</CodeBlock>
      </div>

      {/* Links */}
      <div className="flex flex-wrap gap-3">
        <Link
          to="/settings"
          className="rounded-control border border-border bg-bg-700 px-4 py-2 text-sm text-text-secondary hover:border-accent-500/40 hover:text-accent-500 transition-colors"
        >
          Settings — API Keys
        </Link>
        <Link
          to="/developer/evidence-bundles"
          className="rounded-control border border-border bg-bg-700 px-4 py-2 text-sm text-text-secondary hover:border-accent-500/40 hover:text-accent-500 transition-colors"
        >
          Evidence Bundle Reference
        </Link>
      </div>
    </div>
  );
}
