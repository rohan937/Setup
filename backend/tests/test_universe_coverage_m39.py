"""M39 universe coverage analysis tests.

Covers:
  - compute_symbol_quality: clean, duplicate, space, empty, long symbols
  - compute_universe_delta: no previous, stable, review, high_churn, added/removed counts, capped list
  - compute_metadata_breakdown: no metadata warning, sector breakdown, coverage rate
  - GET /api/universe-snapshots/{id}/coverage-analysis: 200, fields, 404
  - POST /api/strategies/{id}/universe-snapshots stores coverage JSON fields
  - Drilldown computes on-the-fly when stored fields are null
  - Run linkage: linkage_status == "linked" when run references snapshot
"""

from __future__ import annotations

import uuid

import pytest

from app.services.universe_coverage import (
    compute_metadata_breakdown,
    compute_symbol_quality,
    compute_universe_delta,
    compute_universe_quality_summary,
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
        json={"project_id": project_id, "name": name or f"M39 Strategy {uuid.uuid4().hex[:6]}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_universe_snapshot(
    client,
    strategy_id: str,
    label: str = "uni-snap-m39",
    symbols: list[str] | None = None,
    **extra,
) -> dict:
    payload = {
        "label": label,
        "symbols": symbols if symbols is not None else ["AAPL", "MSFT", "GOOG"],
        **extra,
    }
    resp = client.post(f"/api/strategies/{strategy_id}/universe-snapshots", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_run(client, strategy_id: str, run_name: str | None = None, **extra) -> dict:
    payload = {
        "run_name": run_name or f"run-{uuid.uuid4().hex[:6]}",
        "run_type": "backtest",
        **extra,
    }
    resp = client.post(f"/api/strategies/{strategy_id}/runs", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ===========================================================================
# TestSymbolQuality
# ===========================================================================

class TestSymbolQuality:
    def test_clean_valid_symbols(self):
        symbols = ["AAPL", "MSFT", "GOOG", "TSLA"]
        result = compute_symbol_quality(symbols)
        assert len(result) == 4
        for r in result:
            assert r["quality_status"] == "clean", f"{r['symbol']} not clean: {r['issues']}"

    def test_duplicate_detected(self):
        symbols = ["AAPL", "AAPL", "MSFT"]
        result = compute_symbol_quality(symbols)
        # First AAPL is clean, second is duplicate
        aapl_entries = [r for r in result if r["symbol"] == "AAPL"]
        assert len(aapl_entries) == 2
        assert aapl_entries[0]["is_duplicate"] is False
        assert aapl_entries[1]["is_duplicate"] is True
        assert aapl_entries[1]["quality_status"] == "review"

    def test_space_in_symbol_review(self):
        symbols = ["AAPL XYZ"]
        result = compute_symbol_quality(symbols)
        assert result[0]["quality_status"] == "review"
        assert any("spaces" in i for i in result[0]["issues"])

    def test_empty_symbol_weak(self):
        for sym in ["", "   "]:
            result = compute_symbol_quality([sym])
            assert result[0]["quality_status"] == "weak", f"Expected weak for {sym!r}"

    def test_long_symbol_review(self):
        symbols = ["TOOLONGTICKERHERE"]  # 17 chars > 15
        result = compute_symbol_quality(symbols)
        assert result[0]["quality_status"] == "review"
        assert any("long" in i.lower() for i in result[0]["issues"])


# ===========================================================================
# TestUniverseDelta
# ===========================================================================

class TestUniverseDelta:
    def test_no_previous_snapshot(self, client, db):
        strat = _new_strategy(client, name=f"M39-delta-noprev-{uuid.uuid4().hex[:6]}")
        snap = _create_universe_snapshot(client, strat["id"], symbols=["AAPL", "MSFT"])
        from app.models.universe_snapshot import UniverseSnapshot
        snap_obj = db.query(UniverseSnapshot).filter(
            UniverseSnapshot.id == uuid.UUID(snap["id"])
        ).first()
        try:
            delta = compute_universe_delta(snap_obj, db)
            assert delta["delta_status"] == "no_previous_snapshot"
            assert delta["has_previous"] is False
        finally:
            pass

    def test_stable_delta(self, client, db):
        strat = _new_strategy(client, name=f"M39-delta-stable-{uuid.uuid4().hex[:6]}")
        snap1 = _create_universe_snapshot(client, strat["id"], label="snap1", symbols=["AAPL", "MSFT"])
        snap2 = _create_universe_snapshot(client, strat["id"], label="snap2", symbols=["AAPL", "MSFT"])
        from app.models.universe_snapshot import UniverseSnapshot
        snap2_obj = db.query(UniverseSnapshot).filter(
            UniverseSnapshot.id == uuid.UUID(snap2["id"])
        ).first()
        try:
            delta = compute_universe_delta(snap2_obj, db)
            assert delta["has_previous"] is True
            assert delta["churn_rate"] == 0.0
            assert delta["delta_status"] == "stable"
        finally:
            pass

    def test_review_delta(self, client, db):
        # 8 symbols in common, add 3 new = 30% churn (> 0.2, <= 0.5)
        base = [f"SYM{i:02d}" for i in range(8)]
        next_syms = base + ["NEW1", "NEW2", "NEW3"]
        strat = _new_strategy(client, name=f"M39-delta-review-{uuid.uuid4().hex[:6]}")
        _create_universe_snapshot(client, strat["id"], label="snap1", symbols=base)
        snap2 = _create_universe_snapshot(client, strat["id"], label="snap2", symbols=next_syms)
        from app.models.universe_snapshot import UniverseSnapshot
        snap2_obj = db.query(UniverseSnapshot).filter(
            UniverseSnapshot.id == uuid.UUID(snap2["id"])
        ).first()
        try:
            delta = compute_universe_delta(snap2_obj, db)
            assert delta["has_previous"] is True
            assert delta["delta_status"] == "review", f"Expected review, got {delta['delta_status']} (churn={delta['churn_rate']})"
        finally:
            pass

    def test_high_churn_delta(self, client, db):
        # Completely replace symbols: 60%+ churn
        base = ["AAPL", "MSFT", "GOOG", "TSLA", "AMZN"]
        next_syms = ["X1", "X2", "X3", "X4", "X5", "X6", "X7"]
        strat = _new_strategy(client, name=f"M39-delta-highchurn-{uuid.uuid4().hex[:6]}")
        _create_universe_snapshot(client, strat["id"], label="snap1", symbols=base)
        snap2 = _create_universe_snapshot(client, strat["id"], label="snap2", symbols=next_syms)
        from app.models.universe_snapshot import UniverseSnapshot
        snap2_obj = db.query(UniverseSnapshot).filter(
            UniverseSnapshot.id == uuid.UUID(snap2["id"])
        ).first()
        try:
            delta = compute_universe_delta(snap2_obj, db)
            assert delta["has_previous"] is True
            assert delta["delta_status"] == "high_churn", f"Expected high_churn, got {delta['delta_status']} (churn={delta['churn_rate']})"
        finally:
            pass

    def test_added_removed_counts(self, client, db):
        base = ["AAPL", "MSFT", "GOOG", "TSLA", "AMZN", "FB", "NFLX", "NVDA"]
        next_syms = ["AAPL", "MSFT", "GOOG", "TSLA", "AMZN", "NEW1", "NEW2", "NEW3", "NEW4", "NEW5"]
        strat = _new_strategy(client, name=f"M39-delta-counts-{uuid.uuid4().hex[:6]}")
        _create_universe_snapshot(client, strat["id"], label="snap1", symbols=base)
        snap2 = _create_universe_snapshot(client, strat["id"], label="snap2", symbols=next_syms)
        from app.models.universe_snapshot import UniverseSnapshot
        snap2_obj = db.query(UniverseSnapshot).filter(
            UniverseSnapshot.id == uuid.UUID(snap2["id"])
        ).first()
        try:
            delta = compute_universe_delta(snap2_obj, db)
            assert delta["added_count"] == 5
            assert delta["removed_count"] == 3
        finally:
            pass

    def test_added_symbols_capped_at_50(self, client, db):
        base = ["BASE"]
        next_syms = ["BASE"] + [f"NEW{i:03d}" for i in range(60)]
        strat = _new_strategy(client, name=f"M39-delta-cap-{uuid.uuid4().hex[:6]}")
        _create_universe_snapshot(client, strat["id"], label="snap1", symbols=base)
        snap2 = _create_universe_snapshot(client, strat["id"], label="snap2", symbols=next_syms)
        from app.models.universe_snapshot import UniverseSnapshot
        snap2_obj = db.query(UniverseSnapshot).filter(
            UniverseSnapshot.id == uuid.UUID(snap2["id"])
        ).first()
        try:
            delta = compute_universe_delta(snap2_obj, db)
            assert delta["added_count"] == 60
            assert len(delta["added_symbols"]) == 50
        finally:
            pass


# ===========================================================================
# TestMetadataBreakdown
# ===========================================================================

class TestMetadataBreakdown:
    def _make_snapshot_stub(self, symbols, metadata_json=None):
        class _Stub:
            pass

        stub = _Stub()
        stub.symbols_json = symbols
        stub.metadata_json = metadata_json
        return stub

    def test_no_symbol_metadata_warning(self):
        snap = self._make_snapshot_stub(["AAPL", "MSFT"], metadata_json=None)
        result = compute_metadata_breakdown(snap)
        assert result["has_symbol_metadata"] is False
        assert len(result["warnings"]) > 0
        assert any("metadata" in w.lower() for w in result["warnings"])

    def test_sector_breakdown_computed(self):
        symbols = ["AAPL", "MSFT", "GOOG"]
        meta = {
            "symbols": {
                "AAPL": {"sector": "Technology"},
                "MSFT": {"sector": "Technology"},
                "GOOG": {"sector": "Communication"},
            }
        }
        snap = self._make_snapshot_stub(symbols, metadata_json=meta)
        result = compute_metadata_breakdown(snap)
        assert result["has_symbol_metadata"] is True
        assert result["by_sector"].get("Technology") == 2
        assert result["by_sector"].get("Communication") == 1

    def test_coverage_rate_computed(self):
        symbols = ["AAPL", "MSFT", "GOOG"]
        meta = {
            "symbols": {
                "AAPL": {"sector": "Technology"},
                "MSFT": {"sector": "Technology"},
                # GOOG missing from metadata
            }
        }
        snap = self._make_snapshot_stub(symbols, metadata_json=meta)
        result = compute_metadata_breakdown(snap)
        assert result["has_symbol_metadata"] is True
        assert abs(result["metadata_coverage_rate"] - 0.6667) < 0.001


# ===========================================================================
# TestCoverageEndpoint
# ===========================================================================

class TestCoverageEndpoint:
    def test_endpoint_returns_200(self, client):
        strat = _new_strategy(client, name=f"M39-ep-200-{uuid.uuid4().hex[:6]}")
        snap = _create_universe_snapshot(client, strat["id"])
        resp = client.get(f"/api/universe-snapshots/{snap['id']}/coverage-analysis")
        assert resp.status_code == 200, resp.text

    def test_response_fields(self, client):
        strat = _new_strategy(client, name=f"M39-ep-fields-{uuid.uuid4().hex[:6]}")
        snap = _create_universe_snapshot(client, strat["id"])
        resp = client.get(f"/api/universe-snapshots/{snap['id']}/coverage-analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert "coverage_analysis" in data
        assert "symbol_quality" in data
        assert "universe_delta" in data
        assert "quality_summary" in data

    def test_unknown_snapshot_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/universe-snapshots/{fake_id}/coverage-analysis")
        assert resp.status_code == 404

    def test_snapshot_creation_stores_coverage(self, client):
        strat = _new_strategy(client, name=f"M39-ep-stored-{uuid.uuid4().hex[:6]}")
        snap = _create_universe_snapshot(client, strat["id"], symbols=["AAPL", "MSFT"])
        # The POST endpoint stores coverage JSON fields. Verify via the endpoint.
        resp = client.get(f"/api/universe-snapshots/{snap['id']}/coverage-analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol_count"] == 2
        assert data["coverage_analysis"]["symbol_count"] == 2

    def test_drilldown_computes_if_null(self, client, db):
        strat = _new_strategy(client, name=f"M39-ep-null-{uuid.uuid4().hex[:6]}")
        snap_resp = _create_universe_snapshot(client, strat["id"], symbols=["AAPL", "TSLA"])
        snap_id = uuid.UUID(snap_resp["id"])
        from app.models.universe_snapshot import UniverseSnapshot
        snap_obj = db.query(UniverseSnapshot).filter(
            UniverseSnapshot.id == snap_id
        ).first()
        try:
            # Null out stored fields to simulate missing data.
            snap_obj.coverage_analysis_json = None
            snap_obj.symbol_quality_json = None
            snap_obj.universe_quality_summary_json = None
            db.commit()

            resp = client.get(f"/api/universe-snapshots/{snap_resp['id']}/coverage-analysis")
            assert resp.status_code == 200
            data = resp.json()
            assert data["symbol_quality"] is not None
            assert len(data["symbol_quality"]) == 2
        finally:
            db.rollback()

    def test_run_linkage_linked(self, client):
        strat = _new_strategy(client, name=f"M39-ep-linkage-{uuid.uuid4().hex[:6]}")
        snap = _create_universe_snapshot(client, strat["id"], symbols=["AAPL", "GOOG"])
        _create_run(client, strat["id"], universe_snapshot_id=snap["id"])

        resp = client.get(f"/api/universe-snapshots/{snap['id']}/coverage-analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["coverage_analysis"]["linkage_status"] == "linked"
        assert data["coverage_analysis"]["is_used_by_runs"] is True
        assert data["coverage_analysis"]["linked_run_count"] >= 1
