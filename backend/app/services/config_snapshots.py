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


# ---------------------------------------------------------------------------
# M40: Assumption classification constants
# ---------------------------------------------------------------------------

COST_KEYS = {"transaction_cost_bps", "cost_bps", "commission_bps", "tc_bps", "cost"}
SLIPPAGE_KEYS = {"slippage_bps", "slippage_model", "market_impact_bps", "slippage"}
FILL_KEYS = {"fill_model", "execution_timing", "fill_strategy", "fill"}
BORROW_KEYS = {"borrow_cost_bps", "borrow_required", "short_enabled", "borrow_rate_bps"}
LEVERAGE_KEYS = {"max_leverage", "leverage_cap", "gross_leverage", "leverage"}
RISK_KEYS = {"max_position_weight", "max_sector_weight", "stop_loss", "trailing_stop", "position_limit"}
LIQUIDITY_KEYS = {"liquidity_filter", "adv_filter", "min_adv_usd", "volume_filter", "adv_threshold_usd"}

FILL_MODEL_RISK: dict[str, str] = {
    "close": "high_concern",
    "same_close": "high_concern",
    "same_bar": "high_concern",
    "exact_price": "high_concern",
    "prev_close": "high_concern",
    "open": "medium_concern",
    "mid": "medium_concern",
    "vwap": "medium_concern",
    "twap": "medium_concern",
    "next_bar_open": "low_concern",
    "next_close": "low_concern",
    "conservative": "low_concern",
    "mid_plus_5bps": "low_concern",
    "slippage_adjusted": "low_concern",
}


def _safe_float_val(v: Any) -> float | None:
    """Attempt to coerce v to float; return None on failure."""
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def classify_assumption_change(
    key: str,
    old_val: Any,
    new_val: Any,
) -> tuple[str, str, str | None]:
    """Classify the impact of an assumption change.

    Returns (impact_level, impact_reason, suggested_check | None).
    impact_level: "positive" | "neutral" | "review" | "weakening" | "unknown"
    """
    key_lower = key.lower()

    # Cost keys
    if key_lower in COST_KEYS:
        if old_val is None and new_val is not None:
            fv = _safe_float_val(new_val)
            if fv is not None and fv > 0:
                return "positive", "Adding a cost assumption makes the backtest more conservative.", None
            return "neutral", "Cost assumption added with zero or unknown value.", None
        if old_val is not None and new_val is None:
            return (
                "weakening",
                "Removing the cost assumption may make backtest assumptions less conservative.",
                f"Re-add {key} before backtesting.",
            )
        fo, fn = _safe_float_val(old_val), _safe_float_val(new_val)
        if fo is not None and fn is not None:
            if fn > fo:
                return "positive", f"Increasing cost from {fo:.0f} to {fn:.0f} bps is more conservative.", None
            if fn < fo:
                return (
                    "review",
                    f"Decreasing cost from {fo:.0f} to {fn:.0f} bps may reduce backtest conservatism. Review intentionality.",
                    None,
                )
        return "neutral", f"{key} changed from {old_val} to {new_val}.", None

    # Slippage (non-model)
    if key_lower in SLIPPAGE_KEYS and "model" not in key_lower:
        if old_val is None and new_val is not None:
            return "positive", "Adding slippage assumption improves realism.", None
        if old_val is not None and new_val is None:
            return "weakening", "Removing slippage may make assumptions less conservative.", None
        fo, fn = _safe_float_val(old_val), _safe_float_val(new_val)
        if fo is not None and fn is not None:
            if fn < fo:
                return "review", f"Decreasing slippage from {fo:.0f} to {fn:.0f} bps may reduce conservatism.", None
            if fn > fo:
                return "positive", f"Increasing slippage from {fo:.0f} to {fn:.0f} bps is more conservative.", None
        return "neutral", f"Slippage changed from {old_val} to {new_val}.", None

    # Fill model
    if key_lower == "fill_model":
        old_risk = FILL_MODEL_RISK.get(str(old_val or "").lower(), "unknown")
        new_risk = FILL_MODEL_RISK.get(str(new_val or "").lower(), "unknown")
        if new_risk == "high_concern" and old_risk != "high_concern":
            return (
                "weakening",
                f"Changing fill model to {new_val} (same-close/exact) may overstate performance. Requires review.",
                "Consider using next_bar_open or slippage_adjusted fill.",
            )
        if old_risk == "high_concern" and new_risk in ("low_concern", "medium_concern"):
            return "positive", f"Changing fill model from {old_val} to {new_val} is more realistic.", None
        return (
            "review",
            f"Fill model changed from {old_val} to {new_val}. Review whether this affects realism.",
            None,
        )

    # Short enabled
    if key_lower == "short_enabled":
        if new_val is True and not old_val:
            return (
                "review",
                "Enabling shorting. Ensure borrow_cost_bps is set.",
                "Add borrow_cost_bps when short_enabled=True.",
            )

    # Borrow keys (excluding short_enabled)
    if key_lower in BORROW_KEYS and "enabled" not in key_lower:
        if old_val is None and new_val is not None:
            return "positive", "Adding borrow cost assumption improves short-side realism.", None
        if old_val is not None and new_val is None:
            return "weakening", "Removing borrow cost may overstate short-side returns.", None

    # Leverage
    if key_lower in LEVERAGE_KEYS:
        if old_val is None and new_val is not None:
            return "review", "Leverage cap added; review intended leverage.", None
        fo, fn = _safe_float_val(old_val), _safe_float_val(new_val)
        if fo is not None and fn is not None and fn > fo:
            return "review", f"Increasing max leverage from {fo} to {fn}. Review risk implications.", None

    # Risk limits
    if key_lower in RISK_KEYS:
        if old_val is not None and new_val is None:
            return "weakening", f"Removing {key} risk limit may increase backtest fragility.", None
        if old_val is None and new_val is not None:
            return "review", f"Adding {key} risk limit adds constraint realism.", None

    # Liquidity
    if key_lower in LIQUIDITY_KEYS:
        if old_val is not None and new_val is None:
            return "weakening", "Removing liquidity filter may overstate tradability.", None
        if old_val is None and new_val is not None:
            return "review", "Adding liquidity filter; verify threshold matches execution capacity.", None

    return "unknown", f"{key} changed from {old_val} to {new_val}.", None


# ---------------------------------------------------------------------------
# M40: Enriched comparison
# ---------------------------------------------------------------------------

def compare_config_snapshots_enriched(snap_a: Any, snap_b: Any) -> dict:
    """Compare two StrategyConfigSnapshot ORM objects with assumption classification.

    Extends the M15 comparison with per-field impact classification across
    params, assumptions, portfolio, and risk/constraints sections.
    Returns a plain dict suitable for direct serialisation.
    """
    config_a: dict = snap_a.config_json or {}
    config_b: dict = snap_b.config_json or {}

    def _diff_section(section_a: dict, section_b: dict, category: str) -> dict:
        keys_a = set(section_a.keys())
        keys_b = set(section_b.keys())
        added_keys = sorted(keys_b - keys_a)
        removed_keys = sorted(keys_a - keys_b)
        changes: list[dict] = []
        unchanged = 0

        for k in sorted(keys_a & keys_b):
            if section_a[k] != section_b[k]:
                impact, reason, check = classify_assumption_change(k, section_a[k], section_b[k])
                changes.append({
                    "key": k,
                    "key_path": f"{category}.{k}",
                    "old_value": section_a[k],
                    "new_value": section_b[k],
                    "change_type": "changed",
                    "category": category,
                    "impact_level": impact,
                    "impact_reason": reason,
                    "suggested_check": check,
                })
            else:
                unchanged += 1

        for k in added_keys:
            impact, reason, check = classify_assumption_change(k, None, section_b[k])
            changes.append({
                "key": k,
                "key_path": f"{category}.{k}",
                "old_value": None,
                "new_value": section_b[k],
                "change_type": "added",
                "category": category,
                "impact_level": impact,
                "impact_reason": reason,
                "suggested_check": check,
            })

        for k in removed_keys:
            impact, reason, check = classify_assumption_change(k, section_a[k], None)
            changes.append({
                "key": k,
                "key_path": f"{category}.{k}",
                "old_value": section_a[k],
                "new_value": None,
                "change_type": "removed",
                "category": category,
                "impact_level": impact,
                "impact_reason": reason,
                "suggested_check": check,
            })

        changed_count = len([c for c in changes if c["change_type"] == "changed"])
        return {
            "changes": changes,
            "unchanged_count": unchanged,
            "added_count": len(added_keys),
            "removed_count": len(removed_keys),
            "changed_count": changed_count,
        }

    params_diff = _diff_section(
        config_a.get("params") or {},
        config_b.get("params") or {},
        "params",
    )
    assumptions_diff = _diff_section(
        config_a.get("assumptions") or {},
        config_b.get("assumptions") or {},
        "assumptions",
    )
    portfolio_diff = _diff_section(
        config_a.get("portfolio") or {},
        config_b.get("portfolio") or {},
        "portfolio",
    )
    risk_diff = _diff_section(
        config_a.get("risk") or config_a.get("constraints") or {},
        config_b.get("risk") or config_b.get("constraints") or {},
        "risk",
    )

    all_changes = (
        params_diff["changes"]
        + assumptions_diff["changes"]
        + portfolio_diff["changes"]
        + risk_diff["changes"]
    )
    weakening = [c for c in all_changes if c["impact_level"] == "weakening"]
    positive = [c for c in all_changes if c["impact_level"] == "positive"]
    review = [c for c in all_changes if c["impact_level"] == "review"]

    highlighted = (
        [f"Weakening: {c['key']} ({c['impact_reason'][:60]})" for c in weakening[:3]]
        + [f"Positive: {c['key']} ({c['impact_reason'][:60]})" for c in positive[:3]]
    )
    checks = list(dict.fromkeys(c["suggested_check"] for c in all_changes if c.get("suggested_check")))
    total = len(all_changes)

    if total == 0:
        explanation = (
            f"No changes found between '{snap_a.label}' and '{snap_b.label}'. "
            "Configs are identical."
        )
    else:
        w_count = len(weakening)
        p_count = len(positive)
        r_count = len(review)
        parts = [f"{total} config change(s) detected between '{snap_a.label}' and '{snap_b.label}'."]
        if w_count:
            parts.append(f"{w_count} change(s) may make assumptions less conservative.")
        if p_count:
            parts.append(f"{p_count} change(s) add evidence conservatism.")
        if r_count:
            parts.append(f"{r_count} change(s) require review.")
        parts.append(
            "This is a deterministic comparison of logged config snapshots. Not investment advice."
        )
        explanation = " ".join(parts)

    is_same = snap_a.config_hash == snap_b.config_hash

    return {
        "snapshot_a_id": str(snap_a.id),
        "snapshot_b_id": str(snap_b.id),
        "snapshot_a_label": snap_a.label,
        "snapshot_b_label": snap_b.label,
        "is_same_config": is_same,
        "total_changes": total,
        "params_diff": params_diff,
        "assumptions_diff": assumptions_diff,
        "portfolio_diff": portfolio_diff,
        "risk_diff": risk_diff,
        "all_changes": all_changes,
        "weakening_changes": weakening,
        "positive_changes": positive,
        "review_changes": review,
        "highlighted_changes": highlighted,
        "suggested_checks": checks,
        "deterministic_explanation": explanation,
    }
