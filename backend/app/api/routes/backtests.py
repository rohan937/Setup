"""Backtest Reality Check endpoints (M8):

  POST /api/strategy-runs/{run_id}/backtest-audit   — run + store audit (idempotent)
  GET  /api/strategy-runs/{run_id}/backtest-audit   — fetch latest audit for a run
  GET  /api/backtests/audits                        — global list of all audits
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.core.constants import EventType, RunType, Severity
from app.db.session import get_db
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.backtest_audit import BacktestAudit
from app.models.backtest_issue import BacktestIssue
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.strategy_run import StrategyRun
from app.models.strategy import Strategy
from app.schemas.backtest import BacktestAuditDetail, BacktestAuditListItem, BacktestIssueRead
from app.schemas.strategy import DataEvidenceSummary
from app.services.backtest_reality import run_backtest_audit

router = APIRouter(tags=["backtests"])

# Severity ordering for top-issue sorting.
_SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _worst_severity(severities: list[str]) -> str | None:
    for sev in _SEVERITY_ORDER:
        if sev in severities:
            return sev
    return None


def _compute_snapshot_stats(rows: list[dict] | None) -> dict:
    if not rows:
        return {"column_count": 0, "symbol_count": 0, "min_timestamp": None, "max_timestamp": None}
    all_keys: set[str] = set()
    for row in rows:
        all_keys.update(row.keys())
    symbols = {row.get("symbol") for row in rows if row.get("symbol") is not None}
    ts_list = sorted(str(row["timestamp"]) for row in rows if row.get("timestamp") is not None)
    return {
        "column_count": len(all_keys),
        "symbol_count": len(symbols),
        "min_timestamp": ts_list[0] if ts_list else None,
        "max_timestamp": ts_list[-1] if ts_list else None,
    }


def _build_evidence_summary(snap: DatasetSnapshot) -> DataEvidenceSummary:
    stats = _compute_snapshot_stats(snap.rows_json)
    issue_severities = [iss.severity for iss in (snap.issues or [])]
    return DataEvidenceSummary(
        id=snap.id,
        dataset_id=snap.dataset_id,
        dataset_name=snap.dataset.name if snap.dataset else "—",
        snapshot_label=snap.version_label,
        health_score=snap.health_score,
        row_count=snap.row_count,
        column_count=stats["column_count"],
        symbol_count=stats["symbol_count"],
        min_timestamp=stats["min_timestamp"],
        max_timestamp=stats["max_timestamp"],
        issue_count=len(issue_severities),
        worst_severity=_worst_severity(issue_severities),
    )


def _load_run_with_snapshot(
    run_id: uuid.UUID,
    db: Session,
) -> StrategyRun:
    """Load a StrategyRun with its linked snapshot eagerly loaded."""
    run = (
        db.query(StrategyRun)
        .options(
            selectinload(StrategyRun.snapshot)
            .selectinload(DatasetSnapshot.dataset),
            selectinload(StrategyRun.snapshot)
            .selectinload(DatasetSnapshot.issues),
            selectinload(StrategyRun.strategy)
            .selectinload(Strategy.project),
        )
        .filter(StrategyRun.id == run_id)
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Strategy run not found")
    return run


def _build_audit_detail(audit: BacktestAudit) -> BacktestAuditDetail:
    return BacktestAuditDetail(
        id=audit.id,
        strategy_run_id=audit.strategy_run_id,
        trust_score=audit.trust_score,
        lookahead_risk_score=audit.lookahead_risk_score,
        cost_realism_score=audit.cost_realism_score,
        fill_realism_score=audit.fill_realism_score,
        liquidity_realism_score=audit.liquidity_realism_score,
        borrow_realism_score=audit.borrow_realism_score,
        data_quality_score=audit.data_quality_score,
        overall_status=audit.overall_status,
        summary=audit.summary,
        created_at=audit.created_at,
        updated_at=audit.updated_at,
        issues=[BacktestIssueRead.model_validate(i) for i in audit.issues],
    )


def _build_list_item(audit: BacktestAudit) -> BacktestAuditListItem:
    run = audit.strategy_run
    strategy = run.strategy if run else None
    sorted_issues = sorted(
        audit.issues,
        key=lambda i: _SEVERITY_ORDER.index(i.severity) if i.severity in _SEVERITY_ORDER else len(_SEVERITY_ORDER),
    )
    return BacktestAuditListItem(
        id=audit.id,
        strategy_run_id=audit.strategy_run_id,
        trust_score=audit.trust_score,
        lookahead_risk_score=audit.lookahead_risk_score,
        cost_realism_score=audit.cost_realism_score,
        fill_realism_score=audit.fill_realism_score,
        liquidity_realism_score=audit.liquidity_realism_score,
        borrow_realism_score=audit.borrow_realism_score,
        data_quality_score=audit.data_quality_score,
        overall_status=audit.overall_status,
        summary=audit.summary,
        created_at=audit.created_at,
        updated_at=audit.updated_at,
        strategy_id=run.strategy_id if run else uuid.UUID(int=0),
        strategy_name=strategy.name if strategy else "—",
        run_name=run.run_name if run else "—",
        run_type=run.run_type if run else "—",
        issue_count=len(audit.issues),
        top_issues=[BacktestIssueRead.model_validate(i) for i in sorted_issues[:3]],
    )


# ---------------------------------------------------------------------------
# POST /api/strategy-runs/{run_id}/backtest-audit
# ---------------------------------------------------------------------------

@router.post(
    "/strategy-runs/{run_id}/backtest-audit",
    response_model=BacktestAuditDetail,
    status_code=201,
)
def create_backtest_audit(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> BacktestAuditDetail:
    """Run the deterministic backtest reality check and store the result.

    Idempotent — if an audit already exists for this run it is deleted and
    replaced with a fresh one (cascade-deletes the old issues).

    Returns 404 if the run does not exist.
    Returns 400 if the run type is 'live' (live runs cannot be audited).
    """
    run = _load_run_with_snapshot(run_id, db)

    # Live runs are excluded — auditing a live run doesn't make sense here.
    if run.run_type == RunType.live:
        raise HTTPException(
            status_code=400,
            detail="Backtest reality checks are not applicable to live runs.",
        )

    # Build data evidence summary from the linked snapshot (if any).
    evidence: DataEvidenceSummary | None = None
    if run.snapshot is not None:
        evidence = _build_evidence_summary(run.snapshot)

    # Run the deterministic audit engine.
    result = run_backtest_audit(run, data_evidence=evidence)

    # Deduplication: delete any existing audit for this run, then create fresh.
    existing = (
        db.query(BacktestAudit)
        .filter(BacktestAudit.strategy_run_id == run_id)
        .first()
    )
    if existing is not None:
        db.delete(existing)
        db.flush()

    now = datetime.now(timezone.utc)

    audit = BacktestAudit(
        strategy_run_id=run_id,
        trust_score=result.trust_score,
        lookahead_risk_score=result.lookahead_risk_score,
        cost_realism_score=result.cost_realism_score,
        fill_realism_score=result.fill_realism_score,
        liquidity_realism_score=result.liquidity_realism_score,
        borrow_realism_score=result.borrow_realism_score,
        data_quality_score=result.data_quality_score,
        overall_status=result.overall_status,
        summary=result.summary,
    )
    db.add(audit)
    db.flush()

    for issue in result.issues:
        db.add(BacktestIssue(
            backtest_audit_id=audit.id,
            issue_type=issue.issue_type,
            severity=issue.severity,
            title=issue.title,
            description=issue.description,
            evidence_json=issue.evidence_json,
            suggested_check=issue.suggested_check,
        ))

    # Audit timeline event.
    project = run.strategy.project if run.strategy else None
    if project is not None:
        # Severity escalates for weak/unreliable audits so they stand out in the timeline.
        audit_severity = Severity.info
        if result.trust_score < 25:
            audit_severity = Severity.high
        elif result.trust_score < 50:
            audit_severity = Severity.medium
        elif result.trust_score < 75:
            audit_severity = Severity.low
        db.add(AuditTimelineEvent(
            organization_id=project.organization_id,
            project_id=project.id,
            strategy_id=run.strategy_id,
            event_type=EventType.backtest_audited,
            title=f"Backtest audited: {run.run_name} — trust score {result.trust_score}/100",
            description=(
                f"Deterministic backtest reality check completed. "
                f"Trust score {result.trust_score}/100, status '{result.overall_status}'. "
                f"{len(result.issues)} issue(s) detected."
            ),
            source_type="backtest_audit",
            source_id=str(audit.id),
            severity=audit_severity,
            metadata_json={
                "run_id": str(run_id),
                "run_name": run.run_name,
                "trust_score": result.trust_score,
                "overall_status": result.overall_status,
                "issue_count": len(result.issues),
                "strategy_name": run.strategy.name if run.strategy else None,
            },
        ))

    db.commit()
    db.refresh(audit)

    # Re-load issues via the relationship (populated after commit).
    db.refresh(audit)
    # Reload with issues eagerly.
    audit = (
        db.query(BacktestAudit)
        .options(selectinload(BacktestAudit.issues))
        .filter(BacktestAudit.id == audit.id)
        .first()
    )

    return _build_audit_detail(audit)


# ---------------------------------------------------------------------------
# GET /api/strategy-runs/{run_id}/backtest-audit
# ---------------------------------------------------------------------------

@router.get(
    "/strategy-runs/{run_id}/backtest-audit",
    response_model=BacktestAuditDetail,
)
def get_backtest_audit(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> BacktestAuditDetail:
    """Return the latest backtest audit for a run, or 404 if none exists."""
    # Verify the run exists first.
    run_exists = db.query(StrategyRun.id).filter(StrategyRun.id == run_id).first()
    if run_exists is None:
        raise HTTPException(status_code=404, detail="Strategy run not found")

    audit = (
        db.query(BacktestAudit)
        .options(selectinload(BacktestAudit.issues))
        .filter(BacktestAudit.strategy_run_id == run_id)
        .order_by(BacktestAudit.created_at.desc())
        .first()
    )
    if audit is None:
        raise HTTPException(
            status_code=404, detail="No backtest audit found for this run"
        )

    return _build_audit_detail(audit)


# ---------------------------------------------------------------------------
# GET /api/backtests/audits
# ---------------------------------------------------------------------------

@router.get("/backtests/audits", response_model=list[BacktestAuditListItem])
def list_backtest_audits(
    db: Session = Depends(get_db),
) -> list[BacktestAuditListItem]:
    """Return all backtest audits, newest first, enriched with run/strategy context."""
    audits = (
        db.query(BacktestAudit)
        .options(
            selectinload(BacktestAudit.issues),
            selectinload(BacktestAudit.strategy_run).selectinload(StrategyRun.strategy),
        )
        .order_by(BacktestAudit.created_at.desc())
        .all()
    )
    return [_build_list_item(a) for a in audits]
