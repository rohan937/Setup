"""M55 Research Review Cases API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import review_cases as svc
from app.schemas.review_cases import (
    ResearchReviewCaseRead,
    ResearchReviewCaseGenerateResponse,
    ResearchReviewCaseListResponse,
)
from app.models.strategy import Strategy
from app.models.review_case import ResearchReviewCase

router = APIRouter()


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Not found")


@router.post(
    "/strategies/{strategy_id}/review-cases/generate",
    response_model=ResearchReviewCaseGenerateResponse,
)
def generate_review_cases(
    strategy_id: str,
    db: Session = Depends(get_db),
) -> ResearchReviewCaseGenerateResponse:
    """Generate or refresh research review cases for a strategy."""
    strategy = db.query(Strategy).filter(Strategy.id == _parse_uuid(strategy_id)).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    cases = svc.generate_research_review_cases(db, strategy_id)
    db.commit()

    # Reload cases with events
    loaded = [
        svc.get_research_review_case(db, str(c.id))
        for c in cases
        if svc.get_research_review_case(db, str(c.id)) is not None
    ]

    new_count = sum(
        1 for c in loaded
        if c is not None and not c.events or (
            c is not None and c.events and len(c.events) == 1 and c.events[0].event_type == "opened"
        )
    )
    refreshed_count = len(loaded) - new_count

    total_open = (
        db.query(ResearchReviewCase)
        .filter(
            ResearchReviewCase.strategy_id == str(strategy_id),
            ResearchReviewCase.status.in_(["open", "acknowledged"]),
        )
        .count()
    )

    return ResearchReviewCaseGenerateResponse(
        strategy_id=str(strategy_id),
        generated_count=len([c for c in loaded if c is not None]),
        refreshed_count=0,
        total_open=total_open,
        cases=[ResearchReviewCaseRead.model_validate(c) for c in loaded if c is not None],
    )


@router.get(
    "/strategies/{strategy_id}/review-cases",
    response_model=ResearchReviewCaseListResponse,
)
def list_review_cases(
    strategy_id: str,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ResearchReviewCaseListResponse:
    """List research review cases for a strategy."""
    strategy = db.query(Strategy).filter(Strategy.id == _parse_uuid(strategy_id)).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    cases = svc.get_research_review_cases(
        db, strategy_id, status=status, limit=limit, offset=offset
    )
    total = (
        db.query(ResearchReviewCase)
        .filter(ResearchReviewCase.strategy_id == str(strategy_id))
        .count()
    )

    return ResearchReviewCaseListResponse(
        items=[ResearchReviewCaseRead.model_validate(c) for c in cases],
        total=total,
    )


@router.get(
    "/review-cases/{case_id}",
    response_model=ResearchReviewCaseRead,
)
def get_review_case(
    case_id: str,
    db: Session = Depends(get_db),
) -> ResearchReviewCaseRead:
    """Get a single research review case by ID."""
    case = svc.get_research_review_case(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Review case not found")
    return ResearchReviewCaseRead.model_validate(case)


@router.post(
    "/review-cases/{case_id}/acknowledge",
    response_model=ResearchReviewCaseRead,
)
def acknowledge_review_case(
    case_id: str,
    db: Session = Depends(get_db),
) -> ResearchReviewCaseRead:
    """Acknowledge an open review case."""
    case = svc.acknowledge_research_review_case(db, case_id)
    if case is None:
        raise HTTPException(
            status_code=404,
            detail="Review case not found or is not in 'open' status",
        )
    db.commit()
    refreshed = svc.get_research_review_case(db, str(case.id))
    return ResearchReviewCaseRead.model_validate(refreshed)


@router.post(
    "/review-cases/{case_id}/resolve",
    response_model=ResearchReviewCaseRead,
)
def resolve_review_case(
    case_id: str,
    db: Session = Depends(get_db),
) -> ResearchReviewCaseRead:
    """Resolve a review case."""
    case = svc.resolve_research_review_case(db, case_id)
    if case is None:
        raise HTTPException(
            status_code=404,
            detail="Review case not found or is already resolved",
        )
    db.commit()
    refreshed = svc.get_research_review_case(db, str(case.id))
    return ResearchReviewCaseRead.model_validate(refreshed)
