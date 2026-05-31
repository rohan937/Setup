"""M5 deterministic run comparison tests.

Tests cover:
- GET /api/strategies/{id}/runs/compare: 200, response structure
- Missing strategy → 404
- Missing run_a or run_b → 404
- Run from a different strategy → 400
- Same run compared to itself → is_same_run=True, total_changes=0
- Missing query params → 422
- Params: added / removed / changed fields detected
- Assumptions: added / removed / changed fields detected
- Metrics: numeric deltas calculated; non-numeric handled safely
- Highlighted changes generated for recognised important fields
- Explanation avoids causal overclaiming language
- Comparison does NOT create an audit timeline event
- Existing M2/M3/M4 tests still pass (run separately via pytest -q)
"""

from __future__ import annotations

import uuid

import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _new_strategy_id(client, name: str) -> str:
    projects = client.get("/api/projects").json()
    project_id = projects[0]["id"]
    resp = client.post("/api/strategies", json={"project_id": project_id, "name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _add_run(client, sid: str, **kwargs) -> str:
    payload = {"run_name": "Run", "run_type": "backtest", **kwargs}
    resp = client.post(f"/api/strategies/{sid}/runs", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_demo_runs(client) -> tuple[str, str, str]:
    """Return (strategy_id, run_a_id, run_b_id) with known diff data.

    Run A (baseline): lookback=20, txn_cost=5, sharpe=1.6, turnover=0.42
    Run B (modified): lookback=5,  txn_cost=12, sharpe=0.9, turnover=0.71,
                      added new_metric=42, dataset_version changed v1→v2

    Uses a UUID suffix so multiple tests can each call this without slug collisions
    in the shared session-scoped database.
    """
    unique_tag = uuid.uuid4().hex[:8]
    sid = _new_strategy_id(client, f"M5 Demo Comparison Strategy {unique_tag}")

    ra = _add_run(
        client, sid,
        run_name="Baseline v1",
        params_json={"lookback": 20, "threshold": 0.5},
        assumptions_json={"transaction_cost_bps": 5, "fill_model": "close"},
        metrics_json={"sharpe": 1.6, "turnover": 0.42, "max_drawdown": -0.15},
        universe_name="SP500",
        dataset_version="v1",
    )
    rb = _add_run(
        client, sid,
        run_name="Modified v2",
        params_json={"lookback": 5, "threshold": 0.5, "new_param": "added"},
        assumptions_json={"transaction_cost_bps": 12, "fill_model": "close"},
        metrics_json={"sharpe": 0.9, "turnover": 0.71, "max_drawdown": -0.22, "new_metric": 42},
        universe_name="SP500",
        dataset_version="v2",
    )
    return sid, ra, rb


# ---------------------------------------------------------------------------
# Endpoint behaviour
# ---------------------------------------------------------------------------


class TestCompareEndpoint:
    def test_compare_returns_200(self, client):
        sid, ra, rb = _create_demo_runs(client)
        resp = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        )
        assert resp.status_code == 200

    def test_compare_response_has_expected_top_level_fields(self, client):
        sid, ra, rb = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        for field in (
            "strategy_id", "run_a_id", "run_b_id",
            "run_a_name", "run_b_name",
            "run_a_created_at", "run_b_created_at",
            "is_same_run", "metadata", "params", "assumptions", "metrics",
            "highlighted_changes", "deterministic_explanation",
            "warnings", "total_changes",
        ):
            assert field in data, f"Missing field: {field}"

    def test_compare_section_has_expected_keys(self, client):
        sid, ra, rb = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        for section in ("metadata", "params", "assumptions", "metrics"):
            s = data[section]
            for key in ("added", "removed", "changed", "unchanged_count", "total_changes"):
                assert key in s, f"Section '{section}' missing key '{key}'"

    def test_compare_missing_strategy_returns_404(self, client):
        fake = str(uuid.uuid4())
        _, ra, rb = _create_demo_runs(client)
        resp = client.get(
            f"/api/strategies/{fake}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        )
        assert resp.status_code == 404

    def test_compare_missing_run_a_returns_404(self, client):
        sid, _, rb = _create_demo_runs(client)
        resp = client.get(
            f"/api/strategies/{sid}/runs/compare"
            f"?run_a_id={uuid.uuid4()}&run_b_id={rb}"
        )
        assert resp.status_code == 404

    def test_compare_missing_run_b_returns_404(self, client):
        sid, ra, _ = _create_demo_runs(client)
        resp = client.get(
            f"/api/strategies/{sid}/runs/compare"
            f"?run_a_id={ra}&run_b_id={uuid.uuid4()}"
        )
        assert resp.status_code == 404

    def test_compare_run_from_different_strategy_returns_400(self, client):
        sid1, ra, _ = _create_demo_runs(client)
        sid2 = _new_strategy_id(client, "M5 Other Strategy for 400 Test")
        rb_other = _add_run(client, sid2, run_name="Other Strategy Run")

        # Run A belongs to sid1, run_b belongs to sid2 — ask about sid1 → 400
        resp = client.get(
            f"/api/strategies/{sid1}/runs/compare"
            f"?run_a_id={ra}&run_b_id={rb_other}"
        )
        assert resp.status_code == 400

    def test_compare_same_run_returns_no_changes(self, client):
        sid, ra, _ = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={ra}"
        ).json()
        assert data["is_same_run"] is True
        assert data["total_changes"] == 0

    def test_compare_missing_run_a_id_returns_422(self, client):
        sid, _, rb = _create_demo_runs(client)
        resp = client.get(f"/api/strategies/{sid}/runs/compare?run_b_id={rb}")
        assert resp.status_code == 422

    def test_compare_missing_run_b_id_returns_422(self, client):
        sid, ra, _ = _create_demo_runs(client)
        resp = client.get(f"/api/strategies/{sid}/runs/compare?run_a_id={ra}")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Comparison engine — params / assumptions / metrics diffs
# ---------------------------------------------------------------------------


class TestComparisonEngine:
    def test_params_changed_detected(self, client):
        sid, ra, rb = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        changed_fields = [fc["field"] for fc in data["params"]["changed"]]
        assert "lookback" in changed_fields

    def test_params_added_detected(self, client):
        sid, ra, rb = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        added_fields = [fc["field"] for fc in data["params"]["added"]]
        assert "new_param" in added_fields

    def test_params_removed_detected(self, client):
        sid = _new_strategy_id(client, "M5 Param Removed Test")
        ra = _add_run(client, sid, run_name="With extra", params_json={"a": 1, "b": 2})
        rb = _add_run(client, sid, run_name="Without b", params_json={"a": 1})

        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        removed_fields = [fc["field"] for fc in data["params"]["removed"]]
        assert "b" in removed_fields

    def test_assumptions_changed_detected(self, client):
        sid, ra, rb = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        changed_fields = [fc["field"] for fc in data["assumptions"]["changed"]]
        assert "transaction_cost_bps" in changed_fields

    def test_metrics_numeric_delta_calculated(self, client):
        sid, ra, rb = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        sharpe_change = next(
            fc for fc in data["metrics"]["changed"] if fc["field"] == "sharpe"
        )
        assert sharpe_change["delta"] is not None
        assert abs(sharpe_change["delta"] - (-0.7)) < 0.001
        assert sharpe_change["pct_delta"] is not None
        assert abs(sharpe_change["pct_delta"] - (-43.75)) < 0.1

    def test_metrics_added_detected(self, client):
        sid, ra, rb = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        added_fields = [fc["field"] for fc in data["metrics"]["added"]]
        assert "new_metric" in added_fields

    def test_non_numeric_metrics_handled_safely(self, client):
        """String and bool values in metrics must not crash the engine."""
        sid = _new_strategy_id(client, "M5 Non-Numeric Metrics Test")
        ra = _add_run(
            client, sid,
            run_name="String metrics A",
            metrics_json={"model": "linear", "converged": True, "sharpe": 1.2},
        )
        rb = _add_run(
            client, sid,
            run_name="String metrics B",
            metrics_json={"model": "nonlinear", "converged": False, "sharpe": 0.8},
        )
        resp = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        )
        assert resp.status_code == 200
        data = resp.json()
        # String fields changed but have no numeric delta
        model_change = next(
            fc for fc in data["metrics"]["changed"] if fc["field"] == "model"
        )
        assert model_change["delta"] is None
        # Bool fields should also not produce a delta (booleans excluded from numeric delta)
        converged_change = next(
            fc for fc in data["metrics"]["changed"] if fc["field"] == "converged"
        )
        assert converged_change["delta"] is None
        # Numeric field still gets a delta
        sharpe_change = next(
            fc for fc in data["metrics"]["changed"] if fc["field"] == "sharpe"
        )
        assert sharpe_change["delta"] is not None

    def test_highlighted_changes_for_important_metrics(self, client):
        sid, ra, rb = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        highlights = data["highlighted_changes"]
        # sharpe and turnover are in _IMPORTANT_METRICS and changed between runs
        assert any("sharpe" in h for h in highlights)
        assert any("turnover" in h for h in highlights)

    def test_highlighted_changes_for_important_params(self, client):
        sid, ra, rb = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        # lookback is in _IMPORTANT_PARAMS
        assert any("lookback" in h for h in data["highlighted_changes"])

    def test_dataset_version_surfaced_in_highlights(self, client):
        sid, ra, rb = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        assert any("dataset_version" in h for h in data["highlighted_changes"])

    def test_explanation_contains_key_changes(self, client):
        sid, ra, rb = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        exp = data["deterministic_explanation"].lower()
        # Explanation must mention there are changes
        assert "run b differs" in exp or "run b" in exp

    def test_explanation_avoids_causal_language(self, client):
        sid, ra, rb = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        exp = data["deterministic_explanation"].lower()
        for forbidden in ("caused", "because", "therefore", "resulted in"):
            assert forbidden not in exp, (
                f"Causal word '{forbidden}' found in deterministic explanation"
            )

    def test_explanation_flags_same_run(self, client):
        sid, ra, _ = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={ra}"
        ).json()
        exp = data["deterministic_explanation"].lower()
        assert "same run" in exp

    def test_different_run_type_generates_warning(self, client):
        sid = _new_strategy_id(client, "M5 Warning Run Type Test")
        ra = _add_run(client, sid, run_name="Backtest Run", run_type="backtest")
        rb = _add_run(client, sid, run_name="Live Run", run_type="live")
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        assert len(data["warnings"]) > 0
        assert any("type" in w.lower() for w in data["warnings"])

    def test_same_runs_no_warnings_about_type(self, client):
        sid = _new_strategy_id(client, "M5 Same Type No Warning Test")
        ra = _add_run(client, sid, run_name="BT A", run_type="backtest")
        rb = _add_run(client, sid, run_name="BT B", run_type="backtest")
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        assert not any("type" in w.lower() for w in data["warnings"])

    def test_comparison_does_not_create_audit_event(self, client):
        """Comparisons are read-only — they must not pollute the audit timeline."""
        # M10: timeline now returns a paginated envelope; use "total" for counts.
        before_count = client.get("/api/timeline?limit=200").json()["total"]

        sid, ra, rb = _create_demo_runs(client)
        # Creating the strategy and runs above already added events, so
        # snapshot AGAIN after setup but before comparison.
        count_after_setup = client.get("/api/timeline?limit=200").json()["total"]

        # Perform the comparison
        resp = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        )
        assert resp.status_code == 200

        # Verify no new events were added
        count_after_compare = client.get("/api/timeline?limit=200").json()["total"]
        assert count_after_compare == count_after_setup

    def test_total_changes_is_sum_of_all_sections(self, client):
        sid, ra, rb = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        expected = (
            data["metadata"]["total_changes"]
            + data["params"]["total_changes"]
            + data["assumptions"]["total_changes"]
            + data["metrics"]["total_changes"]
        )
        assert data["total_changes"] == expected

    def test_unchanged_count_correct(self, client):
        """threshold is the same in both runs; it must appear in unchanged_count."""
        sid, ra, rb = _create_demo_runs(client)
        data = client.get(
            f"/api/strategies/{sid}/runs/compare?run_a_id={ra}&run_b_id={rb}"
        ).json()
        # threshold=0.5 in both runs — should be counted as unchanged
        assert data["params"]["unchanged_count"] >= 1
