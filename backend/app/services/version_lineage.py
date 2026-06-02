"""Version lineage service (M35).

Computes per-version evidence coverage, transitions between versions,
and a summary for GET /api/strategies/{strategy_id}/version-lineage.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StrategyVersionLineageItemData:
    version_id: uuid.UUID
    version_label: str
    git_commit: str | None
    branch_name: str | None
    code_path: str | None
    signal_name: str | None
    signal_description: str | None
    created_at: datetime
    updated_at: datetime
    run_count: int
    backtest_run_count: int
    research_run_count: int
    paper_run_count: int
    live_run_count: int
    config_snapshot_count: int
    universe_snapshot_count: int
    signal_snapshot_count: int
    dataset_linked_run_count: int
    backtest_audit_count: int
    latest_run_at: datetime | None
    latest_config_snapshot_label: str | None
    latest_universe_snapshot_label: str | None
    latest_signal_snapshot_label: str | None
    latest_backtest_trust_score: float | None
    latest_data_health_score: float | None
    latest_signal_quality_score: float | None
    has_config: bool
    has_universe: bool
    has_signal: bool
    has_runs: bool
    has_dataset_linked_runs: bool
    has_backtest_audit: bool
    version_evidence_score: float
    lineage_status: str
    suggested_checks: list = field(default_factory=list)


@dataclass
class StrategyVersionTransitionData:
    from_version_label: str
    to_version_label: str
    created_at_delta_days: int
    git_commit_changed: bool
    branch_changed: bool
    signal_name_changed: bool
    config_hash_changed: bool | None
    universe_hash_changed: bool | None
    signal_hash_changed: bool | None


@dataclass
class StrategyVersionLineageSummaryData:
    strategy_id: uuid.UUID
    strategy_name: str
    version_count: int
    latest_version_label: str | None
    most_instrumented_version_id: uuid.UUID | None
    least_instrumented_version_id: uuid.UUID | None
    average_version_evidence_score: float | None
    versions_missing_config: int
    versions_missing_signal: int
    versions_missing_universe: int
    versions_without_runs: int
    deterministic_summary: str
    generated_at: datetime


@dataclass
class StrategyVersionLineageData:
    summary: StrategyVersionLineageSummaryData
    versions: list  # list[StrategyVersionLineageItemData], newest first
    transitions: list  # list[StrategyVersionTransitionData]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_version_item(version, strategy_id: uuid.UUID, db: Session) -> StrategyVersionLineageItemData:
    from app.models.backtest_audit import BacktestAudit
    from app.models.dataset_snapshot import DatasetSnapshot
    from app.models.signal_snapshot import SignalSnapshot
    from app.models.strategy_config_snapshot import StrategyConfigSnapshot
    from app.models.strategy_run import StrategyRun
    from app.models.universe_snapshot import UniverseSnapshot

    vid = version.id

    # Run counts by type
    run_type_rows = (
        db.query(StrategyRun.run_type, func.count(StrategyRun.id))
        .filter(StrategyRun.strategy_version_id == vid)
        .group_by(StrategyRun.run_type)
        .all()
    )
    run_type_map = {row[0]: row[1] for row in run_type_rows}
    total_runs = sum(run_type_map.values())

    # Dataset-linked runs
    ds_linked = (
        db.query(func.count(StrategyRun.id))
        .filter(
            StrategyRun.strategy_version_id == vid,
            StrategyRun.dataset_snapshot_id.isnot(None),
        )
        .scalar()
        or 0
    )

    # Config, universe, signal counts
    cfg_count = (
        db.query(func.count(StrategyConfigSnapshot.id))
        .filter(StrategyConfigSnapshot.strategy_version_id == vid)
        .scalar()
        or 0
    )
    uni_count = (
        db.query(func.count(UniverseSnapshot.id))
        .filter(UniverseSnapshot.strategy_version_id == vid)
        .scalar()
        or 0
    )
    sig_count = (
        db.query(func.count(SignalSnapshot.id))
        .filter(SignalSnapshot.strategy_version_id == vid)
        .scalar()
        or 0
    )

    # Backtest audit count (via StrategyRun)
    audit_count = (
        db.query(func.count(BacktestAudit.id))
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .filter(StrategyRun.strategy_version_id == vid)
        .scalar()
        or 0
    )

    # Latest evidence
    latest_run_at = (
        db.query(func.max(StrategyRun.created_at))
        .filter(StrategyRun.strategy_version_id == vid)
        .scalar()
    )

    latest_cfg = (
        db.query(StrategyConfigSnapshot.label)
        .filter(StrategyConfigSnapshot.strategy_version_id == vid)
        .order_by(StrategyConfigSnapshot.created_at.desc())
        .first()
    )

    latest_uni = (
        db.query(UniverseSnapshot.label)
        .filter(UniverseSnapshot.strategy_version_id == vid)
        .order_by(UniverseSnapshot.created_at.desc())
        .first()
    )

    latest_sig = (
        db.query(SignalSnapshot.label)
        .filter(SignalSnapshot.strategy_version_id == vid)
        .order_by(SignalSnapshot.created_at.desc())
        .first()
    )

    latest_sig_quality_row = (
        db.query(SignalSnapshot.quality_score)
        .filter(SignalSnapshot.strategy_version_id == vid)
        .order_by(SignalSnapshot.created_at.desc())
        .first()
    )

    latest_audit_row = (
        db.query(BacktestAudit.trust_score)
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .filter(StrategyRun.strategy_version_id == vid)
        .order_by(BacktestAudit.created_at.desc())
        .first()
    )

    latest_data_row = (
        db.query(DatasetSnapshot.health_score)
        .join(StrategyRun, StrategyRun.dataset_snapshot_id == DatasetSnapshot.id)
        .filter(StrategyRun.strategy_version_id == vid)
        .order_by(DatasetSnapshot.created_at.desc())
        .first()
    )

    # Evidence score
    score = 0.0
    if cfg_count > 0:
        score += 15
    if uni_count > 0:
        score += 15
    if sig_count > 0:
        score += 20
    if total_runs > 0:
        score += 20
    if ds_linked > 0:
        score += 15
    if audit_count > 0:
        score += 15

    # Lineage status
    if score >= 80:
        status = "well_instrumented"
    elif score >= 60:
        status = "usable"
    elif score >= 30:
        status = "partial"
    else:
        status = "under_instrumented"

    # Suggested checks
    checks: list[str] = []
    if cfg_count == 0:
        checks.append("Log a config snapshot for this version.")
    if uni_count == 0:
        checks.append("Link a universe snapshot to this version.")
    if sig_count == 0:
        checks.append("Log signal evidence for this version.")
    if total_runs == 0:
        checks.append("Log at least one run for this version.")
    if audit_count == 0 and total_runs > 0:
        checks.append("Run Backtest Reality Check for this version.")

    return StrategyVersionLineageItemData(
        version_id=vid,
        version_label=version.version_label,
        git_commit=version.git_commit,
        branch_name=version.branch_name,
        code_path=version.code_path,
        signal_name=version.signal_name,
        signal_description=version.signal_description,
        created_at=version.created_at,
        updated_at=version.updated_at,
        run_count=total_runs,
        backtest_run_count=run_type_map.get("backtest", 0),
        research_run_count=run_type_map.get("research", 0),
        paper_run_count=run_type_map.get("paper", 0),
        live_run_count=run_type_map.get("live", 0),
        config_snapshot_count=cfg_count,
        universe_snapshot_count=uni_count,
        signal_snapshot_count=sig_count,
        dataset_linked_run_count=ds_linked,
        backtest_audit_count=audit_count,
        latest_run_at=latest_run_at,
        latest_config_snapshot_label=latest_cfg[0] if latest_cfg else None,
        latest_universe_snapshot_label=latest_uni[0] if latest_uni else None,
        latest_signal_snapshot_label=latest_sig[0] if latest_sig else None,
        latest_backtest_trust_score=float(latest_audit_row[0]) if latest_audit_row else None,
        latest_data_health_score=float(latest_data_row[0]) if latest_data_row else None,
        latest_signal_quality_score=float(latest_sig_quality_row[0]) if latest_sig_quality_row else None,
        has_config=cfg_count > 0,
        has_universe=uni_count > 0,
        has_signal=sig_count > 0,
        has_runs=total_runs > 0,
        has_dataset_linked_runs=ds_linked > 0,
        has_backtest_audit=audit_count > 0,
        version_evidence_score=score,
        lineage_status=status,
        suggested_checks=checks,
    )


def _compute_transitions(versions_sorted_asc: list, db: Session) -> list[StrategyVersionTransitionData]:
    from app.models.signal_snapshot import SignalSnapshot
    from app.models.strategy_config_snapshot import StrategyConfigSnapshot
    from app.models.universe_snapshot import UniverseSnapshot

    def _nt(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    transitions: list[StrategyVersionTransitionData] = []
    for i in range(len(versions_sorted_asc) - 1):
        a = versions_sorted_asc[i]
        b = versions_sorted_asc[i + 1]

        cfg_a = (
            db.query(StrategyConfigSnapshot.config_hash)
            .filter(StrategyConfigSnapshot.strategy_version_id == a.id)
            .order_by(StrategyConfigSnapshot.created_at.desc())
            .first()
        )
        cfg_b = (
            db.query(StrategyConfigSnapshot.config_hash)
            .filter(StrategyConfigSnapshot.strategy_version_id == b.id)
            .order_by(StrategyConfigSnapshot.created_at.desc())
            .first()
        )
        uni_a = (
            db.query(UniverseSnapshot.universe_hash)
            .filter(UniverseSnapshot.strategy_version_id == a.id)
            .order_by(UniverseSnapshot.created_at.desc())
            .first()
        )
        uni_b = (
            db.query(UniverseSnapshot.universe_hash)
            .filter(UniverseSnapshot.strategy_version_id == b.id)
            .order_by(UniverseSnapshot.created_at.desc())
            .first()
        )
        sig_a = (
            db.query(SignalSnapshot.signal_hash)
            .filter(SignalSnapshot.strategy_version_id == a.id)
            .order_by(SignalSnapshot.created_at.desc())
            .first()
        )
        sig_b = (
            db.query(SignalSnapshot.signal_hash)
            .filter(SignalSnapshot.strategy_version_id == b.id)
            .order_by(SignalSnapshot.created_at.desc())
            .first()
        )

        at = _nt(a.created_at)
        bt = _nt(b.created_at)
        delta_days = int((bt - at).days) if (at and bt) else 0

        cfg_changed = None if (cfg_a is None or cfg_b is None) else (cfg_a[0] != cfg_b[0])
        uni_changed = None if (uni_a is None or uni_b is None) else (uni_a[0] != uni_b[0])
        sig_changed = None if (sig_a is None or sig_b is None) else (sig_a[0] != sig_b[0])

        transitions.append(
            StrategyVersionTransitionData(
                from_version_label=a.version_label,
                to_version_label=b.version_label,
                created_at_delta_days=delta_days,
                git_commit_changed=(a.git_commit != b.git_commit),
                branch_changed=(a.branch_name != b.branch_name),
                signal_name_changed=(a.signal_name != b.signal_name),
                config_hash_changed=cfg_changed,
                universe_hash_changed=uni_changed,
                signal_hash_changed=sig_changed,
            )
        )
    return transitions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_strategy_version_lineage(strategy_id: uuid.UUID, db: Session) -> StrategyVersionLineageData:
    """Compute the full version lineage for a strategy.

    Raises ValueError if the strategy is not found.
    """
    from app.models.strategy import Strategy
    from app.models.strategy_version import StrategyVersion

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    versions = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.created_at.desc())
        .all()
    )

    now = datetime.now(timezone.utc)
    version_items = [_compute_version_item(v, strategy_id, db) for v in versions]

    # Transitions need ascending order
    versions_asc = list(reversed(versions))
    transitions = _compute_transitions(versions_asc, db) if len(versions_asc) >= 2 else []

    # Summary
    scores = [vi.version_evidence_score for vi in version_items]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    most_instr = (
        max(version_items, key=lambda v: v.version_evidence_score).version_id
        if version_items
        else None
    )
    least_instr = (
        min(version_items, key=lambda v: v.version_evidence_score).version_id
        if version_items
        else None
    )
    # When there is only one version, don't mark it as both most and least
    if most_instr == least_instr and len(version_items) == 1:
        least_instr = None

    missing_cfg = sum(1 for v in version_items if not v.has_config)
    missing_sig = sum(1 for v in version_items if not v.has_signal)
    missing_uni = sum(1 for v in version_items if not v.has_universe)
    no_runs = sum(1 for v in version_items if not v.has_runs)

    most_instr_label = next(
        (v.version_label for v in version_items if v.version_id == most_instr), None
    )

    if version_items:
        latest_v_label = versions[0].version_label
        if len(version_items) == 1:
            summary = f"Strategy has 1 logged version ({latest_v_label})."
        else:
            summary = f"Strategy has {len(version_items)} logged versions."
        if most_instr_label:
            best_vi = next(v for v in version_items if v.version_id == most_instr)
            summary += f" {most_instr_label} is the most instrumented version (score: {best_vi.version_evidence_score:.0f}/100)."
        if missing_cfg > 0:
            summary += f" {missing_cfg} version(s) missing config snapshots."
        if missing_sig > 0:
            summary += f" {missing_sig} version(s) missing signal snapshots."
        if no_runs > 0:
            summary += f" {no_runs} version(s) have no logged runs."
    else:
        summary = "No strategy versions logged yet."

    lineage_summary = StrategyVersionLineageSummaryData(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        version_count=len(version_items),
        latest_version_label=versions[0].version_label if versions else None,
        most_instrumented_version_id=most_instr,
        least_instrumented_version_id=least_instr,
        average_version_evidence_score=avg_score,
        versions_missing_config=missing_cfg,
        versions_missing_signal=missing_sig,
        versions_missing_universe=missing_uni,
        versions_without_runs=no_runs,
        deterministic_summary=summary,
        generated_at=now,
    )

    return StrategyVersionLineageData(
        summary=lineage_summary,
        versions=version_items,
        transitions=transitions,
    )
