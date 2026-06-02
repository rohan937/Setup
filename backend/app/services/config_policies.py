"""Strategy Config Policy Engine service (M54).

Deterministic — no AI, no live market data, no external calls.
Evaluates a set of rules against a flattened config snapshot.
Creates an AuditTimelineEvent when an evaluation is performed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.config_policy import (
    StrategyConfigPolicy,
    StrategyConfigPolicyEvaluation,
    StrategyConfigPolicyResult,
)
from app.models.strategy_config_snapshot import StrategyConfigSnapshot
from app.models.strategy import Strategy


# ---------------------------------------------------------------------------
# Flatten helper
# ---------------------------------------------------------------------------

def _flatten_config(config_json: dict, prefix: str = "") -> dict[str, Any]:
    """Flatten a nested dict to dot-separated key paths.

    e.g. {"assumptions": {"cost": 5}} -> {"assumptions.cost": 5}
    Non-dict values (lists, strings, numbers, bools, None) are leaf values.
    """
    result: dict[str, Any] = {}
    for key, value in config_json.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten_config(value, prefix=full_key))
        else:
            result[full_key] = value
    return result


# ---------------------------------------------------------------------------
# Rule evaluator
# ---------------------------------------------------------------------------

def _eval_rule(rule: dict, flat_config: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one policy rule against the flattened config.

    Returns a result dict with keys:
        rule_key, title, status, severity, is_required,
        observed_value, expected_value, key_path,
        evidence_json, suggested_action
    """
    rule_key = rule["rule_key"]
    title = rule["title"]
    key_path = rule.get("key_path", "")
    operator = rule.get("operator", "exists")
    expected = rule.get("expected_value")
    severity = rule.get("severity", "medium")
    is_required = rule.get("is_required", True)
    condition_json = rule.get("condition_json")
    now = datetime.now(timezone.utc)

    def _make_result(
        status: str,
        observed: Any = None,
        evidence: dict | None = None,
        suggested: str | None = None,
    ) -> dict[str, Any]:
        obs_str = str(observed) if observed is not None else None
        exp_str = str(expected) if expected is not None else None
        if status == "failed" and is_required and not suggested:
            suggested = f"Review {title} in config snapshot before progressing strategy."
        return {
            "rule_key": rule_key,
            "title": title,
            "status": status,
            "severity": severity,
            "is_required": is_required,
            "observed_value": obs_str,
            "expected_value": exp_str,
            "key_path": key_path,
            "evidence_json": evidence or {},
            "suggested_action": suggested,
            "created_at": now,
        }

    # --- Conditional evaluation ---
    if condition_json:
        cond_key = condition_json.get("key_path", "")
        cond_op = condition_json.get("operator", "eq")
        cond_exp = condition_json.get("expected_value")
        cond_val = flat_config.get(cond_key)
        cond_met = _apply_operator(cond_op, cond_val, cond_exp)
        if not cond_met:
            return _make_result(
                "skipped",
                evidence={
                    "condition_key": cond_key,
                    "condition_value": str(cond_val),
                    "condition_expected": str(cond_exp),
                    "reason": "Condition not met; rule skipped.",
                },
            )

    # --- Normal evaluation ---
    observed = flat_config.get(key_path)
    passed = _apply_operator(operator, observed, expected)

    if passed is None:
        # Non-numeric value for numeric operator: skip
        return _make_result(
            "skipped",
            observed=observed,
            evidence={"reason": f"Non-numeric value for operator '{operator}'; skipped."},
        )

    if passed:
        return _make_result("passed", observed=observed)
    else:
        # failed: severity warning -> warning status, otherwise failed
        status = "warning" if severity in ("low", "medium") and not is_required else "failed"
        return _make_result(
            status,
            observed=observed,
            evidence={"operator": operator, "expected": str(expected) if expected is not None else None},
        )


def _apply_operator(operator: str, observed: Any, expected: Any) -> bool | None:
    """Apply an operator comparison. Returns None to signal skip (e.g. non-numeric)."""
    if operator == "exists":
        return observed is not None
    if operator == "not_exists":
        return observed is None
    if operator == "eq":
        return observed == expected
    if operator == "neq":
        return observed != expected
    if operator == "in":
        if not isinstance(expected, list):
            return False
        return observed in expected
    if operator == "not_in":
        if not isinstance(expected, list):
            return True
        return observed not in expected
    if operator in ("gte", "lte", "gt", "lt"):
        if observed is None:
            # Key absent: for non-required rules this is not a failure
            return None
        try:
            obs_num = float(observed)
            exp_num = float(expected)
        except (TypeError, ValueError):
            return None
        if operator == "gte":
            return obs_num >= exp_num
        if operator == "lte":
            return obs_num <= exp_num
        if operator == "gt":
            return obs_num > exp_num
        if operator == "lt":
            return obs_num < exp_num
    if operator == "contains":
        if observed is None:
            return False
        return str(expected) in str(observed)
    if operator == "not_contains":
        if observed is None:
            return True
        return str(expected) not in str(observed)
    return False


# ---------------------------------------------------------------------------
# Default rules
# ---------------------------------------------------------------------------

DEFAULT_RULES: list[dict[str, Any]] = [
    # 1
    {
        "rule_key": "transaction_cost_required",
        "title": "Transaction cost assumption required",
        "key_path": "assumptions.transaction_cost_bps",
        "operator": "exists",
        "severity": "high",
        "is_required": True,
    },
    # 2
    {
        "rule_key": "transaction_cost_positive",
        "title": "Transaction cost should be positive",
        "key_path": "assumptions.transaction_cost_bps",
        "operator": "gt",
        "expected_value": 0,
        "severity": "medium",
        "is_required": False,
    },
    # 3
    {
        "rule_key": "slippage_required",
        "title": "Slippage assumption recommended",
        "key_path": "assumptions.slippage_bps",
        "operator": "exists",
        "severity": "medium",
        "is_required": False,
    },
    # 4
    {
        "rule_key": "slippage_positive",
        "title": "Slippage should be positive when present",
        "key_path": "assumptions.slippage_bps",
        "operator": "gt",
        "expected_value": 0,
        "severity": "low",
        "is_required": False,
    },
    # 5
    {
        "rule_key": "fill_model_required",
        "title": "Fill model assumption required",
        "key_path": "assumptions.fill_model",
        "operator": "exists",
        "severity": "high",
        "is_required": True,
    },
    # 6
    {
        "rule_key": "fill_model_not_same_close",
        "title": "Fill model must not use same-close or exact execution",
        "key_path": "assumptions.fill_model",
        "operator": "not_in",
        "expected_value": ["same_close", "close", "same_bar", "exact_close"],
        "severity": "high",
        "is_required": True,
    },
    # 7
    {
        "rule_key": "execution_timing_not_same_bar",
        "title": "Execution timing should not be same-bar",
        "key_path": "assumptions.execution_timing",
        "operator": "neq",
        "expected_value": "same_bar",
        "severity": "medium",
        "is_required": False,
    },
    # 8 — conditional
    {
        "rule_key": "borrow_cost_when_short",
        "title": "Borrow cost required when shorting is enabled",
        "key_path": "assumptions.borrow_cost_bps",
        "operator": "exists",
        "severity": "high",
        "is_required": True,
        "condition_json": {
            "key_path": "assumptions.short_enabled",
            "operator": "eq",
            "expected_value": True,
        },
    },
    # 9
    {
        "rule_key": "leverage_limit",
        "title": "Max leverage should not exceed 2x when specified",
        "key_path": "assumptions.max_leverage",
        "operator": "lte",
        "expected_value": 2.0,
        "severity": "medium",
        "is_required": False,
    },
    # 10
    {
        "rule_key": "position_weight_limit",
        "title": "Max position weight should be <= 25% when specified",
        "key_path": "portfolio.max_position_weight",
        "operator": "lte",
        "expected_value": 0.25,
        "severity": "low",
        "is_required": False,
    },
    # 11 — compound (handled specially in evaluator)
    {
        "rule_key": "risk_controls_present",
        "title": "Risk controls recommended",
        "key_path": "__compound__risk_controls",
        "operator": "__compound__",
        "compound_keys": [
            "risk.stop_loss",
            "risk.max_drawdown_limit",
            "assumptions.stop_loss",
            "assumptions.max_drawdown_limit",
        ],
        "severity": "medium",
        "is_required": False,
    },
    # 12 — compound (handled specially)
    {
        "rule_key": "liquidity_filter_present",
        "title": "Liquidity filter recommended",
        "key_path": "__compound__liquidity_filter",
        "operator": "__compound__",
        "compound_keys": [
            "assumptions.liquidity_filter",
            "assumptions.adv_filter",
        ],
        "severity": "low",
        "is_required": False,
    },
    # 13
    {
        "rule_key": "participation_rate_limit",
        "title": "Participation rate should be <= 15% when specified",
        "key_path": "assumptions.participation_rate",
        "operator": "lte",
        "expected_value": 0.15,
        "severity": "low",
        "is_required": False,
    },
    # 14
    {
        "rule_key": "dataset_version_reference",
        "title": "Dataset version reference recommended for evidence traceability",
        "key_path": "assumptions.dataset_version",
        "operator": "exists",
        "severity": "info",
        "is_required": False,
    },
    # 15
    {
        "rule_key": "params_lookback_present",
        "title": "Lookback parameter documented for reproducibility",
        "key_path": "params.lookback_days",
        "operator": "exists",
        "severity": "info",
        "is_required": False,
    },
]


def _eval_rule_with_compound(rule: dict, flat_config: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a rule, handling compound operators specially."""
    operator = rule.get("operator", "exists")
    now = datetime.now(timezone.utc)

    if operator == "__compound__":
        compound_keys = rule.get("compound_keys", [])
        title = rule["title"]
        rule_key = rule["rule_key"]
        severity = rule.get("severity", "medium")
        is_required = rule.get("is_required", False)

        any_present = any(
            flat_config.get(k) is not None for k in compound_keys
        )

        if any_present:
            found_key = next(k for k in compound_keys if flat_config.get(k) is not None)
            return {
                "rule_key": rule_key,
                "title": title,
                "status": "passed",
                "severity": severity,
                "is_required": is_required,
                "observed_value": str(flat_config[found_key]),
                "expected_value": None,
                "key_path": found_key,
                "evidence_json": {"found_key": found_key},
                "suggested_action": None,
                "created_at": now,
            }
        else:
            suggested = None
            if is_required:
                suggested = f"Review {title} in config snapshot before progressing strategy."
            return {
                "rule_key": rule_key,
                "title": title,
                "status": "warning",
                "severity": severity,
                "is_required": is_required,
                "observed_value": None,
                "expected_value": None,
                "key_path": rule.get("key_path"),
                "evidence_json": {"checked_keys": compound_keys},
                "suggested_action": suggested,
                "created_at": now,
            }

    return _eval_rule(rule, flat_config)


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

def create_default_config_policy(db: Session, strategy_id: str) -> StrategyConfigPolicy:
    """Create (or return existing) the default QuantFidelity assumption guardrails policy."""
    default_name = "QuantFidelity Default Assumption Guardrails"

    existing = (
        db.query(StrategyConfigPolicy)
        .filter(
            StrategyConfigPolicy.strategy_id == uuid.UUID(strategy_id),
            StrategyConfigPolicy.name == default_name,
        )
        .first()
    )
    if existing:
        return existing

    policy = StrategyConfigPolicy(
        strategy_id=uuid.UUID(strategy_id),
        name=default_name,
        description=(
            "Default set of assumption guardrails for strategy config snapshots. "
            "Checks transaction costs, fill models, leverage, risk controls, and more."
        ),
        is_active=True,
        policy_json={"rules": DEFAULT_RULES},
    )
    db.add(policy)
    db.flush()
    return policy


def create_config_policy(db: Session, strategy_id: str, payload: dict) -> StrategyConfigPolicy:
    """Create a new custom config policy for a strategy."""
    strategy = db.query(Strategy).filter(Strategy.id == uuid.UUID(strategy_id)).first()
    if not strategy:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Strategy not found")

    policy = StrategyConfigPolicy(
        strategy_id=uuid.UUID(strategy_id),
        name=payload["name"],
        description=payload.get("description"),
        is_active=payload.get("is_active", True),
        policy_json=payload["policy_json"],
    )
    db.add(policy)
    db.flush()
    return policy


def get_config_policies(db: Session, strategy_id: str) -> list[StrategyConfigPolicy]:
    """Return all policies for a strategy, newest first."""
    return (
        db.query(StrategyConfigPolicy)
        .filter(StrategyConfigPolicy.strategy_id == uuid.UUID(strategy_id))
        .order_by(StrategyConfigPolicy.created_at.desc())
        .all()
    )


def evaluate_config_policy(
    db: Session,
    strategy_id: str,
    policy_id: str,
    config_snapshot_id: str | None = None,
) -> StrategyConfigPolicyEvaluation:
    """Evaluate a policy against a config snapshot.

    Persists evaluation + per-rule results + AuditTimelineEvent.
    """
    from app.models.audit_timeline_event import AuditTimelineEvent
    from app.core.constants import EventType, Severity

    now = datetime.now(timezone.utc)

    # Load policy
    policy = (
        db.query(StrategyConfigPolicy)
        .filter(
            StrategyConfigPolicy.id == uuid.UUID(policy_id),
            StrategyConfigPolicy.strategy_id == uuid.UUID(strategy_id),
        )
        .first()
    )
    if not policy:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Policy not found")

    # Load strategy (for timeline event)
    strategy = (
        db.query(Strategy)
        .filter(Strategy.id == uuid.UUID(strategy_id))
        .first()
    )

    # Load config snapshot
    snapshot: StrategyConfigSnapshot | None = None
    if config_snapshot_id:
        snapshot = (
            db.query(StrategyConfigSnapshot)
            .filter(StrategyConfigSnapshot.id == uuid.UUID(config_snapshot_id))
            .first()
        )
    else:
        snapshot = (
            db.query(StrategyConfigSnapshot)
            .filter(StrategyConfigSnapshot.strategy_id == uuid.UUID(strategy_id))
            .order_by(StrategyConfigSnapshot.created_at.desc())
            .first()
        )

    # No snapshot: return insufficient_evidence evaluation
    if snapshot is None:
        evaluation = StrategyConfigPolicyEvaluation(
            strategy_id=uuid.UUID(strategy_id),
            policy_id=policy.id,
            config_snapshot_id=None,
            overall_status="insufficient_evidence",
            passed_count=0,
            warning_count=0,
            failed_count=0,
            skipped_count=0,
            critical_failed_count=0,
            result_json=None,
            deterministic_summary="No config snapshot found for strategy.",
            created_at=now,
        )
        db.add(evaluation)
        db.flush()

        _create_evaluation_timeline_event(
            db=db,
            strategy=strategy,
            evaluation=evaluation,
            now=now,
        )
        return evaluation

    # Flatten config
    flat_config = _flatten_config(snapshot.config_json or {})

    # Evaluate rules
    rules = policy.policy_json.get("rules", []) if policy.policy_json else []

    if not rules or not flat_config:
        evaluation = StrategyConfigPolicyEvaluation(
            strategy_id=uuid.UUID(strategy_id),
            policy_id=policy.id,
            config_snapshot_id=snapshot.id,
            overall_status="insufficient_evidence",
            passed_count=0,
            warning_count=0,
            failed_count=0,
            skipped_count=0,
            critical_failed_count=0,
            result_json=[],
            deterministic_summary="Insufficient evidence: no rules or empty config.",
            created_at=now,
        )
        db.add(evaluation)
        db.flush()
        _create_evaluation_timeline_event(db=db, strategy=strategy, evaluation=evaluation, now=now)
        return evaluation

    rule_results: list[dict[str, Any]] = []
    for rule in rules:
        result = _eval_rule_with_compound(rule, flat_config)
        rule_results.append(result)

    # Compute counts
    passed_count = sum(1 for r in rule_results if r["status"] == "passed")
    warning_count = sum(1 for r in rule_results if r["status"] == "warning")
    failed_count = sum(1 for r in rule_results if r["status"] == "failed")
    skipped_count = sum(1 for r in rule_results if r["status"] == "skipped")
    critical_failed_count = sum(
        1 for r in rule_results
        if r["status"] == "failed" and r["severity"] in ("high", "critical")
    )

    # Compute overall_status
    has_critical_required_fail = any(
        r["status"] == "failed" and r["is_required"] and r["severity"] in ("high", "critical")
        for r in rule_results
    )
    has_any_fail = any(r["status"] == "failed" for r in rule_results)
    has_any_warning = any(r["status"] == "warning" for r in rule_results)

    if has_critical_required_fail or (has_any_fail and any(
        r["status"] == "failed" and r["is_required"] for r in rule_results
    )):
        overall_status = "failed"
    elif has_any_fail or has_any_warning:
        overall_status = "warning"
    else:
        overall_status = "passed"

    # Build deterministic summary
    failed_titles = [r["title"] for r in rule_results if r["status"] == "failed"]
    summary_parts = [
        f"Config policy evaluation: {passed_count} passed, "
        f"{failed_count} failed, {skipped_count} skipped."
    ]
    if failed_titles:
        # Join up to 3 failure titles
        joined = " ".join(f"{t}." for t in failed_titles[:3])
        summary_parts.append(joined)
    deterministic_summary = " ".join(summary_parts)

    # Persist evaluation
    evaluation = StrategyConfigPolicyEvaluation(
        strategy_id=uuid.UUID(strategy_id),
        policy_id=policy.id,
        config_snapshot_id=snapshot.id,
        overall_status=overall_status,
        passed_count=passed_count,
        warning_count=warning_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        critical_failed_count=critical_failed_count,
        result_json=[
            {k: v for k, v in r.items() if k != "created_at"}
            for r in rule_results
        ],
        deterministic_summary=deterministic_summary,
        created_at=now,
    )
    db.add(evaluation)
    db.flush()

    # Persist per-rule results
    for r in rule_results:
        result_row = StrategyConfigPolicyResult(
            evaluation_id=evaluation.id,
            rule_key=r["rule_key"],
            title=r["title"],
            status=r["status"],
            severity=r["severity"],
            is_required=r["is_required"],
            observed_value=r.get("observed_value"),
            expected_value=r.get("expected_value"),
            key_path=r.get("key_path"),
            evidence_json=r.get("evidence_json"),
            suggested_action=r.get("suggested_action"),
            created_at=r.get("created_at", now),
        )
        db.add(result_row)
    db.flush()

    # AuditTimelineEvent
    _create_evaluation_timeline_event(db=db, strategy=strategy, evaluation=evaluation, now=now)

    return evaluation


def _create_evaluation_timeline_event(
    db: Session,
    strategy: Any,
    evaluation: StrategyConfigPolicyEvaluation,
    now: datetime,
) -> None:
    """Persist an AuditTimelineEvent for a config policy evaluation."""
    from app.models.audit_timeline_event import AuditTimelineEvent
    from app.core.constants import EventType, Severity

    if evaluation.overall_status == "passed":
        sev = Severity.info
    elif evaluation.overall_status == "warning":
        sev = Severity.medium
    elif evaluation.overall_status == "failed":
        sev = Severity.high
    else:
        sev = Severity.info

    event = AuditTimelineEvent(
        organization_id=strategy.project.organization_id,
        project_id=strategy.project_id,
        strategy_id=strategy.id,
        event_type=EventType.config_policy_evaluated,
        title="Config policy evaluated",
        description=evaluation.deterministic_summary,
        source_type="config_policy",
        source_id=str(evaluation.id),
        severity=sev,
        event_time=now,
        metadata_json={
            "overall_status": evaluation.overall_status,
            "passed_count": evaluation.passed_count,
            "failed_count": evaluation.failed_count,
            "policy_id": str(evaluation.policy_id),
            "config_snapshot_id": str(evaluation.config_snapshot_id) if evaluation.config_snapshot_id else None,
        },
    )
    db.add(event)
    db.flush()


def get_config_policy_evaluations(
    db: Session,
    strategy_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[StrategyConfigPolicyEvaluation]:
    """Return evaluations for a strategy, newest first."""
    return (
        db.query(StrategyConfigPolicyEvaluation)
        .filter(StrategyConfigPolicyEvaluation.strategy_id == uuid.UUID(strategy_id))
        .order_by(StrategyConfigPolicyEvaluation.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_config_policy_evaluation(
    db: Session,
    evaluation_id: str,
) -> StrategyConfigPolicyEvaluation | None:
    """Return a single evaluation with its results eagerly loaded."""
    from sqlalchemy.orm import joinedload

    return (
        db.query(StrategyConfigPolicyEvaluation)
        .options(joinedload(StrategyConfigPolicyEvaluation.results))
        .filter(StrategyConfigPolicyEvaluation.id == uuid.UUID(evaluation_id))
        .first()
    )
