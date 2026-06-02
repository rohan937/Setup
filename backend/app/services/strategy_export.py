"""Strategy Evidence Export service (M31).

Deterministic export of all evidence for a strategy into JSON or Markdown format.
No AI, no random content, no side effects (no DB writes, no timeline events).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class StrategyExportSectionData:
    section_key: str
    title: str
    summary: str
    severity: str | None  # None, "info", "warning", "review", "critical"
    evidence_json: dict | None = field(default=None)


@dataclass
class StrategyExportMetadataData:
    export_id: str  # short hex from uuid4().hex[:12]
    strategy_id: uuid.UUID
    strategy_name: str
    strategy_slug: str
    generated_at: datetime
    format: str  # "json" or "markdown"
    filename: str  # safe filename
    milestone: str = "QuantFidelity M31"
    note: str = "Deterministic export. No AI was used. Not investment advice."


@dataclass
class StrategyExportData:
    metadata: StrategyExportMetadataData
    sections: list  # list of StrategyExportSectionData
    format: str
    content: str | None  # markdown string if format=="markdown", else None
    raw_evidence: dict | None = field(default=None)  # if include_raw_json=True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_filename(slug: str, fmt: str, ts: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in slug)
    return f"quantfidelity_{safe}_evidence_export_{ts}.{fmt}"


def _collect_sections(
    strategy_id: uuid.UUID,
    strategy,
    db: Session,
    limit_runs: int,
    limit_timeline: int,
) -> tuple[list[StrategyExportSectionData], dict]:
    """Collect all export sections by calling existing services.

    Returns (sections, raw_data_dict).
    Each service call is wrapped in try/except so a failure in one section
    does not abort the entire export.
    """
    sections: list[StrategyExportSectionData] = []
    raw: dict = {}

    # A. Strategy identity section
    sections.append(
        StrategyExportSectionData(
            section_key="identity",
            title="Strategy Identity",
            summary=(
                f"Strategy: {strategy.name} ({strategy.slug}). "
                f"Asset class: {strategy.asset_class}. Status: {strategy.status}."
            ),
            severity=None,
            evidence_json={
                "name": strategy.name,
                "slug": strategy.slug,
                "asset_class": strategy.asset_class,
                "status": strategy.status,
            },
        )
    )

    # B. Health section
    try:
        from app.services.strategy_health import compute_strategy_health

        health = compute_strategy_health(strategy_id, db)
        raw["health"] = {
            "health_status": health.health_status,
            "health_score": health.health_score,
            "primary_concern": health.primary_concern,
        }
        sev = (
            "critical"
            if health.health_status == "critical"
            else "review"
            if health.health_status == "review"
            else "warning"
            if health.health_status == "watch"
            else None
        )
        sections.append(
            StrategyExportSectionData(
                section_key="health",
                title="Current Strategy Health",
                summary=(
                    f"Health status: {health.health_status}. "
                    f"Score: {health.health_score if health.health_score is not None else 'N/A'}. "
                    f"Primary concern: {health.primary_concern}"
                ),
                severity=sev,
                evidence_json=raw["health"],
            )
        )
    except Exception as e:
        sections.append(
            StrategyExportSectionData(
                section_key="health",
                title="Current Strategy Health",
                summary=f"Health data unavailable: {e}",
                severity=None,
            )
        )

    # C. Reliability score section
    try:
        from app.models.strategy_reliability_score import StrategyReliabilityScore

        score = (
            db.query(StrategyReliabilityScore)
            .filter(StrategyReliabilityScore.strategy_id == strategy_id)
            .order_by(StrategyReliabilityScore.generated_at.desc())
            .first()
        )
        if score:
            summary = (
                f"Reliability score: {score.overall_score:.1f}/100 ({score.status}) "
                f"as of {score.generated_at.strftime('%Y-%m-%d') if score.generated_at else 'unknown'}."
            )
            raw["reliability"] = {
                "overall_score": score.overall_score,
                "status": score.status,
            }
            sev = (
                "critical"
                if score.status == "weak"
                and score.overall_score is not None
                and score.overall_score < 35
                else "review"
                if score.status in ("weak", "review")
                else None
            )
            sections.append(
                StrategyExportSectionData(
                    section_key="reliability",
                    title="Latest Reliability Score",
                    summary=summary,
                    severity=sev,
                    evidence_json=raw["reliability"],
                )
            )
        else:
            sections.append(
                StrategyExportSectionData(
                    section_key="reliability",
                    title="Latest Reliability Score",
                    summary="No reliability score computed yet.",
                    severity="warning",
                )
            )
    except Exception as e:
        sections.append(
            StrategyExportSectionData(
                section_key="reliability",
                title="Latest Reliability Score",
                summary=f"Reliability data unavailable: {e}",
                severity=None,
            )
        )

    # D. Evidence coverage section
    try:
        from app.services.evidence_coverage import _compute_row

        cov = _compute_row(strategy, db)
        raw["coverage"] = {
            "evidence_coverage_score": cov.evidence_coverage_score,
            "missing_count": cov.missing_count,
            "review_count": cov.review_count,
            "complete_count": cov.complete_count,
        }
        sections.append(
            StrategyExportSectionData(
                section_key="coverage",
                title="Evidence Coverage",
                summary=(
                    f"Coverage score: {cov.evidence_coverage_score:.0f}/100. "
                    f"Complete: {cov.complete_count}. "
                    f"Review: {cov.review_count}. "
                    f"Missing: {cov.missing_count}."
                ),
                severity=(
                    "review"
                    if cov.missing_count > 3
                    else "warning"
                    if cov.missing_count > 0
                    else None
                ),
                evidence_json=raw["coverage"],
            )
        )
    except Exception as e:
        sections.append(
            StrategyExportSectionData(
                section_key="coverage",
                title="Evidence Coverage",
                summary=f"Coverage data unavailable: {e}",
                severity=None,
            )
        )

    # E. Evidence trends section
    try:
        from app.services.evidence_trends import get_strategy_evidence_trends

        trends = get_strategy_evidence_trends(strategy_id, db, limit_per_series=10)
        raw["trends"] = {
            "reliability": {
                "direction": trends.reliability_trend.direction,
                "latest": trends.reliability_trend.latest_value,
                "summary": trends.reliability_trend.deterministic_summary,
            },
            "data_health": {
                "direction": trends.data_health_trend.direction,
                "latest": trends.data_health_trend.latest_value,
                "summary": trends.data_health_trend.deterministic_summary,
            },
            "backtest_trust": {
                "direction": trends.backtest_trust_trend.direction,
                "latest": trends.backtest_trust_trend.latest_value,
                "summary": trends.backtest_trust_trend.deterministic_summary,
            },
            "signal_quality": {
                "direction": trends.signal_quality_trend.direction,
                "latest": trends.signal_quality_trend.latest_value,
                "summary": trends.signal_quality_trend.deterministic_summary,
            },
        }
        deteriorating = [
            k for k, v in raw["trends"].items() if v["direction"] == "deteriorating"
        ]
        sev = "review" if deteriorating else None
        summary_lines = [v["summary"] for v in raw["trends"].values()]
        sections.append(
            StrategyExportSectionData(
                section_key="trends",
                title="Evidence Trends",
                summary=" ".join(summary_lines),
                severity=sev,
                evidence_json=raw["trends"],
            )
        )
    except Exception as e:
        sections.append(
            StrategyExportSectionData(
                section_key="trends",
                title="Evidence Trends",
                summary=f"Trend data unavailable: {e}",
                severity=None,
            )
        )

    # F. Run history highlights section
    try:
        from app.services.strategy_run_history import get_strategy_run_history

        runs_page, runs_summary = get_strategy_run_history(
            strategy_id, db, limit=limit_runs
        )
        raw["run_history"] = {
            "total_runs": runs_summary.total_runs,
            "weak_count": runs_summary.weak_count,
            "review_count": runs_summary.review_count,
            "strong_count": runs_summary.strong_count,
            "runs_missing_dataset": runs_summary.runs_missing_dataset,
            "runs_missing_audit": runs_summary.runs_missing_audit,
        }
        summary = (
            f"Total runs: {runs_summary.total_runs}. "
            f"Strong: {runs_summary.strong_count}. "
            f"Review: {runs_summary.review_count}. "
            f"Weak: {runs_summary.weak_count}. "
            f"Missing dataset: {runs_summary.runs_missing_dataset}. "
            f"Missing audit: {runs_summary.runs_missing_audit}."
        )
        sev = (
            "review"
            if runs_summary.weak_count > 0
            else "warning"
            if runs_summary.runs_missing_dataset > 0
            else None
        )
        sections.append(
            StrategyExportSectionData(
                section_key="run_history",
                title="Run History Highlights",
                summary=summary,
                severity=sev,
                evidence_json=raw["run_history"],
            )
        )
    except Exception as e:
        sections.append(
            StrategyExportSectionData(
                section_key="run_history",
                title="Run History Highlights",
                summary=f"Run history unavailable: {e}",
                severity=None,
            )
        )

    # G. Alerts section
    try:
        from app.models.alert import Alert

        open_alerts = (
            db.query(Alert)
            .filter(
                Alert.strategy_id == str(strategy_id),
                Alert.status.in_(["open", "acknowledged", "snoozed"]),
            )
            .order_by(Alert.triggered_at.desc())
            .limit(10)
            .all()
        )
        alert_count = len(open_alerts)
        hc_count = sum(1 for a in open_alerts if a.severity in ("high", "critical"))
        raw["alerts"] = {
            "open_count": alert_count,
            "high_critical_count": hc_count,
            "latest": [
                {"title": a.title, "severity": a.severity, "status": a.status}
                for a in open_alerts[:5]
            ],
        }
        sev = (
            "critical"
            if any(a.severity == "critical" for a in open_alerts)
            else "review"
            if hc_count > 0
            else "warning"
            if alert_count > 0
            else None
        )
        summary = (
            f"Open alerts: {alert_count}. High/critical: {hc_count}."
            + (" No open alerts." if alert_count == 0 else "")
        )
        sections.append(
            StrategyExportSectionData(
                section_key="alerts",
                title="Alerts and Review Items",
                summary=summary,
                severity=sev,
                evidence_json=raw["alerts"],
            )
        )
    except Exception as e:
        sections.append(
            StrategyExportSectionData(
                section_key="alerts",
                title="Alerts and Review Items",
                summary=f"Alert data unavailable: {e}",
                severity=None,
            )
        )

    # H. Recent timeline section
    try:
        from app.services.strategy_timeline import get_strategy_timeline_drilldown

        tl_items, tl_summary = get_strategy_timeline_drilldown(
            strategy_id, db, limit=limit_timeline
        )
        raw["timeline"] = {
            "total_events": tl_summary.total_events,
            "event_type_counts": tl_summary.event_type_counts,
        }
        summary = f"Total timeline events: {tl_summary.total_events}."
        sections.append(
            StrategyExportSectionData(
                section_key="timeline",
                title="Recent Evidence Timeline",
                summary=summary,
                severity=None,
                evidence_json=raw["timeline"],
            )
        )
    except Exception as e:
        sections.append(
            StrategyExportSectionData(
                section_key="timeline",
                title="Recent Evidence Timeline",
                summary=f"Timeline data unavailable: {e}",
                severity=None,
            )
        )

    # I. Reports section
    try:
        from app.models.report import Report

        reports = (
            db.query(Report)
            .filter(Report.strategy_id == strategy_id)
            .order_by(Report.generated_at.desc())
            .limit(5)
            .all()
        )
        raw["reports"] = [
            {
                "id": str(r.id),
                "report_type": r.report_type,
                "score": r.score,
                "status": r.status,
                "generated_at": str(r.generated_at),
            }
            for r in reports
        ]
        summary = f"Stored reports: {len(reports)}." + (
            f" Latest type: {reports[0].report_type}, score: {reports[0].score}."
            if reports
            else " No reports generated yet."
        )
        sections.append(
            StrategyExportSectionData(
                section_key="reports",
                title="Existing Reports",
                summary=summary,
                severity=None,
                evidence_json=raw["reports"],
            )
        )
    except Exception as e:
        sections.append(
            StrategyExportSectionData(
                section_key="reports",
                title="Existing Reports",
                summary=f"Report data unavailable: {e}",
                severity=None,
            )
        )

    # J. Suggested checks (aggregate and deduplicate from health service)
    try:
        from app.services.strategy_health import compute_strategy_health

        h = compute_strategy_health(strategy_id, db)
        all_checks = list(h.suggested_checks or [])
        seen: set[str] = set()
        deduped: list[str] = []
        for c in all_checks:
            if c not in seen:
                seen.add(c)
                deduped.append(c)
        if deduped:
            sections.append(
                StrategyExportSectionData(
                    section_key="suggested_checks",
                    title="Suggested Checks",
                    summary=f"{len(deduped)} suggested check(s) identified.",
                    severity="warning",
                    evidence_json={"checks": deduped},
                )
            )
    except Exception:
        pass

    return sections, raw


def _generate_markdown(strategy, metadata: StrategyExportMetadataData, sections: list[StrategyExportSectionData]) -> str:
    lines: list[str] = []
    lines.append(f"# QuantFidelity Strategy Evidence Export: {strategy.name}")
    lines.append("")
    lines.append(f"**Generated:** {metadata.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"**Strategy:** {strategy.name} ({strategy.slug})")
    lines.append(f"**Asset Class:** {strategy.asset_class}  |  **Status:** {strategy.status}")
    lines.append(f"**Export ID:** {metadata.export_id}")
    lines.append("")
    lines.append("> This export is deterministic and based solely on evidence logged in QuantFidelity.")
    lines.append("> No AI was used in generating this document. Not investment advice.")
    lines.append("")
    lines.append("---")
    lines.append("")
    for i, sec in enumerate(sections, 1):
        lines.append(f"## {i}. {sec.title}")
        lines.append("")
        if sec.severity and sec.severity != "info":
            sev_labels = {
                "critical": "CRITICAL",
                "review": "REVIEW REQUIRED",
                "warning": "ATTENTION",
            }
            lines.append(f"**[{sev_labels.get(sec.severity, sec.severity.upper())}]** {sec.summary}")
        else:
            lines.append(sec.summary)
        lines.append("")
        if (
            sec.evidence_json
            and isinstance(sec.evidence_json, dict)
            and sec.section_key == "suggested_checks"
        ):
            checks = sec.evidence_json.get("checks", [])
            if checks:
                for c in checks:
                    lines.append(f"- {c}")
                lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Notes and Limitations")
    lines.append("")
    lines.append(
        f"- This export reflects evidence logged in QuantFidelity as of "
        f"{metadata.generated_at.strftime('%Y-%m-%d %H:%M UTC')}."
    )
    lines.append("- It does not reflect live market conditions or future performance.")
    lines.append("- Score values are deterministic and based on logged evidence only.")
    lines.append("- Not investment advice.")
    lines.append(f"- Generated by {metadata.milestone}.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------


def generate_strategy_export(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    format: str = "json",
    include_raw_json: bool = False,
    limit_recent_runs: int = 10,
    limit_timeline_events: int = 20,
) -> StrategyExportData:
    """Generate a full evidence export for *strategy_id*.

    :param strategy_id: UUID of the strategy to export.
    :param db: SQLAlchemy session.
    :param format: "json" (default) or "markdown".
    :param include_raw_json: If True, the ``raw_evidence`` field is populated.
    :param limit_recent_runs: How many recent runs to include in the run history section.
    :param limit_timeline_events: How many timeline events to include in the timeline section.
    :raises ValueError: If the strategy does not exist or *format* is invalid.
    """
    from app.models.strategy import Strategy

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    if format not in ("json", "markdown"):
        raise ValueError(f"Invalid format: {format!r}. Must be 'json' or 'markdown'.")

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d_%H%M%S")
    export_id = uuid.uuid4().hex[:12]

    slug_or_name = strategy.slug or strategy.name
    if format == "markdown":
        filename = _safe_filename(slug_or_name, "md", ts)
    else:
        filename = _safe_filename(slug_or_name, "json", ts)

    metadata = StrategyExportMetadataData(
        export_id=export_id,
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        strategy_slug=strategy.slug or "",
        generated_at=now,
        format=format,
        filename=filename,
    )

    sections, raw = _collect_sections(
        strategy_id, strategy, db, limit_recent_runs, limit_timeline_events
    )

    content: str | None = None
    if format == "markdown":
        content = _generate_markdown(strategy, metadata, sections)

    return StrategyExportData(
        metadata=metadata,
        sections=sections,
        format=format,
        content=content,
        raw_evidence=raw if include_raw_json else None,
    )
