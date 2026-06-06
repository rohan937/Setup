"""Alert generation service — M11 Alerts Engine + M33 Evidence Quality Checks
+ M85 Candidate/Reconcile Lifecycle.

Deterministic, evidence-driven alert generation.  No AI, no live data, no
external calls.  All thresholds and logic are hardcoded; the service only reads
from the database and writes ``Alert`` / ``AlertHistory`` rows.

M85 lifecycle
-------------
Detection no longer creates ``Alert`` rows inline.  Each check APPENDS a
:class:`AlertCandidate` to a list.  A central :func:`reconcile_alerts` function
then drives the full lifecycle:

  * reactivate expired snoozes,
  * create alerts for firing candidates that have no active duplicate,
  * skip firing candidates that already have an active alert,
  * auto-resolve previously-open/acknowledged alerts that are no longer firing.

Every transition writes an immutable :class:`AlertHistory` audit row.

Detection key
-------------
A candidate is identified by ``(rule_type, source_type, source_id)``.  An
existing Alert is "active" when its status is open/acknowledged or snoozed with
``snoozed_until`` in the future (an expired snooze counts as active until the
reconcile pass reactivates it to open).
"""

from __future__ import annotations

import uuid as _uuid_mod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.alert_history import AlertHistory
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
from app.core.constants import AlertAction, AlertRuleType, AlertStatus
from app.services.alert_catalog import recommended_fix_for


# ---------------------------------------------------------------------------
# Candidate shape
# ---------------------------------------------------------------------------

@dataclass
class AlertCandidate:
    """A firing condition emitted by a detection check.

    Identity is ``(rule_type, source_type, source_id)``.  ``strategy_id`` is the
    32-char hex form expected by the GUID FK column (or ``None``).
    """

    rule_type: str
    severity: str
    title: str
    description: str | None
    source_type: str
    source_id: str
    strategy_id: str | None = None
    metadata: dict = field(default_factory=dict)

    def key(self) -> Tuple[str, str, str]:
        return (str(self.rule_type), str(self.source_type), str(self.source_id))


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
# Status helpers
# ---------------------------------------------------------------------------

_ACTIVE_STATUSES = {AlertStatus.open, AlertStatus.acknowledged, AlertStatus.snoozed}

# Open alerts of these rule types block promotion of a strategy.
_BLOCKING_RULE_TYPES = {
    str(AlertRuleType.promotion_gate_blocked),
    str(AlertRuleType.regression_test_failed),
    str(AlertRuleType.evidence_sla_breached),
}


def is_active_status(alert: Alert, now: datetime | None = None) -> bool:
    """Return True when *alert* is currently active.

    open/acknowledged are always active.  A snoozed alert is active only when
    its snooze has expired (``snoozed_until`` <= now); a future snooze is
    treated as inactive.  resolved/dismissed are inactive.
    """
    now = now or datetime.now(timezone.utc)
    status = str(alert.status)
    if status in (str(AlertStatus.open), str(AlertStatus.acknowledged)):
        return True
    if status == str(AlertStatus.snoozed):
        su = alert.snoozed_until
        if su is None:
            return True
        if su.tzinfo is None:
            su = su.replace(tzinfo=timezone.utc)
        return su <= now  # expired snooze is active again
    return False


def _hexid(value) -> str | None:
    """Normalise a strategy id to the 32-char hex form used by GUID FK columns."""
    if value is None:
        return None
    if isinstance(value, _uuid_mod.UUID):
        return value.hex
    try:
        return _uuid_mod.UUID(str(value)).hex
    except (ValueError, AttributeError):
        return str(value)


def _org_uuid(organization_id):
    """Best-effort parse of an organization id into uuid.UUID; None on failure."""
    if isinstance(organization_id, _uuid_mod.UUID):
        return organization_id
    try:
        return _uuid_mod.UUID(str(organization_id))
    except (ValueError, AttributeError):
        return None


def _org_id_str(organization_id) -> str:
    """Return the 32-char hex form of an org id for FK comparisons."""
    ou = _org_uuid(organization_id)
    return ou.hex if ou is not None else str(organization_id)


# ---------------------------------------------------------------------------
# Result container (back-compat with M11 callers)
# ---------------------------------------------------------------------------

@dataclass
class GenerateResult:
    alerts_created: int = 0
    alerts_skipped_duplicate: int = 0
    alerts_auto_resolved: int = 0
    total_alerts_open: int = 0


# ---------------------------------------------------------------------------
# History helper
# ---------------------------------------------------------------------------

def record_alert_history(
    db: Session,
    alert_id: str,
    actor_user_id: str | None,
    action: str,
    note: str | None = None,
) -> AlertHistory:
    """Append an immutable audit row for a lifecycle action on an alert."""
    entry = AlertHistory(
        alert_id=str(alert_id),
        actor_user_id=actor_user_id,
        action=str(action),
        note=note,
    )
    db.add(entry)
    return entry


# ---------------------------------------------------------------------------
# Candidate collection — legacy (M11) checks
# ---------------------------------------------------------------------------

def _collect_legacy_candidates(db: Session, org_id_str: str) -> list[AlertCandidate]:
    """Re-implements the five M11 checks as candidate emitters.

    Conditions, severities, titles and descriptions are preserved verbatim.
    """
    candidates: list[AlertCandidate] = []

    # 1. data_health_below_threshold
    try:
        snapshots = db.query(DatasetSnapshot).filter(DatasetSnapshot.health_score < 70).all()
        for snap in snapshots:
            severity = _score_to_severity(snap.health_score)
            if severity is None:
                continue
            dataset = db.query(Dataset).filter(Dataset.id == snap.dataset_id).first()
            dataset_name = dataset.name if dataset else "Unknown dataset"
            candidates.append(AlertCandidate(
                rule_type=str(AlertRuleType.data_health_below_threshold),
                severity=severity,
                title=f"Low data health: {dataset_name} · {snap.version_label} ({snap.health_score}/100)",
                description=(
                    f"Dataset snapshot '{snap.version_label}' for '{dataset_name}' "
                    f"has a health score of {snap.health_score}/100, which is below the "
                    f"acceptable threshold of 70."
                ),
                source_type="dataset_snapshot",
                source_id=str(snap.id),
                strategy_id=None,
                metadata={
                    "health_score": snap.health_score,
                    "version_label": snap.version_label,
                    "dataset_name": dataset_name,
                },
            ))
    except Exception:
        pass

    # 2. backtest_trust_below_threshold
    try:
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
            candidates.append(AlertCandidate(
                rule_type=str(AlertRuleType.backtest_trust_below_threshold),
                severity=severity,
                title=f"Low backtest trust: {strategy_name} · {run_name} ({audit.trust_score}/100)",
                description=(
                    f"Backtest audit for run '{run_name}' on strategy '{strategy_name}' "
                    f"has a trust score of {audit.trust_score}/100. {audit.summary}"
                ),
                source_type="backtest_audit",
                source_id=str(audit.id),
                strategy_id=_hexid(strategy_id),
                metadata={
                    "trust_score": audit.trust_score,
                    "overall_status": audit.overall_status,
                    "run_name": run_name,
                    "strategy_name": strategy_name,
                },
            ))
    except Exception:
        pass

    # 3. data_quality_issue_high_or_critical
    try:
        dq_issues = (
            db.query(DataQualityIssue)
            .filter(DataQualityIssue.severity.in_(["high", "critical"]))
            .all()
        )
        for issue in dq_issues:
            alert_severity = "high" if issue.severity == "critical" else "medium"
            field_hint = f" on field '{issue.field_name}'" if issue.field_name else ""
            candidates.append(AlertCandidate(
                rule_type=str(AlertRuleType.data_quality_issue_high_or_critical),
                severity=alert_severity,
                title=f"Data quality issue ({issue.severity}): {issue.issue_type}{field_hint}",
                description=issue.detail or f"{issue.issue_type} detected{field_hint}.",
                source_type="data_quality_issue",
                source_id=str(issue.id),
                strategy_id=None,
                metadata={
                    "issue_type": issue.issue_type,
                    "issue_severity": issue.severity,
                    "field_name": issue.field_name,
                    "snapshot_id": str(issue.snapshot_id),
                },
            ))
    except Exception:
        pass

    # 4. backtest_issue_high_or_critical
    try:
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
            candidates.append(AlertCandidate(
                rule_type=str(AlertRuleType.backtest_issue_high_or_critical),
                severity=alert_severity,
                title=f"Backtest issue ({bt_issue.severity}): {bt_issue.title}",
                description=bt_issue.description,
                source_type="backtest_issue",
                source_id=str(bt_issue.id),
                strategy_id=_hexid(strategy_id),
                metadata={
                    "issue_type": bt_issue.issue_type,
                    "issue_severity": bt_issue.severity,
                    "run_name": run_name,
                    "strategy_name": strategy_name,
                },
            ))
    except Exception:
        pass

    # 5. strategy_run_missing_dataset_evidence
    try:
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
            candidates.append(AlertCandidate(
                rule_type=str(AlertRuleType.strategy_run_missing_dataset_evidence),
                severity="low",
                title=f"Missing data evidence: {strategy_name} · {run.run_name}",
                description=(
                    f"Run '{run.run_name}' ({run.run_type}) for strategy '{strategy_name}' "
                    f"has no linked dataset snapshot.  Linking a snapshot improves auditability."
                ),
                source_type="strategy_run",
                source_id=str(run.id),
                strategy_id=_hexid(run.strategy_id),
                metadata={
                    "run_type": run.run_type,
                    "run_name": run.run_name,
                    "strategy_name": strategy_name,
                },
            ))
    except Exception:
        pass

    return candidates


# ---------------------------------------------------------------------------
# Candidate collection — M33 evidence quality checks
# ---------------------------------------------------------------------------

def _collect_evidence_quality_candidates(
    db: Session,
    strategies: list[Strategy],
) -> list[AlertCandidate]:
    """Re-implements the M33 per-strategy evidence-quality checks as candidates.

    Conditions / severities / titles / descriptions are preserved.  Each check
    is wrapped in try/except so one failing subsystem cannot break generation.
    """
    from app.services.evidence_coverage import _compute_row
    from app.services.strategy_health import compute_strategy_health

    now = datetime.now(timezone.utc)
    candidates: list[AlertCandidate] = []

    def _strat_candidate(strategy, sid, rule_type, severity, title, description, metadata):
        return AlertCandidate(
            rule_type=str(rule_type),
            severity=severity,
            title=title,
            description=description,
            source_type="strategy",
            source_id=str(sid),
            strategy_id=_hexid(sid),
            metadata=metadata,
        )

    for strategy in strategies:
        sid = _hexid(strategy.id)

        # CHECK A: Evidence coverage threshold
        try:
            cov = _compute_row(strategy, db)
            score = cov.evidence_coverage_score
            if score < 50:
                candidates.append(_strat_candidate(
                    strategy, sid, AlertRuleType.evidence_coverage_below_threshold, "high",
                    "Evidence coverage critically low",
                    f"Evidence coverage for {strategy.name} is {score:.0f}/100, "
                    f"below 50. {cov.missing_count} evidence cell(s) missing.",
                    {
                        "evidence_coverage_score": score,
                        "missing_count": cov.missing_count,
                        "suggested_check": "Review missing evidence cells on the Evidence Coverage Matrix.",
                    },
                ))
            elif score < 70:
                candidates.append(_strat_candidate(
                    strategy, sid, AlertRuleType.evidence_coverage_below_threshold, "medium",
                    "Evidence coverage below review threshold",
                    f"Evidence coverage for {strategy.name} is {score:.0f}/100 (threshold: 70).",
                    {
                        "evidence_coverage_score": score,
                        "missing_count": cov.missing_count,
                        "suggested_check": "Review missing evidence cells on the Evidence Coverage Matrix.",
                    },
                ))
        except Exception:
            pass

        # CHECK B: Strategy health critical/review
        try:
            health = compute_strategy_health(strategy.id, db)
            if health.health_status == "critical":
                candidates.append(_strat_candidate(
                    strategy, sid, AlertRuleType.strategy_health_review_or_critical, "critical",
                    f"Strategy health is critical: {strategy.name}",
                    f"Strategy {strategy.name} has health status: critical. "
                    f"Primary concern: {health.primary_concern}",
                    {
                        "health_status": health.health_status,
                        "primary_concern": health.primary_concern,
                        "health_score": health.health_score,
                        "suggested_check": "Review all open alerts and evidence gaps for this strategy.",
                    },
                ))
            elif health.health_status == "review":
                candidates.append(_strat_candidate(
                    strategy, sid, AlertRuleType.strategy_health_review_or_critical, "high",
                    f"Strategy health requires review: {strategy.name}",
                    f"Strategy {strategy.name} has health status: review. "
                    f"Primary concern: {health.primary_concern}",
                    {
                        "health_status": health.health_status,
                        "primary_concern": health.primary_concern,
                        "health_score": health.health_score,
                        "suggested_check": "Review open alerts and evidence gaps for this strategy.",
                    },
                ))
        except Exception:
            pass

        # CHECK C: Reliability score deterioration
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
                sev = None
                if delta <= -15:
                    sev = "high"
                    title = f"Reliability score deteriorated significantly: {strategy.name}"
                elif delta <= -7:
                    sev = "medium"
                    title = f"Reliability score deteriorated: {strategy.name}"
                if sev is not None:
                    candidates.append(_strat_candidate(
                        strategy, sid, AlertRuleType.reliability_score_deteriorating, sev,
                        title,
                        f"Reliability score changed from {prev_rs.overall_score:.1f} to "
                        f"{latest_rs.overall_score:.1f} (delta: {delta:.1f}).",
                        {
                            "previous_score": prev_rs.overall_score,
                            "latest_score": latest_rs.overall_score,
                            "delta": delta,
                            "suggested_check": "Compute a fresh reliability score after resolving flagged evidence items.",
                        },
                    ))
        except Exception:
            pass

        # CHECK D: Data health deterioration
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
            dh_sev = dh_title = dh_desc = None
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
                candidates.append(_strat_candidate(
                    strategy, sid, AlertRuleType.data_health_deteriorating, dh_sev,
                    dh_title, dh_desc,
                    {
                        "previous_value": dh_prev,
                        "latest_value": dh_latest,
                        "delta": dh_delta,
                        "suggested_check": "Inspect Dataset Snapshots on the Strategy Detail page.",
                    },
                ))
        except Exception:
            pass

        # CHECK E: Signal quality deterioration
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
            sq_sev = sq_title = sq_desc = None
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
                candidates.append(_strat_candidate(
                    strategy, sid, AlertRuleType.signal_quality_deteriorating, sq_sev,
                    sq_title, sq_desc,
                    {
                        "previous_value": sq_prev,
                        "latest_value": sq_latest,
                        "delta": sq_delta,
                        "suggested_check": "Inspect Signal Snapshots and quality scores on the Strategy Detail page.",
                    },
                ))
        except Exception:
            pass

        # CHECK F: Backtest trust deterioration
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
            bt_sev = bt_title = bt_desc = None
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
                candidates.append(_strat_candidate(
                    strategy, sid, AlertRuleType.backtest_trust_deteriorating, bt_sev,
                    bt_title, bt_desc,
                    {
                        "previous_value": bt_prev,
                        "latest_value": bt_latest,
                        "delta": bt_delta,
                        "suggested_check": "Run Backtest Reality Check again after updating cost and fill assumptions.",
                    },
                ))
        except Exception:
            pass

        # CHECK G: Stale strategy run
        try:
            latest_run_at = (
                db.query(func.max(StrategyRun.created_at))
                .filter(StrategyRun.strategy_id == strategy.id)
                .scalar()
            )
            if latest_run_at is None:
                candidates.append(_strat_candidate(
                    strategy, sid, AlertRuleType.stale_strategy_run, "medium",
                    f"No strategy runs logged: {strategy.name}",
                    f"Strategy '{strategy.name}' has no strategy runs logged. "
                    f"Log at least one run to begin evidence tracking.",
                    {
                        "days_since_latest_run": None,
                        "suggested_check": "Log at least one strategy run to begin evidence tracking.",
                    },
                ))
            else:
                latest_run_at_tz = (
                    latest_run_at.replace(tzinfo=timezone.utc)
                    if latest_run_at.tzinfo is None else latest_run_at
                )
                days_stale = (now - latest_run_at_tz).days
                stale_sev = stale_title = None
                threshold = None
                if days_stale > 90:
                    stale_sev = "medium"
                    stale_title = f"Strategy run is very stale ({days_stale} days old): {strategy.name}"
                    threshold = 90
                elif days_stale > 30:
                    stale_sev = "low"
                    stale_title = f"Strategy run is stale ({days_stale} days old): {strategy.name}"
                    threshold = 30
                if stale_sev is not None:
                    candidates.append(_strat_candidate(
                        strategy, sid, AlertRuleType.stale_strategy_run, stale_sev,
                        stale_title,
                        f"Strategy '{strategy.name}' last had a run logged {days_stale} days ago.",
                        {
                            "latest_run_at": str(latest_run_at),
                            "days_since_latest_run": days_stale,
                            "threshold_days": threshold,
                            "suggested_check": "Log a new strategy run to keep evidence fresh.",
                        },
                    ))
        except Exception:
            pass

        # CHECK H: Missing evidence (only if strategy has at least 1 run)
        try:
            run_count = (
                db.query(func.count(StrategyRun.id))
                .filter(StrategyRun.strategy_id == strategy.id)
                .scalar()
            ) or 0
            if run_count > 0:
                sig_count = (
                    db.query(func.count(SignalSnapshot.id))
                    .filter(SignalSnapshot.strategy_id == strategy.id).scalar()
                ) or 0
                uni_count = (
                    db.query(func.count(UniverseSnapshot.id))
                    .filter(UniverseSnapshot.strategy_id == strategy.id).scalar()
                ) or 0
                cfg_count = (
                    db.query(func.count(StrategyConfigSnapshot.id))
                    .filter(StrategyConfigSnapshot.strategy_id == strategy.id).scalar()
                ) or 0
                if sig_count == 0:
                    candidates.append(_strat_candidate(
                        strategy, sid, AlertRuleType.missing_signal_evidence, "low",
                        f"No signal snapshots logged: {strategy.name}",
                        f"Strategy '{strategy.name}' has {run_count} run(s) but no signal snapshots.",
                        {
                            "run_count": run_count,
                            "signal_snapshot_count": 0,
                            "suggested_check": "Log a signal snapshot to capture signal quality evidence.",
                        },
                    ))
                if uni_count == 0:
                    candidates.append(_strat_candidate(
                        strategy, sid, AlertRuleType.missing_universe_evidence, "low",
                        f"No universe snapshots logged: {strategy.name}",
                        f"Strategy '{strategy.name}' has {run_count} run(s) but no universe snapshots.",
                        {
                            "run_count": run_count,
                            "universe_snapshot_count": 0,
                            "suggested_check": "Log a universe snapshot to capture universe evidence.",
                        },
                    ))
                if cfg_count == 0:
                    candidates.append(_strat_candidate(
                        strategy, sid, AlertRuleType.missing_config_evidence, "low",
                        f"No config snapshots logged: {strategy.name}",
                        f"Strategy '{strategy.name}' has {run_count} run(s) but no config snapshots.",
                        {
                            "run_count": run_count,
                            "config_snapshot_count": 0,
                            "suggested_check": "Log a config snapshot to capture configuration evidence.",
                        },
                    ))
        except Exception:
            pass

        # CHECK I: Repeated failed ingestion
        try:
            from app.models.sdk_ingestion_batch import SdkIngestionBatch

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
                candidates.append(_strat_candidate(
                    strategy, sid, AlertRuleType.repeated_failed_ingestion, ing_sev,
                    f"Repeated ingestion failures: {strategy.name}",
                    f"{failed_count} failed ingestion batch(es) in the last 7 days.",
                    {
                        "failed_count": failed_count,
                        "window_days": 7,
                        "suggested_check": "Investigate recent ingestion failures.",
                    },
                ))
        except Exception:
            pass

    return candidates


# ---------------------------------------------------------------------------
# Candidate collection — M85 new lifecycle checks
# ---------------------------------------------------------------------------

def _collect_lifecycle_candidates(
    db: Session,
    strategies: list[Strategy],
) -> list[AlertCandidate]:
    """M85 new checks.  Each subsystem call is wrapped in try/except."""
    from app.models.report import Report

    now = datetime.now(timezone.utc)
    candidates: list[AlertCandidate] = []

    for strategy in strategies:
        sid_hex = _hexid(strategy.id)
        sid_str = str(strategy.id)

        # regression_test_failed: latest regression run with failed tests
        try:
            from app.services.regression_tests import get_regression_test_runs

            runs = get_regression_test_runs(strategy.id, db, limit=1)
            if runs:
                rtr = runs[0]
                if (rtr.failed_count or 0) > 0 or str(rtr.overall_status) == "failed":
                    candidates.append(AlertCandidate(
                        rule_type=str(AlertRuleType.regression_test_failed),
                        severity="high",
                        title=f"Regression tests failing: {strategy.name}",
                        description=(
                            f"Latest regression suite for '{strategy.name}' has "
                            f"{rtr.failed_count} failing test(s) "
                            f"(status: {rtr.overall_status})."
                        ),
                        source_type="regression_test_run",
                        source_id=str(rtr.id),
                        strategy_id=sid_hex,
                        metadata={
                            "failed_count": rtr.failed_count,
                            "required_failed_count": rtr.required_failed_count,
                            "overall_status": rtr.overall_status,
                        },
                    ))
        except Exception:
            pass

        # evidence_sla_breached: latest SLA evaluation in breach/at_risk
        try:
            from app.services.evidence_sla import (
                get_evidence_sla_evaluations,
                get_evidence_sla_policies,
                evaluate_evidence_sla_policy,
            )

            evals = get_evidence_sla_evaluations(db, sid_str, limit=1)
            evaluation = evals[0] if evals else None
            if evaluation is None:
                policies = get_evidence_sla_policies(db, sid_str)
                if policies:
                    evaluation = evaluate_evidence_sla_policy(db, sid_str, str(policies[0].id))
            if evaluation is not None:
                status = str(evaluation.overall_status)
                if status in ("breach", "breached", "at_risk", "violated", "warning"):
                    sev = "high" if status in ("breach", "breached", "violated") else "medium"
                    candidates.append(AlertCandidate(
                        rule_type=str(AlertRuleType.evidence_sla_breached),
                        severity=sev,
                        title=f"Evidence SLA {status}: {strategy.name}",
                        description=(
                            f"Evidence SLA for '{strategy.name}' is {status}. "
                            f"Refresh the stale or missing evidence in the SLA monitor."
                        ),
                        source_type="evidence_sla",
                        source_id=sid_str,
                        strategy_id=sid_hex,
                        metadata={"overall_status": status},
                    ))
        except Exception:
            pass

        # report_missing_after_latest_run
        try:
            latest_run_at = (
                db.query(func.max(StrategyRun.created_at))
                .filter(StrategyRun.strategy_id == strategy.id)
                .scalar()
            )
            if latest_run_at is not None:
                latest_run_at_tz = (
                    latest_run_at.replace(tzinfo=timezone.utc)
                    if latest_run_at.tzinfo is None else latest_run_at
                )
                has_report = (
                    db.query(func.count(Report.id))
                    .filter(
                        Report.strategy_id == strategy.id,
                        Report.report_type == "strategy_reliability",
                        Report.created_at >= latest_run_at_tz,
                    )
                    .scalar()
                ) or 0
                if has_report == 0:
                    candidates.append(AlertCandidate(
                        rule_type=str(AlertRuleType.reliability_report_missing),
                        severity="low",
                        title=f"Reliability report missing for latest run: {strategy.name}",
                        description=(
                            f"Strategy '{strategy.name}' has runs but no reliability report "
                            f"generated after its latest run."
                        ),
                        source_type="strategy",
                        source_id=sid_str,
                        strategy_id=sid_hex,
                        metadata={"latest_run_at": str(latest_run_at)},
                    ))
        except Exception:
            pass

        # promotion_gate_blocked
        try:
            from app.services.promotion_gates import evaluate_promotion_gates

            gate = evaluate_promotion_gates(strategy.id, "paper_candidate", db)
            if (gate.blocker_count or 0) > 0:
                candidates.append(AlertCandidate(
                    rule_type=str(AlertRuleType.promotion_gate_blocked),
                    severity="high",
                    title=f"Promotion blocked by gates: {strategy.name}",
                    description=(
                        f"Strategy '{strategy.name}' has {gate.blocker_count} blocking "
                        f"promotion gate(s) toward paper_candidate "
                        f"(verdict: {gate.promotion_verdict})."
                    ),
                    source_type="promotion_gates",
                    source_id=sid_str,
                    strategy_id=sid_hex,
                    metadata={
                        "blocker_count": gate.blocker_count,
                        "promotion_verdict": gate.promotion_verdict,
                        "target_stage": "paper_candidate",
                    },
                ))
        except Exception:
            pass

        # paper_backtest_drift
        try:
            from app.services.strategy_drift import compute_strategy_drift

            drift = compute_strategy_drift(strategy.id, db)
            if str(drift.drift_status) in ("review", "severe", "high"):
                sev = "high" if str(drift.drift_status) in ("severe", "high") else "medium"
                candidates.append(AlertCandidate(
                    rule_type=str(AlertRuleType.paper_backtest_drift),
                    severity=sev,
                    title=f"Drift detected: {strategy.name}",
                    description=(
                        f"Strategy '{strategy.name}' shows {drift.drift_status}-level drift "
                        f"between compared runs (score: {drift.drift_score})."
                    ),
                    source_type="strategy",
                    source_id=sid_str,
                    strategy_id=sid_hex,
                    metadata={
                        "drift_status": drift.drift_status,
                        "drift_score": drift.drift_score,
                    },
                ))
        except Exception:
            pass

        # paper_backtest_drift (shadow monitor secondary check)
        try:
            from app.services.shadow_monitor import compare_backtest_to_paper, get_latest_live_like_run

            live_run = get_latest_live_like_run(strategy.id, db)
            if live_run is not None:
                sm = compare_backtest_to_paper(strategy.id, db)
                if sm.severity in ("high", "critical") and sm.verdict == "drifted":
                    sev = "critical" if sm.severity == "critical" else "high"
                    candidates.append(AlertCandidate(
                        rule_type=str(AlertRuleType.paper_backtest_drift),
                        severity=sev,
                        title=f"Paper/backtest drift: {strategy.name}",
                        description=(
                            f"Shadow monitor detected {sm.verdict}-level drift for '{strategy.name}'. "
                            f"Drift score: {sm.drift_score:.0f}/100. {sm.primary_concern or ''}"
                        ),
                        source_type="strategy",
                        source_id=sid_str,
                        strategy_id=sid_hex,
                        metadata={
                            "verdict": sm.verdict,
                            "drift_score": sm.drift_score,
                            "severity": sm.severity,
                        },
                    ))
        except Exception:
            pass

        # assumption_health_degraded
        try:
            from app.services.assumption_health import compute_assumption_health

            ah = compute_assumption_health(strategy.id, db)
            ah_status = str(ah.get("status"))
            if ah_status in ("review", "weak"):
                sev = "high" if ah_status == "weak" else "medium"
                candidates.append(AlertCandidate(
                    rule_type=str(AlertRuleType.assumption_health_degraded),
                    severity=sev,
                    title=f"Assumption health {ah_status}: {strategy.name}",
                    description=(
                        f"Assumption health for '{strategy.name}' is {ah_status}. "
                        f"Strengthen the weak assumption categories."
                    ),
                    source_type="strategy",
                    source_id=sid_str,
                    strategy_id=sid_hex,
                    metadata={"overall_status": ah_status, "score": ah.get("score")},
                ))
        except Exception:
            pass

        # run_missing_linked_evidence: latest run missing any of the core links
        try:
            latest_run = (
                db.query(StrategyRun)
                .filter(StrategyRun.strategy_id == strategy.id)
                .order_by(StrategyRun.created_at.desc())
                .first()
            )
            if latest_run is not None:
                missing = []
                if latest_run.dataset_snapshot_id is None:
                    missing.append("dataset")
                if latest_run.signal_snapshot_id is None:
                    missing.append("signal")
                if latest_run.universe_snapshot_id is None:
                    missing.append("universe")
                if latest_run.strategy_version_id is None:
                    missing.append("version")
                if missing:
                    candidates.append(AlertCandidate(
                        rule_type=str(AlertRuleType.run_missing_linked_evidence),
                        severity="medium" if len(missing) >= 3 else "low",
                        title=f"Latest run missing evidence links: {strategy.name}",
                        description=(
                            f"Latest run '{latest_run.run_name}' for '{strategy.name}' is "
                            f"missing linked evidence: {', '.join(missing)}."
                        ),
                        source_type="strategy_run",
                        source_id=str(latest_run.id),
                        strategy_id=sid_hex,
                        metadata={"missing_links": missing, "run_name": latest_run.run_name},
                    ))
        except Exception:
            pass

    return candidates


# ---------------------------------------------------------------------------
# Strategy loading helpers
# ---------------------------------------------------------------------------

def _load_org_strategies(db: Session, organization_id) -> list[Strategy]:
    """Return all non-archived strategies for the org (via Project join)."""
    org_uuid = _org_uuid(organization_id)
    if org_uuid is None:
        return []
    return (
        db.query(Strategy)
        .join(Project, Strategy.project_id == Project.id)
        .filter(
            Project.organization_id == org_uuid,
            Strategy.status != "archived",
        )
        .all()
    )


def _org_id_for_strategy(db: Session, strategy_id) -> str | None:
    """Resolve the organization id (hex) that owns *strategy_id*."""
    row = (
        db.query(Project.organization_id)
        .join(Strategy, Strategy.project_id == Project.id)
        .filter(Strategy.id == strategy_id)
        .first()
    )
    if row is None:
        return None
    return _hexid(row[0])


# ---------------------------------------------------------------------------
# Reconcile engine — M85
# ---------------------------------------------------------------------------

def reconcile_alerts(
    db: Session,
    organization_id: str,
    candidates: list[AlertCandidate],
    scope_strategy_id: str | None = None,
) -> dict:
    """Drive the full alert lifecycle for a set of firing *candidates*.

    Returns a dict with counts: alerts_created, alerts_skipped_duplicate,
    alerts_auto_resolved, total_alerts_open.
    """
    now = datetime.now(timezone.utc)
    org_id_str = _org_id_str(organization_id)
    scope_hex = _hexid(scope_strategy_id) if scope_strategy_id is not None else None

    created = 0
    skipped = 0
    auto_resolved = 0

    def _scope_query():
        q = db.query(Alert).filter(Alert.organization_id == org_id_str)
        if scope_hex is not None:
            q = q.filter(Alert.strategy_id == scope_hex)
        return q

    # ------------------------------------------------------------------
    # 1. Reactivate expired snoozes
    # ------------------------------------------------------------------
    expired = (
        _scope_query()
        .filter(
            Alert.status == str(AlertStatus.snoozed),
            Alert.snoozed_until.isnot(None),
            Alert.snoozed_until < now,
        )
        .all()
    )
    for alert in expired:
        alert.status = str(AlertStatus.open)
        record_alert_history(db, str(alert.id), None, str(AlertAction.snooze_expired))

    # ------------------------------------------------------------------
    # 2. Build firing keys + index of existing active alerts by key
    # ------------------------------------------------------------------
    firing_keys = {c.key() for c in candidates}

    existing = _scope_query().all()
    active_keys: set = set()
    for alert in existing:
        if str(alert.status) in (str(s) for s in _ACTIVE_STATUSES):
            active_keys.add(
                (str(alert.rule_type), str(alert.source_type), str(alert.source_id))
            )

    # ------------------------------------------------------------------
    # 3. Create / skip per candidate
    # ------------------------------------------------------------------
    for cand in candidates:
        key = cand.key()
        if key in active_keys:
            skipped += 1
            continue
        rule_type = str(cand.rule_type)
        alert = Alert(
            organization_id=org_id_str,
            rule_type=rule_type,
            status=str(AlertStatus.open),
            severity=cand.severity,
            title=cand.title,
            description=cand.description,
            source_type=cand.source_type,
            source_id=str(cand.source_id),
            strategy_id=cand.strategy_id,
            triggered_at=now,
            recommended_fix=recommended_fix_for(rule_type),
            metadata_json=cand.metadata or {},
        )
        db.add(alert)
        db.flush()  # assign id for history FK
        record_alert_history(db, str(alert.id), None, str(AlertAction.created))
        active_keys.add(key)
        created += 1

    # ------------------------------------------------------------------
    # 4. Auto-resolve open/acknowledged alerts no longer firing
    # ------------------------------------------------------------------
    resolvable = (
        _scope_query()
        .filter(Alert.status.in_([str(AlertStatus.open), str(AlertStatus.acknowledged)]))
        .all()
    )
    for alert in resolvable:
        key = (str(alert.rule_type), str(alert.source_type), str(alert.source_id))
        if key not in firing_keys:
            alert.status = str(AlertStatus.resolved)
            alert.resolved_at = now
            record_alert_history(db, str(alert.id), None, str(AlertAction.auto_resolved))
            auto_resolved += 1

    db.flush()

    total_open = (
        _scope_query().filter(Alert.status == str(AlertStatus.open)).count()
    )

    return {
        "alerts_created": created,
        "alerts_skipped_duplicate": skipped,
        "alerts_auto_resolved": auto_resolved,
        "total_alerts_open": total_open,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_alerts(db: Session, organization_id: str) -> GenerateResult:
    """Collect all candidates (legacy + evidence-quality + M85) for the org and
    reconcile them.  Auto-resolves across the whole org (no strategy scope).
    """
    org_id_str = _org_id_str(organization_id)
    strategies = _load_org_strategies(db, organization_id)

    candidates: list[AlertCandidate] = []
    candidates += _collect_legacy_candidates(db, org_id_str)
    candidates += _collect_evidence_quality_candidates(db, strategies)
    candidates += _collect_lifecycle_candidates(db, strategies)

    counts = reconcile_alerts(db, organization_id, candidates, scope_strategy_id=None)

    return GenerateResult(
        alerts_created=counts["alerts_created"],
        alerts_skipped_duplicate=counts["alerts_skipped_duplicate"],
        alerts_auto_resolved=counts["alerts_auto_resolved"],
        total_alerts_open=counts["total_alerts_open"],
    )


def generate_alerts_for_strategy(db: Session, strategy_id: str) -> dict:
    """Collect candidates for a single strategy and reconcile within that
    strategy's scope (auto-resolve only touches THAT strategy's alerts).
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        return {
            "alerts_created": 0,
            "alerts_skipped_duplicate": 0,
            "alerts_auto_resolved": 0,
            "total_alerts_open": 0,
        }
    org_id_str = _org_id_for_strategy(db, strategy_id)
    if org_id_str is None:
        return {
            "alerts_created": 0,
            "alerts_skipped_duplicate": 0,
            "alerts_auto_resolved": 0,
            "total_alerts_open": 0,
        }

    strategies = [strategy]
    candidates: list[AlertCandidate] = []
    candidates += _collect_evidence_quality_candidates(db, strategies)
    candidates += _collect_lifecycle_candidates(db, strategies)
    # Legacy strategy-scoped candidates: backtest/run checks tied to this strategy.
    for cand in _collect_legacy_candidates(db, org_id_str):
        if cand.strategy_id is not None and cand.strategy_id == _hexid(strategy_id):
            candidates.append(cand)

    return reconcile_alerts(
        db, org_id_str, candidates, scope_strategy_id=str(strategy_id)
    )


# ---------------------------------------------------------------------------
# M33 back-compat shim (kept for callers that import it directly)
# ---------------------------------------------------------------------------

def run_evidence_quality_alerts(organization_id: str, db: Session) -> dict:
    """Back-compat: collect + reconcile only the evidence-quality candidates."""
    strategies = _load_org_strategies(db, organization_id)
    candidates = _collect_evidence_quality_candidates(db, strategies)
    counts = reconcile_alerts(db, organization_id, candidates, scope_strategy_id=None)
    return {"created": counts["alerts_created"], "skipped": counts["alerts_skipped_duplicate"]}


# ---------------------------------------------------------------------------
# Summaries / counts
# ---------------------------------------------------------------------------

def get_open_alert_count(db: Session, organization_id: str) -> int:
    """Count all open alerts for the organisation."""
    return (
        db.query(Alert)
        .filter(
            Alert.organization_id == _org_id_str(organization_id),
            Alert.status == str(AlertStatus.open),
        )
        .count()
    )


def get_high_critical_alert_count(db: Session, organization_id: str) -> int:
    """Count open alerts with severity high or critical."""
    return (
        db.query(Alert)
        .filter(
            Alert.organization_id == _org_id_str(organization_id),
            Alert.status == str(AlertStatus.open),
            Alert.severity.in_(["high", "critical"]),
        )
        .count()
    )


def get_strategy_alert_summary(db: Session, strategy_id: str) -> dict:
    """Return a status/severity breakdown of alerts for a single strategy."""
    sid_hex = _hexid(strategy_id)
    alerts = db.query(Alert).filter(Alert.strategy_id == sid_hex).all()

    summary = {
        "open": 0,
        "acknowledged": 0,
        "snoozed": 0,
        "resolved": 0,
        "by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "blocking_promotion": 0,
    }
    for alert in alerts:
        status = str(alert.status)
        if status in summary:
            summary[status] += 1
        if status == str(AlertStatus.open):
            sev = str(alert.severity)
            if sev in summary["by_severity"]:
                summary["by_severity"][sev] += 1
            if str(alert.rule_type) in _BLOCKING_RULE_TYPES:
                summary["blocking_promotion"] += 1
    return summary
