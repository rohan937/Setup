"""M87 Strategy Review API routes.

Endpoints (all included under the ``/api`` prefix):

  GET    /api/strategies/{strategy_id}/reviews
  POST   /api/strategies/{strategy_id}/reviews
  GET    /api/strategy-reviews/pending
  GET    /api/strategy-reviews/decisions
  GET    /api/strategy-reviews/{review_id}
  POST   /api/strategy-reviews/{review_id}/submit
  POST   /api/strategy-reviews/{review_id}/approve
  POST   /api/strategy-reviews/{review_id}/reject
  POST   /api/strategy-reviews/{review_id}/request-changes
  POST   /api/strategy-reviews/{review_id}/comments
  GET    /api/strategy-reviews/{review_id}/packet

LITERAL paths (/pending, /decisions) are registered BEFORE the
``/{review_id}`` parameterised route so they are not shadowed.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_optional_current_user
from app.core.rbac import (
    get_current_workspace_member,
    require_verified_email,
    require_workspace_admin,
    require_workspace_write_access,
)
from app.db.session import get_db
from app.models.strategy import Strategy
from app.models.strategy_review import StrategyReview
from app.schemas.strategy_reviews import (
    CreateReviewRequest,
    ReviewCommentRequest,
    ReviewDecisionRequest,
    ReviewPacketResponse,
    StrategyReviewCommentRead,
    StrategyReviewDetailResponse,
    StrategyReviewEventRead,
    StrategyReviewListResponse,
    StrategyReviewRead,
)
from app.services import strategy_reviews as svc
from app.services.strategy_reviews import BlockedApproval

router = APIRouter()


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail="Not found")


def _actor_id(current) -> str | None:
    return str(current.id) if current is not None else None


def _list(reviews) -> StrategyReviewListResponse:
    return StrategyReviewListResponse(
        items=[StrategyReviewRead.model_validate(r) for r in reviews]
    )


# ---------------------------------------------------------------------------
# Strategy-scoped
# ---------------------------------------------------------------------------

@router.get(
    "/strategies/{strategy_id}/reviews",
    response_model=StrategyReviewListResponse,
)
def list_strategy_reviews(
    strategy_id: str,
    db: Session = Depends(get_db),
) -> StrategyReviewListResponse:
    sid = _parse_uuid(strategy_id)
    strategy = db.query(Strategy).filter(Strategy.id == sid).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return _list(svc.get_strategy_reviews(db, sid))


@router.post(
    "/strategies/{strategy_id}/reviews",
    response_model=StrategyReviewRead,
)
def create_strategy_review(
    strategy_id: str,
    payload: CreateReviewRequest,
    db: Session = Depends(get_db),
    current=Depends(get_optional_current_user),
    _member=Depends(require_workspace_write_access),
    _verified=Depends(require_verified_email),
) -> StrategyReviewRead:
    sid = _parse_uuid(strategy_id)
    strategy = db.query(Strategy).filter(Strategy.id == sid).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    try:
        review = svc.submit_strategy_review(
            db, sid, payload.target_stage, _actor_id(current), as_draft=payload.as_draft
        )
    except ValueError as exc:
        msg = str(exc)
        if "active review already exists" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    db.commit()
    db.refresh(review)
    return StrategyReviewRead.model_validate(review)


# ---------------------------------------------------------------------------
# Portfolio-level LITERAL paths (must precede /{review_id})
# ---------------------------------------------------------------------------

@router.get("/strategy-reviews/pending", response_model=StrategyReviewListResponse)
def list_pending_reviews(
    db: Session = Depends(get_db),
) -> StrategyReviewListResponse:
    return _list(svc.get_pending_reviews(db))


@router.get("/strategy-reviews/decisions", response_model=StrategyReviewListResponse)
def list_decisions(
    db: Session = Depends(get_db),
) -> StrategyReviewListResponse:
    return _list(svc.get_decisions(db))


# ---------------------------------------------------------------------------
# Review-scoped
# ---------------------------------------------------------------------------

@router.get(
    "/strategy-reviews/{review_id}",
    response_model=StrategyReviewDetailResponse,
)
def get_review(
    review_id: str,
    db: Session = Depends(get_db),
) -> StrategyReviewDetailResponse:
    rid = _parse_uuid(review_id)
    detail = svc.get_review_detail(db, rid)
    if detail is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return StrategyReviewDetailResponse(
        review=StrategyReviewRead.model_validate(detail["review"]),
        checklist=detail["checklist"],
        comments=[
            StrategyReviewCommentRead.model_validate(c) for c in detail["comments"]
        ],
        events=[
            StrategyReviewEventRead.model_validate(e) for e in detail["events"]
        ],
    )


@router.post(
    "/strategy-reviews/{review_id}/submit",
    response_model=StrategyReviewRead,
)
def submit_review(
    review_id: str,
    db: Session = Depends(get_db),
    current=Depends(get_optional_current_user),
    _member=Depends(require_workspace_write_access),
    _verified=Depends(require_verified_email),
) -> StrategyReviewRead:
    rid = _parse_uuid(review_id)
    review = db.query(StrategyReview).filter(StrategyReview.id == str(rid)).first()
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    try:
        review = svc.submit_existing(db, rid, _actor_id(current))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    db.refresh(review)
    return StrategyReviewRead.model_validate(review)


@router.post(
    "/strategy-reviews/{review_id}/approve",
    response_model=StrategyReviewRead,
)
def approve_review(
    review_id: str,
    db: Session = Depends(get_db),
    current=Depends(get_optional_current_user),
    member=Depends(require_workspace_admin),
    _verified=Depends(require_verified_email),
) -> StrategyReviewRead:
    rid = _parse_uuid(review_id)
    review = db.query(StrategyReview).filter(StrategyReview.id == str(rid)).first()
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")

    actor_is_owner = getattr(member, "role", None) == "owner" or getattr(
        member, "is_pseudo", False
    )
    try:
        review = svc.approve_strategy_review(
            db, rid, _actor_id(current), actor_is_owner=actor_is_owner
        )
    except BlockedApproval as exc:
        raise HTTPException(
            status_code=400,
            detail={"message": str(exc), "blockers": exc.blockers},
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    db.refresh(review)
    return StrategyReviewRead.model_validate(review)


@router.post(
    "/strategy-reviews/{review_id}/reject",
    response_model=StrategyReviewRead,
)
def reject_review(
    review_id: str,
    payload: ReviewDecisionRequest,
    db: Session = Depends(get_db),
    current=Depends(get_optional_current_user),
    _member=Depends(require_workspace_admin),
    _verified=Depends(require_verified_email),
) -> StrategyReviewRead:
    rid = _parse_uuid(review_id)
    review = db.query(StrategyReview).filter(StrategyReview.id == str(rid)).first()
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    try:
        review = svc.reject_strategy_review(db, rid, _actor_id(current), payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    db.refresh(review)
    return StrategyReviewRead.model_validate(review)


@router.post(
    "/strategy-reviews/{review_id}/request-changes",
    response_model=StrategyReviewRead,
)
def request_changes_review(
    review_id: str,
    payload: ReviewDecisionRequest,
    db: Session = Depends(get_db),
    current=Depends(get_optional_current_user),
    _member=Depends(require_workspace_admin),
    _verified=Depends(require_verified_email),
) -> StrategyReviewRead:
    rid = _parse_uuid(review_id)
    review = db.query(StrategyReview).filter(StrategyReview.id == str(rid)).first()
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    try:
        review = svc.request_changes(db, rid, _actor_id(current), payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    db.refresh(review)
    return StrategyReviewRead.model_validate(review)


@router.post(
    "/strategy-reviews/{review_id}/comments",
    response_model=StrategyReviewCommentRead,
)
def add_comment(
    review_id: str,
    payload: ReviewCommentRequest,
    db: Session = Depends(get_db),
    current=Depends(get_optional_current_user),
    _member=Depends(require_workspace_write_access),
    _verified=Depends(require_verified_email),
) -> StrategyReviewCommentRead:
    rid = _parse_uuid(review_id)
    review = db.query(StrategyReview).filter(StrategyReview.id == str(rid)).first()
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    try:
        comment = svc.add_review_comment(
            db, rid, _actor_id(current), payload.comment
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    db.refresh(comment)
    return StrategyReviewCommentRead.model_validate(comment)


@router.get(
    "/strategy-reviews/{review_id}/packet",
    response_model=ReviewPacketResponse,
)
def get_review_packet(
    review_id: str,
    format: str = Query(default="json"),
    db: Session = Depends(get_db),
) -> ReviewPacketResponse:
    rid = _parse_uuid(review_id)
    review = db.query(StrategyReview).filter(StrategyReview.id == str(rid)).first()
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    fmt = "markdown" if format == "markdown" else "json"
    try:
        packet = svc.generate_review_packet(db, rid, fmt=fmt)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ReviewPacketResponse(**packet)
