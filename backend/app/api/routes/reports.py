"""Reliability Report endpoints (M14).

  POST /api/reports/strategy/{strategy_id}            — generate strategy reliability report
  POST /api/reports/backtest-audit/{audit_id}         — generate backtest audit report
  POST /api/reports/dataset-snapshot/{snapshot_id}    — generate dataset health report
  GET  /api/reports                                   — list all reports (filtered/paginated)
  GET  /api/reports/{report_id}                       — get report detail with sections
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.core.constants import EventType, Severity
from app.db.session import get_db
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.backtest_audit import BacktestAudit
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.report import Report
from app.models.report_section import ReportSection
from app.models.strategy import Strategy
from app.schemas.reports import ReportDetail, ReportListResponse, ReportRead, ReportSectionRead
from app.services.reports import (
    generate_backtest_audit_report,
    generate_dataset_health_report,
    generate_strategy_reliability_report,
    persist_report,
)

router = APIRouter(tags=["reports"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_to_severity(score: int | None) -> str:
    """Map a 0–100 score to timeline event severity."""
    if score is None:
        return Severity.info
    if score < 50:
        return Severity.high
    if score < 75:
        return Severity.medium
    if score < 90:
        return Severity.low
    return Severity.info


def _build_report_detail(report: Report) -> ReportDetail:
    return ReportDetail(
        id=report.id,
        organization_id=report.organization_id,
        project_id=report.project_id,
        strategy_id=report.strategy_id,
        report_type=report.report_type,
        title=report.title,
        status=report.status,
        summary=report.summary,
        generated_at=report.generated_at,
        source_type=report.source_type,
        source_id=report.source_id,
        score=report.score,
        report_json=report.report_json,
        created_at=report.created_at,
        updated_at=report.updated_at,
        sections=[ReportSectionRead.model_validate(s) for s in report.sections],
    )


def _emit_timeline_event(
    report: Report,
    run_title: str,
    db: Session,
) -> None:
    """Create an audit timeline event for a generated report."""
    if report.organization_id is None:
        return

    sev = _score_to_severity(report.score)
    score_str = f"{report.score}/100" if report.score is not None else "n/a"

    db.add(AuditTimelineEvent(
        organization_id=report.organization_id,
        project_id=report.project_id,
        strategy_id=report.strategy_id,
        event_type=EventType.report_generated,
        title=run_title,
        description=(
            f"Report type: {report.report_type}. Score: {score_str}. "
            f"{len(report.sections)} section(s). "
            f"Source: {report.source_type} {report.source_id}."
        ),
        source_type="report",
        source_id=str(report.id),
        severity=sev,
        metadata_json={
            "report_id": str(report.id),
            "report_type": report.report_type,
            "score": report.score,
            "source_type": report.source_type,
            "source_id": report.source_id,
        },
    ))


# ---------------------------------------------------------------------------
# POST /api/reports/strategy/{strategy_id}
# ---------------------------------------------------------------------------

@router.post(
    "/reports/strategy/{strategy_id}",
    response_model=ReportDetail,
    status_code=201,
)
def generate_strategy_report(
    strategy_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ReportDetail:
    """Generate and store a strategy reliability report.

    Aggregates runs, audits, snapshots, alerts, and timeline events into a
    structured, evidence-backed reliability summary.

    Returns 404 if the strategy does not exist.
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    try:
        result = generate_strategy_reliability_report(strategy_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    report = persist_report(result, db)

    _emit_timeline_event(
        report,
        f"Strategy reliability report generated: {strategy.name} — score {report.score}/100"
        if report.score is not None
        else f"Strategy reliability report generated: {strategy.name}",
        db,
    )

    db.commit()
    db.refresh(report)

    # Reload with sections.
    report = (
        db.query(Report)
        .options(selectinload(Report.sections))
        .filter(Report.id == report.id)
        .first()
    )
    return _build_report_detail(report)


# ---------------------------------------------------------------------------
# POST /api/reports/backtest-audit/{audit_id}
# ---------------------------------------------------------------------------

@router.post(
    "/reports/backtest-audit/{audit_id}",
    response_model=ReportDetail,
    status_code=201,
)
def generate_backtest_report(
    audit_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ReportDetail:
    """Generate and store a backtest audit reliability report.

    Returns 404 if the audit does not exist.
    """
    audit = db.query(BacktestAudit).filter(BacktestAudit.id == audit_id).first()
    if audit is None:
        raise HTTPException(status_code=404, detail="Backtest audit not found")

    try:
        result = generate_backtest_audit_report(audit_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    report = persist_report(result, db)
    _emit_timeline_event(
        report,
        f"Backtest audit report generated — trust score {audit.trust_score}/100 ({audit.overall_status})",
        db,
    )

    db.commit()
    db.refresh(report)

    report = (
        db.query(Report)
        .options(selectinload(Report.sections))
        .filter(Report.id == report.id)
        .first()
    )
    return _build_report_detail(report)


# ---------------------------------------------------------------------------
# POST /api/reports/dataset-snapshot/{snapshot_id}
# ---------------------------------------------------------------------------

@router.post(
    "/reports/dataset-snapshot/{snapshot_id}",
    response_model=ReportDetail,
    status_code=201,
)
def generate_snapshot_report(
    snapshot_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ReportDetail:
    """Generate and store a dataset health report for a snapshot.

    Returns 404 if the snapshot does not exist.
    """
    snapshot = db.query(DatasetSnapshot).filter(DatasetSnapshot.id == snapshot_id).first()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Dataset snapshot not found")

    try:
        result = generate_dataset_health_report(snapshot_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    report = persist_report(result, db)
    _emit_timeline_event(
        report,
        f"Dataset health report generated — health score {snapshot.health_score}/100",
        db,
    )

    db.commit()
    db.refresh(report)

    report = (
        db.query(Report)
        .options(selectinload(Report.sections))
        .filter(Report.id == report.id)
        .first()
    )
    return _build_report_detail(report)


# ---------------------------------------------------------------------------
# GET /api/reports
# ---------------------------------------------------------------------------

@router.get("/reports", response_model=ReportListResponse)
def list_reports(
    report_type: str | None = Query(default=None, description="Filter by report_type"),
    strategy_id: uuid.UUID | None = Query(default=None, description="Filter by strategy_id"),
    source_type: str | None = Query(default=None, description="Filter by source_type"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ReportListResponse:
    """Return a paginated list of generated reports, newest first."""
    q = db.query(Report)
    if report_type is not None:
        q = q.filter(Report.report_type == report_type)
    if strategy_id is not None:
        q = q.filter(Report.strategy_id == strategy_id)
    if source_type is not None:
        q = q.filter(Report.source_type == source_type)

    total = q.count()
    reports = (
        q.order_by(Report.generated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return ReportListResponse(
        items=[ReportRead.model_validate(r) for r in reports],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# GET /api/reports/{report_id}
# ---------------------------------------------------------------------------

@router.get("/reports/{report_id}", response_model=ReportDetail)
def get_report(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ReportDetail:
    """Return a single report with all sections."""
    report = (
        db.query(Report)
        .options(selectinload(Report.sections))
        .filter(Report.id == report_id)
        .first()
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return _build_report_detail(report)
