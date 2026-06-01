"""M26 tests — Pandas + Research Workflow Helpers."""
from __future__ import annotations

import json
import unittest.mock as mock
from pathlib import Path

import pytest

from quantfidelity.bundle import EvidenceBundle
from quantfidelity.dataframe import (
    is_dataframe_like,
    normalize_records,
    rows_from_table,
    validate_required_columns,
)
from quantfidelity.exceptions import QuantFidelityValidationError
from quantfidelity.workflow import QuantResearchWorkflow


# ─────────────────────────────────────────────────────────────────────────── #
# TestDataframeHelpers                                                         #
# ─────────────────────────────────────────────────────────────────────────── #


class TestDataframeHelpers:
    def test_list_of_dicts_accepted(self):
        rows = [{"symbol": "AAPL", "close": 100.0}]
        result = rows_from_table(rows)
        assert result[0]["symbol"] == "AAPL"

    def test_non_list_raises(self):
        with pytest.raises(QuantFidelityValidationError):
            rows_from_table(("AAPL", 100))

    def test_non_list_string_raises(self):
        with pytest.raises(QuantFidelityValidationError):
            rows_from_table("not a list")

    def test_list_of_non_dicts_raises(self):
        with pytest.raises(QuantFidelityValidationError):
            rows_from_table([1, 2, 3])

    def test_normalize_records_nan_float(self):
        import math

        rows = [{"x": float("nan"), "y": 1.0}]
        result = normalize_records(rows)
        assert result[0]["x"] is None
        assert result[0]["y"] == 1.0

    def test_normalize_records_does_not_mutate(self):
        original = [{"x": 1}]
        result = normalize_records(original)
        result[0]["x"] = 999
        assert original[0]["x"] == 1  # original unchanged

    def test_validate_required_columns_passes(self):
        validate_required_columns([{"a": 1, "b": 2}], ["a", "b"])  # should not raise

    def test_validate_required_columns_fails(self):
        with pytest.raises(QuantFidelityValidationError):
            validate_required_columns([{"a": 1}], ["a", "b"], context="test")

    def test_is_dataframe_like_false_for_list(self):
        assert is_dataframe_like([]) is False

    def test_is_dataframe_like_false_for_dict(self):
        assert is_dataframe_like({}) is False

    def test_dataframe_if_available(self):
        """Test with real pandas DataFrame if pandas is installed."""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not installed")
        df = pd.DataFrame([{"symbol": "AAPL", "close": 100.0}])
        assert is_dataframe_like(df) is True
        rows = rows_from_table(df)
        assert rows[0]["symbol"] == "AAPL"
        assert rows[0]["close"] == 100.0

    def test_dataframe_nan_to_none_if_available(self):
        try:
            import numpy as np
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not installed")
        df = pd.DataFrame([{"x": np.nan, "y": 1.0}])
        rows = rows_from_table(df)
        assert rows[0]["x"] is None

    def test_dataframe_timestamp_to_iso_if_available(self):
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not installed")
        df = pd.DataFrame([{"ts": pd.Timestamp("2024-01-01")}])
        rows = rows_from_table(df)
        assert isinstance(rows[0]["ts"], str)
        assert "2024-01-01" in rows[0]["ts"]


# ─────────────────────────────────────────────────────────────────────────── #
# TestBundleHelpers                                                            #
# ─────────────────────────────────────────────────────────────────────────── #


class TestBundleHelpers:
    def test_with_dataset_snapshot_from_table(self):
        b = EvidenceBundle().with_dataset_snapshot_from_table("snap-1", [{"x": 1}])
        assert b.to_dict()["dataset_snapshot"]["rows"][0]["x"] == 1

    def test_with_signal_snapshot_from_table(self):
        rows = [{"symbol": "AAPL", "signal": 1.0}]
        b = EvidenceBundle().with_signal_snapshot_from_table("sig", rows)
        assert b.to_dict()["signal_snapshot"]["rows"][0]["signal"] == 1.0

    def test_with_universe_from_symbols(self):
        b = EvidenceBundle().with_universe_from_symbols("uni", ["AAPL", "MSFT"])
        assert "AAPL" in b.to_dict()["universe_snapshot"]["symbols"]

    def test_with_backtest_run(self):
        b = EvidenceBundle().with_backtest_run("bt-q1", metrics={"sharpe": 1.4})
        sr = b.to_dict()["strategy_run"]
        assert sr["run_type"] == "backtest"
        assert sr["metrics_json"]["sharpe"] == 1.4

    def test_with_research_run(self):
        b = EvidenceBundle().with_research_run("research-1")
        assert b.to_dict()["strategy_run"]["run_type"] == "research"

    def test_dataset_snapshot_from_table_rejects_non_list(self):
        with pytest.raises(QuantFidelityValidationError):
            EvidenceBundle().with_dataset_snapshot_from_table("snap", "not a list")

    def test_signal_snapshot_from_table_rejects_tuple(self):
        with pytest.raises(QuantFidelityValidationError):
            EvidenceBundle().with_signal_snapshot_from_table("sig", ({"signal": 1.0},))

    def test_chaining_new_methods(self):
        b = (
            EvidenceBundle()
            .with_universe_from_symbols("uni", ["AAPL"])
            .with_backtest_run("bt", metrics={"sharpe": 1.2})
        )
        d = b.to_dict()
        assert "universe_snapshot" in d
        assert "strategy_run" in d


# ─────────────────────────────────────────────────────────────────────────── #
# TestBundleValidation                                                         #
# ─────────────────────────────────────────────────────────────────────────── #


class TestBundleValidation:
    def test_empty_bundle_valid(self):
        assert EvidenceBundle().validate() == []

    def test_config_json_list_invalid(self):
        b = EvidenceBundle()
        b._data["config_snapshot"] = {"label": "c", "config_json": [1, 2]}
        issues = b.validate()
        assert any("config_json" in i for i in issues)

    def test_dataset_empty_rows_invalid(self):
        b = EvidenceBundle()
        b._data["dataset_snapshot"] = {"rows": []}
        issues = b.validate()
        assert any("empty" in i for i in issues)

    def test_signal_missing_column(self):
        b = EvidenceBundle()
        b._data["signal_snapshot"] = {"rows": [{"x": 1}], "signal_column": "signal"}
        issues = b.validate()
        assert any("signal" in i for i in issues)

    def test_universe_empty_symbols(self):
        b = EvidenceBundle()
        b._data["universe_snapshot"] = {"label": "u", "symbols": []}
        issues = b.validate()
        assert any("symbols" in i for i in issues)

    def test_metrics_wrong_type(self):
        b = EvidenceBundle()
        b._data["strategy_run"] = {
            "run_name": "bt",
            "run_type": "backtest",
            "metrics_json": "not a dict",
        }
        issues = b.validate()
        assert any("metrics_json" in i for i in issues)

    def test_actions_wrong_type(self):
        b = EvidenceBundle()
        b._data["actions"] = {"run_backtest_audit": "yes"}
        issues = b.validate()
        assert any("boolean" in i for i in issues)

    def test_raise_if_invalid_raises(self):
        b = EvidenceBundle()
        b._data["config_snapshot"] = {"label": "c", "config_json": [1, 2]}
        with pytest.raises(QuantFidelityValidationError):
            b.raise_if_invalid()

    def test_raise_if_invalid_no_raise_when_valid(self):
        EvidenceBundle().raise_if_invalid()  # should not raise


# ─────────────────────────────────────────────────────────────────────────── #
# TestWorkflow                                                                 #
# ─────────────────────────────────────────────────────────────────────────── #


class TestWorkflow:
    def test_workflow_empty_to_bundle(self):
        wf = QuantResearchWorkflow()
        b = wf.to_bundle()
        assert b.is_empty()

    def test_workflow_set_version(self):
        wf = QuantResearchWorkflow().set_version("v1.0")
        d = wf.to_dict()
        assert d["strategy_version"]["version_label"] == "v1.0"

    def test_workflow_version_in_constructor(self):
        wf = QuantResearchWorkflow(strategy_name="AAPL MR", version_label="v2.0")
        d = wf.to_dict()
        assert d["strategy_version"]["version_label"] == "v2.0"

    def test_workflow_set_config(self):
        wf = QuantResearchWorkflow().set_config(
            params={"lookback": 20}, assumptions={"cost_bps": 5}
        )
        d = wf.to_dict()
        assert d["config_snapshot"]["config_json"]["params"]["lookback"] == 20

    def test_workflow_set_universe(self):
        wf = QuantResearchWorkflow().set_version("v1").set_universe(["AAPL", "MSFT"])
        d = wf.to_dict()
        assert "AAPL" in d["universe_snapshot"]["symbols"]
        assert d["universe_snapshot"].get("strategy_version_label") == "v1"

    def test_workflow_set_signals_links_universe(self):
        wf = (
            QuantResearchWorkflow()
            .set_version("v1")
            .set_universe(["AAPL"], label="my-uni")
            .set_signals([{"symbol": "AAPL", "signal": 1.0}], label="my-sig")
        )
        d = wf.to_dict()
        assert d["signal_snapshot"]["universe_snapshot_label"] == "my-uni"

    def test_workflow_set_backtest_links_all(self):
        wf = (
            QuantResearchWorkflow()
            .set_version("v1")
            .set_universe(["AAPL"])
            .set_dataset(
                "My Dataset",
                rows_or_df=[{"close": 100}],
                snapshot_label="snap1",
            )
            .set_signals([{"symbol": "AAPL", "signal": 1.0}], label="sigs")
            .set_backtest_result(metrics={"sharpe": 1.4}, run_name="bt1")
        )
        d = wf.to_dict()
        sr = d["strategy_run"]
        assert sr["run_type"] == "backtest"
        assert sr["strategy_version_label"] == "v1"
        assert sr["universe_snapshot_label"] == "universe"
        assert sr["dataset_snapshot_label"] == "snap1"
        assert sr["signal_snapshot_label"] == "sigs"

    def test_workflow_enable_actions(self):
        wf = QuantResearchWorkflow().enable_actions(compute_reliability_score=True)
        d = wf.to_dict()
        assert d["actions"]["compute_reliability_score"] is True
        assert d["actions"]["run_backtest_audit"] is True

    def test_workflow_to_json(self):
        wf = QuantResearchWorkflow().set_version("v1")
        j = wf.to_json()
        parsed = json.loads(j)
        assert "strategy_version" in parsed

    def test_workflow_validate_catches_issues(self):
        wf = QuantResearchWorkflow()
        wf._signal = {
            "rows_or_df": [{"x": 1}],
            "label": "s",
            "signal_name": None,
            "signal_column": "signal",
        }
        b = wf.to_bundle()
        issues = b.validate()
        assert any("signal" in i for i in issues)

    def test_workflow_repr(self):
        wf = QuantResearchWorkflow(strategy_name="Test")
        assert "Test" in repr(wf)


# ─────────────────────────────────────────────────────────────────────────── #
# TestCliValidate                                                              #
# ─────────────────────────────────────────────────────────────────────────── #


class TestCliValidate:
    def test_validate_valid_file(self, tmp_path, capsys):
        f = tmp_path / "b.json"
        f.write_text(
            json.dumps({"strategy_run": {"run_name": "bt", "run_type": "backtest"}})
        )
        with pytest.raises(SystemExit) as e:
            from quantfidelity.cli import main

            main(["validate", "--file", str(f)])
        assert e.value.code == 0
        assert "valid" in capsys.readouterr().out.lower()

    def test_validate_invalid_file(self, tmp_path, capsys):
        f = tmp_path / "b.json"
        f.write_text(
            json.dumps(
                {"config_snapshot": {"label": "c", "config_json": [1, 2, 3]}}
            )
        )
        with pytest.raises(SystemExit) as e:
            from quantfidelity.cli import main

            main(["validate", "--file", str(f)])
        assert e.value.code == 1

    def test_validate_file_not_found(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as e:
            from quantfidelity.cli import main

            main(["validate", "--file", str(tmp_path / "missing.json")])
        assert e.value.code == 1

    def test_ingest_validate_before_send_blocks_invalid(self, tmp_path, capsys):
        f = tmp_path / "b.json"
        f.write_text(
            json.dumps({"config_snapshot": {"label": "c", "config_json": [1]}})
        )
        with pytest.raises(SystemExit) as e:
            from quantfidelity.cli import main

            main(
                [
                    "ingest",
                    "--strategy-id",
                    "00000000-0000-0000-0000-000000000001",
                    "--file",
                    str(f),
                    "--validate-before-send",
                ]
            )
        assert e.value.code == 1

    def test_ingest_validate_before_send_force_continues(self, tmp_path, capsys):
        f = tmp_path / "b.json"
        f.write_text(
            json.dumps({"config_snapshot": {"label": "c", "config_json": [1]}})
        )
        mock_result = {
            "created_count": 0,
            "summary": "ok",
            "warnings": [],
            "actions_run": [],
            "objects": {},
            "reused_count": 0,
            "alerts_generated": 0,
            "timeline_events_created": 0,
            "generated_at": "2024-01-01T00:00:00Z",
            "strategy_id": "00000000-0000-0000-0000-000000000001",
        }
        with mock.patch(
            "quantfidelity.client.QuantFidelityClient.ingest_evidence_bundle",
            return_value=mock_result,
        ):
            with pytest.raises(SystemExit) as e:
                from quantfidelity.cli import main

                main(
                    [
                        "ingest",
                        "--strategy-id",
                        "00000000-0000-0000-0000-000000000001",
                        "--file",
                        str(f),
                        "--validate-before-send",
                        "--force",
                    ]
                )
        # Should NOT exit 1 due to validation (force overrides)
        assert e.value.code == 0
