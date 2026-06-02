"""Dataset quality drill-down service for M37.

Computes column-level and row-level quality analysis from snapshot rows_json.
Pure Python — no database access, no AI, no causal claims.

This is a NEW service and does NOT modify data_quality.py.
"""

from __future__ import annotations

from datetime import datetime as _dt


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_float(v: object) -> float | None:
    """Return float if v is numeric-ish, else None."""
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _is_numeric(v: object) -> bool:
    """Return True if v is a numeric type (not bool)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ---------------------------------------------------------------------------
# Column quality
# ---------------------------------------------------------------------------

def compute_column_quality(rows_json: list[dict]) -> list[dict]:
    """Compute per-column quality statistics from rows_json.

    Caps processing at the first 1 000 rows for performance.
    Returns a list of dicts, one per column, ordered by first occurrence.
    """
    rows_json = rows_json[:1000]
    if not rows_json:
        return []

    # Collect all column names in order of first occurrence.
    seen_cols: dict[str, None] = {}
    for row in rows_json:
        for k in row.keys():
            seen_cols[k] = None
    all_cols = list(seen_cols.keys())

    results: list[dict] = []

    for col in all_cols:
        vals = [row.get(col) for row in rows_json]
        non_null = [v for v in vals if v is not None]
        null_count = len(vals) - len(non_null)
        null_rate = round(null_count / len(vals), 4) if vals else 0

        # Type classification
        numeric_vals = [float(v) for v in non_null if _is_numeric(v)]
        bool_vals = [v for v in non_null if isinstance(v, bool)]
        string_vals = [v for v in non_null if isinstance(v, str) and not isinstance(v, bool)]

        # Timestamp parsing check (cap at 100 string values)
        ts_parseable = 0
        ts_invalid = 0
        for v in string_vals[:100]:
            if len(str(v)) >= 8:
                try:
                    s = str(v).strip()
                    _dt.fromisoformat(s.replace("Z", "+00:00"))
                    ts_parseable += 1
                except (ValueError, AttributeError):
                    # Check if it looks like it should be a timestamp
                    sv = str(v)
                    if any(c.isdigit() for c in sv[:4]) and ("-" in sv or "/" in sv):
                        ts_invalid += 1

        # Inferred type
        if len(bool_vals) > max(len(numeric_vals), len(string_vals)):
            inferred_type = "boolean"
        elif len(numeric_vals) >= len(string_vals) and len(numeric_vals) > 0:
            inferred_type = "numeric"
        elif ts_parseable > len(string_vals) / 2 and ts_parseable > 3:
            inferred_type = "timestamp"
        elif string_vals:
            inferred_type = "string"
        else:
            inferred_type = "mixed"

        # Numeric stats
        min_v = max_v = mean_v = stddev_v = None
        zero_count = 0
        negative_count = 0
        outlier_count = 0
        if numeric_vals:
            min_v = round(min(numeric_vals), 4)
            max_v = round(max(numeric_vals), 4)
            mean_v = round(sum(numeric_vals) / len(numeric_vals), 4)
            if len(numeric_vals) > 1:
                var = sum((x - mean_v) ** 2 for x in numeric_vals) / (len(numeric_vals) - 1)
                stddev_v = round(var ** 0.5, 4)
            zero_count = sum(1 for v in numeric_vals if v == 0)
            negative_count = sum(1 for v in numeric_vals if v < 0)
            # IQR outlier detection (require >= 4 values)
            if len(numeric_vals) >= 4:
                sv_sorted = sorted(numeric_vals)
                n = len(sv_sorted)
                q1 = sv_sorted[n // 4]
                q3 = sv_sorted[(3 * n) // 4]
                iqr = q3 - q1
                if iqr > 0:
                    lo = q1 - 1.5 * iqr
                    hi = q3 + 1.5 * iqr
                    outlier_count = sum(1 for v in numeric_vals if v < lo or v > hi)

        # Unique and duplicate counts
        unique_vals = list(dict.fromkeys(str(v) for v in non_null))
        unique_count = len(unique_vals)
        dup_count = len(non_null) - unique_count
        sample_values = unique_vals[:5]

        # Quality status
        issues: list[str] = []
        if null_rate > 0.5:
            status = "unusable"
            issues.append(f"Null rate {null_rate:.1%} exceeds 50%")
        elif null_rate > 0.2:
            status = "weak"
            issues.append(f"Null rate {null_rate:.1%} exceeds 20%")
        elif null_count > 0 or outlier_count > 0 or ts_invalid > 0:
            status = "review"
            if null_count > 0:
                issues.append(f"{null_count} null value(s)")
            if outlier_count > 0:
                issues.append(f"{outlier_count} outlier(s)")
            if ts_invalid > 0:
                issues.append(f"{ts_invalid} invalid timestamp format(s)")
        else:
            status = "clean"

        col_result = {
            "column_name": col,
            "inferred_type": inferred_type,
            "non_null_count": len(non_null),
            "null_count": null_count,
            "null_rate": null_rate,
            "unique_count": unique_count,
            "duplicate_value_count": dup_count,
            "numeric_count": len(numeric_vals),
            "string_count": len(string_vals),
            "boolean_count": len(bool_vals),
            "timestamp_parseable_count": ts_parseable,
            "invalid_timestamp_count": ts_invalid,
            "min_value": min_v,
            "max_value": max_v,
            "mean_value": mean_v,
            "stddev_value": stddev_v,
            "zero_count": zero_count,
            "negative_count": negative_count,
            "outlier_count": outlier_count,
            "sample_values": sample_values,
            "quality_status": status,
            "issues": issues,
        }
        results.append(col_result)

    return results


# ---------------------------------------------------------------------------
# Row quality samples
# ---------------------------------------------------------------------------

def compute_row_quality_samples(rows_json: list[dict]) -> dict:
    """Identify and sample problematic rows from rows_json.

    Caps processing at the first 1 000 rows.
    Returns a dict with up to 10 samples per category.
    """
    MAX = 10
    rows = rows_json[:1000]

    samples: dict[str, list[dict]] = {
        k: []
        for k in [
            "duplicate_rows",
            "duplicate_symbol_timestamp",
            "invalid_timestamp_rows",
            "invalid_ohlc_rows",
            "suspicious_return_rows",
            "missing_value_rows",
            "outlier_rows",
        ]
    }

    # Duplicate rows
    seen_rows: dict[str, int] = {}
    for i, row in enumerate(rows):
        k = str(sorted((k2, str(v)) for k2, v in row.items()))
        if k in seen_rows:
            if len(samples["duplicate_rows"]) < MAX:
                samples["duplicate_rows"].append({
                    "row_index": i,
                    "issue_type": "duplicate_row",
                    "severity": "medium",
                    "evidence_json": {k2: v for k2, v in list(row.items())[:6]},
                    "summary": f"Row {i} duplicates row {seen_rows[k]}",
                })
        else:
            seen_rows[k] = i

    # Duplicate symbol + timestamp
    seen_st: dict[str, int] = {}
    for i, row in enumerate(rows):
        sym = row.get("symbol") or row.get("ticker") or row.get("Symbol")
        ts = (
            row.get("timestamp")
            or row.get("date")
            or row.get("datetime")
            or row.get("Date")
        )
        if sym and ts:
            k = f"{sym}_{ts}"
            if k in seen_st:
                if len(samples["duplicate_symbol_timestamp"]) < MAX:
                    samples["duplicate_symbol_timestamp"].append({
                        "row_index": i,
                        "issue_type": "duplicate_symbol_timestamp",
                        "severity": "high",
                        "evidence_json": {"symbol": sym, "timestamp": str(ts)},
                        "summary": f"Duplicate: {sym} at {ts}",
                    })
            else:
                seen_st[k] = i

    # Invalid timestamps
    for i, row in enumerate(rows):
        for tc in ["timestamp", "date", "datetime", "Date", "Timestamp"]:
            val = row.get(tc)
            if val and isinstance(val, str):
                try:
                    _dt.fromisoformat(str(val).replace("Z", "+00:00"))
                except ValueError:
                    sv = str(val)
                    if any(c.isdigit() for c in sv[:4]) and len(sv) >= 6:
                        if len(samples["invalid_timestamp_rows"]) < MAX:
                            samples["invalid_timestamp_rows"].append({
                                "row_index": i,
                                "issue_type": "invalid_timestamp",
                                "severity": "medium",
                                "evidence_json": {tc: sv[:30]},
                                "summary": f"Invalid timestamp in {tc}: {sv[:20]}",
                            })
                        break

    # Invalid OHLC
    for i, row in enumerate(rows):
        o = _safe_float(row.get("open") or row.get("Open"))
        h = _safe_float(row.get("high") or row.get("High"))
        lo = _safe_float(row.get("low") or row.get("Low"))
        c = _safe_float(row.get("close") or row.get("Close"))
        if all(v is not None for v in [o, h, lo, c]):
            # Mypy-safe: we know these are floats at this point
            assert h is not None and lo is not None and o is not None and c is not None
            if h < max(o, c) or lo > min(o, c) or h < lo:
                if len(samples["invalid_ohlc_rows"]) < MAX:
                    samples["invalid_ohlc_rows"].append({
                        "row_index": i,
                        "issue_type": "invalid_ohlc",
                        "severity": "high",
                        "evidence_json": {"open": o, "high": h, "low": lo, "close": c},
                        "summary": f"OHLC inconsistency at row {i}",
                    })

    # Suspicious returns (>50% move)
    prev_c: float | None = None
    for i, row in enumerate(rows):
        c = _safe_float(
            row.get("close") or row.get("Close") or row.get("price")
        )
        if c and prev_c and prev_c != 0:
            pct = abs(c - prev_c) / abs(prev_c)
            if pct > 0.5:
                if len(samples["suspicious_return_rows"]) < MAX:
                    samples["suspicious_return_rows"].append({
                        "row_index": i,
                        "issue_type": "suspicious_return",
                        "severity": "high",
                        "evidence_json": {
                            "close": c,
                            "prev_close": prev_c,
                            "pct_change": round(pct, 4),
                        },
                        "summary": f"Large price move at row {i}: {pct:.1%}",
                    })
        if c:
            prev_c = c

    # Missing value rows
    for i, row in enumerate(rows):
        null_cols = [k for k, v in row.items() if v is None]
        if null_cols and len(samples["missing_value_rows"]) < MAX:
            samples["missing_value_rows"].append({
                "row_index": i,
                "issue_type": "missing_values",
                "severity": "medium",
                "evidence_json": {"null_columns": null_cols[:5]},
                "summary": f"Nulls in: {', '.join(null_cols[:3])}",
            })

    return samples


# ---------------------------------------------------------------------------
# Quality summary
# ---------------------------------------------------------------------------

def compute_quality_summary(
    rows_json: list[dict],
    col_quality: list[dict],
    row_samples: dict,
) -> dict:
    """Compute an aggregate quality summary from column and row analyses."""
    total_rows = len(rows_json)
    total_cols = len(col_quality)
    clean = sum(1 for c in col_quality if c["quality_status"] == "clean")
    review = sum(1 for c in col_quality if c["quality_status"] == "review")
    weak = sum(1 for c in col_quality if c["quality_status"] == "weak")
    unusable = sum(1 for c in col_quality if c["quality_status"] == "unusable")
    total_missing = sum(c["null_count"] for c in col_quality)
    total_outliers = sum(c["outlier_count"] for c in col_quality)
    total_invalid_ts = sum(c["invalid_timestamp_count"] for c in col_quality)
    total_dup_rows = len(row_samples.get("duplicate_rows", []))
    total_dup_st = len(row_samples.get("duplicate_symbol_timestamp", []))

    worst = [
        c["column_name"]
        for c in sorted(
            col_quality,
            key=lambda c: (
                0 if c["quality_status"] == "unusable"
                else 1 if c["quality_status"] == "weak"
                else 2,
                -c["null_rate"],
            ),
        )[:10]
    ]

    checks: list[str] = []
    hn = [c["column_name"] for c in col_quality if c["null_rate"] > 0.2]
    if hn:
        checks.append(
            f"Review columns with null rate above 20%: {', '.join(hn[:3])}."
        )
    if total_invalid_ts > 0:
        checks.append("Validate timestamp parsing before backtesting.")
    if row_samples.get("invalid_ohlc_rows"):
        checks.append(
            "Inspect OHLC rows where close is outside high/low range."
        )
    if row_samples.get("suspicious_return_rows"):
        checks.append(
            "Review suspicious price moves before using this snapshot."
        )
    if total_dup_st > 0:
        checks.append("Resolve duplicate symbol+timestamp combinations.")
    if total_outliers > 0:
        checks.append(
            f"Review {total_outliers} outlier value(s) across numeric columns."
        )

    return {
        "total_rows": total_rows,
        "total_columns": total_cols,
        "clean_column_count": clean,
        "review_column_count": review,
        "weak_column_count": weak,
        "unusable_column_count": unusable,
        "total_missing_values": total_missing,
        "total_outliers": total_outliers,
        "total_invalid_timestamps": total_invalid_ts,
        "total_duplicate_rows": total_dup_rows,
        "total_duplicate_symbol_timestamps": total_dup_st,
        "worst_columns": worst,
        "suggested_checks": checks,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_dataset_quality_drilldown(snapshot: object, db: object = None) -> dict:
    """Compute full quality drill-down for a DatasetSnapshot.

    Args:
        snapshot: DatasetSnapshot ORM instance (must have rows_json attribute).
        db: unused, kept for API consistency.

    Returns:
        dict with keys: column_quality, row_quality, quality_summary.
    """
    rows: list[dict] = getattr(snapshot, "rows_json", None) or []
    col_quality = compute_column_quality(rows)
    row_samples = compute_row_quality_samples(rows)
    summary = compute_quality_summary(rows, col_quality, row_samples)
    return {
        "column_quality": col_quality,
        "row_quality": row_samples,
        "quality_summary": summary,
    }
