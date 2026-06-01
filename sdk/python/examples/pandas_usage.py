"""Pandas integration example.

Demonstrates building an evidence bundle from pandas DataFrames using the
SDK's DataFrame helpers.

Requirements:
    pip install quantfidelity[pandas]

No server required by default.
"""
from __future__ import annotations

import json
import os
import sys

# Ensure the SDK is importable when run from the examples/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import pandas as pd
except ImportError:
    print("pandas is not installed.")
    print("Install it with:  pip install quantfidelity[pandas]")
    sys.exit(0)

from quantfidelity.bundle import EvidenceBundle
from quantfidelity.dataframe import is_dataframe_like, rows_from_table

# ── Build toy OHLCV DataFrame ─────────────────────────────────────────────── #

ohlcv_df = pd.DataFrame(
    [
        {
            "symbol": "AAPL",
            "date": pd.Timestamp("2024-01-02"),
            "open": 184.22,
            "high": 185.88,
            "low": 183.43,
            "close": 185.52,
            "volume": 71_717_800,
        },
        {
            "symbol": "AAPL",
            "date": pd.Timestamp("2024-01-03"),
            "open": 184.22,
            "high": 185.75,
            "low": 182.73,
            "close": 184.25,
            "volume": 58_093_300,
        },
        {
            "symbol": "MSFT",
            "date": pd.Timestamp("2024-01-02"),
            "open": 374.02,
            "high": 376.18,
            "low": 372.95,
            "close": 374.51,
            "volume": 18_902_100,
        },
        {
            "symbol": "MSFT",
            "date": pd.Timestamp("2024-01-03"),
            "open": 372.10,
            "high": 374.00,
            "low": 369.88,
            "close": 370.96,
            "volume": 22_115_400,
        },
    ]
)

# ── Build toy signal DataFrame ─────────────────────────────────────────────── #

signal_df = pd.DataFrame(
    [
        {"symbol": "AAPL", "date": pd.Timestamp("2024-01-02"), "signal": 0.23},
        {"symbol": "AAPL", "date": pd.Timestamp("2024-01-03"), "signal": -0.45},
        {"symbol": "MSFT", "date": pd.Timestamp("2024-01-02"), "signal": 1.12},
        {"symbol": "MSFT", "date": pd.Timestamp("2024-01-03"), "signal": 0.67},
    ]
)

# ── Demonstrate DataFrame detection ──────────────────────────────────────── #

print(f"ohlcv_df is DataFrame-like: {is_dataframe_like(ohlcv_df)}")
print(f"plain list is DataFrame-like: {is_dataframe_like([])}")

# Manually convert to records to inspect
ohlcv_rows = rows_from_table(ohlcv_df)
print(f"\nOHLCV rows[0]: {ohlcv_rows[0]}")
print(f"  date type: {type(ohlcv_rows[0]['date'])}")  # should be str

signal_rows = rows_from_table(signal_df)
print(f"\nSignal rows[0]: {signal_rows[0]}")

# ── Build the EvidenceBundle using DataFrame helpers ──────────────────────── #

bundle = (
    EvidenceBundle()
    .with_strategy_version("v1.0.0", signal_name="z_score")
    .with_dataset(
        "US Equities OHLCV",
        asset_class="equity",
        dataset_type="equity_prices",
        source_type="sdk_table",
    )
    .with_dataset_snapshot_from_table("ohlcv-2024-q1", ohlcv_df)
    .with_universe_from_symbols(
        "us-large-cap",
        ohlcv_df["symbol"].unique().tolist(),
        strategy_version_label="v1.0.0",
    )
    .with_signal_snapshot_from_table(
        "z-score-signals-2024-q1",
        signal_df,
        signal_name="z_score",
        signal_column="signal",
        strategy_version_label="v1.0.0",
        universe_snapshot_label="us-large-cap",
    )
    .with_backtest_run(
        "backtest-pandas-demo",
        metrics={"sharpe": 1.45, "max_drawdown": -0.08},
        strategy_version_label="v1.0.0",
        dataset_snapshot_label="ohlcv-2024-q1",
        universe_snapshot_label="us-large-cap",
        signal_snapshot_label="z-score-signals-2024-q1",
    )
    .with_actions(run_backtest_audit=True, compute_reliability_score=True)
)

print("\n=== Evidence Bundle (pandas DataFrames → list[dict]) ===")
payload = bundle.to_dict()

# Show the dataset snapshot rows (dates should be ISO strings now)
ds_rows = payload["dataset_snapshot"]["rows"]
print(f"\nDataset snapshot rows ({len(ds_rows)} rows):")
for r in ds_rows:
    print(f"  {r}")

sig_rows = payload["signal_snapshot"]["rows"]
print(f"\nSignal snapshot rows ({len(sig_rows)} rows):")
for r in sig_rows:
    print(f"  {r}")

print(f"\nSections: {bundle.sections()}")
print(f"Valid JSON: {bool(bundle.to_json())}")

# Validate
issues = bundle.validate()
if issues:
    print(f"\nValidation issues: {issues}")
else:
    print("\nValidation: OK")

print("\nFull JSON payload (truncated to 1000 chars):")
print(bundle.to_json()[:1000], "...")
