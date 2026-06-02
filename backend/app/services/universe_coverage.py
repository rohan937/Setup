"""Universe coverage analysis service for M39.

Computes symbol quality, metadata breakdown, universe delta, run linkage,
and a quality summary for a universe snapshot.
Pure Python (except DB queries in delta/linkage) — no AI, no causal claims.

This is a NEW service and does NOT modify universe_snapshots.py.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Symbol quality
# ---------------------------------------------------------------------------

VALID_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_+/")


def compute_symbol_quality(symbols_json: list[str]) -> list[dict]:
    """Return per-symbol quality assessment for the given symbol list."""
    seen: dict[str, int] = {}
    results: list[dict] = []

    for sym in (symbols_json or []):
        issues: list[str] = []
        status = "clean"

        if not sym or not sym.strip():
            issues.append("Empty or whitespace symbol")
            status = "weak"
        else:
            if " " in sym:
                issues.append("Symbol contains spaces")
                status = "review" if status == "clean" else status
            if len(sym) > 15:
                issues.append(f"Unusually long symbol ({len(sym)} chars)")
                status = "review" if status == "clean" else status
            invalid_chars = set(sym) - VALID_CHARS
            if invalid_chars:
                issues.append(
                    f"Suspicious characters: {', '.join(sorted(invalid_chars)[:3])}"
                )
                status = "review" if status == "clean" else status

        normalized = sym.strip().upper()
        is_dup = normalized in seen
        if is_dup:
            issues.append(f"Duplicate of {normalized}")
            status = "review" if status == "clean" else status

        seen.setdefault(normalized, 0)
        seen[normalized] += 1

        results.append(
            {
                "symbol": sym,
                "normalized_symbol": normalized,
                "is_duplicate": is_dup,
                "has_invalid_format": bool(issues) and status in ("weak",),
                "format_issues": issues,
                "quality_status": status,
                "issues": issues,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Metadata breakdown
# ---------------------------------------------------------------------------

def compute_metadata_breakdown(snapshot) -> dict:
    """Return a breakdown of symbol-level metadata from snapshot.metadata_json."""
    meta = snapshot.metadata_json or {}
    sym_meta = meta.get("symbols") or meta.get("symbol_metadata")
    symbols = snapshot.symbols_json or []

    if not sym_meta or not isinstance(sym_meta, dict):
        return {
            "has_symbol_metadata": False,
            "metadata_coverage_rate": 0.0,
            "missing_metadata_symbols": len(symbols),
            "by_sector": {},
            "by_country": {},
            "by_exchange": {},
            "by_liquidity_bucket": {},
            "warnings": [
                "No symbol-level metadata available; sector/country/exchange coverage cannot be assessed."
            ],
        }

    with_meta = [s for s in symbols if s in sym_meta]
    without_meta = [s for s in symbols if s not in sym_meta]
    coverage_rate = round(len(with_meta) / len(symbols), 4) if symbols else 0.0

    by_sector: dict[str, int] = {}
    by_country: dict[str, int] = {}
    by_exchange: dict[str, int] = {}
    by_liq: dict[str, int] = {}

    for sym in with_meta:
        m = sym_meta.get(sym)
        if isinstance(m, dict):
            for key, bucket in [
                ("sector", by_sector),
                ("country", by_country),
                ("exchange", by_exchange),
                ("liquidity_bucket", by_liq),
            ]:
                val = m.get(key)
                if val:
                    bucket[str(val)] = bucket.get(str(val), 0) + 1

    return {
        "has_symbol_metadata": True,
        "metadata_coverage_rate": coverage_rate,
        "missing_metadata_symbols": len(without_meta),
        "by_sector": by_sector,
        "by_country": by_country,
        "by_exchange": by_exchange,
        "by_liquidity_bucket": by_liq,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Universe delta (DB-dependent)
# ---------------------------------------------------------------------------

def compute_universe_delta(snapshot, db: Session) -> dict:
    """Compute the delta between this snapshot and the most recent prior snapshot."""
    from app.models.universe_snapshot import UniverseSnapshot
    from datetime import timezone

    def _nt(dt):
        if dt is None:
            return None
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    ct = _nt(snapshot.created_at)
    q = db.query(UniverseSnapshot).filter(
        UniverseSnapshot.strategy_id == snapshot.strategy_id,
        UniverseSnapshot.id != snapshot.id,
    )
    if ct:
        q = q.filter(UniverseSnapshot.created_at < snapshot.created_at)
    prev = q.order_by(UniverseSnapshot.created_at.desc()).first()

    current_syms = set(snapshot.symbols_json or [])

    if prev is None:
        return {
            "has_previous": False,
            "previous_snapshot_id": None,
            "previous_label": None,
            "added_symbols": [],
            "removed_symbols": [],
            "common_symbols_count": 0,
            "added_count": 0,
            "removed_count": 0,
            "overlap_ratio": None,
            "jaccard_similarity": None,
            "churn_rate": None,
            "delta_status": "no_previous_snapshot",
        }

    prev_syms = set(prev.symbols_json or [])
    added = sorted(current_syms - prev_syms)
    removed = sorted(prev_syms - current_syms)
    common = current_syms & prev_syms

    n_added = len(added)
    n_removed = len(removed)
    n_common = len(common)
    n_curr = len(current_syms)
    n_prev = len(prev_syms)
    union_size = len(current_syms | prev_syms)

    jaccard = round(n_common / union_size, 4) if union_size > 0 else 1.0
    overlap = round(n_common / min(n_curr, n_prev), 4) if min(n_curr, n_prev) > 0 else 1.0
    churn = round((n_added + n_removed) / max(n_prev, n_curr, 1), 4)

    delta_status = (
        "high_churn" if churn > 0.5
        else ("review" if churn > 0.2 else "stable")
    )

    return {
        "has_previous": True,
        "previous_snapshot_id": str(prev.id),
        "previous_label": prev.label,
        "added_symbols": added[:50],
        "removed_symbols": removed[:50],
        "common_symbols_count": n_common,
        "added_count": n_added,
        "removed_count": n_removed,
        "overlap_ratio": overlap,
        "jaccard_similarity": jaccard,
        "churn_rate": churn,
        "delta_status": delta_status,
    }


# ---------------------------------------------------------------------------
# Run linkage (DB-dependent)
# ---------------------------------------------------------------------------

def compute_run_linkage(snapshot, db: Session) -> dict:
    """Return run linkage info for this universe snapshot."""
    from app.models.strategy_run import StrategyRun
    from app.models.strategy_version import StrategyVersion

    runs = (
        db.query(StrategyRun)
        .filter(StrategyRun.universe_snapshot_id == snapshot.id)
        .all()
    )

    latest_run_at = (
        max((r.created_at for r in runs if r.created_at), default=None)
        if runs
        else None
    )

    version_label = None
    if snapshot.strategy_version_id:
        v = (
            db.query(StrategyVersion)
            .filter(StrategyVersion.id == snapshot.strategy_version_id)
            .first()
        )
        if v:
            version_label = v.version_label

    return {
        "linked_run_count": len(runs),
        "latest_linked_run_at": latest_run_at,
        "version_label": version_label,
        "is_used_by_runs": len(runs) > 0,
        "linkage_status": "linked" if runs else "unlinked",
    }


# ---------------------------------------------------------------------------
# Quality summary
# ---------------------------------------------------------------------------

def compute_universe_quality_summary(
    symbols_json: list[str],
    symbol_quality: list[dict],
    delta: dict,
    meta_breakdown: dict,
) -> dict:
    """Aggregate quality signals into a single summary dict."""
    n_syms = len(symbols_json or [])
    dups = sum(1 for s in symbol_quality if s["is_duplicate"])
    invalid = sum(1 for s in symbol_quality if s["quality_status"] == "weak")
    review = sum(1 for s in symbol_quality if s["quality_status"] == "review")
    clean = sum(1 for s in symbol_quality if s["quality_status"] == "clean")

    if n_syms == 0 or invalid > 0:
        coverage_status = "weak"
    elif dups > 0 or review > 0:
        coverage_status = "review"
    elif n_syms > 0:
        coverage_status = "complete"
    else:
        coverage_status = "unknown"

    checks: list[str] = []
    if dups > 0:
        checks.append(f"Resolve {dups} duplicate symbol(s).")
    if invalid > 0:
        checks.append(f"Review {invalid} symbol(s) with invalid format.")
    if delta.get("delta_status") == "high_churn":
        checks.append(
            "Universe has high symbol churn. Confirm this change was intentional."
        )
    if not meta_breakdown.get("has_symbol_metadata"):
        checks.append(
            "Add symbol-level metadata (sector/country/exchange) for richer coverage analysis."
        )
    if n_syms == 0:
        checks.append("Universe has no symbols. Log a universe snapshot with symbols.")

    return {
        "symbol_count": n_syms,
        "unique_symbol_count": n_syms - dups,
        "duplicate_symbol_count": dups,
        "invalid_symbol_count": invalid,
        "clean_symbol_count": clean,
        "review_symbol_count": review,
        "weak_symbol_count": invalid,
        "coverage_status": coverage_status,
        "suggested_checks": checks,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_universe_coverage_analysis(snapshot_id: uuid.UUID, db: Session) -> dict:
    """Compute full coverage analysis for a universe snapshot.

    Returns a dict with keys: coverage_analysis, symbol_quality,
    metadata_breakdown, universe_delta, universe_quality_summary.
    """
    from app.models.universe_snapshot import UniverseSnapshot

    snapshot = (
        db.query(UniverseSnapshot)
        .filter(UniverseSnapshot.id == snapshot_id)
        .first()
    )
    if snapshot is None:
        raise ValueError(f"Universe snapshot {snapshot_id} not found")

    symbols = snapshot.symbols_json or []
    sym_q = compute_symbol_quality(symbols)
    meta_b = compute_metadata_breakdown(snapshot)
    delta = compute_universe_delta(snapshot, db)
    run_link = compute_run_linkage(snapshot, db)
    summary = compute_universe_quality_summary(symbols, sym_q, delta, meta_b)

    # coverage_analysis combines summary + linkage
    cov = {**summary, **run_link}

    return {
        "coverage_analysis": cov,
        "symbol_quality": sym_q,
        "metadata_breakdown": meta_b,
        "universe_delta": delta,
        "universe_quality_summary": summary,
    }
