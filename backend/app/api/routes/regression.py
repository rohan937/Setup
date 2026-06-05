"""Regression test endpoints (M53).

POST /api/strategies/{strategy_id}/regression-tests/defaults  — create/reuse default tests
GET  /api/strategies/{strategy_id}/regression-tests           — list tests
POST /api/strategies/{strategy_id}/regression-tests/run       — run tests
GET  /api/strategies/{strategy_id}/regression-tests/runs      — list recent runs
GET  /api/regression-test-runs/{test_run_id}                  — get run detail

Deterministic — no AI, no live market data, no external calls.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.strategy import Strategy
from app.schemas.regression import (
    StrategyRegressionTestRead,
    StrategyRegressionTestRunListResponse,
    StrategyRegressionTestRunRead,
    StrategyRegressionTestRunRequest,
)
from app.services.regression_tests import (
    create_default_regression_tests,
    get_regression_test_run,
    get_regression_test_runs,
    get_regression_tests,
    run_regression_tests,
)

router = APIRouter(tags=["regression"])

VALID_MODES = {"latest_vs_previous", "selected_runs", "latest_backtest_vs_latest_shadow"}


def _get_strategy_or_404(strategy_id: uuid.UUID, db: Session) -> Strategy:
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    return strategy


@router.post(
    "/strategies/{strategy_id}/regression-tests/defaults",
    response_model=list[StrategyRegressionTestRead],
    summary="Create default regression tests for a strategy (idempotent)",
)
def create_defaults(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[StrategyRegressionTestRead]:
    _get_strategy_or_404(strategy_id, db)
    tests = create_default_regression_tests(strategy_id, db)
    db.commit()   # persist — was missing; without this the flush was rolled back on session close
    return [StrategyRegressionTestRead.model_validate(t) for t in tests]


@router.get(
    "/strategies/{strategy_id}/regression-tests",
    response_model=list[StrategyRegressionTestRead],
    summary="List regression tests for a strategy",
)
def list_tests(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[StrategyRegressionTestRead]:
    _get_strategy_or_404(strategy_id, db)
    tests = get_regression_tests(strategy_id, db)
    return [StrategyRegressionTestRead.model_validate(t) for t in tests]


@router.post(
    "/strategies/{strategy_id}/regression-tests/run",
    response_model=StrategyRegressionTestRunRead,
    summary="Run regression tests for a strategy",
)
def run_tests(
    strategy_id: uuid.UUID,
    request: StrategyRegressionTestRunRequest,
    db: Session = Depends(get_db),
) -> StrategyRegressionTestRunRead:
    _get_strategy_or_404(strategy_id, db)

    if request.mode not in VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid mode '{request.mode}'. "
                f"Valid modes: {sorted(VALID_MODES)}"
            ),
        )

    if request.mode == "selected_runs":
        if request.baseline_run_id is None or request.comparison_run_id is None:
            raise HTTPException(
                status_code=400,
                detail="baseline_run_id and comparison_run_id are required for selected_runs mode",
            )

    test_run = run_regression_tests(
        strategy_id=strategy_id,
        db=db,
        mode=request.mode,
        baseline_run_id=request.baseline_run_id,
        comparison_run_id=request.comparison_run_id,
        suite_label=request.suite_label,
    )
    # Eagerly load results for response
    _ = test_run.results
    return StrategyRegressionTestRunRead.model_validate(test_run)


@router.get(
    "/strategies/{strategy_id}/regression-tests/runs",
    response_model=StrategyRegressionTestRunListResponse,
    summary="List recent regression test runs for a strategy",
)
def list_runs(
    strategy_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> StrategyRegressionTestRunListResponse:
    _get_strategy_or_404(strategy_id, db)
    runs = get_regression_test_runs(strategy_id, db, limit=limit, offset=offset)
    from app.models.regression import StrategyRegressionTestRun

    total = (
        db.query(StrategyRegressionTestRun)
        .filter(StrategyRegressionTestRun.strategy_id == strategy_id)
        .count()
    )
    return StrategyRegressionTestRunListResponse(
        items=[StrategyRegressionTestRunRead.model_validate(r) for r in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/regression-test-runs/{test_run_id}",
    response_model=StrategyRegressionTestRunRead,
    summary="Get a regression test run with full results",
)
def get_run_detail(
    test_run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> StrategyRegressionTestRunRead:
    run = get_regression_test_run(test_run_id, db)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail=f"Regression test run {test_run_id} not found",
        )
    return StrategyRegressionTestRunRead.model_validate(run)
