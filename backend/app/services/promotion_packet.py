"""Promotion Review Packet service (M94).

Builds a comprehensive Promotion Review Packet that extends the existing
review packet (generate_review_packet) with M92/M93/M88 data.

Language policy:
  Use: "logged", "observed", "noted"
  Never: "fraud", "falsified", "better strategy", "should trade"
  Always include disclaimer.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Disclaimer
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "This packet is a deterministic research governance summary. "
    "It is not trading advice."
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_GATE_STAGE_MAP = {
    "backtest_review": "backtest_review",
    "paper_candidate": "paper_candidate",
    "shadow": "shadow_production",
    "production_candidate": "production_candidate",
}


def _as_uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    return str(v)


def _jsonable(obj: Any) -> Any:
    """Recursively convert non-JSON-serialisable values to strings."""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(i) for i in obj]
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    return obj


# ---------------------------------------------------------------------------
# Section builders — each wrapped in try/except, returns None on failure
# ---------------------------------------------------------------------------


def _build_strategy_summary(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    target_stage: str | None,
) -> dict | None:
    try:
        from app.models.project import Project
        from app.models.strategy import Strategy
        from app.services.strategy_reviews import effective_current_stage
        from app.core.constants import LIFECYCLE_STAGES

        strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
        if strategy is None:
            return None

        project = db.query(Project).filter(Project.id == strategy.project_id).first()
        project_name = project.name if project else None

        current_stage = effective_current_stage(db, strategy)

        # Infer next stage if not supplied
        if target_stage is None:
            try:
                idx = LIFECYCLE_STAGES.index(current_stage)
                inferred = LIFECYCLE_STAGES[idx + 1] if idx + 1 < len(LIFECYCLE_STAGES) else current_stage
            except (ValueError, IndexError):
                inferred = LIFECYCLE_STAGES[-1]
        else:
            inferred = target_stage

        return {
            "name": strategy.name,
            "slug": strategy.slug,
            "asset_class": strategy.asset_class,
            "status": strategy.status,
            "project_name": project_name,
            "current_stage": current_stage,
            "target_stage": inferred,
            "strategy_id": str(strategy_id),
        }
    except Exception:
        return None


def _build_promotion_context(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    review_id: Any | None,
    target_stage: str | None,
) -> dict | None:
    try:
        from app.services.promotion_gates import evaluate_promotion_gates
        from app.services.strategy_readiness import compute_strategy_readiness

        # Review fields
        review_status = None
        review_decision = None
        reviewer_user_id = None
        submitted_by_user_id = None
        decision_note = None

        if review_id is not None:
            from app.models.strategy_review import StrategyReview

            review = (
                db.query(StrategyReview)
                .filter(StrategyReview.id == str(review_id))
                .first()
            )
            if review is not None:
                review_status = review.status
                review_decision = review.decision
                reviewer_user_id = review.reviewer_user_id
                submitted_by_user_id = review.submitted_by_user_id
                decision_note = review.decision_note

        # Promotion gates
        gate_stage = _GATE_STAGE_MAP.get(target_stage or "", "paper_candidate")
        gate_verdict = None
        gate_score = None
        gate_blocker_count = None
        gate_blockers: list = []
        try:
            gate = evaluate_promotion_gates(strategy_id, gate_stage, db)
            gate_verdict = gate.promotion_verdict
            gate_score = gate.gate_score
            gate_blocker_count = gate.blocker_count
            gate_blockers = list(gate.blockers or [])
        except Exception:
            pass

        # Readiness
        readiness_verdict = None
        readiness_label = None
        try:
            r = compute_strategy_readiness(strategy_id, db)
            readiness_verdict = r.get("verdict") if isinstance(r, dict) else getattr(r, "verdict", None)
            readiness_label = r.get("label") if isinstance(r, dict) else getattr(r, "label", None)
        except Exception:
            pass

        return {
            "review_id": str(review_id) if review_id is not None else None,
            "review_status": review_status,
            "review_decision": review_decision,
            "reviewer_user_id": reviewer_user_id,
            "submitted_by_user_id": submitted_by_user_id,
            "decision_note": decision_note,
            "gate_stage": gate_stage,
            "gate_verdict": gate_verdict,
            "gate_score": gate_score,
            "gate_blocker_count": gate_blocker_count,
            "gate_blockers": gate_blockers,
            "readiness_verdict": readiness_verdict,
            "readiness_label": readiness_label,
        }
    except Exception:
        return None


def _build_reliability_score(strategy_id: uuid.UUID, db: Session) -> dict | None:
    try:
        from app.models.strategy_reliability_score import StrategyReliabilityScore

        scores = (
            db.query(StrategyReliabilityScore)
            .filter(StrategyReliabilityScore.strategy_id == strategy_id)
            .order_by(StrategyReliabilityScore.generated_at.desc())
            .limit(2)
            .all()
        )
        if not scores:
            return None

        latest = scores[0]
        previous = scores[1] if len(scores) > 1 else None

        recent_delta = None
        if previous is not None and latest.overall_score is not None and previous.overall_score is not None:
            recent_delta = round(latest.overall_score - previous.overall_score, 2)

        return {
            "overall_score": latest.overall_score,
            "status": latest.status,
            "backtest_trust_score": latest.backtest_trust_score,
            "data_evidence_score": latest.data_evidence_score,
            "signal_evidence_score": latest.signal_evidence_score,
            "activity_score": latest.strategy_activity_score,
            "recent_delta": recent_delta,
        }
    except Exception:
        return None


def _build_evidence_coverage(strategy_id: uuid.UUID, db: Session) -> dict | None:
    try:
        from app.services.evidence_freshness import compute_evidence_freshness
        from app.models.strategy_reliability_score import StrategyReliabilityScore

        freshness_status = None
        stale_count = None
        missing_count = None
        aging_count = None
        try:
            f = compute_evidence_freshness(strategy_id, db)
            freshness_status = f.freshness_status
            stale_count = f.stale_count
            missing_count = f.missing_count
            aging_count = f.aging_count
        except Exception:
            pass

        evidence_coverage_score = None
        try:
            latest = (
                db.query(StrategyReliabilityScore)
                .filter(StrategyReliabilityScore.strategy_id == strategy_id)
                .order_by(StrategyReliabilityScore.generated_at.desc())
                .first()
            )
            if latest is not None:
                # Use data_evidence_score as a proxy for evidence_coverage_score
                evidence_coverage_score = latest.data_evidence_score
        except Exception:
            pass

        return {
            "freshness_status": freshness_status,
            "stale_count": stale_count,
            "missing_count": missing_count,
            "aging_count": aging_count,
            "evidence_coverage_score": evidence_coverage_score,
        }
    except Exception:
        return None


def _build_backtest_trust(strategy_id: uuid.UUID, db: Session) -> dict | None:
    try:
        from app.models.backtest_audit import BacktestAudit
        from app.models.backtest_issue import BacktestIssue
        from app.models.strategy_run import StrategyRun

        audit = (
            db.query(BacktestAudit)
            .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
            .filter(StrategyRun.strategy_id == strategy_id)
            .order_by(BacktestAudit.created_at.desc())
            .first()
        )
        if audit is None:
            return {"trust_score": None, "overall_status": None, "cost_realism_score": None,
                    "fill_realism_score": None, "summary": None, "top_issues": []}

        top_issues = (
            db.query(BacktestIssue)
            .filter(BacktestIssue.backtest_audit_id == audit.id)
            .order_by(BacktestIssue.created_at.asc())
            .limit(5)
            .all()
        )

        return {
            "trust_score": audit.trust_score,
            "overall_status": audit.overall_status,
            "cost_realism_score": audit.cost_realism_score,
            "fill_realism_score": audit.fill_realism_score,
            "summary": audit.summary,
            "top_issues": [
                {"title": issue.title, "severity": issue.severity}
                for issue in top_issues
            ],
        }
    except Exception:
        return None


def _build_backtest_reality(strategy_id: uuid.UUID, db: Session) -> dict | None:
    try:
        from app.services.backtest_reality_score import compute_backtest_reality_check

        data = compute_backtest_reality_check(strategy_id, db)
        return {
            "backtest_reality_score": data.backtest_reality_score,
            "verdict": data.verdict,
            "severity": data.severity,
            "primary_concern": data.primary_concern,
            "top_concerns": list(data.top_concerns[:3]),
            "suggested_actions": list(data.suggested_actions[:3]),
        }
    except Exception:
        return None


def _build_evidence_verification(strategy_id: uuid.UUID, db: Session) -> dict | None:
    try:
        from app.services.evidence_verification import verify_strategy_evidence

        data = verify_strategy_evidence(strategy_id, db)

        fail_check_count = sum(1 for c in (data.checks or []) if c.status == "fail")
        warning_check_count = sum(1 for c in (data.checks or []) if c.status == "warning")

        root_hash_short = (data.root_hash or "")[:16] or None

        return {
            "verification_score": data.verification_score,
            "verdict": data.verdict,
            "chain_status": data.chain_status,
            "root_hash": root_hash_short,
            "time_consistency_warnings": list((data.time_consistency_warnings or [])[:2]),
            "link_consistency_warnings": list((data.link_consistency_warnings or [])[:2]),
            "fail_check_count": fail_check_count,
            "warning_check_count": warning_check_count,
        }
    except Exception:
        return None


def _build_shadow_monitor(strategy_id: uuid.UUID, db: Session) -> dict | None:
    try:
        from app.services.shadow_monitor import compare_backtest_to_paper, get_latest_live_like_run

        has_paper_run = False
        try:
            paper_run = get_latest_live_like_run(strategy_id, db)
            has_paper_run = paper_run is not None
        except Exception:
            pass

        verdict = None
        drift_score = None
        severity = None
        primary_concern = None
        has_shadow_run = False

        try:
            shadow_data = compare_backtest_to_paper(strategy_id, db)
            verdict = shadow_data.verdict
            drift_score = shadow_data.drift_score
            severity = shadow_data.severity
            primary_concern = shadow_data.primary_concern
            has_shadow_run = shadow_data.comparison_run_id is not None
        except Exception:
            pass

        return {
            "has_paper_run": has_paper_run,
            "has_shadow_run": has_shadow_run,
            "verdict": verdict,
            "drift_score": drift_score,
            "severity": severity,
            "primary_concern": primary_concern,
        }
    except Exception:
        return None


def _build_regression_tests(strategy_id: uuid.UUID, db: Session) -> dict | None:
    try:
        from app.services.regression_tests import get_regression_test_runs, get_regression_tests

        runs = get_regression_test_runs(strategy_id, db, limit=1)
        test_count = 0
        try:
            all_tests = get_regression_tests(strategy_id, db)
            test_count = len(all_tests)
        except Exception:
            pass

        has_tests = test_count > 0 or bool(runs)

        if runs:
            run = runs[0]
            return {
                "has_tests": has_tests,
                "test_count": test_count,
                "latest_run_status": run.overall_status,
                "failed_count": run.failed_count,
                "passed_count": run.passed_count,
                "skipped_count": getattr(run, "skipped_count", None),
            }
        return {
            "has_tests": has_tests,
            "test_count": test_count,
            "latest_run_status": "no_runs",
            "failed_count": None,
            "passed_count": None,
            "skipped_count": None,
        }
    except Exception:
        return None


def _build_config_guardrails(strategy_id: uuid.UUID, db: Session) -> dict | None:
    try:
        from app.services.config_policies import get_config_policy_evaluations

        evals = get_config_policy_evaluations(db, str(strategy_id), limit=1)
        if not evals:
            return {"evaluated": False, "overall_status": "not_evaluated"}

        ev = evals[0]
        violation_count = getattr(ev, "violation_count", None)
        return {
            "evaluated": True,
            "overall_status": str(ev.overall_status),
            "violation_count": violation_count,
        }
    except Exception:
        return None


def _build_assumption_health(strategy_id: uuid.UUID, db: Session) -> dict | None:
    try:
        from app.services.assumption_health import compute_assumption_health
        from app.services.evidence_sla import get_evidence_sla_evaluations

        assumption_health_status = None
        assumption_health_score = None
        try:
            ah = compute_assumption_health(strategy_id, db)
            if isinstance(ah, dict):
                assumption_health_status = ah.get("status")
                assumption_health_score = ah.get("score")
            else:
                assumption_health_status = getattr(ah, "status", None)
                assumption_health_score = getattr(ah, "score", None)
        except Exception:
            pass

        evidence_sla_status = None
        try:
            sla_evals = get_evidence_sla_evaluations(db, str(strategy_id), limit=1)
            evidence_sla_status = str(sla_evals[0].overall_status) if sla_evals else "not_evaluated"
        except Exception:
            pass

        return {
            "assumption_health_status": assumption_health_status,
            "assumption_health_score": assumption_health_score,
            "evidence_sla_status": evidence_sla_status,
        }
    except Exception:
        return None


def _build_alerts_and_blockers(strategy_id: uuid.UUID, db: Session) -> dict | None:
    try:
        from app.services.alerts import get_strategy_alert_summary
        from app.models.alert import Alert

        summary = get_strategy_alert_summary(db, str(strategy_id))
        open_count = summary.get("open", 0) if isinstance(summary, dict) else 0
        by_severity = summary.get("by_severity", {}) if isinstance(summary, dict) else {}
        critical_count = by_severity.get("critical", 0)
        high_count = by_severity.get("high", 0)

        top_alerts: list[dict] = []
        try:
            alerts = (
                db.query(Alert)
                .filter(
                    Alert.strategy_id == strategy_id,
                    Alert.status == "open",
                    Alert.severity.in_(["critical", "high"]),
                )
                .order_by(Alert.triggered_at.desc())
                .limit(3)
                .all()
            )
            top_alerts = [
                {"title": a.title, "severity": a.severity, "rule_type": a.rule_type}
                for a in alerts
            ]
        except Exception:
            pass

        return {
            "open_count": open_count,
            "critical_count": critical_count,
            "high_count": high_count,
            "top_alerts": top_alerts,
        }
    except Exception:
        return None


def _build_run_history(strategy_id: uuid.UUID, db: Session) -> list | None:
    try:
        from app.models.strategy_run import StrategyRun

        runs = (
            db.query(StrategyRun)
            .filter(StrategyRun.strategy_id == strategy_id)
            .order_by(StrategyRun.created_at.desc())
            .limit(5)
            .all()
        )

        result = []
        for run in runs:
            metrics = run.metrics_json or {}
            result.append({
                "run_name": run.run_name,
                "run_type": run.run_type,
                "status": run.status,
                "metrics": {
                    "sharpe": metrics.get("sharpe"),
                    "annual_return": metrics.get("annual_return"),
                    "max_drawdown": metrics.get("max_drawdown"),
                    "volatility": metrics.get("volatility"),
                },
                "created_at": run.created_at,
            })
        return result
    except Exception:
        return None


def _build_reviewer_signoff(
    review_id: Any | None,
    db: Session,
) -> dict | None:
    try:
        if review_id is None:
            return {
                "reviewer_user_id": None,
                "decision": None,
                "decision_note": None,
                "decided_at": None,
                "comments": [],
                "pending_signoff": True,
            }

        from app.models.strategy_review import StrategyReview, StrategyReviewComment

        review = (
            db.query(StrategyReview)
            .filter(StrategyReview.id == str(review_id))
            .first()
        )
        if review is None:
            return {
                "reviewer_user_id": None,
                "decision": None,
                "decision_note": None,
                "decided_at": None,
                "comments": [],
                "pending_signoff": True,
            }

        comments = (
            db.query(StrategyReviewComment)
            .filter(StrategyReviewComment.review_id == str(review_id))
            .order_by(StrategyReviewComment.created_at.asc())
            .limit(3)
            .all()
        )

        return {
            "reviewer_user_id": review.reviewer_user_id,
            "decision": review.decision,
            "decision_note": review.decision_note,
            "decided_at": review.decided_at,
            "comments": [
                {
                    "author_user_id": c.author_user_id,
                    "comment": c.comment,
                    "created_at": c.created_at,
                }
                for c in comments
            ],
            "pending_signoff": review.decision is None,
        }
    except Exception:
        return None


def _build_decision_log(
    review_id: Any | None,
    strategy_id: uuid.UUID,
    db: Session,
) -> list | None:
    try:
        entries: list[dict] = []

        if review_id is not None:
            from app.models.strategy_review import StrategyReviewEvent

            review_events = (
                db.query(StrategyReviewEvent)
                .filter(StrategyReviewEvent.review_id == str(review_id))
                .order_by(StrategyReviewEvent.created_at.asc())
                .all()
            )
            for ev in review_events:
                entries.append({
                    "action": ev.action,
                    "actor_user_id": ev.actor_user_id,
                    "note": ev.note,
                    "created_at": ev.created_at,
                })

        # Audit timeline events for stage transitions
        try:
            from app.models.audit_timeline_event import AuditTimelineEvent

            timeline_events = (
                db.query(AuditTimelineEvent)
                .filter(
                    AuditTimelineEvent.strategy_id == strategy_id,
                    AuditTimelineEvent.event_type.contains("stage"),
                )
                .order_by(AuditTimelineEvent.event_time.asc())
                .limit(20)
                .all()
            )
            for ev in timeline_events:
                entries.append({
                    "action": ev.event_type,
                    "actor_user_id": None,
                    "note": ev.title,
                    "created_at": ev.event_time,
                })
        except Exception:
            pass

        # Sort combined log by created_at ascending
        entries.sort(key=lambda x: x.get("created_at") or datetime.min.replace(tzinfo=timezone.utc))
        return entries
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_promotion_packet(
    strategy_id: Any,
    db: Session,
    *,
    target_stage: str | None = None,
    review_id: Any | None = None,
) -> dict:
    """Build a comprehensive Promotion Review Packet for a strategy.

    All sections are individually guarded; a failure in one section yields
    None for that section rather than aborting the whole packet.
    """
    sid = _as_uuid(strategy_id)

    # Section 1 — strategy summary (also determines resolved target_stage)
    strategy_summary = _build_strategy_summary(sid, db, target_stage=target_stage)
    resolved_target_stage = target_stage
    if strategy_summary is not None:
        resolved_target_stage = strategy_summary.get("target_stage", target_stage)

    # Section 2 — promotion context
    promotion_context = _build_promotion_context(
        sid, db, review_id=review_id, target_stage=resolved_target_stage
    )

    # Section 3 — reliability score
    reliability_score = _build_reliability_score(sid, db)

    # Section 4 — evidence coverage
    evidence_coverage = _build_evidence_coverage(sid, db)

    # Section 5 — backtest trust
    backtest_trust = _build_backtest_trust(sid, db)

    # Section 6 — backtest reality
    backtest_reality = _build_backtest_reality(sid, db)

    # Section 7 — evidence verification
    evidence_verification = _build_evidence_verification(sid, db)

    # Section 8 — shadow monitor
    shadow_monitor = _build_shadow_monitor(sid, db)

    # Section 9 — regression tests
    regression_tests = _build_regression_tests(sid, db)

    # Section 10 — config guardrails
    config_guardrails = _build_config_guardrails(sid, db)

    # Section 11 — assumption health
    assumption_health = _build_assumption_health(sid, db)

    # Section 12 — alerts and blockers
    alerts_and_blockers = _build_alerts_and_blockers(sid, db)

    # Section 13 — run history
    run_history = _build_run_history(sid, db)

    # Section 14 — reviewer signoff
    reviewer_signoff = _build_reviewer_signoff(review_id, db)

    # Section 15 — decision log
    decision_log = _build_decision_log(review_id, sid, db)

    return {
        "packet_version": "1.0",
        "strategy_id": str(sid),
        "target_stage": resolved_target_stage,
        "review_id": str(review_id) if review_id is not None else None,
        "generated_at": _utcnow().isoformat(),
        "strategy_summary": strategy_summary,
        "promotion_context": promotion_context,
        "reliability_score": reliability_score,
        "evidence_coverage": evidence_coverage,
        "backtest_trust": backtest_trust,
        "backtest_reality": backtest_reality,
        "evidence_verification": evidence_verification,
        "shadow_monitor": shadow_monitor,
        "regression_tests": regression_tests,
        "config_guardrails": config_guardrails,
        "assumption_health": assumption_health,
        "alerts_and_blockers": alerts_and_blockers,
        "run_history": run_history,
        "reviewer_signoff": reviewer_signoff,
        "decision_log": decision_log,
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_promotion_packet_markdown(packet: dict) -> str:  # noqa: C901
    lines: list[str] = []

    ss = packet.get("strategy_summary") or {}
    strat_name = _fmt(ss.get("name"))
    generated_at = _fmt(packet.get("generated_at"))
    target_stage = _fmt(packet.get("target_stage"))

    lines.append(f"# Strategy Promotion Review Packet — {strat_name}")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Strategy | {strat_name} |")
    lines.append(f"| Strategy ID | {_fmt(packet.get('strategy_id'))} |")
    lines.append(f"| Target Stage | {target_stage} |")
    lines.append(f"| Generated At | {generated_at} |")
    lines.append(f"| Packet Version | {_fmt(packet.get('packet_version'))} |")
    lines.append(f"| Review ID | {_fmt(packet.get('review_id'))} |")
    lines.append("")

    # --- 1. Strategy Summary ---
    lines.append("## 1. Strategy Summary")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("| --- | --- |")
    for key in ("slug", "asset_class", "status", "project_name", "current_stage", "target_stage"):
        lines.append(f"| {key.replace('_', ' ').title()} | {_fmt(ss.get(key))} |")
    lines.append("")

    # --- 2. Promotion Context ---
    pc = packet.get("promotion_context") or {}
    lines.append("## 2. Promotion Context")
    lines.append("")
    lines.append(f"- Gate stage: {_fmt(pc.get('gate_stage'))}")
    lines.append(f"- Gate verdict: **{_fmt(pc.get('gate_verdict'))}**")
    lines.append(f"- Gate score: {_fmt(pc.get('gate_score'))}")
    lines.append(f"- Blockers: {_fmt(pc.get('gate_blocker_count'))}")
    for b in (pc.get("gate_blockers") or []):
        lines.append(f"  - {_fmt(b)}")
    lines.append(f"- Readiness verdict: {_fmt(pc.get('readiness_verdict'))}")
    lines.append(f"- Readiness label: {_fmt(pc.get('readiness_label'))}")
    lines.append(f"- Review status: {_fmt(pc.get('review_status'))}")
    lines.append(f"- Review decision: {_fmt(pc.get('review_decision'))}")
    lines.append(f"- Reviewer: {_fmt(pc.get('reviewer_user_id'))}")
    lines.append("")

    # --- 3. Reliability Score ---
    rs = packet.get("reliability_score") or {}
    lines.append("## 3. Reliability Score")
    lines.append("")
    lines.append("| Component | Score |")
    lines.append("| --- | --- |")
    lines.append(f"| Overall | {_fmt(rs.get('overall_score'))} ({_fmt(rs.get('status'))}) |")
    lines.append(f"| Backtest Trust | {_fmt(rs.get('backtest_trust_score'))} |")
    lines.append(f"| Data Evidence | {_fmt(rs.get('data_evidence_score'))} |")
    lines.append(f"| Signal Evidence | {_fmt(rs.get('signal_evidence_score'))} |")
    lines.append(f"| Activity | {_fmt(rs.get('activity_score'))} |")
    lines.append(f"| Recent Delta | {_fmt(rs.get('recent_delta'))} |")
    lines.append("")

    # --- 4. Evidence Coverage ---
    ec = packet.get("evidence_coverage") or {}
    lines.append("## 4. Evidence Coverage")
    lines.append("")
    lines.append(f"- Freshness status: {_fmt(ec.get('freshness_status'))}")
    lines.append(f"- Stale: {_fmt(ec.get('stale_count'))}")
    lines.append(f"- Missing: {_fmt(ec.get('missing_count'))}")
    lines.append(f"- Aging: {_fmt(ec.get('aging_count'))}")
    lines.append(f"- Coverage score: {_fmt(ec.get('evidence_coverage_score'))}")
    lines.append("")

    # --- 5. Backtest Trust ---
    bt = packet.get("backtest_trust") or {}
    lines.append("## 5. Backtest Trust")
    lines.append("")
    lines.append(f"- Trust score: {_fmt(bt.get('trust_score'))}")
    lines.append(f"- Status: {_fmt(bt.get('overall_status'))}")
    lines.append(f"- Cost realism: {_fmt(bt.get('cost_realism_score'))}")
    lines.append(f"- Fill realism: {_fmt(bt.get('fill_realism_score'))}")
    lines.append(f"- Summary: {_fmt(bt.get('summary'))}")
    top_issues = bt.get("top_issues") or []
    if top_issues:
        lines.append("")
        lines.append("| Issue | Severity |")
        lines.append("| --- | --- |")
        for issue in top_issues:
            lines.append(f"| {_fmt(issue.get('title'))} | {_fmt(issue.get('severity'))} |")
    lines.append("")

    # --- 6. Backtest Reality Check ---
    br = packet.get("backtest_reality") or {}
    lines.append("## 6. Backtest Reality Check")
    lines.append("")
    lines.append(f"- Score: {_fmt(br.get('backtest_reality_score'))}")
    lines.append(f"- Verdict: **{_fmt(br.get('verdict'))}**")
    lines.append(f"- Severity: {_fmt(br.get('severity'))}")
    lines.append(f"- Primary concern: {_fmt(br.get('primary_concern'))}")
    top_concerns = br.get("top_concerns") or []
    if top_concerns:
        lines.append("")
        lines.append("Top concerns:")
        for c in top_concerns:
            lines.append(f"- {_fmt(c)}")
    suggested_actions = br.get("suggested_actions") or []
    if suggested_actions:
        lines.append("")
        lines.append("Suggested actions:")
        for a in suggested_actions:
            lines.append(f"- {_fmt(a)}")
    lines.append("")

    # --- 7. Evidence Verification ---
    ev = packet.get("evidence_verification") or {}
    lines.append("## 7. Evidence Verification")
    lines.append("")
    lines.append(f"- Score: {_fmt(ev.get('verification_score'))}")
    lines.append(f"- Verdict: **{_fmt(ev.get('verdict'))}**")
    lines.append(f"- Chain status: {_fmt(ev.get('chain_status'))}")
    lines.append(f"- Root hash (first 16): {_fmt(ev.get('root_hash'))}")
    lines.append(f"- Fail checks: {_fmt(ev.get('fail_check_count'))}")
    lines.append(f"- Warning checks: {_fmt(ev.get('warning_check_count'))}")
    tc_warns = ev.get("time_consistency_warnings") or []
    if tc_warns:
        lines.append("")
        lines.append("Time-consistency warnings:")
        for w in tc_warns:
            lines.append(f"- {_fmt(w)}")
    lc_warns = ev.get("link_consistency_warnings") or []
    if lc_warns:
        lines.append("")
        lines.append("Link-consistency warnings:")
        for w in lc_warns:
            lines.append(f"- {_fmt(w)}")
    lines.append("")

    # --- 8. Shadow / Paper Monitoring ---
    sm = packet.get("shadow_monitor") or {}
    lines.append("## 8. Shadow / Paper Monitoring")
    lines.append("")
    lines.append(f"- Paper run present: {_fmt(sm.get('has_paper_run'))}")
    lines.append(f"- Shadow run present: {_fmt(sm.get('has_shadow_run'))}")
    lines.append(f"- Verdict: **{_fmt(sm.get('verdict'))}**")
    lines.append(f"- Drift score: {_fmt(sm.get('drift_score'))}")
    lines.append(f"- Primary concern: {_fmt(sm.get('primary_concern'))}")
    lines.append("")

    # --- 9. Regression Tests ---
    rt = packet.get("regression_tests") or {}
    lines.append("## 9. Regression Tests")
    lines.append("")
    lines.append(f"- Tests defined: {_fmt(rt.get('test_count'))}")
    lines.append(f"- Latest run status: {_fmt(rt.get('latest_run_status'))}")
    lines.append(f"- Passed: {_fmt(rt.get('passed_count'))}")
    lines.append(f"- Failed: {_fmt(rt.get('failed_count'))}")
    lines.append("")

    # --- 10. Config Guardrails ---
    cg = packet.get("config_guardrails") or {}
    lines.append("## 10. Config Guardrails")
    lines.append("")
    lines.append(f"- Evaluated: {_fmt(cg.get('evaluated'))}")
    lines.append(f"- Status: {_fmt(cg.get('overall_status'))}")
    lines.append("")

    # --- 11. Assumption Health & Evidence SLA ---
    ah = packet.get("assumption_health") or {}
    lines.append("## 11. Assumption Health & Evidence SLA")
    lines.append("")
    lines.append(f"- Assumption health status: {_fmt(ah.get('assumption_health_status'))}")
    lines.append(f"- Assumption health score: {_fmt(ah.get('assumption_health_score'))}")
    lines.append(f"- Evidence SLA status: {_fmt(ah.get('evidence_sla_status'))}")
    lines.append("")

    # --- 12. Alerts and Blockers ---
    ab = packet.get("alerts_and_blockers") or {}
    lines.append("## 12. Alerts and Blockers")
    lines.append("")
    lines.append(f"- Open alerts: {_fmt(ab.get('open_count'))}")
    lines.append(f"- Critical: {_fmt(ab.get('critical_count'))}")
    lines.append(f"- High: {_fmt(ab.get('high_count'))}")
    top_alerts = ab.get("top_alerts") or []
    if top_alerts:
        lines.append("")
        lines.append("| Title | Severity | Rule Type |")
        lines.append("| --- | --- | --- |")
        for a in top_alerts:
            lines.append(f"| {_fmt(a.get('title'))} | {_fmt(a.get('severity'))} | {_fmt(a.get('rule_type'))} |")
    gate_blockers = (packet.get("promotion_context") or {}).get("gate_blockers") or []
    if gate_blockers:
        lines.append("")
        lines.append("Gate blockers:")
        for b in gate_blockers:
            lines.append(f"- {_fmt(b)}")
    lines.append("")

    # --- 13. Run History ---
    rh = packet.get("run_history") or []
    lines.append("## 13. Run History")
    lines.append("")
    if rh:
        lines.append("| Name | Type | Sharpe | Return | Max DD | Date |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for run in rh:
            metrics = run.get("metrics") or {}
            lines.append(
                f"| {_fmt(run.get('run_name'))} "
                f"| {_fmt(run.get('run_type'))} "
                f"| {_fmt(metrics.get('sharpe'))} "
                f"| {_fmt(metrics.get('annual_return'))} "
                f"| {_fmt(metrics.get('max_drawdown'))} "
                f"| {_fmt(run.get('created_at'))} |"
            )
    else:
        lines.append("- No runs logged.")
    lines.append("")

    # --- 14. Reviewer Sign-Off ---
    rsf = packet.get("reviewer_signoff") or {}
    lines.append("## 14. Reviewer Sign-Off")
    lines.append("")
    if rsf.get("decision") is not None:
        lines.append(f"- Decision: **{_fmt(rsf.get('decision'))}**")
        lines.append(f"- Reviewer: {_fmt(rsf.get('reviewer_user_id'))}")
        lines.append(f"- Note: {_fmt(rsf.get('decision_note'))}")
        lines.append(f"- Date: {_fmt(rsf.get('decided_at'))}")
        comments = rsf.get("comments") or []
        if comments:
            lines.append("")
            lines.append("Comments:")
            for c in comments:
                lines.append(
                    f"- ({_fmt(c.get('created_at'))}) "
                    f"{_fmt(c.get('author_user_id'))}: "
                    f"{_fmt(c.get('comment'))}"
                )
    else:
        lines.append(
            "Reviewer: ___________  Decision: [ ] Approved [ ] Changes Requested [ ] Rejected"
        )
        lines.append("")
        lines.append("Date: ___________  Signature: ___________")
    lines.append("")

    # --- 15. Decision Log ---
    dl = packet.get("decision_log") or []
    lines.append("## 15. Decision Log")
    lines.append("")
    if dl:
        lines.append("| Action | Actor | Note | Date |")
        lines.append("| --- | --- | --- | --- |")
        for entry in dl:
            lines.append(
                f"| {_fmt(entry.get('action'))} "
                f"| {_fmt(entry.get('actor_user_id'))} "
                f"| {_fmt(entry.get('note'))} "
                f"| {_fmt(entry.get('created_at'))} |"
            )
    else:
        lines.append("- No decision log entries.")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"_{packet.get('disclaimer', DISCLAIMER)}_")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON renderer
# ---------------------------------------------------------------------------


def render_promotion_packet_json(packet: dict) -> str:
    return json.dumps(_jsonable(packet), default=str, indent=2)


# ---------------------------------------------------------------------------
# Export helper
# ---------------------------------------------------------------------------


def export_promotion_packet(
    strategy_id: Any,
    db: Session,
    *,
    target_stage: str | None = None,
    review_id: Any | None = None,
    format: str = "json",
) -> dict:
    """Build and render a promotion packet, returning export metadata + content."""
    packet = build_promotion_packet(
        strategy_id,
        db,
        target_stage=target_stage,
        review_id=review_id,
    )

    strat_slug = (packet.get("strategy_summary") or {}).get("slug") or str(strategy_id)[:8]
    date_str = _utcnow().strftime("%Y-%m-%d")

    if format == "markdown":
        content = render_promotion_packet_markdown(packet)
        filename = f"promotion-packet-{strat_slug}-{date_str}.md"
    else:
        content = render_promotion_packet_json(packet)
        filename = f"promotion-packet-{strat_slug}-{date_str}.json"

    return {
        "filename": filename,
        "format": format,
        "content": content,
        "strategy_id": str(strategy_id),
        "target_stage": packet.get("target_stage"),
        "generated_at": packet.get("generated_at"),
        "disclaimer": DISCLAIMER,
    }
