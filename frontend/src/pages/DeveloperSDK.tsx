import { Link } from "react-router-dom";
import PageHeader from "@/components/PageHeader";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function CodeBlock({ children, lang = "bash" }: { children: string; lang?: string }) {
  return (
    <pre className="overflow-x-auto rounded border border-gray-700 bg-gray-950 p-4 text-xs font-mono text-gray-300 leading-relaxed">
      <code data-lang={lang}>{children}</code>
    </pre>
  );
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-cyan-400">
      {children}
    </h2>
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
    <div className="min-h-screen bg-gray-950 px-6 py-6 text-gray-200">
      <PageHeader
        tag="DEVELOPER"
        title="SDK & CI Integration"
        subtitle="Python SDK, CLI, and CI ingestion for evidence bundles"
      />

      {/* Notice */}
      <div className="mb-6 rounded-lg border border-cyan-700/40 bg-cyan-900/10 p-4 text-sm text-cyan-300">
        No external APIs required. This is a local development SDK — all ingestion goes directly to your
        running QuantFidelity server at <span className="font-mono">localhost:8000</span>.
      </div>

      {/* Installation */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <SectionHeader>Installation</SectionHeader>
        <CodeBlock lang="bash">{`cd sdk/python
pip install -e .`}</CodeBlock>
        <p className="mt-3 text-xs text-gray-500">
          The SDK ships with the repo under <span className="font-mono text-gray-400">sdk/python/</span>.
          Install in editable mode during development.
        </p>
      </div>

      {/* Quick Start */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <SectionHeader>Quick Start</SectionHeader>
        <CodeBlock lang="python">{`from quantfidelity import QuantFidelityClient, EvidenceBundle

client = QuantFidelityClient(base_url="http://localhost:8000")

bundle = (
    EvidenceBundle()
    .with_strategy_run(
        "backtest-q1",
        run_type="backtest",
        metrics_json={"sharpe": 1.4},
    )
)

result = client.ingest_evidence_bundle("<strategy-uuid>", bundle)
print(result.summary)`}</CodeBlock>
        <p className="mt-3 text-xs text-gray-500">
          The client reads <span className="font-mono text-gray-400">QUANTFIDELITY_BASE_URL</span> and{" "}
          <span className="font-mono text-gray-400">QUANTFIDELITY_API_KEY</span> from the environment
          when not passed explicitly.
        </p>
      </div>

      {/* Environment variables */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <SectionHeader>Environment Variables</SectionHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-700 text-left">
                <th className="pb-2 pr-6 font-semibold uppercase tracking-wider text-gray-500">Variable</th>
                <th className="pb-2 pr-6 font-semibold uppercase tracking-wider text-gray-500">Default</th>
                <th className="pb-2 font-semibold uppercase tracking-wider text-gray-500">Description</th>
              </tr>
            </thead>
            <tbody>
              {ENV_VARS.map((v) => (
                <tr key={v.name} className="border-b border-gray-800">
                  <td className="py-2 pr-6 font-mono text-cyan-400">{v.name}</td>
                  <td className="py-2 pr-6 font-mono text-gray-500">{v.default}</td>
                  <td className="py-2 text-gray-400">{v.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-gray-500">
          API keys are created and managed in{" "}
          <Link to="/settings" className="text-cyan-400 underline underline-offset-2 hover:text-cyan-300">
            Settings → API Keys
          </Link>
          .
        </p>
      </div>

      {/* CLI commands */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <SectionHeader>CLI Commands</SectionHeader>
        <CodeBlock lang="bash">{`# Ingest an evidence bundle from a JSON file
qf ingest --strategy-id <uuid> --file bundle.json

# Validate a bundle file without ingesting
qf validate --file bundle.json

# List buffered (pending) bundles
qf buffer list

# Flush all buffered bundles to the server
qf buffer flush`}</CodeBlock>
        <p className="mt-3 text-xs text-gray-500">
          Run <span className="font-mono text-gray-400">qf --help</span> for full command reference.
          Use <span className="font-mono text-gray-400">qf validate</span> in CI before ingesting to
          catch schema errors early.
        </p>
      </div>

      {/* CI example */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <SectionHeader>CI Integration Example (GitHub Actions)</SectionHeader>
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
          className="rounded border border-gray-700 bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:border-cyan-700 hover:text-cyan-400"
        >
          Settings → API Keys
        </Link>
        <Link
          to="/developer/evidence-bundles"
          className="rounded border border-gray-700 bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:border-cyan-700 hover:text-cyan-400"
        >
          Evidence Bundle Reference
        </Link>
      </div>
    </div>
  );
}
