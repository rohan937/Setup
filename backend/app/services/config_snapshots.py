"""Config snapshot service — M15.

Provides deterministic hashing and key-level comparison of strategy config
snapshots.  No AI, no live data, no external calls.

Design constraints:
  - config_hash is derived from normalized (sort_keys=True) JSON; two configs
    with the same keys/values in any order produce the same hash.
  - Comparison is structural only: top-level keys plus nested params/assumptions
    sub-keys.  Values are compared with == ; no deep recursive diff.
  - Language is hedged: "observed", "noted", never causal.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------

def compute_config_hash(config_json: dict) -> str:
    """Return a 64-char hex SHA-256 of the normalised config JSON.

    Deterministic regardless of key insertion order.
    """
    normalised = json.dumps(config_json, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def count_params(config_json: dict) -> int:
    """Count keys in config_json['params'] if that value is a dict; else 0."""
    params = config_json.get("params")
    return len(params) if isinstance(params, dict) else 0


def count_assumptions(config_json: dict) -> int:
    """Count keys in config_json['assumptions'] if that value is a dict; else 0."""
    assumptions = config_json.get("assumptions")
    return len(assumptions) if isinstance(assumptions, dict) else 0


# ---------------------------------------------------------------------------
# Comparison result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ConfigKeyChange:
    key: str
    old_value: Any
    new_value: Any
    change_type: str  # "added" | "removed" | "changed"


@dataclass
class ConfigComparisonSection:
    added: list[ConfigKeyChange] = field(default_factory=list)
    removed: list[ConfigKeyChange] = field(default_factory=list)
    changed: list[ConfigKeyChange] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.removed) + len(self.changed)


@dataclass
class ConfigComparisonResult:
    snapshot_a_id: str
    snapshot_b_id: str
    snapshot_a_label: str
    snapshot_b_label: str
    is_same_config: bool
    top_level: ConfigComparisonSection
    params: ConfigComparisonSection
    assumptions: ConfigComparisonSection
    highlighted_changes: list[str]
    total_changes: int


# ---------------------------------------------------------------------------
# Comparison logic
# ---------------------------------------------------------------------------

def _diff_dicts(
    dict_a: dict,
    dict_b: dict,
) -> ConfigComparisonSection:
    """Produce a flat diff of two dicts at one level of nesting."""
    section = ConfigComparisonSection()
    all_keys = set(dict_a) | set(dict_b)

    for k in sorted(all_keys):
        if k not in dict_a:
            section.added.append(ConfigKeyChange(
                key=k,
                old_value=None,
                new_value=dict_b[k],
                change_type="added",
            ))
        elif k not in dict_b:
            section.removed.append(ConfigKeyChange(
                key=k,
                old_value=dict_a[k],
                new_value=None,
                change_type="removed",
            ))
        elif dict_a[k] != dict_b[k]:
            section.changed.append(ConfigKeyChange(
                key=k,
                old_value=dict_a[k],
                new_value=dict_b[k],
                change_type="changed",
            ))

    return section


def compare_config_snapshots(
    snap_a_id: str,
    snap_b_id: str,
    snap_a_label: str,
    snap_b_label: str,
    config_a: dict,
    config_b: dict,
) -> ConfigComparisonResult:
    """Deterministically compare two config JSON objects.

    Compares:
    - Top-level keys (excluding 'params' and 'assumptions' — handled separately)
    - params sub-keys (if both snapshots have a params dict)
    - assumptions sub-keys

    Returns a structured comparison with highlighted changes.
    """
    same_config = compute_config_hash(config_a) == compute_config_hash(config_b)

    # Top-level comparison (keys other than params/assumptions)
    top_a = {k: v for k, v in config_a.items() if k not in ("params", "assumptions")}
    top_b = {k: v for k, v in config_b.items() if k not in ("params", "assumptions")}
    top_level = _diff_dicts(top_a, top_b)

    # params comparison
    params_a = config_a.get("params", {}) if isinstance(config_a.get("params"), dict) else {}
    params_b = config_b.get("params", {}) if isinstance(config_b.get("params"), dict) else {}
    params = _diff_dicts(params_a, params_b)

    # assumptions comparison
    assump_a = config_a.get("assumptions", {}) if isinstance(config_a.get("assumptions"), dict) else {}
    assump_b = config_b.get("assumptions", {}) if isinstance(config_b.get("assumptions"), dict) else {}
    assumptions = _diff_dicts(assump_a, assump_b)

    # Build highlighted changes (deterministic human-readable bullets)
    highlights: list[str] = []
    for c in params.added[:3]:
        highlights.append(f"Param '{c.key}' added: {c.new_value}")
    for c in params.removed[:3]:
        highlights.append(f"Param '{c.key}' removed (was {c.old_value})")
    for c in params.changed[:3]:
        highlights.append(f"Param '{c.key}' changed: {c.old_value} → {c.new_value}")
    for c in assumptions.added[:3]:
        highlights.append(f"Assumption '{c.key}' added: {c.new_value}")
    for c in assumptions.removed[:3]:
        highlights.append(f"Assumption '{c.key}' removed (was {c.old_value})")
    for c in assumptions.changed[:3]:
        highlights.append(f"Assumption '{c.key}' changed: {c.old_value} → {c.new_value}")
    for c in top_level.added[:2]:
        highlights.append(f"Top-level key '{c.key}' added")
    for c in top_level.removed[:2]:
        highlights.append(f"Top-level key '{c.key}' removed")
    for c in top_level.changed[:2]:
        highlights.append(f"Top-level key '{c.key}' changed")

    total = top_level.total_changes + params.total_changes + assumptions.total_changes

    return ConfigComparisonResult(
        snapshot_a_id=snap_a_id,
        snapshot_b_id=snap_b_id,
        snapshot_a_label=snap_a_label,
        snapshot_b_label=snap_b_label,
        is_same_config=same_config,
        top_level=top_level,
        params=params,
        assumptions=assumptions,
        highlighted_changes=highlights[:10],
        total_changes=total,
    )
