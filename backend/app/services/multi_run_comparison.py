"""Multi-run cross-strategy comparison service (M34).

Compares the latest (or selected) run from 2–4 strategies side-by-side.
Deterministic — no AI, no causal claims, no investment advice.

Language policy:
  Use: "higher logged score", "more complete instrumentation",
       "logged higher", "noted as observed"
  Never: "better strategy", "more profitable", "should trade",
          "buy/sell", "alpha is stronger", "investment recommendation"
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KNOWN_METRICS: list[str] = [
    "sharpe",
    "sortino",
    "annual_return",
    "volatility",
    "max_drawdown",
    "turnover",
    "hit_rate",
    "trade_count",
    "alpha_bps",
    "transaction_cost_bps",
    "slippage_bps",
]

KNOWN_ASSUMPTIONS: list[str] = [
    "transaction_cost_bps",
    "slippage_bps",
    "fill_model",
    "borrow_cost_bps",
    "short_enabled",
    "execution_timing",
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RunMetricsData:
    sharpe: float | None
    sortino: float | None
    annual_return: float | None
    volatility: float | None
    max_drawdown: float | None
    turnover: float | None
    hit_rate: float | None
    trade_count: float | None
    alpha_bps: float | None
    transaction_cost_bps: float | None
    slippage_bps: float | None


@dataclass
class RunAssumptionsData:
    transaction_cost_bps: float | None
    slippage_bps: float | None
    fill_model: str | None
    borrow_cost_bps: float | None
    short_enabled: bool | None
    execution_timing: str | None


@dataclass
class RunEvidenceSummaryData:
    dataset_health_score: float | None
    dataset_issue_count: int
    dataset_label: str | None
    signal_quality_score: float | None
    signal_missing_count: int
    signal_label: str | None
    universe_symbol_count: int | None
    universe_label: str | None
    backtest_trust_score: float | None
    backtest_status: str | None
    backtest_issue_count: int
    cost_fragility_level: str | None
    fill_realism_level: str | None
    run_health_label: str


@dataclass
class MultiRunItemData:
    strategy_id: uuid.UUID
    strategy_name: str
    asset_class: str
    status: str
    run_id: uuid.UUID
    run_name: str
    run_type: str
    run_status: str
    completed_at: datetime | None
    created_at: datetime
    strategy_version_label: str | None
    open_alert_count: int
    reliability_score: float | None
    reliability_status: str | None
    evidence_coverage_score: float | None
    metrics: RunMetricsData
    assumptions: RunAssumptionsData
    evidence: RunEvidenceSummaryData


@dataclass
class MultiRunRankingItemData:
    rank: int
    strategy_id: uuid.UUID
    strategy_name: str
    value: float | None
    value_label: str
    run_name: str


@dataclass
class MultiRunComparisonResult:
    compared_at: datetime
    mode: str
    items: list[MultiRunItemData]
    metric_matrix: dict
    assumption_matrix: dict
    evidence_matrix: dict
    rankings: dict
    gaps: dict
    shared_gaps: list[str]
    highlighted_differences: list[str]
    deterministic_explanation: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_metrics(metrics_json: dict | None) -> RunMetricsData:
    d = metrics_json or {}

    def _f(k: str) -> float | None:
        v = d.get(k)
        return float(v) if v is not None else None

    return RunMetricsData(
        sharpe=_f("sharpe"),
        sortino=_f("sortino"),
        annual_return=_f("annual_return"),
        volatility=_f("volatility"),
        max_drawdown=_f("max_drawdown"),
        turnover=_f("turnover"),
        hit_rate=_f("hit_rate"),
        trade_count=_f("trade_count"),
        alpha_bps=_f("alpha_bps"),
        transaction_cost_bps=_f("transaction_cost_bps"),
        slippage_bps=_f("slippage_bps"),
    )


def _extract_assumptions(assumptions_json: dict | None) -> RunAssumptionsData:
    d = assumptions_json or {}

    def _f(k: str) -> float | None:
        v = d.get(k)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    # Booleans and strings extracted separately
    short_enabled = d.get("short_enabled")
    if isinstance(short_enabled, bool):
        se: bool | None = short_enabled
    elif short_enabled in (0, 1):
        se = bool(short_enabled)
    else:
        se = None

    fill_model = d.get("fill_model")
    execution_timing = d.get("execution_timing")

    return RunAssumptionsData(
        transaction_cost_bps=_f("transaction_cost_bps"),
        slippage_bps=_f("slippage_bps"),
        fill_model=str(fill_model) if fill_model is not None else None,
        borrow_cost_bps=_f("borrow_cost_bps"),
        short_enabled=se,
        execution_timing=str(execution_timing) if execution_timing is not None else None,
    )


def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _load_run_item(strategy, run, db: Session) -> MultiRunItemData:  # type: ignore[type-arg]
    """Build a MultiRunItemData by loading evidence for the given run."""
    from app.models.alert import Alert
    from app.models.strategy_reliability_score import StrategyReliabilityScore
    from app.services.evidence_coverage import _compute_row
    from app.services.strategy_run_history import _load_run_evidence

    history_item = _load_run_evidence(run, db)

    evidence = RunEvidenceSummaryData(
        dataset_health_score=(
            float(history_item.dataset_evidence.health_score)
            if history_item.dataset_evidence
            else None
        ),
        dataset_issue_count=(
            history_item.dataset_evidence.issue_count if history_item.dataset_evidence else 0
        ),
        dataset_label=(
            history_item.dataset_evidence.snapshot_label
            if history_item.dataset_evidence
            else None
        ),
        signal_quality_score=(
            float(history_item.signal_evidence.quality_score)
            if history_item.signal_evidence
            else None
        ),
        signal_missing_count=(
            history_item.signal_evidence.missing_signal_count
            if history_item.signal_evidence
            else 0
        ),
        signal_label=(
            history_item.signal_evidence.label if history_item.signal_evidence else None
        ),
        universe_symbol_count=(
            history_item.universe_evidence.symbol_count
            if history_item.universe_evidence
            else None
        ),
        universe_label=(
            history_item.universe_evidence.label if history_item.universe_evidence else None
        ),
        backtest_trust_score=(
            float(history_item.backtest_audit.trust_score)
            if history_item.backtest_audit
            else None
        ),
        backtest_status=(
            history_item.backtest_audit.overall_status if history_item.backtest_audit else None
        ),
        backtest_issue_count=(
            history_item.backtest_audit.issue_count if history_item.backtest_audit else 0
        ),
        cost_fragility_level=(
            history_item.backtest_audit.cost_fragility_level
            if history_item.backtest_audit
            else None
        ),
        fill_realism_level=(
            history_item.backtest_audit.fill_realism_level
            if history_item.backtest_audit
            else None
        ),
        run_health_label=history_item.run_health_label,
    )

    version_label = (
        history_item.strategy_version.version_label
        if history_item.strategy_version
        else None
    )

    # Open alerts — Alert.strategy_id is String(36)
    open_alerts: int = (
        db.query(func.count(Alert.id))
        .filter(
            Alert.strategy_id == str(strategy.id),
            Alert.status.in_(["open", "acknowledged", "snoozed"]),
        )
        .scalar()
    ) or 0

    # Latest reliability score
    rel = (
        db.query(StrategyReliabilityScore)
        .filter(StrategyReliabilityScore.strategy_id == strategy.id)
        .order_by(StrategyReliabilityScore.generated_at.desc())
        .first()
    )

    # Evidence coverage score
    cov = _compute_row(strategy, db)

    return MultiRunItemData(
        strategy_id=strategy.id,
        strategy_name=strategy.name,
        asset_class=strategy.asset_class,
        status=strategy.status,
        run_id=run.id,
        run_name=run.run_name,
        run_type=run.run_type,
        run_status=run.status,
        completed_at=_normalize_dt(run.completed_at),
        created_at=_normalize_dt(run.created_at) or datetime.now(timezone.utc),
        strategy_version_label=version_label,
        open_alert_count=open_alerts,
        reliability_score=float(rel.overall_score) if rel and rel.overall_score is not None else None,
        reliability_status=rel.status if rel else None,
        evidence_coverage_score=cov.evidence_coverage_score,
        metrics=_extract_metrics(run.metrics_json),
        assumptions=_extract_assumptions(run.assumptions_json),
        evidence=evidence,
    )


def _build_metric_matrix(items: list[MultiRunItemData]) -> dict:
    result: dict = {}
    for key in KNOWN_METRICS:
        row: dict = {}
        for item in items:
            val = getattr(item.metrics, key, None)
            row[str(item.strategy_id)] = val
        if any(v is not None for v in row.values()):
            result[key] = row
    return result


def _build_assumption_matrix(items: list[MultiRunItemData]) -> dict:
    result: dict = {}
    for key in KNOWN_ASSUMPTIONS:
        row: dict = {}
        for item in items:
            val = getattr(item.assumptions, key, None)
            row[str(item.strategy_id)] = val
        if any(v is not None for v in row.values()):
            result[key] = row
    return result


def _build_evidence_matrix(items: list[MultiRunItemData]) -> dict:
    EVIDENCE_KEYS = {
        "dataset_health_score": lambda i: i.evidence.dataset_health_score,
        "signal_quality_score": lambda i: i.evidence.signal_quality_score,
        "universe_symbol_count": lambda i: (
            float(i.evidence.universe_symbol_count)
            if i.evidence.universe_symbol_count is not None
            else None
        ),
        "backtest_trust_score": lambda i: i.evidence.backtest_trust_score,
        "reliability_score": lambda i: i.reliability_score,
        "evidence_coverage_score": lambda i: i.evidence_coverage_score,
        "open_alert_count": lambda i: float(i.open_alert_count),
    }
    result: dict = {}
    for key, getter in EVIDENCE_KEYS.items():
        row = {str(item.strategy_id): getter(item) for item in items}
        result[key] = row
    return result


def _build_rankings(items: list[MultiRunItemData]) -> dict:
    def _rank(
        items: list[MultiRunItemData],
        getter,
        higher_is_better: bool = True,
    ) -> list[MultiRunRankingItemData]:
        scored = [(item, getter(item)) for item in items]
        # Nulls last; sort by value (desc if higher_is_better else asc), then name
        scored.sort(
            key=lambda x: (
                x[1] is None,
                -(x[1] or 0.0) if higher_is_better else (x[1] or 0.0),
                x[0].strategy_name,
            )
        )
        return [
            MultiRunRankingItemData(
                rank=i + 1,
                strategy_id=item.strategy_id,
                strategy_name=item.strategy_name,
                value=val,
                value_label=f"{val:.1f}" if val is not None else "—",
                run_name=item.run_name,
            )
            for i, (item, val) in enumerate(scored)
        ]

    return {
        "by_backtest_trust": _rank(items, lambda i: i.evidence.backtest_trust_score),
        "by_data_health": _rank(items, lambda i: i.evidence.dataset_health_score),
        "by_signal_quality": _rank(items, lambda i: i.evidence.signal_quality_score),
        "by_reliability": _rank(items, lambda i: i.reliability_score),
        "by_evidence_completeness": _rank(items, lambda i: i.evidence_coverage_score),
    }


def _build_gaps(items: list[MultiRunItemData]) -> tuple[dict, list[str]]:
    gaps: dict[str, list[str]] = {}
    for item in items:
        missing: list[str] = []
        if item.evidence.dataset_health_score is None:
            missing.append("Dataset evidence")
        if item.evidence.signal_quality_score is None:
            missing.append("Signal evidence")
        if item.evidence.universe_symbol_count is None:
            missing.append("Universe evidence")
        if item.evidence.backtest_trust_score is None:
            missing.append("Backtest audit")
        gaps[str(item.strategy_id)] = missing

    # Shared gaps: missing in ALL strategies
    if gaps:
        all_missing = [set(m) for m in gaps.values()]
        shared: list[str] = sorted(all_missing[0].intersection(*all_missing[1:]))
    else:
        shared = []
    return gaps, shared


def _build_explanation(items: list[MultiRunItemData], mode: str) -> str:
    n = len(items)
    parts: list[str] = [
        f"{n} strategy run{'s were' if n != 1 else ' was'} compared using logged "
        f"QuantFidelity evidence (mode: {mode})."
    ]
    # Highest backtest trust
    trust_items = [
        (i.evidence.backtest_trust_score, i.strategy_name)
        for i in items
        if i.evidence.backtest_trust_score is not None
    ]
    if trust_items:
        trust_items.sort(reverse=True)
        parts.append(
            f"{trust_items[0][1]} has the highest linked backtest trust score "
            f"at {trust_items[0][0]:.0f}/100."
        )
    # Under-evidenced strategies
    under_evidenced = [
        i.strategy_name
        for i in items
        if i.evidence.signal_quality_score is None and i.evidence.dataset_health_score is None
    ]
    if under_evidenced:
        verb = "has" if len(under_evidenced) == 1 else "have"
        parts.append(
            f"{', '.join(under_evidenced)} {verb} limited linked evidence."
        )
    parts.append(
        "This comparison reflects logged evidence quality and reported metrics only. "
        "No advice is implied regarding trading or portfolio allocation."
    )
    return " ".join(parts)


def _build_highlighted_diffs(
    items: list[MultiRunItemData],
    metric_matrix: dict,
) -> list[str]:
    diffs: list[str] = []
    for metric_key, row in metric_matrix.items():
        vals = [v for v in row.values() if v is not None]
        if len(vals) >= 2:
            spread = max(vals) - min(vals)
            if spread > 0:
                max_pair = max(
                    row.items(),
                    key=lambda x: x[1] if x[1] is not None else float("-inf"),
                )
                min_pair = min(
                    row.items(),
                    key=lambda x: x[1] if x[1] is not None else float("inf"),
                )
                max_name = next(
                    (i.strategy_name for i in items if str(i.strategy_id) == max_pair[0]),
                    max_pair[0],
                )
                min_name = next(
                    (i.strategy_name for i in items if str(i.strategy_id) == min_pair[0]),
                    min_pair[0],
                )
                diffs.append(
                    f"{metric_key}: {max_name} logged {max_pair[1]:.2f}, "
                    f"{min_name} logged {min_pair[1]:.2f}."
                )
    return diffs[:5]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compare_multi_strategy_runs(
    strategy_ids: list[uuid.UUID],
    db: Session,
    *,
    mode: str = "latest",
    run_ids: list[uuid.UUID] | None = None,
) -> MultiRunComparisonResult:
    """Compare the latest (or selected) run from 2–4 strategies side-by-side.

    Parameters
    ----------
    strategy_ids:
        List of 2–4 strategy UUIDs to compare. Duplicates are deduplicated
        while preserving order.
    db:
        Open SQLAlchemy session.
    mode:
        ``"latest"`` selects the most-recently-completed (or most-recently-created)
        run per strategy. ``"selected"`` uses the runs provided in *run_ids*.
    run_ids:
        Required when *mode* is ``"selected"``. One run per strategy.

    Raises
    ------
    ValueError
        When validation fails (too few/many strategies, unknown IDs, missing runs).
    """
    from app.models.strategy import Strategy
    from app.models.strategy_run import StrategyRun

    if len(strategy_ids) < 2:
        raise ValueError("At least 2 strategy IDs required.")
    if len(strategy_ids) > 4:
        raise ValueError("At most 4 strategy IDs may be compared.")

    # Deduplicate while preserving order
    seen: set[uuid.UUID] = set()
    unique_ids: list[uuid.UUID] = []
    for sid in strategy_ids:
        if sid not in seen:
            seen.add(sid)
            unique_ids.append(sid)

    strategies = {
        s.id: s
        for s in db.query(Strategy).filter(Strategy.id.in_(unique_ids)).all()
    }
    missing_strats = [str(sid) for sid in unique_ids if sid not in strategies]
    if missing_strats:
        raise ValueError(f"Strategies not found: {missing_strats}")

    # ── Select runs ──────────────────────────────────────────────────────────
    run_map: dict[uuid.UUID, StrategyRun] = {}

    if mode == "latest":
        for sid in unique_ids:
            run = (
                db.query(StrategyRun)
                .filter(StrategyRun.strategy_id == sid)
                .order_by(
                    StrategyRun.completed_at.desc().nullslast(),
                    StrategyRun.created_at.desc(),
                )
                .first()
            )
            if run is None:
                raise ValueError(
                    f"Strategy {strategies[sid].name!r} has no runs."
                )
            run_map[sid] = run

    elif mode == "selected":
        if not run_ids:
            raise ValueError("run_ids required for selected mode.")
        provided_runs = {
            r.id: r
            for r in db.query(StrategyRun).filter(StrategyRun.id.in_(run_ids)).all()
        }
        for sid in unique_ids:
            matching = [r for r in provided_runs.values() if r.strategy_id == sid]
            if not matching:
                raise ValueError(
                    f"No run provided for strategy {strategies[sid].name!r}"
                )
            run_map[sid] = matching[0]
        # Validate no run belongs to a strategy not in the list
        for run in provided_runs.values():
            if run.strategy_id not in unique_ids:
                raise ValueError(
                    f"Run {run.id} does not belong to any provided strategy."
                )

    else:
        raise ValueError(f"Invalid mode: {mode!r}. Must be 'latest' or 'selected'.")

    now = datetime.now(timezone.utc)
    items = [_load_run_item(strategies[sid], run_map[sid], db) for sid in unique_ids]
    metric_matrix = _build_metric_matrix(items)
    assumption_matrix = _build_assumption_matrix(items)
    evidence_matrix = _build_evidence_matrix(items)
    rankings = _build_rankings(items)
    gaps, shared_gaps = _build_gaps(items)
    highlighted = _build_highlighted_diffs(items, metric_matrix)
    explanation = _build_explanation(items, mode)

    return MultiRunComparisonResult(
        compared_at=now,
        mode=mode,
        items=items,
        metric_matrix=metric_matrix,
        assumption_matrix=assumption_matrix,
        evidence_matrix=evidence_matrix,
        rankings=rankings,
        gaps=gaps,
        shared_gaps=shared_gaps,
        highlighted_differences=highlighted,
        deterministic_explanation=explanation,
    )
