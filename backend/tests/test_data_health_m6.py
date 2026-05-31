"""M6 data health tests.

Tests cover:
- POST /api/datasets: 201, missing project → 404, invalid dataset_type → 422
- GET /api/datasets: 200, list grows after creation
- GET /api/datasets/{id}: 200, 404
- POST /api/datasets/{id}/snapshots: 201, missing dataset → 404
- GET /api/datasets/{id}/snapshots: 200 list
- GET /api/dataset-snapshots/{id}: 200, 404

Data quality service:
- Clean OHLCV data → health_score 100, 0 issues
- Missing fields → missing_values issues
- Duplicate rows → duplicate_rows issue
- Duplicate symbol+timestamp → duplicate_symbol_timestamp issue
- Invalid timestamp → invalid_timestamp issue
- Negative price → negative_zero_price issue (critical)
- high < low → high_lt_low issue (critical)
- close outside range → close_outside_range issue
- open outside range → open_outside_range issue
- Negative volume → negative_volume issue
- Suspicious return jump > 25 % → medium severity
- Suspicious return jump > 50 % → high severity
- Health score decrements correctly (critical=25, high=15, medium=8, low=3)
- Snapshot upload creates an audit timeline event
"""

from __future__ import annotations

import uuid

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_project_id(client) -> str:
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    return resp.json()[0]["id"]


def _create_dataset(client, project_id: str, name: str, **kwargs) -> dict:
    payload = {"project_id": project_id, "name": name, **kwargs}
    resp = client.post("/api/datasets", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _clean_ohlcv_rows(n: int = 3, symbol: str = "AAPL") -> list[dict]:
    """Return n clean OHLCV rows with valid prices and timestamps."""
    base_close = 150.0
    rows = []
    for i in range(n):
        close = base_close + i * 0.50   # tiny moves — no suspicious jump
        rows.append({
            "symbol": symbol,
            "timestamp": f"2024-01-{i + 2:02d}",
            "open": close - 0.10,
            "high": close + 0.30,
            "low": close - 0.20,
            "close": close,
            "volume": 1_000_000,
        })
    return rows


# ---------------------------------------------------------------------------
# Dataset CRUD
# ---------------------------------------------------------------------------

def test_create_dataset_201(client):
    pid = _get_project_id(client)
    data = _create_dataset(client, pid, f"Test OHLCV {uuid.uuid4().hex[:6]}")
    assert data["id"]
    assert data["snapshot_count"] == 0
    assert data["dataset_type"] == "ohlcv"
    assert data["source_type"] == "manual"


def test_create_dataset_invalid_project_404(client):
    resp = client.post(
        "/api/datasets",
        json={"project_id": str(uuid.uuid4()), "name": "Ghost Dataset"},
    )
    assert resp.status_code == 404


def test_create_dataset_invalid_type_422(client):
    pid = _get_project_id(client)
    resp = client.post(
        "/api/datasets",
        json={"project_id": pid, "name": "Bad Type", "dataset_type": "not_a_type"},
    )
    assert resp.status_code == 422


def test_list_datasets_200(client):
    pid = _get_project_id(client)
    name = f"ListTest {uuid.uuid4().hex[:6]}"
    _create_dataset(client, pid, name)
    resp = client.get("/api/datasets")
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()]
    assert name in names


def test_get_dataset_200(client):
    pid = _get_project_id(client)
    d = _create_dataset(client, pid, f"DetailTest {uuid.uuid4().hex[:6]}")
    resp = client.get(f"/api/datasets/{d['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == d["id"]
    assert "snapshots" in resp.json()


def test_get_dataset_404(client):
    resp = client.get(f"/api/datasets/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Snapshot CRUD
# ---------------------------------------------------------------------------

def test_create_snapshot_201(client):
    pid = _get_project_id(client)
    d = _create_dataset(client, pid, f"SnapTest {uuid.uuid4().hex[:6]}")
    resp = client.post(
        f"/api/datasets/{d['id']}/snapshots",
        json={"version_label": "v1", "rows": _clean_ohlcv_rows()},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["row_count"] == 3
    assert body["health_score"] == 100
    assert body["issues"] == []


def test_create_snapshot_missing_dataset_404(client):
    resp = client.post(
        f"/api/datasets/{uuid.uuid4()}/snapshots",
        json={"version_label": "v1", "rows": _clean_ohlcv_rows()},
    )
    assert resp.status_code == 404


def test_list_snapshots_200(client):
    pid = _get_project_id(client)
    d = _create_dataset(client, pid, f"ListSnaps {uuid.uuid4().hex[:6]}")
    client.post(
        f"/api/datasets/{d['id']}/snapshots",
        json={"version_label": "v1", "rows": _clean_ohlcv_rows()},
    )
    resp = client.get(f"/api/datasets/{d['id']}/snapshots")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_snapshot_200(client):
    pid = _get_project_id(client)
    d = _create_dataset(client, pid, f"GetSnap {uuid.uuid4().hex[:6]}")
    snap = client.post(
        f"/api/datasets/{d['id']}/snapshots",
        json={"version_label": "v1", "rows": _clean_ohlcv_rows()},
    ).json()
    resp = client.get(f"/api/dataset-snapshots/{snap['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == snap["id"]
    assert "issues" in resp.json()


def test_get_snapshot_404(client):
    resp = client.get(f"/api/dataset-snapshots/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_snapshot_count_increments(client):
    pid = _get_project_id(client)
    d = _create_dataset(client, pid, f"CountSnaps {uuid.uuid4().hex[:6]}")
    for v in ("v1", "v2"):
        client.post(
            f"/api/datasets/{d['id']}/snapshots",
            json={"version_label": v, "rows": _clean_ohlcv_rows()},
        )
    resp = client.get(f"/api/datasets/{d['id']}")
    assert resp.json()["snapshot_count"] == 2


# ---------------------------------------------------------------------------
# Data quality: issue detection
# ---------------------------------------------------------------------------

def _upload_rows(client, rows: list[dict]) -> dict:
    """Create a temporary dataset and upload rows; return snapshot body."""
    pid = _get_project_id(client)
    d = _create_dataset(client, pid, f"QC {uuid.uuid4().hex[:6]}")
    resp = client.post(
        f"/api/datasets/{d['id']}/snapshots",
        json={"version_label": "v1", "rows": rows},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_clean_data_perfect_score(client):
    snap = _upload_rows(client, _clean_ohlcv_rows(5))
    assert snap["health_score"] == 100
    assert snap["issues"] == []


def test_missing_values_detected(client):
    rows = _clean_ohlcv_rows(2)
    rows[0]["close"] = None   # inject missing field
    snap = _upload_rows(client, rows)
    types = [i["issue_type"] for i in snap["issues"]]
    assert "missing_values" in types


def test_duplicate_rows_detected(client):
    row = _clean_ohlcv_rows(1)[0]
    snap = _upload_rows(client, [row, row])  # exact duplicate
    types = [i["issue_type"] for i in snap["issues"]]
    assert "duplicate_rows" in types


def test_duplicate_symbol_timestamp_detected(client):
    row1 = {**_clean_ohlcv_rows(1)[0], "close": 150.0}
    row2 = {**row1, "close": 155.0}  # same symbol+timestamp, different close
    snap = _upload_rows(client, [row1, row2])
    types = [i["issue_type"] for i in snap["issues"]]
    assert "duplicate_symbol_timestamp" in types


def test_invalid_timestamp_detected(client):
    rows = _clean_ohlcv_rows(1)
    rows[0]["timestamp"] = "not-a-date"
    snap = _upload_rows(client, rows)
    types = [i["issue_type"] for i in snap["issues"]]
    assert "invalid_timestamp" in types


def test_negative_price_detected(client):
    rows = _clean_ohlcv_rows(1)
    rows[0]["close"] = -5.0
    rows[0]["low"] = -6.0   # keep low <= close so range check doesn't fire
    snap = _upload_rows(client, rows)
    types = [i["issue_type"] for i in snap["issues"]]
    assert "negative_zero_price" in types
    sev = next(i["severity"] for i in snap["issues"] if i["issue_type"] == "negative_zero_price")
    assert sev == "critical"


def test_high_lt_low_detected(client):
    rows = _clean_ohlcv_rows(1)
    rows[0]["high"] = 100.0
    rows[0]["low"] = 120.0   # deliberately high < low
    snap = _upload_rows(client, rows)
    types = [i["issue_type"] for i in snap["issues"]]
    assert "high_lt_low" in types
    sev = next(i["severity"] for i in snap["issues"] if i["issue_type"] == "high_lt_low")
    assert sev == "critical"


def test_close_outside_range_detected(client):
    rows = [
        {
            "symbol": "TEST", "timestamp": "2024-01-02",
            "open": 100.0, "high": 110.0, "low": 90.0,
            "close": 120.0,  # above high
            "volume": 100,
        }
    ]
    snap = _upload_rows(client, rows)
    types = [i["issue_type"] for i in snap["issues"]]
    assert "close_outside_range" in types


def test_open_outside_range_detected(client):
    rows = [
        {
            "symbol": "TEST", "timestamp": "2024-01-02",
            "open": 80.0,   # below low
            "high": 110.0, "low": 90.0, "close": 100.0,
            "volume": 100,
        }
    ]
    snap = _upload_rows(client, rows)
    types = [i["issue_type"] for i in snap["issues"]]
    assert "open_outside_range" in types


def test_negative_volume_detected(client):
    rows = _clean_ohlcv_rows(1)
    rows[0]["volume"] = -500
    snap = _upload_rows(client, rows)
    types = [i["issue_type"] for i in snap["issues"]]
    assert "negative_volume" in types


def test_suspicious_return_jump_medium(client):
    """30 % close-to-close jump → medium severity."""
    rows = [
        {
            "symbol": "JUMP", "timestamp": "2024-01-02",
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000,
        },
        {
            "symbol": "JUMP", "timestamp": "2024-01-03",
            "open": 130.0, "high": 131.0, "low": 129.0, "close": 130.0, "volume": 1000,
        },
    ]
    snap = _upload_rows(client, rows)
    types = [i["issue_type"] for i in snap["issues"]]
    assert "suspicious_return_jump" in types
    sev = next(
        i["severity"] for i in snap["issues"]
        if i["issue_type"] == "suspicious_return_jump"
    )
    assert sev == "medium"


def test_suspicious_return_jump_high(client):
    """60 % close-to-close jump → high severity."""
    rows = [
        {
            "symbol": "JUMP2", "timestamp": "2024-01-02",
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000,
        },
        {
            "symbol": "JUMP2", "timestamp": "2024-01-03",
            "open": 160.0, "high": 161.0, "low": 159.0, "close": 160.0, "volume": 1000,
        },
    ]
    snap = _upload_rows(client, rows)
    types = [i["issue_type"] for i in snap["issues"]]
    assert "suspicious_return_jump" in types
    sev = next(
        i["severity"] for i in snap["issues"]
        if i["issue_type"] == "suspicious_return_jump"
    )
    assert sev == "high"


def test_health_score_decrements_for_critical(client):
    """One critical issue → score should be 100 - 25 = 75."""
    rows = _clean_ohlcv_rows(1)
    rows[0]["high"] = 100.0
    rows[0]["low"] = 120.0   # high < low — critical
    snap = _upload_rows(client, rows)
    issue_types = {i["issue_type"] for i in snap["issues"]}
    # high_lt_low is critical (−25); there may be other issues too.
    assert "high_lt_low" in issue_types
    assert snap["health_score"] <= 75


def test_health_score_floor_at_zero(client):
    """Multiple critical issues should not push score below 0."""
    # 5 rows each with high < low and a negative close — many critical issues.
    rows = []
    for i in range(5):
        rows.append({
            "symbol": "BAD",
            "timestamp": f"2024-01-{i + 2:02d}",
            "open": -1.0, "high": 10.0, "low": 50.0, "close": -1.0,
            "volume": -100,
        })
    snap = _upload_rows(client, rows)
    assert snap["health_score"] == 0


# ---------------------------------------------------------------------------
# Audit timeline event
# ---------------------------------------------------------------------------

def test_snapshot_upload_creates_audit_event(client):
    """POST /api/datasets/{id}/snapshots should create one audit timeline event."""
    pid = _get_project_id(client)
    d = _create_dataset(client, pid, f"AuditCheck {uuid.uuid4().hex[:6]}")

    before_resp = client.get("/api/timeline?limit=200")
    before_count = len(before_resp.json())

    client.post(
        f"/api/datasets/{d['id']}/snapshots",
        json={"version_label": "v1", "rows": _clean_ohlcv_rows()},
    )

    after_resp = client.get("/api/timeline?limit=200")
    after_count = len(after_resp.json())

    assert after_count == before_count + 1
    latest_event = after_resp.json()[0]
    assert latest_event["event_type"] == "dataset_snapshot_uploaded"
