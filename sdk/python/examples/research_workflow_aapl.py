"""AAPL Mean Reversion — QuantResearchWorkflow example.

Build a full evidence bundle using the high-level research workflow API.
No pandas required.  No server required by default.

Environment variables:
    RUN_QF_EXAMPLE=1   Set to actually POST to a live server.
    QF_BASE_URL        Server base URL (default: http://localhost:8000).
    QF_STRATEGY_ID     UUID of the strategy to submit to.
"""
from __future__ import annotations

import json
import os
import sys

# Ensure the SDK is importable when run from the examples/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quantfidelity import QuantFidelityClient, QuantResearchWorkflow
from quantfidelity.exceptions import QuantFidelityError

# ── Build the bundle ─────────────────────────────────────────────────────── #

wf = (
    QuantResearchWorkflow(strategy_name="AAPL Mean Reversion", version_label="v3.0.0")
    .set_version(
        "v3.0.0",
        git_commit="d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3",
        branch_name="main",
        code_path="strategies/aapl_mean_reversion.py",
        signal_name="z_score",
        signal_description="Rolling z-score of daily returns vs 20-day window",
    )
    .set_config(
        params={
            "lookback_days": 20,
            "entry_zscore": 2.0,
            "exit_zscore": 0.5,
            "max_position_size": 0.10,
        },
        assumptions={
            "transaction_cost_bps": 5,
            "fill_model": "next_open",
            "borrow_cost_bps": 30,
            "slippage_model": "fixed_1bps",
        },
        label="baseline-config-v3",
    )
    .set_universe(
        ["AAPL", "MSFT", "NVDA", "GOOGL"],
        label="us-large-cap",
        metadata={
            "universe_type": "large_cap_us",
            "rebalance_freq": "quarterly",
            "index_reference": "SP500",
        },
    )
    .set_dataset(
        "AAPL OHLCV",
        rows_or_df=[
            {
                "symbol": "AAPL",
                "date": "2024-01-02",
                "open": 184.22,
                "high": 185.88,
                "low": 183.43,
                "close": 185.52,
                "volume": 71717800,
            },
            {
                "symbol": "AAPL",
                "date": "2024-01-03",
                "open": 184.22,
                "high": 185.75,
                "low": 182.73,
                "close": 184.25,
                "volume": 58093300,
            },
            {
                "symbol": "AAPL",
                "date": "2024-01-04",
                "open": 182.15,
                "high": 183.09,
                "low": 180.63,
                "close": 181.91,
                "volume": 55859300,
            },
        ],
        snapshot_label="ohlcv-2024-q1",
    )
    .set_signals(
        rows_or_df=[
            {"symbol": "AAPL", "date": "2024-01-02", "signal": 0.23},
            {"symbol": "AAPL", "date": "2024-01-03", "signal": -0.45},
            {"symbol": "AAPL", "date": "2024-01-04", "signal": -1.87},
        ],
        signal_name="z_score",
        signal_column="signal",
        label="z-score-signals",
    )
    .set_backtest_result(
        run_name="backtest-aapl-2024-q1",
        params={"lookback_days": 20, "entry_zscore": 2.0},
        assumptions={"transaction_cost_bps": 5},
        metrics={
            "sharpe_ratio": 1.62,
            "annualised_return": 0.183,
            "max_drawdown": -0.072,
            "calmar_ratio": 2.54,
            "win_rate": 0.58,
            "num_trades": 47,
        },
    )
    .enable_actions(
        run_backtest_audit=True,
        compute_reliability_score=True,
    )
)

bundle = wf.to_bundle()

print("=== AAPL Mean Reversion — Research Workflow Bundle ===")
print(wf.to_json(indent=2)[:2000])
print("...")
print(f"\nSections: {bundle.sections()}")

issues = wf.validate()
if issues:
    print(f"\nValidation issues: {issues}")
else:
    print("\nValidation: OK")

# ── Optionally POST to a live server ─────────────────────────────────────── #

if os.environ.get("RUN_QF_EXAMPLE") == "1":
    strategy_id = os.environ.get("QF_STRATEGY_ID")
    base_url = os.environ.get("QF_BASE_URL", "http://localhost:8000")

    if not strategy_id:
        print("\nError: set QF_STRATEGY_ID to POST the bundle.", file=sys.stderr)
        sys.exit(1)

    client = QuantFidelityClient(base_url=base_url)
    try:
        result = client.ingest_bundle(strategy_id, bundle)
        print("\n=== Server response ===")
        print(json.dumps(result, indent=2, default=str))
    except QuantFidelityError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        sys.exit(1)
else:
    print("\n(Set RUN_QF_EXAMPLE=1 to POST to a live server.)")
