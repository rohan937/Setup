"""Tests for EvidenceBundle builder (sdk/python/quantfidelity/bundle.py)."""
from __future__ import annotations

import json

import pytest

from quantfidelity.bundle import EvidenceBundle
from quantfidelity.exceptions import QuantFidelityValidationError


# ---------------------------------------------------------------------------
# Empty bundle
# ---------------------------------------------------------------------------


def test_empty_bundle_serializes_to_empty_dict():
    b = EvidenceBundle()
    assert b.to_dict() == {}


def test_empty_bundle_is_empty():
    assert EvidenceBundle().is_empty()


def test_empty_bundle_has_no_sections():
    assert EvidenceBundle().sections() == []


def test_empty_bundle_to_json():
    b = EvidenceBundle()
    assert b.to_json() == "{}"


# ---------------------------------------------------------------------------
# with_strategy_version
# ---------------------------------------------------------------------------


def test_with_strategy_version_minimal():
    b = EvidenceBundle().with_strategy_version("v1.0")
    d = b.to_dict()
    assert d["strategy_version"]["version_label"] == "v1.0"


def test_with_strategy_version_full():
    b = EvidenceBundle().with_strategy_version(
        "v2.0",
        git_commit="abc123",
        branch_name="main",
        code_path="strategies/aapl.py",
        signal_name="z_score",
        signal_description="Mean reversion z-score",
    )
    sv = b.to_dict()["strategy_version"]
    assert sv["version_label"] == "v2.0"
    assert sv["git_commit"] == "abc123"
    assert sv["branch_name"] == "main"
    assert sv["code_path"] == "strategies/aapl.py"
    assert sv["signal_name"] == "z_score"
    assert sv["signal_description"] == "Mean reversion z-score"


def test_with_strategy_version_omits_none_fields():
    b = EvidenceBundle().with_strategy_version("v1.0")
    sv = b.to_dict()["strategy_version"]
    assert "git_commit" not in sv
    assert "branch_name" not in sv


def test_with_strategy_version_empty_label_raises():
    with pytest.raises(QuantFidelityValidationError):
        EvidenceBundle().with_strategy_version("")


def test_with_strategy_version_blank_label_raises():
    with pytest.raises(QuantFidelityValidationError):
        EvidenceBundle().with_strategy_version("   ")


# ---------------------------------------------------------------------------
# with_config_snapshot
# ---------------------------------------------------------------------------


def test_with_config_snapshot_minimal():
    b = EvidenceBundle().with_config_snapshot(
        "config-v1",
        config_json={"params": {"lookback": 20}},
    )
    cs = b.to_dict()["config_snapshot"]
    assert cs["label"] == "config-v1"
    assert cs["config_json"]["params"]["lookback"] == 20


def test_with_config_snapshot_with_version_label():
    b = EvidenceBundle().with_config_snapshot(
        "config-v1",
        config_json={"params": {}},
        strategy_version_label="v1.0",
    )
    assert b.to_dict()["config_snapshot"]["strategy_version_label"] == "v1.0"


def test_config_json_must_be_dict_not_list():
    with pytest.raises(QuantFidelityValidationError, match="dict"):
        EvidenceBundle().with_config_snapshot("cfg", config_json=[1, 2, 3])


def test_config_json_must_be_dict_not_string():
    with pytest.raises(QuantFidelityValidationError, match="dict"):
        EvidenceBundle().with_config_snapshot("cfg", config_json="params={}")


def test_config_json_must_be_dict_not_none():
    with pytest.raises((QuantFidelityValidationError, TypeError)):
        EvidenceBundle().with_config_snapshot("cfg", config_json=None)


def test_config_snapshot_empty_label_raises():
    with pytest.raises(QuantFidelityValidationError):
        EvidenceBundle().with_config_snapshot("", config_json={})


# ---------------------------------------------------------------------------
# with_universe_snapshot
# ---------------------------------------------------------------------------


def test_with_universe_snapshot_minimal():
    b = EvidenceBundle().with_universe_snapshot("uni-v1", symbols=["AAPL", "MSFT"])
    us = b.to_dict()["universe_snapshot"]
    assert us["label"] == "uni-v1"
    assert us["symbols"] == ["AAPL", "MSFT"]


def test_universe_symbols_must_be_nonempty_list():
    with pytest.raises(QuantFidelityValidationError, match="non-empty"):
        EvidenceBundle().with_universe_snapshot("uni", symbols=[])


def test_universe_symbols_must_be_list_not_string():
    with pytest.raises(QuantFidelityValidationError, match="list"):
        EvidenceBundle().with_universe_snapshot("uni", symbols="AAPL,MSFT")


def test_universe_snapshot_empty_label_raises():
    with pytest.raises(QuantFidelityValidationError):
        EvidenceBundle().with_universe_snapshot("", symbols=["AAPL"])


def test_universe_snapshot_with_metadata():
    b = EvidenceBundle().with_universe_snapshot(
        "uni-v1",
        symbols=["AAPL"],
        metadata_json={"universe_type": "sp500"},
    )
    assert b.to_dict()["universe_snapshot"]["metadata_json"]["universe_type"] == "sp500"


# ---------------------------------------------------------------------------
# with_signal_snapshot
# ---------------------------------------------------------------------------


def test_with_signal_snapshot_minimal():
    rows = [{"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 1.0}]
    b = EvidenceBundle().with_signal_snapshot("sig-v1", rows=rows)
    ss = b.to_dict()["signal_snapshot"]
    assert ss["label"] == "sig-v1"
    assert len(ss["rows"]) == 1


def test_signal_rows_must_be_nonempty_list():
    with pytest.raises(QuantFidelityValidationError, match="non-empty"):
        EvidenceBundle().with_signal_snapshot("sig", rows=[])


def test_signal_rows_must_be_list_not_string():
    with pytest.raises(QuantFidelityValidationError, match="list"):
        EvidenceBundle().with_signal_snapshot("sig", rows="not a list")


def test_signal_snapshot_links():
    rows = [{"symbol": "AAPL", "signal": 1.0}]
    b = EvidenceBundle().with_signal_snapshot(
        "sig-v1",
        rows=rows,
        strategy_version_label="v1.0",
        universe_snapshot_label="uni-v1",
        signal_name="z_score",
        signal_column="z_score",
    )
    ss = b.to_dict()["signal_snapshot"]
    assert ss["strategy_version_label"] == "v1.0"
    assert ss["universe_snapshot_label"] == "uni-v1"
    assert ss["signal_name"] == "z_score"
    assert ss["signal_column"] == "z_score"


# ---------------------------------------------------------------------------
# with_dataset
# ---------------------------------------------------------------------------


def test_with_dataset_minimal():
    b = EvidenceBundle().with_dataset("AAPL OHLCV")
    d = b.to_dict()["dataset"]
    assert d["name"] == "AAPL OHLCV"
    assert d["asset_class"] == "equity"
    assert d["dataset_type"] == "equity_prices"
    assert d["source_type"] == "csv_upload"


def test_with_dataset_custom_fields():
    b = EvidenceBundle().with_dataset(
        "FX Rates",
        asset_class="fx",
        dataset_type="fx_rates",
        source_type="api",
        description="Daily FX rates",
    )
    d = b.to_dict()["dataset"]
    assert d["asset_class"] == "fx"
    assert d["description"] == "Daily FX rates"


def test_dataset_empty_name_raises():
    with pytest.raises(QuantFidelityValidationError):
        EvidenceBundle().with_dataset("")


# ---------------------------------------------------------------------------
# with_dataset_snapshot
# ---------------------------------------------------------------------------


def test_with_dataset_snapshot_minimal():
    rows = [{"symbol": "AAPL", "close": 100.0}]
    b = EvidenceBundle().with_dataset_snapshot(rows=rows)
    ds = b.to_dict()["dataset_snapshot"]
    assert len(ds["rows"]) == 1


def test_with_dataset_snapshot_with_label():
    b = EvidenceBundle().with_dataset_snapshot(
        rows=[{"x": 1}], snapshot_label="2024-q1"
    )
    assert b.to_dict()["dataset_snapshot"]["snapshot_label"] == "2024-q1"


def test_dataset_snapshot_rows_must_be_nonempty_list():
    with pytest.raises(QuantFidelityValidationError, match="non-empty"):
        EvidenceBundle().with_dataset_snapshot(rows=[])


def test_dataset_snapshot_rows_must_be_list_not_string():
    with pytest.raises(QuantFidelityValidationError, match="list"):
        EvidenceBundle().with_dataset_snapshot(rows="not a list")


# ---------------------------------------------------------------------------
# with_strategy_run
# ---------------------------------------------------------------------------


def test_with_strategy_run_minimal():
    b = EvidenceBundle().with_strategy_run("backtest-q1", run_type="backtest")
    sr = b.to_dict()["strategy_run"]
    assert sr["run_name"] == "backtest-q1"
    assert sr["run_type"] == "backtest"
    assert sr["status"] == "completed"


def test_with_strategy_run_full():
    b = EvidenceBundle().with_strategy_run(
        "bt-q1",
        run_type="backtest",
        status="completed",
        params_json={"lookback": 20},
        assumptions_json={"cost_bps": 5},
        metrics_json={"sharpe": 1.4, "max_drawdown": -0.12},
        universe_name="SP500",
        notes="Baseline run",
        strategy_version_label="v1.0",
        dataset_snapshot_label="prices-q1",
        universe_snapshot_label="sp500-q1",
        signal_snapshot_label="signals-q1",
    )
    sr = b.to_dict()["strategy_run"]
    assert sr["metrics_json"]["sharpe"] == 1.4
    assert sr["strategy_version_label"] == "v1.0"
    assert sr["dataset_snapshot_label"] == "prices-q1"


def test_strategy_run_empty_name_raises():
    with pytest.raises(QuantFidelityValidationError):
        EvidenceBundle().with_strategy_run("", run_type="backtest")


def test_strategy_run_none_fields_omitted():
    b = EvidenceBundle().with_strategy_run("bt", run_type="backtest")
    sr = b.to_dict()["strategy_run"]
    assert "params_json" not in sr
    assert "metrics_json" not in sr
    assert "notes" not in sr


# ---------------------------------------------------------------------------
# with_actions
# ---------------------------------------------------------------------------


def test_with_actions_defaults_all_false():
    b = EvidenceBundle().with_actions()
    a = b.to_dict()["actions"]
    assert a["run_backtest_audit"] is False
    assert a["compute_reliability_score"] is False
    assert a["generate_strategy_report"] is False
    assert a["generate_alerts"] is False


def test_with_actions_selective():
    b = EvidenceBundle().with_actions(
        run_backtest_audit=True, compute_reliability_score=True
    )
    a = b.to_dict()["actions"]
    assert a["run_backtest_audit"] is True
    assert a["compute_reliability_score"] is True
    assert a["generate_strategy_report"] is False
    assert a["generate_alerts"] is False


def test_with_actions_all_true():
    b = EvidenceBundle().with_actions(
        run_backtest_audit=True,
        compute_reliability_score=True,
        generate_strategy_report=True,
        generate_alerts=True,
    )
    a = b.to_dict()["actions"]
    assert all(a.values())


# ---------------------------------------------------------------------------
# Chaining
# ---------------------------------------------------------------------------


def test_chaining_returns_self():
    b = EvidenceBundle()
    result = b.with_strategy_version("v1.0")
    assert result is b


def test_full_chain():
    b = (
        EvidenceBundle()
        .with_strategy_version("v1.0")
        .with_config_snapshot("cfg", config_json={"params": {}})
        .with_universe_snapshot("uni", symbols=["AAPL"])
        .with_signal_snapshot("sig", rows=[{"symbol": "AAPL", "signal": 1.0}])
        .with_dataset("AAPL OHLCV")
        .with_dataset_snapshot(rows=[{"close": 100.0}])
        .with_strategy_run("bt-q1", run_type="backtest")
        .with_actions(compute_reliability_score=True)
    )
    sections = b.sections()
    assert "strategy_version" in sections
    assert "config_snapshot" in sections
    assert "universe_snapshot" in sections
    assert "signal_snapshot" in sections
    assert "dataset" in sections
    assert "dataset_snapshot" in sections
    assert "strategy_run" in sections
    assert "actions" in sections


# ---------------------------------------------------------------------------
# Serialisation / deserialisation
# ---------------------------------------------------------------------------


def test_to_dict_and_from_dict_roundtrip():
    b = (
        EvidenceBundle()
        .with_strategy_run("bt", run_type="backtest", metrics_json={"sharpe": 1.6})
        .with_actions(compute_reliability_score=True)
    )
    d = b.to_dict()
    b2 = EvidenceBundle.from_dict(d)
    assert b == b2
    assert b2.to_dict()["strategy_run"]["metrics_json"]["sharpe"] == 1.6


def test_to_json_and_from_json_roundtrip():
    b = EvidenceBundle().with_strategy_run(
        "bt-2024", run_type="backtest", metrics_json={"sharpe": 1.4}
    )
    j = b.to_json()
    b2 = EvidenceBundle.from_json(j)
    assert b2.to_dict()["strategy_run"]["run_name"] == "bt-2024"


def test_from_json_invalid_raises():
    with pytest.raises(QuantFidelityValidationError, match="JSON"):
        EvidenceBundle.from_json("not valid json {{{")


def test_from_dict_non_dict_raises():
    with pytest.raises(QuantFidelityValidationError, match="dict"):
        EvidenceBundle.from_dict("not a dict")


def test_to_json_is_valid_json():
    b = EvidenceBundle().with_universe_snapshot("u", symbols=["AAPL", "MSFT"])
    raw = b.to_json()
    parsed = json.loads(raw)
    assert parsed["universe_snapshot"]["symbols"] == ["AAPL", "MSFT"]


def test_to_json_indent_none():
    b = EvidenceBundle().with_strategy_run("bt", run_type="backtest")
    j = b.to_json(indent=None)
    # Should be compact (no newlines)
    assert "\n" not in j


# ---------------------------------------------------------------------------
# Section management
# ---------------------------------------------------------------------------


def test_without_strategy_version():
    b = EvidenceBundle().with_strategy_version("v1.0")
    b.without_strategy_version()
    assert "strategy_version" not in b.to_dict()


def test_without_actions():
    b = EvidenceBundle().with_actions(compute_reliability_score=True)
    b.without_actions()
    assert "actions" not in b.to_dict()


def test_repr_shows_sections():
    b = EvidenceBundle().with_strategy_run("bt", run_type="backtest")
    r = repr(b)
    assert "strategy_run" in r


def test_repr_empty():
    r = repr(EvidenceBundle())
    assert "empty" in r


def test_equality():
    b1 = EvidenceBundle().with_strategy_run("bt", run_type="backtest")
    b2 = EvidenceBundle().with_strategy_run("bt", run_type="backtest")
    assert b1 == b2


def test_inequality():
    b1 = EvidenceBundle().with_strategy_run("bt1", run_type="backtest")
    b2 = EvidenceBundle().with_strategy_run("bt2", run_type="backtest")
    assert b1 != b2
