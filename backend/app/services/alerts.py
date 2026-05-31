"""Alert generation service — M11 Alerts Engine.

Deterministic, evidence-driven alert generation.  No AI, no live data, no
external calls.  All thresholds and logic are hardcoded; the service only reads
from the database and writes new ``Alert`` rows.

Five checks are performed on each generation run:

  1. data_health_below_threshold  — DatasetSnapshot.health_score < 70
  2. backtest_trust_below_threshold — BacktestAudit.trust_score < 70
  3. data_quality_issue_high_or_critical — DataQualityIssue.severity in (high, critical)
  4. backtest_issue_high_or_critical — BacktestIssue.severity in (high, critical)
  5. strategy_run_missing_dataset_evidence — StrategyRun with no dataset_snapshot_id
     and run_type in (backtest, research, paper)

Deduplication:
  An existing Alert where (rule_type, source_type, source_id) matches AND
  status IN ('open', 'acknowledged', 'snoozed') blocks a new alert from being
  created.  Resolved alerts allow re-triggering.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.backtest_audit import BacktestAudit
from app.models.backtest_issue import BacktestIssue
from app.models.data_quality_issue import DataQualityIssue
from app.models.dataset import Dataset
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun
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
    return result


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
