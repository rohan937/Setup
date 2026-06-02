"""M59 Experiment Registry service.

Deterministic experiment management — no AI calls.  Groups strategy runs into
named experiments, computes evidence-based variant summaries, and persists
analysis snapshots.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.experiment import (
    StrategyExperiment,
    StrategyExperimentRun,
    StrategyExperimentAnalysis,
)
from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun
from app.models.backtest_audit import BacktestAudit
from app.models.audit_timeline_event import AuditTimelineEvent
from app.core.constants import EventType

try:
    from app.services.strategy_run_history import _load_run_evidence
except ImportError:
    _load_run_evidence = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:100]


def _create_timeline_event(
    db: Session,
    strategy: Strategy,
    event_type: EventType,
    title: str,
    source_id: str,
    metadata_json: dict[str, Any] | None,
) -> None:
    """Append an AuditTimelineEvent for an experiment action."""
    # Resolve organization_id via the project relationship
    project = strategy.project
    if project is None:
        from app.models.project import Project
        project = db.query(Project).filter_by(id=strategy.project_id).first()

    organization_id = project.organization_id if project else None

    event = AuditTimelineEvent(
        organization_id=organization_id,
        project_id=strategy.project_id,
        strategy_id=strategy.id,
        event_type=str(event_type),
        title=title,
        source_type="experiment",
        source_id=source_id,
        severity="info",
        event_time=datetime.now(timezone.utc),
        metadata_json=metadata_json,
    )
    db.add(event)
    db.flush()


# ---------------------------------------------------------------------------
# Experiment CRUD
# ---------------------------------------------------------------------------

def create_strategy_experiment(
    db: Session,
    strategy_id: str,
    payload: dict[str, Any],
) -> StrategyExperiment:
    """Create a new experiment for the given strategy."""
    strategy = db.query(Strategy).filter(Strategy.id == uuid.UUID(strategy_id)).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id!r} not found")

    name = payload["name"]
    slug = payload.get("slug") or _slugify(name)

    # Check for duplicate slug within this strategy
    existing = (
        db.query(StrategyExperiment)
        .filter(
            StrategyExperiment.strategy_id == strategy.id,
            StrategyExperiment.slug == slug,
        )
        .first()
    )
    if existing is not None:
        raise ValueError(f"slug already exists: {slug!r}")

    now = datetime.now(timezone.utc)
    experiment = StrategyExperiment(
        strategy_id=strategy.id,
        name=name,
        slug=slug,
        description=payload.get("description"),
        experiment_type=payload.get("experiment_type"),
        hypothesis=payload.get("hypothesis"),
        status="active",
        metadata_json=payload.get("metadata_json"),
        created_at=now,
        updated_at=now,
    )
    db.add(experiment)
    db.flush()

    _create_timeline_event(
        db,
        strategy,
        EventType.strategy_experiment_created,
        "Strategy experiment created",
        str(experiment.id),
        {"experiment_name": experiment.name},
    )

    return experiment


def get_strategy_experiments(
    db: Session,
    strategy_id: str,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[StrategyExperiment]:
    """List experiments for a strategy, optionally filtered by status."""
    q = (
        db.query(StrategyExperiment)
        .filter(StrategyExperiment.strategy_id == uuid.UUID(strategy_id))
    )
    if status is not None:
        q = q.filter(StrategyExperiment.status == status)
    return (
        q.order_by(StrategyExperiment.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )


def get_strategy_experiment(
    db: Session,
    experiment_id: str,
) -> StrategyExperiment | None:
    """Load a single experiment with its runs eagerly loaded."""
    from sqlalchemy.orm import joinedload

    return (
        db.query(StrategyExperiment)
        .options(joinedload(StrategyExperiment.experiment_runs))
        .filter(StrategyExperiment.id == uuid.UUID(experiment_id))
        .first()
    )


# ---------------------------------------------------------------------------
# Run membership
# ---------------------------------------------------------------------------

def add_run_to_experiment(
    db: Session,
    experiment_id: str,
    run_id: str,
    variant_label: str | None = None,
    variant_key: str | None = None,
    variant_params_json: dict | None = None,
    notes: str | None = None,
) -> StrategyExperimentRun:
    """Add a strategy run to an experiment as a variant."""
    experiment = (
        db.query(StrategyExperiment)
        .filter(StrategyExperiment.id == uuid.UUID(experiment_id))
        .first()
    )
    if experiment is None:
        raise ValueError(f"Experiment {experiment_id!r} not found")

    run = (
        db.query(StrategyRun)
        .filter(StrategyRun.id == uuid.UUID(run_id))
        .first()
    )
    if run is None:
        raise ValueError(f"StrategyRun {run_id!r} not found")

    if str(run.strategy_id) != str(experiment.strategy_id):
        raise ValueError(
            f"Run {run_id!r} belongs to a different strategy than experiment {experiment_id!r}"
        )

    # Check duplicate
    existing = (
        db.query(StrategyExperimentRun)
        .filter(
            StrategyExperimentRun.experiment_id == experiment.id,
            StrategyExperimentRun.strategy_run_id == run.id,
        )
        .first()
    )
    if existing is not None:
        raise ValueError("run already in experiment")

    if variant_params_json is None and run.params_json:
        variant_params_json = run.params_json

    exp_run = StrategyExperimentRun(
        experiment_id=experiment.id,
        strategy_run_id=run.id,
        variant_label=variant_label,
        variant_key=variant_key,
        variant_params_json=variant_params_json,
        notes=notes,
        created_at=datetime.now(timezone.utc),
    )
    db.add(exp_run)
    db.flush()

    # Timeline event
    strategy = db.query(Strategy).filter(Strategy.id == experiment.strategy_id).first()
    if strategy is not None:
        _create_timeline_event(
            db,
            strategy,
            EventType.strategy_experiment_run_added,
            "Run added to experiment",
            str(experiment.id),
            {"run_id": str(run_id), "variant_label": variant_label},
        )

    return exp_run


def remove_run_from_experiment(
    db: Session,
    experiment_id: str,
    run_id: str,
) -> bool:
    """Remove a run from an experiment. Returns True if removed, False if not found."""
    exp_run = (
        db.query(StrategyExperimentRun)
        .filter(
            StrategyExperimentRun.experiment_id == uuid.UUID(experiment_id),
            StrategyExperimentRun.strategy_run_id == uuid.UUID(run_id),
        )
        .first()
    )
    if exp_run is None:
        return False
    db.delete(exp_run)
    db.flush()
    return True


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _f(d: dict | None, k: str) -> float | None:
    if not d:
        return None
    v = d.get(k)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def analyze_strategy_experiment(
    db: Session,
    experiment_id: str,
) -> StrategyExperimentAnalysis:
    """Compute a deterministic analysis of all variants in an experiment."""
    from sqlalchemy.orm import joinedload

    experiment = (
        db.query(StrategyExperiment)
        .options(joinedload(StrategyExperiment.experiment_runs))
        .filter(StrategyExperiment.id == uuid.UUID(experiment_id))
        .first()
    )
    if experiment is None:
        raise ValueError(f"Experiment {experiment_id!r} not found")

    exp_runs = list(experiment.experiment_runs)

    if len(exp_runs) < 2:
        analysis = StrategyExperimentAnalysis(
            experiment_id=experiment.id,
            analysis_label=None,
            overall_status="insufficient_evidence",
            variant_count=len(exp_runs),
            run_count=len(exp_runs),
            best_evidenced_run_id=None,
            weakest_evidence_run_id=None,
            result_json={"variant_summaries": [], "metric_comparison": [], "rankings": {}, "review_variant_count": 0},
            deterministic_summary=(
                f"Experiment has {len(exp_runs)} variant(s). "
                "At least 2 runs are required for comparison analysis."
            ),
            created_at=datetime.now(timezone.utc),
        )
        db.add(analysis)
        db.flush()
        return analysis

    # --- Per-variant evidence collection ---
    _METRIC_KEYS = [
        "sharpe", "annual_return", "max_drawdown", "volatility",
        "turnover", "hit_rate", "trade_count",
    ]

    variant_summaries: list[dict] = []
    metric_rows: dict[str, list[tuple[str, float]]] = {k: [] for k in _METRIC_KEYS}

    for exp_run in exp_runs:
        run = db.query(StrategyRun).filter(StrategyRun.id == exp_run.strategy_run_id).first()
        if run is None:
            continue

        run_id_str = str(run.id)

        # Try loading structured evidence
        dataset_health: float | None = None
        signal_quality: float | None = None
        trust_score: float | None = None
        has_dataset = False
        has_signal = False
        has_audit = False

        if _load_run_evidence is not None:
            try:
                item = _load_run_evidence(run, db)
                if item.dataset_evidence is not None:
                    dataset_health = float(item.dataset_evidence.health_score)
                    has_dataset = True
                if item.signal_evidence is not None:
                    signal_quality = float(item.signal_evidence.quality_score)
                    has_signal = True
                if item.backtest_audit is not None:
                    trust_score = float(item.backtest_audit.trust_score)
                    has_audit = True
            except Exception:
                pass

        # Fallback: query BacktestAudit directly
        if trust_score is None:
            audit = (
                db.query(BacktestAudit)
                .filter(BacktestAudit.strategy_run_id == run.id)
                .order_by(BacktestAudit.created_at.desc())
                .first()
            )
            if audit is not None:
                trust_score = float(audit.trust_score)
                has_audit = True

        # Evidence score
        evidence_score = 40
        if has_dataset:
            evidence_score += 15
        if has_signal:
            evidence_score += 15
        if has_audit:
            evidence_score += 20
        if dataset_health is not None and dataset_health >= 75:
            evidence_score += 10

        # Variant status
        if evidence_score >= 80:
            variant_status = "strong_evidence"
        elif evidence_score >= 60:
            variant_status = "usable"
        elif evidence_score >= 40:
            variant_status = "review"
        elif evidence_score >= 20:
            variant_status = "weak"
        else:
            variant_status = "insufficient_evidence"

        # Review reasons
        review_reasons: list[str] = []
        if not has_dataset:
            review_reasons.append("missing dataset evidence")
        if not has_signal:
            review_reasons.append("missing signal evidence")
        if not has_audit:
            review_reasons.append("missing backtest audit")
        if trust_score is not None and trust_score < 60:
            review_reasons.append(f"low audit trust score ({trust_score:.0f})")
        if dataset_health is not None and dataset_health < 60:
            review_reasons.append(f"low dataset health ({dataset_health:.0f})")

        # Metrics
        metrics = {k: _f(run.metrics_json, k) for k in _METRIC_KEYS}
        for k, v in metrics.items():
            if v is not None:
                metric_rows[k].append((run_id_str, v))

        variant_summaries.append({
            "experiment_run_id": str(exp_run.id),
            "run_id": run_id_str,
            "run_name": run.run_name,
            "run_type": run.run_type,
            "variant_label": exp_run.variant_label,
            "variant_key": exp_run.variant_key,
            "variant_params_json": exp_run.variant_params_json,
            "evidence_score": evidence_score,
            "trust_score": trust_score,
            "dataset_health": dataset_health,
            "signal_quality": signal_quality,
            "variant_status": variant_status,
            "review_reasons": review_reasons,
            "metrics": metrics,
        })

    # --- Metric comparison ---
    metric_comparison: list[dict] = []
    for k in _METRIC_KEYS:
        rows = metric_rows[k]
        if not rows:
            metric_comparison.append({
                "metric_key": k,
                "available_count": 0,
                "min_value": None,
                "max_value": None,
                "mean_value": None,
                "spread": None,
                "values_by_run_id": {},
            })
            continue
        vals = [v for _, v in rows]
        mn = min(vals)
        mx = max(vals)
        mean = sum(vals) / len(vals)
        spread = mx - mn
        metric_comparison.append({
            "metric_key": k,
            "available_count": len(rows),
            "min_value": mn,
            "max_value": mx,
            "mean_value": mean,
            "spread": spread,
            "values_by_run_id": {rid: v for rid, v in rows},
        })

    # --- Rankings ---
    evidence_ranking = sorted(
        variant_summaries, key=lambda s: s["evidence_score"], reverse=True
    )
    trust_ranking = sorted(
        variant_summaries,
        key=lambda s: (s["trust_score"] is not None, s["trust_score"] or 0),
        reverse=True,
    )

    evidence_rank_items = [
        {
            "rank": i + 1,
            "run_id": s["run_id"],
            "variant_label": s["variant_label"],
            "score": s["evidence_score"],
            "reason": "evidence completeness",
        }
        for i, s in enumerate(evidence_ranking)
    ]
    trust_rank_items = [
        {
            "rank": i + 1,
            "run_id": s["run_id"],
            "variant_label": s["variant_label"],
            "score": s["trust_score"],
            "reason": "backtest trust score",
        }
        for i, s in enumerate(trust_ranking)
    ]

    best_evidenced_run_id = evidence_ranking[0]["run_id"] if evidence_ranking else None
    weakest_evidence_run_id = evidence_ranking[-1]["run_id"] if evidence_ranking else None
    best_evidence_score = evidence_ranking[0]["evidence_score"] if evidence_ranking else 0
    best_label = evidence_ranking[0]["variant_label"] if evidence_ranking else None

    review_statuses = {"review", "weak", "insufficient_evidence"}
    review_variant_count = sum(
        1 for s in variant_summaries if s["variant_status"] in review_statuses
    )
    n = len(variant_summaries)
    complete_count = sum(1 for s in variant_summaries if s["variant_status"] not in review_statuses)

    if n < 2:
        overall_status = "insufficient_evidence"
    elif review_variant_count > n / 2:
        overall_status = "sparse"
    elif review_variant_count > 0:
        overall_status = "review"
    else:
        overall_status = "complete"

    # Deterministic summary
    deterministic_summary = (
        f"Experiment has {n} variants. "
        f"{complete_count} have complete evidence. "
        f"Best-evidenced variant: {best_label!r} (evidence score: {best_evidence_score}). "
        f"{review_variant_count} variant(s) require review."
    )

    result_json: dict[str, Any] = {
        "variant_summaries": variant_summaries,
        "metric_comparison": metric_comparison,
        "rankings": {
            "by_evidence_completeness": evidence_rank_items,
            "by_backtest_trust": trust_rank_items,
        },
        "review_variant_count": review_variant_count,
    }

    analysis = StrategyExperimentAnalysis(
        experiment_id=experiment.id,
        analysis_label=None,
        overall_status=overall_status,
        variant_count=n,
        run_count=n,
        best_evidenced_run_id=best_evidenced_run_id,
        weakest_evidence_run_id=weakest_evidence_run_id,
        result_json=result_json,
        deterministic_summary=deterministic_summary,
        created_at=datetime.now(timezone.utc),
    )
    db.add(analysis)
    db.flush()

    strategy = db.query(Strategy).filter(Strategy.id == experiment.strategy_id).first()
    if strategy is not None:
        _create_timeline_event(
            db,
            strategy,
            EventType.strategy_experiment_analyzed,
            "Experiment analysis completed",
            str(experiment.id),
            {
                "analysis_id": str(analysis.id),
                "overall_status": overall_status,
                "variant_count": n,
            },
        )

    return analysis


def get_experiment_analyses(
    db: Session,
    experiment_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[StrategyExperimentAnalysis]:
    """List analyses for an experiment, newest first."""
    return (
        db.query(StrategyExperimentAnalysis)
        .filter(StrategyExperimentAnalysis.experiment_id == uuid.UUID(experiment_id))
        .order_by(StrategyExperimentAnalysis.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )


def get_experiment_analysis(
    db: Session,
    analysis_id: str,
) -> StrategyExperimentAnalysis | None:
    """Load a single analysis by ID."""
    return (
        db.query(StrategyExperimentAnalysis)
        .filter(StrategyExperimentAnalysis.id == uuid.UUID(analysis_id))
        .first()
    )
