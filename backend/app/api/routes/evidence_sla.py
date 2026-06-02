"""API routes for M56 Evidence SLA Monitor."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.strategy import Strategy
from app.schemas.evidence_sla import (
    EvidenceSLAEvaluationListResponse,
    EvidenceSLAEvaluationRead,
    EvidenceSLAPolicyCreate,
    EvidenceSLAPolicyRead,
    EvidenceSLAResultRead,
)
from app.services import evidence_sla as svc

router = APIRouter()


def _load_strategy(strategy_id: str, db: Session) -> Strategy:
    strategy = db.query(Strategy).filter(Strategy.id == uuid.UUID(strategy_id)).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


def _eval_to_read(evaluation: object) -> EvidenceSLAEvaluationRead:
    results = [
        EvidenceSLAResultRead(
            id=str(r.id),
            evaluation_id=str(r.evaluation_id),
            rule_key=r.rule_key,
            title=r.title,
            evidence_type=r.evidence_type,
            status=r.status,
            severity=r.severity,
            is_required=r.is_required,
            observed_value=r.observed_value,
            expected_value=r.expected_value,
            days_since_latest=r.days_since_latest,
            latest_at=r.latest_at,
            evidence_json=r.evidence_json,
            suggested_action=r.suggested_action,
            created_at=r.created_at,
        )
        for r in (evaluation.results or [])
    ]
    return EvidenceSLAEvaluationRead(
        id=str(evaluation.id),
        strategy_id=str(evaluation.strategy_id),
        policy_id=str(evaluation.policy_id),
        overall_status=evaluation.overall_status,
        passed_count=evaluation.passed_count,
        warning_count=evaluation.warning_count,
        violated_count=evaluation.violated_count,
        skipped_count=evaluation.skipped_count,
        critical_violation_count=evaluation.critical_violation_count,
        result_json=evaluation.result_json,
        deterministic_summary=evaluation.deterministic_summary,
        created_at=evaluation.created_at,
        results=results,
    )


# POST /strategies/{strategy_id}/evidence-sla/default
@router.post(
    "/strategies/{strategy_id}/evidence-sla/default",
    response_model=EvidenceSLAPolicyRead,
)
def create_default_policy(
    strategy_id: str,
    db: Session = Depends(get_db),
) -> EvidenceSLAPolicyRead:
    _load_strategy(strategy_id, db)
    policy = svc.create_default_evidence_sla_policy(db, strategy_id)
    db.commit()
    return EvidenceSLAPolicyRead.from_orm_with_count(policy)


# POST /strategies/{strategy_id}/evidence-sla/policies
@router.post(
    "/strategies/{strategy_id}/evidence-sla/policies",
    response_model=EvidenceSLAPolicyRead,
    status_code=201,
)
def create_policy(
    strategy_id: str,
    payload: EvidenceSLAPolicyCreate,
    db: Session = Depends(get_db),
) -> EvidenceSLAPolicyRead:
    _load_strategy(strategy_id, db)
    policy = svc.create_evidence_sla_policy(db, strategy_id, payload.model_dump())
    db.commit()
    return EvidenceSLAPolicyRead.from_orm_with_count(policy)


# GET /strategies/{strategy_id}/evidence-sla/policies
@router.get(
    "/strategies/{strategy_id}/evidence-sla/policies",
    response_model=list[EvidenceSLAPolicyRead],
)
def list_policies(
    strategy_id: str,
    db: Session = Depends(get_db),
) -> list[EvidenceSLAPolicyRead]:
    _load_strategy(strategy_id, db)
    policies = svc.get_evidence_sla_policies(db, strategy_id)
    return [EvidenceSLAPolicyRead.from_orm_with_count(p) for p in policies]


# POST /strategies/{strategy_id}/evidence-sla/policies/{policy_id}/evaluate
@router.post(
    "/strategies/{strategy_id}/evidence-sla/policies/{policy_id}/evaluate",
    response_model=EvidenceSLAEvaluationRead,
)
def evaluate_policy(
    strategy_id: str,
    policy_id: str,
    db: Session = Depends(get_db),
) -> EvidenceSLAEvaluationRead:
    _load_strategy(strategy_id, db)
    evaluation = svc.evaluate_evidence_sla_policy(
        db,
        strategy_id=strategy_id,
        policy_id=policy_id,
    )
    db.commit()
    # Reload with results
    reloaded = svc.get_evidence_sla_evaluation(db, str(evaluation.id))
    return _eval_to_read(reloaded)


# GET /strategies/{strategy_id}/evidence-sla/evaluations
@router.get(
    "/strategies/{strategy_id}/evidence-sla/evaluations",
    response_model=EvidenceSLAEvaluationListResponse,
)
def list_evaluations(
    strategy_id: str,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> EvidenceSLAEvaluationListResponse:
    _load_strategy(strategy_id, db)
    evaluations = svc.get_evidence_sla_evaluations(db, strategy_id, limit=limit, offset=offset)
    items = [_eval_to_read(e) for e in evaluations]
    return EvidenceSLAEvaluationListResponse(items=items, total=len(items))


# GET /evidence-sla/evaluations/{evaluation_id}
@router.get(
    "/evidence-sla/evaluations/{evaluation_id}",
    response_model=EvidenceSLAEvaluationRead,
)
def get_evaluation(
    evaluation_id: str,
    db: Session = Depends(get_db),
) -> EvidenceSLAEvaluationRead:
    evaluation = svc.get_evidence_sla_evaluation(db, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return _eval_to_read(evaluation)
