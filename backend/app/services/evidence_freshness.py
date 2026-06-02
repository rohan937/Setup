"""Evidence Freshness service — M48.

Computes a deterministic, evidence-based freshness scorecard for each evidence type
associated with a strategy.

No AI, no live market data, no AuditTimelineEvent created.
Language is hedged — no investment advice, no trading recommendations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FRESHNESS_CONFIGS: dict[str, dict[str, Any]] = {
    "strategy_runs": {
        "fresh_days": 14,
        "aging_days": 30,
        "weight": 0.15,
        "label": "Strategy Runs",
        "suggested_check_template": "Log at least one strategy run.",
    },
    "dataset_snapshots": {
        "fresh_days": 14,
        "aging_days": 45,
        "weight": 0.15,
        "label": "Dataset Snapshots",
        "suggested_check_template": "Link a dataset snapshot to a strategy run.",
    },
    "signal_snapshots": {
        "fresh_days": 14,
        "aging_days": 30,
        "weight": 0.15,
        "label": "Signal Snapshots",
        "suggested_check_template": "Log a signal snapshot.",
    },
    "universe_snapshots": {
        "fresh_days": 30,
        "aging_days": 90,
        "weight": 0.10,
        "label": "Universe Snapshots",
        "suggested_check_template": "Log a universe snapshot.",
    },
    "config_snapshots": {
        "fresh_days": 30,
        "aging_days": 90,
        "weight": 0.10,
        "label": "Config Snapshots",
        "suggested_check_template": "Log a config snapshot.",
    },
    "backtest_audits": {
        "fresh_days": 14,
        "aging_days": 45,
        "weight": 0.15,
        "label": "Backtest Audits",
        "suggested_check_template": "Run Backtest Reality Check.",
    },
    "reliability_scores": {
        "fresh_days": 7,
        "aging_days": 30,
        "weight": 0.10,
        "label": "Reliability Scores",
        "suggested_check_template": "Compute a reliability score.",
    },
    "reports": {
        "fresh_days": 30,
        "aging_days": 90,
        "weight": 0.05,
        "label": "Reports",
        "suggested_check_template": "Generate a strategy reliability report.",
    },
    "timeline_events": {
        "fresh_days": 14,
        "aging_days": 45,
        "weight": 0.05,
        "label": "Timeline Events",
        "suggested_check_template": "Log evidence to generate timeline events.",
    },
    "alerts": {
        "fresh_days": 7,
        "aging_days": 30,
        "weight": 0.00,
        "label": "Alerts",
        "suggested_check_template": "Generate alerts to assess evidence quality.",
    },
}

SCORE_MAP: dict[str, int] = {
    "fresh": 100,
    "aging": 70,
    "stale": 35,
    "missing": 0,
}

SEVERITY_MAP: dict[str, str] = {
    "fresh": "info",
    "aging": "low",
    "stale": "medium",
    "missing": "high",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class EvidenceFreshnessItemData:
    evidence_type: str
    label: str
    status: str
    severity: str
    summary: str
    latest_at: datetime | None
    days_since_latest: int | None
    count: int
    threshold_days: int
    suggested_check: str | None
    latest_object_id: str | None
    latest_object_label: str | None


@dataclass
class StrategyEvidenceFreshnessData:
    strategy_id: uuid.UUID
    strategy_name: str
    generated_at: datetime
    overall_freshness_score: float | None
    freshness_status: str
    evidence_items: list[EvidenceFreshnessItemData]
    stale_count: int
    missing_count: int
    aging_count: int
    fresh_count: int
    oldest_evidence_type: str | None
    freshest_evidence_type: str | None
    suggested_refresh_order: list[str]
    deterministic_summary: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _freshness_status(days_since: int | None, fresh_days: int, aging_days: int) -> str:
    if days_since is None:
        return "missing"
    if days_since <= fresh_days:
        return "fresh"
    elif days_since <= aging_days:
        return "aging"
    else:
        return "stale"


def _normalize_ts(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Main compute function
# ---------------------------------------------------------------------------


def compute_evidence_freshness(
    strategy_id: uuid.UUID, db: Session
) -> StrategyEvidenceFreshnessData:
    """Compute deterministic evidence freshness for a strategy.

    Returns a StrategyEvidenceFreshnessData dataclass. Does not create any
    AuditTimelineEvent — this is a read-only operation.
    Raises ValueError if the strategy does not exist.
    """
    from app.models.strategy import Strategy

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    now = datetime.now(timezone.utc)
    items: list[EvidenceFreshnessItemData] = []

    # ------------------------------------------------------------------
    # 1. strategy_runs
    # ------------------------------------------------------------------
    from app.models.strategy_run import StrategyRun

    latest_run = (
        db.query(StrategyRun)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(StrategyRun.created_at.desc())
        .first()
    )
    run_count = (
        db.query(func.count(StrategyRun.id))
        .filter(StrategyRun.strategy_id == strategy_id)
        .scalar()
        or 0
    )
    latest_run_at = _normalize_ts(latest_run.created_at) if latest_run else None
    days_run = (now - latest_run_at).days if latest_run_at else None
    cfg = FRESHNESS_CONFIGS["strategy_runs"]
    status = _freshness_status(days_run, cfg["fresh_days"], cfg["aging_days"])
    items.append(
        EvidenceFreshnessItemData(
            evidence_type="strategy_runs",
            label=cfg["label"],
            latest_at=latest_run_at,
            days_since_latest=days_run,
            count=run_count,
            status=status,
            threshold_days=cfg["aging_days"],
            severity=SEVERITY_MAP[status],
            summary=(
                f"{run_count} run(s), latest {days_run}d ago"
                if days_run is not None
                else "No runs logged"
            ),
            suggested_check=(
                "Log at least one strategy run."
                if status == "missing"
                else (
                    f"Log a new run; latest is {days_run}d old."
                    if status == "stale"
                    else None
                )
            ),
            latest_object_id=str(latest_run.id) if latest_run else None,
            latest_object_label=latest_run.run_name if latest_run else None,
        )
    )

    # ------------------------------------------------------------------
    # 2. dataset_snapshots (via StrategyRun.dataset_snapshot_id)
    # ------------------------------------------------------------------
    from app.models.dataset_snapshot import DatasetSnapshot

    latest_ds_row = (
        db.query(DatasetSnapshot.id, DatasetSnapshot.version_label, DatasetSnapshot.created_at)
        .join(StrategyRun, StrategyRun.dataset_snapshot_id == DatasetSnapshot.id)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(DatasetSnapshot.created_at.desc())
        .first()
    )
    ds_count = (
        db.query(func.count(func.distinct(DatasetSnapshot.id)))
        .join(StrategyRun, StrategyRun.dataset_snapshot_id == DatasetSnapshot.id)
        .filter(StrategyRun.strategy_id == strategy_id)
        .scalar()
        or 0
    )
    latest_ds_at = _normalize_ts(latest_ds_row[2]) if latest_ds_row else None
    days_ds = (now - latest_ds_at).days if latest_ds_at else None
    cfg = FRESHNESS_CONFIGS["dataset_snapshots"]
    status = _freshness_status(days_ds, cfg["fresh_days"], cfg["aging_days"])
    items.append(
        EvidenceFreshnessItemData(
            evidence_type="dataset_snapshots",
            label=cfg["label"],
            latest_at=latest_ds_at,
            days_since_latest=days_ds,
            count=ds_count,
            status=status,
            threshold_days=cfg["aging_days"],
            severity=SEVERITY_MAP[status],
            summary=(
                f"{ds_count} linked snapshot(s)"
                + (f", latest {days_ds}d ago" if days_ds is not None else "")
            ),
            suggested_check=(
                "Link a dataset snapshot to a strategy run."
                if status == "missing"
                else ("Refresh dataset evidence." if status == "stale" else None)
            ),
            latest_object_id=str(latest_ds_row[0]) if latest_ds_row else None,
            latest_object_label=latest_ds_row[1] if latest_ds_row else None,
        )
    )

    # ------------------------------------------------------------------
    # 3. signal_snapshots (strategy_id direct)
    # ------------------------------------------------------------------
    from app.models.signal_snapshot import SignalSnapshot

    latest_sig = (
        db.query(SignalSnapshot)
        .filter(SignalSnapshot.strategy_id == strategy_id)
        .order_by(SignalSnapshot.created_at.desc())
        .first()
    )
    sig_count = (
        db.query(func.count(SignalSnapshot.id))
        .filter(SignalSnapshot.strategy_id == strategy_id)
        .scalar()
        or 0
    )
    latest_sig_at = _normalize_ts(latest_sig.created_at) if latest_sig else None
    days_sig = (now - latest_sig_at).days if latest_sig_at else None
    cfg = FRESHNESS_CONFIGS["signal_snapshots"]
    status = _freshness_status(days_sig, cfg["fresh_days"], cfg["aging_days"])
    items.append(
        EvidenceFreshnessItemData(
            evidence_type="signal_snapshots",
            label=cfg["label"],
            latest_at=latest_sig_at,
            days_since_latest=days_sig,
            count=sig_count,
            status=status,
            threshold_days=cfg["aging_days"],
            severity=SEVERITY_MAP[status],
            summary=(
                f"{sig_count} signal snapshot(s)"
                + (f", latest {days_sig}d ago" if days_sig is not None else "")
            ),
            suggested_check=(
                "Log a signal snapshot."
                if status == "missing"
                else ("Refresh signal evidence." if status == "stale" else None)
            ),
            latest_object_id=str(latest_sig.id) if latest_sig else None,
            latest_object_label=latest_sig.label if latest_sig else None,
        )
    )

    # ------------------------------------------------------------------
    # 4. universe_snapshots
    # ------------------------------------------------------------------
    from app.models.universe_snapshot import UniverseSnapshot

    latest_uni = (
        db.query(UniverseSnapshot)
        .filter(UniverseSnapshot.strategy_id == strategy_id)
        .order_by(UniverseSnapshot.created_at.desc())
        .first()
    )
    uni_count = (
        db.query(func.count(UniverseSnapshot.id))
        .filter(UniverseSnapshot.strategy_id == strategy_id)
        .scalar()
        or 0
    )
    latest_uni_at = _normalize_ts(latest_uni.created_at) if latest_uni else None
    days_uni = (now - latest_uni_at).days if latest_uni_at else None
    cfg = FRESHNESS_CONFIGS["universe_snapshots"]
    status = _freshness_status(days_uni, cfg["fresh_days"], cfg["aging_days"])
    items.append(
        EvidenceFreshnessItemData(
            evidence_type="universe_snapshots",
            label=cfg["label"],
            latest_at=latest_uni_at,
            days_since_latest=days_uni,
            count=uni_count,
            status=status,
            threshold_days=cfg["aging_days"],
            severity=SEVERITY_MAP[status],
            summary=(
                f"{uni_count} universe snapshot(s)"
                + (f", latest {days_uni}d ago" if days_uni is not None else "")
            ),
            suggested_check=(
                "Log a universe snapshot."
                if status == "missing"
                else ("Refresh universe evidence." if status == "stale" else None)
            ),
            latest_object_id=str(latest_uni.id) if latest_uni else None,
            latest_object_label=latest_uni.label if latest_uni else None,
        )
    )

    # ------------------------------------------------------------------
    # 5. config_snapshots
    # ------------------------------------------------------------------
    from app.models.strategy_config_snapshot import StrategyConfigSnapshot

    latest_cfg_obj = (
        db.query(StrategyConfigSnapshot)
        .filter(StrategyConfigSnapshot.strategy_id == strategy_id)
        .order_by(StrategyConfigSnapshot.created_at.desc())
        .first()
    )
    cfg_count = (
        db.query(func.count(StrategyConfigSnapshot.id))
        .filter(StrategyConfigSnapshot.strategy_id == strategy_id)
        .scalar()
        or 0
    )
    latest_cfg_at = _normalize_ts(latest_cfg_obj.created_at) if latest_cfg_obj else None
    days_cfg = (now - latest_cfg_at).days if latest_cfg_at else None
    conf = FRESHNESS_CONFIGS["config_snapshots"]
    status = _freshness_status(days_cfg, conf["fresh_days"], conf["aging_days"])
    items.append(
        EvidenceFreshnessItemData(
            evidence_type="config_snapshots",
            label=conf["label"],
            latest_at=latest_cfg_at,
            days_since_latest=days_cfg,
            count=cfg_count,
            status=status,
            threshold_days=conf["aging_days"],
            severity=SEVERITY_MAP[status],
            summary=(
                f"{cfg_count} config snapshot(s)"
                + (f", latest {days_cfg}d ago" if days_cfg is not None else "")
            ),
            suggested_check=(
                "Log a config snapshot."
                if status == "missing"
                else ("Refresh config evidence." if status == "stale" else None)
            ),
            latest_object_id=str(latest_cfg_obj.id) if latest_cfg_obj else None,
            latest_object_label=latest_cfg_obj.label if latest_cfg_obj else None,
        )
    )

    # ------------------------------------------------------------------
    # 6. backtest_audits (via StrategyRun)
    # ------------------------------------------------------------------
    from app.models.backtest_audit import BacktestAudit

    latest_audit_row = (
        db.query(BacktestAudit)
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .filter(StrategyRun.strategy_id == strategy_id)
        .order_by(BacktestAudit.created_at.desc())
        .first()
    )
    audit_count = (
        db.query(func.count(BacktestAudit.id))
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .filter(StrategyRun.strategy_id == strategy_id)
        .scalar()
        or 0
    )
    latest_audit_at = _normalize_ts(latest_audit_row.created_at) if latest_audit_row else None
    days_audit = (now - latest_audit_at).days if latest_audit_at else None
    conf = FRESHNESS_CONFIGS["backtest_audits"]
    status = _freshness_status(days_audit, conf["fresh_days"], conf["aging_days"])
    items.append(
        EvidenceFreshnessItemData(
            evidence_type="backtest_audits",
            label=conf["label"],
            latest_at=latest_audit_at,
            days_since_latest=days_audit,
            count=audit_count,
            status=status,
            threshold_days=conf["aging_days"],
            severity=SEVERITY_MAP[status],
            summary=(
                f"{audit_count} audit(s)"
                + (f", latest {days_audit}d ago" if days_audit is not None else "")
            ),
            suggested_check=(
                "Run Backtest Reality Check."
                if status == "missing"
                else ("Rerun Backtest Reality Check." if status == "stale" else None)
            ),
            latest_object_id=str(latest_audit_row.id) if latest_audit_row else None,
            latest_object_label=None,
        )
    )

    # ------------------------------------------------------------------
    # 7. reliability_scores (generated_at)
    # ------------------------------------------------------------------
    from app.models.strategy_reliability_score import StrategyReliabilityScore

    latest_rel = (
        db.query(StrategyReliabilityScore)
        .filter(StrategyReliabilityScore.strategy_id == strategy_id)
        .order_by(StrategyReliabilityScore.generated_at.desc())
        .first()
    )
    rel_count = (
        db.query(func.count(StrategyReliabilityScore.id))
        .filter(StrategyReliabilityScore.strategy_id == strategy_id)
        .scalar()
        or 0
    )
    latest_rel_at = _normalize_ts(latest_rel.generated_at) if latest_rel else None
    days_rel = (now - latest_rel_at).days if latest_rel_at else None
    conf = FRESHNESS_CONFIGS["reliability_scores"]
    status = _freshness_status(days_rel, conf["fresh_days"], conf["aging_days"])
    items.append(
        EvidenceFreshnessItemData(
            evidence_type="reliability_scores",
            label=conf["label"],
            latest_at=latest_rel_at,
            days_since_latest=days_rel,
            count=rel_count,
            status=status,
            threshold_days=conf["aging_days"],
            severity=SEVERITY_MAP[status],
            summary=(
                f"{rel_count} reliability score(s)"
                + (f", latest {days_rel}d ago" if days_rel is not None else "")
            ),
            suggested_check=(
                "Compute a reliability score."
                if status == "missing"
                else ("Recompute reliability score." if status == "stale" else None)
            ),
            latest_object_id=str(latest_rel.id) if latest_rel else None,
            latest_object_label=latest_rel.status if latest_rel else None,
        )
    )

    # ------------------------------------------------------------------
    # 8. reports (generated_at)
    # ------------------------------------------------------------------
    from app.models.report import Report

    latest_report = (
        db.query(Report)
        .filter(Report.strategy_id == strategy_id)
        .order_by(Report.generated_at.desc())
        .first()
    )
    rep_count = (
        db.query(func.count(Report.id))
        .filter(Report.strategy_id == strategy_id)
        .scalar()
        or 0
    )
    latest_rep_at = _normalize_ts(latest_report.generated_at) if latest_report else None
    days_rep = (now - latest_rep_at).days if latest_rep_at else None
    conf = FRESHNESS_CONFIGS["reports"]
    status = _freshness_status(days_rep, conf["fresh_days"], conf["aging_days"])
    items.append(
        EvidenceFreshnessItemData(
            evidence_type="reports",
            label=conf["label"],
            latest_at=latest_rep_at,
            days_since_latest=days_rep,
            count=rep_count,
            status=status,
            threshold_days=conf["aging_days"],
            severity=SEVERITY_MAP[status],
            summary=(
                f"{rep_count} report(s)"
                + (f", latest {days_rep}d ago" if days_rep is not None else "")
            ),
            suggested_check=(
                "Generate a strategy reliability report."
                if status == "missing"
                else ("Refresh strategy report." if status == "stale" else None)
            ),
            latest_object_id=str(latest_report.id) if latest_report else None,
            latest_object_label=latest_report.report_type if latest_report else None,
        )
    )

    # ------------------------------------------------------------------
    # 9. alerts (triggered_at, strategy_id is String(36))
    # ------------------------------------------------------------------
    from app.models.alert import Alert

    latest_alert = (
        db.query(Alert)
        .filter(Alert.strategy_id == str(strategy_id))
        .order_by(Alert.triggered_at.desc())
        .first()
    )
    alert_count = (
        db.query(func.count(Alert.id))
        .filter(Alert.strategy_id == str(strategy_id))
        .scalar()
        or 0
    )
    latest_alert_at = _normalize_ts(latest_alert.triggered_at) if latest_alert else None
    days_alert = (now - latest_alert_at).days if latest_alert_at else None
    conf = FRESHNESS_CONFIGS["alerts"]
    status = (
        "missing"
        if alert_count == 0
        else _freshness_status(days_alert, conf["fresh_days"], conf["aging_days"])
    )
    items.append(
        EvidenceFreshnessItemData(
            evidence_type="alerts",
            label=conf["label"],
            latest_at=latest_alert_at,
            days_since_latest=days_alert,
            count=alert_count,
            status=status,
            threshold_days=conf["aging_days"],
            severity="info" if status == "missing" else SEVERITY_MAP[status],
            summary=(
                f"{alert_count} alert(s)"
                + (
                    f", latest {days_alert}d ago"
                    if days_alert is not None
                    else " (no alerts generated)"
                )
            ),
            suggested_check=(
                "Generate alerts to assess evidence quality."
                if status == "missing"
                else None
            ),
            latest_object_id=str(latest_alert.id) if latest_alert else None,
            latest_object_label=latest_alert.title if latest_alert else None,
        )
    )

    # ------------------------------------------------------------------
    # 10. timeline_events (event_time)
    # ------------------------------------------------------------------
    from app.models.audit_timeline_event import AuditTimelineEvent

    latest_tl = (
        db.query(AuditTimelineEvent)
        .filter(AuditTimelineEvent.strategy_id == strategy_id)
        .order_by(AuditTimelineEvent.event_time.desc())
        .first()
    )
    tl_count = (
        db.query(func.count(AuditTimelineEvent.id))
        .filter(AuditTimelineEvent.strategy_id == strategy_id)
        .scalar()
        or 0
    )
    latest_tl_at = _normalize_ts(latest_tl.event_time) if latest_tl else None
    days_tl = (now - latest_tl_at).days if latest_tl_at else None
    conf = FRESHNESS_CONFIGS["timeline_events"]
    status = _freshness_status(days_tl, conf["fresh_days"], conf["aging_days"])
    items.append(
        EvidenceFreshnessItemData(
            evidence_type="timeline_events",
            label=conf["label"],
            latest_at=latest_tl_at,
            days_since_latest=days_tl,
            count=tl_count,
            status=status,
            threshold_days=conf["aging_days"],
            severity=SEVERITY_MAP[status],
            summary=(
                f"{tl_count} event(s)"
                + (f", latest {days_tl}d ago" if days_tl is not None else "")
            ),
            suggested_check=(
                "Log evidence to generate timeline events."
                if status == "missing"
                else None
            ),
            latest_object_id=str(latest_tl.id) if latest_tl else None,
            latest_object_label=latest_tl.title if latest_tl else None,
        )
    )

    # ------------------------------------------------------------------
    # Overall freshness score (exclude alerts from weighted calc)
    # ------------------------------------------------------------------
    scored_items = [i for i in items if i.evidence_type != "alerts"]
    WEIGHT_MAP = {k: v["weight"] for k, v in FRESHNESS_CONFIGS.items() if k != "alerts"}
    total_weight = sum(WEIGHT_MAP.get(i.evidence_type, 0) for i in scored_items)

    if total_weight == 0:
        overall_score = None
        overall_status = "missing_evidence"
    else:
        meaningful = [i for i in scored_items if WEIGHT_MAP.get(i.evidence_type, 0) > 0]
        if len([m for m in meaningful if m.status != "missing"]) < 3:
            overall_score = None
            overall_status = "missing_evidence"
        else:
            weighted_sum = sum(
                SCORE_MAP.get(i.status, 0) * WEIGHT_MAP.get(i.evidence_type, 0)
                for i in scored_items
            )
            overall_score = round(weighted_sum / total_weight, 1)
            if overall_score >= 85:
                overall_status = "fresh"
            elif overall_score >= 65:
                overall_status = "aging"
            else:
                overall_status = "stale"

    # ------------------------------------------------------------------
    # Counts
    # ------------------------------------------------------------------
    fresh_count = sum(1 for i in items if i.status == "fresh")
    aging_count = sum(1 for i in items if i.status == "aging")
    stale_count = sum(1 for i in items if i.status == "stale")
    missing_count = sum(1 for i in items if i.status == "missing")

    # ------------------------------------------------------------------
    # Oldest and freshest (excluding missing)
    # ------------------------------------------------------------------
    non_missing = [
        i for i in items if i.status != "missing" and i.days_since_latest is not None
    ]
    oldest = max(non_missing, key=lambda x: x.days_since_latest, default=None)
    freshest = min(non_missing, key=lambda x: x.days_since_latest, default=None)

    # ------------------------------------------------------------------
    # Suggested refresh order
    # ------------------------------------------------------------------
    IMPORTANCE: dict[str, int] = {
        "strategy_runs": 0,
        "backtest_audits": 1,
        "dataset_snapshots": 2,
        "signal_snapshots": 3,
        "reliability_scores": 4,
        "universe_snapshots": 5,
        "config_snapshots": 6,
        "reports": 7,
        "timeline_events": 8,
        "alerts": 9,
    }

    def _refresh_sort_key(item: EvidenceFreshnessItemData) -> tuple[int, int]:
        status_rank = (
            0
            if item.status == "stale"
            else 1
            if item.status == "missing"
            else 2
            if item.status == "aging"
            else 3
        )
        return (status_rank, IMPORTANCE.get(item.evidence_type, 9))

    actionable = [i for i in items if i.status in ("stale", "missing", "aging") and i.suggested_check]
    actionable_sorted = sorted(actionable, key=_refresh_sort_key)
    refresh_order = [i.label for i in actionable_sorted]

    # ------------------------------------------------------------------
    # Deterministic summary
    # ------------------------------------------------------------------
    stale_labels = [i.label for i in items if i.status == "stale"]
    aging_labels = [i.label for i in items if i.status == "aging"]
    summary_parts = [
        f"Evidence freshness for {strategy.name} is {overall_status or 'unknown'}."
    ]
    if stale_labels:
        summary_parts.append(f"Stale: {', '.join(stale_labels[:3])}.")
    elif aging_labels:
        summary_parts.append(f"Aging: {', '.join(aging_labels[:3])}.")
    if refresh_order:
        summary_parts.append(f"Recommended to refresh: {', '.join(refresh_order[:3])}.")
    summary_parts.append(
        "This is a deterministic evidence freshness summary, not a trading recommendation."
    )

    return StrategyEvidenceFreshnessData(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        generated_at=now,
        overall_freshness_score=overall_score,
        freshness_status=overall_status or "missing_evidence",
        evidence_items=items,
        stale_count=stale_count,
        missing_count=missing_count,
        aging_count=aging_count,
        fresh_count=fresh_count,
        oldest_evidence_type=oldest.evidence_type if oldest else None,
        freshest_evidence_type=freshest.evidence_type if freshest else None,
        suggested_refresh_order=refresh_order,
        deterministic_summary=" ".join(summary_parts),
    )
