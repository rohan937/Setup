"""Project routes — M28 adds project health endpoints.

GET /api/projects                    — list all projects
GET /api/projects/health             — list project health snapshots
GET /api/projects/{project_id}       — get a single project
GET /api/projects/{project_id}/health — get health snapshot for one project
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.project import Project
from app.schemas.project import ProjectOut
from app.schemas.project_health import ProjectHealthListResponse, ProjectHealthRead
from app.services.project_health import (
    ProjectHealthSnapshot,
    compute_project_health,
    get_projects_health,
)

router = APIRouter(tags=["projects"])


def _snap_to_schema(snap: ProjectHealthSnapshot) -> ProjectHealthRead:
    return ProjectHealthRead(
        project_id=snap.project_id,
        project_name=snap.project_name,
        organization_id=snap.organization_id,
        health_score=snap.health_score,
        health_status=snap.health_status,
        strategy_count=snap.strategy_count,
        healthy_strategy_count=snap.healthy_strategy_count,
        watch_strategy_count=snap.watch_strategy_count,
        review_strategy_count=snap.review_strategy_count,
        critical_strategy_count=snap.critical_strategy_count,
        insufficient_evidence_strategy_count=snap.insufficient_evidence_strategy_count,
        average_strategy_health_score=snap.average_strategy_health_score,
        average_reliability_score=snap.average_reliability_score,
        average_evidence_coverage_score=snap.average_evidence_coverage_score,
        open_alert_count=snap.open_alert_count,
        high_critical_alert_count=snap.high_critical_alert_count,
        recent_failed_ingestion_count=snap.recent_failed_ingestion_count,
        latest_activity_at=snap.latest_activity_at,
        primary_concern=snap.primary_concern,
        suggested_checks=snap.suggested_checks,
        generated_at=snap.generated_at,
    )


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    return db.query(Project).order_by(Project.created_at).all()


# IMPORTANT: /projects/health MUST be declared before /projects/{project_id}
# so the literal "health" segment is not captured as a project_id UUID.


@router.get("/projects/health", response_model=ProjectHealthListResponse)
def list_projects_health(
    organization_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ProjectHealthListResponse:
    """Return a paginated list of project health snapshots."""
    snaps, total = get_projects_health(
        db,
        organization_id=organization_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return ProjectHealthListResponse(
        items=[_snap_to_schema(s) for s in snaps],
        total=total,
        limit=limit,
        offset=offset,
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/projects/{project_id}/health", response_model=ProjectHealthRead)
def get_project_health_endpoint(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ProjectHealthRead:
    """Return a health snapshot for a single project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    snap = compute_project_health(project_id, db)
    return _snap_to_schema(snap)
