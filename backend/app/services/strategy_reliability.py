"""M18/M19: Deterministic per-strategy reliability scoring and comparison service.

Aggregates all evidence collected so far (runs, dataset snapshots, backtest
audits, config/universe/signal snapshots, open alerts, reports) into a single
reliability score.  M19 adds score-to-score comparison for trend analysis.
No AI, no live data, no external calls.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.models.strategy_reliability_score import StrategyReliabilityScore

from app.core.constants import ReliabilityScoreStatus
from app.models.alert import Alert
from app.models.backtest_audit import BacktestAudit
from app.models.data_quality_issue import DataQualityIssue
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.report import Report
from app.models.strategy_config_snapshot import StrategyConfigSnapshot
from app.models.strategy_run import StrategyRun
from app.models.strategy_version import StrategyVersion
from app.models.universe_snapshot import UniverseSnapshot
from app.models.signal_snapshot import SignalSnapshot

# ---------------------------------------------------------------------------
# Weight map for overall score computation
# ---------------------------------------------------------------------------

WEIGHTS: dict[str, float] = {
    "backtest_trust_score": 0.25,
    "data_evidence_score": 0.20,
    "signal_evidence_score": 0.15,
    "universe_evidence_score": 0.10,
    "config_evidence_score": 0.10,
    "strategy_activity_score": 0.10,
    "alert_penalty_score": 0.10,
}


# ---------------------------------------------------------------------------
# Component scoring functions
# ---------------------------------------------------------------------------


def _score_activity(runs: list[StrategyRun]) -> float:
    """Score based on number and diversity of strategy runs. Never None."""
    n = len(runs)
    if n == 0:
        base = 30.0
    elif n == 1:
        base = 55.0
    else:
        base = 75.0

    # Bonus: if run types include backtest AND at least one of (paper/live/research)
    run_types = {r.run_type for r in runs}
    has_backtest = "backtest" in run_types
    has_other = bool(run_types & {"paper", "live", "research"})
    if has_backtest and has_other:
        base = min(base + 10.0, 100.0)

    return base


def _score_data_evidence(
    runs: list[StrategyRun], db: Session
) -> float | None:
    """Score based on linked dataset snapshot health. None when no linked snapshots."""
    # Get run IDs that have dataset_snapshot_id set
    snapshot_ids = [
        r.dataset_snapshot_id
        for r in runs
        if r.dataset_snapshot_id is not None
    ]
    if not snapshot_ids:
        return None

    snapshots = (
        db.query(DatasetSnapshot)
        .filter(DatasetSnapshot.id.in_(snapshot_ids))
        .all()
    )
    if not snapshots:
        return None

    # Average health score
    avg_health = sum(s.health_score for s in snapshots) / len(snapshots)
    result = avg_health

    # Cap at 60 if any snapshot health < 50
    if any(s.health_score < 50 for s in snapshots):
        result = min(result, 60.0)

    # Cap at 70 if any snapshot has critical quality issues
    snap_ids = [s.id for s in snapshots]
    critical_count = (
        db.query(DataQualityIssue)
        .filter(
            DataQualityIssue.snapshot_id.in_(snap_ids),
            DataQualityIssue.severity == "critical",
        )
        .count()
    )
    if critical_count > 0:
        result = min(result, 70.0)

    return round(result, 1)


def _score_backtest_trust(
    runs: list[StrategyRun], db: Session
) -> float | None:
    """Score based on backtest audit trust scores. None when no audits exist."""
    run_ids = [r.id for r in runs]
    if not run_ids:
        return None

    audits = (
        db.query(BacktestAudit)
        .filter(BacktestAudit.strategy_run_id.in_(run_ids))
        .all()
    )
    if not audits:
        return None

    avg_trust = sum(a.trust_score for a in audits) / len(audits)
    result = avg_trust

    # Cap at 65 if any audit has weak or unreliable status
    if any(a.overall_status in ("weak", "unreliable") for a in audits):
        result = min(result, 65.0)

    return round(result, 1)


def _score_config_evidence(
    strategy_id: uuid.UUID,
    versions: list[StrategyVersion],
    db: Session,
) -> float:
    """Score based on config snapshot availability. Never None."""
    if not versions:
        return 40.0

    # Count config snapshots for this strategy
    config_snapshots = (
        db.query(StrategyConfigSnapshot)
        .filter(StrategyConfigSnapshot.strategy_id == strategy_id)
        .all()
    )
    if not config_snapshots:
        return 60.0
    if len(config_snapshots) >= 2:
        return 90.0
    return 85.0


def _score_universe_evidence(
    runs: list[StrategyRun],
    universe_snapshots: list[UniverseSnapshot],
    db: Session,
) -> float | None:
    """Score based on universe snapshot availability. None when no snapshots."""
    if not universe_snapshots:
        return None

    n = len(universe_snapshots)
    if n == 1:
        base = 75.0
    else:
        base = 85.0

    # Bonus if any run has a universe_snapshot_id set
    has_linked_run = any(r.universe_snapshot_id is not None for r in runs)
    if has_linked_run:
        base = min(base + 10.0, 100.0)

    return base


def _score_signal_evidence(
    runs: list[StrategyRun],
    signal_snapshots: list[SignalSnapshot],
    db: Session,
) -> float | None:
    """Score based on signal snapshot quality. None when no snapshots."""
    if not signal_snapshots:
        return None

    # Average quality_score (0–100 integer) across all signal snapshots
    avg_quality = sum(s.quality_score for s in signal_snapshots) / len(signal_snapshots)
    result = float(avg_quality)

    # Cap at 75 if any quality < 70
    if any(s.quality_score < 70 for s in signal_snapshots):
        result = min(result, 75.0)

    # Slight boost if any run links a signal snapshot
    has_linked_run = any(r.signal_snapshot_id is not None for r in runs)
    if has_linked_run:
        result = min(result + 5.0, 100.0)

    return round(result, 1)


def _score_alert_penalty(strategy_id: uuid.UUID, db: Session) -> float:
    """Score penalized by open alerts. Never None."""
    # Load all open alerts for this strategy
    open_alerts = (
        db.query(Alert)
        .filter(
            Alert.strategy_id == str(strategy_id),
            Alert.status == "open",
        )
        .all()
    )

    score = 100.0
    for alert in open_alerts:
        sev = alert.severity
        if sev == "low":
            score -= 5.0
        elif sev == "medium":
            score -= 10.0
        elif sev == "high":
            score -= 20.0
        elif sev == "critical":
            score -= 30.0

    return max(score, 0.0)


def _score_report_coverage(strategy_id: uuid.UUID, db: Session) -> float | None:
    """Score based on report existence and recency. None when no reports."""
    reports = (
        db.query(Report)
        .filter(
            Report.strategy_id == strategy_id,
            Report.report_type == "strategy_reliability",
        )
        .order_by(Report.generated_at.desc())
        .all()
    )
    if not reports:
        return None

    latest = reports[0]
    now = datetime.now(timezone.utc)
    generated = latest.generated_at
    # Make timezone-aware if needed
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)

    age = now - generated
    if age <= timedelta(days=30):
        return 90.0
    return 80.0


# ---------------------------------------------------------------------------
# Status from score
# ---------------------------------------------------------------------------


def _status_from_score(score: float | None) -> str:
    """Deterministic status from overall score."""
    if score is None:
        return ReliabilityScoreStatus.insufficient_evidence
    if score >= 90:
        return ReliabilityScoreStatus.excellent
    if score >= 75:
        return ReliabilityScoreStatus.good
    if score >= 55:
        return ReliabilityScoreStatus.review
    return ReliabilityScoreStatus.weak


# ---------------------------------------------------------------------------
# Main computation function
# ---------------------------------------------------------------------------


def compute_reliability_score(strategy_id: str, db: Session) -> dict:
    """Compute and return all score components as a dict ready for ORM insertion.

    Loads all evidence for the strategy (runs, snapshots, audits, alerts, reports)
    and computes a deterministic per-component + overall reliability score.
    No AI, no live data, no external calls.
    """
    strategy_uuid = uuid.UUID(strategy_id)
    now = datetime.now(timezone.utc)

    # Load data
    runs: list[StrategyRun] = (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_uuid)
        .all()
    )
    versions: list[StrategyVersion] = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_uuid)
        .all()
    )
    universe_snapshots: list[UniverseSnapshot] = (
        db.query(UniverseSnapshot)
        .filter(UniverseSnapshot.strategy_id == strategy_uuid)
        .all()
    )
    signal_snapshots: list[SignalSnapshot] = (
        db.query(SignalSnapshot)
        .filter(SignalSnapshot.strategy_id == strategy_uuid)
        .all()
    )

    # Compute components
    missing_evidence: list[str] = []

    activity_score = _score_activity(runs)

    data_score = _score_data_evidence(runs, db)
    if data_score is None:
        missing_evidence.append("No dataset snapshots linked to any strategy run.")

    backtest_score = _score_backtest_trust(runs, db)
    if backtest_score is None:
        missing_evidence.append("No backtest audits found for any strategy run.")

    config_score = _score_config_evidence(strategy_uuid, versions, db)

    universe_score = _score_universe_evidence(runs, universe_snapshots, db)
    if universe_score is None:
        missing_evidence.append("No universe snapshots found for this strategy.")

    signal_score = _score_signal_evidence(runs, signal_snapshots, db)
    if signal_score is None:
        missing_evidence.append("No signal snapshots found for this strategy.")

    alert_score = _score_alert_penalty(strategy_uuid, db)

    report_score = _score_report_coverage(strategy_uuid, db)
    if report_score is None:
        missing_evidence.append("No strategy_reliability report generated yet.")

    # Build component map
    components: dict[str, float | None] = {
        "strategy_activity_score": activity_score,
        "data_evidence_score": data_score,
        "backtest_trust_score": backtest_score,
        "config_evidence_score": config_score,
        "universe_evidence_score": universe_score,
        "signal_evidence_score": signal_score,
        "alert_penalty_score": alert_score,
        "report_coverage_score": report_score,
    }

    # Compute weighted overall score
    available_weight_sum = 0.0
    weighted_sum = 0.0
    non_null_count = 0
    for key, weight in WEIGHTS.items():
        val = components.get(key)
        if val is not None:
            weighted_sum += weight * val
            available_weight_sum += weight
            non_null_count += 1

    if non_null_count < 3 or available_weight_sum == 0:
        overall_score: float | None = None
        status = ReliabilityScoreStatus.insufficient_evidence
    else:
        overall_score = round(weighted_sum / available_weight_sum, 1)
        status = _status_from_score(overall_score)

    # Suggested checks
    suggested_checks: list[str] = []
    if len(runs) == 0:
        suggested_checks.append("Log at least two strategy runs.")
    elif len(runs) == 1:
        suggested_checks.append("Log at least one more strategy run to improve evidence.")
    if data_score is None:
        suggested_checks.append("Link dataset snapshots to strategy runs.")
    if backtest_score is None:
        suggested_checks.append("Run a Backtest Reality Check.")
    if universe_score is None:
        suggested_checks.append("Log universe snapshots for this strategy.")
    if signal_score is None:
        suggested_checks.append("Log signal snapshots to inspect signal coverage.")
    if alert_score < 80:
        suggested_checks.append("Resolve open alerts for this strategy.")
    if report_score is None:
        suggested_checks.append("Generate a reliability report for this strategy.")
    if backtest_score is not None and backtest_score < 70:
        suggested_checks.append("Investigate low-trust backtest audits.")

    # Evidence counts for transparency
    evidence_counts = {
        "run_count": len(runs),
        "version_count": len(versions),
        "universe_snapshot_count": len(universe_snapshots),
        "signal_snapshot_count": len(signal_snapshots),
        "linked_dataset_snapshot_count": sum(
            1 for r in runs if r.dataset_snapshot_id is not None
        ),
    }

    # Component summaries (brief text description of each score)
    component_summaries: dict[str, str] = {}
    for key, val in components.items():
        if val is not None:
            component_summaries[key] = f"{val:.1f}"
        else:
            component_summaries[key] = "N/A"

    return {
        "strategy_id": strategy_uuid,
        "overall_score": overall_score,
        "status": str(status),
        "strategy_activity_score": activity_score,
        "data_evidence_score": data_score,
        "backtest_trust_score": backtest_score,
        "config_evidence_score": config_score,
        "universe_evidence_score": universe_score,
        "signal_evidence_score": signal_score,
        "alert_penalty_score": alert_score,
        "report_coverage_score": report_score,
        "evidence_counts_json": evidence_counts,
        "component_summaries_json": component_summaries,
        "missing_evidence_json": missing_evidence if missing_evidence else None,
        "suggested_checks_json": suggested_checks if suggested_checks else None,
        "generated_at": now,
    }


# ---------------------------------------------------------------------------
# M19: Deterministic score comparison
# ---------------------------------------------------------------------------

# Human-readable names for component keys (used in explanation text).
_COMPONENT_DISPLAY_NAMES: dict[str, str] = {
    "strategy_activity_score": "Activity",
    "data_evidence_score": "Data Evidence",
    "backtest_trust_score": "Backtest Trust",
    "config_evidence_score": "Config",
    "universe_evidence_score": "Universe",
    "signal_evidence_score": "Signal",
    "alert_penalty_score": "Alert Penalty",
    "report_coverage_score": "Report Coverage",
}

_ALL_COMPONENTS = list(_COMPONENT_DISPLAY_NAMES.keys())


@dataclass
class ReliabilityComponentDelta:
    """Per-component change between two reliability score rows."""
    component: str
    label: str
    score_a: float | None
    score_b: float | None
    delta: float | None        # score_b - score_a; None if either is None
    became_available: bool     # was None → now has value
    became_null: bool          # had value → now None


@dataclass
class EvidenceCountDelta:
    """Change in an evidence count field between two score rows."""
    key: str
    count_a: int | None
    count_b: int | None
    delta: int | None


@dataclass
class ReliabilityComparisonResult:
    """Structured result of comparing two StrategyReliabilityScore rows (M19)."""
    score_a_id: uuid.UUID
    score_b_id: uuid.UUID
    score_a_generated_at: datetime
    score_b_generated_at: datetime
    overall_score_a: float | None
    overall_score_b: float | None
    overall_delta: float | None
    status_a: str
    status_b: str
    status_changed: bool
    component_deltas: list[ReliabilityComponentDelta] = field(default_factory=list)
    evidence_count_deltas: list[EvidenceCountDelta] = field(default_factory=list)
    newly_available_evidence: list[str] = field(default_factory=list)
    resolved_missing_evidence: list[str] = field(default_factory=list)
    still_missing_evidence: list[str] = field(default_factory=list)
    highlighted_changes: list[str] = field(default_factory=list)
    deterministic_explanation: str = ""


def _build_comparison_explanation(
    score_a: "StrategyReliabilityScore",
    score_b: "StrategyReliabilityScore",
    overall_delta: float | None,
    component_deltas: list[ReliabilityComponentDelta],
    resolved_missing: list[str],
    still_missing: list[str],
) -> str:
    """Build a deterministic, evidence-based explanation string.

    Uses hedged language: 'changed from', 'improved alongside', 'may reflect'.
    No causal claims. No AI language.
    """
    parts: list[str] = []

    # --- Overall score description ---
    a_score = score_a.overall_score
    b_score = score_b.overall_score
    if a_score is None and b_score is None:
        parts.append(
            "Both score snapshots have insufficient evidence for an overall score."
        )
    elif a_score is None and b_score is not None:
        parts.append(
            f"Reliability score became available at {b_score:.1f}/100 "
            f"(previously insufficient evidence)."
        )
    elif a_score is not None and b_score is None:
        parts.append(
            f"Reliability score declined to insufficient evidence "
            f"(was {a_score:.1f}/100)."
        )
    else:
        assert a_score is not None and b_score is not None
        delta = b_score - a_score
        if abs(delta) < 0.05:
            parts.append(
                f"Overall reliability score unchanged at {b_score:.1f}/100."
            )
        elif delta > 0:
            parts.append(
                f"Reliability score improved from {a_score:.1f} to {b_score:.1f} "
                f"({delta:+.1f} points)."
            )
        else:
            parts.append(
                f"Reliability score declined from {a_score:.1f} to {b_score:.1f} "
                f"({delta:+.1f} points)."
            )

    # --- Top component movers ---
    movers = [
        d for d in component_deltas
        if d.delta is not None and abs(d.delta) >= 1.0
    ]
    movers.sort(key=lambda x: abs(x.delta), reverse=True)  # type: ignore[arg-type]
    if movers:
        top3 = movers[:3]
        mover_strs = [
            f"{d.label} {d.delta:+.1f}" for d in top3
        ]
        parts.append(
            f"Largest component changes alongside this comparison: "
            f"{', '.join(mover_strs)}."
        )

    # --- Evidence notes ---
    if resolved_missing:
        resolved_preview = "; ".join(resolved_missing[:2])
        parts.append(
            f"{len(resolved_missing)} previously missing evidence item(s) noted as "
            f"addressed: {resolved_preview}."
        )
    if still_missing:
        parts.append(
            f"{len(still_missing)} evidence gap(s) remain unchanged."
        )

    # --- Components that became available ---
    newly_avail_comps = [
        d.label for d in component_deltas if d.became_available
    ]
    if newly_avail_comps:
        parts.append(
            f"Components now scored (were previously N/A): "
            f"{', '.join(newly_avail_comps)}."
        )

    # --- Status change ---
    if score_a.status != score_b.status:
        parts.append(
            f"Status changed from '{score_a.status.replace('_', ' ')}' "
            f"to '{score_b.status.replace('_', ' ')}'."
        )

    parts.append(
        "This is a deterministic score comparison based on stored evidence snapshots, "
        "not a causal claim."
    )

    return " ".join(parts)


def compare_reliability_scores(
    score_a: "StrategyReliabilityScore",
    score_b: "StrategyReliabilityScore",
) -> ReliabilityComparisonResult:
    """Deterministically compare two stored StrategyReliabilityScore rows.

    Score A is the earlier (baseline) snapshot; score B is the later (current).
    Returns a structured ReliabilityComparisonResult with deltas, evidence
    changes, and a plain-English explanation.

    No AI, no live data, no external calls.
    """
    # --- Overall delta ---
    if score_a.overall_score is not None and score_b.overall_score is not None:
        overall_delta: float | None = round(
            score_b.overall_score - score_a.overall_score, 1
        )
    else:
        overall_delta = None

    status_changed = score_a.status != score_b.status

    # --- Component deltas ---
    component_deltas: list[ReliabilityComponentDelta] = []
    for key in _ALL_COMPONENTS:
        val_a: float | None = getattr(score_a, key, None)
        val_b: float | None = getattr(score_b, key, None)

        if val_a is not None and val_b is not None:
            delta: float | None = round(val_b - val_a, 1)
            became_available = False
            became_null = False
        elif val_a is None and val_b is not None:
            delta = None
            became_available = True
            became_null = False
        elif val_a is not None and val_b is None:
            delta = None
            became_available = False
            became_null = True
        else:
            delta = None
            became_available = False
            became_null = False

        component_deltas.append(
            ReliabilityComponentDelta(
                component=key,
                label=_COMPONENT_DISPLAY_NAMES.get(key, key),
                score_a=val_a,
                score_b=val_b,
                delta=delta,
                became_available=became_available,
                became_null=became_null,
            )
        )

    # --- Evidence count deltas ---
    evidence_count_deltas: list[EvidenceCountDelta] = []
    counts_a: dict = score_a.evidence_counts_json or {}
    counts_b: dict = score_b.evidence_counts_json or {}
    all_keys = sorted(set(counts_a) | set(counts_b))
    for k in all_keys:
        ca = counts_a.get(k)
        cb = counts_b.get(k)
        delta_count: int | None = None
        if ca is not None and cb is not None:
            delta_count = cb - ca
        evidence_count_deltas.append(
            EvidenceCountDelta(
                key=k,
                count_a=ca,
                count_b=cb,
                delta=delta_count,
            )
        )

    # --- Missing evidence analysis ---
    missing_a: list[str] = score_a.missing_evidence_json or []
    missing_b: list[str] = score_b.missing_evidence_json or []
    set_a = set(missing_a)
    set_b = set(missing_b)

    resolved_missing_evidence = sorted(set_a - set_b)      # was missing, now absent from list
    still_missing_evidence = sorted(set_a & set_b)          # missing in both
    newly_available_evidence = sorted(set_b - set_a)        # appeared as missing in B

    # --- Highlighted changes ---
    highlighted: list[str] = []
    significant_movers = [
        d for d in component_deltas
        if d.delta is not None and abs(d.delta) >= 3.0
    ]
    significant_movers.sort(key=lambda x: abs(x.delta), reverse=True)  # type: ignore[arg-type]
    for d in significant_movers[:4]:
        direction = "▲" if (d.delta or 0) > 0 else "▼"
        highlighted.append(f"{direction} {d.label}: {d.delta:+.1f}")

    if status_changed:
        highlighted.append(
            f"Status: {score_a.status.replace('_', ' ')} → {score_b.status.replace('_', ' ')}"
        )

    if resolved_missing_evidence:
        highlighted.append(
            f"{len(resolved_missing_evidence)} evidence gap(s) addressed"
        )

    # --- Deterministic explanation ---
    explanation = _build_comparison_explanation(
        score_a=score_a,
        score_b=score_b,
        overall_delta=overall_delta,
        component_deltas=component_deltas,
        resolved_missing=resolved_missing_evidence,
        still_missing=still_missing_evidence,
    )

    return ReliabilityComparisonResult(
        score_a_id=score_a.id,
        score_b_id=score_b.id,
        score_a_generated_at=score_a.generated_at,
        score_b_generated_at=score_b.generated_at,
        overall_score_a=score_a.overall_score,
        overall_score_b=score_b.overall_score,
        overall_delta=overall_delta,
        status_a=score_a.status,
        status_b=score_b.status,
        status_changed=status_changed,
        component_deltas=component_deltas,
        evidence_count_deltas=evidence_count_deltas,
        newly_available_evidence=newly_available_evidence,
        resolved_missing_evidence=resolved_missing_evidence,
        still_missing_evidence=still_missing_evidence,
        highlighted_changes=highlighted,
        deterministic_explanation=explanation,
    )
