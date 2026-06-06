import { useEffect, useRef, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import PageHeader from "@/components/PageHeader";
import Button from "@/components/Button";
import { getStrategies, ingestEvidenceBundle } from "@/lib/api";
import type { EvidenceBundleResponse, Strategy } from "@/types";
import {
  type BuilderState,
  type BuilderValidationError,
  type ParsedCSV,
  buildBundle,
  defaultBuilderState,
  demoDefaultsState,
  parseCSV,
  parseSymbols,
  validateBuilder,
} from "@/lib/bundleBuilder";

// ─────────────────────────────────────────────────────────────
// Helper components
// ─────────────────────────────────────────────────────────────

function Section({
  title,
  expanded,
  onToggle,
  badge,
  children,
}: {
  title: string;
  expanded: boolean;
  onToggle: () => void;
  badge?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`rounded-card border border-border ${
        expanded ? "bg-bg-800" : "bg-bg-900"
      }`}
    >
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-3 cursor-pointer hover:bg-bg-700/50 rounded-card"
      >
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-text-muted select-none">
            {expanded ? "▾" : "▸"}
          </span>
          <span className="text-sm font-semibold tracking-tight text-text-primary">
            {title}
          </span>
        </div>
        {badge && (
          <span className="rounded-chip border border-border bg-bg-700 px-2 py-0.5 font-mono text-2xs text-text-muted">
            {badge}
          </span>
        )}
      </button>
      {expanded && (
        <div className="border-t border-border px-4 pb-4 pt-3">{children}</div>
      )}
    </div>
  );
}

function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="mb-3">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-3">
        <label className="min-w-[160px] pt-1.5 font-mono text-xs text-text-muted shrink-0">
          {label}
        </label>
        <div className="flex-1">{children}</div>
      </div>
      {hint && (
        <p className="mt-1 pl-0 font-mono text-xs text-text-muted sm:pl-[172px]">
          {hint}
        </p>
      )}
    </div>
  );
}

function SectionBadge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-chip border border-border bg-bg-700 px-1.5 py-0.5 font-mono text-2xs text-text-muted">
      {children}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────
// Shared input class
// ─────────────────────────────────────────────────────────────

const INPUT_CLS =
  "w-full rounded-control border border-border bg-bg-700 px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent-500/50";

// ─────────────────────────────────────────────────────────────
// CSV Preview sub-component
// ─────────────────────────────────────────────────────────────

function CSVPreview({ parsed }: { parsed: ParsedCSV | null }) {
  if (!parsed) return null;
  if (parsed.error) {
    return (
      <p className="mt-1.5 font-mono text-xs text-red-400">{parsed.error}</p>
    );
  }
  return (
    <div className="mt-2 rounded-control border border-border bg-bg-900 p-3">
      <div className="mb-2 flex flex-wrap gap-3">
        <span className="font-mono text-xs text-text-muted">
          {parsed.rowCount} rows
        </span>
        {parsed.symbolCount > 0 && (
          <span className="font-mono text-xs text-text-muted">
            {parsed.symbolCount} symbols
          </span>
        )}
        {parsed.dateRange.min && (
          <span className="font-mono text-xs text-text-muted">
            {parsed.dateRange.min} – {parsed.dateRange.max}
          </span>
        )}
        <span className="font-mono text-xs text-text-muted">
          cols: {parsed.columns.join(", ")}
        </span>
      </div>
      {parsed.rows.slice(0, 3).length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr>
                {parsed.columns.map((col) => (
                  <th
                    key={col}
                    className="pb-1 pr-4 font-mono text-2xs text-text-muted"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {parsed.rows.slice(0, 3).map((row, i) => (
                <tr key={i}>
                  {parsed.columns.map((col) => (
                    <td
                      key={col}
                      className="pr-4 font-mono text-2xs text-text-secondary"
                    >
                      {String(row[col] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// EvidenceBuilder
// ─────────────────────────────────────────────────────────────

export default function EvidenceBuilder() {
  const [searchParams] = useSearchParams();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [state, setState] = useState<BuilderState>(() => {
    const s = defaultBuilderState();
    const sid = searchParams.get("strategyId");
    if (sid) s.strategyId = sid;
    return s;
  });

  // Which sections are expanded
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    strategy: true,
    version: false,
    config: false,
    universe: false,
    dataset: false,
    signal: false,
    run: true,
    actions: false,
    preview: true,
  });

  // Ingest state
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState<EvidenceBundleResponse | null>(null);
  const [ingestError, setIngestError] = useState<string | null>(null);

  // Validation flash state
  const [validateFlash, setValidateFlash] = useState<"idle" | "ok" | "fail">("idle");

  // Refs for hidden file inputs
  const datasetFileRef = useRef<HTMLInputElement>(null);
  const signalFileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getStrategies()
      .then(setStrategies)
      .catch(() => {});
  }, []);

  // ── Computed values ──────────────────────────────────────────

  const symbols = parseSymbols(state.universeSymbolsRaw);
  const bundle = buildBundle(state);
  const bundleJson = JSON.stringify(bundle, null, 2);
  const validationErrors: BuilderValidationError[] = validateBuilder(state);
  const isValid = validationErrors.length === 0;

  const selectedStrategy = strategies.find((s) => s.id === state.strategyId) ?? null;

  // Section counts for preview
  const sectionKeys = [
    "strategy_version",
    "config_snapshot",
    "universe_snapshot",
    "dataset",
    "dataset_snapshot",
    "signal_snapshot",
    "strategy_run",
    "actions",
  ] as const;
  const sectionCount = sectionKeys.filter(
    (k) => bundle[k as keyof typeof bundle] !== undefined
  ).length;

  // ── Helpers ──────────────────────────────────────────────────

  function toggleSection(key: string) {
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function update(patch: Partial<BuilderState>) {
    setState((prev) => ({ ...prev, ...patch }));
  }

  function handleFillDemo() {
    const demo = demoDefaultsState();
    demo.strategyId = state.strategyId;
    demo.datasetParsed = parseCSV(demo.datasetCsvRaw);
    demo.signalParsed = parseCSV(demo.signalCsvRaw);
    setState(demo);
    setExpanded({
      strategy: true,
      version: true,
      config: true,
      universe: true,
      dataset: true,
      signal: true,
      run: true,
      actions: true,
      preview: true,
    });
    setIngestResult(null);
    setIngestError(null);
    setValidateFlash("idle");
  }

  function handleCSVFile(
    file: File,
    onParsed: (raw: string, parsed: ParsedCSV) => void
  ) {
    const reader = new FileReader();
    reader.onload = (e) => {
      const raw = e.target?.result as string;
      const parsed = parseCSV(raw);
      onParsed(raw, parsed);
    };
    reader.readAsText(file);
  }

  async function handleIngest() {
    if (!state.strategyId) return;
    setIngesting(true);
    setIngestError(null);
    setIngestResult(null);
    try {
      const result = await ingestEvidenceBundle(state.strategyId, bundle);
      setIngestResult(result);
    } catch (err) {
      setIngestError(err instanceof Error ? err.message : "Ingestion failed.");
    } finally {
      setIngesting(false);
    }
  }

  function handleCopy() {
    navigator.clipboard.writeText(bundleJson).catch(() => {});
  }

  function handleDownload() {
    const blob = new Blob([bundleJson], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "evidence-bundle.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleValidate() {
    if (isValid) {
      setValidateFlash("ok");
    } else {
      setValidateFlash("fail");
    }
    setTimeout(() => setValidateFlash("idle"), 2500);
  }

  function handleReset() {
    setState(defaultBuilderState());
    setIngestResult(null);
    setIngestError(null);
    setValidateFlash("idle");
  }

  // ── Render ───────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-bg-950 px-6 py-6 text-text-primary">
      {/* Header */}
      <PageHeader
        tag="Developer"
        title="Bundle Builder"
        subtitle="Build an evidence bundle without hand-writing JSON."
      >
        <Button variant="secondary" size="sm" onClick={handleFillDemo}>
          Fill SPY Trend Demo
        </Button>
      </PageHeader>

      <div className="space-y-3">

        {/* ── Section 1: Strategy ─────────────────────────────── */}
        <Section
          title="Strategy"
          expanded={expanded.strategy}
          onToggle={() => toggleSection("strategy")}
          badge={selectedStrategy ? selectedStrategy.name : undefined}
        >
          <Field label="strategy" hint="Select the strategy this bundle targets.">
            <select
              className={INPUT_CLS}
              value={state.strategyId}
              onChange={(e) => update({ strategyId: e.target.value })}
            >
              <option value="">— select a strategy —</option>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.slug}) — {s.asset_class}
                </option>
              ))}
            </select>
          </Field>
          {!state.strategyId && (
            <p className="mt-1 font-mono text-xs text-red-400">
              A strategy must be selected before ingesting.
            </p>
          )}
          {selectedStrategy && (
            <div className="mt-2 flex flex-wrap gap-2">
              <SectionBadge>slug: {selectedStrategy.slug}</SectionBadge>
              <SectionBadge>{selectedStrategy.asset_class}</SectionBadge>
              <SectionBadge>{selectedStrategy.status}</SectionBadge>
            </div>
          )}
        </Section>

        {/* ── Section 2: Version ──────────────────────────────── */}
        <Section
          title="Version"
          expanded={expanded.version}
          onToggle={() => toggleSection("version")}
          badge={state.versionEnabled ? state.versionLabel || "enabled" : undefined}
        >
          <Field label="include version">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={state.versionEnabled}
                onChange={(e) => update({ versionEnabled: e.target.checked })}
                className="h-3.5 w-3.5 accent-brand"
              />
              <span className="text-sm text-text-secondary">
                Include version section
              </span>
            </label>
          </Field>
          {state.versionEnabled && (
            <>
              <Field label="version_label">
                <input
                  type="text"
                  className={INPUT_CLS}
                  placeholder="v1.0"
                  value={state.versionLabel}
                  onChange={(e) => update({ versionLabel: e.target.value })}
                />
              </Field>
              <Field label="signal_name">
                <input
                  type="text"
                  className={INPUT_CLS}
                  placeholder="spy_ma_crossover_trend"
                  value={state.versionSignalName}
                  onChange={(e) => update({ versionSignalName: e.target.value })}
                />
              </Field>
              <Field label="git_commit" hint="Optional — short SHA or full hash.">
                <input
                  type="text"
                  className={INPUT_CLS}
                  placeholder="a1b2c3d"
                  value={state.versionGitCommit}
                  onChange={(e) => update({ versionGitCommit: e.target.value })}
                />
              </Field>
              <Field label="branch_name" hint="Optional.">
                <input
                  type="text"
                  className={INPUT_CLS}
                  placeholder="research/spy-trend"
                  value={state.versionBranch}
                  onChange={(e) => update({ versionBranch: e.target.value })}
                />
              </Field>
            </>
          )}
        </Section>

        {/* ── Section 3: Config ───────────────────────────────── */}
        <Section
          title="Config"
          expanded={expanded.config}
          onToggle={() => toggleSection("config")}
          badge={state.configEnabled ? state.configLabel || "enabled" : undefined}
        >
          <Field label="include config">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={state.configEnabled}
                onChange={(e) => update({ configEnabled: e.target.checked })}
                className="h-3.5 w-3.5 accent-brand"
              />
              <span className="text-sm text-text-secondary">
                Include config section
              </span>
            </label>
          </Field>
          {state.configEnabled && (
            <>
              <Field label="label">
                <input
                  type="text"
                  className={INPUT_CLS}
                  placeholder="SPY Trend v1 config"
                  value={state.configLabel}
                  onChange={(e) => update({ configLabel: e.target.value })}
                />
              </Field>
              <Field
                label="params_json"
                hint='JSON object of strategy parameters. e.g. {"lookback": 20}'
              >
                <textarea
                  className={`${INPUT_CLS} resize-y`}
                  rows={3}
                  placeholder='{"lookback": 20}'
                  value={state.configParamsRaw}
                  onChange={(e) => update({ configParamsRaw: e.target.value })}
                />
                {state.configParamsRaw.trim() &&
                  (() => {
                    try {
                      JSON.parse(state.configParamsRaw);
                      return null;
                    } catch {
                      return (
                        <p className="mt-1 font-mono text-xs text-red-400">
                          Invalid JSON.
                        </p>
                      );
                    }
                  })()}
              </Field>
              <p className="mb-2 font-mono text-xs text-text-muted">
                assumptions
              </p>
              <div className="rounded-control border border-border bg-bg-900 p-3 space-y-2">
                <Field label="transaction_cost_bps">
                  <input
                    type="number"
                    className={INPUT_CLS}
                    placeholder="5"
                    value={state.configCostBps}
                    onChange={(e) => update({ configCostBps: e.target.value })}
                  />
                </Field>
                <Field label="slippage_bps">
                  <input
                    type="number"
                    className={INPUT_CLS}
                    placeholder="2"
                    value={state.configSlippageBps}
                    onChange={(e) =>
                      update({ configSlippageBps: e.target.value })
                    }
                  />
                </Field>
                <Field label="fill_model">
                  <select
                    className={INPUT_CLS}
                    value={state.configFillModel}
                    onChange={(e) => update({ configFillModel: e.target.value })}
                  >
                    <option value="">— select —</option>
                    <option value="next_bar_open">next_bar_open</option>
                    <option value="next_open">next_open</option>
                    <option value="vwap">vwap</option>
                    <option value="market">market</option>
                  </select>
                </Field>
                <Field label="rebalance_frequency">
                  <select
                    className={INPUT_CLS}
                    value={state.configRebalanceFreq}
                    onChange={(e) =>
                      update({ configRebalanceFreq: e.target.value })
                    }
                  >
                    <option value="">— select —</option>
                    <option value="daily">daily</option>
                    <option value="weekly">weekly</option>
                    <option value="monthly">monthly</option>
                    <option value="quarterly">quarterly</option>
                  </select>
                </Field>
                <Field label="short_enabled">
                  <label className="flex cursor-pointer items-center gap-2">
                    <input
                      type="checkbox"
                      checked={state.configShortEnabled}
                      onChange={(e) =>
                        update({ configShortEnabled: e.target.checked })
                      }
                      className="h-3.5 w-3.5 accent-brand"
                    />
                    <span className="text-sm text-text-secondary">
                      Allow short selling
                    </span>
                  </label>
                </Field>
                <Field label="leverage_limit">
                  <input
                    type="number"
                    className={INPUT_CLS}
                    placeholder="1.0"
                    step="0.1"
                    value={state.configLeverageLimit}
                    onChange={(e) =>
                      update({ configLeverageLimit: e.target.value })
                    }
                  />
                </Field>
              </div>
            </>
          )}
        </Section>

        {/* ── Section 4: Universe ─────────────────────────────── */}
        <Section
          title="Universe"
          expanded={expanded.universe}
          onToggle={() => toggleSection("universe")}
          badge={
            state.universeEnabled && symbols.length > 0
              ? `${symbols.length} symbol${symbols.length !== 1 ? "s" : ""}`
              : state.universeEnabled
              ? "enabled"
              : undefined
          }
        >
          <Field label="include universe">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={state.universeEnabled}
                onChange={(e) => update({ universeEnabled: e.target.checked })}
                className="h-3.5 w-3.5 accent-brand"
              />
              <span className="text-sm text-text-secondary">
                Include universe section
              </span>
            </label>
          </Field>
          {state.universeEnabled && (
            <>
              <Field label="label">
                <input
                  type="text"
                  className={INPUT_CLS}
                  placeholder="spy-only"
                  value={state.universeLabel}
                  onChange={(e) => update({ universeLabel: e.target.value })}
                />
              </Field>
              <Field
                label="symbols"
                hint="Comma or newline separated, e.g. SPY, QQQ, IWM"
              >
                <textarea
                  className={`${INPUT_CLS} resize-y`}
                  rows={3}
                  placeholder={"SPY\nQQQ\nIWM"}
                  value={state.universeSymbolsRaw}
                  onChange={(e) =>
                    update({ universeSymbolsRaw: e.target.value })
                  }
                />
              </Field>
              {symbols.length > 0 && (
                <div className="mt-1 rounded-control border border-border bg-bg-900 px-3 py-2">
                  <span className="font-mono text-xs text-text-muted">
                    {symbols.length} symbol{symbols.length !== 1 ? "s" : ""}:{" "}
                  </span>
                  <span className="font-mono text-xs text-text-secondary">
                    {symbols.join(", ")}
                  </span>
                </div>
              )}
            </>
          )}
        </Section>

        {/* ── Section 5: Dataset ──────────────────────────────── */}
        <Section
          title="Dataset"
          expanded={expanded.dataset}
          onToggle={() => toggleSection("dataset")}
          badge={
            state.datasetEnabled && state.datasetParsed
              ? `${state.datasetParsed.rowCount} rows`
              : state.datasetEnabled
              ? "enabled"
              : undefined
          }
        >
          <Field label="include dataset">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={state.datasetEnabled}
                onChange={(e) => update({ datasetEnabled: e.target.checked })}
                className="h-3.5 w-3.5 accent-brand"
              />
              <span className="text-sm text-text-secondary">
                Include dataset section
              </span>
            </label>
          </Field>
          {state.datasetEnabled && (
            <>
              <Field label="dataset name">
                <input
                  type="text"
                  className={INPUT_CLS}
                  placeholder="SPY Daily OHLCV"
                  value={state.datasetName}
                  onChange={(e) => update({ datasetName: e.target.value })}
                />
              </Field>
              <Field label="snapshot label">
                <input
                  type="text"
                  className={INPUT_CLS}
                  placeholder="spy-ohlcv-2023"
                  value={state.datasetSnapshotLabel}
                  onChange={(e) =>
                    update({ datasetSnapshotLabel: e.target.value })
                  }
                />
              </Field>
              <Field
                label="CSV data"
                hint="Upload a CSV file or paste CSV text below."
              >
                <div className="space-y-2">
                  <input
                    ref={datasetFileRef}
                    type="file"
                    accept=".csv,text/csv"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (!file) return;
                      handleCSVFile(file, (raw, parsed) => {
                        update({ datasetCsvRaw: raw, datasetParsed: parsed });
                      });
                      e.target.value = "";
                    }}
                  />
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => datasetFileRef.current?.click()}
                  >
                    Upload CSV
                  </Button>
                  <textarea
                    className={`${INPUT_CLS} resize-y font-mono`}
                    rows={5}
                    placeholder={"date,symbol,open,high,low,close,volume\n2023-01-03,SPY,..."}
                    value={state.datasetCsvRaw}
                    onChange={(e) => {
                      const raw = e.target.value;
                      const parsed = raw.trim() ? parseCSV(raw) : null;
                      update({ datasetCsvRaw: raw, datasetParsed: parsed });
                    }}
                  />
                </div>
              </Field>
              <CSVPreview parsed={state.datasetParsed} />
            </>
          )}
        </Section>

        {/* ── Section 6: Signal ───────────────────────────────── */}
        <Section
          title="Signal"
          expanded={expanded.signal}
          onToggle={() => toggleSection("signal")}
          badge={
            state.signalEnabled && state.signalParsed
              ? `${state.signalParsed.rowCount} rows`
              : state.signalEnabled
              ? "enabled"
              : undefined
          }
        >
          <Field label="include signal">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={state.signalEnabled}
                onChange={(e) => update({ signalEnabled: e.target.checked })}
                className="h-3.5 w-3.5 accent-brand"
              />
              <span className="text-sm text-text-secondary">
                Include signal section
              </span>
            </label>
          </Field>
          {state.signalEnabled && (
            <>
              <Field label="label">
                <input
                  type="text"
                  className={INPUT_CLS}
                  placeholder="spy-ma-signal"
                  value={state.signalLabel}
                  onChange={(e) => update({ signalLabel: e.target.value })}
                />
              </Field>
              <Field label="signal_name">
                <input
                  type="text"
                  className={INPUT_CLS}
                  placeholder="spy_ma_crossover_trend"
                  value={state.signalName}
                  onChange={(e) => update({ signalName: e.target.value })}
                />
              </Field>
              <Field
                label="signal_column"
                hint='Name of the column holding signal values. Default: "signal"'
              >
                <input
                  type="text"
                  className={INPUT_CLS}
                  placeholder="signal"
                  value={state.signalColumn}
                  onChange={(e) => update({ signalColumn: e.target.value })}
                />
              </Field>
              <Field
                label="CSV data"
                hint="Expected columns: date, symbol, [signal_column]"
              >
                <div className="space-y-2">
                  <input
                    ref={signalFileRef}
                    type="file"
                    accept=".csv,text/csv"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (!file) return;
                      handleCSVFile(file, (raw, parsed) => {
                        update({ signalCsvRaw: raw, signalParsed: parsed });
                      });
                      e.target.value = "";
                    }}
                  />
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => signalFileRef.current?.click()}
                  >
                    Upload CSV
                  </Button>
                  <textarea
                    className={`${INPUT_CLS} resize-y font-mono`}
                    rows={5}
                    placeholder={"date,symbol,signal\n2023-01-03,SPY,0.0\n2023-01-04,SPY,1.0"}
                    value={state.signalCsvRaw}
                    onChange={(e) => {
                      const raw = e.target.value;
                      const parsed = raw.trim() ? parseCSV(raw) : null;
                      update({ signalCsvRaw: raw, signalParsed: parsed });
                    }}
                  />
                </div>
              </Field>
              <CSVPreview parsed={state.signalParsed} />
            </>
          )}
        </Section>

        {/* ── Section 7: Run ──────────────────────────────────── */}
        <Section
          title="Run"
          expanded={expanded.run}
          onToggle={() => toggleSection("run")}
          badge={
            state.runEnabled
              ? state.runName || state.runType || "enabled"
              : undefined
          }
        >
          <Field label="include run">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={state.runEnabled}
                onChange={(e) => update({ runEnabled: e.target.checked })}
                className="h-3.5 w-3.5 accent-brand"
              />
              <span className="text-sm text-text-secondary">
                Include run section
              </span>
            </label>
          </Field>
          {state.runEnabled && (
            <>
              <Field label="run_name">
                <input
                  type="text"
                  className={INPUT_CLS}
                  placeholder="SPY Trend Backtest v1"
                  value={state.runName}
                  onChange={(e) => update({ runName: e.target.value })}
                />
              </Field>
              <Field label="run_type">
                <select
                  className={INPUT_CLS}
                  value={state.runType}
                  onChange={(e) => update({ runType: e.target.value })}
                >
                  <option value="backtest">backtest</option>
                  <option value="paper">paper</option>
                  <option value="shadow">shadow</option>
                  <option value="live">live</option>
                </select>
              </Field>
              {(state.runType === "paper" || state.runType === "shadow") && (
                <div className="mb-3 rounded-control border border-border bg-bg-900 px-3 py-2.5">
                  <p className="font-mono text-xs text-text-secondary leading-relaxed">
                    Paper/shadow runs enable shadow monitoring. The run will be
                    compared against the backtest baseline to detect
                    research-to-reality drift.
                  </p>
                </div>
              )}
              <Field label="notes" hint="Optional free-text notes about this run.">
                <textarea
                  className={`${INPUT_CLS} resize-y`}
                  rows={2}
                  placeholder="Initial trend-following backtest on SPY"
                  value={state.runNotes}
                  onChange={(e) => update({ runNotes: e.target.value })}
                />
              </Field>

              {/* Metrics */}
              <p className="mb-2 mt-1 font-mono text-xs text-text-muted">
                metrics (leave blank to omit)
              </p>
              <div className="rounded-control border border-border bg-bg-900 p-3 space-y-2">
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                  {(
                    [
                      ["sharpe", "metricSharpe", "1.42"],
                      ["annual_return", "metricAnnualReturn", "0.094"],
                      ["volatility", "metricVolatility", "0.115"],
                      ["max_drawdown", "metricMaxDrawdown", "-0.146"],
                      ["turnover", "metricTurnover", "0.8"],
                      ["trade_count", "metricTradeCount", "24"],
                      ["win_rate", "metricWinRate", "0.54"],
                    ] as const
                  ).map(([label, field, placeholder]) => (
                    <div key={field}>
                      <p className="mb-1 font-mono text-xs text-text-muted">
                        {label}
                      </p>
                      <input
                        type="number"
                        step="any"
                        className={INPUT_CLS}
                        placeholder={placeholder}
                        value={state[field]}
                        onChange={(e) =>
                          update({ [field]: e.target.value } as Partial<BuilderState>)
                        }
                      />
                      {state[field].trim() !== "" &&
                        isNaN(Number(state[field].trim())) && (
                          <p className="mt-0.5 font-mono text-xs text-red-400">
                            Must be a number.
                          </p>
                        )}
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </Section>

        {/* ── Section 8: Actions ──────────────────────────────── */}
        <Section
          title="Actions"
          expanded={expanded.actions}
          onToggle={() => toggleSection("actions")}
          badge={
            [
              state.actionBacktestAudit,
              state.actionReliabilityScore,
              state.actionReport,
              state.actionAlerts,
            ].filter(Boolean).length > 0
              ? `${
                  [
                    state.actionBacktestAudit,
                    state.actionReliabilityScore,
                    state.actionReport,
                    state.actionAlerts,
                  ].filter(Boolean).length
                } active`
              : undefined
          }
        >
          <p className="mb-3 text-xs leading-relaxed text-text-secondary">
            Post-ingestion actions to trigger automatically after the bundle is
            processed.
          </p>
          <div className="space-y-2.5">
            {/* run_backtest_audit */}
            <label
              className={`flex cursor-pointer items-start gap-3 rounded-control border border-border bg-bg-900 px-3 py-2.5 ${
                state.runType !== "backtest" || !state.runEnabled
                  ? "opacity-50 cursor-not-allowed"
                  : ""
              }`}
            >
              <input
                type="checkbox"
                checked={state.actionBacktestAudit}
                disabled={state.runType !== "backtest" || !state.runEnabled}
                onChange={(e) =>
                  update({ actionBacktestAudit: e.target.checked })
                }
                className="mt-0.5 h-3.5 w-3.5 accent-brand"
              />
              <div>
                <p className="font-mono text-xs text-text-primary">
                  run_backtest_audit
                </p>
                <p className="mt-0.5 text-xs leading-relaxed text-text-muted">
                  Generates a BacktestAudit record. Checks for look-ahead bias,
                  overfitting signals, and data leakage.
                  {(state.runType !== "backtest" || !state.runEnabled) && (
                    <span className="ml-1 text-text-muted italic">
                      (requires run_type = backtest)
                    </span>
                  )}
                </p>
              </div>
            </label>

            {/* compute_reliability_score */}
            <label className="flex cursor-pointer items-start gap-3 rounded-control border border-border bg-bg-900 px-3 py-2.5">
              <input
                type="checkbox"
                checked={state.actionReliabilityScore}
                onChange={(e) =>
                  update({ actionReliabilityScore: e.target.checked })
                }
                className="mt-0.5 h-3.5 w-3.5 accent-brand"
              />
              <div>
                <p className="font-mono text-xs text-text-primary">
                  compute_reliability_score
                </p>
                <p className="mt-0.5 text-xs leading-relaxed text-text-muted">
                  Computes the StrategyReliabilityScore from evidence coverage,
                  data health, and backtest quality signals.
                </p>
              </div>
            </label>

            {/* generate_strategy_report */}
            <label className="flex cursor-pointer items-start gap-3 rounded-control border border-border bg-bg-900 px-3 py-2.5">
              <input
                type="checkbox"
                checked={state.actionReport}
                onChange={(e) => update({ actionReport: e.target.checked })}
                className="mt-0.5 h-3.5 w-3.5 accent-brand"
              />
              <div>
                <p className="font-mono text-xs text-text-primary">
                  generate_strategy_report
                </p>
                <p className="mt-0.5 text-xs leading-relaxed text-text-muted">
                  Generates a strategy report snapshot based on all current
                  evidence.
                </p>
              </div>
            </label>

            {/* generate_alerts */}
            <label className="flex cursor-pointer items-start gap-3 rounded-control border border-border bg-bg-900 px-3 py-2.5">
              <input
                type="checkbox"
                checked={state.actionAlerts}
                onChange={(e) => update({ actionAlerts: e.target.checked })}
                className="mt-0.5 h-3.5 w-3.5 accent-brand"
              />
              <div>
                <p className="font-mono text-xs text-text-primary">
                  generate_alerts
                </p>
                <p className="mt-0.5 text-xs leading-relaxed text-text-muted">
                  Triggers alert generation for any reliability thresholds or
                  anomalies detected during ingestion.
                </p>
              </div>
            </label>
          </div>
        </Section>

        {/* ── Preview + Ingest panel ───────────────────────────── */}
        <div className="rounded-card border border-border bg-bg-800 p-5">
          <h2 className="mb-4 text-sm font-semibold tracking-tight text-text-primary">
            Preview &amp; Ingest
          </h2>

          <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
            {/* Left: JSON preview */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="font-mono text-xs text-text-muted">
                  Generated Bundle
                </span>
                <SectionBadge>
                  {sectionCount} section{sectionCount !== 1 ? "s" : ""}
                </SectionBadge>
              </div>
              <pre className="max-h-96 overflow-auto rounded-control border border-border bg-bg-900 p-4 font-mono text-xs leading-relaxed text-text-secondary">
                <code>{bundleJson}</code>
              </pre>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button variant="secondary" size="sm" onClick={handleCopy}>
                  Copy JSON
                </Button>
                <Button variant="secondary" size="sm" onClick={handleDownload}>
                  Download JSON
                </Button>
              </div>
            </div>

            {/* Right: Validation + ingest controls */}
            <div className="flex flex-col gap-3">
              {/* Validation errors */}
              {validationErrors.length > 0 && (
                <div className="rounded-control border border-red-400/30 bg-red-400/5 p-3">
                  <p className="mb-1.5 font-mono text-xs font-semibold text-red-400">
                    Validation errors
                  </p>
                  <ul className="space-y-1">
                    {validationErrors.map((err, i) => (
                      <li key={i} className="font-mono text-xs text-red-400">
                        {err.field}: {err.message}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Validate flash */}
              {validateFlash === "ok" && (
                <div className="rounded-control border border-teal-400/30 bg-teal-400/5 px-3 py-2">
                  <p className="font-mono text-xs text-teal-400">
                    Bundle is valid.
                  </p>
                </div>
              )}
              {validateFlash === "fail" && validationErrors.length > 0 && (
                <div className="rounded-control border border-red-400/30 bg-red-400/5 px-3 py-2">
                  <p className="font-mono text-xs text-red-400">
                    Fix {validationErrors.length} error
                    {validationErrors.length !== 1 ? "s" : ""} above.
                  </p>
                </div>
              )}

              {/* Action buttons */}
              <div className="flex flex-col gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleValidate}
                >
                  Validate
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  disabled={!isValid || !state.strategyId || ingesting}
                  loading={ingesting}
                  onClick={handleIngest}
                >
                  {ingesting ? "Ingesting..." : "Ingest Bundle"}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleReset}
                >
                  Reset Builder
                </Button>
              </div>

              {/* Ingest error */}
              {ingestError && (
                <div className="rounded-control border border-red-400/30 bg-red-400/5 p-3">
                  <p className="font-mono text-xs font-semibold text-red-400">
                    Ingestion failed
                  </p>
                  <p className="mt-1 font-mono text-xs text-red-400">
                    {ingestError}
                  </p>
                </div>
              )}

              {/* Ingest success */}
              {ingestResult && (
                <div className="rounded-control border border-teal-400/30 bg-teal-400/5 p-3">
                  <p className="mb-2 font-mono text-xs font-semibold text-teal-400">
                    Ingestion successful
                  </p>
                  <div className="space-y-1 font-mono text-xs text-teal-400/80">
                    <p>created: {ingestResult.created_count}</p>
                    <p>reused: {ingestResult.reused_count}</p>
                    {ingestResult.alerts_generated > 0 && (
                      <p>alerts: {ingestResult.alerts_generated}</p>
                    )}
                  </div>
                  {ingestResult.warnings.length > 0 && (
                    <div className="mt-2">
                      <p className="font-mono text-xs text-amber-400/80">
                        Warnings:
                      </p>
                      <ul className="mt-1 space-y-0.5">
                        {ingestResult.warnings.map((w, i) => (
                          <li key={i} className="font-mono text-xs text-amber-400/70">
                            {w}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {selectedStrategy && (
                    <div className="mt-3 flex flex-col gap-1.5">
                      <Link
                        to={`/strategies/${selectedStrategy.id}?tab=evidence`}
                        className="font-mono text-xs text-teal-400 underline underline-offset-2 hover:text-teal-300"
                      >
                        View evidence
                      </Link>
                      <Link
                        to={`/strategies/${selectedStrategy.id}?tab=runs`}
                        className="font-mono text-xs text-teal-400 underline underline-offset-2 hover:text-teal-300"
                      >
                        View runs
                      </Link>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Disclaimer */}
          <p className="mt-5 border-t border-border pt-4 font-mono text-xs text-text-muted">
            Evidence bundle builder records research evidence. It is not trading
            advice.
          </p>
        </div>
      </div>
    </div>
  );
}
