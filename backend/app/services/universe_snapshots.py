"""Universe snapshot service — M16.

Provides deterministic symbol normalization, hashing, and comparison of
universe snapshots.  No AI, no live data, no external calls.

Design constraints:
  - Symbols are normalized: trimmed, uppercased, deduplicated, sorted.
  - universe_hash is derived from sorted normalized symbols + optional metadata
    (sort_keys=True JSON); two universes with the same symbols in any order
    produce the same hash.
  - Comparison is set-based: added, removed, common — no order sensitivity.
  - Language is hedged: "observed", "noted", "may affect", never causal.
  - Added/removed lists are capped at 50 in the response; counts are exact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def normalize_symbols(symbols: list[str]) -> list[str]:
    """Return a sorted, uppercase, deduplicated, non-empty list of symbols.

    Empty strings and whitespace-only entries are dropped.
    """
    seen: set[str] = set()
    result: list[str] = []
    for raw in symbols:
        cleaned = raw.strip().upper()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return sorted(result)


# ---------------------------------------------------------------------------
# Hash helper
# ---------------------------------------------------------------------------

def compute_universe_hash(symbols: list[str], metadata: dict | None = None) -> str:
    """Return a 64-char hex SHA-256 of the normalised universe.

    `symbols` must already be normalised (sorted, uppercased, deduped).
    `metadata` is sorted-key serialized alongside the symbols so that two
    identical universes with identical metadata always produce the same hash.
    """
    payload: dict = {"symbols": symbols}
    if metadata:
        payload["metadata"] = metadata
    normalised = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Comparison result dataclass
# ---------------------------------------------------------------------------

_DISPLAY_CAP = 50  # max added/removed symbols shown in response


@dataclass
class UniverseComparisonResult:
    snapshot_a_id: str
    snapshot_b_id: str
    snapshot_a_label: str
    snapshot_b_label: str
    snapshot_a_symbol_count: int
    snapshot_b_symbol_count: int
    is_same_universe: bool
    # Full counts (exact, not capped)
    added_count: int
    removed_count: int
    common_symbols_count: int
    symbol_count_delta: int  # B count − A count
    # Ratios
    overlap_ratio: float    # |A ∩ B| / max(|A|, |B|); 1.0 when both empty
    jaccard_similarity: float  # |A ∩ B| / |A ∪ B|; 1.0 when both empty
    # Capped symbol lists (first _DISPLAY_CAP each)
    added_symbols: list[str] = field(default_factory=list)
    removed_symbols: list[str] = field(default_factory=list)
    highlighted_changes: list[str] = field(default_factory=list)
    deterministic_explanation: str = ""


# ---------------------------------------------------------------------------
# Comparison logic
# ---------------------------------------------------------------------------

def compare_universe_snapshots(
    snap_a_id: str,
    snap_b_id: str,
    snap_a_label: str,
    snap_b_label: str,
    symbols_a: list[str],
    symbols_b: list[str],
    hash_a: str,
    hash_b: str,
) -> UniverseComparisonResult:
    """Deterministically compare two universe snapshots by their symbol sets.

    `symbols_a` and `symbols_b` must be pre-normalised (sorted, uppercased,
    deduped) lists as stored in `UniverseSnapshot.symbols_json`.

    Returns a `UniverseComparisonResult` with exact counts and capped lists.
    Language is hedged — no causal claims.
    """
    set_a = set(symbols_a)
    set_b = set(symbols_b)

    added_full = sorted(set_b - set_a)
    removed_full = sorted(set_a - set_b)
    common = set_a & set_b

    added_count = len(added_full)
    removed_count = len(removed_full)
    common_count = len(common)
    union_count = len(set_a | set_b)

    n_a = len(symbols_a)
    n_b = len(symbols_b)
    max_count = max(n_a, n_b)

    overlap_ratio = round(common_count / max_count, 4) if max_count > 0 else 1.0
    jaccard = round(common_count / union_count, 4) if union_count > 0 else 1.0

    is_same = (hash_a == hash_b) or (set_a == set_b)

    # Build highlighted changes (deterministic, hedged)
    highlights: list[str] = []
    if added_count > 0:
        sample = added_full[:3]
        suffix = f" (e.g. {', '.join(sample)})" if sample else ""
        highlights.append(
            f"{added_count} symbol(s) observed as added{suffix}"
        )
    if removed_count > 0:
        sample = removed_full[:3]
        suffix = f" (e.g. {', '.join(sample)})" if sample else ""
        highlights.append(
            f"{removed_count} symbol(s) observed as removed{suffix}"
        )
    if is_same:
        highlights.append("Universe coverage noted as identical across both snapshots")
    else:
        highlights.append(
            f"Overlap ratio noted at {overlap_ratio:.1%} "
            f"({common_count} common of {max_count} max eligible)"
        )
        highlights.append(
            f"Jaccard similarity observed at {jaccard:.1%}"
        )

    # Deterministic explanation (1-2 sentences, hedged)
    if is_same:
        explanation = (
            f"Universe '{snap_a_label}' and '{snap_b_label}' contain identical "
            f"eligible assets ({n_a} symbol(s)). No coverage changes were noted."
        )
    else:
        delta = n_b - n_a
        direction = "increased" if delta > 0 else "decreased" if delta < 0 else "remained equal"
        explanation = (
            f"Universe '{snap_a_label}' observed {n_a} eligible asset(s); "
            f"'{snap_b_label}' observed {n_b} eligible asset(s) — "
            f"a change of {delta:+d} symbol(s). "
            f"{added_count} symbol(s) were noted as added and "
            f"{removed_count} as removed alongside this transition. "
            f"The overlap ratio was observed at {overlap_ratio:.1%}. "
            f"Coverage {direction} — this may affect backtests and requires review."
        )

    return UniverseComparisonResult(
        snapshot_a_id=snap_a_id,
        snapshot_b_id=snap_b_id,
        snapshot_a_label=snap_a_label,
        snapshot_b_label=snap_b_label,
        snapshot_a_symbol_count=n_a,
        snapshot_b_symbol_count=n_b,
        is_same_universe=is_same,
        added_count=added_count,
        removed_count=removed_count,
        common_symbols_count=common_count,
        symbol_count_delta=n_b - n_a,
        overlap_ratio=overlap_ratio,
        jaccard_similarity=jaccard,
        added_symbols=added_full[:_DISPLAY_CAP],
        removed_symbols=removed_full[:_DISPLAY_CAP],
        highlighted_changes=highlights[:10],
        deterministic_explanation=explanation,
    )
