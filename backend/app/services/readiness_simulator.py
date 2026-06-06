"""Strategy Readiness Simulator service (M96).

A deterministic, READ-ONLY "what-if" engine that estimates how a strategy's
governance readiness would change if specific evidence/governance actions were
completed. It reuses the existing readiness, promotion-gate, and action-queue
logic — it never writes to the database.

Design notes
------------
* READ-ONLY: this module never calls db.add / db.commit / db.flush. It only
  issues queries and calls other read-only services.
* Deterministic: no AI, no live market data, no randomness. The same inputs
  always produce the same output.
* Simulation is a pure arithmetic projection layered on the current evidence
  state — completing an action adds its catalog impact points and (where the
  hard rules allow) clears the matching blocker. No persistence occurs.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.services.promotion_gates import (
    VALID_TARGET_STAGES,
    evaluate_promotion_gates,
)
from app.services.strategy_readiness import compute_strategy_readiness


DISCLAIMER = (
    "Readiness simulation estimates governance readiness from current evidence. "
    "It is not trading advice."
)


# ---------------------------------------------------------------------------
# Action catalog
# ---------------------------------------------------------------------------

# Effort ordering for ranking (low surfaces first when impact ties).
_EFFORT_RANK = {"low": 0, "medium": 1, "high": 2}

ACTION_CATALOG: dict[str, dict] = {
    "add_one_more_run": {
        "title": "Log one more strategy run",
        "category": "run_quality",
        "impact_points": 10,
        "effort": "medium",
        "why_it_matters": (
            "Additional runs strengthen run evidence and enable drift and "
            "reliability comparisons."
        ),
        "cta_label": "Log a run",
        "cta_target": "runs",
    },
    "log_backtest_run": {
        "title": "Log a backtest run",
        "category": "run_quality",
        "impact_points": 12,
        "effort": "medium",
        "why_it_matters": (
            "A backtest run anchors trust scoring, assumption checks, and most "
            "downstream readiness signals."
        ),
        "cta_label": "Log a backtest run",
        "cta_target": "runs",
    },
    "upload_paper_run": {
        "title": "Upload a paper run",
        "category": "shadow",
        "impact_points": 14,
        "effort": "high",
        "why_it_matters": (
            "Paper/live-like runs are required for shadow monitoring and "
            "promotion beyond the paper stage."
        ),
        "cta_label": "Upload a paper run bundle",
        "cta_target": "runs",
    },
    "create_regression_tests": {
        "title": "Create default regression tests",
        "category": "governance",
        "impact_points": 8,
        "effort": "low",
        "why_it_matters": (
            "Regression tests catch metric and trust deterioration between runs "
            "before it reaches review."
        ),
        "cta_label": "Create default tests",
        "cta_target": "governance",
    },
    "run_regression_tests": {
        "title": "Run the regression test suite",
        "category": "governance",
        "impact_points": 6,
        "effort": "low",
        "why_it_matters": (
            "Running the suite produces a concrete pass/fail record that gates "
            "and reviewers rely on."
        ),
        "cta_label": "Run regression tests",
        "cta_target": "governance",
    },
    "create_config_guardrails": {
        "title": "Create config guardrails",
        "category": "governance",
        "impact_points": 6,
        "effort": "low",
        "why_it_matters": (
            "Guardrails prevent unrealistic assumptions such as missing "
            "transaction costs or same-close fills."
        ),
        "cta_label": "Create default guardrails",
        "cta_target": "governance",
    },
    "create_default_sla": {
        "title": "Create an evidence SLA policy",
        "category": "governance",
        "impact_points": 5,
        "effort": "low",
        "why_it_matters": (
            "SLA rules track stale or missing evidence so obligations are "
            "visible before reviews."
        ),
        "cta_label": "Create default SLA",
        "cta_target": "governance",
    },
    "generate_reliability_report": {
        "title": "Generate a reliability report",
        "category": "reporting",
        "impact_points": 6,
        "effort": "low",
        "why_it_matters": (
            "Reports package the current evidence state into a shareable summary "
            "for review and export."
        ),
        "cta_label": "Generate report",
        "cta_target": "exports",
    },
    "refresh_reliability_score": {
        "title": "Refresh the reliability score",
        "category": "reporting",
        "impact_points": 4,
        "effort": "low",
        "why_it_matters": (
            "A current reliability score reflects the latest evidence and feeds "
            "readiness and gate checks."
        ),
        "cta_label": "Refresh score",
        "cta_target": "overview",
    },
    "refresh_shadow_monitor": {
        "title": "Refresh the shadow monitor",
        "category": "shadow",
        "impact_points": 5,
        "effort": "low",
        "why_it_matters": (
            "Recomputing shadow drift surfaces divergence between paper/live and "
            "backtest behavior."
        ),
        "cta_label": "Refresh shadow monitor",
        "cta_target": "runs",
    },
    "resolve_promotion_gates": {
        "title": "Resolve promotion gate failures",
        "category": "governance",
        "impact_points": 8,
        "effort": "medium",
        "why_it_matters": (
            "Required promotion gates must pass before the strategy can advance "
            "to the next stage."
        ),
        "cta_label": "Review promotion gates",
        "cta_target": "governance",
    },
    "resolve_high_alerts": {
        "title": "Resolve high-severity alerts",
        "category": "alerts",
        "impact_points": 12,
        "effort": "medium",
        "why_it_matters": (
            "Open high/critical alerts flag reliability issues that block "
            "progression until resolved."
        ),
        "cta_label": "Open alerts",
        "cta_target": "overview",
    },
    "fix_evidence_links": {
        "title": "Fix evidence links on the latest run",
        "category": "evidence",
        "impact_points": 9,
        "effort": "medium",
        "why_it_matters": (
            "Linked dataset/universe/signal/config evidence is required for "
            "trust scoring and coverage."
        ),
        "cta_label": "Fix evidence links",
        "cta_target": "evidence",
    },
    "upload_fresh_evidence": {
        "title": "Upload fresh evidence",
        "category": "evidence",
        "impact_points": 7,
        "effort": "medium",
        "why_it_matters": (
            "Decisions should use current evidence; stale snapshots understate "
            "real-world risk."
        ),
        "cta_label": "Upload fresh evidence",
        "cta_target": "evidence",
    },
    "add_transaction_cost_assumption": {
        "title": "Add a transaction-cost assumption",
        "category": "assumptions",
        "impact_points": 6,
        "effort": "low",
        "why_it_matters": (
            "Missing transaction costs are the most common reason a backtest "
            "overstates returns."
        ),
        "cta_label": "Add transaction cost",
        "cta_target": "developer",
    },
    "add_slippage_assumption": {
        "title": "Add a slippage assumption",
        "category": "assumptions",
        "impact_points": 5,
        "effort": "low",
        "why_it_matters": (
            "Slippage modeling makes fills realistic and protects backtest "
            "trust."
        ),
        "cta_label": "Add slippage",
        "cta_target": "developer",
    },
    "add_shorting_assumption": {
        "title": "Add a shorting / borrow assumption",
        "category": "assumptions",
        "impact_points": 4,
        "effort": "low",
        "why_it_matters": (
            "Borrow cost and shorting constraints affect the feasibility of "
            "short positions."
        ),
        "cta_label": "Add shorting assumption",
        "cta_target": "developer",
    },
    "add_survivorship_bias_statement": {
        "title": "Add a survivorship-bias statement",
        "category": "assumptions",
        "impact_points": 3,
        "effort": "low",
        "why_it_matters": (
            "Stating how survivorship bias was handled documents a key data "
            "assumption."
        ),
        "cta_label": "Add survivorship statement",
        "cta_target": "developer",
    },
    "add_lookahead_bias_statement": {
        "title": "Add a look-ahead-bias statement",
        "category": "assumptions",
        "impact_points": 3,
        "effort": "low",
        "why_it_matters": (
            "Documenting look-ahead handling reassures reviewers the signal is "
            "point-in-time."
        ),
        "cta_label": "Add look-ahead statement",
        "cta_target": "developer",
    },
    "generate_promotion_packet": {
        "title": "Generate the promotion packet",
        "category": "reporting",
        "impact_points": 2,
        "effort": "low",
        "why_it_matters": (
            "A promotion packet bundles the evidence reviewers need into one "
            "artifact."
        ),
        "cta_label": "Generate promotion packet",
        "cta_target": "governance",
    },
    "submit_for_review": {
        "title": "Submit for review",
        "category": "governance",
        "impact_points": 2,
        "effort": "low",
        "why_it_matters": (
            "Submitting starts the human review that authorizes the next "
            "lifecycle stage."
        ),
        "cta_label": "Submit for review",
        "cta_target": "governance",
    },
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RecommendedAction:
    key: str
    title: str
    category: str
    impact_points: int
    effort: str
    status: str  # not_started / done
    why_it_matters: str
    cta_label: str
    cta_target: str


@dataclass
class ReadinessSimulationData:
    strategy_id: uuid.UUID
    strategy_name: str
    current_stage: str
    target_stage: str
    current_readiness_score: float | None
    projected_readiness_score: float | None
    current_verdict: str
    projected_verdict: str
    estimated_delta: float
    current_blockers: list[str]
    remaining_blockers: list[str]
    recommended_actions: list[RecommendedAction]
    simulated_completed_actions: list[str]
    warnings: list[str]
    generated_at: datetime
    disclaimer: str = DISCLAIMER


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_target_stage(target_stage: str | None) -> str | None:
    """Map the milestone "shadow" alias onto the canonical gate stage."""
    if target_stage == "shadow":
        return "shadow_production"
    return target_stage


def _infer_current_stage(strategy_id: uuid.UUID, db: Session) -> str:
    """Infer the current lifecycle stage exactly as promotion_gates does."""
    from app.models.strategy_run import StrategyRun

    run_types = {
        r.run_type
        for r in db.query(StrategyRun.run_type)
        .filter(StrategyRun.strategy_id == strategy_id)
        .all()
    }
    if not run_types:
        return "idea"
    if "live" in run_types:
        return "shadow_production"
    if "paper" in run_types:
        return "paper_candidate"
    if "backtest" in run_types:
        return "backtest_review"
    if "research" in run_types:
        return "research"
    return "idea"


def _resolve_target_stage(
    strategy_id: uuid.UUID, db: Session, target_stage: str | None
) -> str:
    """Resolve (and validate) the simulation target stage.

    Accepts the "shadow" alias. When *target_stage* is None, infers the next
    sensible stage from the current evidence state. Raises ValueError for an
    invalid explicit target.
    """
    normalized = _normalize_target_stage(target_stage)
    if normalized is not None:
        if normalized not in VALID_TARGET_STAGES:
            raise ValueError(f"Invalid target_stage: {target_stage!r}")
        return normalized

    # Infer the next stage from current state.
    current = _infer_current_stage(strategy_id, db)
    next_by_current = {
        "idea": "backtest_review",
        "research": "backtest_review",
        "backtest_review": "paper_candidate",
        "paper_candidate": "shadow_production",
        "shadow_production": "production_candidate",
        "production_candidate": "production_candidate",
    }
    inferred = next_by_current.get(current)
    if inferred is None:
        # Default: paper_candidate if any backtest exists, else backtest_review.
        from app.models.strategy_run import StrategyRun

        has_backtest = (
            db.query(StrategyRun.id)
            .filter(
                StrategyRun.strategy_id == strategy_id,
                StrategyRun.run_type == "backtest",
            )
            .first()
            is not None
        )
        inferred = "paper_candidate" if has_backtest else "backtest_review"
    return inferred


# ---- DB existence checks (read-only) --------------------------------------


def _has_any_run(strategy_id: uuid.UUID, db: Session) -> bool:
    from app.models.strategy_run import StrategyRun

    return (
        db.query(StrategyRun.id)
        .filter(StrategyRun.strategy_id == strategy_id)
        .first()
        is not None
    )


def _has_run_type(strategy_id: uuid.UUID, db: Session, run_types: list[str]) -> bool:
    from app.models.strategy_run import StrategyRun

    return (
        db.query(StrategyRun.id)
        .filter(
            StrategyRun.strategy_id == strategy_id,
            StrategyRun.run_type.in_(run_types),
        )
        .first()
        is not None
    )


def _has_regression_tests(strategy_id: uuid.UUID, db: Session) -> bool:
    from app.models.regression import StrategyRegressionTest

    return (
        db.query(StrategyRegressionTest.id)
        .filter(StrategyRegressionTest.strategy_id == strategy_id)
        .first()
        is not None
    )


def _has_reliability_report(strategy_id: uuid.UUID, db: Session) -> bool:
    try:
        from app.models.report import Report

        return (
            db.query(Report.id)
            .filter(
                Report.strategy_id == strategy_id,
                Report.report_type == "strategy_reliability",
            )
            .first()
            is not None
        )
    except Exception:
        return False


def _has_config_guardrails(strategy_id: uuid.UUID, db: Session) -> bool:
    try:
        from app.models.config_policy import StrategyConfigPolicy

        return (
            db.query(StrategyConfigPolicy.id)
            .filter(StrategyConfigPolicy.strategy_id == strategy_id)
            .first()
            is not None
        )
    except Exception:
        return False


def _has_sla_policy(strategy_id: uuid.UUID, db: Session) -> bool:
    try:
        from app.models.evidence_sla import EvidenceSLAPolicy

        return (
            db.query(EvidenceSLAPolicy.id)
            .filter(EvidenceSLAPolicy.strategy_id == strategy_id)
            .first()
            is not None
        )
    except Exception:
        return False


def _has_high_or_critical_alerts(strategy_id: uuid.UUID, db: Session) -> bool:
    try:
        from app.models.alert import Alert

        return (
            db.query(Alert.id)
            .filter(
                Alert.strategy_id == str(strategy_id),
                Alert.status.in_(["open", "acknowledged", "snoozed"]),
                Alert.severity.in_(["high", "critical"]),
            )
            .first()
            is not None
        )
    except Exception:
        return False


# ---- Gate-check -> action mapping -----------------------------------------


def _actions_for_gate(check, target_stage: str) -> list[str]:
    """Map a failed/missing gate check onto one or more action keys.

    Uses the stable ``category`` plus ``gate_key`` prefixes (gate keys carry
    dynamic numeric thresholds, so we match on prefixes rather than equality).
    """
    key = (check.gate_key or "").lower()
    category = (check.category or "").lower()

    # Evidence "has run" gates.
    if key.startswith("has_") and (
        "run" in key and ("research" in key or "backtest" in key)
    ):
        return ["log_backtest_run", "add_one_more_run"]
    if key.startswith("has_") and (
        "paper" in key or "live" in key
    ):
        return ["upload_paper_run"]

    # Backtest audit / trust.
    if category == "backtest" or key.startswith("backtest_trust") or key.startswith(
        "backtest_audit"
    ):
        return ["add_transaction_cost_assumption", "add_slippage_assumption"]

    # Evidence coverage.
    if key.startswith("coverage_") or "coverage" in key:
        return ["fix_evidence_links", "upload_fresh_evidence"]

    # Snapshot existence (config/universe/signal/dataset).
    if key.startswith("has_") and any(
        t in key for t in ("config", "universe", "signal", "dataset")
    ):
        return ["fix_evidence_links", "upload_fresh_evidence"]

    # Freshness.
    if category == "freshness" or "freshness" in key:
        return ["upload_fresh_evidence"]

    # Alerts.
    if category == "alerts" or "alert" in key:
        return ["resolve_high_alerts"]

    # Drift / shadow.
    if category == "drift" or "drift" in key:
        return ["refresh_shadow_monitor"]
    if category == "shadow" or "shadow" in key:
        return ["refresh_shadow_monitor"]

    # Assumption health.
    if category == "assumptions" or "assumption" in key:
        return ["add_transaction_cost_assumption", "add_shorting_assumption"]

    # Readiness.
    if category == "readiness" or "readiness" in key:
        return ["add_one_more_run", "refresh_reliability_score"]

    return []


def _blocker_actions_map(gate_data, target_stage: str) -> dict[str, list[str]]:
    """Map each gate blocker string onto the action keys that would resolve it.

    The promotion-gate ``blockers`` list holds ``evidence_summary`` strings of
    failing required checks. We re-derive the action keys from the matching
    gate checks so blockers and actions stay in sync.
    """
    mapping: dict[str, list[str]] = {}
    blockers = set(gate_data.blockers or [])
    for check in gate_data.gate_checks:
        if check.evidence_summary in blockers:
            actions = _actions_for_gate(check, target_stage)
            if actions:
                mapping.setdefault(check.evidence_summary, [])
                for a in actions:
                    if a not in mapping[check.evidence_summary]:
                        mapping[check.evidence_summary].append(a)
    return mapping


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


def recommend_readiness_actions(
    strategy_id: uuid.UUID,
    db: Session,
    target_stage: str | None = None,
) -> list[RecommendedAction]:
    """Return a ranked list of recommended readiness actions (read-only)."""
    from app.models.strategy import Strategy

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    resolved = _resolve_target_stage(strategy_id, db, target_stage)

    # action_key -> worst severity tied to its triggering gate failure.
    action_severity: dict[str, int] = {}

    def _note(action_key: str, severity_rank: int) -> None:
        if action_key not in ACTION_CATALOG:
            return
        prev = action_severity.get(action_key, 9)
        action_severity[action_key] = min(prev, severity_rank)

    has_runs = _has_any_run(strategy_id, db)

    # 1/2. Gate-driven actions.
    try:
        gate_data = evaluate_promotion_gates(strategy_id, resolved, db)
        for check in gate_data.gate_checks:
            if check.passed:
                continue
            if check.status not in ("fail", "missing", "review", "watch"):
                continue
            sev_rank = _SEVERITY_RANK.get(check.severity, 9)
            for action_key in _actions_for_gate(check, resolved):
                _note(action_key, sev_rank)
    except Exception:
        gate_data = None

    # If there are no runs at all, the gate evaluation may be sparse — make sure
    # the foundational run actions are present.
    if not has_runs:
        _note("log_backtest_run", _SEVERITY_RANK["high"])
        _note("add_one_more_run", _SEVERITY_RANK["medium"])

    # 3. Existence-based governance/reporting gaps (deterministic DB checks).
    if not _has_regression_tests(strategy_id, db):
        _note("create_regression_tests", _SEVERITY_RANK["medium"])
    if not _has_reliability_report(strategy_id, db):
        _note("generate_reliability_report", _SEVERITY_RANK["low"])
    if not _has_config_guardrails(strategy_id, db):
        _note("create_config_guardrails", _SEVERITY_RANK["medium"])
    if not _has_sla_policy(strategy_id, db):
        _note("create_default_sla", _SEVERITY_RANK["low"])
    if resolved in ("shadow_production", "production_candidate") and not _has_run_type(
        strategy_id, db, ["paper", "live"]
    ):
        _note("upload_paper_run", _SEVERITY_RANK["high"])
    if _has_high_or_critical_alerts(strategy_id, db):
        _note("resolve_high_alerts", _SEVERITY_RANK["high"])

    # 4/5. Build deduplicated RecommendedAction objects with status.
    actions: list[RecommendedAction] = []
    for action_key, sev_rank in action_severity.items():
        spec = ACTION_CATALOG[action_key]
        status = (
            "done"
            if _action_condition_satisfied(action_key, strategy_id, db, resolved)
            else "not_started"
        )
        actions.append(
            RecommendedAction(
                key=action_key,
                title=spec["title"],
                category=spec["category"],
                impact_points=spec["impact_points"],
                effort=spec["effort"],
                status=status,
                why_it_matters=spec["why_it_matters"],
                cta_label=spec["cta_label"],
                cta_target=spec["cta_target"],
            )
        )

    # 6. Rank: severity (lower rank first), impact desc, effort asc, key alpha.
    actions.sort(
        key=lambda a: (
            action_severity.get(a.key, 9),
            -a.impact_points,
            _EFFORT_RANK.get(a.effort, 9),
            a.key,
        )
    )
    return actions


def _action_condition_satisfied(
    action_key: str,
    strategy_id: uuid.UUID,
    db: Session,
    target_stage: str,
) -> bool:
    """Best-effort check of whether an action's underlying gap is already closed.

    Only existence-based actions can be reliably marked ``done`` from the DB;
    everything else defaults to not-satisfied (so it stays actionable).
    """
    if action_key == "create_regression_tests":
        return _has_regression_tests(strategy_id, db)
    if action_key == "generate_reliability_report":
        return _has_reliability_report(strategy_id, db)
    if action_key == "create_config_guardrails":
        return _has_config_guardrails(strategy_id, db)
    if action_key == "create_default_sla":
        return _has_sla_policy(strategy_id, db)
    if action_key == "upload_paper_run":
        return _has_run_type(strategy_id, db, ["paper", "live"])
    if action_key in ("log_backtest_run",):
        return _has_run_type(strategy_id, db, ["backtest"])
    if action_key == "resolve_high_alerts":
        return not _has_high_or_critical_alerts(strategy_id, db)
    return False


def estimate_action_impacts(
    strategy_id: uuid.UUID,
    db: Session,
    target_stage: str | None = None,
) -> dict:
    """Return {action_key: impact_points} for the recommended actions."""
    actions = recommend_readiness_actions(strategy_id, db, target_stage)
    return {a.key: a.impact_points for a in actions}


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


def get_current_readiness(
    strategy_id: uuid.UUID,
    db: Session,
    target_stage: str | None = None,
) -> ReadinessSimulationData:
    """Current readiness state with no actions simulated."""
    return simulate_readiness(strategy_id, db, target_stage, completed_actions=[])


def _map_gate_verdict_to_simple(gate_verdict: str) -> str:
    if gate_verdict in ("pass", "conditional_pass"):
        return "ready"
    if gate_verdict in ("blocked", "insufficient_evidence"):
        return "blocked"
    return "review"  # requires_review and anything else


def simulate_readiness(
    strategy_id: uuid.UUID,
    db: Session,
    target_stage: str | None = None,
    completed_actions: list[str] | None = None,
) -> ReadinessSimulationData:
    """Project readiness given a hypothetical set of completed actions.

    Pure, deterministic, and READ-ONLY: no records are created or modified.
    """
    from app.models.strategy import Strategy

    # 1. Load strategy.
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    now = _utcnow()
    completed = set(completed_actions or [])

    # 2. Resolve target + current stage.
    resolved_target = _resolve_target_stage(strategy_id, db, target_stage)
    current_stage = _infer_current_stage(strategy_id, db)

    # 6. Recommended actions (also needed for the insufficient-data branch).
    recommended_actions = recommend_readiness_actions(
        strategy_id, db, resolved_target
    )
    recommended_keys = {a.key for a in recommended_actions}

    # Warnings for ignored completed actions (unknown or not applicable).
    warnings: list[str] = []
    for key in sorted(completed):
        if key not in ACTION_CATALOG or key not in recommended_keys:
            warnings.append(
                f"Action {key} is not applicable to this strategy/target and "
                "was ignored."
            )

    # 3. No runs at all -> insufficient data.
    if not _has_any_run(strategy_id, db):
        warnings.insert(
            0,
            "Log a backtest run or ingest an evidence bundle to simulate "
            "readiness.",
        )
        return ReadinessSimulationData(
            strategy_id=strategy_id,
            strategy_name=strategy.name,
            current_stage=current_stage,
            target_stage=resolved_target,
            current_readiness_score=None,
            projected_readiness_score=None,
            current_verdict="insufficient_data",
            projected_verdict="insufficient_data",
            estimated_delta=0.0,
            current_blockers=[],
            remaining_blockers=[],
            recommended_actions=recommended_actions,
            simulated_completed_actions=sorted(completed),
            warnings=warnings,
            generated_at=now,
            disclaimer=DISCLAIMER,
        )

    # Base score: readiness, falling back to gate score, then 0.
    try:
        readiness = compute_strategy_readiness(strategy_id, db)
    except Exception:
        readiness = None

    try:
        gate_data = evaluate_promotion_gates(strategy_id, resolved_target, db)
    except Exception:
        gate_data = None

    base_score = readiness.readiness_score if readiness else None
    if base_score is None and gate_data is not None:
        base_score = gate_data.gate_score
    current_score = base_score  # may still be None

    # 4. Current verdict from gate verdict.
    if gate_data is not None:
        current_verdict = _map_gate_verdict_to_simple(gate_data.promotion_verdict)
    else:
        current_verdict = "review"

    # 5. Current blockers.
    current_blockers = list(gate_data.blockers) if gate_data else []

    # 7. Simulation — additive projection over recommended actions only.
    projected_score = float(base_score) if base_score is not None else 0.0
    for key in completed:
        if key in ACTION_CATALOG and key in recommended_keys:
            projected_score += ACTION_CATALOG[key]["impact_points"]
    projected_score = round(min(100.0, projected_score), 1)

    # Remaining blockers — drop those whose resolving actions are all completed.
    blocker_action_map = (
        _blocker_actions_map(gate_data, resolved_target) if gate_data else {}
    )
    has_paper_run = _has_run_type(strategy_id, db, ["paper", "live"])
    has_high_alerts = _has_high_or_critical_alerts(strategy_id, db)
    target_needs_paper = resolved_target in (
        "shadow_production",
        "production_candidate",
    )

    remaining_blockers: list[str] = []
    for blocker in current_blockers:
        resolving = blocker_action_map.get(blocker, [])

        # HARD RULES — keep the blocker regardless of score when the real-world
        # prerequisite is genuinely absent and not simulated as completed.
        b_lower = blocker.lower()
        is_paper_blocker = ("paper" in b_lower or "live" in b_lower) and target_needs_paper
        is_alert_blocker = "alert" in b_lower
        is_evidence_blocker = any(
            t in b_lower
            for t in ("dataset", "universe", "signal", "config", "coverage")
        )

        if (
            is_paper_blocker
            and not has_paper_run
            and "upload_paper_run" not in completed
        ):
            remaining_blockers.append(blocker)
            continue
        if (
            is_alert_blocker
            and has_high_alerts
            and "resolve_high_alerts" not in completed
        ):
            remaining_blockers.append(blocker)
            continue
        if is_evidence_blocker and not (
            "fix_evidence_links" in completed or "upload_fresh_evidence" in completed
        ):
            remaining_blockers.append(blocker)
            continue

        # General rule: drop the blocker only if it maps to action(s) and all of
        # them are completed. If it maps to nothing, keep it (we can't clear it).
        if resolving and all(a in completed for a in resolving):
            continue
        remaining_blockers.append(blocker)

    # 8. Projected verdict.
    if not remaining_blockers and projected_score >= 80:
        projected_verdict = "ready"
    elif projected_score >= 60:
        projected_verdict = "review"
    else:
        projected_verdict = "blocked"

    # 9. Estimated delta.
    if current_score is None:
        estimated_delta = 0.0
    else:
        estimated_delta = round(projected_score - float(current_score), 1)

    return ReadinessSimulationData(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        current_stage=current_stage,
        target_stage=resolved_target,
        current_readiness_score=(
            round(float(current_score), 1) if current_score is not None else None
        ),
        projected_readiness_score=projected_score,
        current_verdict=current_verdict,
        projected_verdict=projected_verdict,
        estimated_delta=estimated_delta,
        current_blockers=current_blockers,
        remaining_blockers=remaining_blockers,
        recommended_actions=recommended_actions,
        simulated_completed_actions=sorted(completed),
        warnings=warnings,
        generated_at=now,
        disclaimer=DISCLAIMER,
    )
