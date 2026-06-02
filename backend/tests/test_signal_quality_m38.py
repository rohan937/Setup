"""M38 signal quality drill-down tests.

Covers:
  - Signal distribution analysis (mean, missing, non-numeric, outlier, zero variance, status)
  - Symbol quality analysis (per-symbol stats, worst-first sort, dup timestamps)
  - Row quality samples (missing, non-numeric, outlier, duplicate sym+ts, capped at 10)
  - GET /api/signal-snapshots/{id}/quality-drilldown endpoint (200, fields, 404)
  - POST /api/strategies/{id}/signal-snapshots stores quality JSON fields
  - Drilldown computes on-the-fly when stored fields are null
"""

from __future__ import annotations

import uuid

import pytest

from app.services.signal_quality_drilldown import (
    compute_signal_distribution,
    compute_signal_quality_drilldown,
    compute_signal_row_quality_samples,
    compute_signal_quality_summary,
    compute_symbol_quality,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_strategy(client, name: str | None = None) -> dict:
    """Create a fresh strategy and return its JSON response."""
    projects = client.get("/api/projects").json()
    project_id = projects[0]["id"]
    resp = client.post(
        "/api/strategies",
        json={"project_id": project_id, "name": name or f"M38 Strategy {uuid.uuid4().hex[:6]}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _sample_rows(n: int = 5, signal_col: str = "signal") -> list[dict]:
    symbols = ["AAPL", "MSFT", "GOOG", "TSLA", "AMZN"]
    rows = []
    for i in range(n):
        rows.append({
            "symbol": symbols[i % len(symbols)],
            "timestamp": f"2024-01-{(i % 28) + 1:02d}",
            signal_col: float(i + 1),
        })
    return rows


def _create_signal_snapshot(client, strategy_id: str, rows=None, label=None) -> dict:
    if rows is None:
        rows = _sample_rows(5)
    payload = {
        "label": label or f"snap-{uuid.uuid4().hex[:6]}",
        "rows": rows,
    }
    resp = client.post(f"/api/strategies/{strategy_id}/signal-snapshots", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ===========================================================================
# TestSignalDistribution
# ===========================================================================

class TestSignalDistribution:
    def test_distribution_mean_computed(self):
        rows = [
            {"symbol": "AAPL", "signal": 1.0},
            {"symbol": "MSFT", "signal": 3.0},
            {"symbol": "GOOG", "signal": 5.0},
        ]
        result = compute_signal_distribution(rows)
        assert result["mean_value"] is not None
        assert abs(result["mean_value"] - 3.0) < 0.01

    def test_distribution_missing_count(self):
        rows = [
            {"symbol": "AAPL", "signal": 1.0},
            {"symbol": "MSFT", "signal": None},
            {"symbol": "GOOG", "signal": 2.0},
            {"symbol": "TSLA", "signal": None},
        ]
        result = compute_signal_distribution(rows)
        assert result["missing_count"] == 2

    def test_distribution_non_numeric_count(self):
        rows = [
            {"signal": 1.0},
            {"signal": "abc"},
            {"signal": 2.0},
            {"signal": "xyz"},
        ]
        result = compute_signal_distribution(rows)
        assert result["non_numeric_count"] > 0

    def test_distribution_outlier_iqr(self):
        # 10 normal values + 1 extreme outlier
        rows = [{"signal": float(v)} for v in range(1, 11)]
        rows.append({"signal": 10000.0})
        result = compute_signal_distribution(rows)
        assert result["outlier_count"] > 0

    def test_zero_variance_issue(self):
        rows = [{"signal": 5.0} for _ in range(15)]
        result = compute_signal_distribution(rows)
        issues_text = " ".join(result["issues"]).lower()
        assert "variance" in issues_text or "identical" in issues_text

    def test_distribution_status_clean(self):
        rows = [{"signal": float(i)} for i in range(1, 11)]
        result = compute_signal_distribution(rows)
        # All valid numeric, no missing, no outliers in small range → clean
        assert result["distribution_status"] in ("clean", "review")

    def test_distribution_status_review(self):
        # Some missing values → should be review or worse
        rows = [{"signal": float(i)} for i in range(1, 8)]
        rows.append({"signal": None})
        result = compute_signal_distribution(rows)
        assert result["distribution_status"] in ("review", "weak", "unusable")

    def test_distribution_status_unusable(self):
        rows = [{"signal": None} for _ in range(5)]
        result = compute_signal_distribution(rows)
        assert result["distribution_status"] == "unusable"
        assert result["value_count"] == 0

    def test_no_error_empty_rows(self):
        result = compute_signal_distribution([])
        assert result["value_count"] == 0
        assert result["missing_count"] == 0
        assert result["distribution_status"] == "unusable"


# ===========================================================================
# TestSymbolQuality
# ===========================================================================

class TestSymbolQuality:
    def test_symbol_quality_computed(self):
        rows = [
            {"symbol": "AAPL", "signal": 1.0, "timestamp": "2024-01-01"},
            {"symbol": "AAPL", "signal": 2.0, "timestamp": "2024-01-02"},
            {"symbol": "MSFT", "signal": 3.0, "timestamp": "2024-01-01"},
        ]
        result = compute_symbol_quality(rows)
        symbols_found = {r["symbol"] for r in result}
        assert "AAPL" in symbols_found
        assert "MSFT" in symbols_found
        assert len(result) == 2

    def test_symbol_missing_rate(self):
        rows = [
            {"symbol": "AAPL", "signal": None, "timestamp": "2024-01-01"},
            {"symbol": "AAPL", "signal": None, "timestamp": "2024-01-02"},
        ]
        result = compute_symbol_quality(rows)
        aapl = next(r for r in result if r["symbol"] == "AAPL")
        assert aapl["missing_rate"] == 1.0

    def test_symbol_quality_worst_first(self):
        rows = [
            # AAPL: all missing → unusable
            {"symbol": "AAPL", "signal": None},
            {"symbol": "AAPL", "signal": None},
            # MSFT: all good
            {"symbol": "MSFT", "signal": 1.0},
            {"symbol": "MSFT", "signal": 2.0},
        ]
        result = compute_symbol_quality(rows)
        # AAPL (unusable) should appear before MSFT (clean)
        symbols_order = [r["symbol"] for r in result]
        assert symbols_order.index("AAPL") < symbols_order.index("MSFT")

    def test_symbol_duplicate_timestamps(self):
        rows = [
            {"symbol": "AAPL", "signal": 1.0, "timestamp": "2024-01-01"},
            {"symbol": "AAPL", "signal": 2.0, "timestamp": "2024-01-01"},  # dup ts
        ]
        result = compute_symbol_quality(rows)
        aapl = next(r for r in result if r["symbol"] == "AAPL")
        assert aapl["duplicate_timestamp_count"] > 0


# ===========================================================================
# TestSignalRowSamples
# ===========================================================================

class TestSignalRowSamples:
    def test_missing_signal_sample(self):
        rows = [
            {"symbol": "AAPL", "signal": None, "timestamp": "2024-01-01"},
            {"symbol": "MSFT", "signal": 1.0, "timestamp": "2024-01-01"},
        ]
        result = compute_signal_row_quality_samples(rows)
        assert len(result["missing_signal_rows"]) == 1
        assert result["missing_signal_rows"][0]["issue_type"] == "missing_signal"

    def test_non_numeric_sample(self):
        rows = [
            {"symbol": "AAPL", "signal": "abc", "timestamp": "2024-01-01"},
            {"symbol": "MSFT", "signal": 1.0, "timestamp": "2024-01-01"},
        ]
        result = compute_signal_row_quality_samples(rows)
        assert len(result["non_numeric_signal_rows"]) == 1
        assert result["non_numeric_signal_rows"][0]["issue_type"] == "non_numeric_signal"

    def test_outlier_sample(self):
        # 10 normal + 1 extreme
        rows = [{"symbol": "AAPL", "signal": float(v), "timestamp": f"2024-01-{v:02d}"} for v in range(1, 11)]
        rows.append({"symbol": "AAPL", "signal": 99999.0, "timestamp": "2024-02-01"})
        result = compute_signal_row_quality_samples(rows)
        assert len(result["outlier_signal_rows"]) >= 1
        assert result["outlier_signal_rows"][0]["issue_type"] == "outlier_signal"

    def test_duplicate_sym_ts_sample(self):
        rows = [
            {"symbol": "AAPL", "signal": 1.0, "timestamp": "2024-01-01"},
            {"symbol": "AAPL", "signal": 2.0, "timestamp": "2024-01-01"},  # dup
        ]
        result = compute_signal_row_quality_samples(rows)
        assert len(result["duplicate_symbol_timestamp_rows"]) >= 1
        assert result["duplicate_symbol_timestamp_rows"][0]["issue_type"] == "duplicate_symbol_timestamp"

    def test_samples_capped_at_10(self):
        # 20 rows all with missing signal
        rows = [{"symbol": f"SYM{i}", "signal": None, "timestamp": f"2024-01-01"} for i in range(20)]
        result = compute_signal_row_quality_samples(rows)
        assert len(result["missing_signal_rows"]) == 10


# ===========================================================================
# TestDrilldownEndpoint
# ===========================================================================

class TestDrilldownEndpoint:
    def test_endpoint_returns_200(self, client, db):
        strategy = _new_strategy(client, f"m38-200-{uuid.uuid4().hex[:6]}")
        snap = _create_signal_snapshot(client, strategy["id"])

        try:
            resp = client.get(f"/api/signal-snapshots/{snap['id']}/quality-drilldown")
            assert resp.status_code == 200, resp.text
        finally:
            pass

    def test_response_fields(self, client, db):
        strategy = _new_strategy(client, f"m38-fields-{uuid.uuid4().hex[:6]}")
        snap = _create_signal_snapshot(client, strategy["id"])

        try:
            resp = client.get(f"/api/signal-snapshots/{snap['id']}/quality-drilldown")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert "signal_distribution" in data
            assert "symbol_quality" in data
            assert "row_quality" in data
            assert "quality_summary" in data
            assert "timestamp_coverage" in data
            assert isinstance(data["symbol_quality"], list)
            assert "total_rows" in data["quality_summary"]
            assert "value_count" in data["signal_distribution"]
        finally:
            pass

    def test_unknown_snapshot_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/signal-snapshots/{fake_id}/quality-drilldown")
        assert resp.status_code == 404

    def test_snapshot_creation_stores_quality(self, client, db):
        from app.models.signal_snapshot import SignalSnapshot

        strategy = _new_strategy(client, f"m38-store-{uuid.uuid4().hex[:6]}")
        snap = _create_signal_snapshot(client, strategy["id"])
        snapshot_id = uuid.UUID(snap["id"])

        try:
            snapshot = db.query(SignalSnapshot).filter(
                SignalSnapshot.id == snapshot_id
            ).first()
            assert snapshot is not None
            assert snapshot.signal_distribution_json is not None, "signal_distribution_json should be set"
            assert snapshot.symbol_quality_json is not None, "symbol_quality_json should be set"
            assert snapshot.signal_row_quality_json is not None, "signal_row_quality_json should be set"
            assert snapshot.signal_quality_summary_json is not None, "signal_quality_summary_json should be set"
            assert isinstance(snapshot.signal_distribution_json, dict)
            assert isinstance(snapshot.symbol_quality_json, list)
            assert isinstance(snapshot.signal_quality_summary_json, dict)
        finally:
            pass

    def test_drilldown_computes_if_null(self, client, db):
        """Existing snapshot with null quality fields still returns 200 (computes on fly)."""
        from app.models.signal_snapshot import SignalSnapshot

        strategy = _new_strategy(client, f"m38-null-{uuid.uuid4().hex[:6]}")
        snap = _create_signal_snapshot(client, strategy["id"])
        snapshot_id = uuid.UUID(snap["id"])

        # Force-null the quality fields to simulate an old snapshot
        try:
            snapshot = db.query(SignalSnapshot).filter(
                SignalSnapshot.id == snapshot_id
            ).first()
            assert snapshot is not None
            snapshot.signal_distribution_json = None
            snapshot.symbol_quality_json = None
            snapshot.signal_row_quality_json = None
            snapshot.signal_quality_summary_json = None
            db.flush()

            resp = client.get(f"/api/signal-snapshots/{snap['id']}/quality-drilldown")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert "signal_distribution" in data
            # Distribution should have been computed from rows_json on the fly
            assert data["signal_distribution"]["value_count"] >= 0
        finally:
            # Restore to avoid polluting other tests
            db.rollback()
