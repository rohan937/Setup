"""M12 Dataset Snapshot Comparison tests.

Tests cover:
- compare two snapshots success (200, correct shape)
- compare rejects missing dataset (404)
- compare rejects missing snapshot A (404)
- compare rejects missing snapshot B (404)
- compare rejects snapshot from different dataset (400)
- compare same snapshot to itself returns is_same_snapshot=True and no changes
- row_count / column_count changes detected
- added / removed columns detected
- changed inferred types detected
- added / removed symbols detected
- timestamp range changes detected
- health_score delta detected
- issue count / worst severity changed detected
- issue types added / removed detected
- keyed row added / removed / changed detected
- OHLCV value revision example returned
- value revision examples capped at MAX_EXAMPLES
- deterministic explanation avoids causal claims
- existing M2–M11 tests still pass (via full suite run)
"""

from __future__ import annotations

import uuid

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_project_id(client) -> str:
    return client.get("/api/projects").json()[0]["id"]


def _create_dataset(client, name: str | None = None) -> dict:
    pid = _get_project_id(client)
    resp = client.post("/api/datasets", json={
        "project_id": pid,
        "name": name or f"CmpDataset {uuid.uuid4().hex[:6]}",
        "dataset_type": "ohlcv",
        "source_type": "manual",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload_snapshot(client, dataset_id: str, label: str, rows: list) -> dict:
    resp = client.post(f"/api/datasets/{dataset_id}/snapshots", json={
        "version_label": label,
        "rows": rows,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _compare(client, dataset_id: str, snap_a_id: str, snap_b_id: str):
    return client.get(
        f"/api/datasets/{dataset_id}/snapshots/compare"
        f"?snapshot_a_id={snap_a_id}&snapshot_b_id={snap_b_id}"
    )


# Standard OHLCV rows used across multiple tests.
ROWS_V1 = [
    {"symbol": "AAPL", "timestamp": "2024-01-02", "open": 185.0, "high": 188.0, "low": 184.0, "close": 187.0, "volume": 52000000},
    {"symbol": "AAPL", "timestamp": "2024-01-03", "open": 187.0, "high": 190.0, "low": 186.0, "close": 189.0, "volume": 48000000},
    {"symbol": "MSFT", "timestamp": "2024-01-02", "open": 375.0, "high": 380.0, "low": 374.0, "close": 378.0, "volume": 22000000},
    {"symbol": "MSFT", "timestamp": "2024-01-03", "open": 378.0, "high": 382.0, "low": 377.0, "close": 381.0, "volume": 20000000},
]

# V2: same structure, more rows (extended date range), one value revised.
ROWS_V2 = [
    {"symbol": "AAPL", "timestamp": "2024-01-02", "open": 185.0, "high": 188.0, "low": 184.0, "close": 184.91, "volume": 52000000},  # close revised
    {"symbol": "AAPL", "timestamp": "2024-01-03", "open": 187.0, "high": 190.0, "low": 186.0, "close": 189.0, "volume": 48000000},
    {"symbol": "AAPL", "timestamp": "2024-01-04", "open": 189.0, "high": 192.0, "low": 188.0, "close": 191.0, "volume": 45000000},  # new row
    {"symbol": "MSFT", "timestamp": "2024-01-02", "open": 375.0, "high": 380.0, "low": 374.0, "close": 378.0, "volume": 22000000},
    {"symbol": "MSFT", "timestamp": "2024-01-03", "open": 378.0, "high": 382.0, "low": 377.0, "close": 381.0, "volume": 20000000},
]


# ===========================================================================
# Basic shape and routing
# ===========================================================================

class TestCompareBasicShape:
    def test_compare_returns_200(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)
        resp = _compare(client, ds["id"], s1["id"], s2["id"])
        assert resp.status_code == 200, resp.text

    def test_compare_response_has_top_level_fields(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        for field in (
            "dataset_id", "snapshot_a_id", "snapshot_b_id",
            "snapshot_a_label", "snapshot_b_label",
            "is_same_snapshot", "summary",
            "metadata", "schema_diff", "symbol_coverage", "timestamp_coverage",
            "data_health", "value_revisions",
            "highlighted_changes", "deterministic_explanation",
            "warnings", "generated_at",
        ):
            assert field in data, f"Missing field: {field}"

    def test_compare_snapshot_labels_correct(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "baseline-v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "revision-v2", ROWS_V2)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        assert data["snapshot_a_label"] == "baseline-v1"
        assert data["snapshot_b_label"] == "revision-v2"


# ===========================================================================
# Error cases
# ===========================================================================

class TestCompareErrors:
    def test_compare_unknown_dataset_returns_404(self, client):
        # Create a real snapshot for the IDs
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1[:1])
        resp = client.get(
            f"/api/datasets/{uuid.uuid4()}/snapshots/compare"
            f"?snapshot_a_id={s1['id']}&snapshot_b_id={s1['id']}"
        )
        assert resp.status_code == 404

    def test_compare_unknown_snapshot_a_returns_404(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1[:1])
        resp = _compare(client, ds["id"], str(uuid.uuid4()), s1["id"])
        assert resp.status_code == 404

    def test_compare_unknown_snapshot_b_returns_404(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1[:1])
        resp = _compare(client, ds["id"], s1["id"], str(uuid.uuid4()))
        assert resp.status_code == 404

    def test_compare_snapshot_from_different_dataset_returns_400(self, client):
        ds1 = _create_dataset(client)
        ds2 = _create_dataset(client)
        s1 = _upload_snapshot(client, ds1["id"], "v1", ROWS_V1[:1])
        s2 = _upload_snapshot(client, ds2["id"], "v1", ROWS_V1[:1])
        # Ask dataset 1 to compare with snapshot from dataset 2.
        resp = _compare(client, ds1["id"], s1["id"], s2["id"])
        assert resp.status_code == 400


# ===========================================================================
# Same snapshot
# ===========================================================================

class TestCompareSameSnapshot:
    def test_same_snapshot_returns_is_same_snapshot_true(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        data = _compare(client, ds["id"], s1["id"], s1["id"]).json()
        assert data["is_same_snapshot"] is True

    def test_same_snapshot_has_zero_row_count_delta(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        data = _compare(client, ds["id"], s1["id"], s1["id"]).json()
        assert data["metadata"]["row_count_delta"] == 0

    def test_same_snapshot_has_zero_schema_changes(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        data = _compare(client, ds["id"], s1["id"], s1["id"]).json()
        assert data["schema_diff"]["total_changes"] == 0
        assert data["schema_diff"]["added_columns"] == []
        assert data["schema_diff"]["removed_columns"] == []

    def test_same_snapshot_no_value_revisions(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        data = _compare(client, ds["id"], s1["id"], s1["id"]).json()
        rev = data["value_revisions"]
        assert rev["added_rows_count"] == 0
        assert rev["removed_rows_count"] == 0
        assert rev["changed_rows_count"] == 0

    def test_same_snapshot_explanation_mentions_no_changes(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        data = _compare(client, ds["id"], s1["id"], s1["id"]).json()
        exp = data["deterministic_explanation"].lower()
        assert "same snapshot" in exp or "no changes" in exp


# ===========================================================================
# Metadata section
# ===========================================================================

class TestCompareMetadata:
    def test_row_count_delta_detected(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)   # 4 rows
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)   # 5 rows
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        meta = data["metadata"]
        assert meta["row_count_a"] == 4
        assert meta["row_count_b"] == 5
        assert meta["row_count_delta"] == 1

    def test_row_count_decrease_detected(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V2)   # 5 rows
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V1)   # 4 rows
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        assert data["metadata"]["row_count_delta"] == -1

    def test_row_count_in_highlighted_changes(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        assert any("row_count" in h.lower() for h in data["highlighted_changes"])


# ===========================================================================
# Schema section
# ===========================================================================

class TestCompareSchema:
    def test_added_columns_detected(self, client):
        ds = _create_dataset(client)
        rows_a = [{"symbol": "AAPL", "timestamp": "2024-01-01", "close": 150.0}]
        rows_b = [{"symbol": "AAPL", "timestamp": "2024-01-01", "close": 150.0,
                   "adjusted_close": 149.5, "dividend": 0.24}]
        s1 = _upload_snapshot(client, ds["id"], "v1", rows_a)
        s2 = _upload_snapshot(client, ds["id"], "v2", rows_b)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        schema = data["schema_diff"]
        assert "adjusted_close" in schema["added_columns"]
        assert "dividend" in schema["added_columns"]
        assert schema["total_changes"] >= 2

    def test_removed_columns_detected(self, client):
        ds = _create_dataset(client)
        rows_a = [{"symbol": "AAPL", "timestamp": "2024-01-01", "close": 150.0, "volume": 1000}]
        rows_b = [{"symbol": "AAPL", "timestamp": "2024-01-01", "close": 150.0}]
        s1 = _upload_snapshot(client, ds["id"], "v1", rows_a)
        s2 = _upload_snapshot(client, ds["id"], "v2", rows_b)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        schema = data["schema_diff"]
        assert "volume" in schema["removed_columns"]

    def test_added_columns_in_highlighted_changes(self, client):
        ds = _create_dataset(client)
        rows_a = [{"symbol": "AAPL", "timestamp": "2024-01-01", "close": 150.0}]
        rows_b = [{"symbol": "AAPL", "timestamp": "2024-01-01", "close": 150.0,
                   "adjusted_close": 149.5}]
        s1 = _upload_snapshot(client, ds["id"], "v1", rows_a)
        s2 = _upload_snapshot(client, ds["id"], "v2", rows_b)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        assert any("column" in h.lower() and "added" in h.lower()
                   for h in data["highlighted_changes"])

    def test_type_change_detected(self, client):
        ds = _create_dataset(client)
        rows_a = [{"symbol": "AAPL", "timestamp": "2024-01-01", "close": 150.0}]
        rows_b = [{"symbol": "AAPL", "timestamp": "2024-01-01", "close": "150.00"}]  # string now
        s1 = _upload_snapshot(client, ds["id"], "v1", rows_a)
        s2 = _upload_snapshot(client, ds["id"], "v2", rows_b)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        type_changes = data["schema_diff"]["type_changes"]
        close_change = next((tc for tc in type_changes if tc["column"] == "close"), None)
        assert close_change is not None
        assert close_change["type_a"] == "number"
        assert close_change["type_b"] == "string"


# ===========================================================================
# Symbol coverage section
# ===========================================================================

class TestCompareSymbolCoverage:
    def test_added_symbols_detected(self, client):
        ds = _create_dataset(client)
        rows_a = [{"symbol": "AAPL", "timestamp": "2024-01-01", "close": 150.0}]
        rows_b = [
            {"symbol": "AAPL", "timestamp": "2024-01-01", "close": 150.0},
            {"symbol": "GOOG", "timestamp": "2024-01-01", "close": 140.0},
        ]
        s1 = _upload_snapshot(client, ds["id"], "v1", rows_a)
        s2 = _upload_snapshot(client, ds["id"], "v2", rows_b)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        sym = data["symbol_coverage"]
        assert "GOOG" in sym["added_symbols"]
        assert sym["symbol_count_delta"] == 1

    def test_removed_symbols_detected(self, client):
        ds = _create_dataset(client)
        rows_a = [
            {"symbol": "AAPL", "timestamp": "2024-01-01", "close": 150.0},
            {"symbol": "MSFT", "timestamp": "2024-01-01", "close": 350.0},
        ]
        rows_b = [{"symbol": "AAPL", "timestamp": "2024-01-01", "close": 150.0}]
        s1 = _upload_snapshot(client, ds["id"], "v1", rows_a)
        s2 = _upload_snapshot(client, ds["id"], "v2", rows_b)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        sym = data["symbol_coverage"]
        assert "MSFT" in sym["removed_symbols"]
        assert sym["symbol_count_delta"] == -1

    def test_common_symbols_counted(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)  # AAPL + MSFT
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)  # AAPL + MSFT
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        assert data["symbol_coverage"]["common_symbols_count"] == 2

    def test_added_symbols_in_highlighted_changes(self, client):
        ds = _create_dataset(client)
        rows_a = [{"symbol": "AAPL", "timestamp": "2024-01-01", "close": 150.0}]
        rows_b = [
            {"symbol": "AAPL", "timestamp": "2024-01-01", "close": 150.0},
            {"symbol": "GOOG", "timestamp": "2024-01-01", "close": 140.0},
        ]
        s1 = _upload_snapshot(client, ds["id"], "v1", rows_a)
        s2 = _upload_snapshot(client, ds["id"], "v2", rows_b)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        assert any("symbol" in h.lower() and "added" in h.lower()
                   for h in data["highlighted_changes"])

    def test_no_symbol_column_sets_keyed_false(self, client):
        ds = _create_dataset(client)
        rows_a = [{"timestamp": "2024-01-01", "value": 1.0}]
        rows_b = [{"timestamp": "2024-01-01", "value": 2.0}]
        s1 = _upload_snapshot(client, ds["id"], "v1", rows_a)
        s2 = _upload_snapshot(client, ds["id"], "v2", rows_b)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        assert data["symbol_coverage"]["keyed_by_symbol"] is False


# ===========================================================================
# Timestamp coverage section
# ===========================================================================

class TestCompareTimestampCoverage:
    def test_timestamp_range_change_detected(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)  # Jan 2–3
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)  # Jan 2–4
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        ts = data["timestamp_coverage"]
        assert ts["max_changed"] is True
        assert ts["max_timestamp_b"] == "2024-01-04"

    def test_date_range_days_delta_positive(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        ts = data["timestamp_coverage"]
        assert ts["date_range_days_delta"] is not None
        assert ts["date_range_days_delta"] > 0

    def test_min_timestamp_unchanged_when_same(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        ts = data["timestamp_coverage"]
        assert ts["min_changed"] is False  # both start at 2024-01-02

    def test_timestamp_change_in_highlighted(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        # At least one timestamp highlight when max changed
        has_ts = any("timestamp" in h.lower() or "date" in h.lower()
                     for h in data["highlighted_changes"])
        assert has_ts


# ===========================================================================
# Data health section
# ===========================================================================

class TestCompareDataHealth:
    def test_health_score_delta_detected(self, client):
        ds = _create_dataset(client)
        # Clean rows → health 100.
        clean = [{"symbol": "AAPL", "timestamp": "2024-01-02",
                  "open": 185.0, "high": 188.0, "low": 184.0, "close": 187.0, "volume": 1000}]
        # Row with high > low violation → health drops.
        bad = [{"symbol": "AAPL", "timestamp": "2024-01-02",
                "open": 185.0, "high": 180.0, "low": 190.0, "close": 187.0, "volume": 1000}]
        s1 = _upload_snapshot(client, ds["id"], "v1", clean)
        s2 = _upload_snapshot(client, ds["id"], "v2", bad)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        h = data["data_health"]
        assert h["health_score_a"] == 100
        assert h["health_score_b"] < 100
        assert h["health_score_delta"] < 0

    def test_issue_count_delta_detected(self, client):
        ds = _create_dataset(client)
        clean = [{"symbol": "AAPL", "timestamp": "2024-01-02",
                  "open": 185.0, "high": 188.0, "low": 184.0, "close": 187.0, "volume": 1000}]
        bad = [{"symbol": "AAPL", "timestamp": "2024-01-02",
                "open": 185.0, "high": 180.0, "low": 190.0, "close": 187.0, "volume": 1000}]
        s1 = _upload_snapshot(client, ds["id"], "v1", clean)
        s2 = _upload_snapshot(client, ds["id"], "v2", bad)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        h = data["data_health"]
        assert h["issue_count_b"] > h["issue_count_a"]
        assert h["issue_count_delta"] > 0

    def test_worst_severity_reported(self, client):
        ds = _create_dataset(client)
        bad = [{"symbol": "AAPL", "timestamp": "2024-01-02",
                "open": 185.0, "high": 180.0, "low": 190.0, "close": 187.0, "volume": 1000}]
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", bad)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        h = data["data_health"]
        assert h["worst_severity_a"] is None  # ROWS_V1 is clean
        assert h["worst_severity_b"] is not None

    def test_issue_types_added_detected(self, client):
        ds = _create_dataset(client)
        clean = [{"symbol": "AAPL", "timestamp": "2024-01-02",
                  "open": 185.0, "high": 188.0, "low": 184.0, "close": 187.0, "volume": 1000}]
        bad_price = [{"symbol": "AAPL", "timestamp": "2024-01-02",
                      "open": 185.0, "high": 180.0, "low": 190.0, "close": 187.0, "volume": 1000}]
        s1 = _upload_snapshot(client, ds["id"], "v1", clean)
        s2 = _upload_snapshot(client, ds["id"], "v2", bad_price)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        h = data["data_health"]
        # high_lt_low should appear in B but not A.
        assert "high_lt_low" in h["issue_types_b"]
        assert "high_lt_low" in h["issue_types_added"]

    def test_health_delta_in_highlighted_changes(self, client):
        ds = _create_dataset(client)
        clean = [{"symbol": "AAPL", "timestamp": "2024-01-02",
                  "open": 185.0, "high": 188.0, "low": 184.0, "close": 187.0, "volume": 1000}]
        bad = [{"symbol": "AAPL", "timestamp": "2024-01-02",
                "open": 185.0, "high": 180.0, "low": 190.0, "close": 187.0, "volume": 1000}]
        s1 = _upload_snapshot(client, ds["id"], "v1", clean)
        s2 = _upload_snapshot(client, ds["id"], "v2", bad)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        assert any("health" in h.lower() for h in data["highlighted_changes"])


# ===========================================================================
# Value revisions section
# ===========================================================================

class TestCompareValueRevisions:
    def test_value_revisions_available_with_symbol_timestamp(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        rev = data["value_revisions"]
        assert rev["keyed_comparison_available"] is True

    def test_changed_row_detected(self, client):
        """AAPL 2024-01-02 close changed from 187.0 to 184.91."""
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        rev = data["value_revisions"]
        assert rev["changed_rows_count"] >= 1

    def test_added_row_detected(self, client):
        """AAPL 2024-01-04 is new in V2."""
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        rev = data["value_revisions"]
        assert rev["added_rows_count"] >= 1

    def test_removed_row_detected(self, client):
        ds = _create_dataset(client)
        # V1 has AAPL 2024-01-03; V2_no_jan3 does not.
        rows_v2_no_jan3 = [r for r in ROWS_V2 if r["timestamp"] != "2024-01-03"]
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", rows_v2_no_jan3)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        rev = data["value_revisions"]
        assert rev["removed_rows_count"] >= 1

    def test_ohlcv_field_delta_in_example(self, client):
        """The AAPL close revision should appear with a numeric delta."""
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        examples = data["value_revisions"]["examples"]
        changed = [e for e in examples if e["change_type"] == "changed"]
        assert len(changed) >= 1
        # The changed AAPL row should have a close delta.
        aapl_change = next(
            (e for e in changed
             if e.get("symbol") == "AAPL" and e.get("timestamp") == "2024-01-02"),
            None,
        )
        assert aapl_change is not None, "Expected AAPL 2024-01-02 change example"
        assert "close" in aapl_change["changed_fields"]
        # Delta should be negative (187.0 → 184.91)
        assert "close" in aapl_change["field_deltas"]
        assert aapl_change["field_deltas"]["close"] < 0

    def test_ohlcv_example_in_highlighted_changes(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        # Should mention row changes in highlights.
        has_row_change = any(
            "row" in h.lower() or "keyed" in h.lower() or "changed" in h.lower()
            for h in data["highlighted_changes"]
        )
        assert has_row_change

    def test_value_revision_examples_capped_at_max(self, client):
        """Create 25 changed rows — examples should be capped at MAX_EXAMPLES (20)."""
        from app.services.dataset_comparison import MAX_EXAMPLES
        ds = _create_dataset(client)
        rows_a = [
            {"symbol": f"SYM{i:03d}", "timestamp": "2024-01-01",
             "close": float(100 + i)}
            for i in range(25)
        ]
        rows_b = [
            {"symbol": f"SYM{i:03d}", "timestamp": "2024-01-01",
             "close": float(200 + i)}   # all closes changed
            for i in range(25)
        ]
        s1 = _upload_snapshot(client, ds["id"], "v1", rows_a)
        s2 = _upload_snapshot(client, ds["id"], "v2", rows_b)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        rev = data["value_revisions"]
        assert len(rev["examples"]) <= MAX_EXAMPLES
        assert rev["total_examples_capped"] is True

    def test_hash_fallback_when_no_keying_possible(self, client):
        """Rows without symbol+timestamp fall back to hash comparison."""
        ds = _create_dataset(client)
        rows_a = [{"value": 1.0}, {"value": 2.0}]
        rows_b = [{"value": 1.0}, {"value": 3.0}]  # second row changed
        s1 = _upload_snapshot(client, ds["id"], "v1", rows_a)
        s2 = _upload_snapshot(client, ds["id"], "v2", rows_b)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        rev = data["value_revisions"]
        assert rev["keyed_comparison_available"] is False
        # Hash-based: 1 row added (new hash), 1 row removed (old hash).
        assert rev["added_rows_count"] + rev["removed_rows_count"] >= 1


# ===========================================================================
# Explanation quality
# ===========================================================================

class TestCompareExplanation:
    def test_explanation_does_not_use_causal_language(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        exp = data["deterministic_explanation"].lower()
        for banned in ("caused", "because", "therefore", "resulted in"):
            assert banned not in exp, f"Explanation contains banned word: {banned!r}"

    def test_explanation_mentions_deterministic(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        exp = data["deterministic_explanation"].lower()
        assert "deterministic" in exp

    def test_explanation_contains_hedged_language(self, client):
        ds = _create_dataset(client)
        s1 = _upload_snapshot(client, ds["id"], "v1", ROWS_V1)
        s2 = _upload_snapshot(client, ds["id"], "v2", ROWS_V2)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        exp = data["deterministic_explanation"].lower()
        hedged = any(phrase in exp for phrase in (
            "may affect", "observed", "noted", "requires review",
        ))
        assert hedged, "Expected hedged language in explanation"


# ===========================================================================
# Warnings
# ===========================================================================

class TestCompareWarnings:
    def test_different_columns_produces_warning(self, client):
        ds = _create_dataset(client)
        rows_a = [{"symbol": "AAPL", "timestamp": "2024-01-01", "close": 150.0}]
        rows_b = [{"symbol": "AAPL", "timestamp": "2024-01-01", "adjusted_close": 149.5}]
        s1 = _upload_snapshot(client, ds["id"], "v1", rows_a)
        s2 = _upload_snapshot(client, ds["id"], "v2", rows_b)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        assert len(data["warnings"]) >= 1

    def test_capped_examples_produces_warning(self, client):
        ds = _create_dataset(client)
        rows_a = [
            {"symbol": f"S{i}", "timestamp": "2024-01-01", "close": float(i)}
            for i in range(25)
        ]
        rows_b = [
            {"symbol": f"S{i}", "timestamp": "2024-01-01", "close": float(i + 100)}
            for i in range(25)
        ]
        s1 = _upload_snapshot(client, ds["id"], "v1", rows_a)
        s2 = _upload_snapshot(client, ds["id"], "v2", rows_b)
        data = _compare(client, ds["id"], s1["id"], s2["id"]).json()
        assert any("capped" in w.lower() or "20" in w for w in data["warnings"])
