"""Paper run and shadow monitor demo.

Demonstrates logging both a backtest run and a paper run, then comparing
them via the shadow drift monitor (M88).

This demo intentionally creates drift in the paper run (higher turnover,
worse drawdown, lower Sharpe) to show how the shadow monitor catches
research-to-reality discrepancies.

Run after:
    cd sdk/python && pip install -e .
    export QF_API_KEY=qf_your_key_here
    export QF_BASE_URL=http://localhost:8000
    export QF_STRATEGY_SLUG=my-strategy-slug

# Not investment advice. Deterministic reliability tool.
"""
from __future__ import annotations

import os
import sys

# Ensure the SDK is importable when run from the examples/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import quantfidelity as qf
from quantfidelity.exceptions import QuantFidelityAuthError, QuantFidelityNotFoundError

# ── 1. Initialize the client ─────────────────────────────────────────────── #

qf.init(
    base_url=os.getenv("QF_BASE_URL", "http://localhost:8000"),
    api_key=os.getenv("QF_API_KEY"),
)

try:
    qf.test_auth()
    print("Authenticated successfully.")
except QuantFidelityAuthError as exc:
    print(f"Authentication failed: {exc}")
    sys.exit(1)

# ── 2. Get a strategy handle ─────────────────────────────────────────────── #

STRATEGY_SLUG = os.getenv("QF_STRATEGY_SLUG", "my-strategy-slug")

try:
    strategy = qf.strategy(STRATEGY_SLUG)
    print(f"Strategy handle: {strategy}\n")
except QuantFidelityNotFoundError:
    print(f"Strategy '{STRATEGY_SLUG}' not found. Set QF_STRATEGY_SLUG.")
    sys.exit(1)

# ── 3. Log a backtest run with clean metrics ─────────────────────────────── #
# These are the "research" numbers — what the strategy looked like in simulation.

print("Logging backtest run...")
backtest_result = strategy.log_run(
    "backtest-2024-full-year",
    run_type="backtest",
    metrics={
        "sharpe": 1.40,
        "annual_return": 0.182,
        "volatility": 0.140,
        "max_drawdown": -0.120,
        "turnover": 0.35,
        "trade_count": 450,
        "win_rate": 0.55,
    },
    params={
        "lookback_days": 20,
        "entry_zscore": 2.0,
        "exit_zscore": 0.5,
        "max_position_size": 0.10,
    },
    assumptions={
        "commission_bps": 5,
        "slippage_bps": 3,
        "fill_model": "vwap",
    },
    version_label="v1.0",
    notes="Full-year 2024 backtest. Primary evaluation run.",
)
print(f"  Backtest logged: {backtest_result.get('summary', 'OK')}")

# ── 4. Log a paper run with intentionally drifted metrics ────────────────── #
# Real paper trading showed degraded performance — this is the signal to watch.

print("\nLogging paper run (with drift)...")
paper_result = strategy.log_paper_run(
    "paper-2025-q1",
    metrics={
        "sharpe": 0.65,         # was 1.40 in backtest — significant drop
        "annual_return": 0.091,
        "volatility": 0.220,    # was 0.14 — higher realized vol
        "max_drawdown": -0.230, # was -0.12 — nearly double the drawdown
        "turnover": 0.95,       # was 0.35 — transaction cost blowout
        "trade_count": 890,     # was 450 — far more churn
        "win_rate": 0.46,
    },
    params={
        "lookback_days": 20,
        "entry_zscore": 2.0,
        "exit_zscore": 0.5,
        "max_position_size": 0.10,
    },
    assumptions={
        "commission_bps": 8,    # actual costs higher than assumed
        "slippage_bps": 7,
        "fill_model": "market",
    },
    version_label="v1.0",
    notes="Q1 2025 paper run. Observed drift from backtest — higher costs and vol.",
)
print(f"  Paper run logged: {paper_result.get('summary', 'OK')}")

# ── 5. Call shadow_monitor() ─────────────────────────────────────────────── #
# M88 shadow drift monitor compares backtest vs. paper metrics and flags drift.

print("\nRunning shadow drift monitor (M88)...")
monitor = strategy.shadow_monitor()

# ── 6. Print the result ───────────────────────────────────────────────────── #

print("\n" + "=" * 60)
print("SHADOW MONITOR RESULT")
print("=" * 60)
print(f"  verdict:         {monitor.get('verdict', 'N/A')}")
print(f"  drift_score:     {monitor.get('drift_score', 'N/A')}")
print(f"  primary_concern: {monitor.get('primary_concern', 'N/A')}")

details = monitor.get("details") or monitor.get("drift_details")
if details:
    print("\n  Drift details:")
    if isinstance(details, dict):
        for key, val in details.items():
            print(f"    {key}: {val}")
    elif isinstance(details, list):
        for item in details:
            print(f"    - {item}")

alerts = monitor.get("alerts", [])
if alerts:
    print(f"\n  Alerts ({len(alerts)}):")
    for alert in alerts:
        print(f"    [{alert.get('severity', '?').upper()}] {alert.get('message', alert)}")

print("=" * 60)

# Expected outcome with the values above:
# - drift_score > 0.5 (high drift)
# - primary_concern: "turnover" or "volatility" or "max_drawdown"
# - verdict: "DRIFT_DETECTED" or "HIGH_DRIFT"

print("\nInterpretation:")
print("  Sharpe dropped from 1.40 -> 0.65 (-54%)  : cost & slippage blowout")
print("  Turnover nearly tripled (0.35 -> 0.95)   : unexpected signal frequency")
print("  Max drawdown nearly doubled (-0.12->-0.23): fat-tail exposure in live mkt")
print("  Review strategy assumptions before deploying further capital.")

# Not investment advice. Deterministic reliability tool.
