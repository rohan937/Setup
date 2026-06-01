"""Strategy comparison service (M20).

Compares 2–8 strategies side-by-side using existing logged evidence.
Deterministic — no AI, no live market data, no external calls.

Language policy:
  Use: "better evidenced", "higher current reliability score",
       "more complete instrumentation", "requires review"
  Never: "better strategy", "more profitable", "should trade",
          "alpha is stronger", "buy/sell"
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.backtest_audit import BacktestAudit
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.report import Report
from app.models.signal_snapshot import SignalSnapshot
from app.models.strategy import Strategy
from app.models.strategy_config_snapshot import StrategyConfigSnapshot
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.models.strategy_run import StrategyRun
from app.models.universe_snapshot import UniverseSnapshot


# ---------------------------------------------------------------------------
# Gap keys → human-readable labels
# ---------------------------------------------------------------------------

GAP_LABELS: dict[str, str] = {
    "no_runs": "No runs logged",
    "no_dataset_evidence": "No runs with linked dataset evidence",
    "no_backtest_audit": "No backtest audit computed",
    "no_signal_evidence": "No signal snapshots logged",
    "no_universe_evidence": "No universe snapshots logged",
    "no_config_snapshot": "No config snapshots logged",
    "open_high_alerts": "Open high/critical alerts present",
    "insufficient_reliability_score": "Insufficient evidence for reliability score",
    "stale_reliability_score": "Reliability score is stale (>30 days old)",
}

_SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class StrategyEvidenceCoverageData:
    run_count: int
    backtest_run_count: int
    research_run_count: int
    paper_run_count: int
    live_run_count: int
    dataset_snapshot_linked_count: int
    backtest_audit_count: int
    config_snapshot_count: int
    universe_snapshot_count: int
    signal_snapshot_count: int
    open_alert_count: int
    report_count: int
    timeline_event_count: int
    evidence_coverage_score: float


@dataclass
class StrategyComparisonItemData:
    strategy_id: uuid.UUID
    name: str
    slug: str
    asset_class: str
    status: str
    overall_reliability_score: float | None
    reliability_status: str | None
    reliability_generated_at: datetime | None
    strategy_activity_score: float | None
    data_evidence_score: float | None
    backtest_trust_score: float | None
    config_evidence_score: float | None
    universe_evidence_score: float | None
    signal_evidence_score: float | None
    alert_penalty_score: float | None
    report_coverage_score: float | None
    missing_evidence: list[str]
    suggested_checks: list[str]
    coverage: StrategyEvidenceCoverageData
    latest_run_at: datetime | None
    latest_backtest_trust_score: float | None
    latest_data_health_score: float | None
    latest_signal_quality_score: float | None
    latest_report_score: float | None
    highest_severity_open_alert: str | None
    gaps: list[str] = field(default_factory=list)


@dataclass
class StrategyComparisonRankingItemData:
    rank: int
    strategy_id: uuid.UUID
    name: str
    score: float | None
    score_label: str
    status: str


@dataclass
class StrategyComparisonResult:
    strategies: list[StrategyComparisonItemData]
    ranked_by_reliability: list[StrategyComparisonRankingItemData]
    ranked_by_evidence_coverage: list[StrategyComparisonRankingItemData]
    strongest_strategy_id: uuid.UUID | None
    weakest_strategy_id: uuid.UUID | None
    shared_gaps: list[str] = field(default_factory=list)
    differentiators: list[str] = field(default_factory=list)
    deterministic_explanation: str = ""
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _highest_severity(severities: list[str]) -> str | None:
    for sev in _SEVERITY_ORDER:
        if sev in severities:
            return sev
    return None


def _compute_coverage_score(cov: StrategyEvidenceCoverageData) -> float:
    """Weighted evidence coverage score (0–100).

    Each present evidence type contributes a fixed weight.
    Max 100 when all types are present:
      runs present          +10
      backtest runs         +10
      dataset evidence      +20
      backtest audits       +20
      signal snapshots      +15
      universe snapshots    +10
      config snapshots      +10
      reports               + 5
    """
    score = 0.0
    if cov.run_count > 0:
        score += 10.0
    if cov.backtest_run_count > 0:
        score += 10.0
    if cov.dataset_snapshot_linked_count > 0:
        score += 20.0
    if cov.backtest_audit_count > 0:
        score += 20.0
    if cov.signal_snapshot_count > 0:
        score += 15.0
    if cov.universe_snapshot_count > 0:
        score += 10.0
    if cov.config_snapshot_count > 0:
        score += 10.0
    if cov.report_count > 0:
        score += 5.0
    return score


def _compute_gaps(
    item: StrategyComparisonItemData,
    cov: StrategyEvidenceCoverageData,
    now: datetime,
) -> list[str]:
    """Generate deterministic gap labels from evidence coverage."""
    gaps: list[str] = []
    if cov.run_count == 0:
        gaps.append("no_runs")
    if cov.dataset_snapshot_linked_count == 0:
        gaps.append("no_dataset_evidence")
    if cov.backtest_audit_count == 0:
        gaps.append("no_backtest_audit")
    if cov.signal_snapshot_count == 0:
        gaps.append("no_signal_evidence")
    if cov.universe_snapshot_count == 0:
        gaps.append("no_universe_evidence")
    if cov.config_snapshot_count == 0:
        gaps.append("no_config_snapshot")
    if item.highest_severity_open_alert in ("high", "critical"):
        gaps.append("open_high_alerts")
    if item.reliability_status in (None, "insufficient_evidence"):
        gaps.append("insufficient_reliability_score")
    elif item.reliability_generated_at is not None:
        gen_at = item.reliability_generated_at
        # Normalise to offset-aware for comparison (SQLite stores naive UTC)
        if gen_at.tzinfo is None:
            gen_at = gen_at.replace(tzinfo=timezone.utc)
        if (now - gen_at) > timedelta(days=30):
            gaps.append("stale_reliability_score")
    return gaps


def _load_strategy_evidence(
    strategy: Strategy,
    db: Session,
    now: datetime,
) -> StrategyComparisonItemData:
    """Gather evidence counts and latest evidence points for one strategy."""
    sid = strategy.id

    # ── B. Latest reliability score ───────────────────────────────────────────
    latest_score: StrategyReliabilityScore | None = (
        db.query(StrategyReliabilityScore)
        .filter(StrategyReliabilityScore.strategy_id == sid)
        .order_by(StrategyReliabilityScore.generated_at.desc())
        .first()
    )

    # ── C. Evidence coverage counts ───────────────────────────────────────────
    run_type_rows = (
        db.query(StrategyRun.run_type, func.count(StrategyRun.id))
        .filter(StrategyRun.strategy_id == sid)
        .group_by(StrategyRun.run_type)
        .all()
    )
    run_type_map: dict[str, int] = {row[0]: row[1] for row in run_type_rows}
    total_runs = sum(run_type_map.values())

    dataset_linked = (
        db.query(func.count(StrategyRun.id))
        .filter(
            StrategyRun.strategy_id == sid,
            StrategyRun.dataset_snapshot_id.isnot(None),
        )
        .scalar()
    ) or 0

    backtest_audit_count = (
        db.query(func.count(BacktestAudit.id))
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .filter(StrategyRun.strategy_id == sid)
        .scalar()
    ) or 0

    config_count = (
        db.query(func.count(StrategyConfigSnapshot.id))
        .filter(StrategyConfigSnapshot.strategy_id == sid)
        .scalar()
    ) or 0

    universe_count = (
        db.query(func.count(UniverseSnapshot.id))
        .filter(UniverseSnapshot.strategy_id == sid)
        .scalar()
    ) or 0

    signal_count = (
        db.query(func.count(SignalSnapshot.id))
        .filter(SignalSnapshot.strategy_id == sid)
        .scalar()
    ) or 0

    # Alert.strategy_id is String(36) — compare via str()
    open_alert_count = (
        db.query(func.count(Alert.id))
        .filter(
            Alert.strategy_id == str(sid),
            Alert.status.in_(["open", "acknowledged", "snoozed"]),
        )
        .scalar()
    ) or 0

    # Report.strategy_id is Uuid(as_uuid=True) — direct compare
    report_count = (
        db.query(func.count(Report.id))
        .filter(Report.strategy_id == sid)
        .scalar()
    ) or 0

    # AuditTimelineEvent.strategy_id is Uuid(as_uuid=True)
    timeline_count = (
        db.query(func.count(AuditTimelineEvent.id))
        .filter(AuditTimelineEvent.strategy_id == sid)
        .scalar()
    ) or 0

    # ── D. Best/worst evidence points ─────────────────────────────────────────
    latest_run_at = (
        db.query(func.max(StrategyRun.created_at))
        .filter(StrategyRun.strategy_id == sid)
        .scalar()
    )

    latest_audit_row = (
        db.query(BacktestAudit.trust_score)
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .filter(StrategyRun.strategy_id == sid)
        .order_by(BacktestAudit.created_at.desc())
        .first()
    )
    latest_backtest_trust: float | None = (
        float(latest_audit_row[0]) if latest_audit_row else None
    )

    latest_health_row = (
        db.query(DatasetSnapshot.health_score)
        .join(StrategyRun, StrategyRun.dataset_snapshot_id == DatasetSnapshot.id)
        .filter(StrategyRun.strategy_id == sid)
        .order_by(DatasetSnapshot.created_at.desc())
        .first()
    )
    latest_data_health: float | None = (
        float(latest_health_row[0]) if latest_health_row else None
    )

    latest_signal_row = (
        db.query(SignalSnapshot.quality_score)
        .filter(SignalSnapshot.strategy_id == sid)
        .order_by(SignalSnapshot.created_at.desc())
        .first()
    )
    latest_signal_quality: float | None = (
        float(latest_signal_row[0]) if latest_signal_row else None
    )

    latest_report_row = (
        db.query(Report.score)
        .filter(
            Report.strategy_id == sid,
            Report.score.isnot(None),
        )
        .order_by(Report.generated_at.desc())
        .first()
    )
    latest_report_score_val: float | None = (
        float(latest_report_row[0]) if latest_report_row else None
    )

    open_sev_rows = (
        db.query(Alert.severity)
        .filter(
            Alert.strategy_id == str(sid),
            Alert.status.in_(["open", "acknowledged", "snoozed"]),
        )
        .all()
    )
    highest_sev = _highest_severity([row[0] for row in open_sev_rows])

    # ── Assemble coverage ─────────────────────────────────────────────────────
    cov = StrategyEvidenceCoverageData(
        run_count=total_runs,
        backtest_run_count=run_type_map.get("backtest", 0),
        research_run_count=run_type_map.get("research", 0),
        paper_run_count=run_type_map.get("paper", 0),
        live_run_count=run_type_map.get("live", 0),
        dataset_snapshot_linked_count=dataset_linked,
        backtest_audit_count=backtest_audit_count,
        config_snapshot_count=config_count,
        universe_snapshot_count=universe_count,
        signal_snapshot_count=signal_count,
        open_alert_count=open_alert_count,
        report_count=report_count,
        timeline_event_count=timeline_count,
        evidence_coverage_score=0.0,
    )
    cov.evidence_coverage_score = _compute_coverage_score(cov)

    # ── Assemble item ─────────────────────────────────────────────────────────
    item = StrategyComparisonItemData(
        strategy_id=sid,
        name=strategy.name,
        slug=strategy.slug,
        asset_class=strategy.asset_class,
        status=strategy.status,
        overall_reliability_score=(
            latest_score.overall_score if latest_score else None
        ),
        reliability_status=latest_score.status if latest_score else None,
        reliability_generated_at=(
            latest_score.generated_at if latest_score else None
        ),
        strategy_activity_score=(
            latest_score.strategy_activity_score if latest_score else None
        ),
        data_evidence_score=(
            latest_score.data_evidence_score if latest_score else None
        ),
        backtest_trust_score=(
            latest_score.backtest_trust_score if latest_score else None
        ),
        config_evidence_score=(
            latest_score.config_evidence_score if latest_score else None
        ),
        universe_evidence_score=(
            latest_score.universe_evidence_score if latest_score else None
        ),
        signal_evidence_score=(
            latest_score.signal_evidence_score if latest_score else None
        ),
        alert_penalty_score=(
            latest_score.alert_penalty_score if latest_score else None
        ),
        report_coverage_score=(
            latest_score.report_coverage_score if latest_score else None
        ),
        missing_evidence=(
            list(latest_score.missing_evidence_json or []) if latest_score else []
        ),
        suggested_checks=(
            list(latest_score.suggested_checks_json or []) if latest_score else []
        ),
        coverage=cov,
        latest_run_at=latest_run_at,
        latest_backtest_trust_score=latest_backtest_trust,
        latest_data_health_score=latest_data_health,
        latest_signal_quality_score=latest_signal_quality,
        latest_report_score=latest_report_score_val,
        highest_severity_open_alert=highest_sev,
        gaps=[],
    )
    item.gaps = _compute_gaps(item, cov, now)
    return item


def _build_differentiators(items: list[StrategyComparisonItemData]) -> list[str]:
    """Generate bullet-point differentiators for coverage differences."""
    diffs: list[str] = []

    def _maybe_add(getter, label: str) -> None:
        pairs = [(item.name, getter(item)) for item in items]
        pairs.sort(key=lambda x: x[1], reverse=True)
        if len(pairs) >= 2 and pairs[0][1] > pairs[-1][1]:
            diffs.append(
                f"{pairs[0][0]}: {pairs[0][1]} {label}; "
                f"{pairs[-1][0]}: {pairs[-1][1]}"
            )

    _maybe_add(
        lambda x: x.coverage.dataset_snapshot_linked_count,
        "run(s) with linked dataset evidence",
    )
    _maybe_add(
        lambda x: x.coverage.backtest_audit_count,
        "backtest audit(s)",
    )
    _maybe_add(
        lambda x: x.coverage.signal_snapshot_count,
        "signal snapshot(s)",
    )
    _maybe_add(
        lambda x: x.coverage.universe_snapshot_count,
        "universe snapshot(s)",
    )
    _maybe_add(
        lambda x: x.coverage.config_snapshot_count,
        "config snapshot(s)",
    )
    return diffs[:5]


def _build_explanation(
    items: list[StrategyComparisonItemData],
    strongest_id: uuid.UUID | None,
    weakest_id: uuid.UUID | None,
) -> str:
    """Build a deterministic, hedged explanation. No causal claims, no investment language."""
    parts: list[str] = []

    if strongest_id:
        s = next((i for i in items if i.strategy_id == strongest_id), None)
        if s and s.overall_reliability_score is not None:
            parts.append(
                f"{s.name} has the highest current reliability score at "
                f"{s.overall_reliability_score:.1f}/100 ({s.reliability_status})."
            )

    if weakest_id and weakest_id != strongest_id:
        w = next((i for i in items if i.strategy_id == weakest_id), None)
        if w and w.overall_reliability_score is not None:
            parts.append(
                f"{w.name} has the lowest current reliability score at "
                f"{w.overall_reliability_score:.1f}/100 ({w.reliability_status})."
            )

    # Under-instrumented strategies (≥3 gaps)
    under = [i for i in items if len(i.gaps) >= 3]
    for item in under:
        gap_labels = [GAP_LABELS.get(g, g) for g in item.gaps[:3]]
        parts.append(
            f"{item.name} is under-instrumented: {'; '.join(gap_labels)}."
        )

    # Strategies without a reliability score
    unscored = [
        i for i in items
        if i.reliability_status in (None, "insufficient_evidence")
    ]
    if unscored:
        names = ", ".join(i.name for i in unscored)
        verb = "has" if len(unscored) == 1 else "have"
        parts.append(
            f"{names} {verb} insufficient evidence for a reliability score."
        )

    parts.append(
        "This comparison is based only on logged QuantFidelity evidence, "
        "not expected trading performance or investment suitability."
    )
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compare_strategies(
    strategy_ids: list[uuid.UUID],
    db: Session,
    *,
    include_archived: bool = False,
) -> StrategyComparisonResult:
    """Compare 2–8 strategies using existing logged evidence.

    Returns a :class:`StrategyComparisonResult` dataclass with per-strategy
    evidence summaries, reliability rankings, coverage rankings, shared gaps,
    differentiators, and a deterministic explanation.

    Raises :exc:`ValueError` for:
    - Fewer than 2 or more than 8 strategy IDs.
    - Unknown strategy IDs.
    - Archived strategies when ``include_archived=False``.

    No AI, no live market data, no external calls.
    """
    if len(strategy_ids) < 2:
        raise ValueError("At least 2 strategy IDs required for comparison.")
    if len(strategy_ids) > 8:
        raise ValueError("At most 8 strategy IDs may be compared at once.")

    # Deduplicate while preserving input order
    seen: set[uuid.UUID] = set()
    unique_ids: list[uuid.UUID] = []
    for sid in strategy_ids:
        if sid not in seen:
            seen.add(sid)
            unique_ids.append(sid)

    strategies = (
        db.query(Strategy).filter(Strategy.id.in_(unique_ids)).all()
    )
    found_ids = {s.id for s in strategies}
    missing = [str(sid) for sid in unique_ids if sid not in found_ids]
    if missing:
        raise ValueError(f"Strategy IDs not found: {missing}")

    if not include_archived:
        archived_names = [s.name for s in strategies if s.status == "archived"]
        if archived_names:
            raise ValueError(
                "Archived strategies cannot be compared without include_archived=true: "
                f"{archived_names}"
            )

    strat_map = {s.id: s for s in strategies}
    ordered = [strat_map[sid] for sid in unique_ids]

    now = datetime.now(timezone.utc)
    items = [_load_strategy_evidence(s, db, now) for s in ordered]

    # ── Rank by reliability (scored first → desc score, then null/insufficient)
    def _rel_key(item: StrategyComparisonItemData) -> tuple:
        if item.overall_reliability_score is not None and item.reliability_status not in (
            None,
            "insufficient_evidence",
        ):
            return (0, -item.overall_reliability_score, item.name)
        return (1, 0.0, item.name)

    reliability_sorted = sorted(items, key=_rel_key)
    ranked_by_reliability = [
        StrategyComparisonRankingItemData(
            rank=i + 1,
            strategy_id=item.strategy_id,
            name=item.name,
            score=item.overall_reliability_score,
            score_label=(
                f"{item.overall_reliability_score:.1f}"
                if item.overall_reliability_score is not None
                else "—"
            ),
            status=item.reliability_status or "no_score",
        )
        for i, item in enumerate(reliability_sorted)
    ]

    # ── Rank by evidence coverage (desc coverage score)
    coverage_sorted = sorted(
        items,
        key=lambda x: (-x.coverage.evidence_coverage_score, x.name),
    )
    ranked_by_evidence = [
        StrategyComparisonRankingItemData(
            rank=i + 1,
            strategy_id=item.strategy_id,
            name=item.name,
            score=item.coverage.evidence_coverage_score,
            score_label=f"{item.coverage.evidence_coverage_score:.0f}/100",
            status=(
                "complete"
                if item.coverage.evidence_coverage_score >= 80
                else "partial"
                if item.coverage.evidence_coverage_score >= 40
                else "minimal"
            ),
        )
        for i, item in enumerate(coverage_sorted)
    ]

    # ── Strongest / weakest by reliability ───────────────────────────────────
    scored = [
        i
        for i in items
        if i.overall_reliability_score is not None
        and i.reliability_status not in (None, "insufficient_evidence")
    ]
    strongest_id: uuid.UUID | None = None
    weakest_id: uuid.UUID | None = None
    if scored:
        strongest_id = max(
            scored, key=lambda x: x.overall_reliability_score or 0.0
        ).strategy_id
        weakest_id = min(
            scored, key=lambda x: x.overall_reliability_score or 0.0
        ).strategy_id
        if strongest_id == weakest_id:
            weakest_id = None

    # ── Shared gaps ───────────────────────────────────────────────────────────
    if items:
        gap_sets = [set(item.gaps) for item in items]
        shared: set[str] = gap_sets[0].intersection(*gap_sets[1:])
    else:
        shared = set()
    shared_gaps = sorted(shared)

    differentiators = _build_differentiators(items)
    explanation = _build_explanation(items, strongest_id, weakest_id)

    return StrategyComparisonResult(
        strategies=items,
        ranked_by_reliability=ranked_by_reliability,
        ranked_by_evidence_coverage=ranked_by_evidence,
        strongest_strategy_id=strongest_id,
        weakest_strategy_id=weakest_id,
        shared_gaps=shared_gaps,
        differentiators=differentiators,
        deterministic_explanation=explanation,
        generated_at=now,
    )
