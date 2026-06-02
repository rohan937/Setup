"""M37 dataset quality drill-down tests.

Covers:
  - Column quality analysis (null rates, numeric stats, IQR outliers, status)
  - Row quality sample detection (duplicates, invalid OHLC, suspicious returns, etc.)
  - Quality summary aggregation
  - GET /api/dataset-snapshots/{id}/quality-drilldown endpoint
  - POST /api/datasets/{id}/snapshots stores the 3 new quality JSON fields
"""

from __future__ import annotations

import uuid

import pytest

from app.services.dataset_quality_drilldown import (
    compute_column_quality,
    compute_dataset_quality_drilldown,
    compute_quality_summary,
    compute_row_quality_samples,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_project_id(client) -> str:
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    projects = resp.json()
    assert projects, "No projects in test DB"
    return projects[0]["id"]


def _create_dataset(client, project_id: str, name: str) -> dict:
    resp = client.post(
        "/api/datasets",
        json={"project_id": project_id, "name": name},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _clean_ohlcv_rows(n: int = 5, symbol: str = "AAPL") -> list[dict]:
    rows = []
    for i in range(n):
        close = 150.0 + i * 0.5
        rows.append({
            "symbol": symbol,
            "timestamp": f"2024-01-{i + 1:02d}",
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1_000_000,
        })
    return rows


# ===========================================================================
# TestColumnQuality
# ===========================================================================

class TestColumnQuality:
    def test_null_rate_computed(self):
        rows = [
            {"a": 1},
            {"a": None},
            {"a": 3},
            {"a": None},
        ]
        result = compute_column_quality(rows)
        col = next(c for c in result if c["column_name"] == "a")
        assert col["null_count"] == 2
        assert col["null_rate"] == 0.5

    def test_numeric_stats_computed(self):
        rows = [{"x": i} for i in range(1, 6)]  # 1,2,3,4,5
        result = compute_column_quality(rows)
        col = next(c for c in result if c["column_name"] == "x")
        assert col["min_value"] == 1.0
        assert col["max_value"] == 5.0
        assert col["mean_value"] == 3.0
        assert col["stddev_value"] is not None
        assert col["stddev_value"] > 0

    def test_outlier_count_iqr(self):
        # IQR-based outlier: values 1-10 plus a clear outlier at 1000
        rows = [{"v": i} for i in range(1, 11)] + [{"v": 1000}]
        result = compute_column_quality(rows)
        col = next(c for c in result if c["column_name"] == "v")
        assert col["outlier_count"] > 0, "Expected at least one IQR outlier"

    def test_quality_status_clean(self):
        rows = [{"x": i} for i in range(1, 6)]
        result = compute_column_quality(rows)
        col = result[0]
        assert col["quality_status"] == "clean"
        assert col["null_count"] == 0
        assert col["outlier_count"] == 0

    def test_quality_status_review(self):
        # One null out of 10 → null_rate = 0.1 → "review"
        rows = [{"x": i} for i in range(9)] + [{"x": None}]
        result = compute_column_quality(rows)
        col = result[0]
        assert col["quality_status"] == "review"

    def test_quality_status_weak(self):
        # 3 nulls out of 10 → null_rate = 0.3 > 0.2 → "weak"
        rows = [{"x": i} for i in range(7)] + [{"x": None}] * 3
        result = compute_column_quality(rows)
        col = result[0]
        assert col["quality_status"] == "weak"

    def test_quality_status_unusable(self):
        # 6 nulls out of 10 → null_rate = 0.6 > 0.5 → "unusable"
        rows = [{"x": i} for i in range(4)] + [{"x": None}] * 6
        result = compute_column_quality(rows)
        col = result[0]
        assert col["quality_status"] == "unusable"

    def test_no_zero_division_empty(self):
        result = compute_column_quality([])
        assert result == []

    def test_all_columns_covered(self):
        rows = [
            {"a": 1, "b": "hello", "c": None},
            {"a": 2, "b": "world", "d": 3.14},
        ]
        result = compute_column_quality(rows)
        col_names = {c["column_name"] for c in result}
        assert col_names == {"a", "b", "c", "d"}


# ===========================================================================
# TestRowQualitySamples
# ===========================================================================

class TestRowQualitySamples:
    def test_duplicate_rows_detected(self):
        row = {"symbol": "AAPL", "close": 150.0}
        rows = [row, row]  # exact duplicate
        samples = compute_row_quality_samples(rows)
        assert len(samples["duplicate_rows"]) >= 1

    def test_duplicate_symbol_timestamp_detected(self):
        rows = [
            {"symbol": "AAPL", "timestamp": "2024-01-01", "close": 150.0},
            {"symbol": "AAPL", "timestamp": "2024-01-01", "close": 151.0},
        ]
        samples = compute_row_quality_samples(rows)
        assert len(samples["duplicate_symbol_timestamp"]) >= 1

    def test_invalid_ohlc_detected(self):
        # close > high → invalid OHLC
        rows = [{
            "symbol": "AAPL",
            "timestamp": "2024-01-01",
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 110.0,  # above high
        }]
        samples = compute_row_quality_samples(rows)
        assert len(samples["invalid_ohlc_rows"]) >= 1

    def test_suspicious_return_detected(self):
        # 200% move from 100 → 300
        rows = [
            {"close": 100.0},
            {"close": 300.0},
        ]
        samples = compute_row_quality_samples(rows)
        assert len(samples["suspicious_return_rows"]) >= 1

    def test_missing_value_rows_detected(self):
        rows = [
            {"symbol": "AAPL", "close": None},
        ]
        samples = compute_row_quality_samples(rows)
        assert len(samples["missing_value_rows"]) >= 1

    def test_samples_capped_at_10(self):
        # 20 identical duplicate rows (each row identical)
        row = {"symbol": "X", "close": 50.0}
        rows = [row] * 20
        samples = compute_row_quality_samples(rows)
        assert len(samples["duplicate_rows"]) <= 10


# ===========================================================================
# TestQualitySummary
# ===========================================================================

class TestQualitySummary:
    def test_column_status_counts(self):
        rows = [{"a": i} for i in range(4)] + [{"a": None}] * 6  # unusable (60% null)
        col_quality = compute_column_quality(rows)
        row_samples = compute_row_quality_samples(rows)
        summary = compute_quality_summary(rows, col_quality, row_samples)
        assert summary["unusable_column_count"] == 1
        assert summary["clean_column_count"] == 0
        assert summary["total_columns"] == 1

    def test_suggested_checks_generated(self):
        # 80% null → "weak" → should trigger suggested check about null rate
        rows = [{"x": i} for i in range(2)] + [{"x": None}] * 8
        col_quality = compute_column_quality(rows)
        row_samples = compute_row_quality_samples(rows)
        summary = compute_quality_summary(rows, col_quality, row_samples)
        checks_text = " ".join(summary["suggested_checks"])
        assert "null" in checks_text.lower() or "20%" in checks_text

    def test_total_missing_values(self):
        rows = [
            {"a": 1, "b": None},
            {"a": None, "b": 2},
            {"a": 3, "b": 4},
        ]
        col_quality = compute_column_quality(rows)
        row_samples = compute_row_quality_samples(rows)
        summary = compute_quality_summary(rows, col_quality, row_samples)
        # column a has 1 null, column b has 1 null → total 2
        assert summary["total_missing_values"] == 2


# ===========================================================================
# TestDrilldownEndpoint
# ===========================================================================

class TestDrilldownEndpoint:
    def test_endpoint_returns_200(self, client, db):
        project_id = _get_project_id(client)
        dataset = _create_dataset(client, project_id, f"m37-endpoint-test-{uuid.uuid4().hex[:6]}")
        rows = _clean_ohlcv_rows(5)
        snap_resp = client.post(
            f"/api/datasets/{dataset['id']}/snapshots",
            json={"version_label": "v1", "rows": rows},
        )
        assert snap_resp.status_code == 201, snap_resp.text
        snapshot_id = snap_resp.json()["id"]

        try:
            resp = client.get(f"/api/dataset-snapshots/{snapshot_id}/quality-drilldown")
            assert resp.status_code == 200, resp.text
        finally:
            pass

    def test_response_has_required_fields(self, client, db):
        project_id = _get_project_id(client)
        dataset = _create_dataset(client, project_id, f"m37-fields-test-{uuid.uuid4().hex[:6]}")
        rows = _clean_ohlcv_rows(5)
        snap_resp = client.post(
            f"/api/datasets/{dataset['id']}/snapshots",
            json={"version_label": "v1", "rows": rows},
        )
        assert snap_resp.status_code == 201, snap_resp.text
        snapshot_id = snap_resp.json()["id"]

        try:
            resp = client.get(f"/api/dataset-snapshots/{snapshot_id}/quality-drilldown")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert "column_quality" in data
            assert "row_quality" in data
            assert "quality_summary" in data
            assert isinstance(data["column_quality"], list)
            assert "total_rows" in data["quality_summary"]
        finally:
            pass

    def test_unknown_snapshot_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/dataset-snapshots/{fake_id}/quality-drilldown")
        assert resp.status_code == 404

    def test_snapshot_creation_stores_quality(self, client, db):
        from app.models.dataset_snapshot import DatasetSnapshot

        project_id = _get_project_id(client)
        dataset = _create_dataset(client, project_id, f"m37-store-test-{uuid.uuid4().hex[:6]}")
        rows = _clean_ohlcv_rows(5)
        snap_resp = client.post(
            f"/api/datasets/{dataset['id']}/snapshots",
            json={"version_label": "v1", "rows": rows},
        )
        assert snap_resp.status_code == 201, snap_resp.text
        snapshot_id = uuid.UUID(snap_resp.json()["id"])

        try:
            snapshot = db.query(DatasetSnapshot).filter(
                DatasetSnapshot.id == snapshot_id
            ).first()
            assert snapshot is not None
            assert snapshot.column_quality_json is not None, "column_quality_json should be set"
            assert snapshot.row_quality_json is not None, "row_quality_json should be set"
            assert snapshot.quality_summary_json is not None, "quality_summary_json should be set"
            assert isinstance(snapshot.column_quality_json, list)
            assert isinstance(snapshot.quality_summary_json, dict)
        finally:
            pass

    def test_empty_rows_json_returns_empty_quality(self, client, db):
        project_id = _get_project_id(client)
        dataset = _create_dataset(client, project_id, f"m37-empty-test-{uuid.uuid4().hex[:6]}")
        snap_resp = client.post(
            f"/api/datasets/{dataset['id']}/snapshots",
            json={"version_label": "v-empty", "rows": []},
        )
        assert snap_resp.status_code == 201, snap_resp.text
        snapshot_id = snap_resp.json()["id"]

        try:
            resp = client.get(f"/api/dataset-snapshots/{snapshot_id}/quality-drilldown")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["column_quality"] == []
            assert data["quality_summary"]["total_rows"] == 0
        finally:
            pass
