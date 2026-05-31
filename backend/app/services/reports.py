"""Reliability Report generation service — M14.

Generates deterministic, evidence-backed reliability reports from data already
stored in QuantFidelity.  Three report types are supported:

  1. strategy_reliability — aggregates all evidence for a strategy
  2. backtest_audit       — deep-dive on a single backtest audit
  3. dataset_health       — snapshot quality and coverage summary

Design constraints:
  - No AI, no live market data, no external calls.
  - All summaries are hedged ("noted", "observed", "may require review").
  - Scores are null when insufficient evidence — never fabricated.
  - Suggested checks are deterministic and based on detected issues.
  - Language avoids causal claims and trading advice.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session, selectinload

from app.core.constants import AlertStatus
from app.models.alert import Alert
from app.models.audit_timeline_event import AuditTimelineEvent
from app.models.backtest_audit import BacktestAudit
from app.models.backtest_issue import BacktestIssue
from app.models.data_quality_issue import DataQualityIssue
from app.models.dataset_snapshot import DatasetSnapshot
from app.models.report import Report
from app.models.report_section import ReportSection
from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------

_ACTIVE_ALERT_STATUSES = {AlertStatus.open, AlertStatus.acknowledged, AlertStatus.snoozed}
_SEV_RANK = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}


def _worst_severity(severities: list[str]) -> str | None:
    """Return the most severe value from a list, or None for an empty list."""
    best: str | None = None
    best_rank = 0
    for s in severities:
        r = _SEV_RANK.get(s, 0)
        if r > best_rank:
            best_rank = r
            best = s
    return best


def _score_to_section_severity(score: int | None) -> str | None:
    """Map a 0–100 score to section-level severity for colouring."""
    if score is None:
        return None
    if score < 50:
        return "high"
    if score < 75:
        return "medium"
    if score < 90:
        return "low"
    return None


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SectionResult:
    section_key: str
    title: str
    summary: str
    order_index: int
    severity: str | None = None
    evidence_json: dict | None = None


@dataclass
class ReportResult:
    report_type: str
    title: str
    status: str
    summary: str
    generated_at: datetime
    source_type: str
    source_id: str
    score: int | None
    report_json: dict | None
    sections: list[SectionResult] = field(default_factory=list)
    # DB context — populated from source records
    organization_id: str | None = None
    project_id: str | None = None
    strategy_id: str | None = None


# ---------------------------------------------------------------------------
# A. Strategy Reliability Report
# ---------------------------------------------------------------------------

def generate_strategy_reliability_report(
    strategy_id: uuid.UUID,
    db: Session,
) -> ReportResult:
    """Generate a full reliability report for a strategy.

    Aggregates runs, audits, snapshots, alerts, and timeline events into a
    structured, evidence-backed reliability summary.
    """
    strategy = (
        db.query(Strategy)
        .options(
            selectinload(Strategy.runs).selectinload(StrategyRun.backtest_audits).selectinload(BacktestAudit.issues),
            selectinload(Strategy.runs).selectinload(StrategyRun.snapshot).selectinload(DatasetSnapshot.issues),
            selectinload(Strategy.project),
            selectinload(Strategy.alerts),
        )
        .filter(Strategy.id == strategy_id)
        .first()
    )
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    now = datetime.now(timezone.utc)
    runs = sorted(strategy.runs, key=lambda r: r.created_at, reverse=True)
    project = strategy.project

    # ------------------------------------------------------------------
    # Gather evidence
    # ------------------------------------------------------------------

    # All audits across all runs (most recent first)
    all_audits: list[BacktestAudit] = []
    for run in runs:
        all_audits.extend(run.backtest_audits)
    all_audits.sort(key=lambda a: a.created_at, reverse=True)
    latest_audit: BacktestAudit | None = all_audits[0] if all_audits else None

    # All linked snapshots across all runs (deduplicated)
    snapshot_by_id: dict[str, DatasetSnapshot] = {}
    for run in runs:
        if run.snapshot is not None:
            snapshot_by_id[str(run.snapshot.id)] = run.snapshot
    snapshots = list(snapshot_by_id.values())

    # Open/active alerts
    open_alerts = [
        a for a in strategy.alerts
        if a.status in _ACTIVE_ALERT_STATUSES
    ]
    open_alerts.sort(key=lambda a: _SEV_RANK.get(a.severity, 0), reverse=True)

    # Recent timeline events for this strategy
    timeline_events = (
        db.query(AuditTimelineEvent)
        .filter(AuditTimelineEvent.strategy_id == strategy_id)
        .order_by(AuditTimelineEvent.event_time.desc())
        .limit(5)
        .all()
    )
    total_timeline_count = (
        db.query(AuditTimelineEvent)
        .filter(AuditTimelineEvent.strategy_id == strategy_id)
        .count()
    )

    # ------------------------------------------------------------------
    # Compute score
    # ------------------------------------------------------------------

    evidence_scores: list[float] = []
    if latest_audit is not None:
        evidence_scores.append(latest_audit.trust_score)
    if snapshots:
        avg_health = sum(s.health_score for s in snapshots) / len(snapshots)
        evidence_scores.append(avg_health)

    score: int | None = None
    if evidence_scores:
        base_score = sum(evidence_scores) / len(evidence_scores)
        # Penalty for open high/critical alerts (max 30 points)
        penalty = sum(
            15 if a.severity in ("critical", "high") else 5
            for a in open_alerts
        )
        penalty = min(penalty, 30)
        score = max(0, round(base_score - penalty))

    # ------------------------------------------------------------------
    # Build sections
    # ------------------------------------------------------------------
    sections: list[SectionResult] = []
    idx = 0

    # 1. Overview
    run_type_counts: dict[str, int] = {}
    for r in runs:
        run_type_counts[r.run_type] = run_type_counts.get(r.run_type, 0) + 1

    overview_parts = [f"Strategy '{strategy.name}' ({strategy.status}) has {len(runs)} logged run(s)."]
    if latest_audit:
        overview_parts.append(
            f"Latest backtest audit trust score is {latest_audit.trust_score}/100 "
            f"(status: {latest_audit.overall_status})."
        )
    if snapshots:
        avg_h = round(sum(s.health_score for s in snapshots) / len(snapshots))
        overview_parts.append(
            f"{len(snapshots)} dataset snapshot(s) linked, average data health score {avg_h}/100."
        )
    if open_alerts:
        overview_parts.append(
            f"{len(open_alerts)} open alert(s) noted for this strategy."
        )

    sections.append(SectionResult(
        section_key="overview",
        title="Overview",
        summary=" ".join(overview_parts),
        order_index=idx,
        evidence_json={
            "strategy_name": strategy.name,
            "status": strategy.status,
            "asset_class": strategy.asset_class,
            "project_name": project.name if project else None,
            "total_runs": len(runs),
            "run_type_counts": run_type_counts,
            "has_backtest_audit": latest_audit is not None,
            "audit_trust_score": latest_audit.trust_score if latest_audit else None,
            "audit_status": latest_audit.overall_status if latest_audit else None,
            "has_dataset_snapshots": len(snapshots) > 0,
            "snapshot_count": len(snapshots),
            "open_alert_count": len(open_alerts),
            "reliability_score": score,
        },
    ))
    idx += 1

    # 2. Strategy Activity
    first_run_at = runs[-1].created_at.isoformat() if runs else None
    latest_run_at = runs[0].created_at.isoformat() if runs else None
    version_ids = {r.strategy_version_id for r in runs if r.strategy_version_id}

    if not runs:
        activity_summary = "No runs have been logged yet. Log at least one run to begin evidence collection."
        activity_sev = "low"
    elif len(runs) < 3:
        activity_summary = (
            f"{len(runs)} run(s) logged. More runs will improve evidence coverage."
        )
        activity_sev = None
    else:
        activity_summary = (
            f"{len(runs)} run(s) logged across run types: "
            + ", ".join(f"{k} ({v})" for k, v in run_type_counts.items())
            + "."
        )
        activity_sev = None

    sections.append(SectionResult(
        section_key="strategy_activity",
        title="Strategy Activity",
        summary=activity_summary,
        order_index=idx,
        severity=activity_sev,
        evidence_json={
            "run_count": len(runs),
            "run_type_counts": run_type_counts,
            "first_run_at": first_run_at,
            "latest_run_at": latest_run_at,
            "version_count": len(version_ids),
        },
    ))
    idx += 1

    # 3. Latest Runs (up to 5)
    recent_runs_data = []
    for r in runs[:5]:
        metrics = r.metrics_json or {}
        recent_runs_data.append({
            "id": str(r.id),
            "run_name": r.run_name,
            "run_type": r.run_type,
            "status": r.status,
            "sharpe": metrics.get("sharpe"),
            "annual_return": metrics.get("annual_return"),
            "max_drawdown": metrics.get("max_drawdown"),
            "trade_count": metrics.get("trade_count"),
            "turnover": metrics.get("turnover"),
            "has_snapshot": r.snapshot is not None,
            "has_audit": len(r.backtest_audits) > 0,
            "created_at": r.created_at.isoformat(),
        })

    if not runs:
        runs_summary = "No runs logged."
    else:
        n = min(len(runs), 5)
        runs_with_audits = sum(1 for r in runs[:n] if r.backtest_audits)
        runs_with_snapshots = sum(1 for r in runs[:n] if r.snapshot)
        runs_summary = (
            f"Showing {n} of {len(runs)} run(s). "
            f"{runs_with_audits}/{n} have a backtest audit, "
            f"{runs_with_snapshots}/{n} have a linked dataset snapshot."
        )

    sections.append(SectionResult(
        section_key="latest_runs",
        title="Latest Runs",
        summary=runs_summary,
        order_index=idx,
        evidence_json={"runs": recent_runs_data, "total_run_count": len(runs)},
    ))
    idx += 1

    # 4. Data Evidence
    if not snapshots:
        data_ev_summary = (
            "No dataset snapshots are linked to runs for this strategy. "
            "Link snapshots when logging runs to enable data health monitoring."
        )
        data_ev_sev = "low"
    else:
        avg_health = round(sum(s.health_score for s in snapshots) / len(snapshots))
        min_health = min(s.health_score for s in snapshots)
        data_ev_sev = _score_to_section_severity(min_health)
        data_ev_summary = (
            f"{len(snapshots)} linked dataset snapshot(s) noted. "
            f"Average health score: {avg_health}/100, minimum: {min_health}/100."
        )

    snap_data = [
        {
            "id": str(s.id),
            "version_label": s.version_label,
            "health_score": s.health_score,
            "row_count": s.row_count,
            "issue_count": len(s.issues),
            "worst_severity": _worst_severity([i.severity for i in s.issues]),
        }
        for s in snapshots[:5]
    ]
    sections.append(SectionResult(
        section_key="data_evidence",
        title="Data Evidence",
        summary=data_ev_summary,
        order_index=idx,
        severity=data_ev_sev if snapshots else "low",
        evidence_json={
            "snapshot_count": len(snapshots),
            "avg_health_score": round(sum(s.health_score for s in snapshots) / len(snapshots)) if snapshots else None,
            "min_health_score": min(s.health_score for s in snapshots) if snapshots else None,
            "max_health_score": max(s.health_score for s in snapshots) if snapshots else None,
            "snapshots": snap_data,
        },
    ))
    idx += 1

    # 5. Backtest Trust
    if latest_audit is None:
        bt_summary = (
            "No backtest audit has been run for this strategy. "
            "Run the audit on a backtest run to obtain a trust score and realism assessment."
        )
        bt_sev = "low"
    else:
        high_sev = sum(1 for i in latest_audit.issues if i.severity in ("high", "critical"))
        bt_sev = _score_to_section_severity(latest_audit.trust_score)
        bt_summary = (
            f"Latest backtest audit: trust score {latest_audit.trust_score}/100 "
            f"(status: {latest_audit.overall_status}). "
            f"{len(latest_audit.issues)} issue(s) noted"
            + (f", {high_sev} high or critical." if high_sev > 0 else ".")
        )

    bt_evidence: dict = {"has_audit": latest_audit is not None}
    if latest_audit:
        bt_evidence.update({
            "audit_id": str(latest_audit.id),
            "trust_score": latest_audit.trust_score,
            "overall_status": latest_audit.overall_status,
            "cost_realism_score": latest_audit.cost_realism_score,
            "fill_realism_score": latest_audit.fill_realism_score,
            "liquidity_realism_score": latest_audit.liquidity_realism_score,
            "borrow_realism_score": latest_audit.borrow_realism_score,
            "data_quality_score": latest_audit.data_quality_score,
            "issue_count": len(latest_audit.issues),
            "high_severity_count": sum(1 for i in latest_audit.issues if i.severity in ("high", "critical")),
            "audit_summary": latest_audit.summary,
        })

    sections.append(SectionResult(
        section_key="backtest_trust",
        title="Backtest Trust",
        summary=bt_summary,
        order_index=idx,
        severity=bt_sev,
        evidence_json=bt_evidence,
    ))
    idx += 1

    # 6. Cost Sensitivity (only when fragility data available)
    if latest_audit is not None and latest_audit.fragility_summary_json is not None:
        fs = latest_audit.fragility_summary_json
        cs = latest_audit.cost_sensitivity_json or {}
        cost_level = fs.get("cost_fragility_level", "unknown")

        if cost_level == "high":
            cost_sev: str | None = "high"
            cost_summary = (
                "Cost sensitivity analysis (estimate only) suggests the backtest may be "
                "fragile to realistic transaction costs — estimated Sharpe ratio may fall "
                "below 1.0 at 10 bps. This requires review before drawing conclusions."
            )
        elif cost_level == "medium":
            cost_sev = "medium"
            cost_summary = (
                "Cost sensitivity analysis suggests moderate fragility — estimated Sharpe "
                "ratio may decline materially at 25 bps of transaction cost. "
                "These are estimates, not a full re-backtest."
            )
        elif cost_level == "low":
            cost_sev = None
            cost_summary = (
                "Cost sensitivity appears low — estimated Sharpe ratio remains above 1.0 "
                "across standard cost scenarios (up to 25 bps)."
            )
        else:
            cost_sev = None
            cost_summary = (
                "Cost sensitivity could not be estimated — turnover or performance "
                "metrics may not be available in the logged run data."
            )

        sections.append(SectionResult(
            section_key="cost_sensitivity",
            title="Cost Sensitivity",
            summary=cost_summary,
            order_index=idx,
            severity=cost_sev,
            evidence_json={
                "cost_fragility_level": cost_level,
                "overall_fragility": fs.get("overall_fragility"),
                "assumed_cost_bps": cs.get("assumed_cost_bps"),
                "turnover": cs.get("turnover"),
                "base_sharpe": cs.get("base_sharpe"),
                "base_annual_return": cs.get("base_annual_return"),
                "scenarios": cs.get("scenarios", []),
                "key_concerns": fs.get("key_concerns", []),
            },
        ))
        idx += 1

    # 7. Fill Realism (only when fill realism data available)
    if latest_audit is not None and latest_audit.fill_realism_json is not None:
        fr = latest_audit.fill_realism_json
        fill_level = fr.get("fill_realism_level", "unknown")

        if fill_level == "weak":
            fill_sev: str | None = "high"
            fill_summary = (
                "Fill realism assessment is weak — execution assumptions may materially "
                "overstate achievable returns. Review and update fill model assumptions."
            )
        elif fill_level == "review":
            fill_sev = "medium"
            fill_summary = (
                "Fill realism requires review — one or more execution assumptions "
                "may be optimistic relative to live trading conditions."
            )
        elif fill_level in ("acceptable", "strong"):
            fill_sev = None
            fill_summary = (
                f"Fill realism is '{fill_level}' — execution assumptions appear "
                "reasonable based on available evidence."
            )
        else:
            fill_sev = None
            fill_summary = (
                "Fill realism could not be assessed — fill_model was not specified "
                "in the run's assumptions."
            )

        non_info_findings = [
            f for f in fr.get("findings", [])
            if f.get("severity") not in ("info",) and f.get("code") != "missing_slippage"
        ]
        sections.append(SectionResult(
            section_key="fill_realism",
            title="Fill Realism",
            summary=fill_summary,
            order_index=idx,
            severity=fill_sev,
            evidence_json={
                "fill_realism_level": fill_level,
                "fill_model": fr.get("fill_model"),
                "slippage_bps": fr.get("slippage_bps"),
                "execution_timing": fr.get("execution_timing"),
                "participation_rate": fr.get("participation_rate"),
                "liquidity_filter_present": fr.get("liquidity_filter_present"),
                "findings_count": len(non_info_findings),
                "findings": non_info_findings[:5],
            },
        ))
        idx += 1

    # 8. Open Alerts
    if not open_alerts:
        alerts_summary = "No open alerts for this strategy."
        alerts_sev = None
    else:
        high_crit = sum(1 for a in open_alerts if a.severity in ("critical", "high"))
        alerts_sev = _worst_severity([a.severity for a in open_alerts])
        alerts_summary = (
            f"{len(open_alerts)} open alert(s) noted"
            + (f", {high_crit} at high or critical severity." if high_crit > 0 else ".")
            + " Review and resolve open alerts to improve the reliability signal."
        )

    sections.append(SectionResult(
        section_key="open_alerts",
        title="Open Alerts",
        summary=alerts_summary,
        order_index=idx,
        severity=alerts_sev,
        evidence_json={
            "open_count": len(open_alerts),
            "high_critical_count": sum(1 for a in open_alerts if a.severity in ("critical", "high")),
            "alerts": [
                {
                    "id": str(a.id),
                    "rule_type": a.rule_type,
                    "severity": a.severity,
                    "title": a.title,
                    "status": a.status,
                    "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
                }
                for a in open_alerts[:5]
            ],
        },
    ))
    idx += 1

    # 9. Recent Evidence Timeline
    ev_data = [
        {
            "event_type": ev.event_type,
            "title": ev.title,
            "severity": ev.severity,
            "event_time": ev.event_time.isoformat() if ev.event_time else None,
            "source_type": ev.source_type,
        }
        for ev in timeline_events
    ]
    sections.append(SectionResult(
        section_key="recent_timeline",
        title="Recent Evidence Timeline",
        summary=(
            f"{total_timeline_count} timeline event(s) recorded for this strategy. "
            f"Showing {len(timeline_events)} most recent."
        ) if timeline_events else "No timeline events recorded yet.",
        order_index=idx,
        evidence_json={
            "total_events": total_timeline_count,
            "recent_events": ev_data,
        },
    ))
    idx += 1

    # 10. Suggested Checks
    checks: list[str] = []
    if not runs:
        checks.append("Log at least one strategy run to begin evidence collection.")
    else:
        latest_run = runs[0]
        if latest_run.snapshot is None:
            checks.append(
                "Link a dataset snapshot to the latest run using dataset_snapshot_id "
                "to enable data quality integration."
            )
        if not latest_run.backtest_audits and latest_run.run_type in ("backtest", "research"):
            checks.append(
                "Run the backtest audit on the latest run "
                "(POST /api/strategy-runs/{id}/backtest-audit) to obtain a trust score."
            )

    if latest_audit is not None:
        if latest_audit.trust_score < 70:
            high_sev_issues = [i for i in latest_audit.issues if i.severity in ("critical", "high")]
            checks.append(
                f"Review backtest audit — trust score {latest_audit.trust_score}/100 with "
                f"{len(high_sev_issues)} high-severity concern(s)."
            )
        # Issue-specific checks
        issue_types = {i.issue_type for i in latest_audit.issues}
        if "missing_transaction_cost" in issue_types or "zero_transaction_cost" in issue_types:
            checks.append("Add or correct transaction_cost_bps in the run's assumptions_json.")
        if "missing_fill_model" in issue_types:
            checks.append("Specify fill_model in assumptions_json (e.g. 'vwap', 'open', 'arrival').")
        if "missing_trade_count" in issue_types:
            checks.append("Add trade_count to metrics_json when logging runs.")
        if "no_data_snapshot" in issue_types:
            checks.append("Link a dataset snapshot to this run via dataset_snapshot_id.")
        if "high_cost_fragility" in issue_types:
            checks.append(
                "Re-run the backtest with explicit cost assumptions of 10–25 bps "
                "to verify viability under realistic transaction costs."
            )
        if "same_bar_fill" in issue_types:
            checks.append(
                "Replace same-bar fill model with next-bar or arrival-price fills "
                "to reduce same-bar execution bias."
            )

    if snapshots:
        min_health = min(s.health_score for s in snapshots)
        if min_health < 70:
            checks.append(
                f"Review data quality issues in linked snapshot(s) — "
                f"minimum health score is {min_health}/100."
            )

    if open_alerts:
        high_crit = sum(1 for a in open_alerts if a.severity in ("critical", "high"))
        if high_crit > 0:
            checks.append(
                f"Investigate {high_crit} open high or critical alert(s) for this strategy."
            )

    if not checks:
        checks.append(
            "Evidence coverage appears reasonable. Continue logging runs and audits "
            "to maintain an up-to-date reliability record."
        )

    sections.append(SectionResult(
        section_key="suggested_checks",
        title="Suggested Checks",
        summary=f"{len(checks)} suggested check(s) based on available evidence.",
        order_index=idx,
        evidence_json={"checks": checks},
    ))

    # ------------------------------------------------------------------
    # Build report summary
    # ------------------------------------------------------------------
    summary_parts = [
        f"Strategy reliability report for '{strategy.name}'.",
        f"{len(runs)} run(s) logged.",
    ]
    if latest_audit:
        summary_parts.append(
            f"Latest backtest trust score: {latest_audit.trust_score}/100 ({latest_audit.overall_status})."
        )
    if snapshots:
        avg_h = round(sum(s.health_score for s in snapshots) / len(snapshots))
        summary_parts.append(
            f"{len(snapshots)} linked dataset snapshot(s), average health {avg_h}/100."
        )
    if open_alerts:
        summary_parts.append(f"{len(open_alerts)} open alert(s) noted.")
    if score is not None:
        summary_parts.append(f"Reliability score: {score}/100.")
    else:
        summary_parts.append(
            "Reliability score not available — insufficient evidence "
            "(requires at least one backtest audit or linked dataset snapshot)."
        )

    return ReportResult(
        report_type="strategy_reliability",
        title=f"Strategy Reliability Report — {strategy.name}",
        status="generated",
        summary=" ".join(summary_parts),
        generated_at=now,
        source_type="strategy",
        source_id=str(strategy_id),
        score=score,
        report_json={
            "strategy_id": str(strategy_id),
            "strategy_name": strategy.name,
            "strategy_status": strategy.status,
            "total_runs": len(runs),
            "run_type_counts": run_type_counts,
            "snapshot_count": len(snapshots),
            "open_alert_count": len(open_alerts),
            "latest_audit_trust_score": latest_audit.trust_score if latest_audit else None,
            "latest_audit_status": latest_audit.overall_status if latest_audit else None,
        },
        sections=sections,
        organization_id=str(project.organization_id) if project else None,
        project_id=str(project.id) if project else None,
        strategy_id=str(strategy_id),
    )


# ---------------------------------------------------------------------------
# B. Backtest Audit Report
# ---------------------------------------------------------------------------

def generate_backtest_audit_report(
    audit_id: uuid.UUID,
    db: Session,
) -> ReportResult:
    """Generate a deep-dive reliability report for a single backtest audit."""
    audit = (
        db.query(BacktestAudit)
        .options(
            selectinload(BacktestAudit.issues),
            selectinload(BacktestAudit.strategy_run).selectinload(StrategyRun.strategy).selectinload(Strategy.project),
            selectinload(BacktestAudit.strategy_run).selectinload(StrategyRun.snapshot).selectinload(DatasetSnapshot.issues),
        )
        .filter(BacktestAudit.id == audit_id)
        .first()
    )
    if audit is None:
        raise ValueError(f"BacktestAudit {audit_id} not found")

    now = datetime.now(timezone.utc)
    run = audit.strategy_run
    strategy = run.strategy if run else None
    project = strategy.project if strategy else None
    snapshot = run.snapshot if run else None

    sections: list[SectionResult] = []
    idx = 0

    # 1. Audit Summary
    high_sev_count = sum(1 for i in audit.issues if i.severity in ("critical", "high"))
    sections.append(SectionResult(
        section_key="audit_summary",
        title="Audit Summary",
        summary=audit.summary,
        order_index=idx,
        severity=_score_to_section_severity(audit.trust_score),
        evidence_json={
            "audit_id": str(audit_id),
            "run_name": run.run_name if run else None,
            "run_type": run.run_type if run else None,
            "strategy_name": strategy.name if strategy else None,
            "trust_score": audit.trust_score,
            "overall_status": audit.overall_status,
            "issue_count": len(audit.issues),
            "high_severity_count": high_sev_count,
            "audited_at": audit.created_at.isoformat(),
        },
    ))
    idx += 1

    # 2. Trust Score Breakdown
    sections.append(SectionResult(
        section_key="trust_score_breakdown",
        title="Trust Score Breakdown",
        summary=(
            f"Overall trust score: {audit.trust_score}/100. "
            f"Subscores: cost realism {audit.cost_realism_score}/100, "
            f"fill realism {audit.fill_realism_score}/100, "
            f"liquidity {audit.liquidity_realism_score}/100, "
            f"borrow {audit.borrow_realism_score}/100, "
            f"data quality {audit.data_quality_score}/100."
        ),
        order_index=idx,
        severity=_score_to_section_severity(audit.trust_score),
        evidence_json={
            "trust_score": audit.trust_score,
            "lookahead_risk_score": audit.lookahead_risk_score,
            "cost_realism_score": audit.cost_realism_score,
            "fill_realism_score": audit.fill_realism_score,
            "liquidity_realism_score": audit.liquidity_realism_score,
            "borrow_realism_score": audit.borrow_realism_score,
            "data_quality_score": audit.data_quality_score,
        },
    ))
    idx += 1

    # 3. Cost Sensitivity (if available)
    if audit.cost_sensitivity_json is not None:
        cs = audit.cost_sensitivity_json
        fs = audit.fragility_summary_json or {}
        cost_level = cs.get("cost_fragility_level", "unknown")
        cost_sev: str | None = (
            "high" if cost_level == "high"
            else "medium" if cost_level == "medium"
            else None
        )
        cost_summary = (
            f"Cost fragility level: {cost_level}. "
            f"Assumed cost: {cs.get('assumed_cost_bps', 'n/a')} bps, "
            f"turnover: {cs.get('turnover', 'n/a')}x, "
            f"base Sharpe: {cs.get('base_sharpe', 'n/a')}. "
            "All estimates — not a full re-backtest."
        )
        sections.append(SectionResult(
            section_key="cost_sensitivity",
            title="Cost Sensitivity",
            summary=cost_summary,
            order_index=idx,
            severity=cost_sev,
            evidence_json={
                "cost_fragility_level": cost_level,
                "overall_fragility": fs.get("overall_fragility"),
                "assumed_cost_bps": cs.get("assumed_cost_bps"),
                "turnover": cs.get("turnover"),
                "base_annual_return": cs.get("base_annual_return"),
                "base_sharpe": cs.get("base_sharpe"),
                "scenarios": cs.get("scenarios", []),
                "warnings": cs.get("warnings", []),
            },
        ))
        idx += 1

    # 4. Fill Realism (if available)
    if audit.fill_realism_json is not None:
        fr = audit.fill_realism_json
        fill_level = fr.get("fill_realism_level", "unknown")
        fill_sev: str | None = (
            "high" if fill_level == "weak"
            else "medium" if fill_level == "review"
            else None
        )
        non_info = [
            f for f in fr.get("findings", [])
            if f.get("code") != "missing_slippage"
        ]
        fill_summary = (
            f"Fill realism level: {fill_level}. "
            f"Fill model: {fr.get('fill_model') or 'not specified'}. "
            f"{len(non_info)} finding(s) noted."
        )
        sections.append(SectionResult(
            section_key="fill_realism",
            title="Fill Realism",
            summary=fill_summary,
            order_index=idx,
            severity=fill_sev,
            evidence_json={
                "fill_realism_level": fill_level,
                "fill_model": fr.get("fill_model"),
                "slippage_bps": fr.get("slippage_bps"),
                "execution_timing": fr.get("execution_timing"),
                "participation_rate": fr.get("participation_rate"),
                "liquidity_filter_present": fr.get("liquidity_filter_present"),
                "findings": non_info[:10],
            },
        ))
        idx += 1

    # 5. Data Evidence
    if snapshot is None:
        data_sev: str | None = "low"
        data_summary = (
            "No dataset snapshot is linked to this run. "
            "Linking a snapshot enables data health integration in the audit."
        )
        data_evidence: dict = {"has_snapshot": False}
    else:
        data_sev = _score_to_section_severity(snapshot.health_score)
        issue_severities = [i.severity for i in snapshot.issues]
        data_summary = (
            f"Linked snapshot '{snapshot.version_label}': "
            f"health score {snapshot.health_score}/100, "
            f"{len(snapshot.issues)} quality issue(s) noted."
        )
        data_evidence = {
            "has_snapshot": True,
            "snapshot_id": str(snapshot.id),
            "version_label": snapshot.version_label,
            "health_score": snapshot.health_score,
            "row_count": snapshot.row_count,
            "issue_count": len(snapshot.issues),
            "worst_severity": _worst_severity(issue_severities),
        }

    sections.append(SectionResult(
        section_key="data_evidence",
        title="Data Evidence",
        summary=data_summary,
        order_index=idx,
        severity=data_sev,
        evidence_json=data_evidence,
    ))
    idx += 1

    # 6. Issues and Suggested Checks
    issue_data = [
        {
            "issue_type": i.issue_type,
            "severity": i.severity,
            "title": i.title,
            "suggested_check": i.suggested_check,
        }
        for i in sorted(audit.issues, key=lambda x: _SEV_RANK.get(x.severity, 0), reverse=True)
    ]

    issue_types = {i.issue_type for i in audit.issues}
    suggested: list[str] = []
    if "missing_trade_count" in issue_types:
        suggested.append("Add trade_count to metrics_json when logging runs.")
    if "missing_transaction_cost" in issue_types or "zero_transaction_cost" in issue_types:
        suggested.append("Add or correct transaction_cost_bps in assumptions_json.")
    if "missing_fill_model" in issue_types:
        suggested.append("Specify fill_model in assumptions_json (e.g. 'vwap', 'arrival').")
    if "no_data_snapshot" in issue_types:
        suggested.append("Link a dataset snapshot to this run via dataset_snapshot_id.")
    if "high_cost_fragility" in issue_types:
        suggested.append(
            "Re-run the backtest with explicit cost assumptions of 10–25 bps "
            "to verify performance under realistic conditions."
        )
    if "same_bar_fill" in issue_types:
        suggested.append(
            "Replace same-bar fill model with next-bar or arrival-price fills."
        )
    if "mid_fill_no_slippage" in issue_types:
        suggested.append(
            "Add slippage_bps when using mid-price fills to model half-spread friction."
        )
    if not suggested:
        suggested.append(
            "No specific remediation items identified. "
            "Continue monitoring and re-audit after any assumption changes."
        )

    sections.append(SectionResult(
        section_key="issues_and_checks",
        title="Issues and Suggested Checks",
        summary=(
            f"{len(audit.issues)} issue(s) detected, {high_sev_count} at high or critical severity."
            if audit.issues else "No realism concerns detected in this audit."
        ),
        order_index=idx,
        severity=_worst_severity([i.severity for i in audit.issues]) if audit.issues else None,
        evidence_json={
            "issue_count": len(audit.issues),
            "issues": issue_data,
            "suggested_checks": suggested,
        },
    ))

    # Report-level summary
    summary = (
        f"Backtest audit report for run '{run.run_name if run else 'unknown'}'"
        + (f" ({strategy.name})" if strategy else "")
        + f". Trust score {audit.trust_score}/100 ({audit.overall_status}), "
        + f"{len(audit.issues)} issue(s) noted."
    )

    return ReportResult(
        report_type="backtest_audit",
        title=f"Backtest Audit Report — {run.run_name if run else str(audit_id)}",
        status="generated",
        summary=summary,
        generated_at=now,
        source_type="backtest_audit",
        source_id=str(audit_id),
        score=audit.trust_score,
        report_json={
            "audit_id": str(audit_id),
            "run_name": run.run_name if run else None,
            "strategy_name": strategy.name if strategy else None,
            "trust_score": audit.trust_score,
            "overall_status": audit.overall_status,
            "issue_count": len(audit.issues),
            "cost_fragility_level": (audit.cost_sensitivity_json or {}).get("cost_fragility_level"),
            "fill_realism_level": (audit.fill_realism_json or {}).get("fill_realism_level"),
        },
        sections=sections,
        organization_id=str(project.organization_id) if project else None,
        project_id=str(project.id) if project else None,
        strategy_id=str(strategy.id) if strategy else None,
    )


# ---------------------------------------------------------------------------
# C. Dataset Health Report
# ---------------------------------------------------------------------------

def generate_dataset_health_report(
    snapshot_id: uuid.UUID,
    db: Session,
) -> ReportResult:
    """Generate a dataset health report for a single snapshot."""
    snapshot = (
        db.query(DatasetSnapshot)
        .options(
            selectinload(DatasetSnapshot.issues),
            selectinload(DatasetSnapshot.dataset),
            selectinload(DatasetSnapshot.strategy_runs).selectinload(StrategyRun.strategy),
        )
        .filter(DatasetSnapshot.id == snapshot_id)
        .first()
    )
    if snapshot is None:
        raise ValueError(f"DatasetSnapshot {snapshot_id} not found")

    dataset = snapshot.dataset
    now = datetime.now(timezone.utc)
    sections: list[SectionResult] = []
    idx = 0

    # Infer project / org from dataset
    project_id_str: str | None = None
    org_id_str: str | None = None
    if dataset is not None:
        project_id_str = str(dataset.project_id) if dataset.project_id else None
        # Try to get org via project
        from app.models.project import Project as ProjectModel
        proj = db.query(ProjectModel).filter_by(id=dataset.project_id).first() if dataset.project_id else None
        if proj:
            org_id_str = str(proj.organization_id)

    # Issue severity breakdown
    sev_counts: dict[str, int] = {}
    for issue in snapshot.issues:
        sev_counts[issue.severity] = sev_counts.get(issue.severity, 0) + 1

    # 1. Snapshot Summary
    sections.append(SectionResult(
        section_key="snapshot_summary",
        title="Snapshot Summary",
        summary=(
            f"Dataset snapshot '{snapshot.version_label}' from dataset "
            f"'{dataset.name if dataset else 'unknown'}'. "
            f"{snapshot.row_count} row(s), health score {snapshot.health_score}/100, "
            f"{len(snapshot.issues)} quality issue(s) noted."
        ),
        order_index=idx,
        evidence_json={
            "snapshot_id": str(snapshot_id),
            "version_label": snapshot.version_label,
            "dataset_id": str(snapshot.dataset_id),
            "dataset_name": dataset.name if dataset else None,
            "row_count": snapshot.row_count,
            "health_score": snapshot.health_score,
            "issue_count": len(snapshot.issues),
            "created_at": snapshot.created_at.isoformat(),
        },
    ))
    idx += 1

    # 2. Data Health Score
    health_sev = _score_to_section_severity(snapshot.health_score)
    if snapshot.health_score >= 90:
        health_desc = "Data health appears good — no significant quality concerns detected."
    elif snapshot.health_score >= 70:
        health_desc = (
            f"Data health is acceptable ({snapshot.health_score}/100) but has noted issues. "
            "Review the quality items below."
        )
    else:
        health_desc = (
            f"Data health is below threshold ({snapshot.health_score}/100). "
            "Multiple quality issues were detected. Review before using in backtests."
        )

    sections.append(SectionResult(
        section_key="data_health_score",
        title="Data Health Score",
        summary=health_desc,
        order_index=idx,
        severity=health_sev,
        evidence_json={
            "health_score": snapshot.health_score,
            "issues_by_severity": sev_counts,
            "worst_severity": _worst_severity([i.severity for i in snapshot.issues]),
        },
    ))
    idx += 1

    # 3. Quality Issues
    issue_data = [
        {
            "id": str(i.id),
            "issue_type": i.issue_type,
            "severity": i.severity,
            "description": i.description,
            "affected_count": i.affected_count if hasattr(i, "affected_count") else None,
        }
        for i in sorted(snapshot.issues, key=lambda x: _SEV_RANK.get(x.severity, 0), reverse=True)
    ]

    if not snapshot.issues:
        issues_summary = "No data quality issues detected in this snapshot."
        issues_sev = None
    else:
        worst = _worst_severity([i.severity for i in snapshot.issues])
        issues_sev = worst
        issues_summary = (
            f"{len(snapshot.issues)} data quality issue(s) detected: "
            + ", ".join(f"{v} {k}" for k, v in sorted(sev_counts.items(), key=lambda x: _SEV_RANK.get(x[0], 0), reverse=True))
            + "."
        )

    sections.append(SectionResult(
        section_key="quality_issues",
        title="Quality Issues",
        summary=issues_summary,
        order_index=idx,
        severity=issues_sev,
        evidence_json={
            "issue_count": len(snapshot.issues),
            "issues_by_severity": sev_counts,
            "issues": issue_data,
        },
    ))
    idx += 1

    # 4. Schema and Coverage
    # Infer from rows_json if available
    columns: list[str] = []
    if snapshot.rows_json:
        first = snapshot.rows_json[0] if snapshot.rows_json else {}
        columns = sorted(first.keys()) if isinstance(first, dict) else []
    symbols = set()
    ts_list = []
    if snapshot.rows_json:
        for row in snapshot.rows_json:
            if isinstance(row, dict):
                if "symbol" in row and row["symbol"]:
                    symbols.add(row["symbol"])
                if "timestamp" in row and row["timestamp"]:
                    ts_list.append(str(row["timestamp"]))
    ts_list.sort()

    coverage_summary = (
        f"{snapshot.row_count} rows, {len(columns)} columns"
        + (f", {len(symbols)} symbol(s)" if symbols else "")
        + (f", date range {ts_list[0]} to {ts_list[-1]}" if ts_list else "")
        + "."
    )
    sections.append(SectionResult(
        section_key="schema_and_coverage",
        title="Schema and Coverage",
        summary=coverage_summary,
        order_index=idx,
        evidence_json={
            "row_count": snapshot.row_count,
            "column_count": len(columns),
            "columns": columns[:20],  # cap to avoid huge payloads
            "symbol_count": len(symbols),
            "min_timestamp": ts_list[0] if ts_list else None,
            "max_timestamp": ts_list[-1] if ts_list else None,
        },
    ))
    idx += 1

    # 5. Linked Strategy Runs
    linked_runs = snapshot.strategy_runs or []
    run_data = [
        {
            "id": str(r.id),
            "run_name": r.run_name,
            "run_type": r.run_type,
            "status": r.status,
            "strategy_name": r.strategy.name if r.strategy else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in linked_runs[:5]
    ]

    sections.append(SectionResult(
        section_key="linked_strategy_runs",
        title="Linked Strategy Runs",
        summary=(
            f"This snapshot is linked to {len(linked_runs)} strategy run(s)."
            if linked_runs else
            "No strategy runs are currently linked to this snapshot."
        ),
        order_index=idx,
        evidence_json={
            "linked_run_count": len(linked_runs),
            "runs": run_data,
        },
    ))
    idx += 1

    # 6. Suggested Checks
    checks: list[str] = []
    worst_sev = _worst_severity([i.severity for i in snapshot.issues])
    if worst_sev == "critical":
        checks.append(
            "Resolve critical data quality issues before using this snapshot in backtests."
        )
    if worst_sev in ("critical", "high"):
        checks.append(
            "Review and address high-severity data quality issues (e.g. price anomalies, duplicate rows)."
        )
    if snapshot.health_score < 70:
        checks.append(
            f"Data health score is {snapshot.health_score}/100 — review all flagged issues "
            "and consider re-ingesting clean data."
        )
    if not linked_runs:
        checks.append(
            "Link this snapshot to strategy runs using dataset_snapshot_id "
            "to integrate data quality evidence into backtest audits."
        )
    # Check if there are other snapshots for this dataset
    sibling_count = (
        db.query(DatasetSnapshot)
        .filter(
            DatasetSnapshot.dataset_id == snapshot.dataset_id,
            DatasetSnapshot.id != snapshot_id,
        )
        .count()
    )
    if sibling_count > 0:
        checks.append(
            "Compare this snapshot with a previous version "
            f"(GET /api/datasets/{snapshot.dataset_id}/snapshots/compare) "
            "to detect data revisions or drift."
        )
    if not checks:
        checks.append(
            "Data health appears good. Continue monitoring with each new snapshot upload."
        )

    sections.append(SectionResult(
        section_key="suggested_checks",
        title="Suggested Checks",
        summary=f"{len(checks)} suggested check(s) based on available evidence.",
        order_index=idx,
        evidence_json={"checks": checks},
    ))

    # Report-level summary
    summary = (
        f"Dataset health report for snapshot '{snapshot.version_label}' "
        f"(dataset: '{dataset.name if dataset else 'unknown'}'). "
        f"Health score {snapshot.health_score}/100, "
        f"{len(snapshot.issues)} quality issue(s) noted. "
        f"{len(linked_runs)} linked strategy run(s)."
    )

    return ReportResult(
        report_type="dataset_health",
        title=f"Dataset Health Report — {dataset.name if dataset else snapshot.version_label}",
        status="generated",
        summary=summary,
        generated_at=now,
        source_type="dataset_snapshot",
        source_id=str(snapshot_id),
        score=snapshot.health_score,
        report_json={
            "snapshot_id": str(snapshot_id),
            "dataset_name": dataset.name if dataset else None,
            "version_label": snapshot.version_label,
            "row_count": snapshot.row_count,
            "health_score": snapshot.health_score,
            "issue_count": len(snapshot.issues),
            "linked_run_count": len(linked_runs),
        },
        sections=sections,
        organization_id=org_id_str,
        project_id=project_id_str,
        strategy_id=None,
    )


# ---------------------------------------------------------------------------
# Persistence helper
# ---------------------------------------------------------------------------

def persist_report(result: ReportResult, db: Session) -> Report:
    """Write a ReportResult to the database and return the ORM Report object."""
    report = Report(
        organization_id=uuid.UUID(result.organization_id) if result.organization_id else None,
        project_id=uuid.UUID(result.project_id) if result.project_id else None,
        strategy_id=uuid.UUID(result.strategy_id) if result.strategy_id else None,
        report_type=result.report_type,
        title=result.title,
        status=result.status,
        summary=result.summary,
        generated_at=result.generated_at,
        source_type=result.source_type,
        source_id=result.source_id,
        score=result.score,
        report_json=result.report_json,
    )
    db.add(report)
    db.flush()  # get the report id

    for sec in result.sections:
        db.add(ReportSection(
            report_id=report.id,
            section_key=sec.section_key,
            title=sec.title,
            summary=sec.summary,
            severity=sec.severity,
            order_index=sec.order_index,
            evidence_json=sec.evidence_json,
        ))

    return report
