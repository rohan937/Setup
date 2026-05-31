"""Deterministic dataset snapshot comparison service — M12.

Compares two DatasetSnapshot records from the same dataset across six dimensions:

  A. Metadata        — row counts, labels
  B. Schema          — added/removed/type-changed columns
  C. Symbol coverage — added/removed symbols
  D. Timestamp range — min/max timestamp changes, date range delta
  E. Data health     — health score, issue count, severity, issue types
  F. Value revisions — row-level OHLCV diffs keyed by (symbol, timestamp)

Design rules:
  - Pure Python — no database access, no AI, no causal claims.
  - Language: "noted as changed", "may affect", "requires review", "observed".
  - Never "caused", "because", "therefore", "corrupted".
  - Row examples capped at MAX_EXAMPLES (20) to avoid huge payloads.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.data_quality_issue import DataQualityIssue
from app.models.dataset_snapshot import DatasetSnapshot
from app.schemas.dataset_comparison import (
    DataHealthComparison,
    DatasetSnapshotComparisonResponse,
    MetadataComparison,
    SchemaComparison,
    SymbolCoverageComparison,
    TimestampCoverageComparison,
    TypeChange,
    ValueRevisionExample,
    ValueRevisionsComparison,
)

# OHLCV numeric fields tracked in value revisions.
_OHLCV_FIELDS = ("open", "high", "low", "close", "volume")

# Severity ordering for worst-severity comparisons.
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

# Maximum number of row examples returned in the value_revisions section.
MAX_EXAMPLES = 20


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------

def _infer_type(values: list[Any]) -> str:
    """Infer a simple type label from a sample of non-null values.

    Returns one of: "number", "boolean", "string", "null", "mixed".
    """
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "null"
    types: set[str] = set()
    for v in non_null:
        if isinstance(v, bool):
            types.add("boolean")
        elif isinstance(v, (int, float)):
            types.add("number")
        else:
            types.add("string")
    if len(types) == 1:
        return next(iter(types))
    return "mixed"


def _extract_columns(rows: list[dict]) -> dict[str, str]:
    """Return {column: inferred_type} for all columns seen across all rows."""
    if not rows:
        return {}
    col_values: dict[str, list[Any]] = {}
    for row in rows:
        for k, v in row.items():
            col_values.setdefault(k, []).append(v)
    return {col: _infer_type(vals) for col, vals in col_values.items()}


# ---------------------------------------------------------------------------
# Symbol extraction
# ---------------------------------------------------------------------------

def _extract_symbols(rows: list[dict]) -> set[str]:
    """Return the set of unique symbol values present in the rows."""
    symbols: set[str] = set()
    for row in rows:
        sym = row.get("symbol")
        if sym is not None:
            symbols.add(str(sym))
    return symbols


# ---------------------------------------------------------------------------
# Timestamp extraction
# ---------------------------------------------------------------------------

def _try_parse_ts(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v
    if not isinstance(v, str):
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None


def _extract_timestamp_range(rows: list[dict]) -> tuple[str | None, str | None]:
    """Return (min_timestamp, max_timestamp) as ISO strings, or (None, None)."""
    timestamps: list[datetime] = []
    for row in rows:
        ts = _try_parse_ts(row.get("timestamp"))
        if ts is not None:
            timestamps.append(ts)
    if not timestamps:
        return None, None
    min_ts = min(timestamps)
    max_ts = max(timestamps)
    return min_ts.strftime("%Y-%m-%d"), max_ts.strftime("%Y-%m-%d")


def _date_range_days(min_ts: str | None, max_ts: str | None) -> int | None:
    """Return the inclusive calendar-day span, or None if either end is missing."""
    if min_ts is None or max_ts is None:
        return None
    t0 = _try_parse_ts(min_ts)
    t1 = _try_parse_ts(max_ts)
    if t0 is None or t1 is None:
        return None
    return max(0, (t1 - t0).days + 1)


# ---------------------------------------------------------------------------
# Value revision helpers
# ---------------------------------------------------------------------------

def _row_key(row: dict) -> str | None:
    """Return a stable (symbol, timestamp) composite key, or None if unavailable."""
    sym = row.get("symbol")
    ts = row.get("timestamp")
    if sym is not None and ts is not None:
        return f"{sym}\x00{ts}"
    return None


def _row_hash(row: dict) -> str:
    """SHA-256 of the canonical JSON representation of a row."""
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, default=str).encode()
    ).hexdigest()


def _try_float(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _build_revision_example(
    sym: str | None,
    ts: str | None,
    change_type: str,
    row_a: dict | None,
    row_b: dict | None,
) -> ValueRevisionExample:
    """Build a single value revision example."""
    changed_fields: list[str] = []
    field_deltas: dict[str, float] = {}

    if change_type == "changed" and row_a is not None and row_b is not None:
        all_keys = sorted(set(row_a) | set(row_b))
        for k in all_keys:
            v_a = row_a.get(k)
            v_b = row_b.get(k)
            if v_a != v_b:
                changed_fields.append(k)
                # Compute numeric delta for OHLCV fields only.
                if k in _OHLCV_FIELDS:
                    fa = _try_float(v_a)
                    fb = _try_float(v_b)
                    if fa is not None and fb is not None:
                        field_deltas[k] = round(fb - fa, 8)

    # Extract OHLCV subsets for display.
    def _ohlcv_subset(row: dict | None) -> dict | None:
        if row is None:
            return None
        return {k: row[k] for k in _OHLCV_FIELDS if k in row}

    return ValueRevisionExample(
        symbol=sym,
        timestamp=ts,
        change_type=change_type,
        old_values=_ohlcv_subset(row_a),
        new_values=_ohlcv_subset(row_b),
        changed_fields=changed_fields,
        field_deltas=field_deltas,
    )


def _compare_rows(
    rows_a: list[dict],
    rows_b: list[dict],
) -> ValueRevisionsComparison:
    """Compare row lists; prefer (symbol, timestamp) keyed diff, fall back to hashing."""
    has_a = bool(rows_a)
    has_b = bool(rows_b)

    if not has_a and not has_b:
        return ValueRevisionsComparison(
            rows_available_a=False, rows_available_b=False,
            keyed_comparison_available=False,
            added_rows_count=0, removed_rows_count=0, changed_rows_count=0,
            examples=[], total_examples_capped=False, max_examples=MAX_EXAMPLES,
        )

    # Build key→row maps; detect whether (symbol, timestamp) keying is usable.
    def _keyed_index(rows: list[dict]) -> tuple[dict[str, dict], bool]:
        idx: dict[str, dict] = {}
        keyed_count = 0
        for row in rows:
            k = _row_key(row)
            if k is not None:
                idx[k] = row
                keyed_count += 1
        all_keyed = keyed_count == len(rows)
        return idx, all_keyed

    idx_a, all_keyed_a = _keyed_index(rows_a) if has_a else ({}, True)
    idx_b, all_keyed_b = _keyed_index(rows_b) if has_b else ({}, True)
    keyed_available = all_keyed_a and all_keyed_b and (has_a or has_b)

    added_count = removed_count = changed_count = 0
    examples: list[ValueRevisionExample] = []

    if keyed_available:
        keys_a = set(idx_a)
        keys_b = set(idx_b)

        removed_keys = keys_a - keys_b
        added_keys = keys_b - keys_a
        common_keys = keys_a & keys_b

        removed_count = len(removed_keys)
        added_count = len(added_keys)

        for key in sorted(common_keys):
            row_a = idx_a[key]
            row_b = idx_b[key]
            if row_a != row_b:
                changed_count += 1

        def _parse_key(k: str) -> tuple[str | None, str | None]:
            parts = k.split("\x00", 1)
            return (parts[0], parts[1]) if len(parts) == 2 else (None, None)

        # Collect examples: added, removed, changed (priority order).
        for key in sorted(added_keys):
            if len(examples) >= MAX_EXAMPLES:
                break
            sym, ts = _parse_key(key)
            examples.append(_build_revision_example(sym, ts, "added", None, idx_b[key]))

        for key in sorted(removed_keys):
            if len(examples) >= MAX_EXAMPLES:
                break
            sym, ts = _parse_key(key)
            examples.append(_build_revision_example(sym, ts, "removed", idx_a[key], None))

        for key in sorted(common_keys):
            if len(examples) >= MAX_EXAMPLES:
                break
            row_a = idx_a[key]
            row_b = idx_b[key]
            if row_a != row_b:
                sym, ts = _parse_key(key)
                examples.append(_build_revision_example(sym, ts, "changed", row_a, row_b))

    else:
        # Hash-based fallback: no per-field detail, just counts.
        hashes_a: set[str] = {_row_hash(r) for r in rows_a}
        hashes_b: set[str] = {_row_hash(r) for r in rows_b}
        added_count = len(hashes_b - hashes_a)
        removed_count = len(hashes_a - hashes_b)
        # No changed_count since without keys we can't correlate rows.

    total_examples = added_count + removed_count + changed_count
    capped = total_examples > MAX_EXAMPLES

    return ValueRevisionsComparison(
        rows_available_a=has_a,
        rows_available_b=has_b,
        keyed_comparison_available=keyed_available,
        added_rows_count=added_count,
        removed_rows_count=removed_count,
        changed_rows_count=changed_count,
        examples=examples,
        total_examples_capped=capped,
        max_examples=MAX_EXAMPLES,
    )


# ---------------------------------------------------------------------------
# Highlighted changes + explanation
# ---------------------------------------------------------------------------

def _build_highlighted_changes(
    meta: MetadataComparison,
    schema_diff: SchemaComparison,
    sym_cov: SymbolCoverageComparison,
    ts_cov: TimestampCoverageComparison,
    health: DataHealthComparison,
    revisions: ValueRevisionsComparison,
) -> list[str]:
    """Return human-readable bullet strings for the most notable changes."""
    highlights: list[str] = []

    # Row count
    if meta.row_count_delta != 0:
        direction = "increased" if meta.row_count_delta > 0 else "decreased"
        highlights.append(
            f"row_count {direction} from {meta.row_count_a:,} to "
            f"{meta.row_count_b:,} ({meta.row_count_delta:+,} rows)"
        )

    # Schema: added/removed columns
    if schema_diff.added_columns:
        cols = ", ".join(schema_diff.added_columns[:5])
        extra = f" (and {len(schema_diff.added_columns) - 5} more)" if len(schema_diff.added_columns) > 5 else ""
        highlights.append(
            f"{len(schema_diff.added_columns)} column(s) added: {cols}{extra}"
        )
    if schema_diff.removed_columns:
        cols = ", ".join(schema_diff.removed_columns[:5])
        extra = f" (and {len(schema_diff.removed_columns) - 5} more)" if len(schema_diff.removed_columns) > 5 else ""
        highlights.append(
            f"{len(schema_diff.removed_columns)} column(s) removed: {cols}{extra}"
        )
    if schema_diff.type_changes:
        for tc in schema_diff.type_changes[:3]:
            highlights.append(
                f"column '{tc.column}' type changed from {tc.type_a!r} to {tc.type_b!r}"
            )

    # Symbol coverage
    if sym_cov.keyed_by_symbol:
        if sym_cov.added_symbols:
            examples = ", ".join(sym_cov.added_symbols[:3])
            more = f" (+{len(sym_cov.added_symbols) - 3} more)" if len(sym_cov.added_symbols) > 3 else ""
            highlights.append(f"{len(sym_cov.added_symbols)} symbol(s) added: {examples}{more}")
        if sym_cov.removed_symbols:
            examples = ", ".join(sym_cov.removed_symbols[:3])
            more = f" (+{len(sym_cov.removed_symbols) - 3} more)" if len(sym_cov.removed_symbols) > 3 else ""
            highlights.append(f"{len(sym_cov.removed_symbols)} symbol(s) removed: {examples}{more}")

    # Timestamp range
    if ts_cov.min_changed and ts_cov.min_timestamp_a and ts_cov.min_timestamp_b:
        highlights.append(
            f"earliest timestamp changed from {ts_cov.min_timestamp_a} to {ts_cov.min_timestamp_b}"
        )
    if ts_cov.max_changed and ts_cov.max_timestamp_a and ts_cov.max_timestamp_b:
        highlights.append(
            f"latest timestamp changed from {ts_cov.max_timestamp_a} to {ts_cov.max_timestamp_b}"
        )
    if ts_cov.date_range_days_delta is not None and ts_cov.date_range_days_delta != 0:
        direction = "expanded" if ts_cov.date_range_days_delta > 0 else "shrunk"
        highlights.append(
            f"date range {direction} by {abs(ts_cov.date_range_days_delta)} day(s)"
        )

    # Data health
    if health.health_score_delta != 0:
        direction = "improved" if health.health_score_delta > 0 else "decreased"
        highlights.append(
            f"health_score {direction} from {health.health_score_a} to "
            f"{health.health_score_b} ({health.health_score_delta:+d})"
        )
    if health.issue_count_delta != 0:
        direction = "increased" if health.issue_count_delta > 0 else "decreased"
        highlights.append(
            f"data quality issue count {direction} from {health.issue_count_a} to "
            f"{health.issue_count_b}"
        )

    # Value revisions
    if revisions.keyed_comparison_available:
        total_row_changes = (
            revisions.added_rows_count
            + revisions.removed_rows_count
            + revisions.changed_rows_count
        )
        if total_row_changes > 0:
            highlights.append(
                f"{total_row_changes:,} keyed row(s) changed "
                f"({revisions.added_rows_count} added, "
                f"{revisions.removed_rows_count} removed, "
                f"{revisions.changed_rows_count} revised)"
            )
        # Surface notable OHLCV field examples
        for ex in revisions.examples[:3]:
            if ex.change_type == "changed" and ex.field_deltas and ex.symbol and ex.timestamp:
                for field, delta in list(ex.field_deltas.items())[:1]:
                    old_v = (ex.old_values or {}).get(field)
                    new_v = (ex.new_values or {}).get(field)
                    if old_v is not None and new_v is not None:
                        highlights.append(
                            f"{ex.symbol} {field} changed on {ex.timestamp} "
                            f"from {old_v} to {new_v}"
                        )

    return highlights


def _build_explanation(
    highlighted: list[str],
    total_changes: int,
    is_same_snapshot: bool,
) -> str:
    tail = (
        "This is a deterministic comparison of ingested row data — "
        "changes are noted as observed facts and may affect strategy results "
        "if used in backtests; the comparison does not claim causality."
    )
    if is_same_snapshot:
        return "Snapshot A and Snapshot B are the same snapshot. No changes to report."
    if total_changes == 0:
        return (
            "Snapshot B is structurally identical to Snapshot A: same row count, "
            "same columns, same symbols, same timestamp range, and the same health score. "
            "No changes were detected."
        )
    if not highlighted:
        return (
            f"Snapshot B differs from Snapshot A in {total_changes} tracked dimension(s). "
            f"No key structural changes were detected in the highlighted categories. {tail}"
        )
    if len(highlighted) == 1:
        return f"Snapshot B differs from Snapshot A: {highlighted[0]}. {tail}"
    items = "; ".join(highlighted[:5])
    extra = f" (and {len(highlighted) - 5} more)" if len(highlighted) > 5 else ""
    return (
        f"Snapshot B differs from Snapshot A in {len(highlighted)} notable area(s): "
        f"{items}{extra}. {tail}"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compare_snapshots(
    snap_a: DatasetSnapshot,
    snap_b: DatasetSnapshot,
    issues_a: list[DataQualityIssue],
    issues_b: list[DataQualityIssue],
) -> DatasetSnapshotComparisonResponse:
    """Compare two DatasetSnapshot records deterministically.

    Both snapshots must already be loaded, including their rows_json payloads.
    This function is pure Python — no database access.
    """
    now = datetime.now(timezone.utc)
    is_same = snap_a.id == snap_b.id

    rows_a: list[dict] = snap_a.rows_json or []
    rows_b: list[dict] = snap_b.rows_json or []

    # ------------------------------------------------------------------
    # A. Metadata
    # ------------------------------------------------------------------
    meta = MetadataComparison(
        snapshot_a_label=snap_a.version_label,
        snapshot_b_label=snap_b.version_label,
        row_count_a=snap_a.row_count,
        row_count_b=snap_b.row_count,
        row_count_delta=snap_b.row_count - snap_a.row_count,
    )

    # ------------------------------------------------------------------
    # B. Schema
    # ------------------------------------------------------------------
    cols_a = _extract_columns(rows_a)
    cols_b = _extract_columns(rows_b)
    col_names_a = set(cols_a)
    col_names_b = set(cols_b)

    added_cols = sorted(col_names_b - col_names_a)
    removed_cols = sorted(col_names_a - col_names_b)
    common_cols = col_names_a & col_names_b

    type_changes: list[TypeChange] = []
    unchanged_cols = 0
    for col in sorted(common_cols):
        if cols_a[col] != cols_b[col]:
            type_changes.append(TypeChange(column=col, type_a=cols_a[col], type_b=cols_b[col]))
        else:
            unchanged_cols += 1

    schema_diff = SchemaComparison(
        columns_a=sorted(col_names_a),
        columns_b=sorted(col_names_b),
        added_columns=added_cols,
        removed_columns=removed_cols,
        type_changes=type_changes,
        unchanged_columns_count=unchanged_cols,
        total_changes=len(added_cols) + len(removed_cols) + len(type_changes),
    )

    # ------------------------------------------------------------------
    # C. Symbol coverage
    # ------------------------------------------------------------------
    syms_a = _extract_symbols(rows_a)
    syms_b = _extract_symbols(rows_b)
    added_syms = sorted(syms_b - syms_a)
    removed_syms = sorted(syms_a - syms_b)
    has_symbols = bool(syms_a or syms_b)

    sym_cov = SymbolCoverageComparison(
        symbol_count_a=len(syms_a),
        symbol_count_b=len(syms_b),
        symbol_count_delta=len(syms_b) - len(syms_a),
        added_symbols=added_syms,
        removed_symbols=removed_syms,
        common_symbols_count=len(syms_a & syms_b),
        keyed_by_symbol=has_symbols,
    )

    # ------------------------------------------------------------------
    # D. Timestamp coverage
    # ------------------------------------------------------------------
    min_a, max_a = _extract_timestamp_range(rows_a)
    min_b, max_b = _extract_timestamp_range(rows_b)
    days_a = _date_range_days(min_a, max_a)
    days_b = _date_range_days(min_b, max_b)
    days_delta: int | None = None
    if days_a is not None and days_b is not None:
        days_delta = days_b - days_a

    ts_cov = TimestampCoverageComparison(
        min_timestamp_a=min_a,
        max_timestamp_a=max_a,
        min_timestamp_b=min_b,
        max_timestamp_b=max_b,
        min_changed=(min_a != min_b),
        max_changed=(max_a != max_b),
        date_range_days_a=days_a,
        date_range_days_b=days_b,
        date_range_days_delta=days_delta,
    )

    # ------------------------------------------------------------------
    # E. Data health
    # ------------------------------------------------------------------
    def _worst_severity(issues: list[DataQualityIssue]) -> str | None:
        if not issues:
            return None
        return min(
            (iss.severity for iss in issues),
            key=lambda s: _SEVERITY_ORDER.get(s, 99),
        )

    issue_types_a = sorted({iss.issue_type for iss in issues_a})
    issue_types_b = sorted({iss.issue_type for iss in issues_b})
    issue_types_added = sorted(set(issue_types_b) - set(issue_types_a))
    issue_types_removed = sorted(set(issue_types_a) - set(issue_types_b))

    data_health = DataHealthComparison(
        health_score_a=snap_a.health_score,
        health_score_b=snap_b.health_score,
        health_score_delta=snap_b.health_score - snap_a.health_score,
        issue_count_a=len(issues_a),
        issue_count_b=len(issues_b),
        issue_count_delta=len(issues_b) - len(issues_a),
        worst_severity_a=_worst_severity(issues_a),
        worst_severity_b=_worst_severity(issues_b),
        issue_types_a=issue_types_a,
        issue_types_b=issue_types_b,
        issue_types_added=issue_types_added,
        issue_types_removed=issue_types_removed,
    )

    # ------------------------------------------------------------------
    # F. Value revisions
    # ------------------------------------------------------------------
    revisions = _compare_rows(rows_a, rows_b)

    # ------------------------------------------------------------------
    # Highlighted changes + explanation
    # ------------------------------------------------------------------
    highlighted = _build_highlighted_changes(
        meta, schema_diff, sym_cov, ts_cov, data_health, revisions
    )

    total_changes = (
        (1 if meta.row_count_delta != 0 else 0)
        + schema_diff.total_changes
        + (1 if sym_cov.symbol_count_delta != 0 else 0)
        + (1 if ts_cov.min_changed else 0)
        + (1 if ts_cov.max_changed else 0)
        + (1 if data_health.health_score_delta != 0 else 0)
        + revisions.added_rows_count
        + revisions.removed_rows_count
        + revisions.changed_rows_count
    )

    explanation = _build_explanation(highlighted, total_changes, is_same)

    # ------------------------------------------------------------------
    # Warnings
    # ------------------------------------------------------------------
    warnings: list[str] = []
    if schema_diff.added_columns or schema_diff.removed_columns:
        warnings.append(
            "The two snapshots have different column sets. Row-level comparison "
            "may be incomplete or unreliable for columns that do not exist in both."
        )
    if not revisions.keyed_comparison_available and (rows_a or rows_b):
        warnings.append(
            "Rows could not be keyed by (symbol, timestamp). "
            "Value revision counts use hash-based comparison and per-field "
            "deltas are not available."
        )
    if revisions.total_examples_capped:
        warnings.append(
            f"Value revision examples are capped at {MAX_EXAMPLES}. "
            "Not all changed rows are shown."
        )

    # ------------------------------------------------------------------
    # Summary sentence
    # ------------------------------------------------------------------
    if is_same:
        summary = "No changes — comparing a snapshot to itself."
    elif total_changes == 0:
        summary = "No structural differences detected."
    else:
        summary = (
            f"{len(highlighted)} notable change(s) detected across "
            f"schema, coverage, health, and row data."
        )

    return DatasetSnapshotComparisonResponse(
        dataset_id=snap_a.dataset_id,
        snapshot_a_id=snap_a.id,
        snapshot_b_id=snap_b.id,
        snapshot_a_label=snap_a.version_label,
        snapshot_b_label=snap_b.version_label,
        is_same_snapshot=is_same,
        summary=summary,
        metadata=meta,
        schema_diff=schema_diff,
        symbol_coverage=sym_cov,
        timestamp_coverage=ts_cov,
        data_health=data_health,
        value_revisions=revisions,
        highlighted_changes=highlighted,
        deterministic_explanation=explanation,
        warnings=warnings,
        generated_at=now,
    )
