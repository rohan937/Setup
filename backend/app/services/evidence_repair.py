"""M75 Evidence Repair + Strategy Management service.

Deterministic helpers that power the web repair flows:
  - enumerate linkable evidence (repair options) for a strategy
  - link existing evidence to a run (partial, validated)
  - update / archive a strategy

No AI, no external data, no trading actions. Pure DB operations over existing
evidence objects.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session


class RepairNotFound(Exception):
    """Raised when a strategy/run/evidence object does not exist (→ 404)."""


class RepairValidation(Exception):
    """Raised when a link is invalid or incompatible (→ 400)."""


# ---------------------------------------------------------------------------
# Repair options
# ---------------------------------------------------------------------------

def get_repair_options(strategy_id: uuid.UUID, db: Session) -> dict:
    """Return linkable evidence objects + runs that are missing links."""
    from app.models.strategy import Strategy
    from app.models.strategy_run import StrategyRun
    from app.models.strategy_version import StrategyVersion
    from app.models.signal_snapshot import SignalSnapshot
    from app.models.universe_snapshot import UniverseSnapshot
    from app.models.dataset_snapshot import DatasetSnapshot
    from app.models.dataset import Dataset

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise RepairNotFound("Strategy not found")

    # --- Linked-run counts (for context) ----------------------------------
    def _link_counts(col) -> dict:
        rows = (
            db.query(col, func.count(StrategyRun.id))
            .filter(StrategyRun.strategy_id == strategy_id, col.isnot(None))
            .group_by(col)
            .all()
        )
        return {str(k): v for k, v in rows if k is not None}

    ds_counts = _link_counts(StrategyRun.dataset_snapshot_id)
    sig_counts = _link_counts(StrategyRun.signal_snapshot_id)
    uni_counts = _link_counts(StrategyRun.universe_snapshot_id)

    # --- Dataset snapshots (compatible = same project as strategy) ---------
    ds_rows = (
        db.query(DatasetSnapshot, Dataset.name)
        .join(Dataset, DatasetSnapshot.dataset_id == Dataset.id)
        .filter(Dataset.project_id == strategy.project_id)
        .order_by(DatasetSnapshot.created_at.desc())
        .all()
    )
    dataset_snapshots = []
    for i, (snap, dname) in enumerate(ds_rows):
        dataset_snapshots.append({
            "id": str(snap.id),
            "label": f"{dname} · {snap.version_label}",
            "created_at": snap.created_at,
            "quality_score": snap.health_score,
            "row_count": snap.row_count,
            "symbol_count": None,
            "linked_run_count": ds_counts.get(str(snap.id), 0),
            "recommended": i == 0,
            "detail": f"Health {snap.health_score} · {snap.row_count} rows",
        })

    # --- Signal snapshots --------------------------------------------------
    sig_rows = (
        db.query(SignalSnapshot)
        .filter(SignalSnapshot.strategy_id == strategy_id)
        .order_by(SignalSnapshot.created_at.desc())
        .all()
    )
    signal_snapshots = []
    for i, snap in enumerate(sig_rows):
        signal_snapshots.append({
            "id": str(snap.id),
            "label": snap.label,
            "created_at": snap.created_at,
            "quality_score": snap.quality_score,
            "row_count": snap.row_count,
            "symbol_count": snap.symbol_count,
            "linked_run_count": sig_counts.get(str(snap.id), 0),
            "recommended": i == 0,
            "detail": f"Quality {snap.quality_score} · {snap.symbol_count} symbols",
        })

    # --- Universe snapshots ------------------------------------------------
    uni_rows = (
        db.query(UniverseSnapshot)
        .filter(UniverseSnapshot.strategy_id == strategy_id)
        .order_by(UniverseSnapshot.created_at.desc())
        .all()
    )
    universe_snapshots = []
    for i, snap in enumerate(uni_rows):
        universe_snapshots.append({
            "id": str(snap.id),
            "label": snap.label,
            "created_at": snap.created_at,
            "quality_score": None,
            "row_count": None,
            "symbol_count": snap.symbol_count,
            "linked_run_count": uni_counts.get(str(snap.id), 0),
            "recommended": i == 0,
            "detail": f"{snap.symbol_count} symbols",
        })

    # --- Strategy versions -------------------------------------------------
    ver_rows = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.created_at.desc())
        .all()
    )
    strategy_versions = []
    for i, ver in enumerate(ver_rows):
        strategy_versions.append({
            "id": str(ver.id),
            "label": ver.version_label,
            "created_at": ver.created_at,
            "quality_score": None,
            "row_count": None,
            "symbol_count": None,
            "linked_run_count": None,
            "recommended": i == 0,
            "detail": ver.git_commit[:10] if ver.git_commit else None,
        })

    # --- Runs missing links ------------------------------------------------
    runs = (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(StrategyRun.created_at.desc())
        .all()
    )
    runs_missing_links = []
    for run in runs:
        missing = []
        if run.dataset_snapshot_id is None:
            missing.append("dataset")
        if run.signal_snapshot_id is None:
            missing.append("signal")
        if run.universe_snapshot_id is None:
            missing.append("universe")
        if run.strategy_version_id is None:
            missing.append("version")
        if not missing:
            continue
        runs_missing_links.append({
            "run_id": str(run.id),
            "run_name": run.run_name,
            "run_type": run.run_type,
            "created_at": run.created_at,
            "missing": missing,
            "dataset_snapshot_id": str(run.dataset_snapshot_id) if run.dataset_snapshot_id else None,
            "signal_snapshot_id": str(run.signal_snapshot_id) if run.signal_snapshot_id else None,
            "universe_snapshot_id": str(run.universe_snapshot_id) if run.universe_snapshot_id else None,
            "strategy_version_id": str(run.strategy_version_id) if run.strategy_version_id else None,
        })

    return {
        "strategy_id": str(strategy_id),
        "strategy_name": strategy.name,
        "dataset_snapshots": dataset_snapshots,
        "signal_snapshots": signal_snapshots,
        "universe_snapshots": universe_snapshots,
        "strategy_versions": strategy_versions,
        "runs_missing_links": runs_missing_links,
    }


# ---------------------------------------------------------------------------
# Link run evidence (partial, validated)
# ---------------------------------------------------------------------------

def link_run_evidence(
    strategy_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    dataset_snapshot_id: uuid.UUID | None = None,
    signal_snapshot_id: uuid.UUID | None = None,
    universe_snapshot_id: uuid.UUID | None = None,
    strategy_version_id: uuid.UUID | None = None,
    db: Session,
) -> dict:
    """Link existing evidence to a run. Returns a summary dict.

    The caller is responsible for committing, emitting a timeline event, and
    invalidating any reliability snapshot cache.
    """
    from app.models.strategy import Strategy
    from app.models.strategy_run import StrategyRun
    from app.models.strategy_version import StrategyVersion
    from app.models.signal_snapshot import SignalSnapshot
    from app.models.universe_snapshot import UniverseSnapshot
    from app.models.dataset_snapshot import DatasetSnapshot
    from app.models.dataset import Dataset

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise RepairNotFound("Strategy not found")

    run = db.query(StrategyRun).filter(StrategyRun.id == run_id).first()
    if run is None:
        raise RepairNotFound("Run not found")
    if run.strategy_id != strategy_id:
        raise RepairValidation("This run does not belong to the specified strategy.")

    linked_fields: list[str] = []
    labels: dict[str, str | None] = {}

    if dataset_snapshot_id is not None:
        row = (
            db.query(DatasetSnapshot, Dataset.name, Dataset.project_id)
            .join(Dataset, DatasetSnapshot.dataset_id == Dataset.id)
            .filter(DatasetSnapshot.id == dataset_snapshot_id)
            .first()
        )
        if row is None:
            raise RepairNotFound("Dataset snapshot not found")
        snap, dname, project_id = row
        if project_id != strategy.project_id:
            raise RepairValidation(
                "That dataset snapshot belongs to a different project and cannot be linked."
            )
        run.dataset_snapshot_id = dataset_snapshot_id
        linked_fields.append("dataset_snapshot_id")
        labels["dataset_snapshot_label"] = f"{dname} · {snap.version_label}"

    if signal_snapshot_id is not None:
        snap = db.query(SignalSnapshot).filter(SignalSnapshot.id == signal_snapshot_id).first()
        if snap is None:
            raise RepairNotFound("Signal snapshot not found")
        if snap.strategy_id != strategy_id:
            raise RepairValidation(
                "That signal snapshot belongs to a different strategy and cannot be linked."
            )
        run.signal_snapshot_id = signal_snapshot_id
        linked_fields.append("signal_snapshot_id")
        labels["signal_snapshot_label"] = snap.label

    if universe_snapshot_id is not None:
        snap = db.query(UniverseSnapshot).filter(UniverseSnapshot.id == universe_snapshot_id).first()
        if snap is None:
            raise RepairNotFound("Universe snapshot not found")
        if snap.strategy_id != strategy_id:
            raise RepairValidation(
                "That universe snapshot belongs to a different strategy and cannot be linked."
            )
        run.universe_snapshot_id = universe_snapshot_id
        linked_fields.append("universe_snapshot_id")
        labels["universe_snapshot_label"] = snap.label

    if strategy_version_id is not None:
        ver = db.query(StrategyVersion).filter(StrategyVersion.id == strategy_version_id).first()
        if ver is None:
            raise RepairNotFound("Strategy version not found")
        if ver.strategy_id != strategy_id:
            raise RepairValidation(
                "That strategy version belongs to a different strategy and cannot be linked."
            )
        run.strategy_version_id = strategy_version_id
        linked_fields.append("strategy_version_id")
        labels["strategy_version_label"] = ver.version_label

    if not linked_fields:
        raise RepairValidation("No evidence links were provided.")

    db.flush()

    return {
        "run_id": str(run.id),
        "strategy_id": str(strategy_id),
        "run_name": run.run_name,
        "run_type": run.run_type,
        "status": run.status,
        "dataset_snapshot_id": str(run.dataset_snapshot_id) if run.dataset_snapshot_id else None,
        "signal_snapshot_id": str(run.signal_snapshot_id) if run.signal_snapshot_id else None,
        "universe_snapshot_id": str(run.universe_snapshot_id) if run.universe_snapshot_id else None,
        "strategy_version_id": str(run.strategy_version_id) if run.strategy_version_id else None,
        "dataset_snapshot_label": labels.get("dataset_snapshot_label"),
        "signal_snapshot_label": labels.get("signal_snapshot_label"),
        "universe_snapshot_label": labels.get("universe_snapshot_label"),
        "strategy_version_label": labels.get("strategy_version_label"),
        "linked_fields": linked_fields,
        "updated_at": run.updated_at,
        "message": f"Linked {len(linked_fields)} evidence object(s) to “{run.run_name}”.",
    }


# ---------------------------------------------------------------------------
# Strategy management
# ---------------------------------------------------------------------------

_VALID_STATUSES = {"active", "paused", "archived", "draft"}
_VALID_ASSET_CLASSES = {
    "equity", "etf", "future", "option", "fx", "crypto", "rate", "commodity", "other",
}


def update_strategy(
    strategy_id: uuid.UUID,
    *,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
    asset_class: str | None = None,
    db: Session,
) -> dict:
    from app.models.strategy import Strategy

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise RepairNotFound("Strategy not found")

    changed: list[str] = []
    if name is not None:
        name = name.strip()
        if not name:
            raise RepairValidation("Strategy name cannot be empty.")
        strategy.name = name
        changed.append("name")
    if description is not None:
        strategy.description = description
        changed.append("description")
    if status is not None:
        if status not in _VALID_STATUSES:
            raise RepairValidation(f"Invalid status '{status}'.")
        strategy.status = status
        changed.append("status")
    if asset_class is not None:
        if asset_class not in _VALID_ASSET_CLASSES:
            raise RepairValidation(f"Invalid asset class '{asset_class}'.")
        strategy.asset_class = asset_class
        changed.append("asset_class")

    if not changed:
        raise RepairValidation("No fields provided to update.")

    db.flush()

    return _strategy_summary(
        strategy,
        message=f"Updated {', '.join(changed)}.",
    )


def archive_strategy(strategy_id: uuid.UUID, db: Session) -> dict:
    """Soft-delete: set status to archived. Hard delete is intentionally avoided
    because strategies fan out into many cascade relationships (runs, versions,
    snapshots, audits, reports, alerts, timeline)."""
    from app.models.strategy import Strategy

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise RepairNotFound("Strategy not found")

    already = strategy.status == "archived"
    strategy.status = "archived"
    db.flush()

    return _strategy_summary(
        strategy,
        archived=True,
        message=(
            "Strategy was already archived." if already
            else f"Archived strategy “{strategy.name}”."
        ),
    )


def _strategy_summary(strategy, *, archived: bool = False, message: str = "") -> dict:
    return {
        "id": str(strategy.id),
        "name": strategy.name,
        "slug": strategy.slug,
        "description": strategy.description,
        "asset_class": strategy.asset_class,
        "status": strategy.status,
        "archived": archived or strategy.status == "archived",
        "message": message,
    }
