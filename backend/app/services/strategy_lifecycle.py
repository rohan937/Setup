"""M76 Strategy Lifecycle inference.

Infers a strategy's position along the research progression lifecycle and what
blocks it from advancing — reusing the promotion-gate stage inference and the
M74 action queue (so blockers stay consistent with the rest of the product).

Deterministic. No AI, no external data, no trading actions.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

# Canonical lifecycle stages, in order.
_STAGES: list[tuple[str, str]] = [
    ("research", "Research"),
    ("backtest", "Backtest"),
    ("backtest_review", "Backtest Review"),
    ("paper_candidate", "Paper Candidate"),
    ("shadow", "Shadow"),
    ("production_candidate", "Production Candidate"),
]
_STAGE_KEYS = [k for k, _ in _STAGES]
_STAGE_LABEL = {k: label for k, label in _STAGES}

# Action-queue categories that count as progression blockers.
_BLOCKER_CATEGORIES = {
    "readiness", "governance", "assumptions", "freshness", "run_quality", "evidence",
}
_BLOCKER_SEVERITIES = {"critical", "high", "medium"}
_BLOCKER_STATUSES = {"blocked", "pending"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_strategy_lifecycle(strategy_id: uuid.UUID, db: Session) -> dict:
    """Return the inferred lifecycle for *strategy_id*.

    Raises ValueError if the strategy does not exist.
    """
    from app.models.strategy import Strategy
    from app.models.strategy_run import StrategyRun

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError("Strategy not found")

    runs = (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(StrategyRun.created_at.desc())
        .all()
    )
    run_types = {r.run_type for r in runs}
    has_backtest = "backtest" in run_types
    has_paper = "paper" in run_types
    has_live = "live" in run_types

    # --- Stage inference -------------------------------------------------
    gate_current = None
    gate_verdict = None
    try:
        from app.services.promotion_gates import evaluate_promotion_gates

        gate = evaluate_promotion_gates(strategy_id, "production_candidate", db)
        gate_current = getattr(gate, "current_stage", None)
        gate_verdict = getattr(gate, "promotion_verdict", None)
    except Exception:
        gate = None

    readiness_verdict = None
    try:
        from app.services.strategy_readiness import compute_strategy_readiness

        readiness = compute_strategy_readiness(strategy_id, db)
        readiness_verdict = (getattr(readiness, "readiness_verdict", "") or "").lower()
    except Exception:
        readiness = None

    current = _infer_current_stage(
        has_runs=bool(runs),
        has_backtest=has_backtest,
        has_paper=has_paper,
        has_live=has_live,
        gate_current=gate_current,
        gate_verdict=gate_verdict,
        readiness_verdict=readiness_verdict,
    )
    current_idx = _STAGE_KEYS.index(current)
    next_stage = _STAGE_KEYS[current_idx + 1] if current_idx + 1 < len(_STAGE_KEYS) else None

    # --- Blockers (reuse the M74 action queue) ---------------------------
    blockers = _collect_blockers(strategy_id, db)
    blocked = bool(blockers) and next_stage is not None
    blocked_stage = next_stage if blocked else None

    # --- Stage states ----------------------------------------------------
    stages = []
    for i, (key, label) in enumerate(_STAGES):
        if i < current_idx:
            state = "completed"
        elif i == current_idx:
            state = "current"
        elif key == blocked_stage:
            state = "blocked"
        else:
            state = "upcoming"
        stages.append({"key": key, "label": label, "index": i, "state": state})

    # --- Suggested actions (distinct labels from blockers) ---------------
    suggested: list[str] = []
    for b in blockers:
        if b["action_label"] not in suggested:
            suggested.append(b["action_label"])
    suggested = suggested[:5]

    summary = _build_summary(
        strategy.name, current, next_stage, blocked, blockers,
    )

    return {
        "strategy_id": str(strategy_id),
        "strategy_name": strategy.name,
        "generated_at": _utcnow(),
        "stages": stages,
        "current_stage": current,
        "current_stage_label": _STAGE_LABEL[current],
        "next_stage": next_stage,
        "next_stage_label": _STAGE_LABEL[next_stage] if next_stage else None,
        "blocked": blocked,
        "blocked_stage": blocked_stage,
        "blocked_stage_label": _STAGE_LABEL[blocked_stage] if blocked_stage else None,
        "blockers": blockers,
        "suggested_actions": suggested,
        "deterministic_summary": summary,
        "disclaimer": (
            "Lifecycle stage is inferred from research evidence. It is not a "
            "trading recommendation."
        ),
    }


def _infer_current_stage(
    *,
    has_runs: bool,
    has_backtest: bool,
    has_paper: bool,
    has_live: bool,
    gate_current: str | None,
    gate_verdict: str | None,
    readiness_verdict: str | None,
) -> str:
    """Deterministically map runs + readiness + promotion gates onto a stage.

    Progression is conservative: a backtest run only advances past *Backtest*
    once readiness says the evidence is ready for review.
    """
    if not has_runs:
        return "research"

    # Production candidate only when the production gate actually passes.
    if gate_verdict in ("pass", "conditional_pass") and gate_current == "production_candidate":
        return "production_candidate"

    if has_live or gate_current == "shadow_production":
        return "shadow"
    if has_paper or gate_current == "paper_candidate":
        return "paper_candidate"

    if has_backtest:
        # Advance to review only when readiness confirms the evidence is ready.
        if readiness_verdict in (
            "ready_for_backtest_review",
            "ready_for_paper_trading_consideration",
        ):
            return "backtest_review"
        return "backtest"
    return "research"


def _collect_blockers(strategy_id: uuid.UUID, db: Session) -> list[dict]:
    """Derive progression blockers from the action queue (consistent with M74)."""
    try:
        from app.services.action_queue import get_action_queue

        queue = get_action_queue(db, strategy_id, limit=25)
    except Exception:
        return []

    blockers: list[dict] = []
    for it in queue.get("items", []):
        if (
            it.get("category") in _BLOCKER_CATEGORIES
            and it.get("severity") in _BLOCKER_SEVERITIES
            and it.get("status") in _BLOCKER_STATUSES
        ):
            related_run_id = (
                it.get("related_object_id")
                if it.get("related_object_type") == "strategy_run"
                else None
            )
            blockers.append({
                "reason": it.get("title", ""),
                "detail": it.get("why_it_matters", ""),
                "severity": it.get("severity", "medium"),
                "action_type": it.get("action_type", "navigate"),
                "action_label": it.get("action_label", "Review"),
                "target_tab": it.get("target_tab"),
                "related_run_id": related_run_id,
            })
    return blockers[:6]


def _build_summary(
    name: str, current: str, next_stage: str | None, blocked: bool, blockers: list[dict],
) -> str:
    parts = [f"{name}: currently at {_STAGE_LABEL[current]}"]
    if next_stage:
        parts.append(f"next recommended stage is {_STAGE_LABEL[next_stage]}")
    if blocked and blockers:
        parts.append(f"blocked — {blockers[0]['reason'].lower()}")
    elif next_stage:
        parts.append("no progression blockers detected")
    return ". ".join(parts) + "."
