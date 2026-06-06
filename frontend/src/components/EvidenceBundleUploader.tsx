import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { gradeEvidenceBundle, ingestEvidenceBundle } from "@/lib/api";
import type {
  BundleGradeResponse,
  EvidenceBundleObjectRef,
  EvidenceBundleObjects,
  EvidenceBundleRequest,
  EvidenceBundleResponse,
} from "@/types";
import Button from "./Button";
import BundleGradePanel from "./BundleGradePanel";

interface Props {
  strategyId?: string;
  strategies?: { id: string; name: string }[];
  onIngested?: (r: EvidenceBundleResponse) => void;
}

type UploaderState =
  | "idle"
  | "parsing"
  | "valid"
  | "invalid"
  | "ingesting"
  | "success"
  | "error";

const MAX_BYTES = 1024 * 1024; // 1 MB

// Known bundle sections we surface as preview chips.
const KNOWN_SECTIONS: { key: keyof EvidenceBundleRequest; label: string }[] = [
  { key: "strategy_version", label: "strategy_version" },
  { key: "config_snapshot", label: "config_snapshot" },
  { key: "universe_snapshot", label: "universe_snapshot" },
  { key: "signal_snapshot", label: "signal_snapshot" },
  { key: "dataset", label: "dataset" },
  { key: "dataset_snapshot", label: "dataset_snapshot" },
  { key: "strategy_run", label: "strategy_run" },
];

const KNOWN_ACTIONS: { key: string; label: string }[] = [
  { key: "run_backtest_audit", label: "run_backtest_audit" },
  { key: "compute_reliability_score", label: "compute_reliability_score" },
  { key: "generate_strategy_report", label: "generate_strategy_report" },
  { key: "generate_alerts", label: "generate_alerts" },
];

// A realistic but compact KO/PEP pairs-trade evidence bundle.
function sampleBundle(): EvidenceBundleRequest {
  return {
    strategy_version: {
      version_label: "v1.4.0",
      git_commit: "a1b2c3d",
      branch_name: "research/ko-pep-pairs",
      signal_name: "ko_pep_zscore",
      signal_description: "Z-score of KO/PEP log-price spread, 60d window.",
    },
    config_snapshot: {
      strategy_version_label: "v1.4.0",
      label: "baseline-2024Q1",
      source_type: "manual",
      config_json: {
        params: {
          lookback_days: 60,
          entry_z: 2.0,
          exit_z: 0.5,
          max_holding_days: 20,
          hedge_ratio: 1.0,
        },
        assumptions: {
          transaction_cost_bps: 5,
          slippage_bps: 2,
          fill_model: "next_open",
          short_enabled: true,
          borrow_cost_bps: 40,
        },
      },
    },
    universe_snapshot: {
      strategy_version_label: "v1.4.0",
      label: "ko-pep-pair",
      source_type: "manual",
      symbols: ["KO", "PEP"],
    },
    signal_snapshot: {
      strategy_version_label: "v1.4.0",
      universe_snapshot_label: "ko-pep-pair",
      label: "ko-pep-zscore-2024Q1",
      signal_name: "ko_pep_zscore",
      signal_column: "zscore",
      rows: [
        { timestamp: "2024-01-02", symbol: "KO", zscore: 2.31 },
        { timestamp: "2024-01-02", symbol: "PEP", zscore: -2.31 },
        { timestamp: "2024-01-03", symbol: "KO", zscore: 1.88 },
        { timestamp: "2024-01-03", symbol: "PEP", zscore: -1.88 },
      ],
    },
    dataset: {
      name: "US Equities Daily OHLCV",
      asset_class: "equity",
      dataset_type: "ohlcv",
      source_type: "vendor",
    },
    dataset_snapshot: {
      snapshot_label: "2024Q1-eod",
      rows: [
        { timestamp: "2024-01-02", symbol: "KO", open: 58.9, high: 59.4, low: 58.7, close: 59.1, volume: 12500000 },
        { timestamp: "2024-01-02", symbol: "PEP", open: 169.2, high: 170.1, low: 168.8, close: 169.7, volume: 4200000 },
        { timestamp: "2024-01-03", symbol: "KO", open: 59.1, high: 59.3, low: 58.5, close: 58.8, volume: 11800000 },
        { timestamp: "2024-01-03", symbol: "PEP", open: 169.7, high: 170.5, low: 169.0, close: 170.2, volume: 3900000 },
      ],
    },
    strategy_run: {
      strategy_version_label: "v1.4.0",
      dataset_snapshot_label: "2024Q1-eod",
      universe_snapshot_label: "ko-pep-pair",
      signal_snapshot_label: "ko-pep-zscore-2024Q1",
      run_name: "ko-pep-pairs-2024Q1-backtest",
      run_type: "backtest",
      status: "completed",
      metrics_json: {
        sharpe: 1.42,
        annual_return: 0.084,
        max_drawdown: -0.061,
        turnover: 5.3,
        hit_rate: 0.57,
        trade_count: 38,
      },
      assumptions_json: {
        transaction_cost_bps: 5,
        slippage_bps: 2,
        borrow_cost_bps: 40,
        fill_model: "next_open",
        short_enabled: true,
      },
    },
    actions: {
      run_backtest_audit: true,
      compute_reliability_score: true,
    },
  };
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

export default function EvidenceBundleUploader({
  strategyId,
  strategies,
  onIngested,
}: Props) {
  const [text, setText] = useState("");
  const [state, setState] = useState<UploaderState>("idle");
  const [message, setMessage] = useState<string>("");
  const [parsed, setParsed] = useState<EvidenceBundleRequest | null>(null);
  const [selectedStrategy, setSelectedStrategy] = useState<string>("");
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<EvidenceBundleResponse | null>(null);
  const [gradeResult, setGradeResult] = useState<BundleGradeResponse | null>(null);
  const [grading, setGrading] = useState(false);
  const [gradeError, setGradeError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const effectiveStrategyId = strategyId ?? selectedStrategy;
  const isValid = state === "valid" || state === "ingesting" || state === "success";
  const canIngest =
    parsed !== null &&
    Boolean(effectiveStrategyId) &&
    (state === "valid" || state === "error");

  const presentSections = useMemo(() => {
    if (!parsed) return [];
    return KNOWN_SECTIONS.filter(({ key }) => parsed[key] != null);
  }, [parsed]);

  const requestedActions = useMemo(() => {
    if (!parsed || !isPlainObject(parsed.actions)) return [];
    const actions = parsed.actions as Record<string, unknown>;
    return KNOWN_ACTIONS.filter(({ key }) => actions[key] === true);
  }, [parsed]);

  function resetValidation() {
    setParsed(null);
    setResult(null);
    setGradeResult(null);
    setGradeError(null);
    if (state !== "idle") {
      setState("idle");
      setMessage("");
    }
  }

  function loadFile(file: File) {
    setResult(null);
    if (!file.name.toLowerCase().endsWith(".json") && file.type !== "application/json") {
      setState("invalid");
      setParsed(null);
      setMessage("Only .json files are accepted.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setState("invalid");
      setParsed(null);
      setMessage("File is too large. Maximum size is 1 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setText(typeof reader.result === "string" ? reader.result : "");
      setState("idle");
      setMessage("");
      setParsed(null);
    };
    reader.onerror = () => {
      setState("invalid");
      setMessage("Could not read the selected file.");
    };
    reader.readAsText(file);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) loadFile(file);
  }

  function loadSample() {
    setText(JSON.stringify(sampleBundle(), null, 2));
    setState("idle");
    setMessage("");
    setParsed(null);
    setResult(null);
    setGradeResult(null);
    setGradeError(null);
  }

  function validate() {
    setState("parsing");
    setResult(null);
    setGradeResult(null);
    setGradeError(null);
    let value: unknown;
    try {
      // SECURITY: JSON is DATA only — parse, never eval.
      value = JSON.parse(text);
    } catch (err) {
      setParsed(null);
      setState("invalid");
      const detail = err instanceof Error ? err.message : String(err);
      setMessage(`Invalid JSON: ${detail}`);
      return;
    }
    if (!isPlainObject(value)) {
      setParsed(null);
      setState("invalid");
      setMessage("The bundle root must be a JSON object.");
      return;
    }
    setParsed(value as EvidenceBundleRequest);
    setState("valid");
    setMessage("Bundle JSON is valid.");
  }

  async function ingest() {
    if (!parsed || !effectiveStrategyId) return;
    setState("ingesting");
    setMessage("");
    try {
      const res = await ingestEvidenceBundle(effectiveStrategyId, parsed);
      setResult(res);
      setState("success");
      onIngested?.(res);
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      setState("error");
      if (/403|permission/i.test(detail)) {
        setMessage("You do not have permission to ingest evidence.");
      } else {
        setMessage(detail);
      }
    }
  }

  async function handleGrade() {
    if (!parsed) return;
    setGrading(true);
    setGradeError(null);
    try {
      const result = await gradeEvidenceBundle(parsed);
      setGradeResult(result);
    } catch (err) {
      setGradeError(err instanceof Error ? err.message : "Grading failed.");
    } finally {
      setGrading(false);
    }
  }

  const createdObjects = useMemo(() => {
    if (!result) return [];
    const objs = result.objects as EvidenceBundleObjects;
    return (Object.entries(objs) as [string, EvidenceBundleObjectRef | undefined][])
      .filter((entry): entry is [string, EvidenceBundleObjectRef] => entry[1] != null)
      .map(([key, ref]) => ({ key, ...ref }));
  }, [result]);

  return (
    <div className="space-y-5">
      {/* Strategy selector (only when not scoped) */}
      {!strategyId && (
        <div className="space-y-1.5">
          <label className="data-label block" htmlFor="ebu-strategy">
            Strategy
          </label>
          <select
            id="ebu-strategy"
            value={selectedStrategy}
            onChange={(e) => setSelectedStrategy(e.target.value)}
            className="w-full rounded-control border border-border bg-bg-600 px-3 py-2 text-sm text-text-primary focus:border-border-strong focus:outline-none"
          >
            <option value="">Select a strategy…</option>
            {(strategies ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Drag & drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={[
          "rounded-card border border-dashed px-6 py-8 text-center transition-colors",
          dragging
            ? "border-accent-500 bg-bg-600/40"
            : "border-border bg-bg-800/40",
        ].join(" ")}
      >
        <p className="text-sm text-text-secondary">
          Drag &amp; drop a <span className="font-mono text-text-primary">.json</span> bundle here
        </p>
        <p className="mt-1 text-2xs text-text-muted">
          JSON only · max 1 MB · Two ways to add evidence: upload a bundle here, or ingest
          automatically from your pipeline with the SDK / CI.
        </p>
        <div className="mt-4 flex items-center justify-center gap-2">
          <Button size="sm" variant="secondary" onClick={() => fileInputRef.current?.click()}>
            Choose file
          </Button>
          <Button size="sm" variant="ghost" onClick={loadSample}>
            Load sample KO/PEP bundle
          </Button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".json,application/json"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) loadFile(file);
            e.target.value = "";
          }}
        />
      </div>

      {/* JSON editor */}
      <div className="space-y-1.5">
        <label className="data-label block" htmlFor="ebu-json">
          Bundle JSON
        </label>
        <textarea
          id="ebu-json"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            resetValidation();
          }}
          spellCheck={false}
          placeholder='{ "strategy_version": { "version_label": "v1.0.0" }, "actions": { "compute_reliability_score": true } }'
          className="h-64 w-full resize-y rounded-control border border-border bg-bg-900 px-3 py-2.5 font-mono text-xs leading-relaxed text-text-primary placeholder:text-text-muted focus:border-border-strong focus:outline-none"
        />
      </div>

      {/* Action buttons */}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={validate} disabled={!text.trim()}>
          Validate
        </Button>
        <Button
          variant="secondary"
          onClick={handleGrade}
          disabled={!parsed || grading}
          loading={grading}
        >
          {grading ? "Grading..." : "Grade Bundle"}
        </Button>
        <Button
          variant="primary"
          onClick={ingest}
          disabled={!canIngest}
          loading={state === "ingesting"}
        >
          Ingest Bundle
        </Button>
        {!strategyId && !effectiveStrategyId && (
          <span className="text-2xs text-text-muted">Select a strategy to ingest.</span>
        )}
      </div>

      {/* Status message */}
      {message && (state === "invalid" || state === "error" || state === "valid") && (
        <div
          className={[
            "rounded-control border px-3 py-2 text-xs",
            state === "valid"
              ? "border-fidelity-high/40 bg-fidelity-high/5 text-fidelity-high"
              : "border-fidelity-low/40 bg-fidelity-low/5 text-fidelity-low",
          ].join(" ")}
        >
          {message}
        </div>
      )}

      {/* Grade result */}
      {gradeError && <p className="font-mono text-xs text-red-400 mt-2">{gradeError}</p>}
      {gradeResult && (
        <div className="mt-3">
          <BundleGradePanel grade={gradeResult} />
        </div>
      )}

      {/* Preview chips */}
      {isValid && parsed && state !== "success" && (
        <div className="space-y-3 rounded-card border border-border bg-bg-700 p-4 shadow-card">
          <div>
            <p className="data-label mb-2">Sections present</p>
            <div className="flex flex-wrap gap-1.5">
              {presentSections.length === 0 ? (
                <span className="text-2xs text-text-muted">No known sections detected.</span>
              ) : (
                presentSections.map(({ label }) => (
                  <span
                    key={label}
                    className="rounded-chip border border-accent-500/40 px-2 py-0.5 font-mono text-2xs text-accent-300"
                  >
                    {label}
                  </span>
                ))
              )}
            </div>
          </div>
          <div>
            <p className="data-label mb-2">Actions requested</p>
            <div className="flex flex-wrap gap-1.5">
              {requestedActions.length === 0 ? (
                <span className="text-2xs text-text-muted">No actions requested.</span>
              ) : (
                requestedActions.map(({ label }) => (
                  <span
                    key={label}
                    className="rounded-chip border border-teal-500/40 px-2 py-0.5 font-mono text-2xs text-teal-300"
                  >
                    {label}
                  </span>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Success result panel */}
      {state === "success" && result && (
        <div className="space-y-4 rounded-card border border-fidelity-high/30 bg-bg-700 p-5 shadow-card">
          <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
            <span className="text-sm font-medium text-fidelity-high">Bundle ingested</span>
            <span className="font-mono text-2xs text-text-secondary">
              created <span className="text-text-primary">{result.created_count}</span> ·
              reused <span className="text-text-primary">{result.reused_count}</span>
            </span>
          </div>

          {result.summary && (
            <p className="text-xs leading-relaxed text-text-secondary">{result.summary}</p>
          )}

          {result.warnings.length > 0 && (
            <div>
              <p className="data-label mb-1.5">Warnings</p>
              <ul className="space-y-1">
                {result.warnings.map((w, i) => (
                  <li key={i} className="text-2xs text-fidelity-medium">
                    {w}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {createdObjects.length > 0 && (
            <div>
              <p className="data-label mb-2">Objects</p>
              <div className="flex flex-wrap gap-1.5">
                {createdObjects.map((o) => (
                  <span
                    key={o.key}
                    className="rounded-chip border border-border-strong px-2 py-0.5 font-mono text-2xs text-text-secondary"
                  >
                    {o.type}: {o.name}{" "}
                    <span className={o.status === "created" ? "text-fidelity-high" : "text-text-muted"}>
                      ({o.status})
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            <Link to={`/strategies/${result.strategy_id}`}>
              <Button size="sm" variant="primary">
                Open strategy
              </Button>
            </Link>
            <Link to="/audit-trail">
              <Button size="sm" variant="secondary">
                Open Audit Trail
              </Button>
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
