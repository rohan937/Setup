import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getDemoStatus, seedDemoData, seedAdvancedDemoStrategy } from "@/lib/api";
import type { AdvancedDemoSeedResponse, DemoSeedResponse, DemoStatusResponse } from "@/types";
import PageHeader from "@/components/PageHeader";
import { startWalkthrough } from "@/lib/demoWalkthrough";

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

  // Clean realistic demo seed state
  const [cleanResult, setCleanResult] = useState<DemoSeedResponse | null>(null);
  const [cleanError, setCleanError] = useState<string | null>(null);
  const [cleanLoading, setCleanLoading] = useState(false);
  const [cleanConfirmed, setCleanConfirmed] = useState(false);

  // M78: advanced demo strategy seed state
  const [advResult, setAdvResult] = useState<AdvancedDemoSeedResponse | null>(null);
  const [advError, setAdvError] = useState<string | null>(null);
  const [advLoading, setAdvLoading] = useState(false);

  // Legacy seed/reset state
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

  async function handleCleanSeed() {
    if (!cleanConfirmed) return;
    setCleanLoading(true);
    setCleanError(null);
    setCleanResult(null);
    try {
      const result = await seedDemoData({
        mode: "clean_realistic_demo",
        confirm_reset: true,
        include_reports: false,
        include_alerts: true,
        include_backtest_audits: true,
      });
      setCleanResult(result);
      setCleanConfirmed(false);
      fetchStatus();
    } catch (err) {
      setCleanError(err instanceof Error ? err.message : "Clean seed failed.");
    } finally {
      setCleanLoading(false);
    }
  }

  async function handleAdvancedSeed() {
    setAdvLoading(true);
    setAdvError(null);
    setAdvResult(null);
    try {
      const result = await seedAdvancedDemoStrategy();
      setAdvResult(result);
      fetchStatus();
    } catch (err) {
      setAdvError(err instanceof Error ? err.message : "Advanced seed failed.");
    } finally {
      setAdvLoading(false);
    }
  }

  async function handleSeed() {
    setSeedLoading(true);
    setSeedError(null);
    setSeedResult(null);
    try {
      const result = await seedDemoData({
        mode: "extend",
        include_reports: false,
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
        mode: "reset_demo_only",
        confirm_reset: true,
        include_reports: false,
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
                <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Workspace</p>
                <div className="flex items-center gap-2">
                  <StatusDot active={status.demo_org_exists} />
                  <span className="font-mono text-sm text-gray-200">
                    {status.demo_org_exists ? "Alpha Reliability Lab" : "Not seeded"}
                  </span>
                </div>
              </div>
              <div className="rounded border border-gray-800 bg-gray-950 p-3">
                <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Project</p>
                <div className="flex items-center gap-2">
                  <StatusDot active={status.demo_project_exists} />
                  <span className="font-mono text-sm text-gray-200">
                    {status.demo_project_exists ? "Strategy Reliability Demo Portfolio" : "Not seeded"}
                  </span>
                </div>
              </div>
              <div className="rounded border border-gray-800 bg-gray-950 p-3">
                <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Strategies</p>
                <span className={`font-mono text-sm ${status.strategy_count === 3 ? "text-cyan-400" : status.strategy_count > 3 ? "text-amber-400" : "text-gray-400"}`}>
                  {status.strategy_count}
                  {status.strategy_count === 3 && " ✓"}
                  {status.strategy_count > 3 && " (needs reset)"}
                </span>
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
                <span className="font-mono text-gray-400">{new Date(status.last_seeded_at).toLocaleString()}</span>
              </p>
            )}

            {status.summary && (
              <p className="text-xs text-gray-400">{status.summary}</p>
            )}

            {/* M76: start / restart the guided walkthrough at any time */}
            {status.strategy_count > 0 && (
              <button
                onClick={() => startWalkthrough(true)}
                className="mt-3 rounded border border-cyan-700 bg-cyan-950/40 px-3 py-1.5 font-mono text-xs text-cyan-300 hover:border-cyan-500 transition"
              >
                Start / Restart Demo Walkthrough →
              </button>
            )}
          </div>
        )}

        {statusLoading && !status && (
          <p className="text-sm text-gray-500">Loading demo status…</p>
        )}
      </div>

      {/* ──────────────────────────────────────────────────────────────────── */}
      {/* PRIMARY: Reset Clean Realistic Demo                                   */}
      {/* ──────────────────────────────────────────────────────────────────── */}
      <div className="mb-6 rounded-lg border border-cyan-800/50 bg-gray-900 p-5">
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wider text-cyan-400">
          Reset Clean Realistic Demo
        </h2>
        <p className="mb-1 text-xs font-mono text-cyan-600 uppercase tracking-wider">
          Recommended for product walkthroughs
        </p>
        <p className="mb-4 text-sm text-gray-400">
          Wipes <strong className="text-gray-200">all</strong> existing strategy junk data (test runs, M13* names, etc.)
          and creates a fresh, clean workspace with exactly 3 realistic demo strategies that tell a clear product story:
        </p>

        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded border border-green-800/40 bg-green-900/10 p-3">
            <p className="font-mono text-xs font-semibold text-green-400">AAPL Mean Reversion v1</p>
            <p className="mt-1 text-xs text-gray-400">Healthy · well-instrumented · Sharpe ~1.4</p>
          </div>
          <div className="rounded border border-amber-800/40 bg-amber-900/10 p-3">
            <p className="font-mono text-xs font-semibold text-amber-400">Global Futures Trend Model</p>
            <p className="mt-1 text-xs text-gray-400">Review · missing paper/shadow · reliability ~70</p>
          </div>
          <div className="rounded border border-red-800/40 bg-red-900/10 p-3">
            <p className="font-mono text-xs font-semibold text-red-400">Crypto Momentum Intraday</p>
            <p className="mt-1 text-xs text-gray-400">Weak · unrealistic assumptions · Sharpe ~2.8</p>
          </div>
        </div>

        <label className="mb-4 flex cursor-pointer items-center gap-3">
          <input
            type="checkbox"
            checked={cleanConfirmed}
            onChange={(e) => setCleanConfirmed(e.target.checked)}
            className="h-4 w-4 rounded border-gray-600 bg-gray-800 accent-cyan-400"
          />
          <span className="text-sm text-gray-400">
            I understand this resets all local demo data and re-creates the clean demo workspace.
          </span>
        </label>

        <button
          onClick={handleCleanSeed}
          disabled={cleanLoading || !cleanConfirmed}
          className="rounded border border-cyan-700/60 bg-cyan-900/20 px-5 py-2 text-sm font-semibold text-cyan-400 hover:bg-cyan-900/40 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {cleanLoading ? "Resetting…" : "Reset Clean Realistic Demo"}
        </button>

        {cleanError && (
          <p className="mt-3 rounded border border-red-700/40 bg-red-900/20 px-3 py-2 text-xs text-red-400">
            {cleanError}
          </p>
        )}

        {cleanResult && (
          <div className="mt-4 rounded border border-cyan-800/40 bg-gray-950 p-4">
            <p className="mb-2 text-sm font-semibold text-cyan-400">Clean demo seeded</p>
            <p className="mb-3 text-sm text-gray-300">{cleanResult.summary}</p>
            <p className="mb-3 text-xs text-gray-500">
              Wiped: {Object.values(cleanResult.reset_counts).reduce((a, b) => (a as number) + (b as number), 0)} old rows &nbsp;·&nbsp;
              Created: {cleanResult.created_counts.artifacts} artifacts
            </p>

            {/* Suggested next pages */}
            <div className="mb-4 rounded border border-gray-700 bg-gray-900 p-3">
              <p className="mb-2 text-xs uppercase tracking-wider text-gray-500">Suggested walkthrough path</p>
              <div className="flex flex-wrap gap-3 text-sm">
                <Link to="/" className="rounded border border-gray-700 px-3 py-1.5 font-mono text-xs text-cyan-400 hover:border-cyan-600 transition">
                  Dashboard
                </Link>
                <Link to="/portfolio" className="rounded border border-gray-700 px-3 py-1.5 font-mono text-xs text-cyan-400 hover:border-cyan-600 transition">
                  Portfolio
                </Link>
                <Link to="/strategies" className="rounded border border-gray-700 px-3 py-1.5 font-mono text-xs text-cyan-400 hover:border-cyan-600 transition">
                  Strategies
                </Link>
                <Link to="/backtests" className="rounded border border-gray-700 px-3 py-1.5 font-mono text-xs text-cyan-400 hover:border-cyan-600 transition">
                  Backtests
                </Link>
                <Link to="/alerts" className="rounded border border-gray-700 px-3 py-1.5 font-mono text-xs text-amber-400 hover:border-amber-600 transition">
                  Alerts {cleanResult.warnings.length > 0 ? `(${cleanResult.warnings.length} warn)` : ""}
                </Link>
              </div>
              {/* M76: guided walkthrough */}
              <button
                onClick={() => startWalkthrough(true)}
                className="mt-3 rounded border border-cyan-700 bg-cyan-950/40 px-3 py-1.5 font-mono text-xs text-cyan-300 hover:border-cyan-500 transition"
              >
                Start Demo Walkthrough →
              </button>
            </div>

            {cleanResult.warnings.length > 0 && (
              <div className="rounded border border-amber-800/30 bg-amber-900/10 p-3">
                <p className="mb-1 text-xs uppercase tracking-wider text-amber-500">Warnings</p>
                {cleanResult.warnings.map((w, i) => (
                  <p key={i} className="text-xs text-amber-400">{w}</p>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* M78: Advanced Strategy Demo */}
      <div className="mb-6 rounded-lg border border-cyan-800/50 bg-cyan-950/10 p-5">
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wider text-cyan-300">
          Advanced Strategy Demo
        </h2>
        <p className="mb-3 text-xs text-gray-400">
          Seeds one multi-version equity strategy — “US Equity Quality-Momentum Rotation” —
          with historical reports, audits, alerts, review cases, governance, and lifecycle
          progression (v1 → v4). Idempotent: re-running never duplicates it. Deterministic
          synthetic data — not real trading performance.
        </p>
        <button
          onClick={handleAdvancedSeed}
          disabled={advLoading}
          className="rounded border border-cyan-700 bg-cyan-900/30 px-4 py-2 font-mono text-xs text-cyan-300 hover:bg-cyan-900/50 disabled:opacity-50"
        >
          {advLoading ? "Seeding…" : "Seed Advanced Strategy"}
        </button>

        {advError && (
          <p className="mt-3 rounded border border-red-700/40 bg-red-900/20 px-3 py-2 text-xs text-red-400">
            {advError}
          </p>
        )}

        {advResult && (
          <div className="mt-4 rounded border border-gray-700 bg-gray-900 p-4">
            <p className="mb-2 text-sm text-gray-300">
              <span className="uppercase tracking-wider text-cyan-400">{advResult.status}</span>
              {" — "}
              {advResult.strategy_name}
            </p>
            <p className="mb-3 font-mono text-2xs text-gray-500">{advResult.strategy_id}</p>
            <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-2xs text-gray-400">
              <span>{advResult.counts.versions} versions</span>
              <span>{advResult.counts.runs} runs</span>
              <span>{advResult.counts.reports} reports</span>
              <span>{advResult.counts.audits} audits</span>
              <span>{advResult.counts.alerts} alerts</span>
              <span>{advResult.counts.review_cases} review cases</span>
              <span className="text-gray-500">· {advResult.total_artifacts} total artifacts</span>
            </div>
            <Link
              to={`/strategies/${advResult.strategy_id}`}
              className="inline-block rounded border border-cyan-700 px-3 py-1.5 font-mono text-xs text-cyan-400 transition hover:border-cyan-500"
            >
              Open Strategy →
            </Link>
            <p className="mt-3 text-2xs text-gray-600">{advResult.disclaimer}</p>
          </div>
        )}
      </div>

      {/* Legacy: Extend (idempotent) */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-400">
          Extend Demo Data (Idempotent)
        </h2>
        <p className="mb-4 text-sm text-gray-500">
          Creates any missing demo records without touching existing data. Safe to run multiple times.
        </p>
        <button
          onClick={handleSeed}
          disabled={seedLoading}
          className="rounded border border-gray-600 bg-gray-800 px-4 py-2 text-sm font-semibold text-gray-300 hover:border-gray-500 hover:text-gray-200 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {seedLoading ? "Extending…" : "Extend Demo Data"}
        </button>

        {seedError && (
          <p className="mt-3 text-xs text-red-400">{seedError}</p>
        )}
        {seedResult && (
          <p className="mt-3 text-sm text-gray-400">{seedResult.summary}</p>
        )}
      </div>

      {/* Legacy: Reset */}
      <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-amber-400/70">
          Legacy Reset (demo org only)
        </h2>
        <p className="mb-4 text-sm text-gray-500">
          Deletes the demo organization by name only. Does not clean up stray test strategies.
          Use "Reset Clean Realistic Demo" above for a full cleanup.
        </p>

        <label className="mb-4 flex cursor-pointer items-center gap-3">
          <input
            type="checkbox"
            checked={resetConfirmed}
            onChange={(e) => setResetConfirmed(e.target.checked)}
            className="h-4 w-4 rounded border-gray-600 bg-gray-800 accent-amber-400"
          />
          <span className="text-sm text-gray-500">
            I understand this deletes the demo organization.
          </span>
        </label>

        <button
          onClick={handleReset}
          disabled={resetLoading || !resetConfirmed}
          className="rounded border border-amber-800/40 bg-amber-900/10 px-4 py-2 text-sm font-semibold text-amber-500/70 hover:bg-amber-900/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {resetLoading ? "Resetting…" : "Legacy Reset"}
        </button>

        {resetError && (
          <p className="mt-3 text-xs text-red-400">{resetError}</p>
        )}
        {resetResult && (
          <p className="mt-3 text-sm text-gray-400">{resetResult.summary}</p>
        )}
      </div>

      {/* Notes */}
      <div className="rounded-lg border border-gray-700 bg-gray-900 p-5 text-sm text-gray-400">
        <p className="mb-2 font-semibold text-gray-300">Demo walkthrough guide</p>
        <p className="mb-2">
          After "Reset Clean Realistic Demo": Dashboard shows 3 strategies · 6 runs · 11 alerts.
        </p>
        <p className="mb-2">
          See{" "}
          <code className="rounded bg-gray-800 px-1 text-xs text-cyan-400">docs/demo-walkthrough.md</code>{" "}
          for the full page-by-page product story.
        </p>
        <p>
          For system status, see{" "}
          <Link to="/admin/system-health" className="text-cyan-400 underline underline-offset-2 hover:text-cyan-300">
            System Health
          </Link>
          .
        </p>
      </div>
    </div>
  );
}
