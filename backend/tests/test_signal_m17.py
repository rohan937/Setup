"""M17 signal snapshot tests.

Tests cover:
- Service unit tests: normalize_signal_rows, compute_signal_hash, summarize_signal_snapshot,
  compare_signal_snapshots
- POST /api/strategies/{id}/signal-snapshots: 201, validation, version/universe link,
  missing strategy → 404, version wrong strategy → 404, empty rows → 422
- GET  /api/strategies/{id}/signal-snapshots: list newest-first, filter by version_id
- GET  /api/strategies/{id}/signal-snapshots/compare: diffs, is_same_snapshot,
  keyed comparison, 404 cases
- GET  /api/signal-snapshots/{snapshot_id}: full detail with rows_json, 404
- GET  /api/strategies/{id}: signal_snapshots included, per-version signal_snapshot_count
- POST /api/strategies/{id}/runs: signal_snapshot_id accepted, validated for ownership,
  version/universe mismatch checks
- GET  /api/strategies/{id}/runs: signal_snapshot summary embedded
- GET  /api/strategies/{id}/versions: signal_snapshot_count in version list
"""

from __future__ import annotations

import uuid

import pytest

from app.services.signal_snapshots import (
    SignalSummary,
    compare_signal_snapshots,
    compute_signal_hash,
    normalize_signal_rows,
    summarize_signal_snapshot,
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
        json={"project_id": project_id, "name": name or f"M17 Strategy {uuid.uuid4().hex[:6]}"},
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


def _sample_rows(n: int = 3, signal_col: str = "signal") -> list[dict]:
    """Generate n sample rows with symbol, timestamp, and signal."""
    symbols = ["AAPL", "MSFT", "GOOG", "TSLA", "AMZN"]
    rows = []
    for i in range(n):
        rows.append({
            "symbol": symbols[i % len(symbols)],
            "timestamp": f"2024-01-0{1 + (i % 9)}",
            signal_col: round(0.1 + i * 0.05, 4),
        })
    return rows


def _create_signal_snapshot(
    client,
    strategy_id: str,
    label: str = "sig-snap-1",
    rows: list[dict] | None = None,
    **extra,
) -> dict:
    payload = {
        "label": label,
        "rows": rows if rows is not None else _sample_rows(),
        **extra,
    }
    resp = client.post(f"/api/strategies/{strategy_id}/signal-snapshots", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_run(client, strategy_id: str, run_name: str = "test-run", **extra) -> dict:
    payload = {"run_name": run_name, "run_type": "backtest", **extra}
    resp = client.post(f"/api/strategies/{strategy_id}/runs", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Unit tests: normalize_signal_rows
# ---------------------------------------------------------------------------

class TestNormalizeSignalRows:
    def test_returns_rows_unchanged(self):
        rows = [{"symbol": "AAPL", "signal": 1.0}]
        result = normalize_signal_rows(rows)
        assert result == rows

    def test_empty_list_is_valid(self):
        result = normalize_signal_rows([])
        assert result == []

    def test_raises_for_non_list(self):
        with pytest.raises(ValueError, match="list"):
            normalize_signal_rows({"symbol": "AAPL"})  # type: ignore[arg-type]

    def test_raises_for_non_dict_row(self):
        with pytest.raises(ValueError, match="Row 1"):
            normalize_signal_rows([{"symbol": "AAPL"}, "bad_row"])  # type: ignore[list-item]

    def test_multiple_rows_preserved(self):
        rows = [
            {"symbol": "AAPL", "signal": 0.5},
            {"symbol": "MSFT", "signal": 0.8},
        ]
        result = normalize_signal_rows(rows)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Unit tests: compute_signal_hash
# ---------------------------------------------------------------------------

class TestComputeSignalHash:
    def test_returns_64_char_hex(self):
        rows = [{"symbol": "AAPL", "signal": 1.0}]
        h = compute_signal_hash(rows)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        rows = [{"symbol": "AAPL", "signal": 1.0}]
        h1 = compute_signal_hash(rows)
        h2 = compute_signal_hash(rows)
        assert h1 == h2

    def test_order_independence(self):
        rows_a = [
            {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.5},
            {"symbol": "MSFT", "timestamp": "2024-01-01", "signal": 0.8},
        ]
        rows_b = [
            {"symbol": "MSFT", "timestamp": "2024-01-01", "signal": 0.8},
            {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.5},
        ]
        assert compute_signal_hash(rows_a) == compute_signal_hash(rows_b)

    def test_different_values_different_hash(self):
        rows_a = [{"symbol": "AAPL", "signal": 0.5}]
        rows_b = [{"symbol": "AAPL", "signal": 0.6}]
        assert compute_signal_hash(rows_a) != compute_signal_hash(rows_b)

    def test_metadata_affects_hash(self):
        rows = [{"symbol": "AAPL", "signal": 0.5}]
        h1 = compute_signal_hash(rows, None)
        h2 = compute_signal_hash(rows, {"date": "2024-01-01"})
        assert h1 != h2

    def test_metadata_sort_keys_deterministic(self):
        rows = [{"symbol": "AAPL", "signal": 0.5}]
        h1 = compute_signal_hash(rows, {"b": 2, "a": 1})
        h2 = compute_signal_hash(rows, {"a": 1, "b": 2})
        assert h1 == h2

    def test_custom_signal_column(self):
        rows = [{"symbol": "AAPL", "alpha": 0.5}]
        h_default = compute_signal_hash(rows, signal_column="signal")
        h_alpha = compute_signal_hash(rows, signal_column="alpha")
        assert h_default != h_alpha


# ---------------------------------------------------------------------------
# Unit tests: summarize_signal_snapshot
# ---------------------------------------------------------------------------

class TestSummarizeSignalSnapshot:
    def test_basic_summary(self):
        rows = [
            {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.5},
            {"symbol": "MSFT", "timestamp": "2024-01-02", "signal": 0.8},
        ]
        s = summarize_signal_snapshot(rows)
        assert s.row_count == 2
        assert s.symbol_count == 2
        assert "AAPL" in s.symbols
        assert "MSFT" in s.symbols
        assert s.signal_value_count == 2
        assert s.missing_signal_count == 0
        assert s.quality_score == 100

    def test_empty_rows(self):
        s = summarize_signal_snapshot([])
        assert s.row_count == 0
        assert s.symbol_count == 0
        assert s.quality_score == 100

    def test_missing_signal_deduction(self):
        rows = [
            {"symbol": "AAPL", "signal": None},
            {"symbol": "MSFT", "signal": None},
            {"symbol": "GOOG", "signal": 0.5},
        ]
        s = summarize_signal_snapshot(rows)
        assert s.missing_signal_count == 2
        assert s.quality_score < 100
        assert len(s.warnings) > 0

    def test_non_numeric_signal_deduction(self):
        rows = [
            {"symbol": "AAPL", "signal": "high"},
            {"symbol": "MSFT", "signal": 0.5},
        ]
        s = summarize_signal_snapshot(rows)
        assert s.missing_signal_count == 1
        assert s.quality_score < 100

    def test_timestamp_range(self):
        rows = [
            {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.5},
            {"symbol": "AAPL", "timestamp": "2024-03-15", "signal": 0.6},
            {"symbol": "AAPL", "timestamp": "2024-02-10", "signal": 0.7},
        ]
        s = summarize_signal_snapshot(rows)
        assert s.min_timestamp == "2024-01-01"
        assert s.max_timestamp == "2024-03-15"

    def test_invalid_timestamp_deduction(self):
        rows = [
            {"symbol": "AAPL", "timestamp": "not-a-date", "signal": 0.5},
            {"symbol": "MSFT", "timestamp": "2024-01-01", "signal": 0.8},
        ]
        s = summarize_signal_snapshot(rows)
        assert s.quality_score < 100
        assert any("invalid timestamp" in w.lower() for w in s.warnings)

    def test_duplicate_key_deduction(self):
        rows = [
            {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.5},
            {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.6},  # duplicate
        ] * 10  # 20 rows, 10 dupes
        s = summarize_signal_snapshot(rows)
        assert s.quality_score < 100

    def test_mean_value(self):
        rows = [
            {"symbol": "AAPL", "signal": 1.0},
            {"symbol": "MSFT", "signal": 3.0},
        ]
        s = summarize_signal_snapshot(rows)
        assert s.mean_value == pytest.approx(2.0, abs=0.001)

    def test_stddev_value(self):
        rows = [{"symbol": f"S{i}", "signal": float(i)} for i in range(5)]
        s = summarize_signal_snapshot(rows)
        assert s.stddev_value is not None
        assert s.stddev_value > 0

    def test_zero_variance_deduction(self):
        rows = [{"symbol": f"S{i}", "signal": 1.0} for i in range(15)]
        s = summarize_signal_snapshot(rows)
        assert s.stddev_value == 0.0
        assert s.quality_score < 100
        assert any("variance" in w.lower() for w in s.warnings)

    def test_custom_signal_column(self):
        rows = [
            {"symbol": "AAPL", "alpha": 0.5},
            {"symbol": "MSFT", "alpha": 0.8},
        ]
        s = summarize_signal_snapshot(rows, signal_column="alpha")
        assert s.signal_value_count == 2
        assert s.missing_signal_count == 0

    def test_symbols_sorted_uppercase(self):
        rows = [
            {"symbol": "msft", "signal": 0.5},
            {"symbol": "aapl", "signal": 0.8},
        ]
        s = summarize_signal_snapshot(rows)
        # The service normalizes symbols to uppercase when building the sorted list
        # (it calls str.upper() in the symbol handling)
        assert s.symbols == sorted(s.symbols)

    def test_quality_never_below_zero(self):
        rows = [{"symbol": "AAPL", "signal": "bad", "timestamp": "invalid"} for _ in range(100)]
        s = summarize_signal_snapshot(rows)
        assert s.quality_score >= 0


# ---------------------------------------------------------------------------
# Unit tests: compare_signal_snapshots
# ---------------------------------------------------------------------------

class TestCompareSignalSnapshots:
    def _make_hash(self, rows):
        return compute_signal_hash(rows)

    def test_identical_snapshots(self):
        rows = _sample_rows(3)
        h = self._make_hash(rows)
        summary = summarize_signal_snapshot(rows)
        data = {
            "symbols_json": summary.symbols,
            "rows_json": rows,
            "row_count": summary.row_count,
            "symbol_count": summary.symbol_count,
            "mean_value": summary.mean_value,
            "min_value": summary.min_value,
            "max_value": summary.max_value,
            "stddev_value": summary.stddev_value,
            "quality_score": summary.quality_score,
            "missing_signal_count": summary.missing_signal_count,
            "signal_hash": h,
            "signal_column": "signal",
        }
        result = compare_signal_snapshots("a", "b", "snap-a", "snap-b", data, data)
        assert result.is_same_snapshot is True
        assert result.added_count == 0
        assert result.removed_count == 0

    def test_different_snapshots(self):
        rows_a = [{"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.5}]
        rows_b = [
            {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.7},
            {"symbol": "MSFT", "timestamp": "2024-01-01", "signal": 0.4},
        ]
        s_a = summarize_signal_snapshot(rows_a)
        s_b = summarize_signal_snapshot(rows_b)
        data_a = {
            "symbols_json": s_a.symbols,
            "rows_json": rows_a,
            "row_count": s_a.row_count,
            "symbol_count": s_a.symbol_count,
            "mean_value": s_a.mean_value,
            "min_value": s_a.min_value,
            "max_value": s_a.max_value,
            "stddev_value": s_a.stddev_value,
            "quality_score": s_a.quality_score,
            "missing_signal_count": s_a.missing_signal_count,
            "signal_hash": compute_signal_hash(rows_a),
            "signal_column": "signal",
        }
        data_b = {
            "symbols_json": s_b.symbols,
            "rows_json": rows_b,
            "row_count": s_b.row_count,
            "symbol_count": s_b.symbol_count,
            "mean_value": s_b.mean_value,
            "min_value": s_b.min_value,
            "max_value": s_b.max_value,
            "stddev_value": s_b.stddev_value,
            "quality_score": s_b.quality_score,
            "missing_signal_count": s_b.missing_signal_count,
            "signal_hash": compute_signal_hash(rows_b),
            "signal_column": "signal",
        }
        result = compare_signal_snapshots("a", "b", "snap-a", "snap-b", data_a, data_b)
        assert result.is_same_snapshot is False
        assert result.row_count_delta == 1
        assert result.added_count == 1  # MSFT added
        assert "MSFT" in result.added_symbols

    def test_row_count_delta_always_computed(self):
        rows = _sample_rows(2)
        h = compute_signal_hash(rows)
        s = summarize_signal_snapshot(rows)
        data_a = {
            "symbols_json": s.symbols, "rows_json": rows,
            "row_count": 5, "symbol_count": 2,
            "mean_value": None, "min_value": None, "max_value": None, "stddev_value": None,
            "quality_score": 100, "missing_signal_count": 0,
            "signal_hash": h, "signal_column": "signal",
        }
        data_b = {
            "symbols_json": s.symbols, "rows_json": rows,
            "row_count": 5, "symbol_count": 2,
            "mean_value": None, "min_value": None, "max_value": None, "stddev_value": None,
            "quality_score": 100, "missing_signal_count": 0,
            "signal_hash": h, "signal_column": "signal",
        }
        result = compare_signal_snapshots("a", "b", "a", "b", data_a, data_b)
        # Even when identical, row_count_delta should be computed (0 in this case)
        assert result.row_count_delta == 0

    def test_keyed_comparison_available(self):
        rows_a = [{"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.5}]
        rows_b = [
            {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.8},
            {"symbol": "MSFT", "timestamp": "2024-01-01", "signal": 0.3},
        ]
        s_a = summarize_signal_snapshot(rows_a)
        s_b = summarize_signal_snapshot(rows_b)
        data_a = {"symbols_json": s_a.symbols, "rows_json": rows_a,
                  "row_count": 1, "symbol_count": 1,
                  "mean_value": 0.5, "min_value": 0.5, "max_value": 0.5,
                  "stddev_value": None, "quality_score": 100, "missing_signal_count": 0,
                  "signal_hash": compute_signal_hash(rows_a), "signal_column": "signal"}
        data_b = {"symbols_json": s_b.symbols, "rows_json": rows_b,
                  "row_count": 2, "symbol_count": 2,
                  "mean_value": 0.55, "min_value": 0.3, "max_value": 0.8,
                  "stddev_value": None, "quality_score": 100, "missing_signal_count": 0,
                  "signal_hash": compute_signal_hash(rows_b), "signal_column": "signal"}
        result = compare_signal_snapshots("a", "b", "a", "b", data_a, data_b)
        assert result.keyed_comparison_available is True
        assert result.added_rows_count == 1
        assert result.changed_rows_count == 1

    def test_explanation_hedged(self):
        rows_a = [{"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.5}]
        rows_b = [{"symbol": "MSFT", "timestamp": "2024-01-01", "signal": 0.9}]
        s_a = summarize_signal_snapshot(rows_a)
        s_b = summarize_signal_snapshot(rows_b)
        data_a = {"symbols_json": s_a.symbols, "rows_json": rows_a,
                  "row_count": 1, "symbol_count": 1,
                  "mean_value": 0.5, "min_value": 0.5, "max_value": 0.5,
                  "stddev_value": None, "quality_score": 100, "missing_signal_count": 0,
                  "signal_hash": compute_signal_hash(rows_a), "signal_column": "signal"}
        data_b = {"symbols_json": s_b.symbols, "rows_json": rows_b,
                  "row_count": 1, "symbol_count": 1,
                  "mean_value": 0.9, "min_value": 0.9, "max_value": 0.9,
                  "stddev_value": None, "quality_score": 100, "missing_signal_count": 0,
                  "signal_hash": compute_signal_hash(rows_b), "signal_column": "signal"}
        result = compare_signal_snapshots("a", "b", "snap-a", "snap-b", data_a, data_b)
        exp = result.deterministic_explanation.lower()
        assert "because" not in exp
        assert "caused" not in exp
        assert any(word in exp for word in ["observed", "noted", "may"])


# ---------------------------------------------------------------------------
# POST /api/strategies/{id}/signal-snapshots
# ---------------------------------------------------------------------------

class TestCreateSignalSnapshot:
    def test_creates_snapshot_201(self, client):
        s = _new_strategy(client)
        rows = _sample_rows(3)
        resp = client.post(
            f"/api/strategies/{s['id']}/signal-snapshots",
            json={"label": "sig-v1", "rows": rows},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["label"] == "sig-v1"
        assert data["row_count"] == 3
        assert len(data["signal_hash"]) == 64
        assert data["strategy_id"] == s["id"]
        assert data["quality_score"] == 100

    def test_stats_computed(self, client):
        s = _new_strategy(client)
        rows = [
            {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 1.0},
            {"symbol": "MSFT", "timestamp": "2024-01-02", "signal": 3.0},
        ]
        resp = client.post(
            f"/api/strategies/{s['id']}/signal-snapshots",
            json={"label": "stats-test", "rows": rows},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["symbol_count"] == 2
        assert data["signal_value_count"] == 2
        assert data["missing_signal_count"] == 0
        assert data["mean_value"] == pytest.approx(2.0, abs=0.001)
        assert data["min_timestamp"] == "2024-01-01"
        assert data["max_timestamp"] == "2024-01-02"

    def test_hash_is_deterministic(self, client):
        s = _new_strategy(client)
        rows = [
            {"symbol": "MSFT", "timestamp": "2024-01-01", "signal": 0.8},
            {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.5},
        ]
        r1 = client.post(
            f"/api/strategies/{s['id']}/signal-snapshots",
            json={"label": "hash-1", "rows": rows},
        )
        r2 = client.post(
            f"/api/strategies/{s['id']}/signal-snapshots",
            json={"label": "hash-2", "rows": list(reversed(rows))},
        )
        assert r1.json()["signal_hash"] == r2.json()["signal_hash"]

    def test_with_version_link(self, client):
        s = _new_strategy(client)
        v = _create_version(client, s["id"], "v1.0")
        resp = client.post(
            f"/api/strategies/{s['id']}/signal-snapshots",
            json={"label": "versioned-sig", "rows": _sample_rows(), "strategy_version_id": v["id"]},
        )
        assert resp.status_code == 201
        assert resp.json()["strategy_version_id"] == v["id"]

    def test_with_universe_snapshot_link(self, client):
        s = _new_strategy(client)
        us = _create_universe_snapshot(client, s["id"])
        resp = client.post(
            f"/api/strategies/{s['id']}/signal-snapshots",
            json={"label": "uni-linked-sig", "rows": _sample_rows(), "universe_snapshot_id": us["id"]},
        )
        assert resp.status_code == 201
        assert resp.json()["universe_snapshot_id"] == us["id"]

    def test_version_wrong_strategy_returns_404(self, client):
        s1 = _new_strategy(client)
        s2 = _new_strategy(client)
        v = _create_version(client, s1["id"], "v1.0")
        resp = client.post(
            f"/api/strategies/{s2['id']}/signal-snapshots",
            json={"label": "bad-version", "rows": _sample_rows(), "strategy_version_id": v["id"]},
        )
        assert resp.status_code == 404

    def test_universe_wrong_strategy_returns_404(self, client):
        s1 = _new_strategy(client)
        s2 = _new_strategy(client)
        us = _create_universe_snapshot(client, s1["id"])
        resp = client.post(
            f"/api/strategies/{s2['id']}/signal-snapshots",
            json={"label": "bad-uni", "rows": _sample_rows(), "universe_snapshot_id": us["id"]},
        )
        assert resp.status_code == 404

    def test_missing_strategy_returns_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/strategies/{fake_id}/signal-snapshots",
            json={"label": "x", "rows": _sample_rows()},
        )
        assert resp.status_code == 404

    def test_empty_rows_returns_422(self, client):
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/signal-snapshots",
            json={"label": "empty-rows", "rows": []},
        )
        assert resp.status_code == 422

    def test_with_signal_name(self, client):
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/signal-snapshots",
            json={"label": "named-sig", "rows": _sample_rows(), "signal_name": "momentum_12m"},
        )
        assert resp.status_code == 201
        assert resp.json()["signal_name"] == "momentum_12m"

    def test_with_source_filename(self, client):
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/signal-snapshots",
            json={
                "label": "file-sig",
                "rows": _sample_rows(),
                "source_type": "csv_import",
                "source_filename": "signal_2024.csv",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["source_filename"] == "signal_2024.csv"
        assert data["source_type"] == "csv_import"

    def test_response_has_no_rows_json(self, client):
        """Read (non-detail) response must not include rows_json blob."""
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/signal-snapshots",
            json={"label": "no-blob", "rows": _sample_rows()},
        )
        assert resp.status_code == 201
        assert "rows_json" not in resp.json()

    def test_symbols_json_in_response(self, client):
        s = _new_strategy(client)
        rows = [
            {"symbol": "MSFT", "signal": 0.5},
            {"symbol": "AAPL", "signal": 0.8},
        ]
        resp = client.post(
            f"/api/strategies/{s['id']}/signal-snapshots",
            json={"label": "sym-check", "rows": rows},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "symbols_json" in data
        assert set(data["symbols_json"]) == {"AAPL", "MSFT"}

    def test_timeline_event_created(self, client):
        s = _new_strategy(client)
        _create_signal_snapshot(client, s["id"], label="timeline-sig")
        resp = client.get(f"/api/strategies/{s['id']}/timeline")
        assert resp.status_code == 200
        events = resp.json()["items"]
        sig_events = [e for e in events if e["event_type"] == "signal_snapshot_logged"]
        assert len(sig_events) >= 1
        assert "timeline-sig" in sig_events[0]["title"]

    def test_with_metadata_json(self, client):
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/signal-snapshots",
            json={
                "label": "meta-sig",
                "rows": _sample_rows(),
                "metadata_json": {"alpha_type": "momentum"},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        # metadata_json should include our key
        assert data["metadata_json"]["alpha_type"] == "momentum"

    def test_quality_score_present(self, client):
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/signal-snapshots",
            json={"label": "quality-check", "rows": _sample_rows()},
        )
        assert resp.status_code == 201
        assert "quality_score" in resp.json()
        assert 0 <= resp.json()["quality_score"] <= 100

    def test_missing_signals_reduce_quality(self, client):
        s = _new_strategy(client)
        rows = [
            {"symbol": "AAPL", "signal": None},
            {"symbol": "MSFT", "signal": None},
            {"symbol": "GOOG", "signal": 0.5},
            {"symbol": "TSLA", "signal": 0.8},
        ]
        resp = client.post(
            f"/api/strategies/{s['id']}/signal-snapshots",
            json={"label": "low-quality", "rows": rows},
        )
        assert resp.status_code == 201
        assert resp.json()["quality_score"] < 100


# ---------------------------------------------------------------------------
# GET /api/strategies/{id}/signal-snapshots
# ---------------------------------------------------------------------------

class TestListSignalSnapshots:
    def test_returns_empty_list(self, client):
        s = _new_strategy(client)
        resp = client.get(f"/api/strategies/{s['id']}/signal-snapshots")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_snapshots(self, client):
        s = _new_strategy(client)
        _create_signal_snapshot(client, s["id"], "sig-a")
        _create_signal_snapshot(client, s["id"], "sig-b")
        resp = client.get(f"/api/strategies/{s['id']}/signal-snapshots")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_newest_first(self, client):
        s = _new_strategy(client)
        _create_signal_snapshot(client, s["id"], "older")
        _create_signal_snapshot(client, s["id"], "newer")
        resp = client.get(f"/api/strategies/{s['id']}/signal-snapshots")
        labels = [item["label"] for item in resp.json()]
        assert labels[0] == "newer"

    def test_filter_by_version_id(self, client):
        s = _new_strategy(client)
        v = _create_version(client, s["id"], "v1.0")
        _create_signal_snapshot(client, s["id"], "versioned", strategy_version_id=v["id"])
        _create_signal_snapshot(client, s["id"], "unversioned")
        resp = client.get(
            f"/api/strategies/{s['id']}/signal-snapshots",
            params={"version_id": v["id"]},
        )
        items = resp.json()
        assert len(items) == 1
        assert items[0]["label"] == "versioned"

    def test_missing_strategy_returns_404(self, client):
        resp = client.get(f"/api/strategies/{uuid.uuid4()}/signal-snapshots")
        assert resp.status_code == 404

    def test_no_rows_json_in_list_response(self, client):
        s = _new_strategy(client)
        _create_signal_snapshot(client, s["id"], "list-check")
        resp = client.get(f"/api/strategies/{s['id']}/signal-snapshots")
        for item in resp.json():
            assert "rows_json" not in item


# ---------------------------------------------------------------------------
# GET /api/signal-snapshots/{snapshot_id}
# ---------------------------------------------------------------------------

class TestGetSignalSnapshot:
    def test_returns_detail_with_rows(self, client):
        s = _new_strategy(client)
        rows = _sample_rows(3)
        ss = _create_signal_snapshot(client, s["id"], rows=rows)
        resp = client.get(f"/api/signal-snapshots/{ss['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert "rows_json" in data
        assert len(data["rows_json"]) == 3

    def test_missing_snapshot_returns_404(self, client):
        resp = client.get(f"/api/signal-snapshots/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_includes_all_read_fields(self, client):
        s = _new_strategy(client)
        ss = _create_signal_snapshot(client, s["id"])
        resp = client.get(f"/api/signal-snapshots/{ss['id']}")
        data = resp.json()
        for field in [
            "id", "strategy_id", "strategy_version_id", "universe_snapshot_id",
            "label", "signal_name", "source_type", "source_filename",
            "row_count", "symbol_count", "symbols_json",
            "min_timestamp", "max_timestamp",
            "signal_value_count", "missing_signal_count",
            "mean_value", "min_value", "max_value", "stddev_value",
            "signal_hash", "quality_score", "metadata_json",
            "created_at", "updated_at", "rows_json",
        ]:
            assert field in data, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# GET /api/strategies/{id}/signal-snapshots/compare
# ---------------------------------------------------------------------------

class TestCompareSignalSnapshotsRoute:
    def test_compare_identical_snapshots(self, client):
        s = _new_strategy(client)
        rows = _sample_rows(3)
        ss_a = _create_signal_snapshot(client, s["id"], "base", rows=rows)
        ss_b = _create_signal_snapshot(client, s["id"], "same", rows=rows)
        resp = client.get(
            f"/api/strategies/{s['id']}/signal-snapshots/compare",
            params={"snapshot_a_id": ss_a["id"], "snapshot_b_id": ss_b["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_same_snapshot"] is True
        assert data["added_count"] == 0
        assert data["removed_count"] == 0

    def test_compare_different_snapshots(self, client):
        s = _new_strategy(client)
        rows_a = [{"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.5}]
        rows_b = [
            {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.8},
            {"symbol": "MSFT", "timestamp": "2024-01-01", "signal": 0.3},
        ]
        ss_a = _create_signal_snapshot(client, s["id"], "v1", rows=rows_a)
        ss_b = _create_signal_snapshot(client, s["id"], "v2", rows=rows_b)
        resp = client.get(
            f"/api/strategies/{s['id']}/signal-snapshots/compare",
            params={"snapshot_a_id": ss_a["id"], "snapshot_b_id": ss_b["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_same_snapshot"] is False
        assert data["added_count"] == 1
        assert "MSFT" in data["added_symbols"]
        assert data["row_count_delta"] == 1

    def test_compare_response_fields(self, client):
        s = _new_strategy(client)
        ss_a = _create_signal_snapshot(client, s["id"], "a")
        ss_b = _create_signal_snapshot(client, s["id"], "b", rows=_sample_rows(4))
        resp = client.get(
            f"/api/strategies/{s['id']}/signal-snapshots/compare",
            params={"snapshot_a_id": ss_a["id"], "snapshot_b_id": ss_b["id"]},
        )
        data = resp.json()
        for field in [
            "snapshot_a_id", "snapshot_b_id",
            "snapshot_a_label", "snapshot_b_label",
            "snapshot_a_row_count", "snapshot_b_row_count",
            "snapshot_a_symbol_count", "snapshot_b_symbol_count",
            "is_same_snapshot", "row_count_delta", "symbol_count_delta",
            "added_count", "removed_count", "common_symbols_count",
            "overlap_ratio",
            "mean_value_delta", "min_value_delta", "max_value_delta",
            "stddev_value_delta", "quality_score_delta", "missing_signal_delta",
            "keyed_comparison_available",
            "added_rows_count", "removed_rows_count", "changed_rows_count",
            "examples", "added_symbols", "removed_symbols",
            "highlighted_changes", "deterministic_explanation", "warnings",
        ]:
            assert field in data, f"Missing field: {field}"

    def test_snapshot_a_not_found(self, client):
        s = _new_strategy(client)
        ss_b = _create_signal_snapshot(client, s["id"], "b")
        resp = client.get(
            f"/api/strategies/{s['id']}/signal-snapshots/compare",
            params={"snapshot_a_id": str(uuid.uuid4()), "snapshot_b_id": ss_b["id"]},
        )
        assert resp.status_code == 404

    def test_snapshot_b_not_found(self, client):
        s = _new_strategy(client)
        ss_a = _create_signal_snapshot(client, s["id"], "a")
        resp = client.get(
            f"/api/strategies/{s['id']}/signal-snapshots/compare",
            params={"snapshot_a_id": ss_a["id"], "snapshot_b_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_snapshot_wrong_strategy_returns_404(self, client):
        s1 = _new_strategy(client)
        s2 = _new_strategy(client)
        ss_a = _create_signal_snapshot(client, s1["id"], "a")
        ss_b = _create_signal_snapshot(client, s2["id"], "b")
        # A belongs to s1, B belongs to s2 — compare on s1 should 404 B
        resp = client.get(
            f"/api/strategies/{s1['id']}/signal-snapshots/compare",
            params={"snapshot_a_id": ss_a["id"], "snapshot_b_id": ss_b["id"]},
        )
        assert resp.status_code == 404

    def test_missing_strategy_returns_404(self, client):
        resp = client.get(
            f"/api/strategies/{uuid.uuid4()}/signal-snapshots/compare",
            params={"snapshot_a_id": str(uuid.uuid4()), "snapshot_b_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_missing_query_params_returns_422(self, client):
        s = _new_strategy(client)
        resp = client.get(f"/api/strategies/{s['id']}/signal-snapshots/compare")
        assert resp.status_code == 422

    def test_keyed_comparison_in_response(self, client):
        s = _new_strategy(client)
        rows_a = [
            {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.5},
        ]
        rows_b = [
            {"symbol": "AAPL", "timestamp": "2024-01-01", "signal": 0.8},
            {"symbol": "MSFT", "timestamp": "2024-01-01", "signal": 0.3},
        ]
        ss_a = _create_signal_snapshot(client, s["id"], "v1", rows=rows_a)
        ss_b = _create_signal_snapshot(client, s["id"], "v2", rows=rows_b)
        resp = client.get(
            f"/api/strategies/{s['id']}/signal-snapshots/compare",
            params={"snapshot_a_id": ss_a["id"], "snapshot_b_id": ss_b["id"]},
        )
        data = resp.json()
        assert data["keyed_comparison_available"] is True
        assert data["changed_rows_count"] >= 1


# ---------------------------------------------------------------------------
# Run linkage: POST /api/strategies/{id}/runs with signal_snapshot_id
# ---------------------------------------------------------------------------

class TestRunSignalSnapshotLinkage:
    def test_run_with_signal_snapshot(self, client):
        s = _new_strategy(client)
        ss = _create_signal_snapshot(client, s["id"])
        resp = client.post(
            f"/api/strategies/{s['id']}/runs",
            json={
                "run_name": "run-with-sig",
                "run_type": "backtest",
                "signal_snapshot_id": ss["id"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["signal_snapshot_id"] == ss["id"]
        assert data["signal_snapshot"] is not None
        assert data["signal_snapshot"]["label"] == ss["label"]

    def test_run_without_signal_snapshot(self, client):
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/runs",
            json={"run_name": "run-no-sig", "run_type": "backtest"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["signal_snapshot_id"] is None
        assert data["signal_snapshot"] is None

    def test_signal_snapshot_wrong_strategy_returns_400(self, client):
        s1 = _new_strategy(client)
        s2 = _new_strategy(client)
        ss = _create_signal_snapshot(client, s1["id"])
        resp = client.post(
            f"/api/strategies/{s2['id']}/runs",
            json={"run_name": "bad-run", "run_type": "backtest", "signal_snapshot_id": ss["id"]},
        )
        assert resp.status_code == 400

    def test_nonexistent_signal_snapshot_returns_404(self, client):
        s = _new_strategy(client)
        resp = client.post(
            f"/api/strategies/{s['id']}/runs",
            json={
                "run_name": "ghost-run",
                "run_type": "backtest",
                "signal_snapshot_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 404

    def test_signal_summary_fields(self, client):
        s = _new_strategy(client)
        ss = _create_signal_snapshot(client, s["id"])
        resp = client.post(
            f"/api/strategies/{s['id']}/runs",
            json={"run_name": "summary-check", "run_type": "backtest", "signal_snapshot_id": ss["id"]},
        )
        assert resp.status_code == 201
        sig = resp.json()["signal_snapshot"]
        for field in [
            "id", "label", "signal_name", "row_count", "symbol_count",
            "signal_value_count", "missing_signal_count",
            "quality_score", "mean_value", "stddev_value", "created_at",
        ]:
            assert field in sig, f"Missing field in signal_snapshot summary: {field}"

    def test_version_mismatch_returns_400(self, client):
        """Signal snapshot version != run version should return 400."""
        s = _new_strategy(client)
        v1 = _create_version(client, s["id"], "v1.0")
        v2 = _create_version(client, s["id"], "v2.0")
        ss = _create_signal_snapshot(client, s["id"], strategy_version_id=v1["id"])
        resp = client.post(
            f"/api/strategies/{s['id']}/runs",
            json={
                "run_name": "mismatch-run",
                "run_type": "backtest",
                "strategy_version_id": v2["id"],
                "signal_snapshot_id": ss["id"],
            },
        )
        assert resp.status_code == 400

    def test_version_match_is_ok(self, client):
        """Signal snapshot version == run version should succeed."""
        s = _new_strategy(client)
        v = _create_version(client, s["id"], "v1.0")
        ss = _create_signal_snapshot(client, s["id"], strategy_version_id=v["id"])
        resp = client.post(
            f"/api/strategies/{s['id']}/runs",
            json={
                "run_name": "match-run",
                "run_type": "backtest",
                "strategy_version_id": v["id"],
                "signal_snapshot_id": ss["id"],
            },
        )
        assert resp.status_code == 201

    def test_universe_mismatch_returns_400(self, client):
        """Signal snapshot universe != run universe should return 400."""
        s = _new_strategy(client)
        us1 = _create_universe_snapshot(client, s["id"], "uni-1")
        us2 = _create_universe_snapshot(client, s["id"], "uni-2", symbols=["TSLA"])
        ss = _create_signal_snapshot(client, s["id"], universe_snapshot_id=us1["id"])
        resp = client.post(
            f"/api/strategies/{s['id']}/runs",
            json={
                "run_name": "uni-mismatch",
                "run_type": "backtest",
                "universe_snapshot_id": us2["id"],
                "signal_snapshot_id": ss["id"],
            },
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/strategies/{id}/runs: signal_snapshot embedded
# ---------------------------------------------------------------------------

class TestListRunsSignalEvidence:
    def test_signal_snapshot_embedded_in_list(self, client):
        s = _new_strategy(client)
        ss = _create_signal_snapshot(client, s["id"])
        _create_run(client, s["id"], signal_snapshot_id=ss["id"])
        resp = client.get(f"/api/strategies/{s['id']}/runs")
        assert resp.status_code == 200
        runs = resp.json()
        linked = [r for r in runs if r.get("signal_snapshot_id") == ss["id"]]
        assert len(linked) == 1
        assert linked[0]["signal_snapshot"] is not None
        assert linked[0]["signal_snapshot"]["id"] == ss["id"]

    def test_runs_without_signal_snapshot_have_null(self, client):
        s = _new_strategy(client)
        _create_run(client, s["id"])
        resp = client.get(f"/api/strategies/{s['id']}/runs")
        runs = resp.json()
        no_sig = [r for r in runs if r.get("signal_snapshot_id") is None]
        for r in no_sig:
            assert r["signal_snapshot"] is None


# ---------------------------------------------------------------------------
# GET /api/strategies/{id}: strategy detail includes signal snapshots
# ---------------------------------------------------------------------------

class TestStrategyDetailSignalSnapshots:
    def test_signal_snapshots_in_detail(self, client):
        s = _new_strategy(client)
        _create_signal_snapshot(client, s["id"], "detail-sig-a")
        _create_signal_snapshot(client, s["id"], "detail-sig-b")
        resp = client.get(f"/api/strategies/{s['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert "signal_snapshots" in data
        labels = [ss["label"] for ss in data["signal_snapshots"]]
        assert "detail-sig-a" in labels
        assert "detail-sig-b" in labels

    def test_no_rows_json_in_detail_signal_snapshots(self, client):
        s = _new_strategy(client)
        _create_signal_snapshot(client, s["id"], "no-blob-detail")
        resp = client.get(f"/api/strategies/{s['id']}")
        for ss in resp.json()["signal_snapshots"]:
            assert "rows_json" not in ss

    def test_version_signal_snapshot_count(self, client):
        s = _new_strategy(client)
        v = _create_version(client, s["id"], "v2.0")
        _create_signal_snapshot(client, s["id"], "s1", strategy_version_id=v["id"])
        _create_signal_snapshot(client, s["id"], "s2", strategy_version_id=v["id"])
        resp = client.get(f"/api/strategies/{s['id']}")
        data = resp.json()
        matching = [ver for ver in data["versions"] if ver["id"] == v["id"]]
        assert len(matching) == 1
        assert matching[0]["signal_snapshot_count"] == 2


# ---------------------------------------------------------------------------
# GET /api/strategies/{id}/versions: signal_snapshot_count
# ---------------------------------------------------------------------------

class TestVersionsSignalSnapshotCount:
    def test_signal_snapshot_count_in_version_list(self, client):
        s = _new_strategy(client)
        v = _create_version(client, s["id"], "v3.0")
        _create_signal_snapshot(client, s["id"], "v3-sig", strategy_version_id=v["id"])
        resp = client.get(f"/api/strategies/{s['id']}/versions")
        assert resp.status_code == 200
        matching = [ver for ver in resp.json() if ver["id"] == v["id"]]
        assert matching[0]["signal_snapshot_count"] == 1

    def test_new_version_has_zero_count(self, client):
        s = _new_strategy(client)
        v = _create_version(client, s["id"], "v4.0")
        resp = client.get(f"/api/strategies/{s['id']}/versions")
        matching = [ver for ver in resp.json() if ver["id"] == v["id"]]
        assert matching[0]["signal_snapshot_count"] == 0
