#!/usr/bin/env python3
"""AAPL Mean Reversion — evidence bundle example.

Demonstrates how to build and submit a full evidence bundle for the AAPL
Mean Reversion strategy using the QuantFidelity Python SDK.

Usage::

    # Just build and print the payload (no server required):
    python examples/aapl_mean_reversion_bundle.py

    # Build AND send to a local QuantFidelity server:
    RUN_QF_EXAMPLE=1 python examples/aapl_mean_reversion_bundle.py

    # Send to a custom server:
    QF_BASE_URL=http://qf.myteam.internal RUN_QF_EXAMPLE=1 \\
        python examples/aapl_mean_reversion_bundle.py

Env vars:
  RUN_QF_EXAMPLE   — Set to "1" to POST the bundle to the server.
  QF_BASE_URL      — QuantFidelity server URL (default: http://localhost:8000).
  QF_STRATEGY_ID   — Strategy UUID to ingest into.  Required when
                     RUN_QF_EXAMPLE=1.

Notes:
  - No live market data is used.
  - No AI involved — all metrics are hardcoded demo values.
  - Not investment advice.
"""
from __future__ import annotations

import json
import os
import sys

# Allow running directly from the examples/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quantfidelity import EvidenceBundle, QuantFidelityClient
from quantfidelity.exceptions import QuantFidelityError


# ---------------------------------------------------------------------------
# Build the evidence bundle
# ---------------------------------------------------------------------------

bundle = (
    EvidenceBundle()
    # ── Strategy version ──────────────────────────────────────────────
    .with_strategy_version(
        "v2.0.0",
        git_commit="c3d4e5f6a7b8",
        branch_name="main",
        code_path="strategies/aapl_mean_reversion.py",
        signal_name="return_zscore_mean_reversion",
        signal_description="Mean reversion signal using 20-day return z-score",
    )
    # ── Config snapshot ───────────────────────────────────────────────
    .with_config_snapshot(
        "baseline-config-v2",
        strategy_version_label="v2.0.0",
        config_json={
            "params": {
                "lookback_days": 20,
                "zscore_entry_threshold": 2.0,
                "zscore_exit_threshold": 0.5,
                "max_position_size": 0.05,
            },
            "assumptions": {
                "transaction_cost_bps": 5,
                "fill_model": "mid_plus_5bps",
                "borrow_cost_bps": 10,
                "slippage_model": "linear",
            },
        },
    )
    # ── Universe snapshot ─────────────────────────────────────────────
    .with_universe_snapshot(
        "us-large-cap-2024-q1",
        strategy_version_label="v2.0.0",
        symbols=["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA"],
        metadata_json={
            "universe_type": "US_LARGE_CAP",
            "rebalance_freq": "monthly",
            "index_reference": "SP500",
        },
    )
    # ── Signal snapshot ───────────────────────────────────────────────
    .with_signal_snapshot(
        "z-score-signals-2024-01-02",
        strategy_version_label="v2.0.0",
        universe_snapshot_label="us-large-cap-2024-q1",
        signal_name="return_zscore_mean_reversion",
        signal_column="signal",
        rows=[
            {"symbol": "AAPL",  "timestamp": "2024-01-02", "signal":  1.53},
            {"symbol": "MSFT",  "timestamp": "2024-01-02", "signal": -0.42},
            {"symbol": "NVDA",  "timestamp": "2024-01-02", "signal":  2.11},
            {"symbol": "GOOGL", "timestamp": "2024-01-02", "signal": -1.07},
            {"symbol": "META",  "timestamp": "2024-01-02", "signal":  0.35},
            {"symbol": "AMZN",  "timestamp": "2024-01-02", "signal": -0.89},
            {"symbol": "TSLA",  "timestamp": "2024-01-02", "signal":  1.74},
        ],
    )
    # ── Dataset ───────────────────────────────────────────────────────
    .with_dataset(
        "AAPL Mean Reversion OHLCV",
        description="Daily OHLCV data used for the AAPL mean reversion backtest",
        asset_class="equity",
        dataset_type="equity_prices",
        source_type="manual_json",
    )
    # ── Dataset snapshot ──────────────────────────────────────────────
    .with_dataset_snapshot(
        snapshot_label="ohlcv-2024-01-02",
        rows=[
            {
                "symbol": "AAPL",
                "timestamp": "2024-01-02",
                "open":   185.55,
                "high":   188.91,
                "low":    184.81,
                "close":  185.64,
                "volume": 72_043_900,
            },
            {
                "symbol": "MSFT",
                "timestamp": "2024-01-02",
                "open":   374.19,
                "high":   375.66,
                "low":    369.27,
                "close":  374.02,
                "volume": 20_481_300,
            },
        ],
    )
    # ── Strategy run ──────────────────────────────────────────────────
    .with_strategy_run(
        "backtest-q1-2024-v2",
        run_type="backtest",
        strategy_version_label="v2.0.0",
        dataset_snapshot_label="ohlcv-2024-01-02",
        universe_snapshot_label="us-large-cap-2024-q1",
        signal_snapshot_label="z-score-signals-2024-01-02",
        params_json={
            "lookback_days": 20,
            "zscore_entry_threshold": 2.0,
            "zscore_exit_threshold": 0.5,
        },
        assumptions_json={
            "transaction_cost_bps": 5,
            "fill_model": "mid_plus_5bps",
        },
        metrics_json={
            "sharpe_ratio":          1.62,
            "annual_return":         0.184,
            "max_drawdown":         -0.109,
            "calmar_ratio":          1.69,
            "win_rate":              0.54,
            "num_trades":            142,
            "avg_holding_days":      4.2,
            "turnover_annual":       0.38,
        },
        universe_name="US Large Cap (SP500 top 50)",
        notes=(
            "Baseline backtest v2 with tighter exit threshold and updated "
            "fill model.  Not for live trading."
        ),
    )
    # ── Actions ───────────────────────────────────────────────────────
    .with_actions(
        run_backtest_audit=True,
        compute_reliability_score=True,
        generate_strategy_report=False,
        generate_alerts=False,
    )
)


# ---------------------------------------------------------------------------
# Print payload
# ---------------------------------------------------------------------------

print("=" * 70)
print("AAPL Mean Reversion — Evidence Bundle Payload")
print("=" * 70)
print(bundle.to_json(indent=2))
print()
print(f"Sections included:  {bundle.sections()}")
print(f"Empty:              {bundle.is_empty()}")

# ---------------------------------------------------------------------------
# Optionally send to the server
# ---------------------------------------------------------------------------

if os.environ.get("RUN_QF_EXAMPLE") == "1":
    strategy_id = os.environ.get("QF_STRATEGY_ID", "").strip()
    if not strategy_id:
        print(
            "\nError: set QF_STRATEGY_ID env var to the UUID of the strategy to ingest into.",
            file=sys.stderr,
        )
        sys.exit(1)

    base_url = os.environ.get("QF_BASE_URL", "http://localhost:8000")
    client = QuantFidelityClient(base_url=base_url)

    print(f"\nSending bundle to {base_url} for strategy {strategy_id} …")
    try:
        result = client.ingest_evidence_bundle(strategy_id, bundle)
    except QuantFidelityError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 70)
    print("Response:")
    print("=" * 70)
    print(json.dumps(result, indent=2, default=str))
    print()
    print(f"Created:  {result.get('created_count', '?')}")
    print(f"Reused:   {result.get('reused_count', '?')}")
    print(f"Actions:  {result.get('actions_run', [])}")
    print(f"Summary:  {result.get('summary', '')}")
else:
    print(
        "\nTo send this bundle to a running QuantFidelity server, set:\n"
        "  export RUN_QF_EXAMPLE=1\n"
        "  export QF_STRATEGY_ID=<your-strategy-uuid>\n"
        "  export QF_BASE_URL=http://localhost:8000   # optional\n"
        "Then re-run this script."
    )
