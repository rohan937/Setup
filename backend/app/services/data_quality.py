"""Deterministic data quality analysis for dataset snapshots.

Pure Python — no database access, no AI, no causal claims.

Checks performed (OHLCV-focused, gracefully skipped if fields absent):
  1. missing_values          — null/missing OHLCV fields in any row
  2. duplicate_rows          — exact duplicate rows
  3. duplicate_symbol_timestamp — same (symbol, timestamp) pair more than once
  4. invalid_timestamp       — unparseable timestamp field
  5. negative_zero_price     — open / high / low / close <= 0
  6. high_lt_low             — high < low in the same row
  7. close_outside_range     — close < low or close > high
  8. open_outside_range      — open < low or open > high
  9. negative_volume         — volume < 0
 10. suspicious_return_jump  — |return| > 25 % (medium) or > 50 % (high)
                               between consecutive rows per symbol

Health score formula:
  Start at 100; subtract per-issue penalty:
    critical → 25, high → 15, medium → 8, low → 3
  Minimum 0.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.constants import IssueType, Severity

# OHLCV fields that should always be present.
_PRICE_FIELDS = ("open", "high", "low", "close")
_OHLCV_FIELDS = ("symbol", "timestamp", "open", "high", "low", "close", "volume")

_SEVERITY_PENALTY: dict[str, int] = {
    Severity.critical: 25,
    Severity.high: 15,
    Severity.medium: 8,
    Severity.low: 3,
    Severity.info: 0,
}


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------

@dataclass
class IssueSpec:
    """A single deterministic data quality finding."""

    issue_type: str
    severity: str
    field_name: str | None = None
    row_index: int | None = None
    detail: str | None = None


@dataclass
class SnapshotSummary:
    """Result of analyze_snapshot()."""

    issues: list[IssueSpec] = field(default_factory=list)
    health_score: int = 100
    row_count: int = 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _try_parse_float(v: object) -> float | None:
    """Return float if v is numeric-ish, else None."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except (ValueError, TypeError):
            pass
    return None


def _try_parse_ts(v: object) -> datetime | None:
    """Return a datetime if v can be parsed, else None."""
    if isinstance(v, datetime):
        return v
    if not isinstance(v, str):
        return None
    # Try ISO 8601 variants.
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    # Fallback to fromisoformat (Python 3.11+ handles more cases).
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        pass
    return None


def _compute_health_score(issues: list[IssueSpec]) -> int:
    """Subtract per-issue penalties from 100, floor at 0."""
    penalty = sum(_SEVERITY_PENALTY.get(iss.severity, 0) for iss in issues)
    return max(0, 100 - penalty)


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------

def _check_missing_values(rows: list[dict]) -> list[IssueSpec]:
    """One issue per row that has null / missing OHLCV fields."""
    issues: list[IssueSpec] = []
    for i, row in enumerate(rows):
        missing = [f for f in _OHLCV_FIELDS if row.get(f) is None]
        if not missing:
            continue
        # Higher severity when identifier fields are missing.
        critical_missing = [f for f in ("symbol", "timestamp") if f in missing]
        severity = Severity.high if critical_missing else Severity.medium
        issues.append(IssueSpec(
            issue_type=IssueType.missing_values,
            severity=severity,
            row_index=i,
            detail=f"Row {i}: missing fields: {', '.join(missing)}",
        ))
    return issues


def _check_duplicate_rows(rows: list[dict]) -> list[IssueSpec]:
    """Flag rows that are exact duplicates (all fields equal)."""
    issues: list[IssueSpec] = []
    # Use a JSON-serialised canonical key so dict comparison is order-independent.
    seen: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        key = json.dumps(row, sort_keys=True, default=str)
        seen.setdefault(key, []).append(i)
    for indices in seen.values():
        if len(indices) > 1:
            issues.append(IssueSpec(
                issue_type=IssueType.duplicate_rows,
                severity=Severity.medium,
                row_index=indices[0],
                detail=f"Exact duplicate rows at indices: {indices}",
            ))
    return issues


def _check_duplicate_symbol_timestamp(rows: list[dict]) -> list[IssueSpec]:
    """Flag rows sharing the same (symbol, timestamp) pair."""
    issues: list[IssueSpec] = []
    seen: dict[tuple, list[int]] = {}
    for i, row in enumerate(rows):
        sym = row.get("symbol")
        ts = row.get("timestamp")
        if sym is None or ts is None:
            continue
        key = (str(sym), str(ts))
        seen.setdefault(key, []).append(i)
    for (sym, ts), indices in seen.items():
        if len(indices) > 1:
            issues.append(IssueSpec(
                issue_type=IssueType.duplicate_symbol_timestamp,
                severity=Severity.high,
                row_index=indices[0],
                detail=(
                    f"symbol={sym!r} timestamp={ts!r} appears at indices: {indices}"
                ),
            ))
    return issues


def _check_invalid_timestamps(rows: list[dict]) -> list[IssueSpec]:
    """Flag rows where 'timestamp' cannot be parsed as a date/datetime."""
    issues: list[IssueSpec] = []
    for i, row in enumerate(rows):
        ts_val = row.get("timestamp")
        if ts_val is None:
            continue  # handled by missing_values
        if _try_parse_ts(ts_val) is None:
            issues.append(IssueSpec(
                issue_type=IssueType.invalid_timestamp,
                severity=Severity.high,
                field_name="timestamp",
                row_index=i,
                detail=f"Row {i}: cannot parse timestamp value {ts_val!r}",
            ))
    return issues


def _check_negative_zero_prices(rows: list[dict]) -> list[IssueSpec]:
    """Flag rows where any OHLC field is <= 0."""
    issues: list[IssueSpec] = []
    for i, row in enumerate(rows):
        for f in _PRICE_FIELDS:
            val = _try_parse_float(row.get(f))
            if val is not None and val <= 0:
                issues.append(IssueSpec(
                    issue_type=IssueType.negative_zero_price,
                    severity=Severity.critical,
                    field_name=f,
                    row_index=i,
                    detail=f"Row {i}: {f}={val} is <= 0",
                ))
    return issues


def _check_high_lt_low(rows: list[dict]) -> list[IssueSpec]:
    """Flag rows where high < low."""
    issues: list[IssueSpec] = []
    for i, row in enumerate(rows):
        high = _try_parse_float(row.get("high"))
        low = _try_parse_float(row.get("low"))
        if high is not None and low is not None and high < low:
            issues.append(IssueSpec(
                issue_type=IssueType.high_lt_low,
                severity=Severity.critical,
                row_index=i,
                detail=f"Row {i}: high={high} < low={low}",
            ))
    return issues


def _check_close_outside_range(rows: list[dict]) -> list[IssueSpec]:
    """Flag rows where close < low or close > high."""
    issues: list[IssueSpec] = []
    for i, row in enumerate(rows):
        high = _try_parse_float(row.get("high"))
        low = _try_parse_float(row.get("low"))
        close = _try_parse_float(row.get("close"))
        if high is None or low is None or close is None:
            continue
        if close < low or close > high:
            issues.append(IssueSpec(
                issue_type=IssueType.close_outside_range,
                severity=Severity.high,
                field_name="close",
                row_index=i,
                detail=f"Row {i}: close={close} outside [low={low}, high={high}]",
            ))
    return issues


def _check_open_outside_range(rows: list[dict]) -> list[IssueSpec]:
    """Flag rows where open < low or open > high."""
    issues: list[IssueSpec] = []
    for i, row in enumerate(rows):
        high = _try_parse_float(row.get("high"))
        low = _try_parse_float(row.get("low"))
        open_ = _try_parse_float(row.get("open"))
        if high is None or low is None or open_ is None:
            continue
        if open_ < low or open_ > high:
            issues.append(IssueSpec(
                issue_type=IssueType.open_outside_range,
                severity=Severity.medium,
                field_name="open",
                row_index=i,
                detail=f"Row {i}: open={open_} outside [low={low}, high={high}]",
            ))
    return issues


def _check_negative_volume(rows: list[dict]) -> list[IssueSpec]:
    """Flag rows where volume < 0."""
    issues: list[IssueSpec] = []
    for i, row in enumerate(rows):
        vol = _try_parse_float(row.get("volume"))
        if vol is not None and vol < 0:
            issues.append(IssueSpec(
                issue_type=IssueType.negative_volume,
                severity=Severity.medium,
                field_name="volume",
                row_index=i,
                detail=f"Row {i}: volume={vol} is negative",
            ))
    return issues


def _check_suspicious_return_jumps(rows: list[dict]) -> list[IssueSpec]:
    """Flag consecutive close-to-close returns > 25% (medium) or > 50% (high).

    Groups rows by symbol, sorts by timestamp within each group.
    Skipped when close or timestamp is unavailable or unparseable.
    """
    issues: list[IssueSpec] = []

    # Build per-symbol lists of (timestamp, close, original_index).
    by_symbol: dict[str, list[tuple[datetime, float, int]]] = {}
    for i, row in enumerate(rows):
        sym = row.get("symbol")
        if sym is None:
            continue
        ts = _try_parse_ts(row.get("timestamp"))
        close = _try_parse_float(row.get("close"))
        if ts is None or close is None or close <= 0:
            continue
        by_symbol.setdefault(str(sym), []).append((ts, close, i))

    for sym, entries in by_symbol.items():
        entries.sort(key=lambda t: t[0])
        for j in range(1, len(entries)):
            _, prev_close, prev_idx = entries[j - 1]
            ts_b, curr_close, curr_idx = entries[j]
            abs_return = abs((curr_close - prev_close) / prev_close)
            if abs_return > 0.50:
                severity = Severity.high
            elif abs_return > 0.25:
                severity = Severity.medium
            else:
                continue
            pct = round(abs_return * 100, 1)
            issues.append(IssueSpec(
                issue_type=IssueType.suspicious_return_jump,
                severity=severity,
                field_name="close",
                row_index=curr_idx,
                detail=(
                    f"Row {curr_idx}: symbol={sym!r} close-to-close return "
                    f"noted as {pct}% (prev_row={prev_idx})"
                ),
            ))
    return issues


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_snapshot(rows: list[dict]) -> SnapshotSummary:
    """Run all data quality checks on a list of row dicts.

    Returns a SnapshotSummary with all detected issues and the computed
    health score.  Pure function — no side effects.
    """
    all_issues: list[IssueSpec] = []
    all_issues.extend(_check_missing_values(rows))
    all_issues.extend(_check_duplicate_rows(rows))
    all_issues.extend(_check_duplicate_symbol_timestamp(rows))
    all_issues.extend(_check_invalid_timestamps(rows))
    all_issues.extend(_check_negative_zero_prices(rows))
    all_issues.extend(_check_high_lt_low(rows))
    all_issues.extend(_check_close_outside_range(rows))
    all_issues.extend(_check_open_outside_range(rows))
    all_issues.extend(_check_negative_volume(rows))
    all_issues.extend(_check_suspicious_return_jumps(rows))

    health = _compute_health_score(all_issues)
    return SnapshotSummary(
        issues=all_issues,
        health_score=health,
        row_count=len(rows),
    )
