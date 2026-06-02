"""Strategy Comparison Report service (M44).

Deterministic side-by-side comparison report for 2–4 strategies.
No AI, no random content, no side effects (no DB writes, no timeline events).
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class StrategyComparisonReportMetadataData:
    report_id: str
    generated_at: datetime
    format: str
    strategy_count: int
    strategy_ids: list[str]
    note: str = "Deterministic evidence comparison. No AI used. Not investment advice."


@dataclass
class StrategyComparisonReportSectionData:
    section_key: str
    title: str
    summary: str
    severity: str | None = None
    evidence_json: dict | None = None


@dataclass
class StrategyComparisonReportStrategySummaryData:
    strategy_id: uuid.UUID
    name: str
    asset_class: str
    status: str
    health_status: str | None
    health_score: float | None
    primary_concern: str | None
    reliability_score: float | None
    reliability_status: str | None
    evidence_coverage_score: float | None
    assumption_status: str | None
    assumption_score: float | None
    weakening_change_count: int
    positive_change_count: int
    reliability_trend: str | None
    data_health_trend: str | None
    backtest_trust_trend: str | None
    signal_quality_trend: str | None
    open_alert_count: int
    high_critical_alert_count: int
    suggested_checks: list[str] = field(default_factory=list)


@dataclass
class StrategyComparisonReportData:
    metadata: StrategyComparisonReportMetadataData
    sections: list  # list of StrategyComparisonReportSectionData
    strategy_summaries: list  # list of StrategyComparisonReportStrategySummaryData
    rankings: dict  # {dimension: [(name, score), ...]}
    suggested_review_agenda: list[str]
    format: str
    filename: str
    content: str | None  # markdown string if format=="markdown"
    raw_evidence: dict | None = field(default=None)


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------


def generate_strategy_comparison_report(
    strategy_ids: list[uuid.UUID],
    db: Session,
    *,
    format: str = "json",
    include_raw_json: bool = False,
) -> StrategyComparisonReportData:
    """Generate a deterministic comparison report for 2–4 strategies.

    Read-only — no DB writes, no timeline events.
    """
    from app.models.strategy import Strategy

    if len(strategy_ids) < 2:
        raise ValueError("At least 2 strategy IDs required.")
    if len(strategy_ids) > 4:
        raise ValueError("At most 4 strategy IDs may be compared.")

    strategies = {
        s.id: s
        for s in db.query(Strategy).filter(Strategy.id.in_(strategy_ids)).all()
    }
    missing = [str(sid) for sid in strategy_ids if sid not in strategies]
    if missing:
        raise ValueError(f"Strategies not found: {missing}")

    now = datetime.now(timezone.utc)
    report_id = hashlib.sha256(
        f"{now.isoformat()}{''.join(str(s) for s in strategy_ids)}".encode()
    ).hexdigest()[:12]
    ts = now.strftime("%Y%m%d_%H%M%S")
    ext = "md" if format == "markdown" else "json"
    filename = f"quantfidelity_strategy_comparison_report_{ts}.{ext}"

    # ------------------------------------------------------------------
    # Per-strategy data collection
    # ------------------------------------------------------------------
    summaries: list[StrategyComparisonReportStrategySummaryData] = []
    raw: dict = {}

    for sid in strategy_ids:
        strategy = strategies[sid]
        summary = StrategyComparisonReportStrategySummaryData(
            strategy_id=sid,
            name=strategy.name,
            asset_class=strategy.asset_class,
            status=strategy.status,
            health_status=None,
            health_score=None,
            primary_concern=None,
            reliability_score=None,
            reliability_status=None,
            evidence_coverage_score=None,
            assumption_status=None,
            assumption_score=None,
            weakening_change_count=0,
            positive_change_count=0,
            reliability_trend=None,
            data_health_trend=None,
            backtest_trust_trend=None,
            signal_quality_trend=None,
            open_alert_count=0,
            high_critical_alert_count=0,
            suggested_checks=[],
        )
        strategy_raw: dict = {"name": strategy.name}

        # Health
        try:
            from app.services.strategy_health import compute_strategy_health

            h = compute_strategy_health(sid, db)
            summary.health_status = h.health_status
            summary.health_score = _safe_float(h.health_score)
            summary.primary_concern = h.primary_concern
            summary.open_alert_count = h.open_alert_count
            summary.high_critical_alert_count = h.high_critical_alert_count
            strategy_raw["health"] = {
                "status": h.health_status,
                "score": _safe_float(h.health_score),
            }
        except Exception:
            pass

        # Reliability
        try:
            from app.models.strategy_reliability_score import StrategyReliabilityScore

            rel = (
                db.query(StrategyReliabilityScore)
                .filter(StrategyReliabilityScore.strategy_id == sid)
                .order_by(StrategyReliabilityScore.generated_at.desc())
                .first()
            )
            if rel:
                summary.reliability_score = _safe_float(rel.overall_score)
                summary.reliability_status = rel.status
                strategy_raw["reliability"] = {
                    "score": _safe_float(rel.overall_score),
                    "status": rel.status,
                }
        except Exception:
            pass

        # Coverage
        try:
            from app.services.evidence_coverage import _compute_row

            cov = _compute_row(strategy, db)
            summary.evidence_coverage_score = _safe_float(cov.evidence_coverage_score)
            strategy_raw["coverage"] = {
                "score": _safe_float(cov.evidence_coverage_score),
                "missing": getattr(cov, "missing_count", None),
            }
        except Exception:
            pass

        # Assumption health
        try:
            from app.services.assumption_health import compute_assumption_health

            ah = compute_assumption_health(sid, db)
            summary.assumption_status = ah.get("status")
            summary.assumption_score = _safe_float(ah.get("overall_assumption_score"))
            summary.weakening_change_count = ah.get("weakening_change_count", 0) or 0
            summary.positive_change_count = ah.get("positive_change_count", 0) or 0
            ach = ah.get("suggested_checks", [])
            summary.suggested_checks.extend(ach[:3])
            strategy_raw["assumption_health"] = {
                "status": ah.get("status"),
                "score": _safe_float(ah.get("overall_assumption_score")),
            }
        except Exception:
            pass

        # Trends
        try:
            from app.services.evidence_trends import get_strategy_evidence_trends

            trends = get_strategy_evidence_trends(sid, db, limit_per_series=5)
            summary.reliability_trend = trends.reliability_trend.direction
            summary.data_health_trend = trends.data_health_trend.direction
            summary.backtest_trust_trend = trends.backtest_trust_trend.direction
            summary.signal_quality_trend = trends.signal_quality_trend.direction
        except Exception:
            pass

        summaries.append(summary)
        raw[str(sid)] = strategy_raw

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------
    sections: list[StrategyComparisonReportSectionData] = []

    # Summary section
    names = [s.name for s in summaries]
    sections.append(
        StrategyComparisonReportSectionData(
            section_key="comparison_summary",
            title="Comparison Summary",
            summary=(
                f"Comparing {len(summaries)} strategies: {', '.join(names)}. "
                "This comparison reflects logged evidence quality only."
            ),
            evidence_json={"strategy_names": names, "strategy_count": len(summaries)},
        )
    )

    # Health section
    health_data = {
        s.name: {
            "status": s.health_status,
            "score": s.health_score,
            "concern": s.primary_concern,
        }
        for s in summaries
    }
    has_critical = any(s.health_status == "critical" for s in summaries)
    health_sev = (
        "critical"
        if has_critical
        else ("review" if any(s.health_status == "review" for s in summaries) else None)
    )

    def _health_desc(s: StrategyComparisonReportStrategySummaryData) -> str:
        if s.health_score is not None and s.primary_concern:
            return f"{s.name}: {s.health_status or 'unknown'} ({s.health_score:.0f}/100 - {s.primary_concern})"
        elif s.health_score is not None:
            return f"{s.name}: {s.health_status or 'unknown'} ({s.health_score:.0f}/100)"
        return f"{s.name}: {s.health_status or 'unknown'}"

    sections.append(
        StrategyComparisonReportSectionData(
            section_key="health_comparison",
            title="Health Comparison",
            summary=" ".join(_health_desc(s) for s in summaries)
            + ". Health scores reflect logged evidence quality.",
            severity=health_sev,
            evidence_json=health_data,
        )
    )

    # Reliability section
    rel_data = {
        s.name: {"score": s.reliability_score, "status": s.reliability_status}
        for s in summaries
    }

    def _rel_desc(s: StrategyComparisonReportStrategySummaryData) -> str:
        if s.reliability_score is not None:
            return f"{s.name}: {s.reliability_score:.1f}/100 ({s.reliability_status})"
        return f"{s.name}: no score"

    sections.append(
        StrategyComparisonReportSectionData(
            section_key="reliability_comparison",
            title="Reliability Comparison",
            summary=" ".join(_rel_desc(s) for s in summaries) + ".",
            evidence_json=rel_data,
        )
    )

    # Coverage section
    cov_data = {s.name: {"score": s.evidence_coverage_score} for s in summaries}

    def _cov_desc(s: StrategyComparisonReportStrategySummaryData) -> str:
        if s.evidence_coverage_score is not None:
            return f"{s.name}: {s.evidence_coverage_score:.0f}/100 coverage"
        return f"{s.name}: unknown coverage"

    sections.append(
        StrategyComparisonReportSectionData(
            section_key="coverage_comparison",
            title="Evidence Coverage Comparison",
            summary=" ".join(_cov_desc(s) for s in summaries) + ".",
            evidence_json=cov_data,
        )
    )

    # Assumption section
    ah_data = {
        s.name: {
            "score": s.assumption_score,
            "status": s.assumption_status,
            "weakening": s.weakening_change_count,
        }
        for s in summaries
    }

    def _ah_desc(s: StrategyComparisonReportStrategySummaryData) -> str:
        base = f"{s.name}: {s.assumption_status or 'unknown'}"
        if s.weakening_change_count > 0:
            base += f" ({s.weakening_change_count} weakening change(s))"
        return base

    sections.append(
        StrategyComparisonReportSectionData(
            section_key="assumption_comparison",
            title="Assumption Health Comparison",
            summary=" ".join(_ah_desc(s) for s in summaries) + ".",
            evidence_json=ah_data,
        )
    )

    # Trends section
    trend_data = {
        s.name: {
            "reliability": s.reliability_trend,
            "data_health": s.data_health_trend,
            "backtest": s.backtest_trust_trend,
            "signal": s.signal_quality_trend,
        }
        for s in summaries
    }
    sections.append(
        StrategyComparisonReportSectionData(
            section_key="trend_comparison",
            title="Evidence Trend Comparison",
            summary=" ".join(
                f"{s.name}: reliability={s.reliability_trend or '—'}, data={s.data_health_trend or '—'}"
                for s in summaries
            )
            + ".",
            evidence_json=trend_data,
        )
    )

    # Alerts section
    alert_data = {
        s.name: {"open": s.open_alert_count, "high_critical": s.high_critical_alert_count}
        for s in summaries
    }
    sections.append(
        StrategyComparisonReportSectionData(
            section_key="alerts_comparison",
            title="Alerts Comparison",
            summary=" ".join(
                f"{s.name}: {s.open_alert_count} open alert(s), {s.high_critical_alert_count} high/critical"
                for s in summaries
            )
            + ".",
            severity="review" if any(s.high_critical_alert_count > 0 for s in summaries) else None,
            evidence_json=alert_data,
        )
    )

    # ------------------------------------------------------------------
    # Rankings
    # ------------------------------------------------------------------
    def _rank_by(field_getter, higher_is_better: bool = True):
        scored = [(s, field_getter(s)) for s in summaries if field_getter(s) is not None]
        scored.sort(key=lambda x: (-x[1] if higher_is_better else x[1], x[0].name))
        no_score = [(s, None) for s in summaries if field_getter(s) is None]
        return [(s.name, v) for s, v in scored + no_score]

    rankings = {
        "by_evidence_coverage": _rank_by(lambda s: s.evidence_coverage_score),
        "by_reliability_score": _rank_by(lambda s: s.reliability_score),
        "by_health_score": _rank_by(lambda s: s.health_score),
        "by_assumption_health": _rank_by(lambda s: s.assumption_score),
    }

    # ------------------------------------------------------------------
    # Suggested review agenda
    # ------------------------------------------------------------------
    agenda: list[str] = []
    critical_names = [s.name for s in summaries if s.health_status == "critical"]
    review_names = [s.name for s in summaries if s.health_status == "review"]
    if critical_names:
        agenda.append(f"Review critical health issues for: {', '.join(critical_names)}.")
    if review_names:
        agenda.append(f"Inspect review health issues for: {', '.join(review_names)}.")
    for s in summaries:
        if s.weakening_change_count > 0:
            agenda.append(
                f"Inspect weakening config assumption changes for {s.name}."
            )
    deteriorating = [
        s.name
        for s in summaries
        if any(
            t == "deteriorating"
            for t in [
                s.reliability_trend,
                s.data_health_trend,
                s.backtest_trust_trend,
                s.signal_quality_trend,
            ]
        )
    ]
    if deteriorating:
        agenda.append(
            f"Investigate deteriorating evidence trends in: {', '.join(deteriorating)}."
        )
    if not agenda:
        agenda.append(
            "All compared strategies appear to be in acceptable or strong evidence state."
        )
    agenda.append(
        "This report reflects logged evidence only. Not an investment recommendation."
    )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    metadata = StrategyComparisonReportMetadataData(
        report_id=report_id,
        generated_at=now,
        format=format,
        strategy_count=len(summaries),
        strategy_ids=[str(sid) for sid in strategy_ids],
    )

    # ------------------------------------------------------------------
    # Markdown rendering
    # ------------------------------------------------------------------
    content: str | None = None
    if format == "markdown":
        lines: list[str] = []
        lines.append("# QuantFidelity Strategy Comparison Report")
        lines.append("")
        lines.append(f"**Generated:** {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"**Strategies Compared:** {', '.join(s.name for s in summaries)}")
        lines.append(f"**Report ID:** {report_id}")
        lines.append("")
        lines.append("> Deterministic evidence comparison. No AI used. Not investment advice.")
        lines.append(
            "> This report compares logged evidence quality. "
            "Higher scores reflect more complete evidence, not better expected returns."
        )
        lines.append("")
        lines.append("---")
        lines.append("")
        for i, sec in enumerate(sections, 1):
            lines.append(f"## {i}. {sec.title}")
            lines.append("")
            lines.append(sec.summary)
            lines.append("")
        lines.append("## Rankings")
        lines.append("")
        for dim, ranked in rankings.items():
            ranked_str = " > ".join(
                f"{name} ({val:.0f})" if val is not None else name
                for name, val in ranked
            )
            lines.append(
                f"**{dim.replace('_', ' ').title()}:** {ranked_str}"
            )
        lines.append("")
        lines.append("## Suggested Review Agenda")
        lines.append("")
        for item in agenda:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Notes and Limitations")
        lines.append("")
        lines.append(
            "- This report reflects evidence logged in QuantFidelity at the time of generation."
        )
        lines.append(
            "- Scores and statuses reflect evidence completeness, not live trading performance."
        )
        lines.append(
            "- Not investment advice. Not a guarantee of future performance."
        )
        content = "\n".join(lines)

    return StrategyComparisonReportData(
        metadata=metadata,
        sections=sections,
        strategy_summaries=summaries,
        rankings=rankings,
        suggested_review_agenda=agenda,
        format=format,
        filename=filename,
        content=content,
        raw_evidence=raw if include_raw_json else None,
    )
