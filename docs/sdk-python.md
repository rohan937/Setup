# QuantFidelity Python SDK

The QuantFidelity Python SDK provides a concise, notebook-friendly interface for
logging strategy evidence (runs, configs, universes, signals) and querying
reliability scores and the M88 shadow drift monitor.

---

## Installation

```bash
pip install -e sdk/python
```

For pandas helpers:

```bash
pip install -e "sdk/python[pandas]"
```

---

## Quick start (module API)

The simplest workflow uses the module-level `qf` namespace:

```python
import quantfidelity as qf

# 1. Initialize (reads env vars by default)
qf.init()

# 2. Verify authentication
qf.test_auth()

# 3. Get a strategy handle
strategy = qf.strategy("spy-trend-v2")

# 4. Log a backtest run
strategy.log_run(
    "backtest-2024-q1",
    metrics={
        "sharpe": 1.42,
        "annual_return": 0.187,
        "volatility": 0.132,
        "max_drawdown": -0.118,
        "turnover": 0.38,
        "trade_count": 462,
        "win_rate": 0.54,
    },
    params={"lookback_days": 20, "entry_zscore": 2.0},
    version_label="v1.0",
)

# 5. Check shadow drift monitor
result = strategy.shadow_monitor()
print(result["verdict"], result["drift_score"])
```

---

## Authentication

The SDK resolves credentials from environment variables in the following order:

| Environment Variable        | Purpose                         |
|-----------------------------|---------------------------------|
| `QF_API_KEY`                | API key (checked first)         |
| `QUANTFIDELITY_API_KEY`     | API key (fallback)              |
| `QF_BASE_URL`               | Server base URL (checked first) |
| `QUANTFIDELITY_BASE_URL`    | Server base URL (fallback)      |

Defaults to `http://localhost:8000` if no base URL is set.

### Verify authentication

```python
import quantfidelity as qf

qf.init()
result = qf.test_auth()
# {"status": "ok", "authenticated": True}
```

### Handle auth errors

```python
from quantfidelity.exceptions import QuantFidelityAuthError

try:
    qf.test_auth()
except QuantFidelityAuthError as exc:
    print(f"Check your QF_API_KEY: {exc}")
```

---

## StrategyHandle API

`StrategyHandle` is the primary interface returned by `qf.strategy("slug")` or
`client.strategy("uuid-or-slug")`. Slug-to-UUID resolution is lazy and cached.

### Log methods

| Method | Description |
|--------|-------------|
| `log_run(name, *, run_type, metrics, params, assumptions, version_label, notes)` | Log a backtest, paper, research, or live run |
| `log_paper_run(name, *, metrics, params, assumptions, version_label, notes)` | Convenience wrapper — sets `run_type="paper"` |
| `log_config(label, *, params, assumptions, portfolio, version_label)` | Log a config snapshot (params + assumptions) |
| `log_universe(name, *, symbols, metadata, version_label)` | Log a universe/ticker-list snapshot |
| `log_dataset(name, *, rows, symbols, columns, asset_class, dataset_type, ...)` | Log a dataset and optional snapshot rows |
| `log_signal(name, *, rows, signal_key, symbols, signal_column, ...)` | Log a signal snapshot |

### Report, score, and monitor methods

| Method | Description |
|--------|-------------|
| `generate_report()` | POST `/api/reports/strategy/{id}` — generate reliability report |
| `refresh_score()` | POST `/api/strategies/{id}/reliability-score` — recompute score |
| `shadow_monitor()` | GET `/api/strategies/{id}/shadow-monitor/refresh` — M88 drift check |
| `get_detail()` | GET `/api/strategies/{id}` — full strategy detail payload |

### Common metrics keys

```python
metrics = {
    "sharpe":         1.42,   # Sharpe ratio (annualized)
    "annual_return":  0.187,  # CAGR (e.g. 18.7%)
    "volatility":     0.132,  # Annualized realized volatility
    "max_drawdown":  -0.118,  # Maximum peak-to-trough drawdown (negative)
    "turnover":       0.38,   # Average daily/period turnover
    "trade_count":    462,    # Total number of trades
    "win_rate":       0.54,   # Fraction of winning trades
}
```

---

## EvidenceBundle builder (advanced use)

For fine-grained control, build an `EvidenceBundle` directly and submit it via
the client:

```python
from quantfidelity import QuantFidelityClient, EvidenceBundle

client = QuantFidelityClient(base_url="http://localhost:8000", api_key="qf_...")

bundle = (
    EvidenceBundle()
    .with_strategy_version("v2.1", git_commit="a1b2c3d")
    .with_strategy_run(
        "backtest-2024-q1",
        run_type="backtest",
        metrics_json={"sharpe": 1.4, "max_drawdown": -0.12},
        params_json={"lookback_days": 20},
    )
    .with_actions(compute_reliability_score=True, generate_alerts=True)
)

result = client.ingest_bundle("<strategy-uuid>", bundle)
print(result["summary"])
```

### Chaining backtest and paper runs

```python
bundle = (
    EvidenceBundle()
    .with_strategy_version("v1.0")
    .with_strategy_run(
        "backtest-2024",
        run_type="backtest",
        metrics_json={"sharpe": 1.4, "max_drawdown": -0.12, "turnover": 0.35},
    )
    .with_strategy_run(
        "paper-2025-q1",
        run_type="paper",
        metrics_json={"sharpe": 0.65, "max_drawdown": -0.23, "turnover": 0.95},
    )
    .with_actions(compute_reliability_score=True)
)
```

### Grade a bundle before ingest

Use `grade_bundle` (M97) to get a quality grade for an evidence bundle without
ingesting or mutating any data. It returns a dict with `letter_grade`,
`verdict`, `stage_sufficiency`, `included`, `missing`, `warnings`, and
`recommended_fixes`.

```python
grade = client.grade_bundle(bundle)
print(grade["letter_grade"], grade["verdict"])
```

---

## Error handling

All SDK errors inherit from `QuantFidelityError`.

| Exception | HTTP Status | Description |
|-----------|-------------|-------------|
| `QuantFidelityAuthError` | 401 / 403 | Invalid or missing API key |
| `QuantFidelityNotFoundError` | 404 | Strategy or resource not found |
| `QuantFidelityValidationError` | 422 | Request payload failed validation |
| `QuantFidelityConnectionError` | — | Network / connection failure |
| `QuantFidelityAPIError` | Other 4xx/5xx | Unclassified server error |

```python
from quantfidelity.exceptions import (
    QuantFidelityAuthError,
    QuantFidelityNotFoundError,
    QuantFidelityValidationError,
    QuantFidelityConnectionError,
)

try:
    strategy.log_run("my-run", metrics={"sharpe": 1.2})
except QuantFidelityAuthError:
    print("Check QF_API_KEY.")
except QuantFidelityNotFoundError:
    print("Strategy slug not found. Check QF_STRATEGY_SLUG.")
except QuantFidelityValidationError as exc:
    print(f"Payload error: {exc}")
except QuantFidelityConnectionError:
    print("Cannot reach the server. Check QF_BASE_URL.")
```

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QF_API_KEY` | — | API authentication key |
| `QUANTFIDELITY_API_KEY` | — | Alternate API key variable |
| `QF_BASE_URL` | `http://localhost:8000` | Server base URL |
| `QUANTFIDELITY_BASE_URL` | `http://localhost:8000` | Alternate base URL variable |
| `QF_STRATEGY_SLUG` | — | Strategy slug for scripts/CI |

---

## CI/CD integration (GitHub Actions)

Add reliability score logging and shadow monitoring to your CI pipeline:

```yaml
# .github/workflows/strategy-reliability.yml
name: Strategy Reliability Check

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  reliability:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install QuantFidelity SDK
        run: pip install -e sdk/python

      - name: Run backtest and log to QuantFidelity
        env:
          QF_API_KEY: ${{ secrets.QF_API_KEY }}
          QF_BASE_URL: ${{ secrets.QF_BASE_URL }}
          QF_STRATEGY_SLUG: ${{ vars.QF_STRATEGY_SLUG }}
        run: |
          python sdk/python/examples/ci_ingest.py

      - name: Check shadow drift monitor
        env:
          QF_API_KEY: ${{ secrets.QF_API_KEY }}
          QF_BASE_URL: ${{ secrets.QF_BASE_URL }}
          QF_STRATEGY_SLUG: ${{ vars.QF_STRATEGY_SLUG }}
        run: |
          python - <<'EOF'
          import quantfidelity as qf, sys
          qf.init()
          result = qf.strategy("$QF_STRATEGY_SLUG").shadow_monitor()
          print("verdict:", result.get("verdict"))
          print("drift_score:", result.get("drift_score"))
          if result.get("drift_score", 0) > 0.7:
              print("High drift detected — review strategy before deployment.")
              sys.exit(1)
          EOF
```

---

## Shadow monitoring (M88)

The M88 shadow drift monitor compares backtest metrics against paper (or live)
run metrics to detect research-to-reality discrepancies.

```python
import quantfidelity as qf

qf.init()
strategy = qf.strategy("spy-trend-v2")

result = strategy.shadow_monitor()

print("verdict:        ", result["verdict"])
print("drift_score:    ", result["drift_score"])    # 0.0 (no drift) to 1.0 (max drift)
print("primary_concern:", result["primary_concern"])
```

### Interpreting results

| `verdict` | Meaning |
|-----------|---------|
| `NO_DRIFT` | Backtest and paper metrics align within tolerance |
| `MILD_DRIFT` | Minor discrepancies — monitor but no immediate action required |
| `DRIFT_DETECTED` | Meaningful gap between research and reality — review assumptions |
| `HIGH_DRIFT` | Severe divergence — pause live deployment and investigate |
| `INSUFFICIENT_DATA` | Not enough paper/live runs to compare yet |

### Key drift signals to watch

- **Sharpe ratio** drop > 30% from backtest to paper
- **Turnover** more than 2x higher in paper than backtest (cost blowout)
- **Max drawdown** more than 1.5x worse in paper (fat-tail exposure)
- **Volatility** significantly higher than backtest (regime change)

---

> QuantFidelity is a research reliability tool. Nothing in the SDK constitutes
> investment advice.
