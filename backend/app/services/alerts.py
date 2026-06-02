"""Alert generation service — M11 Alerts Engine + M33 Evidence Quality Checks.

Deterministic, evidence-driven alert generation.  No AI, no live data, no
external calls.  All thresholds and logic are hardcoded; the service only reads
from the database and writes new ``Alert`` rows.

Five legacy checks are performed on each generation run:

  1. data_health_below_threshold  — DatasetSnapshot.health_score < 70
  2. backtest_trust_below_threshold — BacktestAudit.trust_score < 70
  3. data_quality_issue_high_or_critical — DataQualityIssue.severity in (high, critical)
  4. backtest_issue_high_or_critical — BacktestIssue.severity in (high, critical)
  5. strategy_run_missing_dataset_evidence — StrategyRun with no dataset_snapshot_id
     and run_type in (backtest, research, paper)

M33 evidence quality checks run per strategy:
  A. evidence_coverage_below_threshold
  B. strategy_health_review_or_critical
  C. reliability_score_deteriorating
  D. data_health_deteriorating
  E. signal_quality_deteriorating
  F. backtest_trust_deteriorating
  G. stale_strategy_run
  H. missing_signal/universe/config_evidence
  I. repeated_failed_ingestion

Deduplication:
  An existing Alert where (rule_type, source_type, source_id) matches AND
  status IN ('open', 'acknowledged', 'snoozed') blocks a new alert from being
  created.  Resolved alerts allow re-triggering.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.backtest_audit import BacktestAudit
from app.models.backtest_issue import BacktestIssue
from app.models.data_quality_issue import DataQualityIssue
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.signal_snapshot import SignalSnapshot
from app.models.strategy import Strategy
from app.models.strategy_config_snapshot import StrategyConfigSnapshot
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.models.strategy_run import StrategyRun
from app.models.universe_snapshot import UniverseSnapshot
from app.models.project import Project
from app.models.organization import Organization
from app.core.constants import AlertRuleType, AlertStatus


# ---------------------------------------------------------------------------
# Severity thresholds
# ---------------------------------------------------------------------------

def _score_to_severity(score: int) -> str | None:
    """Map a 0–100 score to alert severity; return None if score is acceptable.

    < 25  → critical
    < 50  → high
    < 70  → medium
    ≥ 70  → no alert
    """
    if score < 25:
        return "critical"
    if score < 50:
        return "high"
    if score < 70:
        return "medium"
    return None  # score is acceptable


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

_ACTIVE_STATUSES = {AlertStatus.open, AlertStatus.acknowledged, AlertStatus.snoozed}


def _is_duplicate(
    db: Session,
    organization_id: str,
    rule_type: str,
    source_type: str,
    source_id: str,
) -> bool:
    """Return True when an active (non-resolved) alert for this evidence already exists."""
    return (
        db.query(Alert)
        .filter(
            Alert.organization_id == organization_id,
            Alert.rule_type == rule_type,
            Alert.source_type == source_type,
            Alert.source_id == source_id,
            Alert.status.in_([str(s) for s in _ACTIVE_STATUSES]),
        )
        .first()
        is not None
    )


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class GenerateResult:
    alerts_created: int = 0
    alerts_skipped_duplicate: int = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_alerts(db: Session, organization_id: str) -> GenerateResult:
    """Run all five checks and persist new alerts.

    Returns a ``GenerateResult`` with created / skipped counts.
    """
    now = datetime.now(timezone.utc)
    result = GenerateResult()
    org_id_str = str(organization_id)

    # -----------------------------------------------------------------------
    # 1. data_health_below_threshold
    # -----------------------------------------------------------------------
    snapshots = (
        db.query(DatasetSnapshot)
        .filter(DatasetSnapshot.health_score < 70)
        .all()
    )
    for snap in snapshots:
        severity = _score_to_severity(snap.health_score)
        if severity is None:
            continue
        source_type = "dataset_snapshot"
        source_id = str(snap.id)
        rule_type = str(AlertRuleType.data_health_below_threshold)

        if _is_duplicate(db, org_id_str, rule_type, source_type, source_id):
            result.alerts_skipped_duplicate += 1
            continue

        # Resolve dataset name for a better title
        dataset = db.query(Dataset).filter(Dataset.id == snap.dataset_id).first()
        dataset_name = dataset.name if dataset else "Unknown dataset"

        alert = Alert(
            organization_id=org_id_str,
            rule_type=rule_type,
            status=str(AlertStatus.open),
            severity=severity,
            title=f"Low data health: {dataset_name} · {snap.version_label} ({snap.health_score}/100)",
            description=(
                f"Dataset snapshot '{snap.version_label}' for '{dataset_name}' "
                f"has a health score of {snap.health_score}/100, which is below the "
                f"acceptable threshold of 70."
            ),
            source_type=source_type,
            source_id=source_id,
            strategy_id=None,
            triggered_at=now,
            metadata_json={
                "health_score": snap.health_score,
                "version_label": snap.version_label,
                "dataset_name": dataset_name,
            },
        )
        db.add(alert)
        result.alerts_created += 1

    # -----------------------------------------------------------------------
    # 2. backtest_trust_below_threshold
    # -----------------------------------------------------------------------
    audits = (
        db.query(BacktestAudit, StrategyRun.strategy_id, StrategyRun.run_name, Strategy.name)
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .join(Strategy, StrategyRun.strategy_id == Strategy.id)
        .filter(BacktestAudit.trust_score < 70)
        .all()
    )
    for audit, strategy_id, run_name, strategy_name in audits:
        severity = _score_to_severity(audit.trust_score)
        if severity is None:
            continue
        source_type = "backtest_audit"
        source_id = str(audit.id)
        rule_type = str(AlertRuleType.backtest_trust_below_threshold)

        if _is_duplicate(db, org_id_str, rule_type, source_type, source_id):
            result.alerts_skipped_duplicate += 1
            continue

        alert = Alert(
            organization_id=org_id_str,
            rule_type=rule_type,
            status=str(AlertStatus.open),
            severity=severity,
            title=f"Low backtest trust: {strategy_name} · {run_name} ({audit.trust_score}/100)",
            description=(
                f"Backtest audit for run '{run_name}' on strategy '{strategy_name}' "
                f"has a trust score of {audit.trust_score}/100. "
                f"{audit.summary}"
            ),
            source_type=source_type,
            source_id=source_id,
            strategy_id=str(strategy_id) if strategy_id else None,
            triggered_at=now,
            metadata_json={
                "trust_score": audit.trust_score,
                "overall_status": audit.overall_status,
                "run_name": run_name,
                "strategy_name": strategy_name,
            },
        )
        db.add(alert)
        result.alerts_created += 1

    # -----------------------------------------------------------------------
    # 3. data_quality_issue_high_or_critical
    # -----------------------------------------------------------------------
    dq_issues = (
        db.query(DataQualityIssue)
        .filter(DataQualityIssue.severity.in_(["high", "critical"]))
        .all()
    )
    for issue in dq_issues:
        # Severity: critical issue → high alert, high issue → medium alert
        alert_severity = "high" if issue.severity == "critical" else "medium"
        source_type = "data_quality_issue"
        source_id = str(issue.id)
        rule_type = str(AlertRuleType.data_quality_issue_high_or_critical)

        if _is_duplicate(db, org_id_str, rule_type, source_type, source_id):
            result.alerts_skipped_duplicate += 1
            continue

        field_hint = f" on field '{issue.field_name}'" if issue.field_name else ""
        alert = Alert(
            organization_id=org_id_str,
            rule_type=rule_type,
            status=str(AlertStatus.open),
            severity=alert_severity,
            title=f"Data quality issue ({issue.severity}): {issue.issue_type}{field_hint}",
            description=issue.detail or f"{issue.issue_type} detected{field_hint}.",
            source_type=source_type,
            source_id=source_id,
            strategy_id=None,
            triggered_at=now,
            metadata_json={
                "issue_type": issue.issue_type,
                "issue_severity": issue.severity,
                "field_name": issue.field_name,
                "snapshot_id": str(issue.snapshot_id),
            },
        )
        db.add(alert)
        result.alerts_created += 1

    # -----------------------------------------------------------------------
    # 4. backtest_issue_high_or_critical
    # -----------------------------------------------------------------------
    bt_issues = (
        db.query(BacktestIssue, BacktestAudit.strategy_run_id, StrategyRun.strategy_id,
                 StrategyRun.run_name, Strategy.name)
        .join(BacktestAudit, BacktestIssue.backtest_audit_id == BacktestAudit.id)
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .join(Strategy, StrategyRun.strategy_id == Strategy.id)
        .filter(BacktestIssue.severity.in_(["high", "critical"]))
        .all()
    )
    for bt_issue, run_id, strategy_id, run_name, strategy_name in bt_issues:
        alert_severity = "high" if bt_issue.severity == "critical" else "medium"
        source_type = "backtest_issue"
        source_id = str(bt_issue.id)
        rule_type = str(AlertRuleType.backtest_issue_high_or_critical)

        if _is_duplicate(db, org_id_str, rule_type, source_type, source_id):
            result.alerts_skipped_duplicate += 1
            continue

        alert = Alert(
            organization_id=org_id_str,
            rule_type=rule_type,
            status=str(AlertStatus.open),
            severity=alert_severity,
            title=f"Backtest issue ({bt_issue.severity}): {bt_issue.title}",
            description=bt_issue.description,
            source_type=source_type,
            source_id=source_id,
            strategy_id=str(strategy_id) if strategy_id else None,
            triggered_at=now,
            metadata_json={
                "issue_type": bt_issue.issue_type,
                "issue_severity": bt_issue.severity,
                "run_name": run_name,
                "strategy_name": strategy_name,
            },
        )
        db.add(alert)
        result.alerts_created += 1

    # -----------------------------------------------------------------------
    # 5. strategy_run_missing_dataset_evidence
    # -----------------------------------------------------------------------
    _EVIDENCE_RUN_TYPES = {"backtest", "research", "paper"}
    runs_no_snapshot = (
        db.query(StrategyRun, Strategy.name)
        .join(Strategy, StrategyRun.strategy_id == Strategy.id)
        .filter(
            StrategyRun.run_type.in_(list(_EVIDENCE_RUN_TYPES)),
            StrategyRun.dataset_snapshot_id.is_(None),
        )
        .all()
    )
    for run, strategy_name in runs_no_snapshot:
        source_type = "strategy_run"
        source_id = str(run.id)
        rule_type = str(AlertRuleType.strategy_run_missing_dataset_evidence)

        if _is_duplicate(db, org_id_str, rule_type, source_type, source_id):
            result.alerts_skipped_duplicate += 1
            continue

        alert = Alert(
            organization_id=org_id_str,
            rule_type=rule_type,
            status=str(AlertStatus.open),
            severity="low",
            title=f"Missing data evidence: {strategy_name} · {run.run_name}",
            description=(
                f"Run '{run.run_name}' ({run.run_type}) for strategy '{strategy_name}' "
                f"has no linked dataset snapshot.  Linking a snapshot improves auditability."
            ),
            source_type=source_type,
            source_id=source_id,
            strategy_id=str(run.strategy_id),
            triggered_at=now,
            metadata_json={
                "run_type": run.run_type,
                "run_name": run.run_name,
                "strategy_name": strategy_name,
            },
        )
        db.add(alert)
        result.alerts_created += 1

    db.flush()

    # M33: evidence quality checks per strategy
    eq_result = run_evidence_quality_alerts(organization_id, db)
    result.alerts_created += eq_result["created"]
    result.alerts_skipped_duplicate += eq_result["skipped"]

    return result


# ---------------------------------------------------------------------------
# M33: Evidence quality alert helper
# ---------------------------------------------------------------------------

def _create_alert_if_new(
    db: Session,
    org_id: str,
    strategy_id: str,
    rule_type: str,
    severity: str,
    title: str,
    description: str,
    metadata_json: dict,
    now: datetime,
) -> Tuple[bool, Optional[Alert]]:
    """Create a strategy-scoped alert if no active one already exists.

    Uses source_type='strategy' and source_id=str(strategy_id) for dedup.
    Returns (True, alert) if created, (False, None) if skipped (duplicate).
    """
    source_type = "strategy"
    source_id = str(strategy_id)

    if _is_duplicate(db, org_id, rule_type, source_type, source_id):
        return False, None

    alert = Alert(
        organization_id=org_id,
        rule_type=rule_type,
        status=str(AlertStatus.open),
        severity=severity,
        title=title,
        description=description,
        source_type=source_type,
        source_id=source_id,
        strategy_id=str(strategy_id),
        triggered_at=now,
        metadata_json=metadata_json,
    )
    db.add(alert)
    db.flush()
    return True, alert


def run_evidence_quality_alerts(organization_id: str, db: Session) -> dict:
    """Run M33 evidence quality checks for all active strategies in the org.

    Returns a dict with 'created' and 'skipped' counts.
    """
    from app.services.evidence_coverage import _compute_row
    from app.services.strategy_health import compute_strategy_health

    now = datetime.now(timezone.utc)
    org_id_str = str(organization_id)
    created = 0
    skipped = 0

    # Get all non-archived strategies for the org via Project join.
    # organization_id may arrive as str; convert to uuid.UUID for the Uuid column.
    import uuid as _uuid_mod
    if isinstance(organization_id, str):
        try:
            org_uuid = _uuid_mod.UUID(organization_id)
        except ValueError:
            return {"created": 0, "skipped": 0}
    else:
        org_uuid = organization_id

    strategies = (
        db.query(Strategy)
        .join(Project, Strategy.project_id == Project.id)
        .filter(
            Project.organization_id == org_uuid,
            Strategy.status != "archived",
        )
        .all()
    )

    for strategy in strategies:
        sid = str(strategy.id)

        # ------------------------------------------------------------------
        # CHECK A: Evidence coverage threshold
        # ------------------------------------------------------------------
        try:
            cov = _compute_row(strategy, db)
            score = cov.evidence_coverage_score
            if score < 50:
                ok, _ = _create_alert_if_new(
                    db=db,
                    org_id=org_id_str,
                    strategy_id=sid,
                    rule_type=str(AlertRuleType.evidence_coverage_below_threshold),
                    severity="high",
                    title="Evidence coverage critically low",
                    description=(
                        f"Evidence coverage for {strategy.name} is {score:.0f}/100, "
                        f"below 50. {cov.missing_count} evidence cell(s) missing."
                    ),
                    metadata_json={
                        "evidence_coverage_score": score,
                        "missing_count": cov.missing_count,
                        "suggested_check": (
                            "Review missing evidence cells on the Evidence Coverage Matrix."
                        ),
                    },
                    now=now,
                )
                if ok:
                    created += 1
                else:
                    skipped += 1
            elif score < 70:
                ok, _ = _create_alert_if_new(
                    db=db,
                    org_id=org_id_str,
                    strategy_id=sid,
                    rule_type=str(AlertRuleType.evidence_coverage_below_threshold),
                    severity="medium",
                    title="Evidence coverage below review threshold",
                    description=(
                        f"Evidence coverage for {strategy.name} is {score:.0f}/100 "
                        f"(threshold: 70)."
                    ),
                    metadata_json={
                        "evidence_coverage_score": score,
                        "missing_count": cov.missing_count,
                        "suggested_check": (
                            "Review missing evidence cells on the Evidence Coverage Matrix."
                        ),
                    },
                    now=now,
                )
                if ok:
                    created += 1
                else:
                    skipped += 1
        except Exception:
            pass

        # ------------------------------------------------------------------
        # CHECK B: Strategy health critical/review
        # ------------------------------------------------------------------
        try:
            health = compute_strategy_health(strategy.id, db)
            if health.health_status == "critical":
                ok, _ = _create_alert_if_new(
                    db=db,
                    org_id=org_id_str,
                    strategy_id=sid,
                    rule_type=str(AlertRuleType.strategy_health_review_or_critical),
                    severity="critical",
                    title=f"Strategy health is critical: {strategy.name}",
                    description=(
                        f"Strategy {strategy.name} has health status: critical. "
                        f"Primary concern: {health.primary_concern}"
                    ),
                    metadata_json={
                        "health_status": health.health_status,
                        "primary_concern": health.primary_concern,
                        "health_score": health.health_score,
                        "suggested_check": "Review all open alerts and evidence gaps for this strategy.",
                    },
                    now=now,
                )
                if ok:
                    created += 1
                else:
                    skipped += 1
            elif health.health_status == "review":
                ok, _ = _create_alert_if_new(
                    db=db,
                    org_id=org_id_str,
                    strategy_id=sid,
                    rule_type=str(AlertRuleType.strategy_health_review_or_critical),
                    severity="high",
                    title=f"Strategy health requires review: {strategy.name}",
                    description=(
                        f"Strategy {strategy.name} has health status: review. "
                        f"Primary concern: {health.primary_concern}"
                    ),
                    metadata_json={
                        "health_status": health.health_status,
                        "primary_concern": health.primary_concern,
                        "health_score": health.health_score,
                        "suggested_check": "Review open alerts and evidence gaps for this strategy.",
                    },
                    now=now,
                )
                if ok:
                    created += 1
                else:
                    skipped += 1
        except Exception:
            pass

        # ------------------------------------------------------------------
        # CHECK C: Reliability score deterioration
        # ------------------------------------------------------------------
        try:
            rel_scores = (
                db.query(StrategyReliabilityScore)
                .filter(
                    StrategyReliabilityScore.strategy_id == strategy.id,
                    StrategyReliabilityScore.overall_score.isnot(None),
                )
                .order_by(StrategyReliabilityScore.generated_at.desc())
                .limit(2)
                .all()
            )
            if len(rel_scores) >= 2:
                latest_rs, prev_rs = rel_scores[0], rel_scores[1]
                delta = (latest_rs.overall_score or 0) - (prev_rs.overall_score or 0)
                if delta <= -15:
                    sev = "high"
                    title = f"Reliability score deteriorated significantly: {strategy.name}"
                    desc = (
                        f"Reliability score changed from {prev_rs.overall_score:.1f} to "
                        f"{latest_rs.overall_score:.1f} (delta: {delta:.1f})."
                    )
                elif delta <= -7:
                    sev = "medium"
                    title = f"Reliability score deteriorated: {strategy.name}"
                    desc = (
                        f"Reliability score changed from {prev_rs.overall_score:.1f} to "
                        f"{latest_rs.overall_score:.1f} (delta: {delta:.1f})."
                    )
                else:
                    sev = None
                if sev is not None:
                    ok, _ = _create_alert_if_new(
                        db=db,
                        org_id=org_id_str,
                        strategy_id=sid,
                        rule_type=str(AlertRuleType.reliability_score_deteriorating),
                        severity=sev,
                        title=title,
                        description=desc,
                        metadata_json={
                            "previous_score": prev_rs.overall_score,
                            "latest_score": latest_rs.overall_score,
                            "delta": delta,
                            "suggested_check": (
                                "Compute a fresh reliability score after resolving "
                                "flagged evidence items."
                            ),
                        },
                        now=now,
                    )
                    if ok:
                        created += 1
                    else:
                        skipped += 1
        except Exception:
            pass

        # ------------------------------------------------------------------
        # CHECK D: Data health deterioration
        # ------------------------------------------------------------------
        try:
            dh_rows = (
                db.query(DatasetSnapshot.health_score)
                .join(StrategyRun, StrategyRun.dataset_snapshot_id == DatasetSnapshot.id)
                .filter(StrategyRun.strategy_id == strategy.id)
                .order_by(DatasetSnapshot.created_at.desc())
                .limit(2)
                .all()
            )
            dh_scores = [row[0] for row in dh_rows if row[0] is not None]
            dh_latest = dh_scores[0] if dh_scores else None
            dh_prev = dh_scores[1] if len(dh_scores) > 1 else None
            dh_delta = (dh_latest - dh_prev) if (dh_latest is not None and dh_prev is not None) else None

            dh_sev = None
            dh_title = None
            dh_desc = None
            if dh_latest is not None and dh_latest < 50:
                dh_sev = "high"
                dh_title = f"Data health score critically low: {strategy.name}"
                dh_desc = f"Latest data health score is {dh_latest}/100, below 50."
            elif dh_delta is not None and dh_delta < -2.0:
                dh_sev = "medium"
                dh_title = f"Data health deteriorated: {strategy.name}"
                dh_desc = (
                    f"Data health score changed from {dh_prev} to {dh_latest} "
                    f"(delta: {dh_delta:.1f})."
                )
            if dh_sev is not None:
                ok, _ = _create_alert_if_new(
                    db=db,
                    org_id=org_id_str,
                    strategy_id=sid,
                    rule_type=str(AlertRuleType.data_health_deteriorating),
                    severity=dh_sev,
                    title=dh_title,
                    description=dh_desc,
                    metadata_json={
                        "previous_value": dh_prev,
                        "latest_value": dh_latest,
                        "delta": dh_delta,
                        "suggested_check": (
                            "Inspect Dataset Snapshots on the Strategy Detail page."
                        ),
                    },
                    now=now,
                )
                if ok:
                    created += 1
                else:
                    skipped += 1
        except Exception:
            pass

        # ------------------------------------------------------------------
        # CHECK E: Signal quality deterioration
        # ------------------------------------------------------------------
        try:
            sq_rows = (
                db.query(SignalSnapshot.quality_score)
                .filter(SignalSnapshot.strategy_id == strategy.id)
                .order_by(SignalSnapshot.created_at.desc())
                .limit(2)
                .all()
            )
            sq_scores = [row[0] for row in sq_rows if row[0] is not None]
            sq_latest = sq_scores[0] if sq_scores else None
            sq_prev = sq_scores[1] if len(sq_scores) > 1 else None
            sq_delta = (sq_latest - sq_prev) if (sq_latest is not None and sq_prev is not None) else None

            sq_sev = None
            sq_title = None
            sq_desc = None
            if sq_latest is not None and sq_latest < 50:
                sq_sev = "high"
                sq_title = f"Signal quality critically low: {strategy.name}"
                sq_desc = f"Latest signal quality score is {sq_latest}/100, below 50."
            elif sq_delta is not None and sq_delta < -2.0:
                sq_sev = "medium"
                sq_title = f"Signal quality deteriorated: {strategy.name}"
                sq_desc = (
                    f"Signal quality score changed from {sq_prev} to {sq_latest} "
                    f"(delta: {sq_delta:.1f})."
                )
            if sq_sev is not None:
                ok, _ = _create_alert_if_new(
                    db=db,
                    org_id=org_id_str,
                    strategy_id=sid,
                    rule_type=str(AlertRuleType.signal_quality_deteriorating),
                    severity=sq_sev,
                    title=sq_title,
                    description=sq_desc,
                    metadata_json={
                        "previous_value": sq_prev,
                        "latest_value": sq_latest,
                        "delta": sq_delta,
                        "suggested_check": (
                            "Inspect Signal Snapshots and quality scores on the "
                            "Strategy Detail page."
                        ),
                    },
                    now=now,
                )
                if ok:
                    created += 1
                else:
                    skipped += 1
        except Exception:
            pass

        # ------------------------------------------------------------------
        # CHECK F: Backtest trust deterioration
        # ------------------------------------------------------------------
        try:
            bt_rows = (
                db.query(BacktestAudit.trust_score)
                .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
                .filter(StrategyRun.strategy_id == strategy.id)
                .order_by(BacktestAudit.created_at.desc())
                .limit(2)
                .all()
            )
            bt_scores = [row[0] for row in bt_rows if row[0] is not None]
            bt_latest = bt_scores[0] if bt_scores else None
            bt_prev = bt_scores[1] if len(bt_scores) > 1 else None
            bt_delta = (bt_latest - bt_prev) if (bt_latest is not None and bt_prev is not None) else None

            bt_sev = None
            bt_title = None
            bt_desc = None
            if bt_latest is not None and bt_latest < 40:
                bt_sev = "critical"
                bt_title = f"Backtest trust critically low: {strategy.name}"
                bt_desc = f"Latest backtest trust score is {bt_latest}/100, below 40."
            elif bt_latest is not None and bt_latest < 60:
                bt_sev = "high"
                bt_title = f"Backtest trust low: {strategy.name}"
                bt_desc = f"Latest backtest trust score is {bt_latest}/100, below 60."
            elif bt_delta is not None and bt_delta < -2.0:
                bt_sev = "medium"
                bt_title = f"Backtest trust deteriorated: {strategy.name}"
                bt_desc = (
                    f"Backtest trust score changed from {bt_prev} to {bt_latest} "
                    f"(delta: {bt_delta:.1f})."
                )
            if bt_sev is not None:
                ok, _ = _create_alert_if_new(
                    db=db,
                    org_id=org_id_str,
                    strategy_id=sid,
                    rule_type=str(AlertRuleType.backtest_trust_deteriorating),
                    severity=bt_sev,
                    title=bt_title,
                    description=bt_desc,
                    metadata_json={
                        "previous_value": bt_prev,
                        "latest_value": bt_latest,
                        "delta": bt_delta,
                        "suggested_check": (
                            "Run Backtest Reality Check again after updating cost "
                            "and fill assumptions."
                        ),
                    },
                    now=now,
                )
                if ok:
                    created += 1
                else:
                    skipped += 1
        except Exception:
            pass

        # ------------------------------------------------------------------
        # CHECK G: Stale strategy run (active strategies only)
        # ------------------------------------------------------------------
        try:
            latest_run_at = (
                db.query(func.max(StrategyRun.created_at))
                .filter(StrategyRun.strategy_id == strategy.id)
                .scalar()
            )
            if latest_run_at is None:
                ok, _ = _create_alert_if_new(
                    db=db,
                    org_id=org_id_str,
                    strategy_id=sid,
                    rule_type=str(AlertRuleType.stale_strategy_run),
                    severity="medium",
                    title=f"No strategy runs logged: {strategy.name}",
                    description=(
                        f"Strategy '{strategy.name}' has no strategy runs logged. "
                        f"Log at least one run to begin evidence tracking."
                    ),
                    metadata_json={
                        "days_since_latest_run": None,
                        "suggested_check": (
                            "Log at least one strategy run to begin evidence tracking."
                        ),
                    },
                    now=now,
                )
                if ok:
                    created += 1
                else:
                    skipped += 1
            else:
                # Normalize naive datetime
                if latest_run_at.tzinfo is None:
                    latest_run_at_tz = latest_run_at.replace(tzinfo=timezone.utc)
                else:
                    latest_run_at_tz = latest_run_at
                days_stale = (now - latest_run_at_tz).days
                if days_stale > 90:
                    stale_sev = "medium"
                    stale_title = f"Strategy run is very stale ({days_stale} days old): {strategy.name}"
                    threshold = 90
                elif days_stale > 30:
                    stale_sev = "low"
                    stale_title = f"Strategy run is stale ({days_stale} days old): {strategy.name}"
                    threshold = 30
                else:
                    stale_sev = None
                if stale_sev is not None:
                    ok, _ = _create_alert_if_new(
                        db=db,
                        org_id=org_id_str,
                        strategy_id=sid,
                        rule_type=str(AlertRuleType.stale_strategy_run),
                        severity=stale_sev,
                        title=stale_title,
                        description=(
                            f"Strategy '{strategy.name}' last had a run logged "
                            f"{days_stale} days ago."
                        ),
                        metadata_json={
                            "latest_run_at": str(latest_run_at),
                            "days_since_latest_run": days_stale,
                            "threshold_days": threshold,
                            "suggested_check": (
                                "Log a new strategy run to keep evidence fresh."
                            ),
                        },
                        now=now,
                    )
                    if ok:
                        created += 1
                    else:
                        skipped += 1
        except Exception:
            pass

        # ------------------------------------------------------------------
        # CHECK H: Missing evidence (only if strategy has at least 1 run)
        # ------------------------------------------------------------------
        try:
            run_count = (
                db.query(func.count(StrategyRun.id))
                .filter(StrategyRun.strategy_id == strategy.id)
                .scalar()
            ) or 0
            if run_count > 0:
                sig_count = (
                    db.query(func.count(SignalSnapshot.id))
                    .filter(SignalSnapshot.strategy_id == strategy.id)
                    .scalar()
                ) or 0
                uni_count = (
                    db.query(func.count(UniverseSnapshot.id))
                    .filter(UniverseSnapshot.strategy_id == strategy.id)
                    .scalar()
                ) or 0
                cfg_count = (
                    db.query(func.count(StrategyConfigSnapshot.id))
                    .filter(StrategyConfigSnapshot.strategy_id == strategy.id)
                    .scalar()
                ) or 0

                if sig_count == 0:
                    ok, _ = _create_alert_if_new(
                        db=db,
                        org_id=org_id_str,
                        strategy_id=sid,
                        rule_type=str(AlertRuleType.missing_signal_evidence),
                        severity="low",
                        title=f"No signal snapshots logged: {strategy.name}",
                        description=(
                            f"Strategy '{strategy.name}' has {run_count} run(s) but "
                            f"no signal snapshots."
                        ),
                        metadata_json={
                            "run_count": run_count,
                            "signal_snapshot_count": 0,
                            "suggested_check": (
                                "Log a signal snapshot to capture signal quality evidence."
                            ),
                        },
                        now=now,
                    )
                    if ok:
                        created += 1
                    else:
                        skipped += 1

                if uni_count == 0:
                    ok, _ = _create_alert_if_new(
                        db=db,
                        org_id=org_id_str,
                        strategy_id=sid,
                        rule_type=str(AlertRuleType.missing_universe_evidence),
                        severity="low",
                        title=f"No universe snapshots logged: {strategy.name}",
                        description=(
                            f"Strategy '{strategy.name}' has {run_count} run(s) but "
                            f"no universe snapshots."
                        ),
                        metadata_json={
                            "run_count": run_count,
                            "universe_snapshot_count": 0,
                            "suggested_check": (
                                "Log a universe snapshot to capture universe evidence."
                            ),
                        },
                        now=now,
                    )
                    if ok:
                        created += 1
                    else:
                        skipped += 1

                if cfg_count == 0:
                    ok, _ = _create_alert_if_new(
                        db=db,
                        org_id=org_id_str,
                        strategy_id=sid,
                        rule_type=str(AlertRuleType.missing_config_evidence),
                        severity="low",
                        title=f"No config snapshots logged: {strategy.name}",
                        description=(
                            f"Strategy '{strategy.name}' has {run_count} run(s) but "
                            f"no config snapshots."
                        ),
                        metadata_json={
                            "run_count": run_count,
                            "config_snapshot_count": 0,
                            "suggested_check": (
                                "Log a config snapshot to capture configuration evidence."
                            ),
                        },
                        now=now,
                    )
                    if ok:
                        created += 1
                    else:
                        skipped += 1
        except Exception:
            pass

        # ------------------------------------------------------------------
        # CHECK I: Repeated failed ingestion (safe, skip if model unavailable)
        # ------------------------------------------------------------------
        try:
            from app.models.sdk_ingestion_batch import SdkIngestionBatch
            from datetime import timedelta

            cutoff = now - timedelta(days=7)
            failed_count = (
                db.query(func.count(SdkIngestionBatch.id))
                .filter(
                    SdkIngestionBatch.strategy_id == strategy.id,
                    SdkIngestionBatch.status == "failed",
                    SdkIngestionBatch.created_at >= cutoff,
                )
                .scalar()
            ) or 0
            if failed_count >= 3:
                ing_sev = "high" if failed_count >= 5 else "medium"
                ok, _ = _create_alert_if_new(
                    db=db,
                    org_id=org_id_str,
                    strategy_id=sid,
                    rule_type=str(AlertRuleType.repeated_failed_ingestion),
                    severity=ing_sev,
                    title=f"Repeated ingestion failures: {strategy.name}",
                    description=(
                        f"{failed_count} failed ingestion batch(es) in the last 7 days."
                    ),
                    metadata_json={
                        "failed_count": failed_count,
                        "window_days": 7,
                        "suggested_check": "Investigate recent ingestion failures.",
                    },
                    now=now,
                )
                if ok:
                    created += 1
                else:
                    skipped += 1
        except Exception:
            pass

    db.flush()
    return {"created": created, "skipped": skipped}


def get_open_alert_count(db: Session, organization_id: str) -> int:
    """Count all open alerts for the organisation."""
    return (
        db.query(Alert)
        .filter(
            Alert.organization_id == organization_id,
            Alert.status == str(AlertStatus.open),
        )
        .count()
    )


def get_high_critical_alert_count(db: Session, organization_id: str) -> int:
    """Count open alerts with severity high or critical."""
    return (
        db.query(Alert)
        .filter(
            Alert.organization_id == organization_id,
            Alert.status == str(AlertStatus.open),
            Alert.severity.in_(["high", "critical"]),
        )
        .count()
    )
