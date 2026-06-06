"""QuantFidelity SDK — Jupyter notebook demo (cell-by-cell format).

Shows how the SDK looks inside a Jupyter notebook using # %% cell markers.
This is a plain .py file — open it in VS Code (Jupyter extension) or
copy each cell into an actual notebook.

Run after:
    pip install quantfidelity
    export QF_API_KEY=qf_your_key_here
    export QF_BASE_URL=http://localhost:8000

# Not investment advice. Deterministic reliability tool.
"""

# %% [markdown]
# ## QuantFidelity Quickstart
# Log a backtest, check the shadow drift monitor, refresh reliability score.

# %% Cell 1: Install (run once)
# !pip install -e ../  # from within sdk/python/examples/

# %% Cell 2: Initialize
import quantfidelity as qf

qf.init()  # reads QF_API_KEY and QF_BASE_URL from environment
qf.test_auth()

# %% Cell 3: Get a strategy handle
strategy = qf.strategy("my-strategy-slug")
strategy

# %% Cell 4: Log a config snapshot
strategy.log_config(
    "v1.0-config",
    params={"lookback_days": 20, "entry_zscore": 2.0, "exit_zscore": 0.5},
    assumptions={"commission_bps": 5, "slippage_bps": 3, "fill_model": "vwap"},
    version_label="v1.0",
)

# %% Cell 5: Log a backtest run
result = strategy.log_run(
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
    params={"lookback_days": 20, "entry_zscore": 2.0},
    version_label="v1.0",
    notes="Q1 2024 full backtest.",
)
result

# %% Cell 6: Log a paper run
paper = strategy.log_paper_run(
    "paper-2025-q1",
    metrics={
        "sharpe": 1.21,
        "annual_return": 0.151,
        "volatility": 0.158,
        "max_drawdown": -0.145,
        "turnover": 0.44,
        "trade_count": 510,
        "win_rate": 0.52,
    },
    notes="Q1 2025 paper run — within acceptable drift range.",
)
paper

# %% Cell 7: Shadow drift monitor (M88)
monitor = strategy.shadow_monitor()

print("verdict:        ", monitor.get("verdict"))
print("drift_score:    ", monitor.get("drift_score"))
print("primary_concern:", monitor.get("primary_concern"))

# %% Cell 8: Refresh reliability score
score = strategy.refresh_score()
score

# %% [markdown]
# ---
# Not investment advice. Deterministic reliability tool.
