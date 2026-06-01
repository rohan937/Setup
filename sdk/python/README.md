# QuantFidelity Python SDK

Local Python SDK for submitting evidence bundles to QuantFidelity.

Wraps the M22 `POST /api/strategies/{id}/evidence-bundles` endpoint so quant
researchers can log evidence from notebooks, CI scripts, and the command line
without constructing raw HTTP requests.

> **Not investment advice.** Deterministic — no AI, no live market data.

---

## Install locally (editable)

```bash
cd sdk/python
pip install -e .
```

For development (includes pytest + responses):

```bash
pip install -e ".[dev]"
```

Requirements: Python ≥ 3.11, `requests` ≥ 2.28.

---

## Quick start

```python
from quantfidelity import QuantFidelityClient, EvidenceBundle

client = QuantFidelityClient(base_url="http://localhost:8000")

bundle = (
    EvidenceBundle()
    .with_strategy_run(
        "backtest-2024-q1",
        run_type="backtest",
        metrics_json={"sharpe": 1.4, "max_drawdown": -0.12},
    )
    .with_actions(compute_reliability_score=True)
)

result = client.ingest_evidence_bundle("<strategy-uuid>", bundle)
print(result["summary"])
print(f"Created: {result['created_count']}")
```

---

## Pandas-friendly helpers

Install optional pandas support:

```bash
pip install "quantfidelity[pandas]"
```

```python
from quantfidelity.dataframe import rows_from_table

# Accepts list[dict] or pandas DataFrame — both work the same way
rows = rows_from_table(df)  # NaN→None, datetime→ISO, numpy scalars→Python

bundle.with_dataset_snapshot_from_table("snap", df)
bundle.with_signal_snapshot_from_table("sigs", signal_df)
```

Works with plain `list[dict]` even without pandas installed.

---

## QuantResearchWorkflow

```python
from quantfidelity import QuantFidelityClient, QuantResearchWorkflow

client = QuantFidelityClient(base_url="http://localhost:8000")

wf = QuantResearchWorkflow(strategy_name="AAPL MR", version_label="v1.0")
wf.set_config(params={"lookback": 20}).set_universe(["AAPL", "MSFT"]).set_backtest_result(metrics={"sharpe": 1.4})
bundle = wf.to_bundle()
result = client.ingest_bundle(strategy_id, bundle)
```

All `set_*` methods are chainable.  `to_bundle()` returns an `EvidenceBundle` ready to ingest.

---

## Bundle validation

```python
# Returns list[str] of issues — empty means valid
issues = bundle.validate()

# Raises QuantFidelityValidationError if any issues exist
bundle.raise_if_invalid()
```

```bash
# CLI: validate a bundle file without sending
qf validate --file bundle.json

# Validate before ingesting (aborts on issues)
qf ingest --strategy-id <uuid> --file bundle.json --validate-before-send

# Force send even if validation finds issues
qf ingest --strategy-id <uuid> --file bundle.json --validate-before-send --force
```

---

## Safe retries & idempotency

### Auto-retry with idempotency key

```python
client.ingest_evidence_bundle(strategy_id, bundle, retry=True)
```

`retry=True` (the default) auto-generates a UUID idempotency key and retries up to 3 times
on connection errors and 5xx responses (502/503/504). Backoff starts at 0.5 s and doubles
each attempt.

### Manual idempotency key

```python
result = client.ingest_evidence_bundle(
    strategy_id, bundle, idempotency_key="backtest-q1-2024"
)
```

- Same key + same payload → replays stored response (`idempotency_status="replayed"`).
- Same key + different payload → 409 Conflict.

### Offline buffer

If the server is unreachable and you don't want to lose the bundle:

```python
result = client.ingest_evidence_bundle(
    strategy_id, bundle, buffer_on_failure=True
)
```

The bundle is written to `~/.quantfidelity/buffer.jsonl`.  Later, flush buffered records:

```python
result = client.flush_buffer()
# {"flushed": 2, "failed": 0, "remaining": 0}

client.list_buffered()  # see what's buffered
client.clear_buffer()   # remove all
```

### CLI

```bash
qf ingest --strategy-id <uuid> --file bundle.json --idempotency-key my-key
qf ingest --strategy-id <uuid> --file bundle.json --buffer-on-failure

qf buffer list
qf buffer flush --base-url http://localhost:8000
qf buffer clear --yes
```

### Note

The buffer **never** stores API keys.  `api_key` is resolved from the client at flush time.

---

## API key authentication

### Create a key

Create API keys from the QuantFidelity Settings page (/settings) or via the API:

```bash
curl -s -X POST http://localhost:8000/api/api-keys \
  -H "Content-Type: application/json" \
  -d '{"name": "my-sdk-key"}' | python3 -m json.tool
# Returns raw_key once. Store it securely.
```

### Use in the SDK

```python
from quantfidelity import QuantFidelityClient, EvidenceBundle
client = QuantFidelityClient(
    base_url="http://localhost:8000",
    api_key="qf_local_<your-key>",
)
```

### Use with environment variable

```bash
export QUANTFIDELITY_API_KEY=qf_local_<your-key>
qf ingest --strategy-id <uuid> --file bundle.json
```

### CLI

```bash
# --api-key flag
qf --api-key qf_local_<key> ingest --strategy-id <uuid> --file bundle.json

# Or use env var (recommended)
export QUANTFIDELITY_API_KEY=qf_local_<key>
qf ingest --strategy-id <uuid> --file bundle.json
```

### Enabling API key enforcement

By default, API keys are optional (QF_REQUIRE_API_KEY_FOR_INGESTION=false).
To require keys for the evidence bundle endpoint, set in backend/.env:

```
QF_REQUIRE_API_KEY_FOR_INGESTION=true
```

**Note:** API keys are QuantFidelity-owned local keys for SDK authentication.
They are not third-party market data API keys.

---

## Full evidence bundle example

```python
from quantfidelity import QuantFidelityClient, EvidenceBundle

client = QuantFidelityClient(base_url="http://localhost:8000")

bundle = (
    EvidenceBundle()
    # Strategy version (reused if label already exists)
    .with_strategy_version(
        "v1.0.0",
        git_commit="abc123def456",
        branch_name="main",
        code_path="strategies/aapl_mr.py",
        signal_name="return_zscore",
        signal_description="20-day return z-score mean reversion signal",
    )
    # Config snapshot — links to version by label
    .with_config_snapshot(
        "baseline-config",
        strategy_version_label="v1.0.0",
        config_json={
            "params": {"lookback": 20, "entry_z": 2.0},
            "assumptions": {"transaction_cost_bps": 5, "fill_model": "next_open"},
        },
    )
    # Universe snapshot
    .with_universe_snapshot(
        "sp500-2024-q1",
        strategy_version_label="v1.0.0",
        symbols=["AAPL", "MSFT", "NVDA"],
        metadata_json={"universe_type": "SP500", "rebalance_freq": "monthly"},
    )
    # Signal snapshot — linked rows
    .with_signal_snapshot(
        "signals-2024-01-02",
        strategy_version_label="v1.0.0",
        universe_snapshot_label="sp500-2024-q1",
        signal_name="return_zscore",
        rows=[
            {"symbol": "AAPL", "timestamp": "2024-01-02", "signal": 1.5},
            {"symbol": "MSFT", "timestamp": "2024-01-02", "signal": -0.8},
        ],
    )
    # Dataset (reused if name already exists in the project)
    .with_dataset(
        "SP500 OHLCV Demo",
        description="Daily OHLCV data for SP500 constituents",
        dataset_type="equity_prices",
    )
    # Dataset snapshot
    .with_dataset_snapshot(
        snapshot_label="2024-q1",
        rows=[
            {"symbol": "AAPL", "timestamp": "2024-01-02", "open": 185.0,
             "high": 188.0, "low": 184.5, "close": 185.64, "volume": 72043900},
        ],
    )
    # Strategy run — links to all the above by label
    .with_strategy_run(
        "backtest-q1-2024",
        run_type="backtest",
        strategy_version_label="v1.0.0",
        dataset_snapshot_label="2024-q1",
        universe_snapshot_label="sp500-2024-q1",
        signal_snapshot_label="signals-2024-01-02",
        params_json={"lookback": 20, "entry_z": 2.0},
        assumptions_json={"cost_bps": 5, "fill_model": "next_open"},
        metrics_json={"sharpe": 1.6, "annual_return": 0.18, "max_drawdown": -0.11},
        universe_name="SP500 Top 50",
    )
    # Actions — run after all sections are created
    .with_actions(
        run_backtest_audit=True,
        compute_reliability_score=True,
    )
)

result = client.ingest_evidence_bundle("<strategy-uuid>", bundle)
for section, obj in result["objects"].items():
    if obj:
        print(f"  {section}: {obj['status']} — {obj['name']}")
```

---

## Payload serialisation

```python
# Export to dict
payload = bundle.to_dict()

# Export to JSON string
json_text = bundle.to_json(indent=2)

# Load from dict or JSON
bundle2 = EvidenceBundle.from_dict(payload)
bundle3 = EvidenceBundle.from_json(json_text)

# Inspect
print(bundle.sections())   # ['strategy_version', 'config_snapshot', ...]
print(bundle.is_empty())   # False
```

---

## CLI usage

After installing, the `qf` command is available:

```bash
# Ingest from a JSON file
qf ingest --strategy-id <uuid> --file examples/bundle.json

# Dry-run (parse and print, do not send)
qf ingest --strategy-id <uuid> --file bundle.json --dry-run

# Fetch an example payload from the API
qf example --strategy-id <uuid>

# Save the example to a file
qf example --strategy-id <uuid> --output my_bundle.json

# Check server health
qf health

# Custom server
qf --base-url http://qf.myteam.internal ingest --strategy-id <uuid> --file bundle.json
```

---

## Run tests

```bash
cd sdk/python
pip install -e ".[dev]"
pytest -v
```

---

## Exceptions

```python
from quantfidelity.exceptions import (
    QuantFidelityError,          # base
    QuantFidelityConnectionError,  # cannot reach server
    QuantFidelityAPIError,         # non-2xx response
    QuantFidelityValidationError,  # client-side validation
)
```

---

## Known limitations (M26)

- **No async support** — synchronous `requests` only.  Async variant planned for a future milestone.
- **No PyPI publish** — local editable install only.  `pip install quantfidelity` does not work yet.
- **No automatic Git detection** — `git_commit` and `branch_name` must be supplied manually.

---

## Design notes

- **Deterministic**: all server-side computation reuses existing M2–M22 services.
  No AI, no live market data, no external calls.
- **SDK is the foundation**: this package is intentionally minimal; future milestones
  will add auth, batching, async, pandas helpers, and a `pip install quantfidelity`
  release.
- **Backend is source of truth**: client-side validation is lightweight.
  The server enforces all business rules.
