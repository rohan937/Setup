# Web Evidence-Bundle Upload

Guide for ingesting QuantFidelity evidence bundles directly from the web app,
without the SDK or CLI.

> **Deterministic.** Not investment advice. No external APIs, no live market data.
> JSON bundles are treated as **data**, never executed.

---

## Two ingestion paths

QuantFidelity accepts evidence bundles through two complementary paths. Both
hit the same backend endpoint and produce identical results — choose based on
who is ingesting and why.

| Path | Best for | Interface |
|------|----------|-----------|
| **Terminal / SDK** | CI / automated pipelines, cron jobs, notebooks | `qf` CLI, Python SDK (`QuantFidelityClient`) |
| **Web upload** | Manual ingestion, research, demos, one-off bundles | Browser — drag/drop or paste JSON |

- The **terminal/SDK** path is documented in [`ci-ingestion.md`](./ci-ingestion.md).
  Use it when ingestion should be scripted, repeatable, and unattended.
- The **web upload** path (this document) is for people working in the app who
  want to hand a bundle to a strategy without leaving the browser — ideal for
  research review, demos, and ad-hoc uploads.

Neither path replaces the other; the SDK/CLI ingestion remains fully supported.

---

## How to upload via the web app

### Path A — Evidence Bundles page

1. Open **Developer → Evidence Bundles** in the left navigation.
2. **Select a strategy** from the strategy picker — this is the ingestion target.
3. **Drag and drop** a `.json` file onto the drop zone, **or paste** the bundle
   JSON directly into the text area.
4. Click **Validate**. The uploader parses the JSON and surfaces any structural
   issues before anything is sent.
5. Review the **preview** of the parsed bundle (which sections are present).
6. Click **Ingest** to send the bundle to the selected strategy.

### Path B — Strategy Detail panel

Each strategy's detail page includes a per-strategy evidence uploader panel.
The strategy is already selected for you, so the flow is:

1. Open the strategy from **Strategies → (your strategy)**.
2. Scroll to the **Evidence Bundle** panel.
3. Drag/drop or paste JSON → **Validate** → review preview → **Ingest**.

Both panels share the same uploader component, so validation, preview, and
ingest behave identically.

---

## Expected bundle fields

A bundle is a single structured JSON object. **Every field is optional** — send
only the sections you have. Unsupplied sections are simply omitted from the
object.

| Field | Purpose |
|-------|---------|
| `strategy_version` | Version label, git commit/branch, code path, signal name/description |
| `config_snapshot` | Named config snapshot: params and assumptions |
| `universe_snapshot` | Named symbol universe + metadata |
| `signal_snapshot` | Signal rows tied to a universe snapshot |
| `dataset` | Dataset definition (name, description, type) |
| `dataset_snapshot` | Point-in-time OHLCV (or similar) rows |
| `strategy_run` | A backtest/run with params, assumptions, and metrics |
| `actions` | Post-ingest actions (audit, reliability score, alerts, report) |

The web uploader sends exactly the same structured object the SDK would build —
there is no web-specific schema.

---

## Sample KO/PEP bundle

A compact bundle for a Coca-Cola / PepsiCo pairs example. Use it as a template:

```json
{
  "strategy_version": {
    "label": "v1.0.0",
    "git_commit": "f0e1d2c3b4a5f0e1d2c3b4a5f0e1d2c3b4a5f0e1",
    "branch_name": "main",
    "code_path": "strategies/ko_pep_pairs.py",
    "signal_name": "ko_pep_spread_z",
    "signal_description": "KO/PEP price-ratio spread z-score"
  },
  "config_snapshot": {
    "label": "ko-pep-baseline",
    "strategy_version_label": "v1.0.0",
    "config_json": {
      "params": { "lookback": 30, "entry_z": 2.0, "exit_z": 0.5 },
      "assumptions": { "transaction_cost_bps": 5, "fill_model": "next_open" }
    }
  },
  "universe_snapshot": {
    "label": "ko-pep-2024",
    "strategy_version_label": "v1.0.0",
    "symbols": ["KO", "PEP"],
    "metadata_json": { "universe_type": "pairs", "note": "demo data only" }
  },
  "signal_snapshot": {
    "label": "ko-pep-signals-2024-01-02",
    "strategy_version_label": "v1.0.0",
    "universe_snapshot_label": "ko-pep-2024",
    "signal_name": "ko_pep_spread_z",
    "rows": [
      { "symbol": "KO",  "timestamp": "2024-01-02", "signal":  1.84 },
      { "symbol": "PEP", "timestamp": "2024-01-02", "signal": -1.84 }
    ]
  },
  "dataset": {
    "name": "KO/PEP Daily OHLCV",
    "description": "Daily prices for KO and PEP. Synthetic demo data only.",
    "dataset_type": "equity_prices"
  },
  "dataset_snapshot": {
    "label": "ko-pep-snap-2024-01-02",
    "rows": [
      { "symbol": "KO",  "timestamp": "2024-01-02", "open": 59.1, "high": 59.8, "low": 58.9, "close": 59.42, "volume": 12043900 },
      { "symbol": "PEP", "timestamp": "2024-01-02", "open": 169.3, "high": 170.6, "low": 168.7, "close": 169.88, "volume": 4835400 }
    ]
  },
  "strategy_run": {
    "run_name": "ko-pep-backtest-2024-q1",
    "run_type": "backtest",
    "strategy_version_label": "v1.0.0",
    "dataset_snapshot_label": "ko-pep-snap-2024-01-02",
    "universe_snapshot_label": "ko-pep-2024",
    "signal_snapshot_label": "ko-pep-signals-2024-01-02",
    "params_json": { "lookback": 30, "entry_z": 2.0, "exit_z": 0.5 },
    "assumptions_json": { "cost_bps": 5, "fill_model": "next_open" },
    "metrics_json": { "sharpe": 1.18, "annual_return": 0.092, "max_drawdown": -0.061, "win_rate": 0.57, "num_trades": 22 },
    "universe_name": "KO/PEP Pairs"
  },
  "actions": {
    "run_backtest_audit": true,
    "compute_reliability_score": true,
    "generate_strategy_report": false,
    "generate_alerts": true
  }
}
```

---

## File safety

- **Only `.json` files** are accepted. Other file types are rejected by the
  uploader.
- **Maximum size is 1 MB.** Larger files are rejected before upload.
- **JSON is treated as DATA, never executed.** The bundle is parsed and stored;
  no field is ever evaluated as code.

---

## RBAC

- Ingesting evidence requires the **write-research** permission.
- A user without that permission receives a **403** with the message:

  > You do not have permission to ingest evidence.

  The uploader surfaces this message directly so the reason is clear.

---

## Notes

All computations are deterministic. No AI, no live market data, no external API
calls. This guide is for system usage only and is not investment advice.
