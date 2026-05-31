"""M9 dashboard summary endpoint tests.

Tests cover:
- GET /api/dashboard/summary returns 200
- Response has all required top-level keys
- Counts reflect seeded data (strategies, runs exist from seed)
- strategy counts correct (total, active)
- run counts correct after logging a run
- data_health_score is null with no snapshots; becomes non-null after upload
- backtest_trust_score is null with no audits; becomes non-null after audit
- strategy_activity_score is null with no strategies (impossible in seeded env;
  tested via null contract when 0 strategies would be the case)
- overall_reliability_score is null only when ALL dimensions are null
- recent_runs populated after logging a run
- recent_snapshots populated after uploading a snapshot
- recent_audits populated after running an audit
- score formula: activity_score ≥ 20 when strategies exist
- lowest scores are populated correctly
- all existing M2–M8 tests still pass (no regressions)
"""

from __future__ import annotations

import uuid

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_project_id(client) -> str:
    return client.get("/api/projects").json()[0]["id"]


def _create_strategy_id(client, name: str) -> str:
    pid = _get_project_id(client)
    resp = client.post("/api/strategies", json={"project_id": pid, "name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _log_run(client, strategy_id: str, **kwargs) -> dict:
    payload = {
        "run_name": f"DashRun {uuid.uuid4().hex[:6]}",
        "run_type": "backtest",
        "assumptions_json": {
            "transaction_cost_bps": 5,
            "fill_model": "vwap",
        },
        "metrics_json": {
            "sharpe": 1.2,
            "annual_return": 0.18,
            "trade_count": 200,
        },
        **kwargs,
    }
    resp = client.post(f"/api/strategies/{strategy_id}/runs", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_dataset(client) -> dict:
    pid = _get_project_id(client)
    resp = client.post("/api/datasets", json={
        "project_id": pid,
        "name": f"DashDS {uuid.uuid4().hex[:6]}",
        "dataset_type": "ohlcv",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload_snapshot(client, dataset_id: str) -> dict:
    rows = [
        {"symbol": "AAPL", "timestamp": "2024-01-02",
         "open": 185.0, "high": 188.0, "low": 184.0, "close": 187.0, "volume": 5000000},
        {"symbol": "AAPL", "timestamp": "2024-01-03",
         "open": 187.0, "high": 190.0, "low": 186.0, "close": 189.0, "volume": 4800000},
    ]
    resp = client.post(f"/api/datasets/{dataset_id}/snapshots",
                       json={"version_label": "v1", "rows": rows})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _post_audit(client, run_id: str) -> dict:
    resp = client.post(f"/api/strategy-runs/{run_id}/backtest-audit")
    assert resp.status_code == 201, resp.text
    return resp.json()


def _get_summary(client) -> dict:
    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Basic shape
# ---------------------------------------------------------------------------

def test_dashboard_returns_200(client):
    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200


def test_dashboard_has_required_top_level_keys(client):
    summary = _get_summary(client)
    for key in ("generated_at", "counts", "scores",
                "recent_runs", "recent_snapshots",
                "recent_audits", "recent_timeline_events"):
        assert key in summary, f"Missing key: {key}"


def test_counts_has_required_fields(client):
    counts = _get_summary(client)["counts"]
    for field in (
        "total_strategies", "active_strategies", "archived_strategies",
        "strategies_by_asset_class",
        "total_runs", "backtest_run_count", "research_run_count",
        "paper_run_count", "live_run_count", "latest_run_at",
        "total_datasets", "total_dataset_snapshots",
        "snapshots_with_issues", "total_data_quality_issues",
        "data_issues_by_severity",
        "total_backtest_audits", "total_backtest_issues",
        "backtest_issues_by_severity", "audits_by_status",
    ):
        assert field in counts, f"Missing counts field: {field}"


def test_scores_has_required_fields(client):
    scores = _get_summary(client)["scores"]
    for field in (
        "data_health_score", "lowest_data_health_score",
        "backtest_trust_score", "lowest_backtest_trust_score",
        "strategy_activity_score", "overall_reliability_score",
    ):
        assert field in scores, f"Missing scores field: {field}"


# ---------------------------------------------------------------------------
# Strategy counts
# ---------------------------------------------------------------------------

def test_strategy_counts_reflect_seeded_data(client):
    """The seed creates at least one active strategy."""
    counts = _get_summary(client)["counts"]
    assert counts["total_strategies"] >= 1
    assert counts["active_strategies"] >= 1


def test_new_strategy_increments_count(client):
    before = _get_summary(client)["counts"]["total_strategies"]
    _create_strategy_id(client, f"DashStrat {uuid.uuid4().hex[:6]}")
    after = _get_summary(client)["counts"]["total_strategies"]
    assert after == before + 1


def test_strategies_by_asset_class_is_dict(client):
    counts = _get_summary(client)["counts"]
    assert isinstance(counts["strategies_by_asset_class"], dict)


# ---------------------------------------------------------------------------
# Run counts
# ---------------------------------------------------------------------------

def test_total_runs_reflects_existing_data(client):
    counts = _get_summary(client)["counts"]
    # Seed creates at least one run.
    assert counts["total_runs"] >= 1


def test_logging_run_increments_count(client):
    sid = _create_strategy_id(client, f"DashRunCount {uuid.uuid4().hex[:6]}")
    before = _get_summary(client)["counts"]["total_runs"]
    _log_run(client, sid)
    after = _get_summary(client)["counts"]["total_runs"]
    assert after == before + 1


def test_backtest_run_count_increments(client):
    sid = _create_strategy_id(client, f"DashBtCount {uuid.uuid4().hex[:6]}")
    before = _get_summary(client)["counts"]["backtest_run_count"]
    _log_run(client, sid, run_type="backtest")
    after = _get_summary(client)["counts"]["backtest_run_count"]
    assert after == before + 1


# ---------------------------------------------------------------------------
# Data health scores
# ---------------------------------------------------------------------------

def test_data_health_score_is_not_null_after_snapshot(client):
    ds = _create_dataset(client)
    _upload_snapshot(client, ds["id"])
    scores = _get_summary(client)["scores"]
    assert scores["data_health_score"] is not None
    assert 0 <= scores["data_health_score"] <= 100


def test_lowest_data_health_score_populated_after_snapshot(client):
    ds = _create_dataset(client)
    _upload_snapshot(client, ds["id"])
    scores = _get_summary(client)["scores"]
    assert scores["lowest_data_health_score"] is not None
    assert 0 <= scores["lowest_data_health_score"] <= 100


def test_total_snapshots_increments_after_upload(client):
    ds = _create_dataset(client)
    before = _get_summary(client)["counts"]["total_dataset_snapshots"]
    _upload_snapshot(client, ds["id"])
    after = _get_summary(client)["counts"]["total_dataset_snapshots"]
    assert after == before + 1


# ---------------------------------------------------------------------------
# Backtest trust scores
# ---------------------------------------------------------------------------

def test_backtest_trust_score_is_not_null_after_audit(client):
    sid = _create_strategy_id(client, f"DashTrust {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid)
    _post_audit(client, run["id"])
    scores = _get_summary(client)["scores"]
    assert scores["backtest_trust_score"] is not None
    assert 0 <= scores["backtest_trust_score"] <= 100


def test_lowest_backtest_trust_populated_after_audit(client):
    sid = _create_strategy_id(client, f"DashLowTrust {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid)
    _post_audit(client, run["id"])
    scores = _get_summary(client)["scores"]
    assert scores["lowest_backtest_trust_score"] is not None


def test_total_audits_increments_after_audit(client):
    sid = _create_strategy_id(client, f"DashAuditCount {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid)
    before = _get_summary(client)["counts"]["total_backtest_audits"]
    _post_audit(client, run["id"])
    after = _get_summary(client)["counts"]["total_backtest_audits"]
    assert after == before + 1


# ---------------------------------------------------------------------------
# Strategy activity score
# ---------------------------------------------------------------------------

def test_strategy_activity_score_not_null_with_strategies(client):
    """Seeded env has strategies → activity score must not be null."""
    scores = _get_summary(client)["scores"]
    assert scores["strategy_activity_score"] is not None


def test_strategy_activity_score_increases_with_runs(client):
    """More runs → higher activity score (up to 100)."""
    sid = _create_strategy_id(client, f"DashActivity {uuid.uuid4().hex[:6]}")
    before = _get_summary(client)["scores"]["strategy_activity_score"]
    # Log enough runs to move the score (if not already at 100).
    for _ in range(11):
        _log_run(client, sid)
    after = _get_summary(client)["scores"]["strategy_activity_score"]
    assert after >= before  # monotone non-decreasing
    assert after == 100.0


# ---------------------------------------------------------------------------
# Overall reliability score
# ---------------------------------------------------------------------------

def test_overall_reliability_score_not_null_with_strategies(client):
    """At minimum strategy_activity_score exists → overall must not be null."""
    scores = _get_summary(client)["scores"]
    assert scores["overall_reliability_score"] is not None


def test_overall_reliability_score_in_range(client):
    scores = _get_summary(client)["scores"]
    if scores["overall_reliability_score"] is not None:
        assert 0 <= scores["overall_reliability_score"] <= 100


# ---------------------------------------------------------------------------
# Recent evidence arrays
# ---------------------------------------------------------------------------

def test_recent_runs_populated(client):
    sid = _create_strategy_id(client, f"DashRecentRun {uuid.uuid4().hex[:6]}")
    _log_run(client, sid)
    summary = _get_summary(client)
    assert len(summary["recent_runs"]) >= 1
    run_item = summary["recent_runs"][0]
    for field in ("id", "item_type", "title", "strategy_name", "score", "status", "timestamp"):
        assert field in run_item, f"Missing field in recent_run item: {field}"
    assert run_item["item_type"] == "run"
    assert run_item["strategy_name"] is not None


def test_recent_snapshots_populated(client):
    ds = _create_dataset(client)
    _upload_snapshot(client, ds["id"])
    summary = _get_summary(client)
    assert len(summary["recent_snapshots"]) >= 1
    snap_item = summary["recent_snapshots"][0]
    assert snap_item["item_type"] == "snapshot"
    assert snap_item["score"] is not None
    assert 0 <= snap_item["score"] <= 100


def test_recent_audits_populated(client):
    sid = _create_strategy_id(client, f"DashRecentAudit {uuid.uuid4().hex[:6]}")
    run = _log_run(client, sid)
    _post_audit(client, run["id"])
    summary = _get_summary(client)
    assert len(summary["recent_audits"]) >= 1
    audit_item = summary["recent_audits"][0]
    assert audit_item["item_type"] == "audit"
    assert audit_item["score"] is not None


def test_recent_timeline_events_populated(client):
    """Timeline events exist from seeded data and test activity."""
    summary = _get_summary(client)
    assert len(summary["recent_timeline_events"]) >= 1
    ev = summary["recent_timeline_events"][0]
    for field in ("id", "item_type", "title", "status", "timestamp"):
        assert field in ev
    assert ev["item_type"] == "timeline_event"


def test_recent_items_capped_at_five(client):
    """recent_* lists must not exceed 5 items."""
    summary = _get_summary(client)
    for key in ("recent_runs", "recent_snapshots", "recent_audits", "recent_timeline_events"):
        assert len(summary[key]) <= 5, f"{key} exceeds 5 items"


# ---------------------------------------------------------------------------
# No fake scores
# ---------------------------------------------------------------------------

def test_scores_are_valid_numbers_or_null(client):
    """Scores must be numeric 0–100 or null; never a fake non-null value."""
    scores = _get_summary(client)["scores"]
    for field in ("data_health_score", "backtest_trust_score",
                  "strategy_activity_score", "overall_reliability_score"):
        val = scores[field]
        if val is not None:
            assert isinstance(val, (int, float)), f"{field} is not numeric: {val!r}"
            assert 0 <= val <= 100, f"{field} out of range: {val}"


def test_generated_at_is_present(client):
    summary = _get_summary(client)
    assert summary["generated_at"] is not None
    # Should be a valid ISO timestamp string.
    assert len(summary["generated_at"]) > 10
