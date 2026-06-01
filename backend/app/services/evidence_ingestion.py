"""Evidence Ingestion Bundle service (M22).

Accepts a structured bundle of evidence sections and persists them all in a
single transaction, in dependency order:

  strategy_version → config_snapshot → universe_snapshot → signal_snapshot
  → dataset → dataset_snapshot → strategy_run → [actions]

Exactly one bundle-level AuditTimelineEvent is created at the end
(event_type = evidence_bundle_ingested).

The service does NOT call db.commit() — the caller (route handler) does.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.constants import EventType, Severity
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.backtest_audit import BacktestAudit
from app.models.backtest_issue import BacktestIssue
from app.models.data_quality_issue import DataQualityIssue
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.signal_snapshot import SignalSnapshot
from app.models.strategy_config_snapshot import StrategyConfigSnapshot
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.models.strategy_run import StrategyRun
from app.models.strategy_version import StrategyVersion
from app.models.universe_snapshot import UniverseSnapshot
from app.schemas.evidence_ingestion import EvidenceBundleRequest
from app.services.config_snapshots import compute_config_hash, count_params, count_assumptions
from app.services.data_quality import analyze_snapshot
from app.services.universe_snapshots import normalize_symbols, compute_universe_hash
from app.services.signal_snapshots import (
    normalize_signal_rows,
    summarize_signal_snapshot,
    compute_signal_hash,
)


@dataclass
class EvidenceBundleResult:
    strategy_id: uuid.UUID
    created_count: int
    reused_count: int
    actions_run: list[str]
    objects: dict  # {section_name: {"id": UUID, "name": str, "type": str, "status": str} | None}
    alerts_generated: int
    warnings: list[str]
    summary: str
    timeline_events_created: int
    generated_at: datetime


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _add_event(
    db: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    strategy_id: uuid.UUID,
    event_type: str,
    title: str,
    description: str | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    severity: str = Severity.info,
    metadata_json: dict | None = None,
) -> None:
    db.add(AuditTimelineEvent(
        organization_id=org_id,
        project_id=project_id,
        strategy_id=strategy_id,
        event_type=event_type,
        title=title,
        description=description,
        source_type=source_type,
        source_id=source_id,
        severity=severity,
        metadata_json=metadata_json,
    ))


def _resolve_version_id(
    strategy_id: uuid.UUID,
    label: str | None,
    db: Session,
) -> uuid.UUID | None:
    """Look up a StrategyVersion by label for a strategy. Returns None if label is None."""
    if label is None:
        return None
    sv = (
        db.query(StrategyVersion)
        .filter(
            StrategyVersion.strategy_id == strategy_id,
            StrategyVersion.version_label == label,
        )
        .first()
    )
    return sv.id if sv else None


def _resolve_universe_snapshot_id(
    strategy_id: uuid.UUID,
    label: str | None,
    db: Session,
) -> uuid.UUID | None:
    if label is None:
        return None
    us = (
        db.query(UniverseSnapshot)
        .filter(
            UniverseSnapshot.strategy_id == strategy_id,
            UniverseSnapshot.label == label,
        )
        .first()
    )
    return us.id if us else None


def _resolve_dataset_snapshot_id(
    dataset_id: uuid.UUID,
    label: str | None,
    db: Session,
) -> uuid.UUID | None:
    if label is None:
        return None
    ds = (
        db.query(DatasetSnapshot)
        .filter(
            DatasetSnapshot.dataset_id == dataset_id,
            DatasetSnapshot.version_label == label,
        )
        .first()
    )
    return ds.id if ds else None


def _resolve_signal_snapshot_id(
    strategy_id: uuid.UUID,
    label: str | None,
    db: Session,
) -> uuid.UUID | None:
    if label is None:
        return None
    ss = (
        db.query(SignalSnapshot)
        .filter(
            SignalSnapshot.strategy_id == strategy_id,
            SignalSnapshot.label == label,
        )
        .first()
    )
    return ss.id if ss else None


class _EmptyActions:
    """Sentinel used when bundle.actions is None."""
    run_backtest_audit = False
    compute_reliability_score = False
    generate_strategy_report = False
    generate_alerts = False


# ---------------------------------------------------------------------------
# Main ingestion function
# ---------------------------------------------------------------------------

def ingest_evidence_bundle(
    strategy_id: uuid.UUID,
    bundle: EvidenceBundleRequest,
    db: Session,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
) -> EvidenceBundleResult:
    """Process all sections in the bundle and persist them via db.flush().

    Does NOT call db.commit() — the route handler is responsible for that.
    """
    objects: dict = {}
    warnings: list[str] = []
    actions_run: list[str] = []
    created_count = 0
    reused_count = 0
    timeline_events = 0
    alerts_generated = 0

    actions = bundle.actions if bundle.actions is not None else _EmptyActions()

    # ------------------------------------------------------------------
    # 1. strategy_version
    # ------------------------------------------------------------------
    sv_obj: StrategyVersion | None = None
    if bundle.strategy_version is not None:
        sec = bundle.strategy_version
        try:
            existing_sv = (
                db.query(StrategyVersion)
                .filter(
                    StrategyVersion.strategy_id == strategy_id,
                    StrategyVersion.version_label == sec.version_label,
                )
                .first()
            )
            if existing_sv is not None:
                sv_obj = existing_sv
                objects["strategy_version"] = {
                    "id": sv_obj.id,
                    "name": sv_obj.version_label,
                    "type": "strategy_version",
                    "status": "reused",
                }
                reused_count += 1
            else:
                sv_obj = StrategyVersion(
                    strategy_id=strategy_id,
                    version_label=sec.version_label,
                    git_commit=sec.git_commit,
                    branch_name=sec.branch_name,
                    code_path=sec.code_path,
                    signal_name=sec.signal_name,
                    signal_description=sec.signal_description,
                )
                db.add(sv_obj)
                db.flush()
                objects["strategy_version"] = {
                    "id": sv_obj.id,
                    "name": sv_obj.version_label,
                    "type": "strategy_version",
                    "status": "created",
                }
                created_count += 1
                _add_event(
                    db,
                    org_id=org_id,
                    project_id=project_id,
                    strategy_id=strategy_id,
                    event_type=EventType.strategy_version_created,
                    title=f"Strategy version created: {sec.version_label}",
                    source_type="strategy_version",
                    source_id=str(sv_obj.id),
                )
                timeline_events += 1
        except Exception as exc:
            warnings.append(f"strategy_version failed: {exc}")

    # ------------------------------------------------------------------
    # 2. config_snapshot
    # ------------------------------------------------------------------
    if bundle.config_snapshot is not None:
        sec = bundle.config_snapshot
        try:
            sv_id = _resolve_version_id(strategy_id, sec.strategy_version_label, db)
            config_hash = compute_config_hash(sec.config_json)
            param_count = count_params(sec.config_json)
            assumption_count = count_assumptions(sec.config_json)

            cs = StrategyConfigSnapshot(
                strategy_id=strategy_id,
                strategy_version_id=sv_id,
                label=sec.label,
                source_type=sec.source_type,
                source_filename=sec.source_filename,
                config_json=sec.config_json,
                config_hash=config_hash,
                param_count=param_count,
                assumption_count=assumption_count,
            )
            db.add(cs)
            db.flush()
            objects["config_snapshot"] = {
                "id": cs.id,
                "name": sec.label,
                "type": "config_snapshot",
                "status": "created",
            }
            created_count += 1
            _add_event(
                db,
                org_id=org_id,
                project_id=project_id,
                strategy_id=strategy_id,
                event_type=EventType.strategy_config_snapshot_logged,
                title=f"Config snapshot logged: {sec.label}",
                source_type="config_snapshot",
                source_id=str(cs.id),
            )
            timeline_events += 1
        except Exception as exc:
            warnings.append(f"config_snapshot failed: {exc}")

    # ------------------------------------------------------------------
    # 3. universe_snapshot
    # ------------------------------------------------------------------
    us_obj: UniverseSnapshot | None = None
    if bundle.universe_snapshot is not None:
        sec = bundle.universe_snapshot
        try:
            sv_id = _resolve_version_id(strategy_id, sec.strategy_version_label, db)
            norm_symbols = normalize_symbols(sec.symbols)
            u_hash = compute_universe_hash(norm_symbols, metadata=sec.metadata_json)

            us_obj = UniverseSnapshot(
                strategy_id=strategy_id,
                strategy_version_id=sv_id,
                label=sec.label,
                source_type=sec.source_type,
                source_filename=sec.source_filename,
                symbols_json=norm_symbols,
                symbol_count=len(norm_symbols),
                metadata_json=sec.metadata_json,
                universe_hash=u_hash,
            )
            db.add(us_obj)
            db.flush()
            objects["universe_snapshot"] = {
                "id": us_obj.id,
                "name": sec.label,
                "type": "universe_snapshot",
                "status": "created",
            }
            created_count += 1
            _add_event(
                db,
                org_id=org_id,
                project_id=project_id,
                strategy_id=strategy_id,
                event_type=EventType.universe_snapshot_logged,
                title=f"Universe snapshot logged: {sec.label} ({len(norm_symbols)} symbols)",
                source_type="universe_snapshot",
                source_id=str(us_obj.id),
            )
            timeline_events += 1
        except Exception as exc:
            warnings.append(f"universe_snapshot failed: {exc}")

    # ------------------------------------------------------------------
    # 4. signal_snapshot
    # ------------------------------------------------------------------
    ss_obj: SignalSnapshot | None = None
    if bundle.signal_snapshot is not None:
        sec = bundle.signal_snapshot
        try:
            sv_id = _resolve_version_id(strategy_id, sec.strategy_version_label, db)
            # Resolve universe_snapshot_id: prefer the one just created, then by label
            if us_obj is not None and sec.universe_snapshot_label is None:
                us_id = us_obj.id
            else:
                us_id = _resolve_universe_snapshot_id(
                    strategy_id, sec.universe_snapshot_label, db
                )

            norm_rows = normalize_signal_rows(sec.rows, signal_column=sec.signal_column)
            summary = summarize_signal_snapshot(norm_rows, signal_column=sec.signal_column)
            sig_hash = compute_signal_hash(
                norm_rows,
                metadata=sec.metadata_json,
                signal_column=sec.signal_column,
            )

            ss_obj = SignalSnapshot(
                strategy_id=strategy_id,
                strategy_version_id=sv_id,
                universe_snapshot_id=us_id,
                label=sec.label,
                signal_name=sec.signal_name,
                source_type=sec.source_type,
                source_filename=sec.source_filename,
                rows_json=norm_rows,
                row_count=summary.row_count,
                symbol_count=summary.symbol_count,
                symbols_json=summary.symbols,
                min_timestamp=summary.min_timestamp,
                max_timestamp=summary.max_timestamp,
                signal_value_count=summary.signal_value_count,
                missing_signal_count=summary.missing_signal_count,
                mean_value=summary.mean_value,
                min_value=summary.min_value,
                max_value=summary.max_value,
                stddev_value=summary.stddev_value,
                quality_score=summary.quality_score,
                signal_hash=sig_hash,
                metadata_json=sec.metadata_json,
            )
            db.add(ss_obj)
            db.flush()
            objects["signal_snapshot"] = {
                "id": ss_obj.id,
                "name": sec.label,
                "type": "signal_snapshot",
                "status": "created",
            }
            created_count += 1
            _add_event(
                db,
                org_id=org_id,
                project_id=project_id,
                strategy_id=strategy_id,
                event_type=EventType.signal_snapshot_logged,
                title=f"Signal snapshot logged: {sec.label} ({summary.row_count} rows)",
                source_type="signal_snapshot",
                source_id=str(ss_obj.id),
            )
            timeline_events += 1
        except Exception as exc:
            warnings.append(f"signal_snapshot failed: {exc}")

    # ------------------------------------------------------------------
    # 5. dataset (create or reuse by name within project)
    # ------------------------------------------------------------------
    dataset_obj: Dataset | None = None
    if bundle.dataset is not None:
        sec = bundle.dataset
        try:
            existing_ds = (
                db.query(Dataset)
                .filter(
                    Dataset.project_id == project_id,
                    Dataset.name == sec.name,
                )
                .first()
            )
            if existing_ds is not None:
                dataset_obj = existing_ds
                objects["dataset"] = {
                    "id": dataset_obj.id,
                    "name": dataset_obj.name,
                    "type": "dataset",
                    "status": "reused",
                }
                reused_count += 1
            else:
                dataset_obj = Dataset(
                    project_id=project_id,
                    name=sec.name,
                    description=sec.description,
                    dataset_type=sec.dataset_type,
                    source_type=sec.source_type,
                )
                db.add(dataset_obj)
                db.flush()
                objects["dataset"] = {
                    "id": dataset_obj.id,
                    "name": dataset_obj.name,
                    "type": "dataset",
                    "status": "created",
                }
                created_count += 1
                _add_event(
                    db,
                    org_id=org_id,
                    project_id=project_id,
                    strategy_id=strategy_id,
                    event_type=EventType.dataset_snapshot_uploaded,
                    title=f"Dataset created: {sec.name}",
                    source_type="dataset",
                    source_id=str(dataset_obj.id),
                )
                timeline_events += 1
        except Exception as exc:
            warnings.append(f"dataset failed: {exc}")

    # ------------------------------------------------------------------
    # 6. dataset_snapshot
    # ------------------------------------------------------------------
    dsnap_obj: DatasetSnapshot | None = None
    if bundle.dataset_snapshot is not None and dataset_obj is not None:
        sec = bundle.dataset_snapshot
        try:
            snap_label = sec.snapshot_label or f"v{_utcnow().strftime('%Y%m%d%H%M%S')}"
            quality_summary = analyze_snapshot(sec.rows)

            dsnap_obj = DatasetSnapshot(
                dataset_id=dataset_obj.id,
                version_label=snap_label,
                row_count=quality_summary.row_count,
                health_score=quality_summary.health_score,
                rows_json=sec.rows,
            )
            db.add(dsnap_obj)
            db.flush()

            for issue_spec in quality_summary.issues:
                db.add(DataQualityIssue(
                    snapshot_id=dsnap_obj.id,
                    issue_type=issue_spec.issue_type,
                    severity=issue_spec.severity,
                    field_name=issue_spec.field_name,
                    row_index=issue_spec.row_index,
                    detail=issue_spec.detail,
                ))
            db.flush()

            objects["dataset_snapshot"] = {
                "id": dsnap_obj.id,
                "name": snap_label,
                "type": "dataset_snapshot",
                "status": "created",
            }
            created_count += 1
            sev = Severity.high if quality_summary.health_score < 70 else Severity.info
            _add_event(
                db,
                org_id=org_id,
                project_id=project_id,
                strategy_id=strategy_id,
                event_type=EventType.dataset_snapshot_uploaded,
                title=f"Dataset snapshot uploaded: {snap_label} (health {quality_summary.health_score}/100)",
                source_type="dataset_snapshot",
                source_id=str(dsnap_obj.id),
                severity=sev,
            )
            timeline_events += 1
        except Exception as exc:
            warnings.append(f"dataset_snapshot failed: {exc}")
    elif bundle.dataset_snapshot is not None and dataset_obj is None:
        warnings.append("dataset_snapshot skipped: no dataset was provided or created")

    # ------------------------------------------------------------------
    # 7. strategy_run
    # ------------------------------------------------------------------
    run_obj: StrategyRun | None = None
    if bundle.strategy_run is not None:
        sec = bundle.strategy_run
        try:
            # Resolve linked IDs
            run_sv_id = _resolve_version_id(strategy_id, sec.strategy_version_label, db)
            run_us_id: uuid.UUID | None = None
            run_dsnap_id: uuid.UUID | None = None
            run_ss_id: uuid.UUID | None = None

            # Prefer freshly-created objects, fall back to label lookup
            if us_obj is not None and sec.universe_snapshot_label is None:
                run_us_id = us_obj.id
            else:
                run_us_id = _resolve_universe_snapshot_id(
                    strategy_id, sec.universe_snapshot_label, db
                )

            if dsnap_obj is not None and sec.dataset_snapshot_label is None:
                run_dsnap_id = dsnap_obj.id
            elif dataset_obj is not None and sec.dataset_snapshot_label is not None:
                run_dsnap_id = _resolve_dataset_snapshot_id(
                    dataset_obj.id, sec.dataset_snapshot_label, db
                )

            if ss_obj is not None and sec.signal_snapshot_label is None:
                run_ss_id = ss_obj.id
            else:
                run_ss_id = _resolve_signal_snapshot_id(
                    strategy_id, sec.signal_snapshot_label, db
                )

            run_obj = StrategyRun(
                strategy_id=strategy_id,
                strategy_version_id=run_sv_id,
                dataset_snapshot_id=run_dsnap_id,
                universe_snapshot_id=run_us_id,
                signal_snapshot_id=run_ss_id,
                run_name=sec.run_name,
                run_type=sec.run_type,
                status=sec.status,
                started_at=sec.started_at,
                completed_at=sec.completed_at,
                params_json=sec.params_json,
                assumptions_json=sec.assumptions_json,
                metrics_json=sec.metrics_json,
                universe_name=sec.universe_name,
                dataset_version=sec.dataset_version,
                notes=sec.notes,
            )
            db.add(run_obj)
            db.flush()
            objects["strategy_run"] = {
                "id": run_obj.id,
                "name": sec.run_name,
                "type": "strategy_run",
                "status": "created",
            }
            created_count += 1
            _add_event(
                db,
                org_id=org_id,
                project_id=project_id,
                strategy_id=strategy_id,
                event_type=EventType.strategy_run_logged,
                title=f"Strategy run logged: {sec.run_name} ({sec.run_type})",
                source_type="strategy_run",
                source_id=str(run_obj.id),
            )
            timeline_events += 1
        except Exception as exc:
            warnings.append(f"strategy_run failed: {exc}")

    # ------------------------------------------------------------------
    # 8. Action: run_backtest_audit
    # ------------------------------------------------------------------
    if getattr(bundle.actions, "run_backtest_audit", False) and run_obj is not None:
        try:
            from app.services.backtest_reality import run_backtest_audit
            from app.schemas.strategy import DataEvidenceSummary

            # Build evidence summary if we have a dataset snapshot
            evidence = None
            if dsnap_obj is not None:
                try:
                    evidence = DataEvidenceSummary(
                        id=dsnap_obj.id,
                        dataset_id=dsnap_obj.dataset_id,
                        dataset_name=dataset_obj.name if dataset_obj else "—",
                        snapshot_label=dsnap_obj.version_label,
                        health_score=dsnap_obj.health_score,
                        row_count=dsnap_obj.row_count,
                        column_count=0,
                        symbol_count=0,
                        min_timestamp=None,
                        max_timestamp=None,
                        issue_count=0,
                        worst_severity=None,
                    )
                except Exception:
                    evidence = None

            audit_result = run_backtest_audit(run_obj, data_evidence=evidence)

            # Delete any existing audit for this run
            existing_audit = (
                db.query(BacktestAudit)
                .filter(BacktestAudit.strategy_run_id == run_obj.id)
                .first()
            )
            if existing_audit is not None:
                db.delete(existing_audit)
                db.flush()

            audit_obj = BacktestAudit(
                strategy_run_id=run_obj.id,
                trust_score=audit_result.trust_score,
                lookahead_risk_score=audit_result.lookahead_risk_score,
                cost_realism_score=audit_result.cost_realism_score,
                fill_realism_score=audit_result.fill_realism_score,
                liquidity_realism_score=audit_result.liquidity_realism_score,
                borrow_realism_score=audit_result.borrow_realism_score,
                data_quality_score=audit_result.data_quality_score,
                overall_status=audit_result.overall_status,
                summary=audit_result.summary,
                cost_sensitivity_json=audit_result.cost_sensitivity_json,
                fill_realism_json=audit_result.fill_realism_json,
                fragility_summary_json=audit_result.fragility_summary_json,
            )
            db.add(audit_obj)
            db.flush()

            for issue in audit_result.issues:
                db.add(BacktestIssue(
                    backtest_audit_id=audit_obj.id,
                    issue_type=issue.issue_type,
                    severity=issue.severity,
                    title=issue.title,
                    description=issue.description,
                    evidence_json=issue.evidence_json,
                    suggested_check=issue.suggested_check,
                ))
            db.flush()

            objects["backtest_audit"] = {
                "id": audit_obj.id,
                "name": f"Backtest audit (trust={audit_result.trust_score})",
                "type": "backtest_audit",
                "status": "created",
            }
            created_count += 1
            actions_run.append("run_backtest_audit")
            _add_event(
                db,
                org_id=org_id,
                project_id=project_id,
                strategy_id=strategy_id,
                event_type=EventType.backtest_audited,
                title=f"Backtest audited: trust score {audit_result.trust_score}/100",
                source_type="backtest_audit",
                source_id=str(audit_obj.id),
                severity=Severity.high if audit_result.trust_score < 70 else Severity.info,
            )
            timeline_events += 1
        except Exception as exc:
            warnings.append(f"run_backtest_audit failed: {exc}")

    # ------------------------------------------------------------------
    # 9. Action: compute_reliability_score
    # ------------------------------------------------------------------
    if getattr(bundle.actions, "compute_reliability_score", False):
        try:
            from app.services.strategy_reliability import compute_reliability_score as _compute_rs

            score_dict = _compute_rs(str(strategy_id), db)
            rs_obj = StrategyReliabilityScore(**score_dict)
            db.add(rs_obj)
            db.flush()

            objects["reliability_score"] = {
                "id": rs_obj.id,
                "name": f"Reliability score ({rs_obj.status})",
                "type": "reliability_score",
                "status": "created",
            }
            created_count += 1
            actions_run.append("compute_reliability_score")
            _add_event(
                db,
                org_id=org_id,
                project_id=project_id,
                strategy_id=strategy_id,
                event_type=EventType.strategy_reliability_scored,
                title=f"Reliability scored: {rs_obj.overall_score} ({rs_obj.status})",
                source_type="reliability_score",
                source_id=str(rs_obj.id),
            )
            timeline_events += 1
        except Exception as exc:
            warnings.append(f"compute_reliability_score failed: {exc}")

    # ------------------------------------------------------------------
    # 10. Action: generate_strategy_report
    # ------------------------------------------------------------------
    if getattr(bundle.actions, "generate_strategy_report", False):
        try:
            from app.services.reports import generate_strategy_reliability_report, persist_report

            report_result = generate_strategy_reliability_report(strategy_id, db)
            report_obj = persist_report(report_result, db)

            objects["report"] = {
                "id": report_obj.id,
                "name": report_obj.title,
                "type": "report",
                "status": "created",
            }
            created_count += 1
            actions_run.append("generate_strategy_report")
            _add_event(
                db,
                org_id=org_id,
                project_id=project_id,
                strategy_id=strategy_id,
                event_type=EventType.report_generated,
                title=f"Strategy report generated: {report_obj.title}",
                source_type="report",
                source_id=str(report_obj.id),
            )
            timeline_events += 1
        except Exception as exc:
            warnings.append(f"generate_strategy_report failed: {exc}")

    # ------------------------------------------------------------------
    # 11. Action: generate_alerts
    # ------------------------------------------------------------------
    if getattr(bundle.actions, "generate_alerts", False):
        try:
            from app.services.alerts import generate_alerts

            alert_result = generate_alerts(db, str(org_id))
            alerts_generated = alert_result.alerts_created
            actions_run.append("generate_alerts")
        except Exception as exc:
            warnings.append(f"generate_alerts failed: {exc}")

    # ------------------------------------------------------------------
    # Bundle-level timeline event
    # ------------------------------------------------------------------
    section_names = [k for k, v in objects.items() if v is not None]
    _add_event(
        db,
        org_id=org_id,
        project_id=project_id,
        strategy_id=strategy_id,
        event_type=EventType.evidence_bundle_ingested,
        title=f"Evidence bundle ingested: {created_count} created, {reused_count} reused",
        description=(
            f"Sections: {', '.join(section_names) if section_names else 'none'}. "
            f"Actions: {', '.join(actions_run) if actions_run else 'none'}. "
            f"Warnings: {len(warnings)}."
        ),
        source_type="evidence_bundle",
        source_id=str(strategy_id),
        metadata_json={
            "created_count": created_count,
            "reused_count": reused_count,
            "actions_run": actions_run,
            "warnings": warnings,
        },
    )
    timeline_events += 1

    # Build summary string
    parts = []
    if created_count:
        parts.append(f"{created_count} object(s) created")
    if reused_count:
        parts.append(f"{reused_count} object(s) reused")
    if actions_run:
        parts.append(f"actions: {', '.join(actions_run)}")
    if warnings:
        parts.append(f"{len(warnings)} warning(s)")
    summary = "; ".join(parts) if parts else "No evidence sections provided"

    return EvidenceBundleResult(
        strategy_id=strategy_id,
        created_count=created_count,
        reused_count=reused_count,
        actions_run=actions_run,
        objects=objects,
        alerts_generated=alerts_generated,
        warnings=warnings,
        summary=summary,
        timeline_events_created=timeline_events,
        generated_at=_utcnow(),
    )
