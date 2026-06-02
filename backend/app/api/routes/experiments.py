"""M59 Experiment Registry API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import experiments as svc
from app.schemas.experiment import (
    StrategyExperimentCreate,
    StrategyExperimentRead,
    StrategyExperimentDetail,
    StrategyExperimentRunRead,
    ExperimentRunAddRequest,
    StrategyExperimentAnalysisRead,
    StrategyExperimentAnalysisListResponse,
)
from app.models.strategy import Strategy
from app.models.experiment import StrategyExperiment

router = APIRouter()


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Not found")


# ---------------------------------------------------------------------------
# Strategy-scoped endpoints  (literal paths before parameterized paths)
# ---------------------------------------------------------------------------

@router.post(
    "/strategies/{strategy_id}/experiments",
    response_model=StrategyExperimentRead,
    status_code=201,
)
def create_experiment(
    strategy_id: str,
    body: StrategyExperimentCreate,
    db: Session = Depends(get_db),
) -> StrategyExperimentRead:
    """Create a new experiment for a strategy."""
    _parse_uuid(strategy_id)
    strategy = db.query(Strategy).filter(Strategy.id == uuid.UUID(strategy_id)).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    try:
        experiment = svc.create_strategy_experiment(db, strategy_id, body.model_dump())
    except ValueError as exc:
        msg = str(exc)
        if "slug already exists" in msg:
            raise HTTPException(status_code=409, detail=msg)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    db.commit()
    db.refresh(experiment)

    schema = StrategyExperimentRead.model_validate(experiment)
    schema.run_count = len(experiment.experiment_runs) if experiment.experiment_runs else 0
    return schema


@router.get(
    "/strategies/{strategy_id}/experiments",
    response_model=list[StrategyExperimentRead],
)
def list_experiments(
    strategy_id: str,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[StrategyExperimentRead]:
    """List experiments for a strategy."""
    _parse_uuid(strategy_id)
    strategy = db.query(Strategy).filter(Strategy.id == uuid.UUID(strategy_id)).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    experiments = svc.get_strategy_experiments(db, strategy_id, status=status, limit=limit, offset=offset)
    result = []
    for exp in experiments:
        s = StrategyExperimentRead.model_validate(exp)
        s.run_count = len(exp.experiment_runs) if exp.experiment_runs else 0
        result.append(s)
    return result


# ---------------------------------------------------------------------------
# Experiment-scoped endpoints  (GET detail first, then action/sub-resource)
# ---------------------------------------------------------------------------

@router.get(
    "/experiments/{experiment_id}",
    response_model=StrategyExperimentDetail,
)
def get_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
) -> StrategyExperimentDetail:
    """Get experiment detail including all runs."""
    _parse_uuid(experiment_id)
    experiment = svc.get_strategy_experiment(db, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    detail = StrategyExperimentDetail.model_validate(experiment)
    detail.run_count = len(experiment.experiment_runs)
    detail.experiment_runs = [
        StrategyExperimentRunRead.model_validate(r) for r in experiment.experiment_runs
    ]
    return detail


@router.post(
    "/experiments/{experiment_id}/runs",
    response_model=StrategyExperimentRunRead,
    status_code=201,
)
def add_run(
    experiment_id: str,
    body: ExperimentRunAddRequest,
    db: Session = Depends(get_db),
) -> StrategyExperimentRunRead:
    """Add a strategy run to an experiment as a variant."""
    _parse_uuid(experiment_id)

    try:
        exp_run = svc.add_run_to_experiment(
            db,
            experiment_id,
            body.strategy_run_id,
            variant_label=body.variant_label,
            variant_key=body.variant_key,
            variant_params_json=body.variant_params_json,
            notes=body.notes,
        )
    except ValueError as exc:
        msg = str(exc)
        if "run already in experiment" in msg:
            raise HTTPException(status_code=409, detail=msg)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        if "different strategy" in msg.lower():
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    db.commit()
    db.refresh(exp_run)
    return StrategyExperimentRunRead.model_validate(exp_run)


@router.delete(
    "/experiments/{experiment_id}/runs/{run_id}",
    status_code=204,
    response_class=Response,
)
def remove_run(
    experiment_id: str,
    run_id: str,
    db: Session = Depends(get_db),
) -> Response:
    """Remove a strategy run from an experiment."""
    _parse_uuid(experiment_id)
    _parse_uuid(run_id)

    removed = svc.remove_run_from_experiment(db, experiment_id, run_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Run not found in experiment")
    db.commit()
    return Response(status_code=204)


@router.post(
    "/experiments/{experiment_id}/analyze",
    response_model=StrategyExperimentAnalysisRead,
)
def analyze_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
) -> StrategyExperimentAnalysisRead:
    """Run a deterministic analysis of an experiment's variants."""
    _parse_uuid(experiment_id)

    try:
        analysis = svc.analyze_strategy_experiment(db, experiment_id)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    db.commit()
    db.refresh(analysis)
    return StrategyExperimentAnalysisRead.model_validate(analysis)


@router.get(
    "/experiments/{experiment_id}/analyses",
    response_model=StrategyExperimentAnalysisListResponse,
)
def list_analyses(
    experiment_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> StrategyExperimentAnalysisListResponse:
    """List analyses for an experiment, newest first."""
    _parse_uuid(experiment_id)

    experiment = db.query(StrategyExperiment).filter(
        StrategyExperiment.id == uuid.UUID(experiment_id)
    ).first()
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    analyses = svc.get_experiment_analyses(db, experiment_id, limit=limit, offset=offset)
    total = len(analyses)
    return StrategyExperimentAnalysisListResponse(
        items=[StrategyExperimentAnalysisRead.model_validate(a) for a in analyses],
        total=total,
    )


# ---------------------------------------------------------------------------
# Analysis detail (standalone resource)
# ---------------------------------------------------------------------------

@router.get(
    "/experiment-analyses/{analysis_id}",
    response_model=StrategyExperimentAnalysisRead,
)
def get_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
) -> StrategyExperimentAnalysisRead:
    """Get a single experiment analysis by ID."""
    _parse_uuid(analysis_id)
    analysis = svc.get_experiment_analysis(db, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return StrategyExperimentAnalysisRead.model_validate(analysis)
