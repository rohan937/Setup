"""Dataset endpoints:
  POST /api/datasets
  GET  /api/datasets
  GET  /api/datasets/{dataset_id}
  POST /api/datasets/{dataset_id}/snapshots
  GET  /api/datasets/{dataset_id}/snapshots
  GET  /api/dataset-snapshots/{snapshot_id}
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.core.constants import (
    DatasetSourceType,
    DatasetType,
    EventType,
    Severity,
)
from app.db.session import get_db
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.data_quality_issue import DataQualityIssue
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.project import Project
from app.schemas.dataset import (
    DataQualityIssueRead,
    DatasetCreate,
    DatasetDetail,
    DatasetRead,
    DatasetSnapshotCreate,
    DatasetSnapshotDetail,
    DatasetSnapshotRead,
)
from app.schemas.dataset_comparison import DatasetSnapshotComparisonResponse
from app.services.data_quality import analyze_snapshot
from app.services.dataset_comparison import compare_snapshots

router = APIRouter(tags=["datasets"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# POST /api/datasets
# ---------------------------------------------------------------------------

@router.post("/datasets", response_model=DatasetRead, status_code=201)
def create_dataset(
    body: DatasetCreate, db: Session = Depends(get_db)
) -> DatasetRead:
    try:
        DatasetType(body.dataset_type)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid dataset_type '{body.dataset_type}'",
        )

    try:
        DatasetSourceType(body.source_type)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid source_type '{body.source_type}'",
        )

    project = db.query(Project).filter(Project.id == body.project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    dataset = Dataset(
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        dataset_type=body.dataset_type,
        source_type=body.source_type,
    )
    db.add(dataset)
    db.flush()

    db.commit()
    db.refresh(dataset)

    return DatasetRead(
        id=dataset.id,
        project_id=dataset.project_id,
        name=dataset.name,
        description=dataset.description,
        dataset_type=dataset.dataset_type,
        source_type=dataset.source_type,
        snapshot_count=0,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
    )


# ---------------------------------------------------------------------------
# GET /api/datasets
# ---------------------------------------------------------------------------

@router.get("/datasets", response_model=list[DatasetRead])
def list_datasets(db: Session = Depends(get_db)) -> list[DatasetRead]:
    # Count snapshots per dataset in one query.
    snapshot_counts: dict[str, int] = {
        str(row.dataset_id): row.cnt
        for row in db.query(
            DatasetSnapshot.dataset_id,
            func.count(DatasetSnapshot.id).label("cnt"),
        ).group_by(DatasetSnapshot.dataset_id).all()
    }

    datasets = (
        db.query(Dataset)
        .order_by(Dataset.created_at.desc())
        .all()
    )

    return [
        DatasetRead(
            id=d.id,
            project_id=d.project_id,
            name=d.name,
            description=d.description,
            dataset_type=d.dataset_type,
            source_type=d.source_type,
            snapshot_count=snapshot_counts.get(str(d.id), 0),
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in datasets
    ]


# ---------------------------------------------------------------------------
# GET /api/datasets/{dataset_id}
# ---------------------------------------------------------------------------

@router.get("/datasets/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: str, db: Session = Depends(get_db)) -> DatasetDetail:
    dataset = (
        db.query(Dataset)
        .options(selectinload(Dataset.snapshots))
        .filter(Dataset.id == uuid.UUID(dataset_id))
        .first()
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return DatasetDetail(
        id=dataset.id,
        project_id=dataset.project_id,
        name=dataset.name,
        description=dataset.description,
        dataset_type=dataset.dataset_type,
        source_type=dataset.source_type,
        snapshot_count=len(dataset.snapshots),
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        snapshots=[
            DatasetSnapshotRead(
                id=s.id,
                dataset_id=s.dataset_id,
                version_label=s.version_label,
                row_count=s.row_count,
                health_score=s.health_score,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in dataset.snapshots
        ],
    )


# ---------------------------------------------------------------------------
# POST /api/datasets/{dataset_id}/snapshots
# ---------------------------------------------------------------------------

@router.post(
    "/datasets/{dataset_id}/snapshots",
    response_model=DatasetSnapshotDetail,
    status_code=201,
)
def create_snapshot(
    dataset_id: str, body: DatasetSnapshotCreate, db: Session = Depends(get_db)
) -> DatasetSnapshotDetail:
    dataset = (
        db.query(Dataset)
        .options(selectinload(Dataset.project))
        .filter(Dataset.id == uuid.UUID(dataset_id))
        .first()
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Run deterministic data quality analysis (pure function, no DB).
    summary = analyze_snapshot(body.rows)

    snapshot = DatasetSnapshot(
        dataset_id=dataset.id,
        version_label=body.version_label,
        row_count=summary.row_count,
        health_score=summary.health_score,
        rows_json=body.rows,
    )
    db.add(snapshot)
    db.flush()

    # Persist quality issues.
    issue_records: list[DataQualityIssue] = []
    for spec in summary.issues:
        issue = DataQualityIssue(
            snapshot_id=snapshot.id,
            issue_type=spec.issue_type,
            severity=spec.severity,
            field_name=spec.field_name,
            row_index=spec.row_index,
            detail=spec.detail,
        )
        db.add(issue)
        issue_records.append(issue)

    db.flush()

    # Audit timeline event.
    org_id = dataset.project.organization_id
    project_id = dataset.project_id

    severity = Severity.info
    if summary.health_score < 50:
        severity = Severity.high
    elif summary.health_score < 80:
        severity = Severity.medium

    event = AuditTimelineEvent(
        organization_id=org_id,
        project_id=project_id,
        strategy_id=None,
        event_type=EventType.dataset_snapshot_uploaded,
        title=(
            f"Dataset snapshot uploaded: {dataset.name} · "
            f"{body.version_label} ({summary.row_count} rows, "
            f"health {summary.health_score}/100)"
        ),
        description=(
            f"{len(summary.issues)} data quality issue(s) detected. "
            f"Health score: {summary.health_score}/100."
        ),
        source_type="dataset_snapshot",
        source_id=str(snapshot.id),
        severity=severity,
        event_time=_utcnow(),
        metadata_json={
            "dataset_id": str(dataset.id),
            "dataset_name": dataset.name,
            "snapshot_id": str(snapshot.id),
            "version_label": body.version_label,
            "row_count": summary.row_count,
            "health_score": summary.health_score,
            "issue_count": len(summary.issues),
        },
    )
    db.add(event)
    db.commit()
    db.refresh(snapshot)

    return DatasetSnapshotDetail(
        id=snapshot.id,
        dataset_id=snapshot.dataset_id,
        version_label=snapshot.version_label,
        row_count=snapshot.row_count,
        health_score=snapshot.health_score,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
        issues=[
            DataQualityIssueRead(
                id=iss.id,
                snapshot_id=iss.snapshot_id,
                issue_type=iss.issue_type,
                severity=iss.severity,
                field_name=iss.field_name,
                row_index=iss.row_index,
                detail=iss.detail,
                created_at=iss.created_at,
            )
            for iss in issue_records
        ],
    )


# ---------------------------------------------------------------------------
# GET /api/datasets/{dataset_id}/snapshots
# ---------------------------------------------------------------------------

@router.get(
    "/datasets/{dataset_id}/snapshots",
    response_model=list[DatasetSnapshotRead],
)
def list_snapshots(
    dataset_id: str, db: Session = Depends(get_db)
) -> list[DatasetSnapshotRead]:
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == uuid.UUID(dataset_id))
        .first()
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    snapshots = (
        db.query(DatasetSnapshot)
        .filter(DatasetSnapshot.dataset_id == uuid.UUID(dataset_id))
        .order_by(DatasetSnapshot.created_at.desc())
        .all()
    )
    return [
        DatasetSnapshotRead(
            id=s.id,
            dataset_id=s.dataset_id,
            version_label=s.version_label,
            row_count=s.row_count,
            health_score=s.health_score,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in snapshots
    ]


# ---------------------------------------------------------------------------
# GET /api/dataset-snapshots/{snapshot_id}
# ---------------------------------------------------------------------------

@router.get(
    "/dataset-snapshots/{snapshot_id}",
    response_model=DatasetSnapshotDetail,
)
def get_snapshot(
    snapshot_id: str, db: Session = Depends(get_db)
) -> DatasetSnapshotDetail:
    snapshot = (
        db.query(DatasetSnapshot)
        .options(selectinload(DatasetSnapshot.issues))
        .filter(DatasetSnapshot.id == uuid.UUID(snapshot_id))
        .first()
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return DatasetSnapshotDetail(
        id=snapshot.id,
        dataset_id=snapshot.dataset_id,
        version_label=snapshot.version_label,
        row_count=snapshot.row_count,
        health_score=snapshot.health_score,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
        issues=[
            DataQualityIssueRead(
                id=iss.id,
                snapshot_id=iss.snapshot_id,
                issue_type=iss.issue_type,
                severity=iss.severity,
                field_name=iss.field_name,
                row_index=iss.row_index,
                detail=iss.detail,
                created_at=iss.created_at,
            )
            for iss in snapshot.issues
        ],
    )


# ---------------------------------------------------------------------------
# GET /api/datasets/{dataset_id}/snapshots/compare
# ---------------------------------------------------------------------------

@router.get(
    "/datasets/{dataset_id}/snapshots/compare",
    response_model=DatasetSnapshotComparisonResponse,
)
def compare_dataset_snapshots(
    dataset_id: str,
    snapshot_a_id: str = Query(..., description="ID of snapshot A (baseline)"),
    snapshot_b_id: str = Query(..., description="ID of snapshot B (comparison target)"),
    db: Session = Depends(get_db),
) -> DatasetSnapshotComparisonResponse:
    """Compare two snapshots from the same dataset.

    Returns a deterministic, structured diff across schema, symbol coverage,
    timestamp range, data health, and row-level value revisions.

    Rules:
    - Both snapshots must exist and belong to the specified dataset.
    - Comparing a snapshot to itself is allowed and returns an empty diff.
    - No AI, no causality claims — observed differences only.
    """
    # Validate dataset exists.
    try:
        ds_uuid = uuid.UUID(dataset_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Dataset not found")

    dataset = db.query(Dataset).filter(Dataset.id == ds_uuid).first()
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Parse snapshot IDs.
    try:
        snap_a_uuid = uuid.UUID(snapshot_a_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Snapshot A not found")

    try:
        snap_b_uuid = uuid.UUID(snapshot_b_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Snapshot B not found")

    # Load snapshots with issues eagerly.
    snap_a = (
        db.query(DatasetSnapshot)
        .options(selectinload(DatasetSnapshot.issues))
        .filter(DatasetSnapshot.id == snap_a_uuid)
        .first()
    )
    if snap_a is None:
        raise HTTPException(status_code=404, detail="Snapshot A not found")

    snap_b = (
        db.query(DatasetSnapshot)
        .options(selectinload(DatasetSnapshot.issues))
        .filter(DatasetSnapshot.id == snap_b_uuid)
        .first()
    )
    if snap_b is None:
        raise HTTPException(status_code=404, detail="Snapshot B not found")

    # Both snapshots must belong to the specified dataset.
    if snap_a.dataset_id != ds_uuid:
        raise HTTPException(
            status_code=400,
            detail="Snapshot A does not belong to the specified dataset",
        )
    if snap_b.dataset_id != ds_uuid:
        raise HTTPException(
            status_code=400,
            detail="Snapshot B does not belong to the specified dataset",
        )

    return compare_snapshots(snap_a, snap_b, snap_a.issues, snap_b.issues)
