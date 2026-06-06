"""M106 Research Command Center — read-only workspace triage aggregation.

Composes existing read-only services into a single Home-page payload, collapsing
the previous per-strategy N+1 fan-out into one call:

  - :func:`app.services.portfolio_reliability.build_portfolio_reliability`
  - :func:`app.services.lifecycle_pipeline.get_lifecycle_stage_summary`
  - the StrategyReview active-review query (M87)
  - the Alert open-alert query (M11)

CRITICAL: READ-ONLY. No db.add/commit/flush, no migration, no new scoring /
promotion / alert logic. Every sub-section is independently guarded so one
failing subsystem can never break the whole payload — failures degrade to empty
defaults. Deterministic — no AI, no live market data, no trading advice.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

DISCLAIMER = (
    "Command Center prioritizes research governance tasks. "
    "It is not trading advice."
)

# Severity ranking for action / alert sorting (lower = more urgent).
SEVERITY_RANK: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}

# Active strategy-review statuses (mirror strategy_reviews._ACTIVE_STATUSES).
_ACTIVE_REVIEW_STATUSES = ("submitted", "changes_requested")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_command_center(db: Session, *, organization_id=None) -> dict:
    """Build the read-only Command Center workspace-triage payload."""
    # ---- 1. portfolio reliability (composed; never mutate) ----
    try:
        pr = build_portfolio_reliability_safe(db, organization_id=organization_id)
    except Exception:
        pr = {"summary": {}, "strategies": []}
    rows: list[dict] = pr.get("strategies") or []
    summary: dict = pr.get("summary") or {}

    # ---- 2. lifecycle stage summary ----
    try:
        from app.services.lifecycle_pipeline import get_lifecycle_stage_summary

        lifecycle = get_lifecycle_stage_summary(db)
    except Exception:
        lifecycle = {"stages": []}
    lifecycle_summary = lifecycle.get("stages") or []

    # ---- 3 & 4. workspace summary (deterministic counts off the rows) ----
    workspace_summary = _build_workspace_summary(rows, summary)

    # ---- 6. top actions (derived from per-row top_blocker — no N+1) ----
    top_actions = _build_top_actions(rows)

    # ---- 7. strategies needing attention ----
    strategies_needing_attention = _build_attention(rows)

    # ---- 8. pending reviews ----
    pending_reviews = _build_pending_reviews(db)

    # ---- 9. top alerts ----
    top_alerts = _build_top_alerts(db)

    return {
        "workspace_summary": workspace_summary,
        "lifecycle_summary": lifecycle_summary,
        "top_actions": top_actions,
        "strategies_needing_attention": strategies_needing_attention,
        "pending_reviews": pending_reviews,
        "top_alerts": top_alerts,
        "generated_at": _utcnow(),
        "disclaimer": DISCLAIMER,
    }


def build_portfolio_reliability_safe(db: Session, *, organization_id=None) -> dict:
    """Call the portfolio reliability builder with its existing signature."""
    from app.services.portfolio_reliability import build_portfolio_reliability

    return build_portfolio_reliability(db, organization_id=organization_id)


def _build_workspace_summary(rows: list[dict], summary: dict) -> dict:
    strategy_count = summary.get("total_strategies")
    if strategy_count is None:
        strategy_count = len(rows)

    healthy_count = summary.get("healthy_count")
    review_count = summary.get("review_count")
    blocked_count = summary.get("blocked_count")
    # Fall back to deriving from rows if the summary lacks them.
    if healthy_count is None:
        healthy_count = sum(
            1 for r in rows if r.get("health_classification") == "healthy"
        )
    if review_count is None:
        review_count = sum(
            1 for r in rows if r.get("health_classification") == "review"
        )
    if blocked_count is None:
        blocked_count = sum(
            1 for r in rows if r.get("health_classification") == "blocked"
        )

    open_alert_count = sum(int(r.get("open_alert_count") or 0) for r in rows)
    high_critical_alert_count = sum(
        int(r.get("high_critical_alert_count") or 0) for r in rows
    )

    pending_action_count = sum(1 for r in rows if r.get("top_blocker") is not None)
    pending_review_count = sum(1 for r in rows if r.get("pending_review") is not None)
    production_ready_count = int(summary.get("ready_for_production_candidate") or 0)

    return {
        "strategy_count": int(strategy_count or 0),
        "healthy_count": int(healthy_count or 0),
        "review_count": int(review_count or 0),
        "blocked_count": int(blocked_count or 0),
        "open_alert_count": open_alert_count,
        "high_critical_alert_count": high_critical_alert_count,
        "pending_action_count": pending_action_count,
        "pending_review_count": pending_review_count,
        "production_ready_count": production_ready_count,
    }


def _build_top_actions(rows: list[dict]) -> list[dict]:
    actions: list[dict] = []
    for r in rows:
        tb = r.get("top_blocker")
        if not tb:
            continue
        actions.append(
            {
                "strategy_id": str(r.get("strategy_id")),
                "strategy_name": r.get("name"),
                "title": tb.get("title"),
                "severity": tb.get("severity"),
                "category": tb.get("category"),
                "recommended_action": tb.get("recommended_action"),
                "target_tab": tb.get("target_tab"),
            }
        )
    actions.sort(key=lambda a: SEVERITY_RANK.get(a.get("severity"), 99))
    return actions[:5]


def _build_attention(rows: list[dict]) -> list[dict]:
    candidates = [
        r
        for r in rows
        if r.get("health_classification") in ("blocked", "review")
        or int(r.get("high_critical_alert_count") or 0) > 0
        or r.get("pending_review") is not None
    ]

    # blocked first, then review, then others; ties broken by reliability asc.
    health_rank = {"blocked": 0, "review": 1}

    def _key(r: dict):
        score = r.get("reliability_score")
        return (
            health_rank.get(r.get("health_classification"), 2),
            score if score is not None else 999.0,
        )

    candidates.sort(key=_key)

    out: list[dict] = []
    for r in candidates[:8]:
        tb = r.get("top_blocker")
        out.append(
            {
                "strategy_id": str(r.get("strategy_id")),
                "name": r.get("name"),
                "slug": r.get("slug"),
                "lifecycle_stage": r.get("promotion_stage"),
                "health_classification": r.get("health_classification"),
                "reliability_score": r.get("reliability_score"),
                "primary_concern": r.get("primary_concern"),
                "top_blocker_title": tb.get("title") if tb else None,
                "open_alert_count": int(r.get("open_alert_count") or 0),
            }
        )
    return out


def _build_pending_reviews(db: Session) -> list[dict]:
    try:
        from app.models.strategy import Strategy
        from app.models.strategy_review import StrategyReview

        reviews = (
            db.query(StrategyReview)
            .filter(StrategyReview.status.in_(_ACTIVE_REVIEW_STATUSES))
            .order_by(StrategyReview.created_at.desc())
            .limit(5)
            .all()
        )
        if not reviews:
            return []

        # Resolve strategy names in one query to avoid N+1.
        sid_set = {str(r.strategy_id) for r in reviews}
        names: dict[str, str] = {}
        try:
            strat_rows = (
                db.query(Strategy.id, Strategy.name)
                .filter(Strategy.id.in_(sid_set))
                .all()
            )
            names = {str(sid): name for sid, name in strat_rows}
        except Exception:
            names = {}

        out: list[dict] = []
        for r in reviews:
            out.append(
                {
                    "review_id": str(r.id),
                    "strategy_id": str(r.strategy_id),
                    "strategy_name": names.get(str(r.strategy_id)),
                    "target_stage": r.target_stage,
                    "status": r.status,
                    "reviewer_user_id": r.reviewer_user_id,
                }
            )
        return out
    except Exception:
        return []


def _build_top_alerts(db: Session) -> list[dict]:
    try:
        from app.models.alert import Alert

        alerts = (
            db.query(Alert)
            .filter(Alert.status == "open")
            .order_by(Alert.triggered_at.desc())
            .limit(50)
            .all()
        )
        if not alerts:
            return []

        # Rank by severity (critical/high first), then recency (already desc).
        alerts.sort(key=lambda a: SEVERITY_RANK.get(str(a.severity), 99))
        out: list[dict] = []
        for a in alerts[:3]:
            out.append(
                {
                    "id": str(a.id),
                    "title": a.title,
                    "severity": a.severity,
                    "strategy_id": str(a.strategy_id) if a.strategy_id else None,
                    "rule_type": a.rule_type,
                }
            )
        return out
    except Exception:
        return []
