"""M60 Parameter Sweep Reliability Analysis service.

Deterministic sweep analysis — no AI calls.  Reads existing experiment runs,
detects the swept parameter, builds per-variant evidence summaries, detects
fragility signals, and persists a StrategyExperimentAnalysis snapshot.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
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
    from app.services.strategy_run_history import _load_run_evidence  # type: ignore[attr-defined]
except ImportError:
    _load_run_evidence = None  # type: ignore[assignment]

# Keys to skip when flattening parameter dicts — these are identity / run-metadata
# fields that are not sweep parameters.
_SKIP_KEYS = {"id", "strategy_id", "run_name", "run_type"}

_METRIC_KEYS = [
    "sharpe",
    "annual_return",
    "max_drawdown",
    "volatility",
    "turnover",
    "hit_rate",
    "trade_count",
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DetectedParameterData:
    parameter_key: str
    value_count: int
    numeric: bool
    unique_values: list = field(default_factory=list)
    coverage_rate: float = 0.0
    examples: list = field(default_factory=list)


@dataclass
class ParameterSweepVariantData:
    experiment_run_id: str
    run_id: str
    run_name: str
    run_type: str
    variant_label: str | None
    parameter_key: str | None
    parameter_value: str | None
    parameter_value_numeric: float | None
    sharpe: float | None
    annual_return: float | None
    max_drawdown: float | None
    volatility: float | None
    turnover: float | None
    hit_rate: float | None
    trade_count: int | None
    dataset_health: float | None
    signal_quality: float | None
    backtest_trust: float | None
    evidence_score: float
    run_health_label: str | None
    variant_status: str
    review_reasons: list = field(default_factory=list)
    suggested_checks: list = field(default_factory=list)


@dataclass
class ParameterSweepRegionData:
    region_key: str
    label: str
    parameter_min: float | None
    parameter_max: float | None
    variant_count: int
    run_ids: list = field(default_factory=list)
    status: str = "unknown"
    evidence_score_avg: float | None = None
    backtest_trust_avg: float | None = None
    metric_stability_score: float | None = None
    reason: str = ""
    suggested_check: str | None = None


@dataclass
class ParameterSweepFragilityData:
    fragile_variant_count: int
    review_variant_count: int
    under_instrumented_variant_count: int
    narrow_peak_detected: bool
    evidence_degradation_detected: bool
    trust_degradation_detected: bool
    metric_instability_detected: bool


@dataclass
class ParameterSweepRankingItemData:
    rank: int
    run_id: str
    variant_label: str | None
    parameter_value: str | None
    score: float | None
    reason: str


@dataclass
class ParameterSweepAnalysisData:
    experiment_id: str
    strategy_id: str
    parameter_key: str | None
    generated_at: datetime
    sweep_status: str
    sweep_reliability_score: float | None
    detected_parameters: list = field(default_factory=list)
    variant_summaries: list = field(default_factory=list)
    metric_comparisons: list = field(default_factory=list)
    regions: list = field(default_factory=list)
    fragility_signals: ParameterSweepFragilityData | None = None
    rankings: list = field(default_factory=list)
    suggested_checks: list = field(default_factory=list)
    deterministic_summary: str = ""
    analysis_id: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flatten_params(params_json: dict | None) -> dict:
    """Flatten a nested dict to dot-paths.

    {"params": {"lookback": 20}} -> {"params.lookback": 20}
    Top-level identity keys are excluded.
    """
    if not params_json:
        return {}

    result: dict[str, Any] = {}

    def _recurse(obj: Any, prefix: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                full_key = f"{prefix}.{k}" if prefix else k
                _recurse(v, full_key)
        else:
            result[prefix] = obj

    for k, v in params_json.items():
        if k in _SKIP_KEYS:
            continue
        _recurse(v, k)

    return result


def _extract_param_value(
    run: StrategyRun,
    exp_run: StrategyExperimentRun,
    parameter_key: str,
) -> tuple[str | None, float | None]:
    """Return (str_value, numeric_value) for *parameter_key* from this variant.

    Priority: exp_run.variant_params_json > run.params_json (flattened).
    Also supports bare-key matching: "lookback" matches "params.lookback".
    """
    # Build merged flat dict: variant_params first, run.params second
    sources = [exp_run.variant_params_json, run.params_json]
    for source in sources:
        flat = _flatten_params(source)
        if not flat:
            continue

        # Direct key match
        if parameter_key in flat:
            raw = flat[parameter_key]
            str_val = str(raw) if raw is not None else None
            try:
                num_val: float | None = float(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                num_val = None
            return str_val, num_val

        # Bare key suffix match: "lookback" matches "params.lookback"
        for k, v in flat.items():
            if k == parameter_key or k.endswith(f".{parameter_key}"):
                str_val = str(v) if v is not None else None
                try:
                    num_val = float(v)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    num_val = None
                return str_val, num_val

    return None, None


def _infer_parameter_key(
    runs_with_exprun: list[tuple[StrategyRun, StrategyExperimentRun]],
) -> str | None:
    """Find the parameter key that varies most consistently across variants."""
    if not runs_with_exprun:
        return None

    n = len(runs_with_exprun)

    # Collect all keys and their values across variants
    key_values: dict[str, list[Any]] = {}
    for run, exp_run in runs_with_exprun:
        flat = _flatten_params(exp_run.variant_params_json) or _flatten_params(run.params_json)
        for k, v in flat.items():
            if k in _SKIP_KEYS:
                continue
            key_values.setdefault(k, []).append(v)

    if not key_values:
        return None

    best_key: str | None = None
    best_score = -1

    for k, values in key_values.items():
        # Skip identity-like keys
        if any(skip in k for skip in _SKIP_KEYS):
            continue

        coverage = len(values) / n
        unique_vals = list({str(v) for v in values})

        # Prefer keys with variation (multiple unique values)
        variation = len(unique_vals) / max(len(values), 1)

        # Check if numeric
        numeric_count = 0
        for v in values:
            try:
                float(v)  # type: ignore[arg-type]
                numeric_count += 1
            except (TypeError, ValueError):
                pass
        is_numeric = numeric_count == len(values) and len(values) > 0

        # Score: coverage * variation * (1.5 if numeric else 1.0)
        score = coverage * variation * (1.5 if is_numeric else 1.0)

        if score > best_score:
            best_score = score
            best_key = k

    return best_key


def _get_run_evidence(db: Session, run: StrategyRun) -> dict:
    """Return a dict of evidence fields for a StrategyRun."""
    dataset_health: float | None = None
    signal_quality: float | None = None
    backtest_trust: float | None = None

    try:
        # Dataset health
        if run.dataset_snapshot_id is not None:
            from app.models.dataset_snapshot import DatasetSnapshot

            snap = db.query(DatasetSnapshot).filter(
                DatasetSnapshot.id == run.dataset_snapshot_id
            ).first()
            if snap is not None:
                dataset_health = float(snap.health_score)

        # Signal quality
        if run.signal_snapshot_id is not None:
            from app.models.signal_snapshot import SignalSnapshot

            sig = db.query(SignalSnapshot).filter(
                SignalSnapshot.id == run.signal_snapshot_id
            ).first()
            if sig is not None:
                signal_quality = float(sig.quality_score)

        # Backtest trust
        audit = (
            db.query(BacktestAudit)
            .filter(BacktestAudit.strategy_run_id == run.id)
            .order_by(BacktestAudit.created_at.desc())
            .first()
        )
        if audit is not None:
            backtest_trust = float(audit.trust_score)

    except Exception:
        pass

    return {
        "dataset_health": dataset_health,
        "signal_quality": signal_quality,
        "backtest_trust": backtest_trust,
    }


def _compute_variant_evidence_score(evidence: dict, run: StrategyRun) -> float:
    """Compute evidence score 0-100 using same formula as M59 analyze_strategy_experiment."""
    score = 40.0

    if run.dataset_snapshot_id is not None:
        score += 15
    if run.signal_snapshot_id is not None:
        score += 15
    if evidence.get("backtest_trust") is not None:
        score += 20

    dh = evidence.get("dataset_health")
    if dh is not None and dh >= 75:
        score += 10

    return min(score, 100.0)


def _detect_parameters(
    runs_with_exprun: list[tuple[StrategyRun, StrategyExperimentRun]],
) -> list[DetectedParameterData]:
    """Detect all varying parameters across the sweep variants."""
    if not runs_with_exprun:
        return []

    n = len(runs_with_exprun)
    key_values: dict[str, list[Any]] = {}

    for run, exp_run in runs_with_exprun:
        flat = _flatten_params(exp_run.variant_params_json) or _flatten_params(run.params_json)
        for k, v in flat.items():
            if any(skip == k or k.endswith(f".{skip}") for skip in _SKIP_KEYS):
                continue
            key_values.setdefault(k, []).append(v)

    result: list[DetectedParameterData] = []
    for k, values in key_values.items():
        unique_vals: list[Any] = []
        seen: set[str] = set()
        for v in values:
            sv = str(v)
            if sv not in seen:
                seen.add(sv)
                unique_vals.append(v)

        numeric_count = 0
        for v in values:
            try:
                float(v)  # type: ignore[arg-type]
                numeric_count += 1
            except (TypeError, ValueError):
                pass

        result.append(
            DetectedParameterData(
                parameter_key=k,
                value_count=len(values),
                numeric=numeric_count == len(values) and len(values) > 0,
                unique_values=unique_vals,
                coverage_rate=len(values) / n,
                examples=unique_vals[:5],
            )
        )

    result.sort(key=lambda d: d.coverage_rate, reverse=True)
    return result[:10]


def _build_variant_summary(
    run: StrategyRun,
    exp_run: StrategyExperimentRun,
    parameter_key: str | None,
    evidence: dict,
) -> ParameterSweepVariantData:
    """Build a ParameterSweepVariantData for a single experiment run."""
    param_value, param_value_numeric = (
        _extract_param_value(run, exp_run, parameter_key)
        if parameter_key
        else (None, None)
    )

    evidence_score = _compute_variant_evidence_score(evidence, run)
    backtest_trust = evidence.get("backtest_trust")
    dataset_health = evidence.get("dataset_health")
    signal_quality = evidence.get("signal_quality")

    # Variant status
    if evidence_score >= 80 and backtest_trust is not None and backtest_trust >= 70:
        variant_status = "stable"
    elif evidence_score >= 60 and backtest_trust is not None and backtest_trust >= 60:
        variant_status = "usable"
    elif evidence_score >= 40:
        variant_status = "review"
    elif evidence_score >= 20 and (backtest_trust is None or backtest_trust < 60):
        variant_status = "fragile"
    else:
        variant_status = "insufficient_evidence"

    review_reasons: list[str] = []
    if run.dataset_snapshot_id is None:
        review_reasons.append("no dataset snapshot linked")
    if run.signal_snapshot_id is None:
        review_reasons.append("no signal snapshot linked")
    if backtest_trust is None:
        review_reasons.append("no backtest audit found")
    elif backtest_trust < 60:
        review_reasons.append(f"low backtest trust score ({backtest_trust:.0f})")
    if dataset_health is not None and dataset_health < 60:
        review_reasons.append(f"low dataset health ({dataset_health:.0f})")

    suggested_checks: list[str] = []
    if variant_status in ("fragile", "insufficient_evidence"):
        suggested_checks.append("Run backtest audit to establish trust score baseline")
    if run.dataset_snapshot_id is None:
        suggested_checks.append("Link a dataset snapshot to enable health scoring")
    if run.signal_snapshot_id is None:
        suggested_checks.append("Link a signal snapshot for signal quality evidence")

    def _mf(k: str) -> float | None:
        if not run.metrics_json:
            return None
        v = run.metrics_json.get(k)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    trade_count_raw = _mf("trade_count")
    trade_count = int(trade_count_raw) if trade_count_raw is not None else None

    run_health_label: str | None = None
    if evidence_score >= 80:
        run_health_label = "strong"
    elif evidence_score >= 60:
        run_health_label = "usable"
    elif evidence_score >= 40:
        run_health_label = "review"
    else:
        run_health_label = "weak"

    return ParameterSweepVariantData(
        experiment_run_id=str(exp_run.id),
        run_id=str(run.id),
        run_name=run.run_name,
        run_type=run.run_type,
        variant_label=exp_run.variant_label,
        parameter_key=parameter_key,
        parameter_value=param_value,
        parameter_value_numeric=param_value_numeric,
        sharpe=_mf("sharpe"),
        annual_return=_mf("annual_return"),
        max_drawdown=_mf("max_drawdown"),
        volatility=_mf("volatility"),
        turnover=_mf("turnover"),
        hit_rate=_mf("hit_rate"),
        trade_count=trade_count,
        dataset_health=dataset_health,
        signal_quality=signal_quality,
        backtest_trust=backtest_trust,
        evidence_score=evidence_score,
        run_health_label=run_health_label,
        variant_status=variant_status,
        review_reasons=review_reasons,
        suggested_checks=suggested_checks,
    )


def _compute_metric_comparisons(
    variants: list[ParameterSweepVariantData],
) -> list[dict]:
    """Compute per-metric comparison stats across variants."""
    result: list[dict] = []
    for mk in _METRIC_KEYS:
        values_by_run_id: dict[str, Any] = {}
        for v in variants:
            val = getattr(v, mk, None)
            if val is not None:
                values_by_run_id[v.run_id] = val

        vals = list(values_by_run_id.values())
        if not vals:
            result.append(
                {
                    "metric_key": mk,
                    "available_count": 0,
                    "min_value": None,
                    "max_value": None,
                    "mean_value": None,
                    "range_value": None,
                    "values_by_run_id": {},
                }
            )
        else:
            mn = min(vals)
            mx = max(vals)
            mean = sum(vals) / len(vals)
            result.append(
                {
                    "metric_key": mk,
                    "available_count": len(vals),
                    "min_value": mn,
                    "max_value": mx,
                    "mean_value": mean,
                    "range_value": mx - mn,
                    "values_by_run_id": values_by_run_id,
                }
            )
    return result


def _avg(values: list[float | None]) -> float | None:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return None
    return sum(non_null) / len(non_null)


def _detect_regions_numeric(
    variants_sorted: list[ParameterSweepVariantData],
) -> list[ParameterSweepRegionData]:
    """Detect stable / fragile / narrow-peak / under-instrumented regions in numeric sweep."""
    regions: list[ParameterSweepRegionData] = []

    # Under-instrumented: no dataset, no signal, no audit
    under_instr = [
        v
        for v in variants_sorted
        if v.dataset_health is None and v.signal_quality is None and v.backtest_trust is None
    ]
    if under_instr:
        regions.append(
            ParameterSweepRegionData(
                region_key="under_instrumented",
                label="Under-instrumented variants",
                parameter_min=None,
                parameter_max=None,
                variant_count=len(under_instr),
                run_ids=[v.run_id for v in under_instr],
                status="under_instrumented",
                evidence_score_avg=_avg([v.evidence_score for v in under_instr]),
                backtest_trust_avg=None,
                metric_stability_score=None,
                reason=f"{len(under_instr)} variant(s) have no dataset, signal, or audit evidence.",
                suggested_check="Link dataset and signal snapshots, then run backtest audit.",
            )
        )

    if len(variants_sorted) < 2:
        return regions

    # Stable regions: consecutive run of variants with evidence >= 75 and trust >= 70
    stable_region_idx = 0
    i = 0
    while i < len(variants_sorted):
        run_start = i
        while i < len(variants_sorted):
            v = variants_sorted[i]
            if v.evidence_score >= 75 and v.backtest_trust is not None and v.backtest_trust >= 70:
                i += 1
            else:
                break
        run_end = i
        if run_end - run_start >= 2:
            stable_region_idx += 1
            seg = variants_sorted[run_start:run_end]
            p_vals = [v.parameter_value_numeric for v in seg if v.parameter_value_numeric is not None]
            regions.append(
                ParameterSweepRegionData(
                    region_key=f"stable_region_{stable_region_idx}",
                    label=f"Stable region {stable_region_idx}",
                    parameter_min=min(p_vals) if p_vals else None,
                    parameter_max=max(p_vals) if p_vals else None,
                    variant_count=len(seg),
                    run_ids=[v.run_id for v in seg],
                    status="stable",
                    evidence_score_avg=_avg([v.evidence_score for v in seg]),
                    backtest_trust_avg=_avg([v.backtest_trust for v in seg]),
                    metric_stability_score=None,
                    reason="Consecutive variants with high evidence and trust scores.",
                    suggested_check=None,
                )
            )
        i = max(i, run_start + 1)

    # Fragile regions: consecutive run with trust < 60 or evidence < 50
    fragile_region_idx = 0
    i = 0
    while i < len(variants_sorted):
        run_start = i
        while i < len(variants_sorted):
            v = variants_sorted[i]
            is_fragile = v.backtest_trust is None or v.backtest_trust < 60 or v.evidence_score < 50
            if is_fragile:
                i += 1
            else:
                break
        run_end = i
        if run_end - run_start >= 1:
            fragile_region_idx += 1
            seg = variants_sorted[run_start:run_end]
            p_vals = [v.parameter_value_numeric for v in seg if v.parameter_value_numeric is not None]
            regions.append(
                ParameterSweepRegionData(
                    region_key=f"fragile_region_{fragile_region_idx}",
                    label=f"Fragile region {fragile_region_idx}",
                    parameter_min=min(p_vals) if p_vals else None,
                    parameter_max=max(p_vals) if p_vals else None,
                    variant_count=len(seg),
                    run_ids=[v.run_id for v in seg],
                    status="fragile",
                    evidence_score_avg=_avg([v.evidence_score for v in seg]),
                    backtest_trust_avg=_avg([v.backtest_trust for v in seg]),
                    metric_stability_score=None,
                    reason="Variants with low trust or insufficient evidence.",
                    suggested_check="Review backtest audit findings for these parameter values.",
                )
            )
        i = max(i, run_start + 1)

    # Narrow peak: one variant has sharpe significantly higher than both neighbors
    sharpe_vals = [v.sharpe for v in variants_sorted]
    if len(sharpe_vals) >= 3:
        for idx in range(1, len(variants_sorted) - 1):
            curr = sharpe_vals[idx]
            prev_v = sharpe_vals[idx - 1]
            next_v = sharpe_vals[idx + 1]
            if curr is not None and prev_v is not None and next_v is not None:
                neighbor_avg = (prev_v + next_v) / 2
                if curr - neighbor_avg > 0.5:
                    v = variants_sorted[idx]
                    p_val = v.parameter_value_numeric
                    regions.append(
                        ParameterSweepRegionData(
                            region_key="narrow_peak_region",
                            label="Narrow Sharpe peak",
                            parameter_min=p_val,
                            parameter_max=p_val,
                            variant_count=1,
                            run_ids=[v.run_id],
                            status="review",
                            evidence_score_avg=v.evidence_score,
                            backtest_trust_avg=v.backtest_trust,
                            metric_stability_score=None,
                            reason=(
                                f"Sharpe at this parameter value ({curr:.2f}) is notably higher "
                                f"than neighbors ({neighbor_avg:.2f}). May indicate overfitting."
                            ),
                            suggested_check="Verify this parameter value is not curve-fitted to in-sample data.",
                        )
                    )
                    break  # one narrow peak region max

    return regions


def _detect_regions_categorical(
    variants: list[ParameterSweepVariantData],
) -> list[ParameterSweepRegionData]:
    """Detect regions for categorical parameter sweep."""
    groups: dict[str, list[ParameterSweepVariantData]] = {}
    for v in variants:
        key = v.parameter_value or "_unknown_"
        groups.setdefault(key, []).append(v)

    regions: list[ParameterSweepRegionData] = []
    for group_key, group_variants in groups.items():
        avg_evidence = _avg([v.evidence_score for v in group_variants])
        avg_trust = _avg([v.backtest_trust for v in group_variants])
        regions.append(
            ParameterSweepRegionData(
                region_key=f"group_{group_key}",
                label=f"Parameter group: {group_key}",
                parameter_min=None,
                parameter_max=None,
                variant_count=len(group_variants),
                run_ids=[v.run_id for v in group_variants],
                status="stable" if (avg_evidence or 0) >= 75 else "review",
                evidence_score_avg=avg_evidence,
                backtest_trust_avg=avg_trust,
                metric_stability_score=None,
                reason=f"Group for parameter value '{group_key}'.",
                suggested_check=None,
            )
        )

    return regions


def _detect_fragility_signals(
    variants: list[ParameterSweepVariantData],
    regions: list[ParameterSweepRegionData],
) -> ParameterSweepFragilityData:
    """Compute fragility signal flags."""
    fragile_count = sum(1 for v in variants if v.variant_status == "fragile")
    review_count = sum(
        1 for v in variants if v.variant_status in ("review", "fragile", "insufficient_evidence")
    )
    under_instr_count = sum(
        1
        for v in variants
        if v.dataset_health is None and v.signal_quality is None and v.backtest_trust is None
    )

    # Narrow peak: any region with status "review" and key contains "narrow"
    narrow_peak = any(
        r.status == "review" and "narrow" in r.region_key.lower() for r in regions
    )

    # Evidence degradation: for numeric sorted variants, first two avg > last two avg by > 15
    numeric_sorted = sorted(
        [v for v in variants if v.parameter_value_numeric is not None],
        key=lambda v: v.parameter_value_numeric,  # type: ignore[arg-type]
    )
    evidence_degradation = False
    trust_degradation = False
    if len(numeric_sorted) >= 4:
        first_two_evidence = _avg([v.evidence_score for v in numeric_sorted[:2]])
        last_two_evidence = _avg([v.evidence_score for v in numeric_sorted[-2:]])
        if (
            first_two_evidence is not None
            and last_two_evidence is not None
            and first_two_evidence - last_two_evidence > 15
        ):
            evidence_degradation = True

        first_two_trust = _avg([v.backtest_trust for v in numeric_sorted[:2]])
        last_two_trust = _avg([v.backtest_trust for v in numeric_sorted[-2:]])
        if (
            first_two_trust is not None
            and last_two_trust is not None
            and first_two_trust - last_two_trust > 15
        ):
            trust_degradation = True

    # Metric instability
    sharpe_vals = [v.sharpe for v in variants if v.sharpe is not None]
    sharpe_range = (max(sharpe_vals) - min(sharpe_vals)) if len(sharpe_vals) >= 2 else 0.0
    drawdown_vals = [v.max_drawdown for v in variants if v.max_drawdown is not None]
    drawdown_range = (max(drawdown_vals) - min(drawdown_vals)) if len(drawdown_vals) >= 2 else 0.0
    turnover_vals = [v.turnover for v in variants if v.turnover is not None]
    turnover_range = (max(turnover_vals) - min(turnover_vals)) if len(turnover_vals) >= 2 else 0.0

    metric_instability = (
        sharpe_range > 1.0 or drawdown_range > 0.15 or turnover_range > 0.5
    )

    return ParameterSweepFragilityData(
        fragile_variant_count=fragile_count,
        review_variant_count=review_count,
        under_instrumented_variant_count=under_instr_count,
        narrow_peak_detected=narrow_peak,
        evidence_degradation_detected=evidence_degradation,
        trust_degradation_detected=trust_degradation,
        metric_instability_detected=metric_instability,
    )


def _compute_sweep_score(
    variants: list[ParameterSweepVariantData],
    fragility: ParameterSweepFragilityData,
) -> tuple[float, str]:
    """Compute sweep reliability score (0-100) and status string."""
    score = 100.0

    # Deductions
    score -= min(fragility.fragile_variant_count * 15, 45)
    score -= min(fragility.under_instrumented_variant_count * 10, 30)
    if fragility.narrow_peak_detected:
        score -= 20
    if fragility.evidence_degradation_detected:
        score -= 15
    if fragility.trust_degradation_detected:
        score -= 15
    if fragility.metric_instability_detected:
        score -= 10

    if len(variants) < 3:
        score = min(score, 70.0)

    score = max(score, 0.0)

    if len(variants) < 2:
        status = "insufficient_variants"
    elif score >= 85:
        status = "stable"
    elif score >= 70:
        status = "usable"
    elif score >= 50:
        status = "review"
    else:
        status = "fragile"

    return score, status


def _build_rankings(
    variants: list[ParameterSweepVariantData],
) -> list[ParameterSweepRankingItemData]:
    """Rank variants by evidence_score descending, return top 5."""
    sorted_variants = sorted(variants, key=lambda v: v.evidence_score, reverse=True)
    result: list[ParameterSweepRankingItemData] = []
    for i, v in enumerate(sorted_variants[:5]):
        result.append(
            ParameterSweepRankingItemData(
                rank=i + 1,
                run_id=v.run_id,
                variant_label=v.variant_label,
                parameter_value=v.parameter_value,
                score=v.evidence_score,
                reason=f"evidence score {v.evidence_score:.0f}; status: {v.variant_status}",
            )
        )
    return result


def _build_suggested_checks(
    variants: list[ParameterSweepVariantData],
    fragility: ParameterSweepFragilityData,
    regions: list[ParameterSweepRegionData],
) -> list[str]:
    """Build deduplicated list of suggested checks based on findings."""
    checks: list[str] = []

    if fragility.under_instrumented_variant_count > 0:
        checks.append(
            f"{fragility.under_instrumented_variant_count} variant(s) lack evidence links — "
            "add dataset and signal snapshots before drawing conclusions."
        )
    if fragility.narrow_peak_detected:
        checks.append(
            "Narrow performance peak detected — verify no in-sample over-selection of this parameter value."
        )
    if fragility.evidence_degradation_detected:
        checks.append(
            "Evidence quality degrades at higher parameter values — check data coverage for those runs."
        )
    if fragility.trust_degradation_detected:
        checks.append(
            "Backtest trust degrades at higher parameter values — review audit findings for those runs."
        )
    if fragility.metric_instability_detected:
        checks.append(
            "High metric variability across the sweep — consider narrowing the parameter range."
        )
    if fragility.fragile_variant_count > 0:
        checks.append(
            f"{fragility.fragile_variant_count} fragile variant(s) — run backtest audits to establish trust baselines."
        )

    # Collect from region suggested_checks
    for r in regions:
        if r.suggested_check and r.suggested_check not in checks:
            checks.append(r.suggested_check)

    # Collect from variant-level suggested_checks (deduplicate)
    seen = set(checks)
    for v in variants:
        for sc in v.suggested_checks:
            if sc not in seen:
                checks.append(sc)
                seen.add(sc)

    return checks


def _build_sweep_summary(
    parameter_key: str | None,
    variants: list[ParameterSweepVariantData],
    fragility: ParameterSweepFragilityData,
    sweep_status: str,
    regions: list[ParameterSweepRegionData],
) -> str:
    """Build a deterministic, plain-language summary of the sweep analysis."""
    n = len(variants)
    key_label = parameter_key or "unknown parameter"

    stable_count = sum(1 for v in variants if v.variant_status == "stable")
    usable_count = sum(1 for v in variants if v.variant_status == "usable")
    review_count = fragility.review_variant_count
    fragile_count = fragility.fragile_variant_count

    parts = [f"Parameter sweep over '{key_label}' with {n} variant(s)."]

    if stable_count > 0:
        parts.append(f"{stable_count} variant(s) have stable evidence.")
    if usable_count > 0:
        parts.append(f"{usable_count} variant(s) are usable.")
    if review_count > 0:
        parts.append(f"{review_count} variant(s) require review.")
    if fragile_count > 0:
        parts.append(f"{fragile_count} variant(s) are fragile.")

    if fragility.narrow_peak_detected:
        parts.append("A narrow performance peak was detected — verify no over-selection.")
    if fragility.evidence_degradation_detected:
        parts.append("Evidence quality degrades at higher parameter values.")
    if fragility.trust_degradation_detected:
        parts.append("Backtest trust degrades at higher parameter values.")
    if fragility.metric_instability_detected:
        parts.append("High metric variability observed across the sweep.")

    stable_regions = [r for r in regions if r.status == "stable"]
    if stable_regions:
        r = stable_regions[0]
        if r.parameter_min is not None and r.parameter_max is not None:
            parts.append(
                f"Stable region spans parameter values {r.parameter_min} to {r.parameter_max}."
            )

    parts.append(f"Overall sweep status: {sweep_status}.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def analyze_parameter_sweep(
    db: Session,
    experiment_id: str,
    parameter_key: str | None = None,
    analysis_label: str | None = None,
    persist: bool = True,
) -> ParameterSweepAnalysisData:
    """Run a deterministic parameter sweep reliability analysis for an experiment."""
    from sqlalchemy.orm import joinedload

    experiment = (
        db.query(StrategyExperiment)
        .options(joinedload(StrategyExperiment.experiment_runs))
        .filter(StrategyExperiment.id == uuid.UUID(experiment_id))
        .first()
    )
    if experiment is None:
        raise ValueError(f"Experiment {experiment_id!r} not found")

    strategy_id_str = str(experiment.strategy_id)

    exp_runs = list(experiment.experiment_runs)

    # Insufficient variants early return
    if len(exp_runs) < 2:
        _empty_fragility = ParameterSweepFragilityData(
            fragile_variant_count=0,
            review_variant_count=0,
            under_instrumented_variant_count=0,
            narrow_peak_detected=False,
            evidence_degradation_detected=False,
            trust_degradation_detected=False,
            metric_instability_detected=False,
        )
        return ParameterSweepAnalysisData(
            experiment_id=experiment_id,
            strategy_id=strategy_id_str,
            parameter_key=parameter_key,
            generated_at=datetime.now(timezone.utc),
            sweep_status="insufficient_variants",
            sweep_reliability_score=None,
            detected_parameters=[],
            variant_summaries=[],
            metric_comparisons=[],
            regions=[],
            fragility_signals=_empty_fragility,
            rankings=[],
            suggested_checks=["Add at least 2 runs to the experiment before running sweep analysis."],
            deterministic_summary=(
                f"Experiment has {len(exp_runs)} variant(s). "
                "At least 2 runs are required for parameter sweep analysis."
            ),
            analysis_id=None,
        )

    # Load runs
    runs_with_exprun: list[tuple[StrategyRun, StrategyExperimentRun]] = []
    for exp_run in exp_runs:
        run = db.query(StrategyRun).filter(StrategyRun.id == exp_run.strategy_run_id).first()
        if run is not None:
            runs_with_exprun.append((run, exp_run))

    # Detect parameters
    detected_parameters = _detect_parameters(runs_with_exprun)

    # Infer parameter key if not provided
    if parameter_key is None:
        parameter_key = _infer_parameter_key(runs_with_exprun)

    if parameter_key is None:
        _empty_fragility = ParameterSweepFragilityData(
            fragile_variant_count=0,
            review_variant_count=0,
            under_instrumented_variant_count=0,
            narrow_peak_detected=False,
            evidence_degradation_detected=False,
            trust_degradation_detected=False,
            metric_instability_detected=False,
        )
        return ParameterSweepAnalysisData(
            experiment_id=experiment_id,
            strategy_id=strategy_id_str,
            parameter_key=None,
            generated_at=datetime.now(timezone.utc),
            sweep_status="insufficient_parameter_data",
            sweep_reliability_score=None,
            detected_parameters=detected_parameters,
            variant_summaries=[],
            metric_comparisons=[],
            regions=[],
            fragility_signals=_empty_fragility,
            rankings=[],
            suggested_checks=["Set params_json or variant_params_json on each run to enable parameter detection."],
            deterministic_summary=(
                "No varying parameter key could be inferred from the experiment runs. "
                "Ensure runs have params_json or variant_params_json populated."
            ),
            analysis_id=None,
        )

    # Build per-variant summaries
    variants: list[ParameterSweepVariantData] = []
    for run, exp_run in runs_with_exprun:
        evidence = _get_run_evidence(db, run)
        v = _build_variant_summary(run, exp_run, parameter_key, evidence)
        variants.append(v)

    # Determine if numeric
    numeric_variants = [v for v in variants if v.parameter_value_numeric is not None]
    is_numeric = len(numeric_variants) == len(variants) and len(variants) > 0

    # Metric comparisons
    metric_comparisons = _compute_metric_comparisons(variants)

    # Regions
    if is_numeric:
        sorted_variants = sorted(variants, key=lambda v: v.parameter_value_numeric)  # type: ignore[arg-type]
        regions = _detect_regions_numeric(sorted_variants)
    else:
        regions = _detect_regions_categorical(variants)

    # Fragility signals
    fragility = _detect_fragility_signals(variants, regions)

    # Sweep score and status
    sweep_score, sweep_status = _compute_sweep_score(variants, fragility)

    # Rankings
    rankings = _build_rankings(variants)

    # Suggested checks
    suggested_checks = _build_suggested_checks(variants, fragility, regions)

    # Summary
    deterministic_summary = _build_sweep_summary(
        parameter_key, variants, fragility, sweep_status, regions
    )

    # Persist if requested
    analysis_id: str | None = None
    if persist:
        label = analysis_label or f"Parameter Sweep: {parameter_key}"

        def _dc_to_dict(obj: Any) -> Any:
            """Recursively convert dataclasses to dicts for JSON serialisation."""
            import dataclasses

            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                return {k: _dc_to_dict(v) for k, v in dataclasses.asdict(obj).items()}
            if isinstance(obj, list):
                return [_dc_to_dict(i) for i in obj]
            if isinstance(obj, datetime):
                return obj.isoformat()
            return obj

        result_json: dict[str, Any] = {
            "parameter_key": parameter_key,
            "sweep_status": sweep_status,
            "sweep_reliability_score": sweep_score,
            "detected_parameters": [_dc_to_dict(d) for d in detected_parameters],
            "variant_summaries": [_dc_to_dict(v) for v in variants],
            "metric_comparisons": metric_comparisons,
            "regions": [_dc_to_dict(r) for r in regions],
            "fragility_signals": _dc_to_dict(fragility),
            "rankings": [_dc_to_dict(r) for r in rankings],
            "suggested_checks": suggested_checks,
        }

        best_run_id = rankings[0].run_id if rankings else None

        analysis = StrategyExperimentAnalysis(
            experiment_id=experiment.id,
            analysis_label=label,
            overall_status=sweep_status,
            variant_count=len(variants),
            run_count=len(variants),
            best_evidenced_run_id=best_run_id,
            weakest_evidence_run_id=rankings[-1].run_id if rankings else None,
            result_json=result_json,
            deterministic_summary=deterministic_summary,
            created_at=datetime.now(timezone.utc),
        )
        db.add(analysis)
        db.flush()
        analysis_id = str(analysis.id)

        # Timeline event
        strategy = db.query(Strategy).filter(Strategy.id == experiment.strategy_id).first()
        if strategy is not None:
            project = strategy.project
            if project is None:
                from app.models.project import Project

                project = db.query(Project).filter_by(id=strategy.project_id).first()

            organization_id = project.organization_id if project else None

            event = AuditTimelineEvent(
                organization_id=organization_id,
                project_id=strategy.project_id,
                strategy_id=strategy.id,
                event_type=str(EventType.strategy_sweep_analyzed),
                title="Parameter sweep analysis completed",
                source_type="experiment",
                source_id=str(experiment.id),
                severity="info",
                event_time=datetime.now(timezone.utc),
                metadata_json={
                    "analysis_id": analysis_id,
                    "analysis_type": "parameter_sweep",
                    "parameter_key": parameter_key,
                    "sweep_status": sweep_status,
                    "variant_count": len(variants),
                },
            )
            db.add(event)
            db.flush()

    return ParameterSweepAnalysisData(
        experiment_id=experiment_id,
        strategy_id=strategy_id_str,
        parameter_key=parameter_key,
        generated_at=datetime.now(timezone.utc),
        sweep_status=sweep_status,
        sweep_reliability_score=sweep_score,
        detected_parameters=detected_parameters,
        variant_summaries=variants,
        metric_comparisons=metric_comparisons,
        regions=regions,
        fragility_signals=fragility,
        rankings=rankings,
        suggested_checks=suggested_checks,
        deterministic_summary=deterministic_summary,
        analysis_id=analysis_id,
    )
