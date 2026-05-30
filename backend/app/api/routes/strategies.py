"""Strategy endpoints:
  GET /api/strategies
  GET /api/strategies/{strategy_id}
  GET /api/strategies/{strategy_id}/runs
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun
from app.schemas.strategy import StrategyDetailOut, StrategyOut, StrategyRunOut

router = APIRouter(tags=["strategies"])


@router.get("/strategies", response_model=list[StrategyOut])
def list_strategies(db: Session = Depends(get_db)) -> list[Strategy]:
    return db.query(Strategy).order_by(Strategy.created_at).all()


@router.get("/strategies/{strategy_id}", response_model=StrategyDetailOut)
def get_strategy(
    strategy_id: uuid.UUID, db: Session = Depends(get_db)
) -> Strategy:
    strategy = (
        db.query(Strategy)
        .options(selectinload(Strategy.versions))
        .filter(Strategy.id == strategy_id)
        .first()
    )
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


@router.get("/strategies/{strategy_id}/runs", response_model=list[StrategyRunOut])
def list_strategy_runs(
    strategy_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[StrategyRun]:
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(StrategyRun.created_at)
        .all()
    )
