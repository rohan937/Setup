"""M4 strategy run logging tests.

Tests cover:
- POST /api/strategies/{id}/runs: success (201), required fields, field values
- completed_at auto-set when status=completed; not set for non-completed status
- run_type invalid → 422
- status invalid → 422
- params_json/assumptions_json/metrics_json must be dict, not list → 422
- strategy not found → 404
- strategy_version_id not found (or wrong strategy) → 404
- run_name required → 422
- run_type required → 422
- created run appears in GET /api/strategies/{id}/runs
- GET /api/strategies/{id}/runs returns newest-first ordering
- created run appears in GET /api/strategies/{id} runs array
"""

from __future__ import annotations

import uuid

import pytest


def _seed_strategy_id(client) -> str:
    """Return the ID of the seeded aapl-mean-reversion-v1 strategy."""
    strategies = client.get("/api/strategies").json()
    return next(s["id"] for s in strategies if s["slug"] == "aapl-mean-reversion-v1")


def _new_strategy_id(client, name: str) -> str:
    """Create a fresh strategy and return its ID."""
    projects = client.get("/api/projects").json()
    project_id = projects[0]["id"]
    resp = client.post("/api/strategies", json={"project_id": project_id, "name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestCreateStrategyRun:
    def test_create_run_returns_201(self, client):
        sid = _seed_strategy_id(client)
        resp = client.post(
            f"/api/strategies/{sid}/runs",
            json={"run_name": "M4 Baseline", "run_type": "backtest"},
        )
        assert resp.status_code == 201

    def test_create_run_returns_expected_fields(self, client):
        sid = _seed_strategy_id(client)
        resp = client.post(
            f"/api/strategies/{sid}/runs",
            json={
                "run_name": "Full Fields Run",
                "run_type": "research",
                "status": "completed",
                "universe_name": "SP500",
                "dataset_version": "v2024-01",
                "metrics_json": {"sharpe": 1.4, "max_drawdown": -0.12},
                "params_json": {"lookback": 20, "threshold": 0.5},
                "assumptions_json": {"transaction_cost_bps": 5, "fill_model": "close"},
                "notes": "M4 integration run",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["run_name"] == "Full Fields Run"
        assert data["run_type"] == "research"
        assert data["status"] == "completed"
        assert data["universe_name"] == "SP500"
        assert data["dataset_version"] == "v2024-01"
        assert data["metrics_json"]["sharpe"] == 1.4
        assert data["params_json"]["lookback"] == 20
        assert data["assumptions_json"]["fill_model"] == "close"
        assert data["notes"] == "M4 integration run"
        assert "id" in data
        assert "created_at" in data
        assert "strategy_id" in data
        assert data["strategy_id"] == sid

    def test_completed_at_auto_set_for_completed_status(self, client):
        sid = _seed_strategy_id(client)
        resp = client.post(
            f"/api/strategies/{sid}/runs",
            json={"run_name": "Auto Completed At", "run_type": "backtest", "status": "completed"},
        )
        assert resp.status_code == 201
        assert resp.json()["completed_at"] is not None

    def test_completed_at_not_set_for_pending_status(self, client):
        sid = _seed_strategy_id(client)
        resp = client.post(
            f"/api/strategies/{sid}/runs",
            json={"run_name": "Pending Run", "run_type": "backtest", "status": "pending"},
        )
        assert resp.status_code == 201
        assert resp.json()["completed_at"] is None

    def test_invalid_run_type_returns_422(self, client):
        sid = _seed_strategy_id(client)
        resp = client.post(
            f"/api/strategies/{sid}/runs",
            json={"run_name": "Bad Type", "run_type": "live_real_money"},
        )
        assert resp.status_code == 422

    def test_invalid_status_returns_422(self, client):
        sid = _seed_strategy_id(client)
        resp = client.post(
            f"/api/strategies/{sid}/runs",
            json={"run_name": "Bad Status", "run_type": "backtest", "status": "invented"},
        )
        assert resp.status_code == 422

    def test_params_json_must_be_dict_not_list(self, client):
        sid = _seed_strategy_id(client)
        resp = client.post(
            f"/api/strategies/{sid}/runs",
            json={"run_name": "List Params", "run_type": "backtest", "params_json": [1, 2, 3]},
        )
        assert resp.status_code == 422

    def test_metrics_json_must_be_dict_not_scalar(self, client):
        sid = _seed_strategy_id(client)
        resp = client.post(
            f"/api/strategies/{sid}/runs",
            json={"run_name": "Scalar Metrics", "run_type": "backtest", "metrics_json": "1.4"},
        )
        assert resp.status_code == 422

    def test_strategy_not_found_returns_404(self, client):
        resp = client.post(
            f"/api/strategies/{uuid.uuid4()}/runs",
            json={"run_name": "Orphan Run", "run_type": "backtest"},
        )
        assert resp.status_code == 404

    def test_invalid_strategy_version_id_returns_404(self, client):
        sid = _seed_strategy_id(client)
        resp = client.post(
            f"/api/strategies/{sid}/runs",
            json={
                "run_name": "Version Not Found",
                "run_type": "backtest",
                "strategy_version_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 404

    def test_run_name_required(self, client):
        sid = _seed_strategy_id(client)
        resp = client.post(
            f"/api/strategies/{sid}/runs",
            json={"run_type": "backtest"},
        )
        assert resp.status_code == 422

    def test_run_type_required(self, client):
        sid = _seed_strategy_id(client)
        resp = client.post(
            f"/api/strategies/{sid}/runs",
            json={"run_name": "No Type Run"},
        )
        assert resp.status_code == 422


class TestRunListAndOrdering:
    def test_run_appears_in_strategy_runs_endpoint(self, client):
        sid = _new_strategy_id(client, "M4 Visibility Check Strategy")

        resp = client.post(
            f"/api/strategies/{sid}/runs",
            json={"run_name": "Visibility Run", "run_type": "backtest"},
        )
        assert resp.status_code == 201
        run_id = resp.json()["id"]

        runs = client.get(f"/api/strategies/{sid}/runs").json()
        assert any(r["id"] == run_id for r in runs)

    def test_runs_returned_newest_first(self, client):
        sid = _new_strategy_id(client, "M4 Newest First Strategy")

        r1 = client.post(
            f"/api/strategies/{sid}/runs",
            json={"run_name": "Older Run", "run_type": "backtest"},
        ).json()
        r2 = client.post(
            f"/api/strategies/{sid}/runs",
            json={"run_name": "Newer Run", "run_type": "backtest"},
        ).json()

        runs = client.get(f"/api/strategies/{sid}/runs").json()
        assert len(runs) == 2
        # Newest (r2) must be index 0
        assert runs[0]["id"] == r2["id"]
        assert runs[1]["id"] == r1["id"]

    def test_run_appears_in_strategy_detail(self, client):
        sid = _new_strategy_id(client, "M4 Detail Visibility Strategy")

        resp = client.post(
            f"/api/strategies/{sid}/runs",
            json={"run_name": "Detail Check Run", "run_type": "research"},
        )
        assert resp.status_code == 201
        run_id = resp.json()["id"]

        detail = client.get(f"/api/strategies/{sid}").json()
        run_ids = [r["id"] for r in detail["runs"]]
        assert run_id in run_ids
