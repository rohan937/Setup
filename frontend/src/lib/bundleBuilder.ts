import type { EvidenceBundleRequest } from "../types";

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

export interface ParsedCSV {
  rows: Record<string, unknown>[];
  columns: string[];
  rowCount: number;
  symbolCount: number;
  dateRange: { min: string | null; max: string | null };
  error: string | null;
}

export interface BuilderValidationError {
  field: string;
  message: string;
}

export interface BuilderState {
  // Strategy
  strategyId: string;

  // Version (optional)
  versionEnabled: boolean;
  versionLabel: string;
  versionSignalName: string;
  versionGitCommit: string;
  versionBranch: string;

  // Config (optional)
  configEnabled: boolean;
  configLabel: string;
  configParamsRaw: string;
  configCostBps: string;
  configSlippageBps: string;
  configFillModel: string;
  configShortEnabled: boolean;
  configLeverageLimit: string;
  configRebalanceFreq: string;

  // Universe (optional)
  universeEnabled: boolean;
  universeLabel: string;
  universeSymbolsRaw: string;

  // Dataset (optional)
  datasetEnabled: boolean;
  datasetName: string;
  datasetSnapshotLabel: string;
  datasetCsvRaw: string;
  datasetParsed: ParsedCSV | null;

  // Signal (optional)
  signalEnabled: boolean;
  signalLabel: string;
  signalName: string;
  signalColumn: string;
  signalCsvRaw: string;
  signalParsed: ParsedCSV | null;

  // Run (optional but core)
  runEnabled: boolean;
  runName: string;
  runType: string;
  runNotes: string;
  metricSharpe: string;
  metricAnnualReturn: string;
  metricVolatility: string;
  metricMaxDrawdown: string;
  metricTurnover: string;
  metricTradeCount: string;
  metricWinRate: string;

  // Actions
  actionBacktestAudit: boolean;
  actionReliabilityScore: boolean;
  actionReport: boolean;
  actionAlerts: boolean;
}

// ─────────────────────────────────────────────────────────────
// defaultBuilderState
// ─────────────────────────────────────────────────────────────

export function defaultBuilderState(): BuilderState {
  return {
    strategyId: "",

    versionEnabled: false,
    versionLabel: "",
    versionSignalName: "",
    versionGitCommit: "",
    versionBranch: "",

    configEnabled: false,
    configLabel: "",
    configParamsRaw: "",
    configCostBps: "",
    configSlippageBps: "",
    configFillModel: "",
    configShortEnabled: false,
    configLeverageLimit: "",
    configRebalanceFreq: "",

    universeEnabled: false,
    universeLabel: "",
    universeSymbolsRaw: "",

    datasetEnabled: false,
    datasetName: "",
    datasetSnapshotLabel: "",
    datasetCsvRaw: "",
    datasetParsed: null,

    signalEnabled: false,
    signalLabel: "",
    signalName: "",
    signalColumn: "",
    signalCsvRaw: "",
    signalParsed: null,

    runEnabled: false,
    runName: "",
    runType: "backtest",
    runNotes: "",
    metricSharpe: "",
    metricAnnualReturn: "",
    metricVolatility: "",
    metricMaxDrawdown: "",
    metricTurnover: "",
    metricTradeCount: "",
    metricWinRate: "",

    actionBacktestAudit: false,
    actionReliabilityScore: false,
    actionReport: false,
    actionAlerts: false,
  };
}

// ─────────────────────────────────────────────────────────────
// demoDefaultsState
// ─────────────────────────────────────────────────────────────

export function demoDefaultsState(): BuilderState {
  return {
    strategyId: "",

    versionEnabled: true,
    versionLabel: "v1.0",
    versionSignalName: "spy_ma_crossover_trend",
    versionGitCommit: "a1b2c3d",
    versionBranch: "research/spy-trend",

    configEnabled: true,
    configLabel: "SPY Trend v1 config",
    configParamsRaw: '{"lookback_fast": 20, "lookback_slow": 100, "entry_threshold": 0.02}',
    configCostBps: "5",
    configSlippageBps: "2",
    configFillModel: "next_bar_open",
    configShortEnabled: false,
    configLeverageLimit: "1.0",
    configRebalanceFreq: "weekly",

    universeEnabled: true,
    universeLabel: "spy-only",
    universeSymbolsRaw: "SPY",

    datasetEnabled: true,
    datasetName: "SPY Daily OHLCV",
    datasetSnapshotLabel: "spy-ohlcv-2023",
    datasetCsvRaw:
      "date,symbol,open,high,low,close,volume\n" +
      "2023-01-03,SPY,381.20,387.60,379.80,386.04,89320000\n" +
      "2023-01-04,SPY,383.50,388.70,382.10,387.45,78540000\n" +
      "2023-01-05,SPY,386.20,389.10,381.90,383.29,72100000\n" +
      "2023-01-06,SPY,383.00,392.50,382.20,391.15,98700000\n" +
      "2023-01-09,SPY,393.20,395.80,389.40,392.39,81500000",
    datasetParsed: null,

    signalEnabled: true,
    signalLabel: "spy-ma-signal",
    signalName: "spy_ma_crossover_trend",
    signalColumn: "signal",
    signalCsvRaw:
      "date,symbol,signal\n" +
      "2023-01-03,SPY,0.0\n" +
      "2023-01-04,SPY,0.0\n" +
      "2023-01-05,SPY,0.0\n" +
      "2023-01-06,SPY,1.0\n" +
      "2023-01-09,SPY,1.0",
    signalParsed: null,

    runEnabled: true,
    runName: "SPY Trend Backtest v1",
    runType: "backtest",
    runNotes: "Initial trend-following backtest on SPY",
    metricSharpe: "1.42",
    metricAnnualReturn: "0.094",
    metricVolatility: "0.115",
    metricMaxDrawdown: "-0.146",
    metricTurnover: "0.8",
    metricTradeCount: "24",
    metricWinRate: "0.54",

    actionBacktestAudit: true,
    actionReliabilityScore: true,
    actionReport: false,
    actionAlerts: true,
  };
}

// ─────────────────────────────────────────────────────────────
// parseCSV
// ─────────────────────────────────────────────────────────────

export function parseCSV(raw: string): ParsedCSV {
  const empty: ParsedCSV = {
    rows: [],
    columns: [],
    rowCount: 0,
    symbolCount: 0,
    dateRange: { min: null, max: null },
    error: null,
  };

  if (!raw || !raw.trim()) {
    return { ...empty, error: "Need at least one header row and one data row." };
  }

  const lines = raw
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  if (lines.length < 2) {
    return { ...empty, error: "Need at least one header row and one data row." };
  }

  // Parse a single CSV line, handling optional quotes
  function parseLine(line: string): string[] {
    const result: string[] = [];
    let current = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        inQuotes = !inQuotes;
      } else if (ch === "," && !inQuotes) {
        result.push(current.trim().replace(/^"|"$/g, ""));
        current = "";
      } else {
        current += ch;
      }
    }
    result.push(current.trim().replace(/^"|"$/g, ""));
    return result;
  }

  const headers = parseLine(lines[0]).map((h) => h.trim().replace(/^"|"$/g, ""));
  const dataLines = lines.slice(1);

  const rows: Record<string, unknown>[] = dataLines.map((line) => {
    const values = parseLine(line);
    const row: Record<string, unknown> = {};
    headers.forEach((h, i) => {
      const raw_val = values[i] !== undefined ? values[i] : "";
      // Attempt numeric coercion
      const num = Number(raw_val);
      row[h] = raw_val !== "" && !isNaN(num) ? num : raw_val;
    });
    return row;
  });

  // symbolCount: distinct non-empty values in a "symbol" column (case-insensitive)
  const symbolHeader = headers.find((h) => h.toLowerCase() === "symbol");
  let symbolCount = 0;
  if (symbolHeader) {
    const symbolSet = new Set<string>();
    rows.forEach((r) => {
      const v = r[symbolHeader];
      if (v !== undefined && v !== null && String(v).trim() !== "") {
        symbolSet.add(String(v).trim().toUpperCase());
      }
    });
    symbolCount = symbolSet.size;
  }

  // dateRange: min/max of "date" or "timestamp" column
  const dateHeader = headers.find(
    (h) => h.toLowerCase() === "date" || h.toLowerCase() === "timestamp"
  );
  let dateMin: string | null = null;
  let dateMax: string | null = null;
  if (dateHeader) {
    const dateVals: string[] = rows
      .map((r) => String(r[dateHeader] ?? "").trim())
      .filter((v) => v !== "");
    if (dateVals.length > 0) {
      const sorted = [...dateVals].sort();
      dateMin = sorted[0];
      dateMax = sorted[sorted.length - 1];
    }
  }

  return {
    rows,
    columns: headers,
    rowCount: rows.length,
    symbolCount,
    dateRange: { min: dateMin, max: dateMax },
    error: null,
  };
}

// ─────────────────────────────────────────────────────────────
// parseSymbols
// ─────────────────────────────────────────────────────────────

export function parseSymbols(raw: string): string[] {
  if (!raw || !raw.trim()) return [];
  return [
    ...new Set(
      raw
        .split(/[\n,]+/)
        .map((s) => s.trim().toUpperCase())
        .filter((s) => s.length > 0)
    ),
  ].sort();
}

// ─────────────────────────────────────────────────────────────
// buildBundle
// ─────────────────────────────────────────────────────────────

export function buildBundle(state: BuilderState): EvidenceBundleRequest {
  const bundle: EvidenceBundleRequest = {};

  const versionActive = state.versionEnabled && state.versionLabel.trim() !== "";
  const configActive = state.configEnabled && state.configLabel.trim() !== "";
  const symbols = parseSymbols(state.universeSymbolsRaw);
  const universeActive = state.universeEnabled && symbols.length > 0;
  const datasetActive = state.datasetEnabled && state.datasetName.trim() !== "";
  const datasetSnapshotActive = state.datasetEnabled && (state.datasetParsed?.rows.length ?? 0) > 0;
  const signalActive = state.signalEnabled && (state.signalParsed?.rows.length ?? 0) > 0;
  const runActive = state.runEnabled && state.runName.trim() !== "";

  // strategy_version
  if (versionActive) {
    bundle.strategy_version = {
      version_label: state.versionLabel.trim(),
      ...(state.versionGitCommit.trim() ? { git_commit: state.versionGitCommit.trim() } : {}),
      ...(state.versionBranch.trim() ? { branch_name: state.versionBranch.trim() } : {}),
      ...(state.versionSignalName.trim() ? { signal_name: state.versionSignalName.trim() } : {}),
    };
  }

  // config_snapshot
  if (configActive) {
    let parsedParams: Record<string, unknown> = {};
    if (state.configParamsRaw.trim()) {
      try {
        parsedParams = JSON.parse(state.configParamsRaw) as Record<string, unknown>;
      } catch {
        // invalid JSON — pass empty params; validation will catch this
      }
    }

    const assumptions: Record<string, unknown> = {};
    if (state.configCostBps.trim()) {
      const n = Number(state.configCostBps);
      assumptions["cost_bps"] = isNaN(n) ? state.configCostBps : n;
    }
    if (state.configSlippageBps.trim()) {
      const n = Number(state.configSlippageBps);
      assumptions["slippage_bps"] = isNaN(n) ? state.configSlippageBps : n;
    }
    if (state.configFillModel.trim()) {
      assumptions["fill_model"] = state.configFillModel.trim();
    }
    assumptions["short_enabled"] = state.configShortEnabled;
    if (state.configLeverageLimit.trim()) {
      const n = Number(state.configLeverageLimit);
      assumptions["leverage_limit"] = isNaN(n) ? state.configLeverageLimit : n;
    }
    if (state.configRebalanceFreq.trim()) {
      assumptions["rebalance_freq"] = state.configRebalanceFreq.trim();
    }

    bundle.config_snapshot = {
      label: state.configLabel.trim(),
      config_json: {
        params: parsedParams,
        assumptions,
      },
      ...(versionActive ? { strategy_version_label: state.versionLabel.trim() } : {}),
    };
  }

  // universe_snapshot
  if (universeActive) {
    bundle.universe_snapshot = {
      label: state.universeLabel.trim() || "universe-snapshot",
      symbols,
      ...(versionActive ? { strategy_version_label: state.versionLabel.trim() } : {}),
    };
  }

  // dataset
  if (datasetActive) {
    bundle.dataset = {
      name: state.datasetName.trim(),
    };
  }

  // dataset_snapshot
  if (datasetSnapshotActive) {
    bundle.dataset_snapshot = {
      snapshot_label: state.datasetSnapshotLabel.trim() || "dataset-snapshot",
      rows: state.datasetParsed!.rows,
    };
  }

  // signal_snapshot
  if (signalActive) {
    bundle.signal_snapshot = {
      label: state.signalLabel.trim() || "signal-snapshot",
      signal_name: state.signalName.trim() || undefined,
      signal_column: state.signalColumn.trim() || "signal",
      rows: state.signalParsed!.rows,
      ...(universeActive
        ? { universe_snapshot_label: state.universeLabel.trim() || "universe-snapshot" }
        : {}),
      ...(versionActive ? { strategy_version_label: state.versionLabel.trim() } : {}),
    };
  }

  // strategy_run
  if (runActive) {
    const metrics: Record<string, unknown> = {};
    const metricMap: [string, string][] = [
      ["sharpe", state.metricSharpe],
      ["annual_return", state.metricAnnualReturn],
      ["volatility", state.metricVolatility],
      ["max_drawdown", state.metricMaxDrawdown],
      ["turnover", state.metricTurnover],
      ["trade_count", state.metricTradeCount],
      ["win_rate", state.metricWinRate],
    ];
    for (const [key, val] of metricMap) {
      if (val.trim() !== "") {
        const n = Number(val.trim());
        if (!isNaN(n)) {
          metrics[key] = n;
        }
      }
    }

    bundle.strategy_run = {
      run_name: state.runName.trim(),
      run_type: state.runType || "backtest",
      ...(state.runNotes.trim() ? { notes: state.runNotes.trim() } : {}),
      ...(Object.keys(metrics).length > 0 ? { metrics_json: metrics } : {}),
      ...(versionActive ? { strategy_version_label: state.versionLabel.trim() } : {}),
      ...(datasetSnapshotActive
        ? { dataset_snapshot_label: state.datasetSnapshotLabel.trim() || "dataset-snapshot" }
        : {}),
      ...(universeActive
        ? { universe_snapshot_label: state.universeLabel.trim() || "universe-snapshot" }
        : {}),
      ...(signalActive
        ? { signal_snapshot_label: state.signalLabel.trim() || "signal-snapshot" }
        : {}),
    };
  }

  // actions — always included
  bundle.actions = {
    run_backtest_audit: state.actionBacktestAudit,
    compute_reliability_score: state.actionReliabilityScore,
    generate_strategy_report: state.actionReport,
    generate_alerts: state.actionAlerts,
  };

  return bundle;
}

// ─────────────────────────────────────────────────────────────
// validateBuilder
// ─────────────────────────────────────────────────────────────

export function validateBuilder(state: BuilderState): BuilderValidationError[] {
  const errors: BuilderValidationError[] = [];

  // strategyId is required
  if (!state.strategyId.trim()) {
    errors.push({ field: "strategy", message: "Select a strategy." });
  }

  // At least one section must be enabled
  const anySectionEnabled =
    state.runEnabled ||
    state.datasetEnabled ||
    state.configEnabled ||
    state.universeEnabled ||
    state.signalEnabled;
  if (!anySectionEnabled) {
    errors.push({
      field: "sections",
      message: "Enable at least one section: run, dataset, config, universe, or signal.",
    });
  }

  // Run section validations
  if (state.runEnabled) {
    if (!state.runName.trim()) {
      errors.push({ field: "run.name", message: "Run name is required." });
    }

    const metricFields: [string, string][] = [
      ["run.metricSharpe", state.metricSharpe],
      ["run.metricAnnualReturn", state.metricAnnualReturn],
      ["run.metricVolatility", state.metricVolatility],
      ["run.metricMaxDrawdown", state.metricMaxDrawdown],
      ["run.metricTurnover", state.metricTurnover],
      ["run.metricTradeCount", state.metricTradeCount],
      ["run.metricWinRate", state.metricWinRate],
    ];
    for (const [field, val] of metricFields) {
      if (val.trim() !== "" && isNaN(Number(val.trim()))) {
        const labelMap: Record<string, string> = {
          "run.metricSharpe": "Sharpe ratio",
          "run.metricAnnualReturn": "Annual return",
          "run.metricVolatility": "Volatility",
          "run.metricMaxDrawdown": "Max drawdown",
          "run.metricTurnover": "Turnover",
          "run.metricTradeCount": "Trade count",
          "run.metricWinRate": "Win rate",
        };
        errors.push({
          field,
          message: `${labelMap[field] ?? field} must be a number.`,
        });
      }
    }
  }

  // Universe section validations
  if (state.universeEnabled) {
    const symbols = parseSymbols(state.universeSymbolsRaw);
    if (symbols.length === 0) {
      errors.push({ field: "universe.symbols", message: "Enter at least one symbol." });
    }
  }

  // Dataset section validations
  if (state.datasetEnabled && state.datasetParsed?.error) {
    errors.push({ field: "dataset.csv", message: state.datasetParsed.error });
  }

  // Signal section validations
  if (state.signalEnabled && state.signalParsed?.error) {
    errors.push({ field: "signal.csv", message: state.signalParsed.error });
  }

  // Config section validations
  if (state.configEnabled && state.configParamsRaw.trim()) {
    try {
      JSON.parse(state.configParamsRaw);
    } catch {
      errors.push({ field: "config.params", message: "Params JSON is not valid JSON." });
    }
  }

  return errors;
}
