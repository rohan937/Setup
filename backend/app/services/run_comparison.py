"""Deterministic run comparison engine.

Compares two StrategyRun records and produces a structured, evidence-backed diff.
Pure Python — no database access, no AI, no causal claims.

Design rules:
  - Changes are stated as observed facts, not causes.
  - Language: "associated with", "changed alongside", "noted as observed".
  - Never use "caused", "because", "therefore", "resulted in".
  - Never generate investment advice.
"""

from __future__ import annotations

from typing import Any

from app.models.strategy_run import StrategyRun
from app.schemas.comparison import (
    ComparisonSection,
    FieldChange,
    RunComparisonResponse,
)

# Sentinel for keys missing from a dict
_MISSING = object()

# Performance metrics recognised by name — used to generate highlighted_changes
# in priority order (most important first).
_IMPORTANT_METRICS: list[str] = [
    "sharpe",
    "sortino",
    "annual_return",
    "volatility",
    "max_drawdown",
    "turnover",
    "hit_rate",
    "average_holding_period",
    "gross_exposure",
    "net_exposure",
    "capacity_estimate",
    "transaction_cost_bps",
    "slippage_bps",
    "alpha_bps",
]

# Parameters recognised by name — surfaced in highlighted_changes when changed.
_IMPORTANT_PARAMS: list[str] = [
    "lookback",
    "lookback_days",
    "threshold",
    "rebal_freq",
    "half_life",
    "leverage",
    "max_position_size",
    "stop_loss",
    "transaction_cost_bps",
    "slippage_bps",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fmt(v: Any) -> str:
    """Format a value for human-readable output (no trailing float zeros)."""
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _compare_dicts(
    dict_a: dict | None,
    dict_b: dict | None,
    *,
    compute_numeric_delta: bool = True,
) -> ComparisonSection:
    """Compare two JSON dicts key-by-key.

    Returns a ComparisonSection with added / removed / changed / unchanged.
    """
    a: dict = dict_a or {}
    b: dict = dict_b or {}

    added: list[FieldChange] = []
    removed: list[FieldChange] = []
    changed: list[FieldChange] = []
    unchanged_count = 0

    for key in sorted(set(a) | set(b)):
        a_val = a.get(key, _MISSING)
        b_val = b.get(key, _MISSING)

        if a_val is _MISSING:
            added.append(
                FieldChange(
                    field=key,
                    old_value=None,
                    new_value=b_val,
                    change_type="added",
                )
            )
        elif b_val is _MISSING:
            removed.append(
                FieldChange(
                    field=key,
                    old_value=a_val,
                    new_value=None,
                    change_type="removed",
                )
            )
        elif a_val == b_val:
            unchanged_count += 1
        else:
            delta: float | None = None
            pct_delta: float | None = None
            if (
                compute_numeric_delta
                and isinstance(a_val, (int, float))
                and isinstance(b_val, (int, float))
                and not isinstance(a_val, bool)
                and not isinstance(b_val, bool)
            ):
                delta = round(float(b_val) - float(a_val), 8)
                if a_val != 0:
                    pct_delta = round((delta / abs(float(a_val))) * 100, 2)
            changed.append(
                FieldChange(
                    field=key,
                    old_value=a_val,
                    new_value=b_val,
                    change_type="changed",
                    delta=delta,
                    pct_delta=pct_delta,
                )
            )

    return ComparisonSection(
        added=added,
        removed=removed,
        changed=changed,
        unchanged_count=unchanged_count,
        total_changes=len(added) + len(removed) + len(changed),
    )


def _compare_metadata(run_a: StrategyRun, run_b: StrategyRun) -> ComparisonSection:
    """Compare the scalar metadata fields of two runs."""
    fields: dict[str, tuple[Any, Any]] = {
        "run_type": (run_a.run_type, run_b.run_type),
        "status": (run_a.status, run_b.status),
        "universe_name": (run_a.universe_name, run_b.universe_name),
        "dataset_version": (run_a.dataset_version, run_b.dataset_version),
        "strategy_version_id": (
            str(run_a.strategy_version_id) if run_a.strategy_version_id else None,
            str(run_b.strategy_version_id) if run_b.strategy_version_id else None,
        ),
    }

    changed: list[FieldChange] = []
    unchanged_count = 0

    for field_name, (a_val, b_val) in fields.items():
        if a_val == b_val:
            unchanged_count += 1
        else:
            changed.append(
                FieldChange(
                    field=field_name,
                    old_value=a_val,
                    new_value=b_val,
                    change_type="changed",
                )
            )

    return ComparisonSection(
        added=[],
        removed=[],
        changed=changed,
        unchanged_count=unchanged_count,
        total_changes=len(changed),
    )


def _build_highlighted_changes(
    metadata: ComparisonSection,
    params: ComparisonSection,
    assumptions: ComparisonSection,
    metrics: ComparisonSection,
) -> list[str]:
    """Return human-readable sentences for the most important changed fields.

    Phrasing is directional and factual — no causal or investment language.
    """
    highlights: list[str] = []

    # ---- Important metrics ----
    metric_idx: dict[str, FieldChange] = {
        fc.field: fc
        for fc in (metrics.changed + metrics.added + metrics.removed)
    }
    for key in _IMPORTANT_METRICS:
        fc = metric_idx.get(key)
        if fc is None:
            continue
        if fc.change_type == "added":
            highlights.append(f"{key} added with value {_fmt(fc.new_value)}")
        elif fc.change_type == "removed":
            highlights.append(f"{key} removed (was {_fmt(fc.old_value)})")
        else:
            a_s, b_s = _fmt(fc.old_value), _fmt(fc.new_value)
            if fc.delta is not None:
                direction = "increased" if fc.delta > 0 else "decreased"
                pct_str = (
                    f", {abs(fc.pct_delta):.1f}% change"
                    if fc.pct_delta is not None
                    else ""
                )
                highlights.append(f"{key} {direction} from {a_s} to {b_s}{pct_str}")
            else:
                highlights.append(f"{key} changed from {a_s!r} to {b_s!r}")

    # ---- Important params (combined from params + assumptions sections) ----
    param_idx: dict[str, FieldChange] = {
        fc.field: fc
        for section in (params, assumptions)
        for fc in (section.changed + section.added + section.removed)
    }
    for key in _IMPORTANT_PARAMS:
        fc = param_idx.get(key)
        if fc is None or fc.field in metric_idx:
            # skip if already surfaced via metrics
            continue
        if fc.change_type == "added":
            highlights.append(f"param {key} added ({_fmt(fc.new_value)})")
        elif fc.change_type == "removed":
            highlights.append(f"param {key} removed (was {_fmt(fc.old_value)})")
        else:
            highlights.append(
                f"param {key} changed from {_fmt(fc.old_value)} to {_fmt(fc.new_value)}"
            )

    # ---- Dataset / universe metadata ----
    for fc in metadata.changed:
        if fc.field in ("dataset_version", "universe_name"):
            highlights.append(
                f"{fc.field} changed from {_fmt(fc.old_value)} to {_fmt(fc.new_value)}"
            )

    return highlights


def _build_explanation(
    highlighted: list[str],
    total_changes: int,
    is_same_run: bool,
) -> str:
    """Build a deterministic, hedged plain-language explanation.

    Rules: no "caused", no "because", no "therefore", no investment advice.
    """
    if is_same_run:
        return "Run A and Run B are the same run. No changes to report."
    if total_changes == 0:
        return (
            "Run B is identical to Run A across all tracked dimensions "
            "(params, assumptions, metrics, and metadata)."
        )
    if not highlighted:
        return (
            f"Run B differs from Run A in {total_changes} tracked field(s). "
            "No key performance metrics or recognised parameters changed; "
            "the differences are in other fields."
        )

    tail = (
        "This is a deterministic comparison of logged run data — "
        "changes are noted as observed alongside each other, not as causal claims."
    )
    if len(highlighted) == 1:
        return f"Run B differs from Run A: {highlighted[0]}. {tail}"

    items = "; ".join(highlighted)
    return (
        f"Run B differs from Run A in {len(highlighted)} key area(s): {items}. {tail}"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compare_runs(run_a: StrategyRun, run_b: StrategyRun) -> RunComparisonResponse:
    """Compare two StrategyRun records deterministically.

    Both runs must already be loaded.  This function is pure Python —
    no database access.  The caller is responsible for validating that
    both runs belong to the same strategy.
    """
    is_same_run = run_a.id == run_b.id

    metadata_section = _compare_metadata(run_a, run_b)
    params_section = _compare_dicts(run_a.params_json, run_b.params_json)
    assumptions_section = _compare_dicts(run_a.assumptions_json, run_b.assumptions_json)
    metrics_section = _compare_dicts(
        run_a.metrics_json,
        run_b.metrics_json,
        compute_numeric_delta=True,
    )

    total_changes = (
        metadata_section.total_changes
        + params_section.total_changes
        + assumptions_section.total_changes
        + metrics_section.total_changes
    )

    warnings: list[str] = []
    if run_a.run_type != run_b.run_type:
        warnings.append(
            f"Runs have different types ({run_a.run_type!r} vs {run_b.run_type!r}). "
            "Comparison across run types may not be meaningful."
        )

    highlighted = _build_highlighted_changes(
        metadata_section, params_section, assumptions_section, metrics_section
    )
    explanation = _build_explanation(highlighted, total_changes, is_same_run)

    return RunComparisonResponse(
        strategy_id=str(run_a.strategy_id),
        run_a_id=str(run_a.id),
        run_b_id=str(run_b.id),
        run_a_name=run_a.run_name,
        run_b_name=run_b.run_name,
        run_a_created_at=run_a.created_at,
        run_b_created_at=run_b.created_at,
        is_same_run=is_same_run,
        metadata=metadata_section,
        params=params_section,
        assumptions=assumptions_section,
        metrics=metrics_section,
        highlighted_changes=highlighted,
        deterministic_explanation=explanation,
        warnings=warnings,
        total_changes=total_changes,
    )
