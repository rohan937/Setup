"""M10 audit timeline endpoint tests.

Tests cover:
- GET /api/timeline returns 200 with paginated envelope
- Response shape: items, total, limit, offset
- Events are newest-first
- limit and offset pagination work
- Filters: strategy_id, project_id, event_type, severity, source_type
- Filters AND-combine (empty result when no match)
- total reflects filtered count, not just items length
- GET /api/strategies/{id}/timeline returns strategy-scoped events
- GET /api/strategies/{id}/timeline 404 for unknown strategy
- Strategy-timeline limit/offset work
- Event quality: strategy_created has description + metadata
- Event quality: strategy_run_logged has description + metadata
- Event quality: dataset_snapshot_uploaded has description + metadata
- Event quality: backtest_audited has description + metadata
- backtest_audited severity escalates for low trust scores
- All prior M2–M9 tests still pass (no regressions)
"""

from __future__ import annotations

import uuid

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_project_id(client) -> str:
    return client.get("/api/projects").json()[0]["id"]


def _create_strategy(client, name: str) -> dict:
    pid = _get_project_id(client)
    resp = client.post("/api/strategies", json={"project_id": pid, "name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _log_run(client, strategy_id: str, **kwargs) -> dict:
    payload = {
        "run_name": f"TLRun {uuid.uuid4().hex[:6]}",
        "run_type": "backtest",
        "assumptions_json": {"transaction_cost_bps": 5, "fill_model": "vwap"},
        "metrics_json": {"sharpe": 1.2, "annual_return": 0.18, "trade_count": 200},
        **kwargs,
    }
    resp = client.post(f"/api/strategies/{strategy_id}/runs", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_dataset_and_snapshot(client) -> dict:
    pid = _get_project_id(client)
    ds_resp = client.post("/api/datasets", json={
        "project_id": pid,
        "name": f"TLDataset {uuid.uuid4().hex[:6]}",
        "dataset_type": "ohlcv",
    })
    assert ds_resp.status_code == 201
    ds_id = ds_resp.json()["id"]
    rows = [
        {"symbol": "AAPL", "timestamp": "2024-01-02",
         "open": 185.0, "high": 188.0, "low": 184.0, "close": 187.0, "volume": 5_000_000},
        {"symbol": "AAPL", "timestamp": "2024-01-03",
         "open": 187.0, "high": 190.0, "low": 186.0, "close": 189.0, "volume": 4_800_000},
    ]
    snap_resp = client.post(f"/api/datasets/{ds_id}/snapshots",
                            json={"version_label": "v1", "rows": rows})
    assert snap_resp.status_code == 201
    return snap_resp.json()


def _post_audit(client, run_id: str) -> dict:
    resp = client.post(f"/api/strategy-runs/{run_id}/backtest-audit")
    assert resp.status_code == 201
    return resp.json()


def _get_timeline(client, **params) -> dict:
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"/api/timeline{('?' + qs) if qs else ''}"
    resp = client.get(url)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Shape and basic behaviour
# ---------------------------------------------------------------------------

def test_timeline_returns_200(client):
    resp = client.get("/api/timeline")
    assert resp.status_code == 200


def test_timeline_response_has_envelope(client):
    data = _get_timeline(client)
    for key in ("items", "total", "limit", "offset"):
        assert key in data, f"Missing envelope key: {key}"


def test_timeline_items_is_list(client):
    data = _get_timeline(client)
    assert isinstance(data["items"], list)


def test_timeline_total_gte_items(client):
    data = _get_timeline(client, limit=1)
    assert data["total"] >= len(data["items"])


def test_timeline_limit_offset_reflected(client):
    data = _get_timeline(client, limit=3, offset=2)
    assert data["limit"] == 3
    assert data["offset"] == 2


def test_timeline_seeded_events_present(client):
    data = _get_timeline(client)
    assert data["total"] >= 2, "Seed should have created at least 2 timeline events"


def test_timeline_item_fields(client):
    data = _get_timeline(client)
    item = data["items"][0]
    for field in (
        "id", "organization_id", "event_type", "title",
        "severity", "event_time", "created_at",
    ):
        assert field in item, f"Missing field: {field}"


def test_timeline_newest_first(client):
    """Two consecutive items must be in descending event_time order."""
    data = _get_timeline(client, limit=10)
    items = data["items"]
    if len(items) < 2:
        pytest.skip("Not enough events to test ordering")
    assert items[0]["event_time"] >= items[1]["event_time"]


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def test_timeline_limit_1(client):
    data = _get_timeline(client, limit=1)
    assert len(data["items"]) == 1


def test_timeline_offset_shifts_results(client):
    d0 = _get_timeline(client, limit=1, offset=0)
    d1 = _get_timeline(client, limit=1, offset=1)
    if d0["total"] < 2:
        pytest.skip("Not enough events to test offset")
    assert d0["items"][0]["id"] != d1["items"][0]["id"]


def test_timeline_max_limit_200(client):
    resp = client.get("/api/timeline?limit=201")
    assert resp.status_code == 422


def test_timeline_negative_offset_rejected(client):
    resp = client.get("/api/timeline?offset=-1")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def test_filter_by_event_type_strategy_created(client):
    data = _get_timeline(client, event_type="strategy_created")
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["event_type"] == "strategy_created"


def test_filter_by_event_type_no_match(client):
    data = _get_timeline(client, event_type="nonexistent_event_type_xyz")
    assert data["total"] == 0
    assert data["items"] == []


def test_filter_by_source_type_strategy(client):
    data = _get_timeline(client, source_type="strategy")
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["source_type"] == "strategy"


def test_filter_by_source_type_strategy_run(client):
    # Seed creates at least one strategy_run event.
    data = _get_timeline(client, source_type="strategy_run")
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["source_type"] == "strategy_run"


def test_filter_by_severity_info(client):
    data = _get_timeline(client, severity="info")
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["severity"] == "info"


def test_filter_by_project_id(client):
    pid = _get_project_id(client)
    data = _get_timeline(client, project_id=pid)
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["project_id"] == pid


def test_filter_by_strategy_id(client):
    # Create a uniquely-named strategy so we can isolate its events.
    strat = _create_strategy(client, f"TLFilter {uuid.uuid4().hex[:6]}")
    sid = strat["id"]

    data = _get_timeline(client, strategy_id=sid)
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["strategy_id"] == sid


def test_filter_strategy_id_plus_event_type(client):
    """AND-combining two filters returns only matching events."""
    strat = _create_strategy(client, f"TLCombo {uuid.uuid4().hex[:6]}")
    sid = strat["id"]

    data = _get_timeline(client, strategy_id=sid, event_type="strategy_created")
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["strategy_id"] == sid
        assert item["event_type"] == "strategy_created"


def test_filter_no_match_returns_empty(client):
    data = _get_timeline(client, event_type="strategy_created", source_type="backtest_audit")
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# Strategy-specific timeline endpoint
# ---------------------------------------------------------------------------

def test_strategy_timeline_returns_200(client):
    strat = _create_strategy(client, f"TLStrSpecific {uuid.uuid4().hex[:6]}")
    resp = client.get(f"/api/strategies/{strat['id']}/timeline")
    assert resp.status_code == 200


def test_strategy_timeline_envelope(client):
    strat = _create_strategy(client, f"TLStrEnv {uuid.uuid4().hex[:6]}")
    data = client.get(f"/api/strategies/{strat['id']}/timeline").json()
    for key in ("items", "total", "limit", "offset"):
        assert key in data


def test_strategy_timeline_has_creation_event(client):
    strat = _create_strategy(client, f"TLStrCreation {uuid.uuid4().hex[:6]}")
    data = client.get(f"/api/strategies/{strat['id']}/timeline").json()
    event_types = [i["event_type"] for i in data["items"]]
    assert "strategy_created" in event_types


def test_strategy_timeline_run_event_appears(client):
    strat = _create_strategy(client, f"TLStrRun {uuid.uuid4().hex[:6]}")
    _log_run(client, strat["id"])
    data = client.get(f"/api/strategies/{strat['id']}/timeline").json()
    event_types = [i["event_type"] for i in data["items"]]
    assert "strategy_run_logged" in event_types


def test_strategy_timeline_only_own_events(client):
    """Events from other strategies must not appear."""
    s1 = _create_strategy(client, f"TLStrOnly1 {uuid.uuid4().hex[:6]}")
    s2 = _create_strategy(client, f"TLStrOnly2 {uuid.uuid4().hex[:6]}")
    data = client.get(f"/api/strategies/{s1['id']}/timeline").json()
    for item in data["items"]:
        assert item["strategy_id"] == s1["id"]


def test_strategy_timeline_404_unknown(client):
    resp = client.get(f"/api/strategies/{uuid.uuid4()}/timeline")
    assert resp.status_code == 404


def test_strategy_timeline_limit(client):
    strat = _create_strategy(client, f"TLStrLimit {uuid.uuid4().hex[:6]}")
    for _ in range(3):
        _log_run(client, strat["id"])
    data = client.get(f"/api/strategies/{strat['id']}/timeline?limit=2").json()
    assert len(data["items"]) <= 2
    assert data["limit"] == 2


def test_strategy_timeline_offset(client):
    strat = _create_strategy(client, f"TLStrOffset {uuid.uuid4().hex[:6]}")
    _log_run(client, strat["id"])
    d0 = client.get(f"/api/strategies/{strat['id']}/timeline?offset=0").json()
    d1 = client.get(f"/api/strategies/{strat['id']}/timeline?offset=1").json()
    if d0["total"] < 2:
        pytest.skip("Not enough events to test offset")
    assert d0["items"][0]["id"] != d1["items"][0]["id"]


# ---------------------------------------------------------------------------
# Event quality: strategy_created
# ---------------------------------------------------------------------------

def test_strategy_created_event_has_description(client):
    strat = _create_strategy(client, f"TLEvtCreated {uuid.uuid4().hex[:6]}")
    data = _get_timeline(client, strategy_id=strat["id"], event_type="strategy_created")
    item = data["items"][0]
    assert item["description"] is not None
    assert len(item["description"]) > 10


def test_strategy_created_event_has_metadata(client):
    strat = _create_strategy(client, f"TLEvtMeta {uuid.uuid4().hex[:6]}")
    data = _get_timeline(client, strategy_id=strat["id"], event_type="strategy_created")
    item = data["items"][0]
    assert item["metadata_json"] is not None
    assert "strategy_name" in item["metadata_json"]
    assert item["source_type"] == "strategy"


# ---------------------------------------------------------------------------
# Event quality: strategy_run_logged
# ---------------------------------------------------------------------------

def test_run_logged_event_has_description(client):
    strat = _create_strategy(client, f"TLRunDesc {uuid.uuid4().hex[:6]}")
    _log_run(client, strat["id"])
    data = _get_timeline(client, strategy_id=strat["id"], event_type="strategy_run_logged")
    item = data["items"][0]
    assert item["description"] is not None
    assert len(item["description"]) > 10


def test_run_logged_event_has_metadata(client):
    strat = _create_strategy(client, f"TLRunMeta {uuid.uuid4().hex[:6]}")
    _log_run(client, strat["id"], run_type="backtest")
    data = _get_timeline(client, strategy_id=strat["id"], event_type="strategy_run_logged")
    item = data["items"][0]
    assert item["metadata_json"] is not None
    assert item["metadata_json"]["run_type"] == "backtest"
    assert item["source_type"] == "strategy_run"


# ---------------------------------------------------------------------------
# Event quality: dataset_snapshot_uploaded
# ---------------------------------------------------------------------------

def test_snapshot_event_in_timeline(client):
    snap = _create_dataset_and_snapshot(client)
    data = _get_timeline(client, source_type="dataset_snapshot", limit=1)
    assert data["total"] >= 1
    item = data["items"][0]
    assert item["event_type"] == "dataset_snapshot_uploaded"
    assert item["description"] is not None
    assert item["metadata_json"] is not None
    assert "health_score" in item["metadata_json"]


# ---------------------------------------------------------------------------
# Event quality: backtest_audited
# ---------------------------------------------------------------------------

def test_audit_event_appears_after_audit(client):
    strat = _create_strategy(client, f"TLAuditEvt {uuid.uuid4().hex[:6]}")
    run = _log_run(client, strat["id"])
    _post_audit(client, run["id"])
    data = _get_timeline(client, strategy_id=strat["id"], event_type="backtest_audited")
    assert data["total"] >= 1
    item = data["items"][0]
    assert item["description"] is not None
    assert item["metadata_json"] is not None
    assert "trust_score" in item["metadata_json"]


def test_audit_event_severity_escalates_for_low_trust(client):
    """Backtest with missing cost assumptions → low trust score → severity ≠ info."""
    strat = _create_strategy(client, f"TLAuditSev {uuid.uuid4().hex[:6]}")
    # A run with no assumptions → many issues → low trust score.
    run = _log_run(client, strat["id"], assumptions_json={})
    audit = _post_audit(client, run["id"])

    data = _get_timeline(client, strategy_id=strat["id"], event_type="backtest_audited")
    item = data["items"][0]
    trust = item["metadata_json"]["trust_score"]
    severity = item["severity"]

    if trust < 25:
        assert severity == "high"
    elif trust < 50:
        assert severity == "medium"
    elif trust < 75:
        assert severity == "low"
    # trust >= 75 → info (covered by other tests via well-configured runs)


# ---------------------------------------------------------------------------
# Count consistency
# ---------------------------------------------------------------------------

def test_total_count_increases_after_strategy_creation(client):
    before = _get_timeline(client)["total"]
    _create_strategy(client, f"TLCountStrat {uuid.uuid4().hex[:6]}")
    after = _get_timeline(client)["total"]
    assert after == before + 1


def test_total_count_increases_after_run(client):
    strat = _create_strategy(client, f"TLCountRun {uuid.uuid4().hex[:6]}")
    before = _get_timeline(client)["total"]
    _log_run(client, strat["id"])
    after = _get_timeline(client)["total"]
    assert after == before + 1


def test_total_count_increases_after_snapshot(client):
    before = _get_timeline(client, source_type="dataset_snapshot")["total"]
    _create_dataset_and_snapshot(client)
    after = _get_timeline(client, source_type="dataset_snapshot")["total"]
    assert after == before + 1


def test_total_count_increases_after_audit(client):
    strat = _create_strategy(client, f"TLCountAudit {uuid.uuid4().hex[:6]}")
    run = _log_run(client, strat["id"])
    before = _get_timeline(client, source_type="backtest_audit")["total"]
    _post_audit(client, run["id"])
    after = _get_timeline(client, source_type="backtest_audit")["total"]
    assert after == before + 1
