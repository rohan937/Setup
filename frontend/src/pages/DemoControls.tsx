import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getDemoStatus, seedDemoData } from "@/lib/api";
import type { DemoSeedResponse, DemoStatusResponse } from "@/types";
import PageHeader from "@/components/PageHeader";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function StatusDot({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${active ? "bg-cyan-400" : "bg-gray-600"}`}
    />
  );
}

// ---------------------------------------------------------------------------
// DemoControls
// ---------------------------------------------------------------------------

export default function DemoControls() {
  const [status, setStatus] = useState<DemoStatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);

  const [seedResult, setSeedResult] = useState<DemoSeedResponse | null>(null);
  const [seedError, setSeedError] = useState<string | null>(null);
  const [seedLoading, setSeedLoading] = useState(false);

  const [resetResult, setResetResult] = useState<DemoSeedResponse | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);
  const [resetLoading, setResetLoading] = useState(false);
  const [resetConfirmed, setResetConfirmed] = useState(false);

  const fetchStatus = useCallback(async () => {
    setStatusLoading(true);
    setStatusError(null);
    try {
      const data = await getDemoStatus();
      setStatus(data);
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "Failed to load demo status.");
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  async function handleSeed() {
    setSeedLoading(true);
    setSeedError(null);
    setSeedResult(null);
    try {
      const result = await seedDemoData({
        mode: "seed",
        include_reports: true,
        include_alerts: true,
        include_backtest_audits: true,
      });
      setSeedResult(result);
      fetchStatus();
    } catch (err) {
      setSeedError(err instanceof Error ? err.message : "Seed failed.");
    } finally {
      setSeedLoading(false);
    }
  }

  async function handleReset() {
    if (!resetConfirmed) return;
    setResetLoading(true);
    setResetError(null);
    setResetResult(null);
    try {
      const result = await seedDemoData({
        mode: "reset",
        confirm_reset: true,
        include_reports: true,
        include_alerts: true,
        include_backtest_audits: true,
      });
      setResetResult(result);
      setResetConfirmed(false);
      fetchStatus();
    } catch (err) {
      setResetError(err instanceof Error ? err.message : "Reset failed.");
    } finally {
      setResetLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 px-6 py-6 text-gray-200">
      <PageHeader
        tag="ADMIN"
        title="Demo Controls"
        subtitle="Seed and reset demo data for walkthrough scenarios"
      />

      {/* Demo status */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-cyan-400">
            Demo Status
          </h2>
          <button
            onClick={fetchStatus}
            disabled={statusLoading}
            className="text-xs text-gray-500 hover:text-cyan-400 disabled:opacity-50"
          >
            {statusLoading ? "Loading…" : "Refresh"}
          </button>
        </div>

        {statusError && (
          <p className="mb-3 rounded border border-red-700/40 bg-red-900/20 px-3 py-2 text-xs text-red-400">
            {statusError}
          </p>
        )}

        {status && (
          <div className="space-y-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="rounded border border-gray-800 bg-gray-950 p-3">
                <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Demo Org</p>
                <div className="flex items-center gap-2">
                  <StatusDot active={status.demo_org_exists} />
                  <span className="font-mono text-sm text-gray-200">
                    {status.demo_org_exists ? "Exists" : "Not seeded"}
                  </span>
                </div>
              </div>
              <div className="rounded border border-gray-800 bg-gray-950 p-3">
                <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Demo Project</p>
                <div className="flex items-center gap-2">
                  <StatusDot active={status.demo_project_exists} />
                  <span className="font-mono text-sm text-gray-200">
                    {status.demo_project_exists ? "Exists" : "Not seeded"}
                  </span>
                </div>
              </div>
              <div className="rounded border border-gray-800 bg-gray-950 p-3">
                <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Strategies</p>
                <span className="font-mono text-sm text-cyan-400">{status.strategy_count}</span>
              </div>
            </div>

            {status.demo_strategy_names.length > 0 && (
              <div className="rounded border border-gray-800 bg-gray-950 p-3">
                <p className="mb-2 text-xs uppercase tracking-wider text-gray-500">Strategy Names</p>
                <div className="flex flex-wrap gap-2">
                  {status.demo_strategy_names.map((name) => (
                    <span
                      key={name}
                      className="rounded bg-gray-800 px-2 py-0.5 font-mono text-xs text-gray-300"
                    >
                      {name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {status.last_seeded_at && (
              <p className="text-xs text-gray-500">
                Last seeded:{" "}
                <span className="font-mono text-gray-400">{status.last_seeded_at}</span>
              </p>
            )}

            {status.summary && (
              <p className="text-xs text-gray-400">{status.summary}</p>
            )}
          </div>
        )}

        {statusLoading && !status && (
          <p className="text-sm text-gray-500">Loading demo status…</p>
        )}
      </div>

      {/* Seed action */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-cyan-400">
          Seed Demo Data
        </h2>
        <p className="mb-4 text-sm text-gray-400">
          Creates the demo organization, project, and strategies if they do not already exist.
          Existing demo data is reused — idempotent.
        </p>
        <button
          onClick={handleSeed}
          disabled={seedLoading}
          className="rounded border border-cyan-700/60 bg-cyan-900/20 px-4 py-2 text-sm font-semibold text-cyan-400 hover:bg-cyan-900/40 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {seedLoading ? "Seeding…" : "Seed Demo Data"}
        </button>

        {seedError && (
          <p className="mt-3 rounded border border-red-700/40 bg-red-900/20 px-3 py-2 text-xs text-red-400">
            {seedError}
          </p>
        )}

        {seedResult && (
          <div className="mt-4 rounded border border-gray-700 bg-gray-950 p-4">
            <p className="mb-2 text-sm font-semibold text-cyan-400">Seed complete</p>
            <p className="mb-3 text-sm text-gray-300">{seedResult.summary}</p>
            <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {Object.entries(seedResult.created_counts).map(([k, v]) => (
                <div key={k} className="rounded border border-gray-800 bg-gray-900 p-2">
                  <p className="text-xs text-gray-500">{k}</p>
                  <p className="font-mono text-sm text-cyan-400">{v} created</p>
                </div>
              ))}
              {Object.entries(seedResult.reused_counts).map(([k, v]) => (
                <div key={k} className="rounded border border-gray-800 bg-gray-900 p-2">
                  <p className="text-xs text-gray-500">{k}</p>
                  <p className="font-mono text-sm text-gray-400">{v} reused</p>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-3 text-sm">
              <Link to="/" className="text-cyan-400 underline underline-offset-2 hover:text-cyan-300">
                Dashboard
              </Link>
              <Link to="/portfolio" className="text-cyan-400 underline underline-offset-2 hover:text-cyan-300">
                Portfolio
              </Link>
              <Link to="/strategies" className="text-cyan-400 underline underline-offset-2 hover:text-cyan-300">
                Strategies
              </Link>
            </div>
          </div>
        )}
      </div>

      {/* Reset action */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-amber-400">
          Reset Demo Data
        </h2>
        <p className="mb-4 text-sm text-gray-400">
          Deletes and re-creates all demo organization data. Non-demo data is preserved.
          This action cannot be undone.
        </p>

        <label className="mb-4 flex cursor-pointer items-center gap-3">
          <input
            type="checkbox"
            checked={resetConfirmed}
            onChange={(e) => setResetConfirmed(e.target.checked)}
            className="h-4 w-4 rounded border-gray-600 bg-gray-800 accent-amber-400"
          />
          <span className="text-sm text-gray-400">
            I understand this will delete all demo organization data and re-seed from scratch.
          </span>
        </label>

        <button
          onClick={handleReset}
          disabled={resetLoading || !resetConfirmed}
          className="rounded border border-amber-700/60 bg-amber-900/20 px-4 py-2 text-sm font-semibold text-amber-400 hover:bg-amber-900/40 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {resetLoading ? "Resetting…" : "Reset Demo Data"}
        </button>

        {resetError && (
          <p className="mt-3 rounded border border-red-700/40 bg-red-900/20 px-3 py-2 text-xs text-red-400">
            {resetError}
          </p>
        )}

        {resetResult && (
          <div className="mt-4 rounded border border-gray-700 bg-gray-950 p-4">
            <p className="mb-2 text-sm font-semibold text-amber-400">Reset complete</p>
            <p className="mb-3 text-sm text-gray-300">{resetResult.summary}</p>
            <div className="flex flex-wrap gap-3 text-sm">
              <Link to="/" className="text-cyan-400 underline underline-offset-2 hover:text-cyan-300">
                Dashboard
              </Link>
              <Link to="/strategies" className="text-cyan-400 underline underline-offset-2 hover:text-cyan-300">
                Strategies
              </Link>
            </div>
          </div>
        )}
      </div>

      {/* Notes */}
      <div className="rounded-lg border border-gray-700 bg-gray-900 p-5 text-sm text-gray-400">
        <p className="mb-2">
          Demo reset only affects the deterministic demo organization and its project. All
          non-demo strategies and data are preserved.
        </p>
        <p>
          For full system controls, see{" "}
          <Link to="/admin/system-health" className="text-cyan-400 underline underline-offset-2 hover:text-cyan-300">
            System Health
          </Link>
          .
        </p>
      </div>
    </div>
  );
}
