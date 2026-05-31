"""M16 universe snapshot tests.

Tests cover:
- POST /api/strategies/{id}/universe-snapshots: 201, symbol normalization, hash,
  version link, missing strategy → 404, version belongs to wrong strategy → 404,
  empty symbols → 422
- GET  /api/strategies/{id}/universe-snapshots: list newest-first, filter by version_id
- GET  /api/strategies/{id}/universe-snapshots/compare: diffs, is_same_universe,
  overlap/jaccard, 404 cases
- GET  /api/universe-snapshots/{snapshot_id}: full detail with symbols_json, 404
- GET  /api/strategies/{id}: universe_snapshots included, per-version universe_snapshot_count
- POST /api/strategies/{id}/runs: universe_snapshot_id accepted, validated for ownership
- GET  /api/strategies/{id}/runs: universe_snapshot summary embedded
- services.universe_snapshots: normalize_symbols, compute_universe_hash,
  compare_universe_snapshots unit tests
"""

from __future__ import annotations

import uuid

import pytest

from app.services.universe_snapshots import (
    compare_universe_snapshots,
    compute_universe_hash,
    normalize_symbols,
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
        json={"project_id": project_id, "name": name or f"M16 Strategy {uuid.uuid4().hex[:6]}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_version(client, strategy_id: str, label: str = "v1.0", **extra) -> dict:
    payload = {"version_label": label, **extra}
    resp = client.post(f"/api/strategies/{strategy_id}/versions", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_universe_snapshot(
    client,
    strategy_id: str,
    label: str = "uni-snap-1",
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


def _create_run(client, strategy_id: str, run_name: str = "test-run", **extra) -> dict:
    payload = {
        "run_name": run_name,
        "run_type": "backtest",
        **extra,
    }
    resp = client.post(f"/api/strategies/{strategy_id}/runs", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Unit tests: normalize_symbols
# ---------------------------------------------------------------------------

class TestNormalizeSymbols:
    def test_returns_sorted_uppercase(self):
        result = normalize_symbols(["msft", "aapl", "goog"])
        assert result == ["AAPL", "GOOG", "MSFT"]

    def test_deduplication(self):
        result = normalize_symbols(["AAPL", "aapl", "AAPL"])
        assert result == ["AAPL"]

    def test_strips_whitespace(self):
        result = normalize_symbols(["  AAPL  ", " msft "])
        assert result == ["AAPL", "MSFT"]

    def test_drops_empty_strings(self):
        result = normalize_symbols(["AAPL", "", "  ", "MSFT"])
        assert result == ["AAPL", "MSFT"]

    def test_empty_list(self):
        assert normalize_symbols([]) == []

    def test_single_symbol(self):
        assert normalize_symbols(["tsla"]) == ["TSLA"]

    def test_order_independence(self):
        a = normalize_symbols(["Z", "A", "M"])
        b = normalize_symbols(["M", "Z", "A"])
        assert a == b == ["A", "M", "Z"]


# ---------------------------------------------------------------------------
# Unit tests: compute_universe_hash
# ---------------------------------------------------------------------------

class TestComputeUniverseHash:
    def test_returns_64_char_hex(self):
        h = compute_universe_hash(["AAPL", "MSFT"])
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        h1 = compute_universe_hash(["AAPL", "MSFT"])
        h2 = compute_universe_hash(["AAPL", "MSFT"])
        assert h1 == h2

    def test_different_symbols_different_hash(self):
        h1 = compute_universe_hash(["AAPL", "MSFT"])
        h2 = compute_universe_hash(["AAPL", "GOOG"])
        assert h1 != h2

    def test_metadata_affects_hash(self):
        h1 = compute_universe_hash(["AAPL"], None)
        h2 = compute_universe_hash(["AAPL"], {"region": "US"})
        assert h1 != h2

    def test_metadata_sort_keys_deterministic(self):
        h1 = compute_universe_hash(["AAPL"], {"b": 2, "a": 1})
        h2 = compute_universe_hash(["AAPL"], {"a": 1, "b": 2})
        assert h1 == h2


# ---------------------------------------------------------------------------
# Unit tests: compare_universe_snapshots
# ---------------------------------------------------------------------------

class TestCompareUniverseSnapshots:
    def _make_hash(self, symbols):
        return compute_universe_hash(normalize_symbols(symbols))

    def test_identical_universes(self):
        syms = ["AAPL", "MSFT", "GOOG"]
        h = self._make_hash(syms)
        result = compare_universe_snapshots(
            "a", "b", "snap-a", "snap-b", syms, syms, h, h
        )
        assert result.is_same_universe is True
        assert result.added_count == 0
        assert result.removed_count == 0
        assert result.common_symbols_count == 3
        assert result.overlap_ratio == 1.0
        assert result.jaccard_similarity == 1.0

    def test_different_universes(self):
        syms_a = ["AAPL", "MSFT"]
        syms_b = ["AAPL", "GOOG"]
        ha = self._make_hash(syms_a)
        hb = self._make_hash(syms_b)
        result = compare_universe_snapshots(
            "a", "b", "snap-a", "snap-b", syms_a, syms_b, ha, hb
        )
        assert result.is_same_universe is False
        assert result.added_count == 1          # GOOG added
        assert result.removed_count == 1        # MSFT removed
        assert result.common_symbols_count == 1  # AAPL
        assert "GOOG" in result.added_symbols
        assert "MSFT" in result.removed_symbols

    def test_b_is_superset(self):
        syms_a = ["AAPL"]
        syms_b = ["AAPL", "MSFT", "GOOG"]
        ha = self._make_hash(syms_a)
        hb = self._make_hash(syms_b)
        result = compare_universe_snapshots(
            "a", "b", "snap-a", "snap-b", syms_a, syms_b, ha, hb
        )
        assert result.symbol_count_delta == 2
        assert result.added_count == 2
        assert result.removed_count == 0

    def test_empty_universes(self):
        result = compare_universe_snapshots(
            "a", "b", "snap-a", "snap-b", [], [], "x" * 64, "y" * 64
        )
        assert result.is_same_universe is True
        assert result.overlap_ratio == 1.0
        assert result.jaccard_similarity == 1.0

    def test_overlap_ratio_formula(self):
        """overlap = |A ∩ B| / max(|A|, |B|)"""
        syms_a = ["A", "B", "C", "D"]   # |A|=4
        syms_b = ["A", "B", "C", "E"]   # |B|=4
        ha = self._make_hash(syms_a)
        hb = self._make_hash(syms_b)
        result = compare_universe_snapshots(
            "a", "b", "snap-a", "snap-b", syms_a, syms_b, ha, hb
        )
        # |A ∩ B| = 3 (A, B, C), max = 4 → 3/4 = 0.75
        assert result.overlap_ratio == 0.75
        # |A ∪ B| = 5 (A, B, C, D, E) → 3/5 = 0.6
        assert result.jaccard_similarity == 0.6

    def test_highlighted_changes_not_empty(self):
        syms_a = ["AAPL"]
        syms_b = ["AAPL", "GOOG"]
        result = compare_universe_snapshots(
            "a", "b", "snap-a", "snap-b", syms_a, syms_b,
            self._make_hash(syms_a), self._make_hash(syms_b),
        )
        assert len(result.highlighted_changes) > 0

    def test_explanation_is_hedged(self):
        syms_a = ["AAPL"]
        syms_b = ["AAPL", "GOOG"]
        result = compare_universe_snapshots(
            "a", "b", "snap-a", "snap-b", syms_a, syms_b,
            self._make_hash(syms_a), self._make_hash(syms_b),
        )
        exp = result.deterministic_explanation.lower()
        # Must not contain causal language
        assert "because" not in exp
        assert "caused" not in exp
        # Should contain hedged language
        assert any(word in exp for word in ["observed", "noted", "may"])


# ---------------------------------------------------------------------------
# POST /api/strategies/{id}/universe-snapshots
# ---------------------------------------------------------------------------

class TestCreateUniverseSnapshot:
    def test_creates_snapshot_201(self, client):
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/universe-snapshots",
            json={"label": "uni-v1", "symbols": ["AAPL", "MSFT", "GOOG"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["label"] == "uni-v1"
        assert data["symbol_count"] == 3
        assert len(data["universe_hash"]) == 64
        assert data["strategy_id"] == s["id"]

    def test_symbols_normalized(self, client):
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/universe-snapshots",
            json={"label": "norm-test", "symbols": ["msft", "AAPL", "  goog  ", "aapl"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        # aapl deduped, msft/goog uppercased, goog whitespace stripped
        assert data["symbol_count"] == 3

    def test_hash_is_deterministic(self, client):
        s = _new_strategy(client)
        syms = ["Z", "A", "M"]
        r1 = client.post(
            f"/api/strategies/{s['id']}/universe-snapshots",
            json={"label": "hash-test-1", "symbols": syms},
        )
        r2 = client.post(
            f"/api/strategies/{s['id']}/universe-snapshots",
            json={"label": "hash-test-2", "symbols": list(reversed(syms))},
        )
        assert r1.json()["universe_hash"] == r2.json()["universe_hash"]

    def test_with_version_link(self, client):
        s = _new_strategy(client)
        v = _create_version(client, s["id"], "v1.0")
        resp = client.post(
            f"/api/strategies/{s['id']}/universe-snapshots",
            json={
                "label": "versioned-uni",
                "symbols": ["AAPL"],
                "strategy_version_id": v["id"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["strategy_version_id"] == v["id"]

    def test_version_wrong_strategy_returns_404(self, client):
        s1 = _new_strategy(client)
        s2 = _new_strategy(client)
        v = _create_version(client, s1["id"], "v1.0")
        resp = client.post(
            f"/api/strategies/{s2['id']}/universe-snapshots",
            json={
                "label": "bad-version",
                "symbols": ["AAPL"],
                "strategy_version_id": v["id"],
            },
        )
        assert resp.status_code == 404

    def test_missing_strategy_returns_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/strategies/{fake_id}/universe-snapshots",
            json={"label": "x", "symbols": ["AAPL"]},
        )
        assert resp.status_code == 404

    def test_empty_symbols_returns_422(self, client):
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/universe-snapshots",
            json={"label": "empty-syms", "symbols": []},
        )
        assert resp.status_code == 422

    def test_all_whitespace_symbols_returns_422(self, client):
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/universe-snapshots",
            json={"label": "ws-only", "symbols": ["  ", "", "   "]},
        )
        assert resp.status_code == 422

    def test_with_metadata_json(self, client):
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/universe-snapshots",
            json={
                "label": "meta-test",
                "symbols": ["AAPL"],
                "metadata_json": {"exchange": "NASDAQ", "date": "2026-01-01"},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["metadata_json"]["exchange"] == "NASDAQ"

    def test_with_source_filename(self, client):
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/universe-snapshots",
            json={
                "label": "file-source",
                "symbols": ["AAPL"],
                "source_type": "csv_import",
                "source_filename": "universe_2026.csv",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["source_filename"] == "universe_2026.csv"
        assert data["source_type"] == "csv_import"

    def test_response_has_no_symbols_json(self, client):
        """List/Read response must not include symbols_json blob."""
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/universe-snapshots",
            json={"label": "no-blob", "symbols": ["AAPL", "MSFT"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "symbols_json" not in data

    def test_timeline_event_created(self, client):
        s = _new_strategy(client)
        _create_universe_snapshot(client, s["id"], label="timeline-uni")
        resp = client.get(f"/api/strategies/{s['id']}/timeline")
        assert resp.status_code == 200
        events = resp.json()["items"]
        uni_events = [e for e in events if e["event_type"] == "universe_snapshot_logged"]
        assert len(uni_events) >= 1
        assert "timeline-uni" in uni_events[0]["title"]


# ---------------------------------------------------------------------------
# GET /api/strategies/{id}/universe-snapshots
# ---------------------------------------------------------------------------

class TestListUniverseSnapshots:
    def test_returns_empty_list(self, client):
        s = _new_strategy(client)
        resp = client.get(f"/api/strategies/{s['id']}/universe-snapshots")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_snapshots(self, client):
        s = _new_strategy(client)
        _create_universe_snapshot(client, s["id"], "uni-a")
        _create_universe_snapshot(client, s["id"], "uni-b")
        resp = client.get(f"/api/strategies/{s['id']}/universe-snapshots")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 2

    def test_newest_first(self, client):
        s = _new_strategy(client)
        _create_universe_snapshot(client, s["id"], "older")
        _create_universe_snapshot(client, s["id"], "newer")
        resp = client.get(f"/api/strategies/{s['id']}/universe-snapshots")
        labels = [item["label"] for item in resp.json()]
        assert labels[0] == "newer"

    def test_filter_by_version_id(self, client):
        s = _new_strategy(client)
        v = _create_version(client, s["id"], "v1.0")
        _create_universe_snapshot(client, s["id"], "versioned", strategy_version_id=v["id"])
        _create_universe_snapshot(client, s["id"], "unversioned")
        resp = client.get(
            f"/api/strategies/{s['id']}/universe-snapshots",
            params={"version_id": v["id"]},
        )
        items = resp.json()
        assert len(items) == 1
        assert items[0]["label"] == "versioned"

    def test_missing_strategy_returns_404(self, client):
        resp = client.get(f"/api/strategies/{uuid.uuid4()}/universe-snapshots")
        assert resp.status_code == 404

    def test_no_symbols_json_in_list_response(self, client):
        s = _new_strategy(client)
        _create_universe_snapshot(client, s["id"], "list-check")
        resp = client.get(f"/api/strategies/{s['id']}/universe-snapshots")
        for item in resp.json():
            assert "symbols_json" not in item


# ---------------------------------------------------------------------------
# GET /api/universe-snapshots/{snapshot_id}
# ---------------------------------------------------------------------------

class TestGetUniverseSnapshot:
    def test_returns_detail_with_symbols(self, client):
        s = _new_strategy(client)
        us = _create_universe_snapshot(client, s["id"], symbols=["AAPL", "MSFT", "GOOG"])
        resp = client.get(f"/api/universe-snapshots/{us['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert "symbols_json" in data
        assert set(data["symbols_json"]) == {"AAPL", "MSFT", "GOOG"}

    def test_symbols_are_normalized(self, client):
        s = _new_strategy(client)
        us = _create_universe_snapshot(client, s["id"], symbols=["msft", "aapl", "GOOG"])
        resp = client.get(f"/api/universe-snapshots/{us['id']}")
        data = resp.json()
        assert data["symbols_json"] == sorted(data["symbols_json"])  # sorted
        for sym in data["symbols_json"]:
            assert sym == sym.upper()  # uppercased

    def test_missing_snapshot_returns_404(self, client):
        resp = client.get(f"/api/universe-snapshots/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_includes_all_read_fields(self, client):
        s = _new_strategy(client)
        us = _create_universe_snapshot(client, s["id"])
        resp = client.get(f"/api/universe-snapshots/{us['id']}")
        data = resp.json()
        for field in [
            "id", "strategy_id", "strategy_version_id", "label",
            "source_type", "symbol_count", "universe_hash",
            "metadata_json", "created_at", "updated_at", "symbols_json",
        ]:
            assert field in data, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# GET /api/strategies/{id}/universe-snapshots/compare
# ---------------------------------------------------------------------------

class TestCompareUniverseSnapshotsRoute:
    def test_compare_identical_snapshots(self, client):
        s = _new_strategy(client)
        syms = ["AAPL", "MSFT", "GOOG"]
        us_a = _create_universe_snapshot(client, s["id"], "base", symbols=syms)
        us_b = _create_universe_snapshot(client, s["id"], "same", symbols=syms)
        resp = client.get(
            f"/api/strategies/{s['id']}/universe-snapshots/compare",
            params={"snapshot_a_id": us_a["id"], "snapshot_b_id": us_b["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_same_universe"] is True
        assert data["added_count"] == 0
        assert data["removed_count"] == 0
        assert data["common_symbols_count"] == 3
        assert data["overlap_ratio"] == 1.0
        assert data["jaccard_similarity"] == 1.0

    def test_compare_different_snapshots(self, client):
        s = _new_strategy(client)
        us_a = _create_universe_snapshot(client, s["id"], "v1", symbols=["AAPL", "MSFT"])
        us_b = _create_universe_snapshot(client, s["id"], "v2", symbols=["AAPL", "GOOG"])
        resp = client.get(
            f"/api/strategies/{s['id']}/universe-snapshots/compare",
            params={"snapshot_a_id": us_a["id"], "snapshot_b_id": us_b["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_same_universe"] is False
        assert data["added_count"] == 1
        assert data["removed_count"] == 1
        assert "GOOG" in data["added_symbols"]
        assert "MSFT" in data["removed_symbols"]
        assert len(data["highlighted_changes"]) > 0
        assert data["deterministic_explanation"] != ""

    def test_compare_response_fields(self, client):
        s = _new_strategy(client)
        us_a = _create_universe_snapshot(client, s["id"], "a", symbols=["AAPL"])
        us_b = _create_universe_snapshot(client, s["id"], "b", symbols=["MSFT"])
        resp = client.get(
            f"/api/strategies/{s['id']}/universe-snapshots/compare",
            params={"snapshot_a_id": us_a["id"], "snapshot_b_id": us_b["id"]},
        )
        data = resp.json()
        for field in [
            "snapshot_a_id", "snapshot_b_id",
            "snapshot_a_label", "snapshot_b_label",
            "snapshot_a_symbol_count", "snapshot_b_symbol_count",
            "is_same_universe", "added_count", "removed_count",
            "common_symbols_count", "symbol_count_delta",
            "overlap_ratio", "jaccard_similarity",
            "added_symbols", "removed_symbols",
            "highlighted_changes", "deterministic_explanation",
        ]:
            assert field in data, f"Missing field: {field}"

    def test_snapshot_a_not_found(self, client):
        s = _new_strategy(client)
        us_b = _create_universe_snapshot(client, s["id"], "b")
        resp = client.get(
            f"/api/strategies/{s['id']}/universe-snapshots/compare",
            params={"snapshot_a_id": str(uuid.uuid4()), "snapshot_b_id": us_b["id"]},
        )
        assert resp.status_code == 404

    def test_snapshot_b_not_found(self, client):
        s = _new_strategy(client)
        us_a = _create_universe_snapshot(client, s["id"], "a")
        resp = client.get(
            f"/api/strategies/{s['id']}/universe-snapshots/compare",
            params={"snapshot_a_id": us_a["id"], "snapshot_b_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_snapshot_wrong_strategy_returns_404(self, client):
        s1 = _new_strategy(client)
        s2 = _new_strategy(client)
        us_a = _create_universe_snapshot(client, s1["id"], "a")
        us_b = _create_universe_snapshot(client, s2["id"], "b")
        # A belongs to s1, B belongs to s2 — compare endpoint on s1 should 404 B
        resp = client.get(
            f"/api/strategies/{s1['id']}/universe-snapshots/compare",
            params={"snapshot_a_id": us_a["id"], "snapshot_b_id": us_b["id"]},
        )
        assert resp.status_code == 404

    def test_missing_strategy_returns_404(self, client):
        resp = client.get(
            f"/api/strategies/{uuid.uuid4()}/universe-snapshots/compare",
            params={"snapshot_a_id": str(uuid.uuid4()), "snapshot_b_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_symbol_count_delta(self, client):
        s = _new_strategy(client)
        us_a = _create_universe_snapshot(client, s["id"], "small", symbols=["AAPL", "MSFT"])
        us_b = _create_universe_snapshot(client, s["id"], "large", symbols=["AAPL", "MSFT", "GOOG", "TSLA"])
        resp = client.get(
            f"/api/strategies/{s['id']}/universe-snapshots/compare",
            params={"snapshot_a_id": us_a["id"], "snapshot_b_id": us_b["id"]},
        )
        data = resp.json()
        assert data["symbol_count_delta"] == 2

    def test_missing_query_params_returns_422(self, client):
        s = _new_strategy(client)
        resp = client.get(f"/api/strategies/{s['id']}/universe-snapshots/compare")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Run linkage: POST /api/strategies/{id}/runs with universe_snapshot_id
# ---------------------------------------------------------------------------

class TestRunUniverseSnapshotLinkage:
    def test_run_with_universe_snapshot(self, client):
        s = _new_strategy(client)
        us = _create_universe_snapshot(client, s["id"], symbols=["AAPL", "MSFT"])
        resp = client.post(
            f"/api/strategies/{s['id']}/runs",
            json={
                "run_name": "run-with-uni",
                "run_type": "backtest",
                "universe_snapshot_id": us["id"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["universe_snapshot_id"] == us["id"]
        assert data["universe_snapshot"] is not None
        assert data["universe_snapshot"]["label"] == us["label"]
        assert data["universe_snapshot"]["symbol_count"] == 2

    def test_run_without_universe_snapshot(self, client):
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/runs",
            json={"run_name": "run-no-uni", "run_type": "backtest"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["universe_snapshot_id"] is None
        assert data["universe_snapshot"] is None

    def test_universe_snapshot_wrong_strategy_returns_400(self, client):
        s1 = _new_strategy(client)
        s2 = _new_strategy(client)
        us = _create_universe_snapshot(client, s1["id"])
        resp = client.post(
            f"/api/strategies/{s2['id']}/runs",
            json={
                "run_name": "bad-run",
                "run_type": "backtest",
                "universe_snapshot_id": us["id"],
            },
        )
        assert resp.status_code == 400

    def test_nonexistent_universe_snapshot_returns_404(self, client):
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/runs",
            json={
                "run_name": "ghost-run",
                "run_type": "backtest",
                "universe_snapshot_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 404

    def test_universe_summary_fields(self, client):
        s = _new_strategy(client)
        us = _create_universe_snapshot(client, s["id"], symbols=["AAPL", "MSFT", "GOOG"])
        resp = client.post(
            f"/api/strategies/{s['id']}/runs",
            json={
                "run_name": "summary-check",
                "run_type": "backtest",
                "universe_snapshot_id": us["id"],
            },
        )
        assert resp.status_code == 201
        uni = resp.json()["universe_snapshot"]
        for field in ["id", "label", "symbol_count", "universe_hash", "strategy_version_id", "created_at"]:
            assert field in uni, f"Missing field in universe_snapshot summary: {field}"
        assert uni["symbol_count"] == 3


# ---------------------------------------------------------------------------
# GET /api/strategies/{id}/runs: universe_snapshot embedded
# ---------------------------------------------------------------------------

class TestListRunsUniverseEvidence:
    def test_universe_snapshot_embedded_in_list(self, client):
        s = _new_strategy(client)
        us = _create_universe_snapshot(client, s["id"], symbols=["AAPL"])
        _create_run(client, s["id"], universe_snapshot_id=us["id"])
        resp = client.get(f"/api/strategies/{s['id']}/runs")
        assert resp.status_code == 200
        runs = resp.json()
        linked = [r for r in runs if r.get("universe_snapshot_id") == us["id"]]
        assert len(linked) == 1
        assert linked[0]["universe_snapshot"] is not None
        assert linked[0]["universe_snapshot"]["id"] == us["id"]

    def test_runs_without_universe_snapshot_have_null(self, client):
        s = _new_strategy(client)
        _create_run(client, s["id"])
        resp = client.get(f"/api/strategies/{s['id']}/runs")
        runs = resp.json()
        no_uni = [r for r in runs if r.get("universe_snapshot_id") is None]
        for r in no_uni:
            assert r["universe_snapshot"] is None


# ---------------------------------------------------------------------------
# GET /api/strategies/{id}: strategy detail includes universe snapshots
# ---------------------------------------------------------------------------

class TestStrategyDetailUniverseSnapshots:
    def test_universe_snapshots_in_detail(self, client):
        s = _new_strategy(client)
        _create_universe_snapshot(client, s["id"], "detail-uni-a")
        _create_universe_snapshot(client, s["id"], "detail-uni-b")
        resp = client.get(f"/api/strategies/{s['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert "universe_snapshots" in data
        labels = [u["label"] for u in data["universe_snapshots"]]
        assert "detail-uni-a" in labels
        assert "detail-uni-b" in labels

    def test_version_universe_snapshot_count(self, client):
        s = _new_strategy(client)
        v = _create_version(client, s["id"], "v2.0")
        _create_universe_snapshot(client, s["id"], "u1", strategy_version_id=v["id"])
        _create_universe_snapshot(client, s["id"], "u2", strategy_version_id=v["id"])
        resp = client.get(f"/api/strategies/{s['id']}")
        data = resp.json()
        matching = [ver for ver in data["versions"] if ver["id"] == v["id"]]
        assert len(matching) == 1
        assert matching[0]["universe_snapshot_count"] == 2

    def test_no_symbols_json_in_detail_universe_snapshots(self, client):
        s = _new_strategy(client)
        _create_universe_snapshot(client, s["id"], "no-blob-detail")
        resp = client.get(f"/api/strategies/{s['id']}")
        for us in resp.json()["universe_snapshots"]:
            assert "symbols_json" not in us


# ---------------------------------------------------------------------------
# GET /api/strategies/{id}/versions: universe_snapshot_count
# ---------------------------------------------------------------------------

class TestVersionsUniverseSnapshotCount:
    def test_universe_snapshot_count_in_version_list(self, client):
        s = _new_strategy(client)
        v = _create_version(client, s["id"], "v3.0")
        _create_universe_snapshot(client, s["id"], "v3-uni", strategy_version_id=v["id"])
        resp = client.get(f"/api/strategies/{s['id']}/versions")
        assert resp.status_code == 200
        matching = [ver for ver in resp.json() if ver["id"] == v["id"]]
        assert matching[0]["universe_snapshot_count"] == 1

    def test_new_version_has_zero_count(self, client):
        s = _new_strategy(client)
        v = _create_version(client, s["id"], "v4.0")
        resp = client.get(f"/api/strategies/{s['id']}/versions")
        matching = [ver for ver in resp.json() if ver["id"] == v["id"]]
        assert matching[0]["universe_snapshot_count"] == 0
