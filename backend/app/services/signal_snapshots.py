"""Signal snapshot service — M17.

Provides deterministic signal normalization, hashing, quality scoring,
and comparison of signal snapshots. No AI, no live data, no external calls.

Design constraints:
  - Signal rows are stored verbatim but normalized for hash/stats.
  - signal_hash is derived from sorted rows (by symbol+timestamp or row index) + optional metadata.
  - Comparison is deterministic: set-based for symbols, keyed for row-level changes.
  - Language is hedged throughout — no causal claims.
  - Quality score: start 100, deduct for missing/non-numeric/duplicate/invalid-timestamp issues.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


_DISPLAY_CAP_SYMBOLS = 50
_DISPLAY_CAP_EXAMPLES = 20


# ---------------------------------------------------------------------------
# Row normalization and hashing
# ---------------------------------------------------------------------------

def _is_numeric(v: Any) -> bool:
    """Return True if v is a real finite number (int or float, not NaN/Inf)."""
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return math.isfinite(v)
    return False


def _parse_timestamp(ts: Any) -> str | None:
    """Try to parse a timestamp value to an ISO string. Return None if invalid."""
    if ts is None:
        return None
    s = str(ts).strip()
    if not s:
        return None
    # Try common ISO formats
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            datetime.strptime(s, fmt)
            return s
        except ValueError:
            continue
    return None


def normalize_signal_rows(rows: list[dict], signal_column: str = "signal") -> list[dict]:
    """Return rows as-is (stored verbatim). Validates that rows is a list of dicts."""
    if not isinstance(rows, list):
        raise ValueError("rows must be a list of objects")
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"Row {i} is not an object")
    return rows


def compute_signal_hash(
    rows: list[dict],
    metadata: dict | None = None,
    signal_column: str = "signal",
) -> str:
    """Return a 64-char hex SHA-256 of the signal snapshot.

    Rows are sorted by (symbol, timestamp, signal_column) for determinism.
    Metadata is included with sort_keys=True.
    """

    def _row_sort_key(row: dict):
        return (
            str(row.get("symbol", "") or ""),
            str(row.get("timestamp", "") or ""),
            str(row.get(signal_column, "") or ""),
        )

    sorted_rows = sorted(rows, key=_row_sort_key)
    payload: dict = {"rows": sorted_rows, "signal_column": signal_column}
    if metadata:
        payload["metadata"] = metadata
    normalised = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Signal summary
# ---------------------------------------------------------------------------

@dataclass
class SignalSummary:
    row_count: int
    symbol_count: int
    symbols: list[str]
    min_timestamp: str | None
    max_timestamp: str | None
    signal_value_count: int        # non-null, numeric signal values
    missing_signal_count: int      # null or non-numeric signal values
    mean_value: float | None
    min_value: float | None
    max_value: float | None
    stddev_value: float | None
    quality_score: int
    warnings: list[str] = field(default_factory=list)


def summarize_signal_snapshot(
    rows: list[dict], signal_column: str = "signal"
) -> SignalSummary:
    """Compute summary statistics and quality score from signal rows.

    Quality deductions:
    - Missing/non-numeric signal values: up to -40 (proportional)
    - Duplicate symbol+timestamp keys: -15 if > 5% of rows are dupes
    - Invalid timestamps: -10 if any present (when timestamp field exists)
    - Zero variance (all same value, many rows): -5
    """
    row_count = len(rows)

    # --- Collect symbols ---
    symbols_seen: set[str] = set()

    # --- Collect signal values ---
    numeric_values: list[float] = []
    missing_count = 0
    non_numeric_count = 0

    # --- Collect timestamps ---
    valid_ts: list[str] = []
    invalid_ts_count = 0
    has_timestamp_field = False

    # --- Duplicate tracking ---
    key_set: set[tuple] = set()
    dupe_count = 0

    warnings: list[str] = []

    for row in rows:
        # Symbol
        sym = row.get("symbol")
        if sym is not None:
            sym_str = str(sym).strip().upper()
            if sym_str:
                symbols_seen.add(sym_str)

        # Timestamp
        ts_raw = row.get("timestamp")
        if ts_raw is not None:
            has_timestamp_field = True
            parsed = _parse_timestamp(ts_raw)
            if parsed is not None:
                valid_ts.append(parsed)
            else:
                invalid_ts_count += 1

        # Signal value
        sig = row.get(signal_column)
        if sig is None:
            missing_count += 1
        elif _is_numeric(sig):
            numeric_values.append(float(sig))
        else:
            missing_count += 1
            non_numeric_count += 1

        # Duplicate key check
        sym_key = str(row.get("symbol", "")) if row.get("symbol") is not None else ""
        ts_key = str(row.get("timestamp", "")) if row.get("timestamp") is not None else ""
        key = (sym_key, ts_key)
        if key in key_set and (sym_key or ts_key):
            dupe_count += 1
        else:
            key_set.add(key)

    symbols_list_sorted = sorted(symbols_seen)
    symbol_count = len(symbols_list_sorted)

    # Timestamps
    min_timestamp: str | None = None
    max_timestamp: str | None = None
    if valid_ts:
        ts_sorted = sorted(valid_ts)
        min_timestamp = ts_sorted[0]
        max_timestamp = ts_sorted[-1]

    # Signal stats
    signal_value_count = len(numeric_values)

    mean_value: float | None = None
    min_value_f: float | None = None
    max_value_f: float | None = None
    stddev_value: float | None = None

    if numeric_values:
        mean_value = round(sum(numeric_values) / len(numeric_values), 6)
        min_value_f = min(numeric_values)
        max_value_f = max(numeric_values)

        if len(numeric_values) >= 2:
            variance = sum((x - mean_value) ** 2 for x in numeric_values) / len(numeric_values)
            stddev_value = round(math.sqrt(variance), 6)

    # --- Quality score ---
    quality = 100

    # Missing/non-numeric signal deduction
    if row_count > 0 and missing_count > 0:
        missing_ratio = missing_count / row_count
        if missing_ratio >= 0.5:
            deduction = 40
        elif missing_ratio >= 0.25:
            deduction = 25
        elif missing_ratio >= 0.1:
            deduction = 15
        else:
            deduction = 8
        quality -= deduction
        warnings.append(
            f"{missing_count} missing/non-numeric signal value(s) observed "
            f"({missing_ratio:.1%} of rows)"
        )

    # Non-numeric specific mention
    if non_numeric_count > 0:
        warnings.append(f"{non_numeric_count} non-numeric signal value(s) noted")

    # Duplicate key deduction
    if row_count > 0 and dupe_count > 0:
        dupe_ratio = dupe_count / row_count
        if dupe_ratio > 0.05:
            quality -= 15
            warnings.append(
                f"{dupe_count} duplicate symbol+timestamp pair(s) observed "
                f"({dupe_ratio:.1%} of rows)"
            )
        else:
            warnings.append(f"{dupe_count} duplicate symbol+timestamp pair(s) noted")

    # Invalid timestamp deduction
    if has_timestamp_field and invalid_ts_count > 0:
        quality -= 10
        warnings.append(f"{invalid_ts_count} invalid timestamp(s) noted")

    # Zero variance warning
    if len(numeric_values) >= 10 and stddev_value is not None and stddev_value == 0.0:
        quality -= 5
        warnings.append("Zero signal variance observed — all values identical")

    quality = max(0, quality)

    return SignalSummary(
        row_count=row_count,
        symbol_count=symbol_count,
        symbols=symbols_list_sorted,
        min_timestamp=min_timestamp,
        max_timestamp=max_timestamp,
        signal_value_count=signal_value_count,
        missing_signal_count=missing_count,
        mean_value=mean_value,
        min_value=min_value_f,
        max_value=max_value_f,
        stddev_value=stddev_value,
        quality_score=quality,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Comparison result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SignalRowChange:
    symbol: str | None
    timestamp: str | None
    change_type: str  # "added" | "removed" | "changed"
    old_value: float | None = None
    new_value: float | None = None
    delta: float | None = None


@dataclass
class SignalComparisonResult:
    snapshot_a_id: str
    snapshot_b_id: str
    snapshot_a_label: str
    snapshot_b_label: str
    snapshot_a_row_count: int
    snapshot_b_row_count: int
    snapshot_a_symbol_count: int
    snapshot_b_symbol_count: int
    is_same_snapshot: bool
    row_count_delta: int
    symbol_count_delta: int
    added_count: int
    removed_count: int
    common_symbols_count: int
    overlap_ratio: float
    mean_value_delta: float | None
    min_value_delta: float | None
    max_value_delta: float | None
    stddev_value_delta: float | None
    quality_score_delta: int
    missing_signal_delta: int
    # Keyed row changes (if symbol+timestamp available)
    keyed_comparison_available: bool
    added_rows_count: int
    removed_rows_count: int
    changed_rows_count: int
    examples: list[SignalRowChange] = field(default_factory=list)
    added_symbols: list[str] = field(default_factory=list)
    removed_symbols: list[str] = field(default_factory=list)
    highlighted_changes: list[str] = field(default_factory=list)
    deterministic_explanation: str = ""
    warnings: list[str] = field(default_factory=list)


def compare_signal_snapshots(
    snap_a_id: str,
    snap_b_id: str,
    snap_a_label: str,
    snap_b_label: str,
    snap_a_data: dict,  # keys: symbols_json, rows_json, row_count, symbol_count,
                        # mean_value, min_value, max_value, stddev_value, quality_score,
                        # missing_signal_count, signal_hash, signal_column
    snap_b_data: dict,
) -> SignalComparisonResult:
    """Deterministically compare two signal snapshots."""

    signal_col_a = snap_a_data.get("signal_column", "signal")
    signal_col_b = snap_b_data.get("signal_column", "signal")

    symbols_a = set(snap_a_data.get("symbols_json") or [])
    symbols_b = set(snap_b_data.get("symbols_json") or [])

    added_syms_full = sorted(symbols_b - symbols_a)
    removed_syms_full = sorted(symbols_a - symbols_b)
    common_syms = symbols_a & symbols_b

    n_a = snap_a_data.get("symbol_count", 0) or len(symbols_a)
    n_b = snap_b_data.get("symbol_count", 0) or len(symbols_b)
    max_syms = max(n_a, n_b)
    overlap_ratio = round(len(common_syms) / max_syms, 4) if max_syms > 0 else 1.0

    is_same = (snap_a_data.get("signal_hash") == snap_b_data.get("signal_hash"))

    # Numeric deltas
    def _delta(va: Any, vb: Any) -> float | None:
        if va is None or vb is None:
            return None
        return round(float(vb) - float(va), 6)

    mean_delta = _delta(snap_a_data.get("mean_value"), snap_b_data.get("mean_value"))
    min_delta = _delta(snap_a_data.get("min_value"), snap_b_data.get("min_value"))
    max_delta = _delta(snap_a_data.get("max_value"), snap_b_data.get("max_value"))
    std_delta = _delta(snap_a_data.get("stddev_value"), snap_b_data.get("stddev_value"))
    quality_delta = (
        (snap_b_data.get("quality_score", 100) or 100)
        - (snap_a_data.get("quality_score", 100) or 100)
    )
    missing_delta = (
        (snap_b_data.get("missing_signal_count", 0) or 0)
        - (snap_a_data.get("missing_signal_count", 0) or 0)
    )

    # Row count delta — always computed regardless of is_same
    row_delta = (
        (snap_b_data.get("row_count", 0) or 0)
        - (snap_a_data.get("row_count", 0) or 0)
    )

    # Keyed row comparison
    rows_a = snap_a_data.get("rows_json") or []
    rows_b = snap_b_data.get("rows_json") or []

    keyed_available = False
    added_rows_count = 0
    removed_rows_count = 0
    changed_rows_count = 0
    examples: list[SignalRowChange] = []
    warnings: list[str] = []

    # Check if rows have symbol and timestamp
    has_keys_a = any("symbol" in r and "timestamp" in r for r in rows_a[:5])
    has_keys_b = any("symbol" in r and "timestamp" in r for r in rows_b[:5])

    if has_keys_a and has_keys_b:
        keyed_available = True

        def _row_key(row: dict) -> tuple:
            return (
                str(row.get("symbol", "") or ""),
                str(row.get("timestamp", "") or ""),
            )

        def _sig_val(row: dict, col: str) -> float | None:
            v = row.get(col)
            if _is_numeric(v):
                return float(v)
            return None

        map_a = {_row_key(r): r for r in rows_a}
        map_b = {_row_key(r): r for r in rows_b}

        keys_a = set(map_a.keys())
        keys_b = set(map_b.keys())

        added_keys = keys_b - keys_a
        removed_keys = keys_a - keys_b
        common_keys = keys_a & keys_b

        added_rows_count = len(added_keys)
        removed_rows_count = len(removed_keys)

        for k in common_keys:
            va = _sig_val(map_a[k], signal_col_a)
            vb = _sig_val(map_b[k], signal_col_b)
            if va != vb:
                changed_rows_count += 1

        # Collect examples (capped at _DISPLAY_CAP_EXAMPLES)
        for k in sorted(added_keys)[: _DISPLAY_CAP_EXAMPLES // 3 + 1]:
            row = map_b[k]
            examples.append(
                SignalRowChange(
                    symbol=row.get("symbol"),
                    timestamp=row.get("timestamp"),
                    change_type="added",
                    new_value=_sig_val(row, signal_col_b),
                )
            )
        for k in sorted(removed_keys)[: _DISPLAY_CAP_EXAMPLES // 3 + 1]:
            row = map_a[k]
            examples.append(
                SignalRowChange(
                    symbol=row.get("symbol"),
                    timestamp=row.get("timestamp"),
                    change_type="removed",
                    old_value=_sig_val(row, signal_col_a),
                )
            )
        changed_examples = 0
        for k in sorted(common_keys):
            if changed_examples >= _DISPLAY_CAP_EXAMPLES // 3:
                break
            va = _sig_val(map_a[k], signal_col_a)
            vb = _sig_val(map_b[k], signal_col_b)
            if va != vb:
                delta_val = round(vb - va, 6) if (va is not None and vb is not None) else None
                examples.append(
                    SignalRowChange(
                        symbol=map_a[k].get("symbol"),
                        timestamp=map_a[k].get("timestamp"),
                        change_type="changed",
                        old_value=va,
                        new_value=vb,
                        delta=delta_val,
                    )
                )
                changed_examples += 1

        examples = examples[:_DISPLAY_CAP_EXAMPLES]

        if len(added_keys) + len(removed_keys) + changed_rows_count > _DISPLAY_CAP_EXAMPLES:
            warnings.append(f"Row-level changes capped at {_DISPLAY_CAP_EXAMPLES} examples")

    # Highlighted changes
    highlights: list[str] = []
    if is_same:
        highlights.append(
            "Signal snapshots noted as identical — no coverage or distribution changes observed"
        )
    else:
        if added_syms_full:
            sample = added_syms_full[:3]
            highlights.append(
                f"{len(added_syms_full)} symbol(s) observed as added (e.g. {', '.join(sample)})"
            )
        if removed_syms_full:
            sample = removed_syms_full[:3]
            highlights.append(
                f"{len(removed_syms_full)} symbol(s) observed as removed (e.g. {', '.join(sample)})"
            )
        if mean_delta is not None and abs(mean_delta) > 1e-9:
            direction = "increased" if mean_delta > 0 else "decreased"
            highlights.append(f"Mean signal value {direction} by {mean_delta:+.4f}")
        if std_delta is not None and abs(std_delta) > 1e-9:
            highlights.append(f"Signal stddev changed by {std_delta:+.4f}")
        if quality_delta != 0:
            direction = "improved" if quality_delta > 0 else "declined"
            highlights.append(f"Quality score {direction} by {quality_delta:+d} point(s)")
        if missing_delta != 0:
            highlights.append(f"Missing signal count changed by {missing_delta:+d}")
        if keyed_available and (added_rows_count + removed_rows_count + changed_rows_count) > 0:
            highlights.append(
                f"{added_rows_count} row(s) added, {removed_rows_count} removed, "
                f"{changed_rows_count} changed at row level"
            )

    # Explanation
    if is_same:
        explanation = (
            f"Signal snapshot '{snap_a_label}' and '{snap_b_label}' contain identical "
            f"signal data. No coverage or distribution changes were observed."
        )
    else:
        parts = [
            f"Signal snapshot '{snap_a_label}' observed {snap_a_data.get('row_count', 0)} row(s); "
            f"'{snap_b_label}' observed {snap_b_data.get('row_count', 0)} row(s) — "
            f"a row count change of {row_delta:+d}."
        ]
        if len(added_syms_full) + len(removed_syms_full) > 0:
            parts.append(
                f"Symbol coverage: {len(added_syms_full)} added, {len(removed_syms_full)} removed. "
                f"Overlap ratio observed at {overlap_ratio:.1%}."
            )
        if mean_delta is not None:
            a_mean = snap_a_data.get("mean_value")
            b_mean = snap_b_data.get("mean_value")
            parts.append(
                f"Mean signal value shifted from "
                f"{a_mean:.4f} to {b_mean:.4f} "
                f"({mean_delta:+.4f}). Distribution shift may affect backtest behavior and requires review."
            )
        explanation = " ".join(parts)

    return SignalComparisonResult(
        snapshot_a_id=snap_a_id,
        snapshot_b_id=snap_b_id,
        snapshot_a_label=snap_a_label,
        snapshot_b_label=snap_b_label,
        snapshot_a_row_count=snap_a_data.get("row_count", 0) or 0,
        snapshot_b_row_count=snap_b_data.get("row_count", 0) or 0,
        snapshot_a_symbol_count=n_a,
        snapshot_b_symbol_count=n_b,
        is_same_snapshot=is_same,
        row_count_delta=row_delta,
        symbol_count_delta=n_b - n_a,
        added_count=len(added_syms_full),
        removed_count=len(removed_syms_full),
        common_symbols_count=len(common_syms),
        overlap_ratio=overlap_ratio,
        mean_value_delta=mean_delta,
        min_value_delta=min_delta,
        max_value_delta=max_delta,
        stddev_value_delta=std_delta,
        quality_score_delta=quality_delta,
        missing_signal_delta=missing_delta,
        keyed_comparison_available=keyed_available,
        added_rows_count=added_rows_count,
        removed_rows_count=removed_rows_count,
        changed_rows_count=changed_rows_count,
        examples=examples,
        added_symbols=added_syms_full[:_DISPLAY_CAP_SYMBOLS],
        removed_symbols=removed_syms_full[:_DISPLAY_CAP_SYMBOLS],
        highlighted_changes=highlights[:10],
        deterministic_explanation=explanation,
        warnings=warnings,
    )
