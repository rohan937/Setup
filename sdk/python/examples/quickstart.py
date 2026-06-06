"""QuantFidelity SDK Quickstart example.

Shows the full research-to-monitoring workflow using the M89 module-level API.
Copy-paste friendly. Run after:
    cd sdk/python && pip install -e .
    export QF_API_KEY=qf_your_key_here
    export QF_BASE_URL=http://localhost:8000

# Not investment advice. Deterministic reliability tool.
"""
from __future__ import annotations

import os
import sys

# Ensure the SDK is importable when run from the examples/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import quantfidelity as qf
from quantfidelity.exceptions import (
    QuantFidelityAuthError,
    QuantFidelityNotFoundError,
)

# ── 1. Initialize the default client from environment variables ──────────── #
# Set QF_API_KEY and QF_BASE_URL before running, or pass them explicitly here.

qf.init(
    base_url=os.getenv("QF_BASE_URL", "http://localhost:8000"),
    api_key=os.getenv("QF_API_KEY"),
)

# ── 2. Test authentication ───────────────────────────────────────────────── #

try:
    auth_result = qf.test_auth()
    print("Auth OK:", auth_result)
except QuantFidelityAuthError as exc:
    print(f"Authentication failed: {exc}")
    print("Set QF_API_KEY to a valid API key and retry.")
    sys.exit(1)

# ── 3. List strategies ───────────────────────────────────────────────────── #

from quantfidelity import QuantFidelityClient  # noqa: E402

client = qf._get_default_client()  # type: ignore[attr-defined]
strategies = client.list_strategies()
print(f"\nFound {len(strategies)} strategies:")
for s in strategies[:5]:
    print(f"  {s.get('slug', s.get('id'))}  —  {s.get('name', 'Unnamed')}")

# ── 4. Get a strategy handle ─────────────────────────────────────────────── #

STRATEGY_SLUG = os.getenv("QF_STRATEGY_SLUG", "my-strategy-slug")

try:
    strategy = qf.strategy(STRATEGY_SLUG)
    print(f"\nStrategy handle: {strategy}")
except QuantFidelityNotFoundError:
    print(f"\nStrategy '{STRATEGY_SLUG}' not found. Set QF_STRATEGY_SLUG to an existing slug.")
    sys.exit(1)

# ── 5. Log a config snapshot ─────────────────────────────────────────────── #

config_result = strategy.log_config(
    "v1.0-config",
    params={
        "lookback_days": 20,
        "entry_zscore": 2.0,
        "exit_zscore": 0.5,
        "max_position_size": 0.10,
        "rebalance_frequency": "weekly",
    },
    assumptions={
        "commission_bps": 5,
        "slippage_bps": 3,
        "fill_model": "vwap",
        "borrow_cost_bps": 0,
    },
    version_label="v1.0",
)
print("\nConfig logged:", config_result.get("summary", config_result))

# ── 6. Log a universe snapshot ───────────────────────────────────────────── #

universe_result = strategy.log_universe(
    "sp500-2024-q1",
    symbols=["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "BRK.B"],
    metadata={"index": "S&P 500", "as_of": "2024-03-31"},
    version_label="v1.0",
)
print("Universe logged:", universe_result.get("summary", universe_result))

# ── 7. Log a backtest run with full metrics ──────────────────────────────── #

run_result = strategy.log_run(
    "backtest-2024-q1",
    run_type="backtest",
    metrics={
        "sharpe": 1.42,
        "annual_return": 0.187,
        "volatility": 0.132,
        "max_drawdown": -0.118,
        "turnover": 0.38,
        "trade_count": 462,
        "win_rate": 0.54,
    },
    params={
        "lookback_days": 20,
        "entry_zscore": 2.0,
        "exit_zscore": 0.5,
    },
    assumptions={
        "commission_bps": 5,
        "slippage_bps": 3,
        "fill_model": "vwap",
    },
    version_label="v1.0",
    notes="Full in-sample backtest Q1 2024. Walk-forward validated.",
)
print("Run logged:", run_result.get("summary", run_result))

# ── 8. Generate a reliability report ─────────────────────────────────────── #

report = strategy.generate_report()
print("\nReport:", report)

# ── 9. Refresh the reliability score ─────────────────────────────────────── #

score = strategy.refresh_score()
print("Reliability score:", score)

# ── 10. Shadow monitor (M88) ─────────────────────────────────────────────── #

monitor = strategy.shadow_monitor()
print("\nShadow monitor result:")
print(f"  verdict:         {monitor.get('verdict')}")
print(f"  drift_score:     {monitor.get('drift_score')}")
print(f"  primary_concern: {monitor.get('primary_concern')}")

# Not investment advice. Deterministic reliability tool.
