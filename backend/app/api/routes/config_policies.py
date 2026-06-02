"""API routes for M54 config policy engine."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.strategy import Strategy
from app.schemas.config_policy import (
    ConfigPolicyEvaluationListResponse,
    ConfigPolicyEvaluationRead,
    ConfigPolicyEvaluationRequest,
    ConfigPolicyResultRead,
    StrategyConfigPolicyCreate,
    StrategyConfigPolicyRead,
)
from app.services import config_policies as svc

router = APIRouter()


def _load_strategy(strategy_id: str, db: Session) -> Strategy:
    strategy = db.query(Strategy).filter(Strategy.id == uuid.UUID(strategy_id)).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


def _eval_to_read(evaluation) -> ConfigPolicyEvaluationRead:
    results = [
        ConfigPolicyResultRead(
            id=str(r.id),
            evaluation_id=str(r.evaluation_id),
            rule_key=r.rule_key,
            title=r.title,
            status=r.status,
            severity=r.severity,
            is_required=r.is_required,
            observed_value=r.observed_value,
            expected_value=r.expected_value,
            key_path=r.key_path,
            evidence_json=r.evidence_json,
            suggested_action=r.suggested_action,
            created_at=r.created_at,
        )
        for r in (evaluation.results or [])
    ]
    return ConfigPolicyEvaluationRead(
        id=str(evaluation.id),
        strategy_id=str(evaluation.strategy_id),
        policy_id=str(evaluation.policy_id),
        config_snapshot_id=str(evaluation.config_snapshot_id) if evaluation.config_snapshot_id else None,
        overall_status=evaluation.overall_status,
        passed_count=evaluation.passed_count,
        warning_count=evaluation.warning_count,
        failed_count=evaluation.failed_count,
        skipped_count=evaluation.skipped_count,
        critical_failed_count=evaluation.critical_failed_count,
        result_json=evaluation.result_json,
        deterministic_summary=evaluation.deterministic_summary,
        created_at=evaluation.created_at,
        results=results,
    )


# POST /strategies/{strategy_id}/config-policies/default
@router.post(
    "/strategies/{strategy_id}/config-policies/default",
    response_model=StrategyConfigPolicyRead,
)
def create_default_policy(
    strategy_id: str,
    db: Session = Depends(get_db),
) -> StrategyConfigPolicyRead:
    _load_strategy(strategy_id, db)
    policy = svc.create_default_config_policy(db, strategy_id)
    db.commit()
    return StrategyConfigPolicyRead.from_orm_with_count(policy)


# POST /strategies/{strategy_id}/config-policies
@router.post(
    "/strategies/{strategy_id}/config-policies",
    response_model=StrategyConfigPolicyRead,
    status_code=201,
)
def create_policy(
    strategy_id: str,
    payload: StrategyConfigPolicyCreate,
    db: Session = Depends(get_db),
) -> StrategyConfigPolicyRead:
    _load_strategy(strategy_id, db)
    policy = svc.create_config_policy(db, strategy_id, payload.model_dump())
    db.commit()
    return StrategyConfigPolicyRead.from_orm_with_count(policy)


# GET /strategies/{strategy_id}/config-policies
@router.get(
    "/strategies/{strategy_id}/config-policies",
    response_model=list[StrategyConfigPolicyRead],
)
def list_policies(
    strategy_id: str,
    db: Session = Depends(get_db),
) -> list[StrategyConfigPolicyRead]:
    _load_strategy(strategy_id, db)
    policies = svc.get_config_policies(db, strategy_id)
    return [StrategyConfigPolicyRead.from_orm_with_count(p) for p in policies]


# POST /strategies/{strategy_id}/config-policies/{policy_id}/evaluate
@router.post(
    "/strategies/{strategy_id}/config-policies/{policy_id}/evaluate",
    response_model=ConfigPolicyEvaluationRead,
)
def evaluate_policy(
    strategy_id: str,
    policy_id: str,
    body: ConfigPolicyEvaluationRequest | None = None,
    db: Session = Depends(get_db),
) -> ConfigPolicyEvaluationRead:
    _load_strategy(strategy_id, db)
    config_snapshot_id = body.config_snapshot_id if body else None
    evaluation = svc.evaluate_config_policy(
        db,
        strategy_id=strategy_id,
        policy_id=policy_id,
        config_snapshot_id=config_snapshot_id,
    )
    db.commit()
    # Reload with results
    reloaded = svc.get_config_policy_evaluation(db, str(evaluation.id))
    return _eval_to_read(reloaded)


# GET /strategies/{strategy_id}/config-policy-evaluations
@router.get(
    "/strategies/{strategy_id}/config-policy-evaluations",
    response_model=ConfigPolicyEvaluationListResponse,
)
def list_evaluations(
    strategy_id: str,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> ConfigPolicyEvaluationListResponse:
    _load_strategy(strategy_id, db)
    evaluations = svc.get_config_policy_evaluations(db, strategy_id, limit=limit, offset=offset)
    items = [_eval_to_read(e) for e in evaluations]
    return ConfigPolicyEvaluationListResponse(items=items, total=len(items))


# GET /config-policy-evaluations/{evaluation_id}
@router.get(
    "/config-policy-evaluations/{evaluation_id}",
    response_model=ConfigPolicyEvaluationRead,
)
def get_evaluation(
    evaluation_id: str,
    db: Session = Depends(get_db),
) -> ConfigPolicyEvaluationRead:
    evaluation = svc.get_config_policy_evaluation(db, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return _eval_to_read(evaluation)
