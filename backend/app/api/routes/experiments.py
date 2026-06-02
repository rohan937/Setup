"""M59 Experiment Registry API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import experiments as svc
from app.services.parameter_sweep import analyze_parameter_sweep
from app.schemas.experiment import (
    StrategyExperimentCreate,
    StrategyExperimentRead,
    StrategyExperimentDetail,
    StrategyExperimentRunRead,
    ExperimentRunAddRequest,
    StrategyExperimentAnalysisRead,
    StrategyExperimentAnalysisListResponse,
)
from app.schemas.parameter_sweep import (
    ParameterSweepAnalysisRequest,
    ParameterSweepAnalysisResponse,
    DetectedParameter,
    ParameterSweepVariant,
    ParameterSweepMetricComparison,
    ParameterSweepRegion,
    ParameterSweepFragilitySignals,
    ParameterSweepRankingItem,
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


@router.post(
    "/experiments/{experiment_id}/sweep-analysis",
    response_model=ParameterSweepAnalysisResponse,
)
def sweep_analysis(
    experiment_id: str,
    body: ParameterSweepAnalysisRequest,
    db: Session = Depends(get_db),
) -> ParameterSweepAnalysisResponse:
    """Run a deterministic parameter sweep reliability analysis for an experiment."""
    _parse_uuid(experiment_id)

    try:
        result = analyze_parameter_sweep(
            db,
            experiment_id,
            parameter_key=body.parameter_key,
            analysis_label=body.analysis_label,
            persist=body.persist,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    if body.persist:
        db.commit()

    fragility = result.fragility_signals
    fragility_schema = ParameterSweepFragilitySignals(
        fragile_variant_count=fragility.fragile_variant_count,
        review_variant_count=fragility.review_variant_count,
        under_instrumented_variant_count=fragility.under_instrumented_variant_count,
        narrow_peak_detected=fragility.narrow_peak_detected,
        evidence_degradation_detected=fragility.evidence_degradation_detected,
        trust_degradation_detected=fragility.trust_degradation_detected,
        metric_instability_detected=fragility.metric_instability_detected,
    ) if fragility is not None else ParameterSweepFragilitySignals(
        fragile_variant_count=0,
        review_variant_count=0,
        under_instrumented_variant_count=0,
        narrow_peak_detected=False,
        evidence_degradation_detected=False,
        trust_degradation_detected=False,
        metric_instability_detected=False,
    )

    return ParameterSweepAnalysisResponse(
        experiment_id=result.experiment_id,
        strategy_id=result.strategy_id,
        parameter_key=result.parameter_key,
        generated_at=result.generated_at,
        sweep_status=result.sweep_status,
        sweep_reliability_score=result.sweep_reliability_score,
        detected_parameters=[
            DetectedParameter(
                parameter_key=d.parameter_key,
                value_count=d.value_count,
                numeric=d.numeric,
                unique_values=d.unique_values,
                coverage_rate=d.coverage_rate,
                examples=d.examples,
            )
            for d in result.detected_parameters
        ],
        variant_summaries=[
            ParameterSweepVariant(
                experiment_run_id=v.experiment_run_id,
                run_id=v.run_id,
                run_name=v.run_name,
                run_type=v.run_type,
                variant_label=v.variant_label,
                parameter_key=v.parameter_key,
                parameter_value=v.parameter_value,
                parameter_value_numeric=v.parameter_value_numeric,
                sharpe=v.sharpe,
                annual_return=v.annual_return,
                max_drawdown=v.max_drawdown,
                volatility=v.volatility,
                turnover=v.turnover,
                hit_rate=v.hit_rate,
                trade_count=v.trade_count,
                dataset_health=v.dataset_health,
                signal_quality=v.signal_quality,
                backtest_trust=v.backtest_trust,
                evidence_score=v.evidence_score,
                variant_status=v.variant_status,
                review_reasons=v.review_reasons,
                suggested_checks=v.suggested_checks,
            )
            for v in result.variant_summaries
        ],
        metric_comparisons=[
            ParameterSweepMetricComparison(
                metric_key=mc["metric_key"],
                available_count=mc["available_count"],
                min_value=mc["min_value"],
                max_value=mc["max_value"],
                mean_value=mc["mean_value"],
                range_value=mc["range_value"],
                values_by_run_id=mc["values_by_run_id"],
            )
            for mc in result.metric_comparisons
        ],
        regions=[
            ParameterSweepRegion(
                region_key=r.region_key,
                label=r.label,
                parameter_min=r.parameter_min,
                parameter_max=r.parameter_max,
                variant_count=r.variant_count,
                run_ids=r.run_ids,
                status=r.status,
                evidence_score_avg=r.evidence_score_avg,
                backtest_trust_avg=r.backtest_trust_avg,
                metric_stability_score=r.metric_stability_score,
                reason=r.reason,
                suggested_check=r.suggested_check,
            )
            for r in result.regions
        ],
        fragility_signals=fragility_schema,
        rankings=[
            ParameterSweepRankingItem(
                rank=r.rank,
                run_id=r.run_id,
                variant_label=r.variant_label,
                parameter_value=r.parameter_value,
                score=r.score,
                reason=r.reason,
            )
            for r in result.rankings
        ],
        suggested_checks=result.suggested_checks,
        deterministic_summary=result.deterministic_summary,
        analysis_id=result.analysis_id,
    )


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
