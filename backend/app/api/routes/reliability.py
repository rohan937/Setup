"""Global reliability scores endpoint (M18).

GET /api/reliability-scores — list all computed reliability scores with filters.
"""

from __future__ import annotations

import uuid as _uuid_module

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.schemas.strategy import (
    StrategyReliabilityScoreListResponse,
    StrategyReliabilityScoreRead,
)

router = APIRouter(tags=["reliability"])


@router.get("/reliability-scores", response_model=StrategyReliabilityScoreListResponse)
def list_reliability_scores(
    status: str | None = Query(default=None, description="Filter by status"),
    strategy_id: str | None = Query(default=None, description="Filter by strategy_id"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> StrategyReliabilityScoreListResponse:
    """List reliability scores, newest-first.

    Optionally filter by ``status`` (excellent/good/review/weak/insufficient_evidence)
    and/or ``strategy_id``.
    """
    q = db.query(StrategyReliabilityScore)

    if status is not None:
        q = q.filter(StrategyReliabilityScore.status == status)
    if strategy_id is not None:
        try:
            sid_uuid = _uuid_module.UUID(strategy_id)
        except ValueError:
            # Invalid UUID → return empty result
            return StrategyReliabilityScoreListResponse(total=0, items=[])
        q = q.filter(StrategyReliabilityScore.strategy_id == sid_uuid)

    total: int = q.count()
    items = (
        q.order_by(StrategyReliabilityScore.generated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return StrategyReliabilityScoreListResponse(
        total=total,
        items=[StrategyReliabilityScoreRead.model_validate(s) for s in items],
    )
