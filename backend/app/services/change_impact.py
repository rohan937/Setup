"""Change Impact Analysis service — M57.

Analyses the ripple-effect of a recent strategy change across all downstream
evidence artefacts.  Deterministic — no AI, no live market data, no external
calls, no AuditTimelineEvent created.  Read-only service.

Language is hedged: "may affect", "requires review" — not investment advice.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _score_label(score: float) -> str:
    if score >= 85:
        return "low"
    if score >= 70:
        return "medium"
    if score >= 50:
        return "high"
    return "requires_review"


# ---------------------------------------------------------------------------
# 1. Resolve focus node
# ---------------------------------------------------------------------------

def _resolve_focus_node(
    db: Session,
    strategy_id: uuid.UUID,
    mode: str,
    focus_node_id: Optional[str],
    focus_node_type: Optional[str],
) -> Optional[dict]:
    """Return a dict describing the change focus node, or None."""

    if mode == "focus_node" and focus_node_id and focus_node_type:
        # Load the specified node
        return _load_focus_node_by_id(db, strategy_id, focus_node_id, focus_node_type)

    if mode == "latest_config_change":
        return _latest_config_snapshot_node(db, strategy_id)

    if mode in ("latest_evidence_change", "latest_change"):
        return _latest_any_evidence_node(db, strategy_id)

    # Fallback: try latest change
    return _latest_any_evidence_node(db, strategy_id)


def _latest_config_snapshot_node(db: Session, strategy_id: uuid.UUID) -> Optional[dict]:
    try:
        from app.models.strategy_config_snapshot import StrategyConfigSnapshot
        snap = (
            db.query(StrategyConfigSnapshot)
            .filter(StrategyConfigSnapshot.strategy_id == strategy_id)
            .order_by(StrategyConfigSnapshot.created_at.desc())
            .first()
        )
        if snap is None:
            return None
        return {
            "node_id": str(snap.id),
            "node_type": "config_snapshot",
            "label": snap.label,
            "created_at": snap.created_at,
            "score": None,
            "status": "present",
            "route_hint": f"/strategies/{strategy_id}/config-snapshots/{snap.id}",
            "metadata_json": {"param_count": snap.param_count, "assumption_count": snap.assumption_count},
        }
    except Exception:
        return None


def _latest_any_evidence_node(db: Session, strategy_id: uuid.UUID) -> Optional[dict]:
    """Find the most recently created evidence item across all evidence types."""
    candidates: list[dict] = []

    # StrategyConfigSnapshot
    try:
        from app.models.strategy_config_snapshot import StrategyConfigSnapshot
        snap = (
            db.query(StrategyConfigSnapshot)
            .filter(StrategyConfigSnapshot.strategy_id == strategy_id)
            .order_by(StrategyConfigSnapshot.created_at.desc())
            .first()
        )
        if snap:
            candidates.append({
                "node_id": str(snap.id),
                "node_type": "config_snapshot",
                "label": snap.label,
                "created_at": snap.created_at,
                "score": None,
                "status": "present",
                "route_hint": f"/strategies/{strategy_id}/config-snapshots/{snap.id}",
                "metadata_json": {"param_count": snap.param_count, "assumption_count": snap.assumption_count},
            })
    except Exception:
        pass

    # SignalSnapshot
    try:
        from app.models.signal_snapshot import SignalSnapshot
        sig = (
            db.query(SignalSnapshot)
            .filter(SignalSnapshot.strategy_id == strategy_id)
            .order_by(SignalSnapshot.created_at.desc())
            .first()
        )
        if sig:
            candidates.append({
                "node_id": str(sig.id),
                "node_type": "signal_snapshot",
                "label": sig.label,
                "created_at": sig.created_at,
                "score": float(sig.quality_score) if sig.quality_score is not None else None,
                "status": "present",
                "route_hint": f"/strategies/{strategy_id}/signal-snapshots/{sig.id}",
                "metadata_json": {"quality_score": sig.quality_score, "row_count": sig.row_count},
            })
    except Exception:
        pass

    # UniverseSnapshot
    try:
        from app.models.universe_snapshot import UniverseSnapshot
        uni = (
            db.query(UniverseSnapshot)
            .filter(UniverseSnapshot.strategy_id == strategy_id)
            .order_by(UniverseSnapshot.created_at.desc())
            .first()
        )
        if uni:
            candidates.append({
                "node_id": str(uni.id),
                "node_type": "universe_snapshot",
                "label": uni.label,
                "created_at": uni.created_at,
                "score": None,
                "status": "present",
                "route_hint": f"/strategies/{strategy_id}/universe-snapshots/{uni.id}",
                "metadata_json": {},
            })
    except Exception:
        pass

    # StrategyRun
    try:
        from app.models.strategy_run import StrategyRun
        run = (
            db.query(StrategyRun)
            .filter(StrategyRun.strategy_id == strategy_id)
            .order_by(StrategyRun.created_at.desc())
            .first()
        )
        if run:
            candidates.append({
                "node_id": str(run.id),
                "node_type": "strategy_run",
                "label": run.run_name,
                "created_at": run.created_at,
                "score": None,
                "status": run.status,
                "route_hint": f"/strategy-runs/{run.id}",
                "metadata_json": {"run_type": run.run_type, "status": run.status},
            })
    except Exception:
        pass

    # BacktestAudit (via StrategyRun join)
    try:
        from app.models.backtest_audit import BacktestAudit
        from app.models.strategy_run import StrategyRun
        audit = (
            db.query(BacktestAudit)
            .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
            .filter(StrategyRun.strategy_id == strategy_id)
            .order_by(BacktestAudit.created_at.desc())
            .first()
        )
        if audit:
            candidates.append({
                "node_id": str(audit.id),
                "node_type": "backtest_audit",
                "label": f"Backtest Audit (trust={audit.trust_score})",
                "created_at": audit.created_at,
                "score": float(audit.trust_score),
                "status": audit.overall_status,
                "route_hint": f"/strategy-runs/{audit.strategy_run_id}/backtest-audit",
                "metadata_json": {"trust_score": audit.trust_score, "overall_status": audit.overall_status},
            })
    except Exception:
        pass

    if not candidates:
        return None

    # Return most recently created
    candidates.sort(key=lambda c: c["created_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return candidates[0]


def _load_focus_node_by_id(
    db: Session,
    strategy_id: uuid.UUID,
    focus_node_id: str,
    focus_node_type: str,
) -> Optional[dict]:
    try:
        node_uuid = uuid.UUID(focus_node_id)
    except (ValueError, AttributeError):
        return None

    if focus_node_type == "config_snapshot":
        try:
            from app.models.strategy_config_snapshot import StrategyConfigSnapshot
            snap = db.query(StrategyConfigSnapshot).filter(
                StrategyConfigSnapshot.id == node_uuid,
                StrategyConfigSnapshot.strategy_id == strategy_id,
            ).first()
            if snap:
                return {
                    "node_id": str(snap.id),
                    "node_type": "config_snapshot",
                    "label": snap.label,
                    "created_at": snap.created_at,
                    "score": None,
                    "status": "present",
                    "route_hint": f"/strategies/{strategy_id}/config-snapshots/{snap.id}",
                    "metadata_json": {"param_count": snap.param_count, "assumption_count": snap.assumption_count},
                }
        except Exception:
            pass

    if focus_node_type == "signal_snapshot":
        try:
            from app.models.signal_snapshot import SignalSnapshot
            sig = db.query(SignalSnapshot).filter(
                SignalSnapshot.id == node_uuid,
                SignalSnapshot.strategy_id == strategy_id,
            ).first()
            if sig:
                return {
                    "node_id": str(sig.id),
                    "node_type": "signal_snapshot",
                    "label": sig.label,
                    "created_at": sig.created_at,
                    "score": float(sig.quality_score) if sig.quality_score is not None else None,
                    "status": "present",
                    "route_hint": f"/strategies/{strategy_id}/signal-snapshots/{sig.id}",
                    "metadata_json": {"quality_score": sig.quality_score},
                }
        except Exception:
            pass

    if focus_node_type == "strategy_run":
        try:
            from app.models.strategy_run import StrategyRun
            run = db.query(StrategyRun).filter(
                StrategyRun.id == node_uuid,
                StrategyRun.strategy_id == strategy_id,
            ).first()
            if run:
                return {
                    "node_id": str(run.id),
                    "node_type": "strategy_run",
                    "label": run.run_name,
                    "created_at": run.created_at,
                    "score": None,
                    "status": run.status,
                    "route_hint": f"/strategy-runs/{run.id}",
                    "metadata_json": {"run_type": run.run_type, "status": run.status},
                }
        except Exception:
            pass

    if focus_node_type == "backtest_audit":
        try:
            from app.models.backtest_audit import BacktestAudit
            audit = db.query(BacktestAudit).filter(BacktestAudit.id == node_uuid).first()
            if audit:
                return {
                    "node_id": str(audit.id),
                    "node_type": "backtest_audit",
                    "label": f"Backtest Audit (trust={audit.trust_score})",
                    "created_at": audit.created_at,
                    "score": float(audit.trust_score),
                    "status": audit.overall_status,
                    "route_hint": f"/strategy-runs/{audit.strategy_run_id}/backtest-audit",
                    "metadata_json": {"trust_score": audit.trust_score},
                }
        except Exception:
            pass

    return None


# ---------------------------------------------------------------------------
# 2. Readiness impacts
# ---------------------------------------------------------------------------

def _gather_readiness_impacts(db: Session, strategy_id: uuid.UUID) -> dict:
    readiness_verdict: Optional[str] = None
    promotion_risk_count: int = 0
    failed_regression_count: int = 0
    failed_policy_count: int = 0
    sla_violation_count: int = 0
    open_review_case_count: int = 0
    suggested_checks: list[str] = []

    # Readiness verdict
    try:
        from app.services.strategy_readiness import compute_strategy_readiness
        result = compute_strategy_readiness(strategy_id, db)
        readiness_verdict = getattr(result, "readiness_verdict", None)
        if readiness_verdict in ("blocked", "requires_review_before_progression"):
            promotion_risk_count += 1
            suggested_checks.append("Review readiness scorecard blockers before progression")
    except Exception:
        pass

    # Regression tests
    try:
        from app.services.regression_tests import get_regression_test_runs
        runs = get_regression_test_runs(strategy_id, db, limit=1)
        if runs:
            latest = runs[0]
            if getattr(latest, "overall_status", None) in ("failed", "warning"):
                rfc = getattr(latest, "required_failed_count", 0) or 0
                if rfc > 0:
                    failed_regression_count = rfc
                    suggested_checks.append("Review and resolve failed regression tests")
    except Exception:
        pass

    # Config policy evaluations
    try:
        from app.services.config_policies import get_config_policy_evaluations
        evals = get_config_policy_evaluations(db, str(strategy_id), limit=1)
        if evals:
            latest = evals[0]
            if getattr(latest, "overall_status", None) == "failed":
                failed_policy_count = 1
                suggested_checks.append("Config policy evaluation is failing — review policy rules")
    except Exception:
        pass

    # Evidence SLA evaluations
    try:
        from app.services.evidence_sla import get_evidence_sla_evaluations
        evals = get_evidence_sla_evaluations(db, str(strategy_id), limit=1)
        if evals:
            latest = evals[0]
            if getattr(latest, "overall_status", None) == "violated":
                sla_violation_count = 1
                suggested_checks.append("Evidence SLA is violated — refresh stale evidence artefacts")
    except Exception:
        pass

    # Research review cases
    try:
        from app.services.review_cases import get_research_review_cases
        cases = get_research_review_cases(db, str(strategy_id), status="open")
        open_review_case_count = len(cases)
        if open_review_case_count > 0:
            suggested_checks.append(f"Acknowledge or resolve {open_review_case_count} open research review case(s)")
    except Exception:
        pass

    # Impact level
    critical_count = failed_policy_count + sla_violation_count
    high_count = failed_regression_count + (1 if promotion_risk_count > 0 else 0)
    if critical_count > 0:
        impact_level = "critical"
    elif high_count > 0:
        impact_level = "high"
    elif open_review_case_count > 0:
        impact_level = "medium"
    else:
        impact_level = "none"

    return {
        "readiness_verdict": readiness_verdict,
        "promotion_risk_count": promotion_risk_count,
        "failed_regression_count": failed_regression_count,
        "failed_policy_count": failed_policy_count,
        "sla_violation_count": sla_violation_count,
        "open_review_case_count": open_review_case_count,
        "impact_level": impact_level,
        "suggested_checks": suggested_checks,
    }


# ---------------------------------------------------------------------------
# 3. Assumption impacts
# ---------------------------------------------------------------------------

def _gather_assumption_impacts(
    db: Session,
    strategy_id: uuid.UUID,
    focus_node: Optional[dict],
) -> dict:
    has_assumption_change: bool = False
    positive_change_count: int = 0
    weakening_change_count: int = 0
    review_change_count: int = 0
    key_changes: list[dict] = []
    suggested_checks: list[str] = []

    # If focus node is a config snapshot, compare with previous
    if focus_node and focus_node.get("node_type") == "config_snapshot":
        try:
            from app.models.strategy_config_snapshot import StrategyConfigSnapshot
            from app.services.config_snapshots import compare_config_snapshots_enriched

            current_id = uuid.UUID(focus_node["node_id"])
            current_snap = db.query(StrategyConfigSnapshot).filter(
                StrategyConfigSnapshot.id == current_id
            ).first()

            if current_snap:
                previous_snap = (
                    db.query(StrategyConfigSnapshot)
                    .filter(
                        StrategyConfigSnapshot.strategy_id == strategy_id,
                        StrategyConfigSnapshot.created_at < current_snap.created_at,
                    )
                    .order_by(StrategyConfigSnapshot.created_at.desc())
                    .first()
                )

                if previous_snap:
                    diff = compare_config_snapshots_enriched(previous_snap, current_snap)
                    # diff is a plain dict with keys like "assumptions", "params" etc.
                    all_changes: list[dict] = []
                    for section_key in ("assumptions", "params", "portfolio", "risk_constraints"):
                        section = diff.get(section_key) or {}
                        changes_in_section = section.get("changes") or []
                        all_changes.extend(changes_in_section)

                    if all_changes:
                        has_assumption_change = True
                        for ch in all_changes:
                            impact = ch.get("impact_level", "none")
                            if impact == "positive":
                                positive_change_count += 1
                            elif impact in ("weakening", "high"):
                                weakening_change_count += 1
                            elif impact in ("review", "medium"):
                                review_change_count += 1

                        key_changes = all_changes[:10]
                        if weakening_change_count > 0:
                            suggested_checks.append(
                                f"{weakening_change_count} potentially weakening assumption change(s) detected — re-audit backtest"
                            )
                        if review_change_count > 0:
                            suggested_checks.append(
                                f"{review_change_count} assumption change(s) require review"
                            )
        except Exception:
            pass

    # Assumption health check (always run)
    try:
        from app.services.assumption_health import compute_assumption_health
        health = compute_assumption_health(strategy_id, db)
        # Returns a plain dict
        status = health.get("overall_status") or health.get("status")
        score = health.get("overall_assumption_score") or health.get("score")
        if status in ("poor", "weak", "critical") or (score is not None and float(score) < 50):
            suggested_checks.append("Assumption health score is low — review assumption configuration")
    except Exception:
        pass

    if weakening_change_count > 0:
        impact_level = "high"
    elif review_change_count > 0 or has_assumption_change:
        impact_level = "medium"
    else:
        impact_level = "none"

    return {
        "has_assumption_change": has_assumption_change,
        "positive_change_count": positive_change_count,
        "weakening_change_count": weakening_change_count,
        "review_change_count": review_change_count,
        "key_changes": key_changes,
        "impact_level": impact_level,
        "suggested_checks": suggested_checks,
    }


# ---------------------------------------------------------------------------
# 4. Quality impacts
# ---------------------------------------------------------------------------

def _gather_quality_impacts(db: Session, strategy_id: uuid.UUID) -> dict:
    quality_impact_count: int = 0
    degraded_quality_count: int = 0
    missing_quality_count: int = 0
    key_quality_findings: list[str] = []

    # Signal snapshot quality
    try:
        from app.models.signal_snapshot import SignalSnapshot
        sig = (
            db.query(SignalSnapshot)
            .filter(SignalSnapshot.strategy_id == strategy_id)
            .order_by(SignalSnapshot.created_at.desc())
            .first()
        )
        if sig is None:
            missing_quality_count += 1
            key_quality_findings.append("No signal snapshot present for this strategy")
        else:
            qs = sig.quality_score
            if qs is None:
                missing_quality_count += 1
                key_quality_findings.append("Signal snapshot has no quality score")
            elif qs < 50:
                degraded_quality_count += 1
                quality_impact_count += 1
                key_quality_findings.append(f"Signal quality score is degraded ({qs}/100)")
            elif qs < 75:
                quality_impact_count += 1
                key_quality_findings.append(f"Signal quality score is below target ({qs}/100)")
    except Exception:
        pass

    # Dataset snapshot health (via latest strategy run)
    try:
        from app.models.strategy_run import StrategyRun
        from app.models.dataset_snapshot import DatasetSnapshot
        run = (
            db.query(StrategyRun)
            .filter(StrategyRun.strategy_id == strategy_id)
            .order_by(StrategyRun.created_at.desc())
            .first()
        )
        if run and run.dataset_snapshot_id:
            ds = db.query(DatasetSnapshot).filter(DatasetSnapshot.id == run.dataset_snapshot_id).first()
            if ds:
                hs = ds.health_score
                if hs is None:
                    missing_quality_count += 1
                elif hs < 50:
                    degraded_quality_count += 1
                    quality_impact_count += 1
                    key_quality_findings.append(f"Dataset snapshot health score is degraded ({hs}/100)")
                elif hs < 75:
                    quality_impact_count += 1
                    key_quality_findings.append(f"Dataset health score is below target ({hs}/100)")
    except Exception:
        pass

    # Backtest audit trust score
    try:
        from app.models.backtest_audit import BacktestAudit
        from app.models.strategy_run import StrategyRun
        audit = (
            db.query(BacktestAudit)
            .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
            .filter(StrategyRun.strategy_id == strategy_id)
            .order_by(BacktestAudit.created_at.desc())
            .first()
        )
        if audit is None:
            missing_quality_count += 1
            key_quality_findings.append("No backtest audit available")
        else:
            ts = audit.trust_score
            if ts < 50:
                degraded_quality_count += 1
                quality_impact_count += 1
                key_quality_findings.append(f"Backtest trust score is low ({ts}/100)")
            elif ts < 75:
                quality_impact_count += 1
                key_quality_findings.append(f"Backtest trust score is below target ({ts}/100)")
    except Exception:
        pass

    return {
        "quality_impact_count": quality_impact_count,
        "degraded_quality_count": degraded_quality_count,
        "missing_quality_count": missing_quality_count,
        "key_quality_findings": key_quality_findings,
    }


# ---------------------------------------------------------------------------
# 5. Build rechecks
# ---------------------------------------------------------------------------

_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _build_rechecks(
    focus_node: Optional[dict],
    assumption_impacts: dict,
    quality_impacts: dict,
    readiness_impacts: dict,
) -> list[dict]:
    rechecks: list[dict] = []
    seen_keys: set[str] = set()

    def _add(key, title, priority, reason, endpoint_hint="", depends_on=None, status="pending"):
        if key in seen_keys:
            return
        seen_keys.add(key)
        rechecks.append({
            "recheck_key": key,
            "title": title,
            "priority": priority,
            "reason": reason,
            "endpoint_hint": endpoint_hint,
            "depends_on": depends_on or [],
            "status": status,
        })

    node_type = focus_node.get("node_type") if focus_node else None

    if node_type == "config_snapshot":
        _add("config_policy_eval", "Re-run Config Policy Evaluation",
             "high", "Config change may have introduced policy violations",
             "POST /api/strategies/{id}/config-policies/{policy_id}/evaluate")
        _add("assumption_health", "Review Assumption Health Scorecard",
             "high", "Assumption changes require health re-assessment",
             "GET /api/strategies/{id}/assumption-health")
        if assumption_impacts.get("weakening_change_count", 0) > 0:
            _add("backtest_audit", "Re-audit Backtest After Assumption Change",
                 "critical", "Weakening assumption changes detected — prior backtest may no longer be valid",
                 "POST /api/strategy-runs/{id}/backtest-audit")
        _add("regression_tests", "Run Regression Test Suite",
             "high", "Config changes may affect existing regression baselines",
             "POST /api/strategies/{id}/regression-tests/run")
        _add("promotion_gates", "Check Promotion Gates",
             "medium", "Verify promotion eligibility after config change",
             "GET /api/strategies/{id}/promotion-gates")
        _add("review_cases", "Generate Research Review Cases",
             "medium", "New config may surface assumption review cases",
             "POST /api/strategies/{id}/review-cases/generate")
        _add("evidence_sla", "Re-evaluate Evidence SLA",
             "low", "Verify evidence freshness requirements are still met",
             "POST /api/strategies/{id}/evidence-sla/policies/{id}/evaluate")

    elif node_type == "signal_snapshot":
        _add("signal_quality", "Review Signal Quality Drilldown",
             "high", "New signal snapshot — review quality metrics",
             "GET /api/strategies/{id}/signal-quality")
        _add("evidence_freshness", "Check Evidence Freshness",
             "medium", "Signal update may affect freshness tracking",
             "GET /api/strategies/{id}/evidence-freshness")
        _add("regression_tests", "Run Regression Tests",
             "high", "Signal change may affect regression baselines",
             "POST /api/strategies/{id}/regression-tests/run")
        if quality_impacts.get("degraded_quality_count", 0) > 0:
            _add("backtest_audit", "Audit Backtest With New Signal",
                 "high", "Degraded signal quality may affect backtest validity",
                 "POST /api/strategy-runs/{id}/backtest-audit")
        _add("readiness", "Re-evaluate Strategy Readiness",
             "medium", "Updated signal affects readiness scorecard",
             "GET /api/strategies/{id}/readiness-scorecard")

    elif node_type == "dataset_snapshot":
        _add("dataset_quality", "Review Dataset Quality Drilldown",
             "high", "New dataset snapshot — review quality metrics",
             "GET /api/datasets/{id}/quality-drilldown")
        _add("backtest_audit", "Re-audit Backtest With New Dataset",
             "high", "Dataset change requires backtest re-audit",
             "POST /api/strategy-runs/{id}/backtest-audit")
        _add("regression_tests", "Run Regression Tests",
             "medium", "Dataset update may shift regression baselines",
             "POST /api/strategies/{id}/regression-tests/run")
        _add("readiness", "Re-evaluate Strategy Readiness",
             "low", "Dataset update affects readiness scorecard",
             "GET /api/strategies/{id}/readiness-scorecard")

    elif node_type == "strategy_run":
        _add("backtest_audit", "Audit New Strategy Run",
             "critical", "New run requires backtest reality check",
             "POST /api/strategy-runs/{id}/backtest-audit")
        _add("reliability_score", "Compute Reliability Score",
             "critical", "New run should be included in reliability assessment",
             "POST /api/strategies/{id}/reliability-score")
        _add("regression_tests", "Run Regression Tests Against New Run",
             "high", "New run may alter regression baselines",
             "POST /api/strategies/{id}/regression-tests/run")
        _add("drift_analysis", "Check Strategy Drift",
             "medium", "New run results may indicate strategy drift",
             "GET /api/strategies/{id}/drift")
        _add("readiness", "Re-evaluate Strategy Readiness",
             "medium", "New run data affects readiness scorecard",
             "GET /api/strategies/{id}/readiness-scorecard")
        _add("alerts", "Review Active Alerts",
             "low", "Check for new alerts triggered by run results",
             "GET /api/alerts?strategy_id={id}")

    elif node_type == "backtest_audit":
        _add("readiness", "Re-evaluate Strategy Readiness",
             "high", "Backtest audit result affects readiness scorecard",
             "GET /api/strategies/{id}/readiness-scorecard")
        _add("promotion_gates", "Check Promotion Gates",
             "high", "Backtest audit affects promotion eligibility",
             "GET /api/strategies/{id}/promotion-gates")
        _add("review_cases", "Review Research Cases",
             "medium", "Audit findings may require research review cases",
             "POST /api/strategies/{id}/review-cases/generate")
        _add("regression_tests", "Run Regression Tests",
             "medium", "Audit insights may update regression expectations",
             "POST /api/strategies/{id}/regression-tests/run")

    else:
        # General fallback
        _add("evidence_freshness", "Check Evidence Freshness",
             "medium", "Verify all evidence artefacts are up to date",
             "GET /api/strategies/{id}/evidence-freshness")
        _add("regression_tests", "Run Regression Tests",
             "medium", "Confirm regression baselines are still valid",
             "POST /api/strategies/{id}/regression-tests/run")
        _add("readiness", "Check Strategy Readiness",
             "low", "Review overall readiness scorecard",
             "GET /api/strategies/{id}/readiness-scorecard")
        _add("review_cases", "Review Research Review Cases",
             "low", "Check for open review cases",
             "GET /api/strategies/{id}/review-cases")

    # Additional rechecks from readiness impacts
    if readiness_impacts.get("sla_violation_count", 0) > 0:
        _add("evidence_sla", "Re-evaluate Evidence SLA",
             "critical", "Evidence SLA violation detected",
             "POST /api/strategies/{id}/evidence-sla/policies/{id}/evaluate")
    if readiness_impacts.get("failed_policy_count", 0) > 0:
        _add("config_policy_eval", "Review Config Policy Evaluation",
             "critical", "Config policy evaluation is failing",
             "GET /api/strategies/{id}/config-policies")
    if readiness_impacts.get("failed_regression_count", 0) > 0:
        _add("regression_tests", "Resolve Failing Regression Tests",
             "high", "Required regression tests are failing",
             "GET /api/strategies/{id}/regression-tests")

    rechecks.sort(key=lambda r: _PRIORITY_ORDER.get(r["priority"], 99))
    return rechecks


# ---------------------------------------------------------------------------
# 6. Build impacted artifacts
# ---------------------------------------------------------------------------

def _build_impacted_artifacts(
    db: Session,
    strategy_id: uuid.UUID,
    focus_node: Optional[dict],
    readiness_impacts: dict,
    assumption_impacts: dict,
    quality_impacts: dict,
) -> list[dict]:
    artifacts: list[dict] = []

    def _add_artifact(
        artifact_id: str,
        artifact_type: str,
        label: str,
        relationship: str,
        impact_level: str,
        reason: str,
        current_status: str = "unknown",
        current_score: Optional[float] = None,
        route_hint: str = "",
        suggested_recheck: str = "",
    ):
        if impact_level == "none":
            return
        artifacts.append({
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "label": label,
            "relationship": relationship,
            "impact_level": impact_level,
            "reason": reason,
            "current_status": current_status,
            "current_score": current_score,
            "route_hint": route_hint,
            "suggested_recheck": suggested_recheck,
        })

    # Readiness scorecard
    ri = readiness_impacts
    readiness_verdict = ri.get("readiness_verdict")
    if readiness_verdict in ("blocked", "requires_review_before_progression"):
        readiness_il = "critical"
    elif readiness_verdict in ("ready_for_backtest_review",):
        readiness_il = "medium"
    elif ri.get("promotion_risk_count", 0) > 0:
        readiness_il = "high"
    else:
        readiness_il = "low"

    _add_artifact(
        f"readiness-{strategy_id}", "readiness_scorecard", "Readiness Scorecard",
        "downstream", readiness_il,
        f"Readiness verdict: {readiness_verdict or 'unknown'}",
        current_status=readiness_verdict or "unknown",
        route_hint=f"/strategies/{strategy_id}/readiness-scorecard",
        suggested_recheck="GET /api/strategies/{id}/readiness-scorecard",
    )

    # Promotion gates
    promo_il = "high" if ri.get("promotion_risk_count", 0) > 0 else "low"
    _add_artifact(
        f"promotion-{strategy_id}", "promotion_gates", "Promotion Gates",
        "downstream", promo_il,
        "Promotion eligibility may be affected by recent changes",
        route_hint=f"/strategies/{strategy_id}/promotion-gates",
        suggested_recheck="GET /api/strategies/{id}/promotion-gates",
    )

    # Regression tests
    reg_il = "high" if ri.get("failed_regression_count", 0) > 0 else "medium"
    _add_artifact(
        f"regression-{strategy_id}", "regression_tests", "Regression Test Suite",
        "downstream", reg_il,
        "Regression tests should be re-run after evidence changes",
        route_hint=f"/strategies/{strategy_id}/regression-tests",
        suggested_recheck="POST /api/strategies/{id}/regression-tests/run",
    )

    # Config policy
    policy_il = "critical" if ri.get("failed_policy_count", 0) > 0 else "medium"
    _add_artifact(
        f"config-policy-{strategy_id}", "config_policy", "Config Policy Evaluation",
        "downstream", policy_il,
        "Config policy evaluation may be affected by assumption changes",
        route_hint=f"/strategies/{strategy_id}/config-policies",
        suggested_recheck="POST /api/strategies/{id}/config-policies/{id}/evaluate",
    )

    # Evidence SLA
    sla_il = "critical" if ri.get("sla_violation_count", 0) > 0 else "low"
    _add_artifact(
        f"evidence-sla-{strategy_id}", "evidence_sla", "Evidence SLA Monitor",
        "downstream", sla_il,
        "Evidence SLA compliance may be impacted by stale or missing artefacts",
        route_hint=f"/strategies/{strategy_id}/evidence-sla/evaluations",
        suggested_recheck="POST /api/strategies/{id}/evidence-sla/policies/{id}/evaluate",
    )

    # Review cases
    review_il = "medium" if ri.get("open_review_case_count", 0) > 0 else "low"
    _add_artifact(
        f"review-cases-{strategy_id}", "review_cases", "Research Review Cases",
        "downstream", review_il,
        f"{ri.get('open_review_case_count', 0)} open review case(s) may require attention",
        route_hint=f"/strategies/{strategy_id}/review-cases",
        suggested_recheck="POST /api/strategies/{id}/review-cases/generate",
    )

    # Backtest audit — if quality is degraded
    qi = quality_impacts
    if qi.get("degraded_quality_count", 0) > 0 or qi.get("missing_quality_count", 0) > 0:
        audit_il = "high" if qi.get("degraded_quality_count", 0) > 0 else "medium"
        _add_artifact(
            f"backtest-audit-{strategy_id}", "backtest_audit", "Backtest Audit",
            "quality", audit_il,
            "Quality degradation detected — backtest audit should be re-run",
            route_hint=f"/strategies/{strategy_id}/backtest-audit",
            suggested_recheck="POST /api/strategy-runs/{id}/backtest-audit",
        )

    # Assumption health
    ai = assumption_impacts
    if ai.get("weakening_change_count", 0) > 0:
        assump_il = "high"
    elif ai.get("has_assumption_change", False) or ai.get("review_change_count", 0) > 0:
        assump_il = "medium"
    else:
        assump_il = "low"
    _add_artifact(
        f"assumption-health-{strategy_id}", "assumption_health", "Assumption Health",
        "downstream", assump_il,
        "Assumption changes may affect assumption health scorecard",
        route_hint=f"/strategies/{strategy_id}/assumption-health",
        suggested_recheck="GET /api/strategies/{id}/assumption-health",
    )

    # Shadow monitor
    node_type = focus_node.get("node_type") if focus_node else None
    if node_type in ("strategy_run", "backtest_audit", "config_snapshot"):
        _add_artifact(
            f"shadow-monitor-{strategy_id}", "shadow_monitor", "Shadow Production Monitor",
            "downstream", "medium",
            "Run or config changes may affect shadow monitoring",
            route_hint=f"/strategies/{strategy_id}/shadow-monitor",
            suggested_recheck="GET /api/strategies/{id}/shadow-monitor",
        )

    # Drift analysis
    if node_type in ("strategy_run", "signal_snapshot"):
        _add_artifact(
            f"drift-{strategy_id}", "drift_analysis", "Strategy Drift Analysis",
            "downstream", "medium",
            "New run or signal data may indicate drift",
            route_hint=f"/strategies/{strategy_id}/drift",
            suggested_recheck="GET /api/strategies/{id}/drift",
        )

    # Cap at 15
    return artifacts[:15]


# ---------------------------------------------------------------------------
# 7. Compute impact score
# ---------------------------------------------------------------------------

def _compute_impact_score(
    impacted_artifacts: list[dict],
    assumption_impacts: dict,
    quality_impacts: dict,
    readiness_impacts: dict,
    graph_blast: Any,
) -> tuple[float, str]:
    score = 100.0

    # Critical artifacts: -25 each, max -50
    critical_count = sum(1 for a in impacted_artifacts if a.get("impact_level") == "critical")
    score -= min(critical_count * 25, 50)

    # High artifacts: -15 each, max -45
    high_count = sum(1 for a in impacted_artifacts if a.get("impact_level") == "high")
    score -= min(high_count * 15, 45)

    # Medium artifacts: -8 each, max -30
    medium_count = sum(1 for a in impacted_artifacts if a.get("impact_level") == "medium")
    score -= min(medium_count * 8, 30)

    # Weakening changes: -10 each, max -30
    wc = assumption_impacts.get("weakening_change_count", 0)
    score -= min(wc * 10, 30)

    # Degraded quality: -10 each, max -30
    dq = quality_impacts.get("degraded_quality_count", 0)
    score -= min(dq * 10, 30)

    # Failed dimensions: regression/policy/sla/promotion: -15 each, max -45
    failed_dims = (
        (1 if readiness_impacts.get("failed_regression_count", 0) > 0 else 0)
        + (1 if readiness_impacts.get("failed_policy_count", 0) > 0 else 0)
        + (1 if readiness_impacts.get("sla_violation_count", 0) > 0 else 0)
        + (1 if readiness_impacts.get("promotion_risk_count", 0) > 0 else 0)
    )
    score -= min(failed_dims * 15, 45)

    # Graph blast radius penalty
    if graph_blast is not None:
        severity = getattr(graph_blast, "blast_radius_severity", None)
        if severity == "high":
            score -= 20
        elif severity == "medium":
            score -= 10

    score = max(0.0, score)

    # Check whether any meaningful focus/impacts exist
    has_focus = impacted_artifacts or wc > 0 or dq > 0 or failed_dims > 0
    if not has_focus and score >= 95:
        status = "no_change_detected"
    elif score >= 85:
        status = "low"
    elif score >= 70:
        status = "medium"
    elif score >= 50:
        status = "high"
    else:
        status = "requires_review"

    return round(score, 1), status


# ---------------------------------------------------------------------------
# 8. Main entry point
# ---------------------------------------------------------------------------

def analyze_strategy_change_impact(
    db: Session,
    strategy_id: uuid.UUID,
    focus_node_id: Optional[str] = None,
    focus_node_type: Optional[str] = None,
    mode: str = "latest_change",
) -> dict:
    """Analyse the downstream impact of a recent strategy change.

    Returns a plain dict suitable for serialisation.  Read-only — no events
    are written.  All service calls are wrapped in try/except so partial
    failures return a degraded-but-valid response.
    """
    now = _utcnow()

    # Load strategy
    try:
        from app.models.strategy import Strategy
        strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    except Exception:
        strategy = None

    if strategy is None:
        return {
            "strategy_id": str(strategy_id),
            "strategy_name": "unknown",
            "generated_at": now.isoformat(),
            "mode": mode,
            "focus_node": None,
            "impact_score": 100.0,
            "impact_status": "no_change_detected",
            "assumption_impacts": {},
            "quality_impacts": {},
            "readiness_impacts": {},
            "graph_blast_radius": None,
            "impacted_artifacts": [],
            "recommended_rechecks": [],
            "suggested_actions": [],
            "deterministic_summary": "Strategy not found — no impact analysis available.",
        }

    # 1. Resolve focus node
    focus_node: Optional[dict] = None
    try:
        focus_node = _resolve_focus_node(db, strategy_id, mode, focus_node_id, focus_node_type)
    except Exception:
        focus_node = None

    # 2. Readiness impacts
    readiness_impacts: dict = {}
    try:
        readiness_impacts = _gather_readiness_impacts(db, strategy_id)
    except Exception:
        readiness_impacts = {
            "readiness_verdict": None,
            "promotion_risk_count": 0,
            "failed_regression_count": 0,
            "failed_policy_count": 0,
            "sla_violation_count": 0,
            "open_review_case_count": 0,
            "impact_level": "none",
            "suggested_checks": [],
        }

    # 3. Assumption impacts
    assumption_impacts: dict = {}
    try:
        assumption_impacts = _gather_assumption_impacts(db, strategy_id, focus_node)
    except Exception:
        assumption_impacts = {
            "has_assumption_change": False,
            "positive_change_count": 0,
            "weakening_change_count": 0,
            "review_change_count": 0,
            "key_changes": [],
            "impact_level": "none",
            "suggested_checks": [],
        }

    # 4. Quality impacts
    quality_impacts: dict = {}
    try:
        quality_impacts = _gather_quality_impacts(db, strategy_id)
    except Exception:
        quality_impacts = {
            "quality_impact_count": 0,
            "degraded_quality_count": 0,
            "missing_quality_count": 0,
            "key_quality_findings": [],
        }

    # 5. Graph blast radius (best-effort)
    graph_blast = None
    graph_blast_dict: Optional[dict] = None
    try:
        from app.services.evidence_graph import build_strategy_evidence_graph
        graph_data = build_strategy_evidence_graph(
            strategy_id,
            db,
            focus_node_id=focus_node.get("node_id") if focus_node else None,
            focus_node_type=focus_node.get("node_type") if focus_node else None,
            include_timeline=False,
            include_computed=True,
        )
        graph_blast = graph_data.blast_radius
        if graph_blast is not None:
            graph_blast_dict = {
                "focus_node_id": graph_blast.focus_node_id,
                "focus_node_type": graph_blast.focus_node_type,
                "upstream_count": graph_blast.upstream_count,
                "downstream_count": graph_blast.downstream_count,
                "affected_run_count": graph_blast.affected_run_count,
                "affected_report_count": graph_blast.affected_report_count,
                "affected_alert_count": graph_blast.affected_alert_count,
                "affected_audit_count": graph_blast.affected_audit_count,
                "affected_readiness": graph_blast.affected_readiness,
                "affected_shadow_monitor": graph_blast.affected_shadow_monitor,
                "affected_promotion_gates": graph_blast.affected_promotion_gates,
                "blast_radius_severity": graph_blast.blast_radius_severity,
            }
    except Exception:
        graph_blast = None
        graph_blast_dict = None

    # 6. Build rechecks
    recommended_rechecks: list[dict] = []
    try:
        recommended_rechecks = _build_rechecks(
            focus_node, assumption_impacts, quality_impacts, readiness_impacts
        )
    except Exception:
        recommended_rechecks = []

    # 7. Build impacted artifacts
    impacted_artifacts: list[dict] = []
    try:
        impacted_artifacts = _build_impacted_artifacts(
            db, strategy_id, focus_node, readiness_impacts, assumption_impacts, quality_impacts
        )
    except Exception:
        impacted_artifacts = []

    # 8. Compute impact score
    try:
        impact_score, impact_status = _compute_impact_score(
            impacted_artifacts, assumption_impacts, quality_impacts, readiness_impacts, graph_blast
        )
    except Exception:
        impact_score, impact_status = 100.0, "no_change_detected"

    # Suggested actions — deduplicated, capped at 8
    seen_actions: set[str] = set()
    suggested_actions: list[str] = []

    for recheck in recommended_rechecks:
        action = recheck.get("title", "")
        if action and action not in seen_actions and len(suggested_actions) < 8:
            seen_actions.add(action)
            suggested_actions.append(action)

    for checks in [
        readiness_impacts.get("suggested_checks") or [],
        assumption_impacts.get("suggested_checks") or [],
    ]:
        for check in checks:
            if check not in seen_actions and len(suggested_actions) < 8:
                seen_actions.add(check)
                suggested_actions.append(check)

    # Deterministic summary
    parts: list[str] = []
    if focus_node:
        parts.append(
            f"Focus: {focus_node['node_type']} '{focus_node['label']}' "
            f"(created {focus_node['created_at'].strftime('%Y-%m-%d') if focus_node.get('created_at') else 'unknown'})."
        )
    else:
        parts.append("No specific focus node identified — general change scan performed.")

    critical_arts = [a for a in impacted_artifacts if a.get("impact_level") == "critical"]
    if critical_arts:
        labels = ", ".join(a["label"] for a in critical_arts[:3])
        parts.append(f"Critical downstream artefacts requiring attention: {labels}.")

    if assumption_impacts.get("weakening_change_count", 0) > 0:
        parts.append(
            f"{assumption_impacts['weakening_change_count']} potentially weakening assumption change(s) detected."
        )
    if quality_impacts.get("degraded_quality_count", 0) > 0:
        parts.append(
            f"{quality_impacts['degraded_quality_count']} quality metric(s) are below acceptable thresholds."
        )
    if readiness_impacts.get("readiness_verdict"):
        parts.append(f"Readiness verdict: {readiness_impacts['readiness_verdict']}.")

    parts.append(f"Impact score: {impact_score}/100 (status: {impact_status}).")
    parts.append("This analysis is for research workflow guidance only.")

    deterministic_summary = " ".join(parts)

    return {
        "strategy_id": str(strategy_id),
        "strategy_name": strategy.name,
        "generated_at": now.isoformat(),
        "mode": mode,
        "focus_node": focus_node,
        "impact_score": impact_score,
        "impact_status": impact_status,
        "assumption_impacts": assumption_impacts,
        "quality_impacts": quality_impacts,
        "readiness_impacts": readiness_impacts,
        "graph_blast_radius": graph_blast_dict,
        "impacted_artifacts": impacted_artifacts,
        "recommended_rechecks": recommended_rechecks,
        "suggested_actions": suggested_actions,
        "deterministic_summary": deterministic_summary,
    }
