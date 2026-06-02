"""Signal quality drill-down service for M38.

Computes distribution-level, symbol-level, and row-level quality analysis
from signal snapshot rows_json.
Pure Python — no database access, no AI, no causal claims.

This is a NEW service and does NOT modify signal_snapshots.py.
"""

from __future__ import annotations

from datetime import datetime as _dt


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_float(v):
    """Return float if v is a real number, else None."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None


def _is_numeric_signal(v) -> bool:
    """Return True if v has a valid float representation."""
    return _safe_float(v) is not None


def _iqr_bounds(numeric_vals):
    """Return (lower, upper) IQR-based outlier bounds, or (None, None) if too few values."""
    if len(numeric_vals) < 4:
        return None, None
    sv = sorted(numeric_vals)
    n = len(sv)
    q1 = sv[n // 4]
    q3 = sv[(3 * n) // 4]
    iqr = q3 - q1
    if iqr <= 0:
        return None, None
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


# ---------------------------------------------------------------------------
# Distribution analysis
# ---------------------------------------------------------------------------

def compute_signal_distribution(rows_json: list[dict], signal_column: str = "signal") -> dict:
    """Compute signal value distribution statistics from rows_json.

    Caps processing at 5000 rows.
    """
    rows = rows_json[:5000]
    total_rows = len(rows)
    all_vals = [row.get(signal_column) for row in rows]
    missing_count = sum(1 for v in all_vals if v is None)
    non_numeric_count = sum(1 for v in all_vals if v is not None and _safe_float(v) is None)
    numeric_vals = [_safe_float(v) for v in all_vals if _safe_float(v) is not None]
    value_count = len(numeric_vals)
    missing_rate = round(missing_count / total_rows, 4) if total_rows > 0 else 0
    non_numeric_rate = round(non_numeric_count / total_rows, 4) if total_rows > 0 else 0

    mean_v = median_v = min_v = max_v = stddev_v = None
    zero_count = positive_count = negative_count = 0
    outlier_count = extreme_pos = extreme_neg = unique_count = 0

    if numeric_vals:
        min_v = round(min(numeric_vals), 4)
        max_v = round(max(numeric_vals), 4)
        mean_v = round(sum(numeric_vals) / len(numeric_vals), 4)
        sv = sorted(numeric_vals)
        n = len(sv)
        median_v = round(sv[n // 2] if n % 2 == 1 else (sv[n // 2 - 1] + sv[n // 2]) / 2, 4)
        if n > 1:
            var = sum((v - mean_v) ** 2 for v in numeric_vals) / (n - 1)
            stddev_v = round(var ** 0.5, 4)
        zero_count = sum(1 for v in numeric_vals if v == 0)
        positive_count = sum(1 for v in numeric_vals if v > 0)
        negative_count = sum(1 for v in numeric_vals if v < 0)
        unique_count = len(set(round(v, 8) for v in numeric_vals))
        lo, hi = _iqr_bounds(numeric_vals)
        if lo is not None:
            outlier_count = sum(1 for v in numeric_vals if v < lo or v > hi)
        if stddev_v and stddev_v > 0:
            extreme_pos = sum(1 for v in numeric_vals if (v - mean_v) / stddev_v > 3)
            extreme_neg = sum(1 for v in numeric_vals if (v - mean_v) / stddev_v < -3)

    issues = []
    if value_count == 0:
        status = "unusable"
        issues.append("No valid numeric signal values found")
    elif non_numeric_rate > 0.5:
        status = "unusable"
        issues.append(
            f"{non_numeric_count} non-numeric signal values (>{round(non_numeric_rate * 100)}%)"
        )
    elif missing_rate > 0.2 or non_numeric_rate > 0.2:
        status = "weak"
        if missing_rate > 0.2:
            issues.append(f"Missing signal rate {missing_rate:.1%}")
        if non_numeric_rate > 0.2:
            issues.append(f"Non-numeric rate {non_numeric_rate:.1%}")
    else:
        status = "clean"

    if status in ("clean", "review"):
        if outlier_count > 0:
            status = "review"
            issues.append(f"{outlier_count} outlier value(s)")
        if value_count >= 10 and unique_count == 1:
            status = "review"
            issues.append("All signal values are identical (zero variance)")
        if missing_count > 0:
            status = "review" if status == "clean" else status
            issues.append(f"{missing_count} missing value(s)")

    return {
        "signal_column": signal_column,
        "value_count": value_count,
        "missing_count": missing_count,
        "non_numeric_count": non_numeric_count,
        "mean_value": mean_v,
        "median_value": median_v,
        "min_value": min_v,
        "max_value": max_v,
        "stddev_value": stddev_v,
        "zero_count": zero_count,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "unique_value_count": unique_count,
        "outlier_count": outlier_count,
        "extreme_positive_count": extreme_pos,
        "extreme_negative_count": extreme_neg,
        "distribution_status": status,
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# Symbol-level quality
# ---------------------------------------------------------------------------

def compute_symbol_quality(rows_json: list[dict], signal_column: str = "signal") -> list[dict]:
    """Compute per-symbol quality statistics from rows_json.

    Caps processing at 5000 rows. Returns list capped at 200 symbols,
    sorted worst-first (unusable → weak → review → clean).
    """
    rows = rows_json[:5000]
    from collections import defaultdict

    symbol_data = defaultdict(
        lambda: {"rows": [], "vals": [], "missing": 0, "non_num": 0, "timestamps": []}
    )
    for i, row in enumerate(rows):
        sym = str(
            row.get("symbol")
            or row.get("Symbol")
            or row.get("ticker")
            or "UNKNOWN"
        )
        v = row.get(signal_column)
        ts = str(
            row.get("timestamp")
            or row.get("date")
            or row.get("datetime")
            or ""
        )
        symbol_data[sym]["rows"].append(i)
        if v is None:
            symbol_data[sym]["missing"] += 1
        elif _safe_float(v) is not None:
            symbol_data[sym]["vals"].append(_safe_float(v))
        else:
            symbol_data[sym]["non_num"] += 1
        if ts:
            symbol_data[sym]["timestamps"].append(ts)

    STATUS_ORDER = {"unusable": 0, "weak": 1, "review": 2, "clean": 3}
    results = []
    for sym, d in symbol_data.items():
        row_count = len(d["rows"])
        vals = d["vals"]
        missing = d["missing"]
        missing_rate = round(missing / row_count, 4) if row_count > 0 else 0
        mean_v = round(sum(vals) / len(vals), 4) if vals else None
        stddev_v = None
        if len(vals) > 1:
            var = sum((v - mean_v) ** 2 for v in vals) / (len(vals) - 1)
            stddev_v = round(var ** 0.5, 4)
        ts_counts: dict = {}
        for t in d["timestamps"]:
            ts_counts[t] = ts_counts.get(t, 0) + 1
        dup_ts = sum(1 for c in ts_counts.values() if c > 1)
        lo, hi = _iqr_bounds(vals)
        outlier_count = (
            sum(1 for v in vals if lo is not None and (v < lo or v > hi))
            if lo is not None
            else 0
        )
        min_ts = min(d["timestamps"]) if d["timestamps"] else None
        max_ts = max(d["timestamps"]) if d["timestamps"] else None
        issues = []
        if missing_rate > 0.5:
            status = "unusable"
            issues.append(f"Missing rate {missing_rate:.1%}")
        elif missing_rate > 0.2:
            status = "weak"
            issues.append(f"Missing rate {missing_rate:.1%}")
        elif missing > 0 or outlier_count > 0 or dup_ts > 0:
            status = "review"
            if missing > 0:
                issues.append(f"{missing} missing")
            if outlier_count > 0:
                issues.append(f"{outlier_count} outliers")
            if dup_ts > 0:
                issues.append(f"{dup_ts} dup timestamps")
        else:
            status = "clean"
        results.append(
            {
                "symbol": sym,
                "row_count": row_count,
                "signal_value_count": len(vals),
                "missing_signal_count": missing,
                "missing_rate": missing_rate,
                "non_numeric_count": d["non_num"],
                "min_timestamp": min_ts,
                "max_timestamp": max_ts,
                "mean_value": mean_v,
                "stddev_value": stddev_v,
                "outlier_count": outlier_count,
                "duplicate_timestamp_count": dup_ts,
                "quality_status": status,
                "issues": issues,
            }
        )
    results.sort(key=lambda x: (STATUS_ORDER.get(x["quality_status"], 4), x["symbol"]))
    return results[:200]


# ---------------------------------------------------------------------------
# Timestamp coverage
# ---------------------------------------------------------------------------

def compute_timestamp_coverage(rows_json: list[dict]) -> dict:
    """Compute timestamp coverage statistics from rows_json.

    Caps processing at 5000 rows.
    """
    rows = rows_json[:5000]
    timestamps = []
    invalid_ts = 0
    seen_sym_ts: dict = {}
    dup_sym_ts = 0
    for row in rows:
        sym = row.get("symbol") or row.get("Symbol")
        ts = row.get("timestamp") or row.get("date") or row.get("datetime")
        if ts:
            ts_str = str(ts)
            timestamps.append(ts_str)
            try:
                _dt.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                if any(c.isdigit() for c in ts_str[:4]) and len(ts_str) >= 6:
                    invalid_ts += 1
            if sym:
                key = f"{sym}_{ts_str}"
                if key in seen_sym_ts:
                    dup_sym_ts += 1
                else:
                    seen_sym_ts[key] = True
    min_ts = min(timestamps) if timestamps else None
    max_ts = max(timestamps) if timestamps else None
    if invalid_ts > len(rows) * 0.2:
        status = "weak"
    elif invalid_ts > 0 or dup_sym_ts > 0:
        status = "review"
    else:
        status = "clean"
    return {
        "total_timestamp_count": len(timestamps),
        "duplicate_symbol_timestamp_count": dup_sym_ts,
        "invalid_timestamp_count": invalid_ts,
        "min_timestamp": min_ts,
        "max_timestamp": max_ts,
        "symbols_with_gaps_count": None,
        "timestamp_status": status,
    }


# ---------------------------------------------------------------------------
# Row quality samples
# ---------------------------------------------------------------------------

def compute_signal_row_quality_samples(
    rows_json: list[dict], signal_column: str = "signal"
) -> dict:
    """Detect and collect sample rows with quality issues.

    Caps processing at 5000 rows. Each sample bucket capped at 10 entries.
    """
    MAX = 10
    rows = rows_json[:5000]
    samples: dict = {
        k: []
        for k in [
            "missing_signal_rows",
            "non_numeric_signal_rows",
            "duplicate_symbol_timestamp_rows",
            "outlier_signal_rows",
            "invalid_timestamp_rows",
        ]
    }
    numeric_vals = [
        _safe_float(row.get(signal_column))
        for row in rows
        if _safe_float(row.get(signal_column)) is not None
    ]
    lo, hi = _iqr_bounds(numeric_vals)
    seen_sym_ts: dict = {}
    for i, row in enumerate(rows):
        sym = row.get("symbol") or row.get("Symbol")
        ts = row.get("timestamp") or row.get("date") or row.get("datetime")
        v = row.get(signal_column)
        sym_s = str(sym) if sym else None
        ts_s = str(ts) if ts else None
        fv = _safe_float(v)

        if v is None and len(samples["missing_signal_rows"]) < MAX:
            samples["missing_signal_rows"].append(
                {
                    "row_index": i,
                    "issue_type": "missing_signal",
                    "severity": "medium",
                    "symbol": sym_s,
                    "timestamp": ts_s,
                    "signal_value": None,
                    "evidence_json": {"symbol": sym, "timestamp": ts},
                    "summary": f"Missing signal for {sym} at {ts}",
                }
            )
        elif v is not None and fv is None and len(samples["non_numeric_signal_rows"]) < MAX:
            samples["non_numeric_signal_rows"].append(
                {
                    "row_index": i,
                    "issue_type": "non_numeric_signal",
                    "severity": "medium",
                    "symbol": sym_s,
                    "timestamp": ts_s,
                    "signal_value": str(v)[:30],
                    "evidence_json": {signal_column: str(v)[:30]},
                    "summary": f"Non-numeric: {str(v)[:20]}",
                }
            )
        if (
            fv is not None
            and lo is not None
            and (fv < lo or fv > hi)
            and len(samples["outlier_signal_rows"]) < MAX
        ):
            samples["outlier_signal_rows"].append(
                {
                    "row_index": i,
                    "issue_type": "outlier_signal",
                    "severity": "high",
                    "symbol": sym_s,
                    "timestamp": ts_s,
                    "signal_value": fv,
                    "evidence_json": {signal_column: fv, "symbol": sym},
                    "summary": f"Outlier: {sym} signal={fv:.4f}",
                }
            )
        if sym and ts:
            key = f"{sym}_{ts}"
            if key in seen_sym_ts and len(samples["duplicate_symbol_timestamp_rows"]) < MAX:
                samples["duplicate_symbol_timestamp_rows"].append(
                    {
                        "row_index": i,
                        "issue_type": "duplicate_symbol_timestamp",
                        "severity": "high",
                        "symbol": sym_s,
                        "timestamp": ts_s,
                        "signal_value": str(v) if v is not None else None,
                        "evidence_json": {"symbol": sym, "timestamp": ts},
                        "summary": f"Duplicate: {sym} at {ts}",
                    }
                )
            seen_sym_ts[key] = True
        if ts and isinstance(ts, str):
            try:
                _dt.fromisoformat(str(ts).replace("Z", "+00:00"))
            except ValueError:
                if (
                    any(c.isdigit() for c in str(ts)[:4])
                    and len(str(ts)) >= 6
                    and len(samples["invalid_timestamp_rows"]) < MAX
                ):
                    samples["invalid_timestamp_rows"].append(
                        {
                            "row_index": i,
                            "issue_type": "invalid_timestamp",
                            "severity": "medium",
                            "symbol": sym_s,
                            "timestamp": ts_s,
                            "signal_value": None,
                            "evidence_json": {"timestamp": str(ts)[:30]},
                            "summary": f"Invalid ts: {str(ts)[:20]}",
                        }
                    )
    return samples


# ---------------------------------------------------------------------------
# Quality summary
# ---------------------------------------------------------------------------

def compute_signal_quality_summary(
    rows_json: list[dict],
    dist: dict,
    sym_quality: list[dict],
    row_samples: dict,
) -> dict:
    """Aggregate quality summary from distribution, symbol quality, and row samples."""
    total_rows = len(rows_json)
    symbols = {
        str(row.get("symbol") or "") for row in rows_json if row.get("symbol")
    }
    clean = sum(1 for s in sym_quality if s["quality_status"] == "clean")
    review = sum(1 for s in sym_quality if s["quality_status"] == "review")
    weak = sum(1 for s in sym_quality if s["quality_status"] == "weak")
    unusable = sum(1 for s in sym_quality if s["quality_status"] == "unusable")
    worst = [
        s["symbol"]
        for s in sym_quality
        if s["quality_status"] in ("unusable", "weak", "review")
    ][:10]
    checks = []
    bad_sym = [s["symbol"] for s in sym_quality if s["missing_rate"] > 0.2]
    if bad_sym:
        checks.append(
            f"Review symbols with missing signal rate above 20%: {', '.join(bad_sym[:3])}."
        )
    if len(row_samples.get("duplicate_symbol_timestamp_rows", [])) > 0:
        checks.append("Inspect duplicate symbol/timestamp signal rows.")
    if dist.get("unique_value_count") == 1 and dist.get("value_count", 0) >= 10:
        checks.append("Confirm whether zero signal variance is expected.")
    if dist.get("outlier_count", 0) > 0:
        checks.append("Review outlier signal values before using this snapshot.")
    if len(row_samples.get("invalid_timestamp_rows", [])) > 0:
        checks.append("Validate timestamp parsing before linking this snapshot.")
    return {
        "total_rows": total_rows,
        "symbol_count": len(symbols),
        "signal_value_count": dist.get("value_count", 0),
        "missing_signal_count": dist.get("missing_count", 0),
        "non_numeric_signal_count": dist.get("non_numeric_count", 0),
        "outlier_count": dist.get("outlier_count", 0),
        "duplicate_symbol_timestamp_count": len(
            row_samples.get("duplicate_symbol_timestamp_rows", [])
        ),
        "invalid_timestamp_count": len(row_samples.get("invalid_timestamp_rows", [])),
        "clean_symbol_count": clean,
        "review_symbol_count": review,
        "weak_symbol_count": weak,
        "unusable_symbol_count": unusable,
        "worst_symbols": worst,
        "suggested_checks": checks,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_signal_quality_drilldown(snapshot, signal_column: str | None = None) -> dict:
    """Compute the full signal quality drilldown for a SignalSnapshot ORM object.

    Returns a dict with keys:
      signal_distribution, symbol_quality, timestamp_coverage, row_quality, quality_summary
    """
    rows = snapshot.rows_json or []
    meta = snapshot.metadata_json or {}
    sig_col = signal_column or meta.get("signal_column") or "signal"
    dist = compute_signal_distribution(rows, sig_col)
    sym_q = compute_symbol_quality(rows, sig_col)
    ts_cov = compute_timestamp_coverage(rows)
    row_q = compute_signal_row_quality_samples(rows, sig_col)
    summary = compute_signal_quality_summary(rows, dist, sym_q, row_q)
    return {
        "signal_distribution": dist,
        "symbol_quality": sym_q,
        "timestamp_coverage": ts_cov,
        "row_quality": row_q,
        "quality_summary": summary,
    }
