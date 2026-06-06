"""Strategy Review service — M87 Strategy Review.

A *strategy review* is a governance promotion request: a submitter asks for a
strategy to be advanced to a ``target_stage`` along the canonical research
lifecycle.  A reviewer approves / rejects / requests changes, and approval
ADVANCES the persisted ``Strategy.lifecycle_stage``.  Every decision is captured
immutably in ``strategy_review_events``.

Distinct from ``ResearchReviewCase`` (issue groupings).

Deterministic governance workflow — no AI, no live market data, no trading
actions.  Every source-service call is wrapped in try/except so one failing
subsystem can never break the checklist.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.constants import ReviewAction, ReviewDecision, ReviewStatus
from app.models.strategy import Strategy
from app.models.strategy_review import (
    StrategyReview,
    StrategyReviewComment,
    StrategyReviewEvent,
)


# ---------------------------------------------------------------------------
# Canonical lifecycle stages (persisted governance stage + review target_stage)
# ---------------------------------------------------------------------------

STAGE_ORDER = [
    "research",
    "backtest",
    "backtest_review",
    "paper_candidate",
    "shadow",
    "production_candidate",
]

STAGE_LABELS = {
    "research": "Research",
    "backtest": "Backtest",
    "backtest_review": "Backtest Review",
    "paper_candidate": "Paper Candidate",
    "shadow": "Shadow",
    "production_candidate": "Production Candidate",
}

DISCLAIMER = "Research governance workflow result, not trading advice."

# Review statuses that count as "active" (an open, undecided review).
_ACTIVE_STATUSES = {str(ReviewStatus.submitted), str(ReviewStatus.changes_requested)}
# Review statuses that count as "open" (can still receive a decision).
_OPEN_STATUSES = {str(ReviewStatus.submitted), str(ReviewStatus.changes_requested)}
# Decided / terminal statuses.
_DECIDED_STATUSES = {str(ReviewStatus.approved), str(ReviewStatus.rejected)}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class BlockedApproval(Exception):
    """Raised when an approval is attempted but required checklist items fail.

    ``.blockers`` carries the list of blocker dicts (title/reason/suggested_action).
    """

    def __init__(self, blockers: list[dict], message: str | None = None):
        self.blockers = blockers
        super().__init__(
            message
            or "Approval blocked: required checklist items are failing or missing."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_ts(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _as_uuid(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def effective_current_stage(db: Session, strategy: Strategy) -> str:
    """Return the persisted governance stage if set, else the computed stage."""
    if strategy.lifecycle_stage:
        return strategy.lifecycle_stage
    try:
        from app.services.strategy_lifecycle import compute_strategy_lifecycle

        lc = compute_strategy_lifecycle(strategy.id, db)
        return lc.get("current_stage") or "research"
    except Exception:
        return "research"


# Promotion-gate target_stage mapping (review target -> promotion_gates stage).
_GATE_STAGE_MAP = {
    "backtest_review": "backtest_review",
    "paper_candidate": "paper_candidate",
    "shadow": "shadow_production",
    "production_candidate": "production_candidate",
}


# ---------------------------------------------------------------------------
# Target-stage requirement policy
# ---------------------------------------------------------------------------
# A checklist item is REQUIRED only when its key appears in the set for the
# target stage. Required items that fail/missing block approval.

_PAPER_CANDIDATE_REQUIRED = [
    "promotion_gates_pass",
    "reliability_report_exists",
    "no_critical_alerts",
    "evidence_fresh",
    "evidence_complete",
    "regression_pass_if_exists",
]

_REQUIRED_BY_STAGE: dict[str, list[str]] = {
    "research": [],
    "backtest": ["has_backtest_run"],
    "backtest_review": ["has_backtest_run", "reliability_score_exists"],
    "paper_candidate": list(_PAPER_CANDIDATE_REQUIRED),
    "shadow": list(_PAPER_CANDIDATE_REQUIRED) + ["has_paper_or_live_run"],
    "production_candidate": (
        list(_PAPER_CANDIDATE_REQUIRED)
        + ["has_paper_or_live_run", "promotion_gates_pass_production"]
    ),
}


# ---------------------------------------------------------------------------
# Individual checklist item builders. Each returns a dict and never raises.
# ---------------------------------------------------------------------------

def _item(
    key: str,
    title: str,
    category: str,
    status: str,
    required: bool,
    detail: str | None = None,
    observed_value: str | None = None,
    suggested_action: str | None = None,
) -> dict:
    return {
        "key": key,
        "title": title,
        "category": category,
        "status": status,
        "required": required,
        "detail": detail,
        "observed_value": observed_value,
        "suggested_action": suggested_action,
    }


def _ck_has_backtest_run(db, strategy_id, required) -> dict:
    try:
        from app.models.strategy_run import StrategyRun

        count = (
            db.query(StrategyRun)
            .filter(
                StrategyRun.strategy_id == strategy_id,
                StrategyRun.run_type.in_(["backtest", "paper", "live"]),
            )
            .count()
        )
        if count > 0:
            return _item(
                "has_backtest_run", "Has Backtest Run", "evidence", "pass",
                required, detail=f"{count} backtest/paper/live run(s) logged.",
                observed_value=str(count),
            )
        return _item(
            "has_backtest_run", "Has Backtest Run", "evidence", "fail", required,
            detail="No backtest, paper, or live run logged.",
            suggested_action="Log a backtest run for this strategy.",
        )
    except Exception:
        return _item(
            "has_backtest_run", "Has Backtest Run", "evidence", "fail", required,
            detail="Run check unavailable.",
        )


def _ck_has_paper_or_live_run(db, strategy_id, required) -> dict:
    try:
        from app.models.strategy_run import StrategyRun

        count = (
            db.query(StrategyRun)
            .filter(
                StrategyRun.strategy_id == strategy_id,
                StrategyRun.run_type.in_(["paper", "live"]),
            )
            .count()
        )
        if count > 0:
            return _item(
                "has_paper_or_live_run", "Has Paper/Live Run", "evidence", "pass",
                required, detail=f"{count} paper/live run(s) logged.",
                observed_value=str(count),
            )
        return _item(
            "has_paper_or_live_run", "Has Paper/Live Run", "evidence", "fail",
            required, detail="No paper or live run logged.",
            suggested_action="Log a paper or live run before this stage.",
        )
    except Exception:
        return _item(
            "has_paper_or_live_run", "Has Paper/Live Run", "evidence", "fail",
            required, detail="Run check unavailable.",
        )


def _ck_reliability_score_exists(db, strategy_id, required) -> dict:
    try:
        from app.models.strategy_reliability_score import StrategyReliabilityScore

        latest = (
            db.query(StrategyReliabilityScore)
            .filter(StrategyReliabilityScore.strategy_id == strategy_id)
            .order_by(StrategyReliabilityScore.generated_at.desc())
            .first()
        )
        if latest is not None:
            obs = (
                f"{latest.overall_score:.0f}"
                if latest.overall_score is not None
                else (latest.status or "computed")
            )
            return _item(
                "reliability_score_exists", "Reliability Score Exists",
                "reliability", "pass", required,
                detail=f"Latest reliability score: {obs} ({latest.status}).",
                observed_value=obs,
            )
        return _item(
            "reliability_score_exists", "Reliability Score Exists", "reliability",
            "missing", required, detail="No reliability score computed.",
            suggested_action="Compute a reliability score for this strategy.",
        )
    except Exception:
        return _item(
            "reliability_score_exists", "Reliability Score Exists", "reliability",
            "missing", required, detail="Reliability score check unavailable.",
        )


def _ck_promotion_gates(db, strategy_id, required, *, key, title, gate_stage) -> dict:
    try:
        from app.services.promotion_gates import evaluate_promotion_gates

        gate = evaluate_promotion_gates(strategy_id, gate_stage, db)
        blocker_count = gate.blocker_count or 0
        req_fail = gate.required_fail_count or 0
        if blocker_count == 0 and req_fail == 0:
            return _item(
                key, title, "governance", "pass", required,
                detail=f"Promotion gates pass (verdict: {gate.promotion_verdict}).",
                observed_value=gate.promotion_verdict,
            )
        blockers = list(gate.blockers or [])
        detail = (
            f"{blocker_count} blocking gate(s), {req_fail} required gate(s) failing "
            f"(verdict: {gate.promotion_verdict})."
        )
        if blockers:
            detail += " " + "; ".join(b[:80] for b in blockers[:3])
        suggested = (
            (gate.suggested_actions or [None])[0]
            or "Resolve blocking promotion gates before approval."
        )
        return _item(
            key, title, "governance", "fail", required,
            detail=detail, observed_value=gate.promotion_verdict,
            suggested_action=suggested,
        )
    except Exception:
        return _item(
            key, title, "governance", "fail", required,
            detail="Promotion gate evaluation unavailable.",
            suggested_action="Resolve blocking promotion gates before approval.",
        )


def _ck_reliability_report_exists(db, strategy_id, required) -> dict:
    try:
        from app.models.report import Report
        from app.models.strategy_run import StrategyRun

        report = (
            db.query(Report)
            .filter(
                Report.strategy_id == strategy_id,
                Report.report_type == "strategy_reliability",
            )
            .order_by(Report.created_at.desc())
            .first()
        )
        if report is None:
            return _item(
                "reliability_report_exists", "Reliability Report Exists",
                "reliability", "missing", required,
                detail="No strategy reliability report generated.",
                suggested_action="Generate a strategy reliability report.",
            )
        latest_run = (
            db.query(StrategyRun)
            .filter(StrategyRun.strategy_id == strategy_id)
            .order_by(StrategyRun.created_at.desc())
            .first()
        )
        rep_at = _normalize_ts(report.generated_at)
        run_at = _normalize_ts(latest_run.created_at) if latest_run else None
        if run_at is None or (rep_at is not None and rep_at >= run_at):
            return _item(
                "reliability_report_exists", "Reliability Report Exists",
                "reliability", "pass", required,
                detail="Reliability report is current with the latest run.",
                observed_value=str(rep_at),
            )
        return _item(
            "reliability_report_exists", "Reliability Report Exists",
            "reliability", "warn", required,
            detail="Reliability report is older than the latest run.",
            observed_value=str(rep_at),
            suggested_action="Regenerate the reliability report after the latest run.",
        )
    except Exception:
        return _item(
            "reliability_report_exists", "Reliability Report Exists",
            "reliability", "missing", required,
            detail="Reliability report check unavailable.",
        )


def _ck_no_critical_alerts(db, strategy_id, required) -> dict:
    try:
        from app.services.alerts import get_strategy_alert_summary

        summary = get_strategy_alert_summary(db, str(strategy_id))
        crit = (summary.get("by_severity") or {}).get("critical", 0)
        if crit == 0:
            return _item(
                "no_critical_alerts", "No Critical Alerts", "alerts", "pass",
                required, detail="No open critical alerts.", observed_value="0",
            )
        return _item(
            "no_critical_alerts", "No Critical Alerts", "alerts", "fail", required,
            detail=f"{crit} open critical alert(s).", observed_value=str(crit),
            suggested_action="Resolve open critical alerts before approval.",
        )
    except Exception:
        return _item(
            "no_critical_alerts", "No Critical Alerts", "alerts", "fail", required,
            detail="Alert check unavailable.",
        )


def _ck_evidence_fresh(db, strategy_id, required) -> dict:
    try:
        from app.services.evidence_freshness import compute_evidence_freshness

        f = compute_evidence_freshness(strategy_id, db)
        status_val = f.freshness_status
        if status_val in ("fresh", "aging"):
            return _item(
                "evidence_fresh", "Evidence Fresh", "freshness", "pass", required,
                detail=f"Evidence freshness: {status_val}.",
                observed_value=status_val,
            )
        return _item(
            "evidence_fresh", "Evidence Fresh", "freshness", "fail", required,
            detail=(
                f"Evidence freshness: {status_val} "
                f"({f.stale_count} stale, {f.missing_count} missing)."
            ),
            observed_value=status_val,
            suggested_action="Refresh stale or missing evidence.",
        )
    except Exception:
        return _item(
            "evidence_fresh", "Evidence Fresh", "freshness", "fail", required,
            detail="Freshness check unavailable.",
        )


def _ck_evidence_complete(db, strategy_id, required) -> dict:
    try:
        from app.models.strategy_run import StrategyRun
        from app.models.strategy_config_snapshot import StrategyConfigSnapshot

        latest_run = (
            db.query(StrategyRun)
            .filter(StrategyRun.strategy_id == strategy_id)
            .order_by(StrategyRun.created_at.desc())
            .first()
        )
        missing: list[str] = []
        if latest_run is None:
            missing = ["dataset", "signal", "universe", "version"]
        else:
            if latest_run.dataset_snapshot_id is None:
                missing.append("dataset")
            if latest_run.signal_snapshot_id is None:
                missing.append("signal")
            if latest_run.universe_snapshot_id is None:
                missing.append("universe")
            if latest_run.strategy_version_id is None:
                missing.append("version")
        has_config = (
            db.query(StrategyConfigSnapshot)
            .filter(StrategyConfigSnapshot.strategy_id == strategy_id)
            .first()
            is not None
        )
        if not has_config:
            missing.append("config")
        if not missing:
            return _item(
                "evidence_complete", "Evidence Complete", "evidence", "pass",
                required,
                detail="Latest run links dataset, signal, universe, version + config.",
                observed_value="complete",
            )
        return _item(
            "evidence_complete", "Evidence Complete", "evidence", "fail", required,
            detail=f"Missing evidence layers: {', '.join(missing)}.",
            observed_value=f"missing: {', '.join(missing)}",
            suggested_action=f"Link the missing evidence: {', '.join(missing)}.",
        )
    except Exception:
        return _item(
            "evidence_complete", "Evidence Complete", "evidence", "fail", required,
            detail="Evidence completeness check unavailable.",
        )


def _ck_regression_pass_if_exists(db, strategy_id, required) -> dict:
    try:
        from app.services.regression_tests import get_regression_test_runs

        runs = get_regression_test_runs(strategy_id, db, limit=1)
        if not runs:
            return _item(
                "regression_pass_if_exists", "Regression Tests Pass", "regression",
                "pass", required, detail="No regression tests configured (n/a).",
                observed_value="no tests",
            )
        latest = runs[0]
        failed = getattr(latest, "failed_count", 0) or 0
        overall = str(getattr(latest, "overall_status", "") or "")
        if failed == 0 and overall not in ("failed",):
            return _item(
                "regression_pass_if_exists", "Regression Tests Pass", "regression",
                "pass", required,
                detail=f"Latest regression run passed (status: {overall}).",
                observed_value=overall or "passed",
            )
        return _item(
            "regression_pass_if_exists", "Regression Tests Pass", "regression",
            "fail", required,
            detail=f"Latest regression run has {failed} failing test(s) (status: {overall}).",
            observed_value=overall or "failed",
            suggested_action="Investigate and resolve failing regression tests.",
        )
    except Exception:
        return _item(
            "regression_pass_if_exists", "Regression Tests Pass", "regression",
            "pass", required, detail="No regression tests configured (n/a).",
        )


# --- Always-shown informational items (required=False) ----------------------

def _info_reliability_value(db, strategy_id) -> dict:
    try:
        from app.models.strategy_reliability_score import StrategyReliabilityScore

        latest = (
            db.query(StrategyReliabilityScore)
            .filter(StrategyReliabilityScore.strategy_id == strategy_id)
            .order_by(StrategyReliabilityScore.generated_at.desc())
            .first()
        )
        if latest is None:
            return _item(
                "reliability_score_value", "Reliability Score", "reliability",
                "missing", False, detail="No reliability score computed.",
            )
        score = (
            f"{latest.overall_score:.0f}"
            if latest.overall_score is not None else "n/a"
        )
        return _item(
            "reliability_score_value", "Reliability Score", "reliability", "pass",
            False, detail=f"Reliability score {score} ({latest.status}).",
            observed_value=score,
        )
    except Exception:
        return _item(
            "reliability_score_value", "Reliability Score", "reliability",
            "missing", False, detail="Reliability score unavailable.",
        )


def _info_backtest_trust(db, strategy_id) -> dict:
    try:
        from app.models.strategy_reliability_score import StrategyReliabilityScore

        latest = (
            db.query(StrategyReliabilityScore)
            .filter(StrategyReliabilityScore.strategy_id == strategy_id)
            .order_by(StrategyReliabilityScore.generated_at.desc())
            .first()
        )
        if latest is None or latest.backtest_trust_score is None:
            return _item(
                "backtest_trust", "Backtest Trust", "reliability", "missing",
                False, detail="No backtest trust score.",
            )
        bt = f"{latest.backtest_trust_score:.0f}"
        return _item(
            "backtest_trust", "Backtest Trust", "reliability", "pass", False,
            detail=f"Backtest trust score {bt}.", observed_value=bt,
        )
    except Exception:
        return _item(
            "backtest_trust", "Backtest Trust", "reliability", "missing", False,
            detail="Backtest trust unavailable.",
        )


def _info_assumption_health(db, strategy_id) -> dict:
    try:
        from app.services.assumption_health import compute_assumption_health

        ah = compute_assumption_health(strategy_id, db)
        status_val = ah.get("status", "missing_evidence")
        return _item(
            "assumption_health", "Assumption Health", "assumptions",
            "pass" if status_val in ("strong", "acceptable") else "warn", False,
            detail=f"Assumption health: {status_val}.", observed_value=status_val,
        )
    except Exception:
        return _item(
            "assumption_health", "Assumption Health", "assumptions", "missing",
            False, detail="Assumption health unavailable.",
        )


def _info_config_guardrails(db, strategy_id) -> dict:
    try:
        from app.services.config_policies import (
            get_config_policies,
            get_config_policy_evaluations,
        )

        sid = str(strategy_id)
        evals = get_config_policy_evaluations(db, sid, limit=1)
        if evals:
            status_val = str(evals[0].overall_status)
        else:
            policies = get_config_policies(db, sid)
            status_val = "not_evaluated" if policies else "no_policy"
        return _item(
            "config_guardrails", "Config Guardrails", "governance",
            "pass" if status_val == "passed" else "warn", False,
            detail=f"Config guardrails: {status_val}.", observed_value=status_val,
        )
    except Exception:
        return _item(
            "config_guardrails", "Config Guardrails", "governance", "missing",
            False, detail="Config guardrails unavailable.",
        )


def _info_evidence_sla(db, strategy_id) -> dict:
    try:
        from app.services.evidence_sla import get_evidence_sla_evaluations

        evals = get_evidence_sla_evaluations(db, str(strategy_id), limit=1)
        if evals:
            status_val = str(evals[0].overall_status)
        else:
            status_val = "not_evaluated"
        return _item(
            "evidence_sla", "Evidence SLA", "freshness",
            "pass" if status_val == "passed" else "warn", False,
            detail=f"Evidence SLA: {status_val}.", observed_value=status_val,
        )
    except Exception:
        return _item(
            "evidence_sla", "Evidence SLA", "freshness", "missing", False,
            detail="Evidence SLA unavailable.",
        )


def _info_open_high_alerts(db, strategy_id) -> dict:
    try:
        from app.services.alerts import get_strategy_alert_summary

        summary = get_strategy_alert_summary(db, str(strategy_id))
        high = (summary.get("by_severity") or {}).get("high", 0)
        return _item(
            "open_high_alerts", "Open High Alerts", "alerts",
            "pass" if high == 0 else "warn", False,
            detail=f"{high} open high-severity alert(s).", observed_value=str(high),
        )
    except Exception:
        return _item(
            "open_high_alerts", "Open High Alerts", "alerts", "missing", False,
            detail="Alert check unavailable.",
        )


def _info_freshness_status(db, strategy_id) -> dict:
    try:
        from app.services.evidence_freshness import compute_evidence_freshness

        f = compute_evidence_freshness(strategy_id, db)
        return _item(
            "freshness_status", "Freshness Status", "freshness",
            "pass" if f.freshness_status in ("fresh", "aging") else "warn", False,
            detail=f"Overall freshness: {f.freshness_status}.",
            observed_value=f.freshness_status,
        )
    except Exception:
        return _item(
            "freshness_status", "Freshness Status", "freshness", "missing", False,
            detail="Freshness unavailable.",
        )


def _info_readiness_verdict(db, strategy_id) -> dict:
    try:
        from app.services.strategy_readiness import compute_strategy_readiness

        r = compute_strategy_readiness(strategy_id, db)
        verdict = r.readiness_verdict
        ok = verdict not in ("blocked", "under_instrumented")
        return _item(
            "readiness_verdict", "Readiness Verdict", "readiness",
            "pass" if ok else "warn", False,
            detail=f"Readiness verdict: {verdict}.", observed_value=verdict,
        )
    except Exception:
        return _item(
            "readiness_verdict", "Readiness Verdict", "readiness", "missing", False,
            detail="Readiness unavailable.",
        )


# ---------------------------------------------------------------------------
# Checklist assembly
# ---------------------------------------------------------------------------

def build_review_checklist(db: Session, strategy_id, target_stage: str) -> dict:
    """Build the deterministic review checklist for advancing to *target_stage*.

    Never raises on subsystem failure: every source-service call is guarded.
    """
    sid = _as_uuid(strategy_id)
    strategy = db.query(Strategy).filter(Strategy.id == sid).first()
    current_stage = (
        effective_current_stage(db, strategy) if strategy is not None else None
    )

    required_keys = set(_REQUIRED_BY_STAGE.get(target_stage, []))

    def req(key: str) -> bool:
        return key in required_keys

    items: list[dict] = []

    # --- Requirement-driven items (added when relevant to this target) ------
    # has_backtest_run: relevant for backtest, backtest_review (+always informative)
    items.append(_ck_has_backtest_run(db, sid, req("has_backtest_run")))

    # reliability_score_exists
    items.append(_ck_reliability_score_exists(db, sid, req("reliability_score_exists")))

    # promotion gates for the (mapped) target stage
    gate_stage = _GATE_STAGE_MAP.get(target_stage)
    if gate_stage is not None:
        items.append(
            _ck_promotion_gates(
                db, sid, req("promotion_gates_pass"),
                key="promotion_gates_pass",
                title=f"Promotion Gates Pass ({STAGE_LABELS.get(target_stage, target_stage)})",
                gate_stage=gate_stage,
            )
        )

    # promotion_gates_pass_production (only meaningful for production_candidate)
    if "promotion_gates_pass_production" in required_keys or target_stage == "production_candidate":
        items.append(
            _ck_promotion_gates(
                db, sid, req("promotion_gates_pass_production"),
                key="promotion_gates_pass_production",
                title="Promotion Gates Pass (Production)",
                gate_stage="production_candidate",
            )
        )

    items.append(_ck_reliability_report_exists(db, sid, req("reliability_report_exists")))
    items.append(_ck_no_critical_alerts(db, sid, req("no_critical_alerts")))
    items.append(_ck_evidence_fresh(db, sid, req("evidence_fresh")))
    items.append(_ck_evidence_complete(db, sid, req("evidence_complete")))
    items.append(_ck_regression_pass_if_exists(db, sid, req("regression_pass_if_exists")))
    items.append(_ck_has_paper_or_live_run(db, sid, req("has_paper_or_live_run")))

    # --- Always-shown informational items (required=False) ------------------
    items.append(_info_backtest_trust(db, sid))
    items.append(_info_assumption_health(db, sid))
    items.append(_info_config_guardrails(db, sid))
    items.append(_info_evidence_sla(db, sid))
    items.append(_info_open_high_alerts(db, sid))
    items.append(_info_freshness_status(db, sid))
    items.append(_info_readiness_verdict(db, sid))

    # De-duplicate by key (a required item may overlap an informational one);
    # keep the first (requirement-driven) occurrence.
    seen: set[str] = set()
    deduped: list[dict] = []
    for it in items:
        if it["key"] in seen:
            continue
        seen.add(it["key"])
        deduped.append(it)
    items = deduped

    # can_approve = no required item is fail/missing.
    blockers: list[dict] = []
    for it in items:
        if it["required"] and it["status"] in ("fail", "missing"):
            blockers.append({
                "title": it["title"],
                "reason": it.get("detail") or f"{it['title']} is {it['status']}.",
                "suggested_action": it.get("suggested_action"),
            })
    can_approve = len(blockers) == 0

    return {
        "target_stage": target_stage,
        "current_stage": current_stage,
        "items": items,
        "can_approve": can_approve,
        "blockers": blockers,
        "generated_at": _utcnow(),
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# Evidence snapshot (captured at submission time)
# ---------------------------------------------------------------------------

def _build_evidence_snapshot(db: Session, strategy_id, target_stage: str) -> dict:
    """Capture a point-in-time evidence snapshot for the review record."""
    sid = _as_uuid(strategy_id)
    snapshot: dict = {
        "captured_at": _utcnow().isoformat(),
        "target_stage": target_stage,
    }

    try:
        from app.services.promotion_gates import evaluate_promotion_gates

        gate_stage = _GATE_STAGE_MAP.get(target_stage, "paper_candidate")
        gate = evaluate_promotion_gates(sid, gate_stage, db)
        snapshot["promotion_gates"] = {
            "target_stage": gate_stage,
            "verdict": gate.promotion_verdict,
            "gate_score": gate.gate_score,
            "blocker_count": gate.blocker_count,
            "required_fail_count": gate.required_fail_count,
            "blockers": list(gate.blockers or []),
        }
    except Exception:
        snapshot["promotion_gates"] = None

    try:
        from app.services.evidence_freshness import compute_evidence_freshness

        f = compute_evidence_freshness(sid, db)
        snapshot["evidence_freshness"] = {
            "freshness_status": f.freshness_status,
            "stale_count": f.stale_count,
            "missing_count": f.missing_count,
            "aging_count": f.aging_count,
        }
    except Exception:
        snapshot["evidence_freshness"] = None

    try:
        from app.services.alerts import get_strategy_alert_summary

        snapshot["alerts"] = get_strategy_alert_summary(db, str(sid))
    except Exception:
        snapshot["alerts"] = None

    try:
        from app.models.strategy_reliability_score import StrategyReliabilityScore

        latest = (
            db.query(StrategyReliabilityScore)
            .filter(StrategyReliabilityScore.strategy_id == sid)
            .order_by(StrategyReliabilityScore.generated_at.desc())
            .first()
        )
        if latest is not None:
            snapshot["reliability_score"] = {
                "overall_score": latest.overall_score,
                "status": latest.status,
                "backtest_trust_score": latest.backtest_trust_score,
            }
        else:
            snapshot["reliability_score"] = None
    except Exception:
        snapshot["reliability_score"] = None

    try:
        from app.services.assumption_health import compute_assumption_health

        ah = compute_assumption_health(sid, db)
        snapshot["assumption_health"] = {
            "status": ah.get("status"),
            "overall_assumption_score": ah.get("overall_assumption_score"),
        }
    except Exception:
        snapshot["assumption_health"] = None

    return snapshot


# ---------------------------------------------------------------------------
# Event helper
# ---------------------------------------------------------------------------

def _record_event(
    db: Session,
    review_id,
    actor_user_id: str | None,
    action: str,
    note: str | None = None,
    metadata: dict | None = None,
) -> StrategyReviewEvent:
    event = StrategyReviewEvent(
        review_id=str(review_id),
        actor_user_id=actor_user_id,
        action=str(action),
        note=note,
        metadata_json=metadata,
    )
    db.add(event)
    return event


# ---------------------------------------------------------------------------
# Org resolution (mirror alerts._org_id_for_strategy)
# ---------------------------------------------------------------------------

def _org_uuid_for_strategy(db: Session, strategy_id):
    from app.models.project import Project

    row = (
        db.query(Project.organization_id)
        .join(Strategy, Strategy.project_id == Project.id)
        .filter(Strategy.id == strategy_id)
        .first()
    )
    return row[0] if row is not None else None


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------

def submit_strategy_review(
    db: Session,
    strategy_id,
    target_stage: str,
    user_id: str | None,
    as_draft: bool = False,
) -> StrategyReview:
    """Create a new strategy review (draft or submitted) for *target_stage*."""
    if target_stage not in STAGE_ORDER:
        raise ValueError(f"Invalid target_stage: {target_stage!r}")

    sid = _as_uuid(strategy_id)
    strategy = db.query(Strategy).filter(Strategy.id == sid).first()
    if strategy is None:
        raise ValueError("Strategy not found")

    # DEDUP: refuse a second active review for the same (strategy, target_stage).
    existing = (
        db.query(StrategyReview)
        .filter(
            StrategyReview.strategy_id == str(sid),
            StrategyReview.target_stage == target_stage,
            StrategyReview.status.in_(list(_ACTIVE_STATUSES)),
        )
        .first()
    )
    if existing is not None:
        raise ValueError(
            "an active review already exists for this strategy and target stage"
        )

    now = _utcnow()
    checklist = build_review_checklist(db, sid, target_stage)
    snapshot = _build_evidence_snapshot(db, sid, target_stage)
    current_stage = effective_current_stage(db, strategy)

    review = StrategyReview(
        strategy_id=str(sid),
        target_stage=target_stage,
        current_stage_at_submission=current_stage,
        status=str(ReviewStatus.draft) if as_draft else str(ReviewStatus.submitted),
        submitted_by_user_id=user_id,
        submitted_at=None if as_draft else now,
        checklist_json=_jsonable(checklist),
        evidence_snapshot_json=snapshot,
    )
    db.add(review)
    db.flush()

    _record_event(db, review.id, user_id, str(ReviewAction.created))
    if not as_draft:
        _record_event(db, review.id, user_id, str(ReviewAction.submitted))
    db.flush()

    return review


def submit_existing(db: Session, review_id, user_id: str | None) -> StrategyReview:
    """Transition a draft review to submitted; refresh the checklist."""
    review = db.query(StrategyReview).filter(StrategyReview.id == str(review_id)).first()
    if review is None:
        raise ValueError("Review not found")
    if str(review.status) != str(ReviewStatus.draft):
        raise ValueError("Only draft reviews can be submitted")

    now = _utcnow()
    review.status = str(ReviewStatus.submitted)
    review.submitted_at = now
    if review.submitted_by_user_id is None:
        review.submitted_by_user_id = user_id
    review.checklist_json = _jsonable(
        build_review_checklist(db, review.strategy_id, review.target_stage)
    )
    db.flush()
    _record_event(db, review.id, user_id, str(ReviewAction.submitted))
    db.flush()
    return review


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

def approve_strategy_review(
    db: Session,
    review_id,
    actor_user_id: str | None,
    actor_is_owner: bool = False,
) -> StrategyReview:
    """Approve a review; on success advance the strategy lifecycle stage.

    Raises:
        ValueError       — review missing or not in an approvable state.
        PermissionError  — self-approval by a non-owner.
        BlockedApproval  — required checklist items fail/missing.
    """
    review = db.query(StrategyReview).filter(StrategyReview.id == str(review_id)).first()
    if review is None:
        raise ValueError("Review not found")
    if str(review.status) not in _OPEN_STATUSES:
        raise ValueError("Review is not open for a decision")

    # Self-approval policy.
    if (
        review.submitted_by_user_id is not None
        and actor_user_id is not None
        and review.submitted_by_user_id == actor_user_id
        and not actor_is_owner
    ):
        raise PermissionError(
            "You cannot approve your own review; a different reviewer must approve. "
            "(Owners may override.)"
        )

    # Recompute checklist live; block if any required item fails.
    checklist = build_review_checklist(db, review.strategy_id, review.target_stage)
    if not checklist["can_approve"]:
        raise BlockedApproval(checklist["blockers"])

    now = _utcnow()
    strategy = (
        db.query(Strategy).filter(Strategy.id == _as_uuid(review.strategy_id)).first()
    )
    from_stage = effective_current_stage(db, strategy) if strategy is not None else None

    review.status = str(ReviewStatus.approved)
    review.decision = str(ReviewDecision.approved)
    review.decided_at = now
    review.reviewer_user_id = actor_user_id
    review.checklist_json = _jsonable(checklist)

    # Advance the persisted governance lifecycle stage.
    if strategy is not None:
        strategy.lifecycle_stage = review.target_stage
    db.flush()

    _record_event(db, review.id, actor_user_id, str(ReviewAction.approved))
    _record_event(
        db, review.id, actor_user_id, str(ReviewAction.lifecycle_advanced),
        metadata={"from": from_stage, "to": review.target_stage},
    )
    db.flush()
    return review


def reject_strategy_review(
    db: Session,
    review_id,
    actor_user_id: str | None,
    note: str | None,
) -> StrategyReview:
    """Reject a review. No lifecycle change."""
    review = db.query(StrategyReview).filter(StrategyReview.id == str(review_id)).first()
    if review is None:
        raise ValueError("Review not found")
    if str(review.status) not in _OPEN_STATUSES:
        raise ValueError("Review is not open for a decision")

    now = _utcnow()
    review.status = str(ReviewStatus.rejected)
    review.decision = str(ReviewDecision.rejected)
    review.decision_note = note
    review.decided_at = now
    review.reviewer_user_id = actor_user_id
    db.flush()
    _record_event(db, review.id, actor_user_id, str(ReviewAction.rejected), note=note)
    db.flush()
    return review


def request_changes(
    db: Session,
    review_id,
    actor_user_id: str | None,
    note: str | None,
) -> StrategyReview:
    """Request changes on a review. No lifecycle change; not final."""
    review = db.query(StrategyReview).filter(StrategyReview.id == str(review_id)).first()
    if review is None:
        raise ValueError("Review not found")
    if str(review.status) not in _OPEN_STATUSES:
        raise ValueError("Review is not open for a decision")

    review.status = str(ReviewStatus.changes_requested)
    review.decision = str(ReviewDecision.changes_requested)
    review.decision_note = note
    review.reviewer_user_id = actor_user_id
    # decided_at stays null — not a final decision.
    db.flush()
    _record_event(
        db, review.id, actor_user_id, str(ReviewAction.changes_requested), note=note
    )
    db.flush()
    return review


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def add_review_comment(
    db: Session,
    review_id,
    author_user_id: str | None,
    comment: str,
) -> StrategyReviewComment:
    review = db.query(StrategyReview).filter(StrategyReview.id == str(review_id)).first()
    if review is None:
        raise ValueError("Review not found")

    row = StrategyReviewComment(
        review_id=str(review_id),
        author_user_id=author_user_id,
        comment=comment,
    )
    db.add(row)
    db.flush()
    _record_event(
        db, review_id, author_user_id, str(ReviewAction.commented),
        note=comment[:500],
    )
    db.flush()
    return row


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def get_strategy_reviews(db: Session, strategy_id) -> list[StrategyReview]:
    sid = _as_uuid(strategy_id)
    return (
        db.query(StrategyReview)
        .filter(StrategyReview.strategy_id == str(sid))
        .order_by(StrategyReview.created_at.desc())
        .all()
    )


def _reviews_by_status(
    db: Session, statuses: list[str], organization_id=None
) -> list[StrategyReview]:
    q = db.query(StrategyReview).filter(StrategyReview.status.in_(statuses))
    reviews = q.order_by(StrategyReview.created_at.desc()).all()
    if organization_id is None:
        return reviews
    # Scope to the org via the strategy's project.
    out: list[StrategyReview] = []
    for r in reviews:
        try:
            org = _org_uuid_for_strategy(db, _as_uuid(r.strategy_id))
        except Exception:
            org = None
        if org is not None and str(org) == str(organization_id):
            out.append(r)
    return out


def get_pending_reviews(db: Session, organization_id=None) -> list[StrategyReview]:
    return _reviews_by_status(
        db, list(_ACTIVE_STATUSES), organization_id=organization_id
    )


def get_decisions(db: Session, organization_id=None) -> list[StrategyReview]:
    return _reviews_by_status(
        db, list(_DECIDED_STATUSES), organization_id=organization_id
    )


def get_review_detail(db: Session, review_id) -> dict | None:
    review = db.query(StrategyReview).filter(StrategyReview.id == str(review_id)).first()
    if review is None:
        return None
    comments = (
        db.query(StrategyReviewComment)
        .filter(StrategyReviewComment.review_id == str(review_id))
        .order_by(StrategyReviewComment.created_at.asc())
        .all()
    )
    events = (
        db.query(StrategyReviewEvent)
        .filter(StrategyReviewEvent.review_id == str(review_id))
        .order_by(StrategyReviewEvent.created_at.asc())
        .all()
    )
    checklist = build_review_checklist(db, review.strategy_id, review.target_stage)
    return {
        "review": review,
        "checklist": checklist,
        "comments": comments,
        "events": events,
    }


# ---------------------------------------------------------------------------
# Review packet
# ---------------------------------------------------------------------------

def _jsonable(obj):
    """Recursively convert datetimes/UUIDs to JSON-serialisable primitives."""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    return obj


def generate_review_packet(db: Session, review_id, fmt: str = "json") -> dict:
    """Assemble a full review packet (json or markdown)."""
    detail = get_review_detail(db, review_id)
    if detail is None:
        raise ValueError("Review not found")

    review: StrategyReview = detail["review"]
    checklist = detail["checklist"]
    comments = detail["comments"]
    events = detail["events"]

    sid = _as_uuid(review.strategy_id)
    strategy = db.query(Strategy).filter(Strategy.id == sid).first()

    # Promotion gates
    promotion_gates = None
    try:
        from app.services.promotion_gates import evaluate_promotion_gates

        gate_stage = _GATE_STAGE_MAP.get(review.target_stage, "paper_candidate")
        gate = evaluate_promotion_gates(sid, gate_stage, db)
        promotion_gates = {
            "target_stage": gate_stage,
            "verdict": gate.promotion_verdict,
            "gate_score": gate.gate_score,
            "blocker_count": gate.blocker_count,
            "blockers": list(gate.blockers or []),
        }
    except Exception:
        pass

    reliability_score = None
    try:
        from app.models.strategy_reliability_score import StrategyReliabilityScore

        latest = (
            db.query(StrategyReliabilityScore)
            .filter(StrategyReliabilityScore.strategy_id == sid)
            .order_by(StrategyReliabilityScore.generated_at.desc())
            .first()
        )
        if latest is not None:
            reliability_score = {
                "overall_score": latest.overall_score,
                "status": latest.status,
                "backtest_trust_score": latest.backtest_trust_score,
            }
    except Exception:
        pass

    evidence_freshness = None
    try:
        from app.services.evidence_freshness import compute_evidence_freshness

        f = compute_evidence_freshness(sid, db)
        evidence_freshness = {
            "freshness_status": f.freshness_status,
            "stale_count": f.stale_count,
            "missing_count": f.missing_count,
            "aging_count": f.aging_count,
        }
    except Exception:
        pass

    open_alerts = None
    try:
        from app.services.alerts import get_strategy_alert_summary

        open_alerts = get_strategy_alert_summary(db, str(sid))
    except Exception:
        pass

    regression_status = None
    try:
        from app.services.regression_tests import get_regression_test_runs

        runs = get_regression_test_runs(sid, db, limit=1)
        if runs:
            regression_status = {
                "overall_status": runs[0].overall_status,
                "failed_count": runs[0].failed_count,
                "passed_count": runs[0].passed_count,
            }
        else:
            regression_status = {"overall_status": "no_tests"}
    except Exception:
        pass

    guardrails_status = None
    try:
        from app.services.config_policies import get_config_policy_evaluations

        evals = get_config_policy_evaluations(db, str(sid), limit=1)
        guardrails_status = str(evals[0].overall_status) if evals else "not_evaluated"
    except Exception:
        pass

    sla_status = None
    try:
        from app.services.evidence_sla import get_evidence_sla_evaluations

        evals = get_evidence_sla_evaluations(db, str(sid), limit=1)
        sla_status = str(evals[0].overall_status) if evals else "not_evaluated"
    except Exception:
        pass

    packet = {
        "review_id": str(review.id),
        "strategy": {
            "strategy_id": str(sid),
            "name": strategy.name if strategy else None,
            "slug": strategy.slug if strategy else None,
        },
        "current_stage": review.current_stage_at_submission,
        "target_stage": review.target_stage,
        "status": review.status,
        "decision": review.decision,
        "decision_note": review.decision_note,
        "submitted_by_user_id": review.submitted_by_user_id,
        "reviewer_user_id": review.reviewer_user_id,
        "submitted_at": review.submitted_at,
        "decided_at": review.decided_at,
        "checklist": checklist,
        "promotion_gates": promotion_gates,
        "reliability_score": reliability_score,
        "evidence_freshness": evidence_freshness,
        "open_alerts": open_alerts,
        "regression_status": regression_status,
        "guardrails_status": guardrails_status,
        "evidence_sla_status": sla_status,
        "comments": [
            {
                "author_user_id": c.author_user_id,
                "comment": c.comment,
                "created_at": c.created_at,
            }
            for c in comments
        ],
        "decision_log": [
            {
                "action": e.action,
                "actor_user_id": e.actor_user_id,
                "note": e.note,
                "metadata": e.metadata_json,
                "created_at": e.created_at,
            }
            for e in events
        ],
        "disclaimer": DISCLAIMER,
    }

    short = str(review.id).replace("-", "")[:8]
    date = _utcnow().strftime("%Y-%m-%d")

    if fmt == "markdown":
        content = render_review_packet_markdown(packet)
        filename = f"review-packet-{short}-{date}.md"
        return {"filename": filename, "format": "markdown", "content": content}

    content = json.dumps(_jsonable(packet), default=str, indent=2)
    filename = f"review-packet-{short}-{date}.json"
    return {"filename": filename, "format": "json", "content": content}


def _fmt(v) -> str:
    if v is None:
        return "—"
    return str(v)


def render_review_packet_markdown(packet: dict) -> str:
    lines: list[str] = []
    strat = packet.get("strategy", {})
    lines.append(f"# Strategy Review Packet — {_fmt(strat.get('name'))}")
    lines.append("")
    lines.append(f"- Review ID: {_fmt(packet.get('review_id'))}")
    lines.append(f"- Current stage: {_fmt(packet.get('current_stage'))}")
    lines.append(f"- Target stage: {_fmt(packet.get('target_stage'))}")
    lines.append(f"- Status: {_fmt(packet.get('status'))}")
    lines.append(f"- Decision: {_fmt(packet.get('decision'))}")
    lines.append(f"- Submitted by: {_fmt(packet.get('submitted_by_user_id'))}")
    lines.append(f"- Reviewer: {_fmt(packet.get('reviewer_user_id'))}")
    lines.append(f"- Submitted at: {_fmt(packet.get('submitted_at'))}")
    lines.append(f"- Decided at: {_fmt(packet.get('decided_at'))}")
    lines.append("")

    # Checklist
    checklist = packet.get("checklist", {}) or {}
    lines.append("## Checklist")
    lines.append("")
    lines.append(f"_Can approve: {_fmt(checklist.get('can_approve'))}_")
    lines.append("")
    lines.append("| Item | Category | Required | Status | Detail |")
    lines.append("| --- | --- | --- | --- | --- |")
    for it in checklist.get("items", []):
        lines.append(
            f"| {_fmt(it.get('title'))} | {_fmt(it.get('category'))} | "
            f"{_fmt(it.get('required'))} | {_fmt(it.get('status'))} | "
            f"{_fmt(it.get('detail'))} |"
        )
    lines.append("")

    blockers = checklist.get("blockers", [])
    if blockers:
        lines.append("### Blockers")
        lines.append("")
        for b in blockers:
            lines.append(
                f"- **{_fmt(b.get('title'))}**: {_fmt(b.get('reason'))} "
                f"(action: {_fmt(b.get('suggested_action'))})"
            )
        lines.append("")

    # Promotion gates
    pg = packet.get("promotion_gates")
    lines.append("## Promotion Gates")
    lines.append("")
    if pg:
        lines.append(f"- Target: {_fmt(pg.get('target_stage'))}")
        lines.append(f"- Verdict: {_fmt(pg.get('verdict'))}")
        lines.append(f"- Gate score: {_fmt(pg.get('gate_score'))}")
        lines.append(f"- Blocker count: {_fmt(pg.get('blocker_count'))}")
        for b in pg.get("blockers", []):
            lines.append(f"  - {_fmt(b)}")
    else:
        lines.append("- Unavailable.")
    lines.append("")

    # Reliability / freshness / alerts / regression / guardrails / SLA
    rs = packet.get("reliability_score")
    lines.append("## Reliability Score")
    lines.append("")
    if rs:
        lines.append(
            f"- Overall: {_fmt(rs.get('overall_score'))} ({_fmt(rs.get('status'))}), "
            f"backtest trust: {_fmt(rs.get('backtest_trust_score'))}"
        )
    else:
        lines.append("- No reliability score.")
    lines.append("")

    ef = packet.get("evidence_freshness")
    lines.append("## Evidence Freshness")
    lines.append("")
    if ef:
        lines.append(
            f"- {_fmt(ef.get('freshness_status'))} "
            f"({_fmt(ef.get('stale_count'))} stale, "
            f"{_fmt(ef.get('missing_count'))} missing, "
            f"{_fmt(ef.get('aging_count'))} aging)"
        )
    else:
        lines.append("- Unavailable.")
    lines.append("")

    oa = packet.get("open_alerts")
    lines.append("## Open Alerts")
    lines.append("")
    if oa:
        bs = oa.get("by_severity", {}) or {}
        lines.append(
            f"- Open: {_fmt(oa.get('open'))} "
            f"(critical {_fmt(bs.get('critical'))}, high {_fmt(bs.get('high'))})"
        )
    else:
        lines.append("- Unavailable.")
    lines.append("")

    reg = packet.get("regression_status")
    lines.append("## Regression Status")
    lines.append("")
    lines.append(f"- {_fmt(reg.get('overall_status') if reg else None)}")
    lines.append("")

    lines.append("## Guardrails & SLA")
    lines.append("")
    lines.append(f"- Config guardrails: {_fmt(packet.get('guardrails_status'))}")
    lines.append(f"- Evidence SLA: {_fmt(packet.get('evidence_sla_status'))}")
    lines.append("")

    # Comments
    lines.append("## Comments")
    lines.append("")
    comments = packet.get("comments", [])
    if comments:
        for c in comments:
            lines.append(
                f"- ({_fmt(c.get('created_at'))}) {_fmt(c.get('author_user_id'))}: "
                f"{_fmt(c.get('comment'))}"
            )
    else:
        lines.append("- No comments.")
    lines.append("")

    # Decision log
    lines.append("## Decision Log")
    lines.append("")
    for e in packet.get("decision_log", []):
        lines.append(
            f"- ({_fmt(e.get('created_at'))}) **{_fmt(e.get('action'))}** "
            f"by {_fmt(e.get('actor_user_id'))}"
            + (f" — {_fmt(e.get('note'))}" if e.get("note") else "")
        )
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"_{packet.get('disclaimer', DISCLAIMER)}_")
    lines.append("")
    return "\n".join(lines)
