"""Promotion Gates service (M51).

Evaluates deterministic evidence gates for strategy promotion between stages.
Deterministic -- no AI, no live market data, no external calls.
Read-only -- no AuditTimelineEvent created, not trading approval.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_TARGET_STAGES = {
    "backtest_review",
    "paper_candidate",
    "shadow_production",
    "production_candidate",
}

STAGE_LABELS = {
    "idea": "Idea",
    "research": "Research",
    "backtest_review": "Backtest Review",
    "paper_candidate": "Paper Candidate",
    "shadow_production": "Shadow Production",
    "production_candidate": "Production Candidate",
    "archived": "Archived",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PromotionGateCheckData:
    gate_key: str
    title: str
    category: str
    required: bool
    passed: bool
    status: str  # pass/watch/review/fail/missing
    severity: str  # info/low/medium/high/critical
    observed_value: Optional[str]
    required_value: Optional[str]
    evidence_summary: str
    suggested_action: Optional[str]


@dataclass
class StrategyPromotionGateData:
    strategy_id: uuid.UUID
    strategy_name: str
    generated_at: datetime
    current_stage: str
    target_stage: str
    stage_path: list
    promotion_verdict: str  # pass/conditional_pass/requires_review/blocked/insufficient_evidence
    gate_score: Optional[float]
    gate_checks: list
    required_pass_count: int
    required_fail_count: int
    recommended_pass_count: int
    recommended_fail_count: int
    blocker_count: int
    review_count: int
    blockers: list
    warnings: list
    suggested_actions: list
    deterministic_summary: str
    note: str = "This is a deterministic evidence gate result, not trading approval."


# ---------------------------------------------------------------------------
# Helper gate functions
# ---------------------------------------------------------------------------

def _gate_has_run(
    strategy_id: uuid.UUID,
    run_types: list,
    db: Session,
    required: bool = True,
    title: Optional[str] = None,
) -> PromotionGateCheckData:
    from app.models.strategy_run import StrategyRun

    runs = (
        db.query(StrategyRun)
        .filter(
            StrategyRun.strategy_id == strategy_id,
            StrategyRun.run_type.in_(run_types),
        )
        .all()
    )
    passed = len(runs) > 0
    key = f"has_{'_or_'.join(run_types)}_run"
    label = title or f"Has {'/'.join(run_types)} run"
    return PromotionGateCheckData(
        gate_key=key,
        title=label,
        category="evidence",
        required=required,
        passed=passed,
        status="pass" if passed else "missing",
        severity="medium" if (required and not passed) else "info",
        observed_value=str(len(runs)) if passed else None,
        required_value=">= 1",
        evidence_summary=(
            f"{len(runs)} {'/'.join(run_types)} run(s)."
            if passed
            else f"No {'/'.join(run_types)} run logged."
        ),
        suggested_action=f"Log a {run_types[0]} run." if not passed else None,
    )


def _gate_has_snapshot(
    strategy_id: uuid.UUID,
    snapshot_type: str,
    db: Session,
    required: bool = True,
) -> PromotionGateCheckData:
    SNAPSHOT_MODELS = {
        "signal": ("app.models.signal_snapshot", "SignalSnapshot"),
        "universe": ("app.models.universe_snapshot", "UniverseSnapshot"),
        "config": ("app.models.strategy_config_snapshot", "StrategyConfigSnapshot"),
    }
    labels = {
        "signal": "Signal Snapshots",
        "universe": "Universe Snapshots",
        "config": "Config Snapshots",
        "dataset_linked_run": "Dataset-Linked Run",
    }
    try:
        if snapshot_type == "dataset_linked_run":
            from app.models.strategy_run import StrategyRun

            count = (
                db.query(func.count(StrategyRun.id))
                .filter(
                    StrategyRun.strategy_id == strategy_id,
                    StrategyRun.dataset_snapshot_id.isnot(None),
                )
                .scalar()
                or 0
            )
            passed = count > 0
            return PromotionGateCheckData(
                gate_key=f"has_{snapshot_type}",
                title=labels[snapshot_type],
                category="evidence",
                required=required,
                passed=passed,
                status="pass" if passed else "missing",
                severity="medium" if (required and not passed) else "low",
                observed_value=str(count) if passed else None,
                required_value=">= 1",
                evidence_summary=(
                    f"{count} dataset-linked run(s)."
                    if passed
                    else "No dataset-linked runs."
                ),
                suggested_action=(
                    "Link a dataset snapshot to a run." if not passed else None
                ),
            )

        mod_path, cls_name = SNAPSHOT_MODELS[snapshot_type]
        mod = __import__(mod_path, fromlist=[cls_name])
        cls = getattr(mod, cls_name)
        count = (
            db.query(func.count(cls.id))
            .filter(cls.strategy_id == strategy_id)
            .scalar()
            or 0
        )
        passed = count > 0
        return PromotionGateCheckData(
            gate_key=f"has_{snapshot_type}_snapshot",
            title=labels[snapshot_type],
            category="evidence",
            required=required,
            passed=passed,
            status="pass" if passed else "missing",
            severity="medium" if (required and not passed) else "low",
            observed_value=str(count) if passed else None,
            required_value=">= 1",
            evidence_summary=(
                f"{count} {snapshot_type} snapshot(s)."
                if passed
                else f"No {snapshot_type} snapshots."
            ),
            suggested_action=(
                f"Log a {snapshot_type} snapshot." if not passed else None
            ),
        )
    except Exception:
        return PromotionGateCheckData(
            gate_key=f"has_{snapshot_type}_snapshot",
            title=labels.get(snapshot_type, "Snapshot"),
            category="evidence",
            required=required,
            passed=False,
            status="missing",
            severity="low",
            observed_value=None,
            required_value=">= 1",
            evidence_summary="Snapshot check unavailable.",
            suggested_action=None,
        )


def _gate_backtest_audit(
    strategy_id: uuid.UUID,
    min_trust: float,
    db: Session,
    required: bool = True,
) -> PromotionGateCheckData:
    from app.models.backtest_audit import BacktestAudit
    from app.models.strategy_run import StrategyRun

    try:
        audit = (
            db.query(BacktestAudit)
            .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
            .filter(StrategyRun.strategy_id == strategy_id)
            .order_by(BacktestAudit.created_at.desc())
            .first()
        )
        if not audit:
            return PromotionGateCheckData(
                gate_key="backtest_audit_exists",
                title="Backtest Audit Exists",
                category="backtest",
                required=required,
                passed=False,
                status="missing",
                severity="high" if required else "medium",
                observed_value=None,
                required_value=f"Trust >= {min_trust:.0f}",
                evidence_summary="No backtest audit found.",
                suggested_action="Run Backtest Reality Check.",
            )
        trust = float(audit.trust_score)
        passed = trust >= min_trust
        return PromotionGateCheckData(
            gate_key=f"backtest_trust_gte_{min_trust:.0f}",
            title=f"Backtest Trust >= {min_trust:.0f}",
            category="backtest",
            required=required,
            passed=passed,
            status=(
                "pass"
                if passed
                else ("review" if trust >= min_trust * 0.8 else "fail")
            ),
            severity=(
                "high"
                if (required and not passed and trust < min_trust * 0.6)
                else ("medium" if not passed else "info")
            ),
            observed_value=f"{trust:.0f}",
            required_value=f">= {min_trust:.0f}",
            evidence_summary=(
                f"Latest trust: {trust:.0f}/100 ({audit.overall_status})."
            ),
            suggested_action=(
                "Improve backtest assumptions and rerun Reality Check."
                if not passed
                else None
            ),
        )
    except Exception:
        return PromotionGateCheckData(
            gate_key="backtest_trust",
            title="Backtest Trust",
            category="backtest",
            required=required,
            passed=False,
            status="missing",
            severity="low",
            observed_value=None,
            required_value=f">= {min_trust:.0f}",
            evidence_summary="Audit check unavailable.",
            suggested_action=None,
        )


def _gate_no_alerts(
    strategy_id: uuid.UUID,
    max_severity: str,
    db: Session,
    required: bool = True,
) -> PromotionGateCheckData:
    SEV_ORDER = ["info", "low", "medium", "high", "critical"]
    from app.models.alert import Alert

    try:
        sev_threshold = SEV_ORDER.index(max_severity)
        sevs_to_check = SEV_ORDER[sev_threshold:]
        open_alerts = (
            db.query(Alert)
            .filter(
                Alert.strategy_id == str(strategy_id),
                Alert.status.in_(["open", "acknowledged", "snoozed"]),
                Alert.severity.in_(sevs_to_check),
            )
            .all()
        )
        count = len(open_alerts)
        passed = count == 0
        return PromotionGateCheckData(
            gate_key=f"no_{max_severity}_or_worse_alerts",
            title=f"No {max_severity.title()}+ Open Alerts",
            category="alerts",
            required=required,
            passed=passed,
            status="pass" if passed else ("review" if max_severity == "medium" else "fail"),
            severity=(
                "critical"
                if (not passed and max_severity == "critical")
                else ("high" if not passed else "info")
            ),
            observed_value=str(count) + " open",
            required_value="0",
            evidence_summary=(
                f"{count} open {max_severity}+ alert(s)."
                if not passed
                else f"No {max_severity}+ alerts open."
            ),
            suggested_action="Resolve open alerts." if not passed else None,
        )
    except Exception:
        return PromotionGateCheckData(
            gate_key=f"no_{max_severity}_alerts",
            title="No Alerts",
            category="alerts",
            required=required,
            passed=False,
            status="missing",
            severity="low",
            observed_value=None,
            required_value="0",
            evidence_summary="Alert check unavailable.",
            suggested_action=None,
        )


def _gate_coverage(
    strategy_id: uuid.UUID,
    min_score: float,
    db: Session,
    required: bool = True,
) -> PromotionGateCheckData:
    from app.models.strategy import Strategy
    from app.services.evidence_coverage import _compute_row

    try:
        strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
        cov = _compute_row(strategy, db)
        score = cov.evidence_coverage_score
        passed = score >= min_score
        return PromotionGateCheckData(
            gate_key=f"coverage_gte_{min_score:.0f}",
            title=f"Evidence Coverage >= {min_score:.0f}",
            category="evidence",
            required=required,
            passed=passed,
            status=(
                "pass"
                if passed
                else (
                    "watch"
                    if score >= min_score * 0.85
                    else "review" if score >= min_score * 0.7 else "fail"
                )
            ),
            severity=(
                "high"
                if (not passed and score < min_score * 0.6)
                else ("medium" if not passed else "info")
            ),
            observed_value=f"{score:.0f}",
            required_value=f">= {min_score:.0f}",
            evidence_summary=(
                f"Coverage: {score:.0f}/100 ({cov.complete_count} complete, "
                f"{cov.missing_count} missing)."
            ),
            suggested_action="Improve evidence coverage." if not passed else None,
        )
    except Exception:
        return PromotionGateCheckData(
            gate_key=f"coverage_gte_{min_score:.0f}",
            title=f"Coverage >= {min_score:.0f}",
            category="evidence",
            required=required,
            passed=False,
            status="missing",
            severity="low",
            observed_value=None,
            required_value=f">= {min_score:.0f}",
            evidence_summary="Coverage check unavailable.",
            suggested_action=None,
        )


def _gate_freshness(
    strategy_id: uuid.UUID,
    min_status: str,
    db: Session,
    required: bool = True,
) -> PromotionGateCheckData:
    STATUS_ORDER = ["missing_evidence", "stale", "aging", "fresh"]
    try:
        from app.services.evidence_freshness import compute_evidence_freshness

        f = compute_evidence_freshness(strategy_id, db)
        status = f.freshness_status
        threshold_idx = (
            STATUS_ORDER.index(min_status) if min_status in STATUS_ORDER else 0
        )
        actual_idx = STATUS_ORDER.index(status) if status in STATUS_ORDER else 0
        passed = actual_idx >= threshold_idx
        return PromotionGateCheckData(
            gate_key=f"freshness_not_worse_than_{min_status}",
            title=f"Freshness >= {min_status.title()}",
            category="freshness",
            required=required,
            passed=passed,
            status=(
                "pass"
                if passed
                else ("watch" if status == "aging" else "review")
            ),
            severity=(
                "medium"
                if (not passed and status in ("stale", "missing_evidence"))
                else "low"
            ),
            observed_value=status,
            required_value=f">= {min_status}",
            evidence_summary=(
                f"Freshness: {status} ({f.stale_count} stale, {f.missing_count} missing)."
            ),
            suggested_action="Refresh stale evidence." if not passed else None,
        )
    except Exception:
        return PromotionGateCheckData(
            gate_key="freshness",
            title="Evidence Freshness",
            category="freshness",
            required=required,
            passed=False,
            status="missing",
            severity="low",
            observed_value=None,
            required_value=f">= {min_status}",
            evidence_summary="Freshness check unavailable.",
            suggested_action=None,
        )


def _gate_readiness(
    strategy_id: uuid.UUID,
    min_score: float,
    allowed_verdicts: list,
    db: Session,
    required: bool = True,
) -> PromotionGateCheckData:
    try:
        from app.services.strategy_readiness import compute_strategy_readiness

        r = compute_strategy_readiness(strategy_id, db)
        score = r.readiness_score
        verdict = r.readiness_verdict
        passed = (score is not None and score >= min_score) and (
            verdict in allowed_verdicts
        )
        return PromotionGateCheckData(
            gate_key=f"readiness_gte_{min_score:.0f}",
            title=f"Readiness Score >= {min_score:.0f}",
            category="readiness",
            required=required,
            passed=passed,
            status=(
                "pass"
                if passed
                else (
                    "watch"
                    if (score and score >= min_score * 0.9)
                    else "review"
                )
            ),
            severity=(
                "high"
                if (
                    not passed
                    and verdict in ("blocked", "under_instrumented")
                )
                else ("medium" if not passed else "info")
            ),
            observed_value=(
                f"{score:.0f} ({verdict})" if score else verdict
            ),
            required_value=f">= {min_score:.0f} + acceptable verdict",
            evidence_summary=(
                f"Readiness: {score:.0f}/100, {r.verdict_label}."
                if score
                else f"Readiness: {r.verdict_label}."
            ),
            suggested_action=(
                "Resolve readiness blockers." if not passed else None
            ),
        )
    except Exception:
        return PromotionGateCheckData(
            gate_key="readiness",
            title="Readiness Score",
            category="readiness",
            required=required,
            passed=False,
            status="missing",
            severity="low",
            observed_value=None,
            required_value=f">= {min_score:.0f}",
            evidence_summary="Readiness check unavailable.",
            suggested_action=None,
        )


def _gate_drift(
    strategy_id: uuid.UUID,
    max_status: str,
    db: Session,
    required: bool = True,
) -> PromotionGateCheckData:
    STATUS_WORSE = {
        "stable": 4,
        "watch": 3,
        "review": 2,
        "severe": 1,
        "insufficient_evidence": 0,
    }
    try:
        from app.services.strategy_drift import compute_strategy_drift

        d = compute_strategy_drift(
            strategy_id, db, mode="latest_stage_pair"
        )
        if d.drift_status == "insufficient_evidence":
            return PromotionGateCheckData(
                gate_key="drift_not_severe",
                title="Drift Acceptable",
                category="drift",
                required=required,
                passed=False,
                status="missing",
                severity="low",
                observed_value="insufficient_evidence",
                required_value=f"<= {max_status}",
                evidence_summary="Insufficient runs for drift analysis.",
                suggested_action=(
                    "Log multiple run stages for drift analysis."
                ),
            )
        passed = STATUS_WORSE.get(d.drift_status, 0) >= STATUS_WORSE.get(
            max_status, 0
        )
        return PromotionGateCheckData(
            gate_key="drift_not_severe",
            title=f"Drift <= {max_status.title()}",
            category="drift",
            required=required,
            passed=passed,
            status=(
                "pass"
                if passed
                else ("review" if d.drift_status == "review" else "fail")
            ),
            severity=(
                "high"
                if d.drift_status == "severe"
                else ("medium" if not passed else "info")
            ),
            observed_value=d.drift_status,
            required_value=f"<= {max_status}",
            evidence_summary=(
                f"Drift: {d.drift_status} (score: {d.drift_score:.0f}/100)."
                if d.drift_score
                else f"Drift: {d.drift_status}."
            ),
            suggested_action=(
                "Investigate severe drift." if not passed else None
            ),
        )
    except Exception:
        return PromotionGateCheckData(
            gate_key="drift",
            title="Drift Stability",
            category="drift",
            required=required,
            passed=False,
            status="missing",
            severity="low",
            observed_value=None,
            required_value=f"<= {max_status}",
            evidence_summary="Drift check unavailable.",
            suggested_action=None,
        )


def _gate_shadow_monitor(
    strategy_id: uuid.UUID,
    min_status: str,
    db: Session,
    required: bool = True,
) -> PromotionGateCheckData:
    STATUS_ORDER = {
        "no_shadow_runs": 0,
        "insufficient_baseline": 0,
        "severe": 1,
        "review": 2,
        "watch": 3,
        "stable": 4,
    }
    try:
        from app.services.shadow_production import compute_shadow_production_monitor

        sm = compute_shadow_production_monitor(strategy_id, db)
        if sm.monitor_status in ("no_shadow_runs", "insufficient_baseline"):
            return PromotionGateCheckData(
                gate_key="shadow_monitor",
                title="Shadow Monitor",
                category="shadow",
                required=required,
                passed=False,
                status="missing",
                severity="medium",
                observed_value=sm.monitor_status,
                required_value=f">= {min_status}",
                evidence_summary=f"Shadow monitor: {sm.monitor_status}.",
                suggested_action=(
                    "Log a paper or live-like run to enable shadow monitoring."
                ),
            )
        passed = STATUS_ORDER.get(sm.monitor_status, 0) >= STATUS_ORDER.get(
            min_status, 0
        )
        return PromotionGateCheckData(
            gate_key="shadow_stability",
            title=f"Shadow Stability >= {min_status.title()}",
            category="shadow",
            required=required,
            passed=passed,
            status=(
                "pass"
                if passed
                else ("review" if sm.monitor_status == "review" else "fail")
            ),
            severity=(
                "high"
                if sm.monitor_status == "severe"
                else ("medium" if not passed else "info")
            ),
            observed_value=(
                f"{sm.monitor_status} ({sm.shadow_stability_score:.0f}/100)"
                if sm.shadow_stability_score
                else sm.monitor_status
            ),
            required_value=f">= {min_status}",
            evidence_summary=f"Shadow: {sm.monitor_status}.",
            suggested_action=(
                "Investigate shadow monitor issues." if not passed else None
            ),
        )
    except Exception:
        return PromotionGateCheckData(
            gate_key="shadow",
            title="Shadow Monitor",
            category="shadow",
            required=required,
            passed=False,
            status="missing",
            severity="low",
            observed_value=None,
            required_value=f">= {min_status}",
            evidence_summary="Shadow monitor unavailable.",
            suggested_action=None,
        )


def _gate_assumption_health(
    strategy_id: uuid.UUID,
    min_status: str,
    db: Session,
    required: bool = True,
) -> PromotionGateCheckData:
    STATUS_ORDER = {
        "weak": 0,
        "review": 1,
        "watch": 2,
        "acceptable": 3,
        "strong": 4,
        "missing_evidence": 0,
    }
    try:
        from app.services.assumption_health import compute_assumption_health

        ah = compute_assumption_health(strategy_id, db)
        status = ah.get("status", "missing_evidence")
        passed = STATUS_ORDER.get(status, 0) >= STATUS_ORDER.get(min_status, 0)
        score = ah.get("overall_assumption_score")
        return PromotionGateCheckData(
            gate_key="assumption_health",
            title=f"Assumption Health >= {min_status.title()}",
            category="assumptions",
            required=required,
            passed=passed,
            status=(
                "pass"
                if passed
                else ("review" if status in ("watch", "review") else "fail")
            ),
            severity=(
                "high"
                if status == "weak"
                else ("medium" if not passed else "info")
            ),
            observed_value=(
                f"{status}" + (f" ({score:.0f}/100)" if score else "")
            ),
            required_value=f">= {min_status}",
            evidence_summary=f"Assumption health: {status}.",
            suggested_action=(
                "Review weakening assumption changes." if not passed else None
            ),
        )
    except Exception:
        return PromotionGateCheckData(
            gate_key="assumption_health",
            title="Assumption Health",
            category="assumptions",
            required=required,
            passed=False,
            status="missing",
            severity="low",
            observed_value=None,
            required_value=f">= {min_status}",
            evidence_summary="Assumption health unavailable.",
            suggested_action=None,
        )


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def evaluate_promotion_gates(
    strategy_id: uuid.UUID,
    target_stage: str,
    db: Session,
) -> StrategyPromotionGateData:
    """Evaluate all promotion gate checks for a given target stage.

    Raises ValueError for invalid target_stage or unknown strategy_id.
    """
    from app.models.strategy import Strategy
    from app.models.strategy_run import StrategyRun

    if target_stage not in VALID_TARGET_STAGES:
        raise ValueError(f"Invalid target_stage: {target_stage!r}")

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    now = datetime.now(timezone.utc)

    # Infer current stage from run types
    all_runs = (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_id)
        .all()
    )
    run_types = {r.run_type for r in all_runs}
    if not all_runs:
        current_stage = "idea"
    elif "live" in run_types:
        current_stage = "shadow_production"
    elif "paper" in run_types:
        current_stage = "paper_candidate"
    elif "backtest" in run_types:
        current_stage = "backtest_review"
    elif "research" in run_types:
        current_stage = "research"
    else:
        current_stage = "idea"

    stage_path = [
        "idea",
        "research",
        "backtest_review",
        "paper_candidate",
        "shadow_production",
        "production_candidate",
    ]

    # Define gates per target_stage
    checks: list[PromotionGateCheckData] = []

    if target_stage == "backtest_review":
        checks = [
            _gate_has_run(
                strategy_id,
                ["research", "backtest"],
                db,
                required=True,
                title="Has Research or Backtest Run",
            ),
            _gate_has_snapshot(strategy_id, "config", db, required=True),
            _gate_has_snapshot(
                strategy_id, "dataset_linked_run", db, required=True
            ),
            _gate_has_snapshot(strategy_id, "universe", db, required=True),
            _gate_has_snapshot(strategy_id, "signal", db, required=True),
            _gate_coverage(strategy_id, 60.0, db, required=True),
            _gate_no_alerts(strategy_id, "critical", db, required=True),
            _gate_freshness(strategy_id, "aging", db, required=False),
            _gate_backtest_audit(strategy_id, 60.0, db, required=False),
        ]
    elif target_stage == "paper_candidate":
        checks = [
            _gate_has_run(
                strategy_id,
                ["backtest"],
                db,
                required=True,
                title="Has Backtest Run",
            ),
            _gate_backtest_audit(strategy_id, 70.0, db, required=True),
            _gate_coverage(strategy_id, 75.0, db, required=True),
            _gate_readiness(
                strategy_id,
                75.0,
                [
                    "ready_for_backtest_review",
                    "ready_for_paper_trading_consideration",
                ],
                db,
                required=True,
            ),
            _gate_assumption_health(
                strategy_id, "acceptable", db, required=True
            ),
            _gate_no_alerts(strategy_id, "high", db, required=True),
            _gate_freshness(strategy_id, "aging", db, required=True),
            _gate_drift(strategy_id, "review", db, required=True),
            _gate_backtest_audit(strategy_id, 80.0, db, required=False),
            _gate_readiness(
                strategy_id,
                85.0,
                ["ready_for_paper_trading_consideration"],
                db,
                required=False,
            ),
        ]
    elif target_stage == "shadow_production":
        checks = [
            _gate_has_run(
                strategy_id,
                ["paper", "live"],
                db,
                required=True,
                title="Has Paper/Live Run",
            ),
            _gate_readiness(
                strategy_id,
                80.0,
                [
                    "ready_for_backtest_review",
                    "ready_for_paper_trading_consideration",
                ],
                db,
                required=True,
            ),
            _gate_backtest_audit(strategy_id, 75.0, db, required=True),
            _gate_assumption_health(
                strategy_id, "acceptable", db, required=True
            ),
            _gate_no_alerts(strategy_id, "high", db, required=True),
            _gate_freshness(strategy_id, "aging", db, required=True),
            _gate_drift(strategy_id, "watch", db, required=False),
        ]
    elif target_stage == "production_candidate":
        checks = [
            _gate_has_run(
                strategy_id,
                ["paper", "live"],
                db,
                required=True,
                title="Has Paper/Live Run",
            ),
            _gate_shadow_monitor(strategy_id, "watch", db, required=True),
            _gate_readiness(
                strategy_id,
                85.0,
                ["ready_for_paper_trading_consideration"],
                db,
                required=True,
            ),
            _gate_backtest_audit(strategy_id, 75.0, db, required=True),
            _gate_no_alerts(strategy_id, "high", db, required=True),
            _gate_drift(strategy_id, "watch", db, required=True),
            _gate_freshness(strategy_id, "aging", db, required=True),
            _gate_assumption_health(
                strategy_id, "acceptable", db, required=True
            ),
            _gate_coverage(strategy_id, 80.0, db, required=True),
        ]

    # Count outcomes
    req = [c for c in checks if c.required]
    rec = [c for c in checks if not c.required]
    req_pass = sum(1 for c in req if c.passed)
    req_fail = sum(1 for c in req if not c.passed)
    rec_pass = sum(1 for c in rec if c.passed)
    rec_fail = sum(1 for c in rec if not c.passed)

    blockers_list = [
        c.evidence_summary
        for c in req
        if c.status in ("fail", "missing") and c.severity in ("high", "critical")
    ]
    warnings_list = [
        c.evidence_summary
        for c in checks
        if c.status in ("review", "watch")
        and not (
            c.status in ("fail", "missing") and c.severity in ("high", "critical")
        )
    ]
    actions_list = list(
        dict.fromkeys(
            c.suggested_action
            for c in checks
            if not c.passed and c.suggested_action
        )
    )[:8]

    # Gate score
    WEIGHT_REQ = 1.0
    WEIGHT_REC = 0.3
    CREDIT = {
        "pass": 1.0,
        "watch": 0.7,
        "review": 0.4,
        "fail": 0.0,
        "missing": 0.0,
    }
    total_w = sum(WEIGHT_REQ for _ in req) + sum(WEIGHT_REC for _ in rec)
    if total_w == 0:
        gate_score = None
    else:
        weighted_sum = sum(
            CREDIT.get(c.status, "pass" if c.passed else "fail") * WEIGHT_REQ
            for c in req
        ) + sum(
            CREDIT.get(c.status, "pass" if c.passed else "fail") * WEIGHT_REC
            for c in rec
        )
        gate_score = round((weighted_sum / total_w) * 100, 1)

    # Verdict
    blocker_count = req_fail
    review_count = sum(1 for c in checks if c.status in ("review", "watch"))
    has_critical_fail = any(
        c.severity in ("high", "critical") and not c.passed for c in req
    )

    if (
        req_fail == 0
        and rec_fail == 0
        and gate_score is not None
        and gate_score >= 90
    ):
        verdict = "pass"
    elif req_fail == 0 and gate_score is not None and gate_score >= 70:
        verdict = "conditional_pass"
    elif not all_runs or (
        req_fail > 0 and any(c.status == "missing" for c in req)
    ):
        verdict = "insufficient_evidence"
    elif has_critical_fail or any(
        c.severity in ("high", "critical") and c.status in ("fail", "missing")
        for c in req
    ):
        verdict = "blocked"
    else:
        verdict = "requires_review"

    # Summary
    summary_parts = [
        f"Promotion to {STAGE_LABELS.get(target_stage, target_stage)} for "
        f"{strategy.name}: {verdict.replace('_', ' ')}."
    ]
    if blockers_list:
        summary_parts.append(
            f"Blocking issues: {'; '.join(b[:60] for b in blockers_list[:2])}."
        )
    if gate_score is not None:
        summary_parts.append(f"Gate score: {gate_score:.0f}/100.")
    summary_parts.append(
        "This is a deterministic evidence gate result, not trading approval."
    )

    return StrategyPromotionGateData(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        generated_at=now,
        current_stage=current_stage,
        target_stage=target_stage,
        stage_path=stage_path,
        promotion_verdict=verdict,
        gate_score=gate_score,
        gate_checks=checks,
        required_pass_count=req_pass,
        required_fail_count=req_fail,
        recommended_pass_count=rec_pass,
        recommended_fail_count=rec_fail,
        blocker_count=blocker_count,
        review_count=review_count,
        blockers=blockers_list[:5],
        warnings=warnings_list[:5],
        suggested_actions=actions_list,
        deterministic_summary=" ".join(summary_parts),
    )
