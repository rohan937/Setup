"""Strategy run history service (M29).

Loads per-run evidence (dataset, universe, signal, backtest audit) and computes
run health labels for a given strategy.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.backtest_audit import BacktestAudit
from app.models.backtest_issue import BacktestIssue
from app.models.data_quality_issue import DataQualityIssue
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.signal_snapshot import SignalSnapshot
from app.models.strategy_run import StrategyRun
from app.models.strategy_version import StrategyVersion
from app.models.universe_snapshot import UniverseSnapshot


# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]


def _worst_severity_from_list(severities: list[str]) -> str | None:
    for sev in _SEVERITY_ORDER:
        if sev in severities:
            return sev
    return None


def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StrategyVersionSummaryData:
    version_id: uuid.UUID
    version_label: str | None
    git_commit: str | None
    branch_name: str | None
    signal_name: str | None


@dataclass
class DatasetEvidenceData:
    dataset_snapshot_id: uuid.UUID
    dataset_name: str
    snapshot_label: str
    health_score: int
    issue_count: int
    worst_severity: str | None


@dataclass
class UniverseEvidenceData:
    universe_snapshot_id: uuid.UUID
    label: str
    symbol_count: int
    universe_hash: str


@dataclass
class SignalEvidenceData:
    signal_snapshot_id: uuid.UUID
    label: str
    signal_name: str | None
    quality_score: int
    missing_signal_count: int
    symbol_count: int
    mean_value: float | None
    stddev_value: float | None


@dataclass
class BacktestAuditData:
    audit_id: uuid.UUID
    trust_score: int
    overall_status: str
    issue_count: int
    high_critical_issue_count: int
    cost_fragility_level: str | None
    fill_realism_level: str | None


@dataclass
class StrategyRunHistoryItem:
    run_id: uuid.UUID
    run_name: str
    run_type: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    params_json: dict | None
    assumptions_json: dict | None
    metrics_json: dict | None
    notes: str | None
    strategy_version: StrategyVersionSummaryData | None
    dataset_evidence: DatasetEvidenceData | None
    universe_evidence: UniverseEvidenceData | None
    signal_evidence: SignalEvidenceData | None
    backtest_audit: BacktestAuditData | None
    has_dataset_evidence: bool
    has_universe_evidence: bool
    has_signal_evidence: bool
    has_backtest_audit: bool
    has_strategy_version: bool
    run_health_label: str


@dataclass
class StrategyRunHistorySummaryData:
    total_runs: int
    strong_count: int
    usable_count: int
    review_count: int
    weak_count: int
    insufficient_evidence_count: int
    runs_missing_dataset: int
    runs_missing_signal: int
    runs_missing_universe: int
    runs_missing_audit: int
    latest_run_at: datetime | None


# ---------------------------------------------------------------------------
# Health label computation
# ---------------------------------------------------------------------------

def _compute_run_health_label(item: StrategyRunHistoryItem) -> str:
    """Compute a deterministic health label for a run based on its evidence."""
    # No evidence at all
    if (
        not item.has_dataset_evidence
        and not item.has_signal_evidence
        and not item.has_backtest_audit
        and not item.has_strategy_version
    ):
        return "insufficient_evidence"

    # Weak: any key score below 50
    if item.backtest_audit is not None and item.backtest_audit.trust_score < 50:
        return "weak"
    if item.dataset_evidence is not None and item.dataset_evidence.health_score < 50:
        return "weak"
    if item.signal_evidence is not None and item.signal_evidence.quality_score < 50:
        return "weak"

    # Review: any key score below 75, or missing major evidence
    if item.backtest_audit is not None and item.backtest_audit.trust_score < 75:
        return "review"
    if item.dataset_evidence is not None and item.dataset_evidence.health_score < 75:
        return "review"
    if item.signal_evidence is not None and item.signal_evidence.quality_score < 75:
        return "review"
    if not item.has_dataset_evidence:
        return "review"
    if not item.has_backtest_audit:
        return "review"

    # Strong: all key scores >=80, has version and universe
    if (
        item.backtest_audit is not None
        and item.backtest_audit.trust_score >= 80
        and item.dataset_evidence is not None
        and item.dataset_evidence.health_score >= 80
        and (item.signal_evidence is None or item.signal_evidence.quality_score >= 80)
        and item.has_strategy_version
        and item.has_universe_evidence
    ):
        return "strong"

    return "usable"


# ---------------------------------------------------------------------------
# Evidence loader
# ---------------------------------------------------------------------------

def _load_run_evidence(run: StrategyRun, db: Session) -> StrategyRunHistoryItem:
    """Load all evidence for a single run and build a StrategyRunHistoryItem."""

    # Strategy version
    strategy_version: StrategyVersionSummaryData | None = None
    if run.strategy_version_id is not None:
        sv = db.query(StrategyVersion).filter(StrategyVersion.id == run.strategy_version_id).first()
        if sv is not None:
            strategy_version = StrategyVersionSummaryData(
                version_id=sv.id,
                version_label=sv.version_label,
                git_commit=sv.git_commit,
                branch_name=sv.branch_name,
                signal_name=sv.signal_name,
            )

    # Dataset evidence
    dataset_evidence: DatasetEvidenceData | None = None
    if run.dataset_snapshot_id is not None:
        ds = (
            db.query(DatasetSnapshot)
            .filter(DatasetSnapshot.id == run.dataset_snapshot_id)
            .first()
        )
        if ds is not None:
            dataset_obj = db.query(Dataset).filter(Dataset.id == ds.dataset_id).first()
            dataset_name = dataset_obj.name if dataset_obj else "—"
            # Count issues and worst severity
            issues = (
                db.query(DataQualityIssue)
                .filter(DataQualityIssue.snapshot_id == ds.id)
                .all()
            )
            issue_severities = [iss.severity for iss in issues]
            dataset_evidence = DatasetEvidenceData(
                dataset_snapshot_id=ds.id,
                dataset_name=dataset_name,
                snapshot_label=ds.version_label,
                health_score=ds.health_score,
                issue_count=len(issues),
                worst_severity=_worst_severity_from_list(issue_severities),
            )

    # Universe evidence
    universe_evidence: UniverseEvidenceData | None = None
    if run.universe_snapshot_id is not None:
        us = (
            db.query(UniverseSnapshot)
            .filter(UniverseSnapshot.id == run.universe_snapshot_id)
            .first()
        )
        if us is not None:
            universe_evidence = UniverseEvidenceData(
                universe_snapshot_id=us.id,
                label=us.label,
                symbol_count=us.symbol_count,
                universe_hash=us.universe_hash,
            )

    # Signal evidence
    signal_evidence: SignalEvidenceData | None = None
    if run.signal_snapshot_id is not None:
        ss = (
            db.query(SignalSnapshot)
            .filter(SignalSnapshot.id == run.signal_snapshot_id)
            .first()
        )
        if ss is not None:
            signal_evidence = SignalEvidenceData(
                signal_snapshot_id=ss.id,
                label=ss.label,
                signal_name=ss.signal_name,
                quality_score=ss.quality_score,
                missing_signal_count=ss.missing_signal_count,
                symbol_count=ss.symbol_count,
                mean_value=ss.mean_value,
                stddev_value=ss.stddev_value,
            )

    # Backtest audit
    backtest_audit: BacktestAuditData | None = None
    audit = (
        db.query(BacktestAudit)
        .filter(BacktestAudit.strategy_run_id == run.id)
        .order_by(BacktestAudit.created_at)
        .first()
    )
    if audit is not None:
        # Count issues
        all_issues = (
            db.query(BacktestIssue)
            .filter(BacktestIssue.backtest_audit_id == audit.id)
            .all()
        )
        issue_count = len(all_issues)
        high_critical_count = sum(
            1 for iss in all_issues if iss.severity in ("critical", "high")
        )

        # Extract fragility levels from JSON blobs
        cost_fragility_level: str | None = None
        fill_realism_level: str | None = None
        if isinstance(audit.fragility_summary_json, dict):
            cost_fragility_level = audit.fragility_summary_json.get("fragility_level")
        if isinstance(audit.fill_realism_json, dict):
            fill_realism_level = audit.fill_realism_json.get("fragility_level")

        backtest_audit = BacktestAuditData(
            audit_id=audit.id,
            trust_score=audit.trust_score,
            overall_status=audit.overall_status,
            issue_count=issue_count,
            high_critical_issue_count=high_critical_count,
            cost_fragility_level=cost_fragility_level,
            fill_realism_level=fill_realism_level,
        )

    has_dataset_evidence = dataset_evidence is not None
    has_universe_evidence = universe_evidence is not None
    has_signal_evidence = signal_evidence is not None
    has_backtest_audit = backtest_audit is not None
    has_strategy_version = strategy_version is not None

    # Build partial item to compute health label
    item = StrategyRunHistoryItem(
        run_id=run.id,
        run_name=run.run_name,
        run_type=run.run_type,
        status=run.status,
        started_at=_normalize_dt(run.started_at),
        completed_at=_normalize_dt(run.completed_at),
        created_at=_normalize_dt(run.created_at) or datetime.now(timezone.utc),
        params_json=run.params_json,
        assumptions_json=run.assumptions_json,
        metrics_json=run.metrics_json,
        notes=run.notes,
        strategy_version=strategy_version,
        dataset_evidence=dataset_evidence,
        universe_evidence=universe_evidence,
        signal_evidence=signal_evidence,
        backtest_audit=backtest_audit,
        has_dataset_evidence=has_dataset_evidence,
        has_universe_evidence=has_universe_evidence,
        has_signal_evidence=has_signal_evidence,
        has_backtest_audit=has_backtest_audit,
        has_strategy_version=has_strategy_version,
        run_health_label="",  # filled below
    )
    item.run_health_label = _compute_run_health_label(item)
    return item


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_strategy_run_history(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    run_type: str | None = None,
    status: str | None = None,
    evidence_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[StrategyRunHistoryItem], StrategyRunHistorySummaryData]:
    """Return enriched run history for a strategy with optional filtering.

    Returns a paginated list and a summary computed across all filtered runs.
    """
    q = (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(StrategyRun.created_at.desc())
    )

    if run_type is not None:
        q = q.filter(StrategyRun.run_type == run_type)
    if status is not None:
        q = q.filter(StrategyRun.status == status)

    runs = q.all()

    # Load evidence for all matching runs
    all_items: list[StrategyRunHistoryItem] = [_load_run_evidence(r, db) for r in runs]

    # Apply evidence_status filter post-load
    if evidence_status is not None:
        if evidence_status == "complete":
            all_items = [
                i for i in all_items
                if i.has_dataset_evidence and i.has_signal_evidence
                and i.has_universe_evidence and i.has_backtest_audit
            ]
        elif evidence_status == "missing_dataset":
            all_items = [i for i in all_items if not i.has_dataset_evidence]
        elif evidence_status == "missing_signal":
            all_items = [i for i in all_items if not i.has_signal_evidence]
        elif evidence_status == "missing_universe":
            all_items = [i for i in all_items if not i.has_universe_evidence]
        elif evidence_status == "missing_audit":
            all_items = [i for i in all_items if not i.has_backtest_audit]
        elif evidence_status == "review":
            all_items = [i for i in all_items if i.run_health_label == "review"]
        elif evidence_status == "weak":
            all_items = [i for i in all_items if i.run_health_label == "weak"]

    # Compute summary across ALL filtered items (before pagination)
    total_runs = len(all_items)
    strong_count = sum(1 for i in all_items if i.run_health_label == "strong")
    usable_count = sum(1 for i in all_items if i.run_health_label == "usable")
    review_count = sum(1 for i in all_items if i.run_health_label == "review")
    weak_count = sum(1 for i in all_items if i.run_health_label == "weak")
    insufficient_evidence_count = sum(
        1 for i in all_items if i.run_health_label == "insufficient_evidence"
    )
    runs_missing_dataset = sum(1 for i in all_items if not i.has_dataset_evidence)
    runs_missing_signal = sum(1 for i in all_items if not i.has_signal_evidence)
    runs_missing_universe = sum(1 for i in all_items if not i.has_universe_evidence)
    runs_missing_audit = sum(1 for i in all_items if not i.has_backtest_audit)

    latest_run_at: datetime | None = None
    if all_items:
        latest_run_at = max(
            (i.created_at for i in all_items if i.created_at is not None),
            default=None,
        )

    summary = StrategyRunHistorySummaryData(
        total_runs=total_runs,
        strong_count=strong_count,
        usable_count=usable_count,
        review_count=review_count,
        weak_count=weak_count,
        insufficient_evidence_count=insufficient_evidence_count,
        runs_missing_dataset=runs_missing_dataset,
        runs_missing_signal=runs_missing_signal,
        runs_missing_universe=runs_missing_universe,
        runs_missing_audit=runs_missing_audit,
        latest_run_at=latest_run_at,
    )

    # Paginate
    page = all_items[offset : offset + limit]
    return page, summary
