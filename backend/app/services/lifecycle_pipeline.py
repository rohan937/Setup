"""M104 Lifecycle pipeline summary (read-only).

Aggregates the per-strategy research-progression lifecycle
(:func:`app.services.strategy_lifecycle.compute_strategy_lifecycle`) into an
org-/project-level stage-count snapshot for the Home page.

Read-only. No DB mutation, no migration, no lifecycle mutation. Deterministic —
no AI, no live market data, no trading advice.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

DISCLAIMER = (
    "Lifecycle status summarizes research governance readiness. "
    "It is not trading advice."
)

# The 5 canonical DISPLAY stages. The internal "backtest" stage collapses into
# "Backtest Review" for presentation.
DISPLAY_STAGES: list[tuple[str, str]] = [
    ("research", "Research"),
    ("backtest_review", "Backtest Review"),
    ("paper_candidate", "Paper Candidate"),
    ("shadow", "Shadow"),
    ("production_candidate", "Production Candidate"),
]
_DISPLAY_KEYS = [k for k, _ in DISPLAY_STAGES]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_display_stage(raw_stage: str | None) -> str:
    """Map a raw lifecycle stage onto one of the 5 display stages."""
    if raw_stage == "backtest":
        return "backtest_review"
    if raw_stage in _DISPLAY_KEYS:
        return raw_stage
    return "research"


def get_lifecycle_stage_summary(
    db: Session, *, project_id: uuid.UUID | None = None
) -> dict:
    """Return a stage-count summary across non-archived strategies.

    Optionally filtered by *project_id*. Read-only.
    """
    from app.core.constants import StrategyStatus
    from app.models.strategy import Strategy
    from app.services.strategy_lifecycle import compute_strategy_lifecycle

    query = db.query(Strategy).filter(
        Strategy.status != StrategyStatus.archived.value
    )
    if project_id is not None:
        query = query.filter(Strategy.project_id == project_id)
    strategies = query.all()

    counts: dict[str, int] = {k: 0 for k in _DISPLAY_KEYS}
    blocked_counts: dict[str, int] = {k: 0 for k in _DISPLAY_KEYS}
    total = 0
    blocked_total = 0

    for strategy in strategies:
        try:
            lifecycle = compute_strategy_lifecycle(strategy.id, db)
        except Exception:
            continue
        display = _to_display_stage(lifecycle.get("current_stage"))
        counts[display] += 1
        total += 1
        if lifecycle.get("blocked"):
            blocked_counts[display] += 1
            blocked_total += 1

    stages = [
        {
            "key": key,
            "label": label,
            "count": counts[key],
            "blocked_count": blocked_counts[key],
        }
        for key, label in DISPLAY_STAGES
    ]

    return {
        "generated_at": _utcnow(),
        "total_strategies": total,
        "stages": stages,
        "blocked_total": blocked_total,
        "disclaimer": DISCLAIMER,
    }


def get_strategy_lifecycle_pipeline(strategy_id: uuid.UUID, db: Session) -> dict:
    """Reshape a strategy's lifecycle into the 5 DISPLAY stages (M104 shape).

    Thin convenience over :func:`compute_strategy_lifecycle`. Each display stage
    gets a status in {complete, current, next, blocked, locked}. Read-only.

    Raises ValueError if the strategy does not exist.
    """
    from app.services.strategy_lifecycle import compute_strategy_lifecycle

    lifecycle = compute_strategy_lifecycle(strategy_id, db)

    current = _to_display_stage(lifecycle.get("current_stage"))
    raw_next = lifecycle.get("next_stage")
    next_display = _to_display_stage(raw_next) if raw_next else None
    blocked = bool(lifecycle.get("blocked"))
    raw_blocked = lifecycle.get("blocked_stage")
    blocked_display = _to_display_stage(raw_blocked) if raw_blocked else None

    current_idx = _DISPLAY_KEYS.index(current)
    next_idx = _DISPLAY_KEYS.index(next_display) if next_display else None

    stages: list[dict] = []
    for i, (key, label) in enumerate(DISPLAY_STAGES):
        if i < current_idx:
            status = "complete"
        elif i == current_idx:
            status = "current"
        elif blocked and key == blocked_display:
            status = "blocked"
        elif next_idx is not None and i == next_idx:
            status = "next"
        else:
            status = "locked"
        stages.append({"key": key, "label": label, "status": status})

    blockers = lifecycle.get("blockers") or []
    primary_blocker = blockers[0].get("reason") if blockers else None
    suggested = lifecycle.get("suggested_actions") or []
    suggested_action = suggested[0] if suggested else None

    return {
        "strategy_id": str(strategy_id),
        "strategy_name": lifecycle.get("strategy_name"),
        "generated_at": _utcnow(),
        "current_stage": current,
        "next_stage": next_display,
        "blocked": blocked,
        "stages": stages,
        "primary_blocker": primary_blocker,
        "suggested_action": suggested_action,
        "disclaimer": DISCLAIMER,
    }
