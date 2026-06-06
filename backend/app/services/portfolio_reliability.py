"""Portfolio Reliability service (M86).

Aggregates every per-strategy reliability subsystem (reliability score, health,
readiness, promotion gates, evidence freshness, alerts, reports, regression
runs) into a single portfolio-wide research-readiness summary.

Deterministic — no AI, no live market data, no external calls.  Read-only on
the build path; the refresh helper is the only mutation surface and is invoked
explicitly by the refresh endpoint.

Every subsystem call is wrapped in try/except so a single failing subsystem can
never break a strategy row or the whole portfolio build.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Severity ranking for blocker sorting (lower = more urgent)
# ---------------------------------------------------------------------------

SEVERITY_RANK: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


DISCLAIMER = (
    "Portfolio reliability is a deterministic research-readiness summary, "
    "not trading advice."
)


# ---------------------------------------------------------------------------
# Strategy enumeration — mirrors get_portfolio_overview scoping exactly.
# ---------------------------------------------------------------------------

def _enumerate_strategies(
    db: Session,
    *,
    organization_id=None,
    project_id=None,
    include_archived: bool = False,
):
    """Mirror the M32 portfolio overview enumeration/scoping."""
    from app.models.project import Project
    from app.models.strategy import Strategy

    q = db.query(Strategy)
    if not include_archived:
        q = q.filter(Strategy.status != "archived")
    if project_id is not None:
        q = q.filter(Strategy.project_id == project_id)
    if organization_id is not None:
        q = q.join(Project, Strategy.project_id == Project.id).filter(
            Project.organization_id == organization_id
        )
    return q.order_by(Strategy.name).all()


def _resolve_organization_id(
    db: Session,
    *,
    organization_id=None,
    project_id=None,
    strategies=None,
):
    """Best-effort resolution of the org id for org-wide alert counts and the
    refresh path.  Prefer the explicit organization_id; else derive from the
    project or the first strategy's project."""
    from app.models.project import Project

    if organization_id is not None:
        return organization_id
    if project_id is not None:
        proj = db.query(Project).filter(Project.id == project_id).first()
        if proj is not None:
            return proj.organization_id
    if strategies:
        first = strategies[0]
        proj = db.query(Project).filter(Project.id == first.project_id).first()
        if proj is not None:
            return proj.organization_id
    return None


# ---------------------------------------------------------------------------
# Per-strategy aggregation
# ---------------------------------------------------------------------------

def _aggregate_strategy(strategy, db: Session) -> dict:
    """Aggregate every subsystem for one strategy into a flat row dict.

    Each subsystem call is independently guarded; defaults are sensible so a
    missing subsystem degrades gracefully rather than dropping the row.
    """
    from app.models.project import Project
    from app.models.report import Report
    from app.models.strategy_reliability_score import StrategyReliabilityScore
    from app.models.strategy_run import StrategyRun

    sid = strategy.id

    # ---- project name ----
    project_name = None
    try:
        proj = db.query(Project).filter(Project.id == strategy.project_id).first()
        project_name = proj.name if proj else None
    except Exception:
        project_name = None

    # ---- reliability: latest + previous stored scores ----
    reliability_score = None
    reliability_status = None
    recent_score_change = None
    try:
        rel_rows = (
            db.query(StrategyReliabilityScore)
            .filter(StrategyReliabilityScore.strategy_id == sid)
            .order_by(StrategyReliabilityScore.generated_at.desc())
            .limit(2)
            .all()
        )
        if rel_rows:
            latest = rel_rows[0]
            reliability_score = latest.overall_score
            reliability_status = latest.status
            if (
                len(rel_rows) >= 2
                and latest.overall_score is not None
                and rel_rows[1].overall_score is not None
            ):
                prev = rel_rows[1]
                delta = round(latest.overall_score - prev.overall_score, 1)
                if delta > 0:
                    direction = "up"
                elif delta < 0:
                    direction = "down"
                else:
                    direction = "flat"
                recent_score_change = {
                    "delta": delta,
                    "latest": latest.overall_score,
                    "previous": prev.overall_score,
                    "direction": direction,
                }
    except Exception:
        pass

    # ---- health ----
    health_status = "insufficient_evidence"
    health_score = None
    open_alert_count = 0
    high_critical_alert_count = 0
    latest_run_at = None
    days_since_latest_run = None
    primary_concern = ""
    missing_evidence: list[str] = []
    try:
        from app.services.strategy_health import compute_strategy_health

        health = compute_strategy_health(sid, db)
        health_status = health.health_status
        health_score = health.health_score
        open_alert_count = health.open_alert_count
        high_critical_alert_count = health.high_critical_alert_count
        latest_run_at = health.latest_run_at
        days_since_latest_run = health.days_since_latest_run
        primary_concern = health.primary_concern
        missing_evidence = list(health.missing_evidence or [])
        if reliability_score is None and health.latest_reliability_score is not None:
            reliability_score = health.latest_reliability_score
        if reliability_status is None and health.reliability_status is not None:
            reliability_status = health.reliability_status
    except Exception:
        pass

    # ---- readiness ----
    readiness_verdict = "under_instrumented"
    readiness_blockers: list[str] = []
    promotion_stage = None
    next_recommended_stage = None
    try:
        from app.services.strategy_readiness import compute_strategy_readiness

        readiness = compute_strategy_readiness(sid, db)
        readiness_verdict = readiness.readiness_verdict
        readiness_blockers = list(readiness.blockers or [])
        if readiness.progression_path is not None:
            promotion_stage = readiness.progression_path.current_stage
            next_recommended_stage = readiness.progression_path.next_recommended_stage
    except Exception:
        pass

    # ---- promotion gates (paper_candidate) ----
    promotion_blocker_count = 0
    promotion_blockers: list[str] = []
    promotion_verdict = "insufficient_evidence"
    try:
        from app.services.promotion_gates import evaluate_promotion_gates

        gate = evaluate_promotion_gates(sid, "paper_candidate", db)
        promotion_blocker_count = gate.blocker_count or 0
        promotion_blockers = list(gate.blockers or [])
        promotion_verdict = gate.promotion_verdict
    except Exception:
        pass

    # ---- evidence freshness ----
    stale_count = 0
    missing_count = 0
    aging_count = 0
    try:
        from app.services.evidence_freshness import compute_evidence_freshness

        freshness = compute_evidence_freshness(sid, db)
        stale_count = freshness.stale_count or 0
        missing_count = freshness.missing_count or 0
        aging_count = freshness.aging_count or 0
    except Exception:
        pass
    stale_evidence_count = stale_count + missing_count

    # ---- alerts ----
    alert_open = 0
    alert_by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    alert_blocking_promotion = 0
    try:
        from app.services.alerts import get_strategy_alert_summary

        summary = get_strategy_alert_summary(db, str(sid))
        alert_open = summary.get("open", 0)
        bs = summary.get("by_severity") or {}
        for k in alert_by_severity:
            alert_by_severity[k] = bs.get(k, 0)
        alert_blocking_promotion = summary.get("blocking_promotion", 0)
    except Exception:
        pass

    # ---- missing report ----
    # has >= 1 run AND (no strategy_reliability report OR report older than latest run)
    missing_report = False
    try:
        latest_run = (
            db.query(StrategyRun)
            .filter(StrategyRun.strategy_id == sid)
            .order_by(StrategyRun.created_at.desc())
            .first()
        )
        if latest_run is not None:
            report = (
                db.query(Report)
                .filter(
                    Report.strategy_id == sid,
                    Report.report_type == "strategy_reliability",
                )
                .order_by(Report.generated_at.desc())
                .first()
            )
            if report is None:
                missing_report = True
            else:
                rep_at = report.generated_at
                run_at = latest_run.created_at
                if rep_at is not None and rep_at.tzinfo is None:
                    rep_at = rep_at.replace(tzinfo=timezone.utc)
                if run_at is not None and run_at.tzinfo is None:
                    run_at = run_at.replace(tzinfo=timezone.utc)
                if rep_at is not None and run_at is not None and rep_at < run_at:
                    missing_report = True
    except Exception:
        pass

    # ---- pending review (M87): active strategy review for this strategy ----
    pending_review = None
    try:
        from app.models.strategy_review import StrategyReview

        active = (
            db.query(StrategyReview)
            .filter(
                StrategyReview.strategy_id == str(sid),
                StrategyReview.status.in_(["submitted", "changes_requested"]),
            )
            .order_by(StrategyReview.created_at.desc())
            .first()
        )
        if active is not None:
            pending_review = {
                "review_id": str(active.id),
                "target_stage": active.target_stage,
                "status": active.status,
                "reviewer_user_id": active.reviewer_user_id,
            }
    except Exception:
        pending_review = None

    # ---- shadow monitor (M88) ----
    shadow_verdict = None
    shadow_drift_score = None
    shadow_primary_concern = None
    has_paper_run = False
    has_shadow_run = False
    try:
        from app.models.strategy_run import StrategyRun as _SR
        paper_run = db.query(_SR).filter(
            _SR.strategy_id == sid,
            _SR.run_type == "paper",
        ).first()
        has_paper_run = paper_run is not None
        live_like = db.query(_SR).filter(
            _SR.strategy_id == sid,
            _SR.run_type.in_(["paper", "live"]),
        ).first()
        has_shadow_run = live_like is not None
        if has_shadow_run:
            from app.services.shadow_monitor import compare_backtest_to_paper
            sm = compare_backtest_to_paper(sid, db)
            shadow_verdict = sm.verdict
            shadow_drift_score = sm.drift_score
            shadow_primary_concern = sm.primary_concern
    except Exception:
        pass

    # ---- evidence verification (M92) ----
    evidence_verification_score = None
    evidence_verification_verdict = None
    evidence_chain_status = None
    verification_primary_concern = None
    try:
        from app.services.evidence_verification import verify_strategy_evidence as _ev
        ev_data = _ev(sid, db)
        evidence_verification_score = ev_data.verification_score
        evidence_verification_verdict = ev_data.verdict
        evidence_chain_status = ev_data.chain_status
        if ev_data.time_consistency_warnings:
            verification_primary_concern = ev_data.time_consistency_warnings[0][:80]
        elif ev_data.link_consistency_warnings:
            verification_primary_concern = ev_data.link_consistency_warnings[0][:80]
    except Exception:
        pass

    # ---- regression: latest run failed_count ----
    regression_failed_count = 0
    try:
        from app.services.regression_tests import get_regression_test_runs

        runs = get_regression_test_runs(sid, db, limit=1)
        if runs:
            regression_failed_count = runs[0].failed_count or 0
    except Exception:
        pass

    # ---- health classification (deterministic 3-way) ----
    # "blocked" is reserved for GENUINE hard problems. An early / under-
    # instrumented strategy (no evidence yet) reports critical health, unmet
    # promotion gates, and an under_instrumented readiness verdict — but that is
    # the normal "needs work" state, NOT a hard block. Classifying it as blocked
    # would make essentially every minimally-evidenced strategy read as blocked
    # and the 3-way manager view useless. So:
    #   - under-instrumented strategies -> review (needs evidence to progress)
    #   - "critical" health blocks ONLY when the strategy is actually
    #     instrumented (critical health then reflects bad evidence, not absence)
    #   - genuine hard problems (open critical alert, failing regression run,
    #     an explicit readiness 'blocked' verdict) ALWAYS block.
    alert_critical = alert_by_severity.get("critical", 0)
    under_instrumented = (
        readiness_verdict == "under_instrumented"
        or reliability_status == "insufficient_evidence"
    )
    hard_problem = (
        alert_critical > 0
        or regression_failed_count > 0
        or readiness_verdict == "blocked"
        or (health_status == "critical" and not under_instrumented)
    )
    if hard_problem:
        health_classification = "blocked"
    elif (
        under_instrumented
        or health_status in ("review", "watch", "critical")
        or alert_open > 0
        or stale_evidence_count > 0
        or missing_report
        or reliability_status in ("review", "weak")
        or promotion_blocker_count > 0
    ):
        health_classification = "review"
    else:
        health_classification = "healthy"

    # ---- top blocker (single most important by priority) ----
    top_blocker = _compute_top_blocker(
        promotion_blockers=promotion_blockers,
        alert_by_severity=alert_by_severity,
        alert_open=alert_open,
        regression_failed_count=regression_failed_count,
        stale_evidence_count=stale_evidence_count,
        stale_count=stale_count,
        missing_count=missing_count,
        missing_report=missing_report,
        readiness_blockers=readiness_blockers,
    )

    return {
        "strategy_id": sid,
        "name": strategy.name,
        "slug": strategy.slug,
        "project_id": strategy.project_id,
        "project_name": project_name,
        "asset_class": strategy.asset_class,
        "status": strategy.status,
        "reliability_score": reliability_score,
        "reliability_status": reliability_status,
        "health_classification": health_classification,
        "health_status": health_status,
        "health_score": health_score,
        "promotion_stage": promotion_stage,
        "promotion_verdict": promotion_verdict,
        "promotion_blocker_count": promotion_blocker_count,
        "open_alert_count": open_alert_count,
        "high_critical_alert_count": high_critical_alert_count,
        "top_blocker": top_blocker,
        "stale_evidence_count": stale_evidence_count,
        "stale_count": stale_count,
        "missing_count": missing_count,
        "aging_count": aging_count,
        "missing_report": missing_report,
        "recent_score_change": recent_score_change,
        "latest_run_at": latest_run_at,
        "days_since_latest_run": days_since_latest_run,
        "owner_user_id": None,
        "owner_name": None,
        "regression_failed_count": regression_failed_count,
        "primary_concern": primary_concern,
        "next_recommended_stage": next_recommended_stage,
        "pending_review": pending_review,
        "shadow_verdict": shadow_verdict,
        "shadow_drift_score": shadow_drift_score,
        "shadow_primary_concern": shadow_primary_concern,
        "has_paper_run": has_paper_run,
        "has_shadow_run": has_shadow_run,
        "evidence_verification_score": evidence_verification_score,
        "evidence_verification_verdict": evidence_verification_verdict,
        "evidence_chain_status": evidence_chain_status,
        "verification_primary_concern": verification_primary_concern,
    }


def _compute_top_blocker(
    *,
    promotion_blockers: list[str],
    alert_by_severity: dict,
    alert_open: int,
    regression_failed_count: int,
    stale_evidence_count: int,
    stale_count: int,
    missing_count: int,
    missing_report: bool,
    readiness_blockers: list[str],
) -> dict | None:
    """Pick the single most important blocker by fixed priority order."""
    # 1. promotion blocker
    if promotion_blockers:
        return {
            "title": promotion_blockers[0],
            "severity": "high",
            "category": "promotion",
            "recommended_action": "Resolve blocking promotion gates before progression.",
            "target_tab": "governance",
        }
    # 2. critical/high open alert
    if alert_by_severity.get("critical", 0) > 0:
        return {
            "title": "Critical-severity alert is open",
            "severity": "critical",
            "category": "alert",
            "recommended_action": "Resolve the open critical alert in Governance.",
            "target_tab": "governance",
        }
    if alert_by_severity.get("high", 0) > 0:
        return {
            "title": "High-severity alert is open",
            "severity": "high",
            "category": "alert",
            "recommended_action": "Review and resolve the open high-severity alert.",
            "target_tab": "governance",
        }
    # 3. regression failure
    if regression_failed_count > 0:
        return {
            "title": f"{regression_failed_count} regression test(s) failing",
            "severity": "high",
            "category": "regression",
            "recommended_action": "Investigate failing regression tests in Governance.",
            "target_tab": "governance",
        }
    # 4. stale / missing evidence
    if stale_evidence_count > 0:
        return {
            "title": f"{stale_count} stale and {missing_count} missing evidence type(s)",
            "severity": "medium",
            "category": "evidence",
            "recommended_action": "Refresh stale and missing evidence.",
            "target_tab": "evidence",
        }
    # 5. missing report
    if missing_report:
        return {
            "title": "Reliability report missing for latest run",
            "severity": "low",
            "category": "report",
            "recommended_action": "Generate a strategy reliability report.",
            "target_tab": "exports",
        }
    # 6. readiness blocker
    if readiness_blockers:
        return {
            "title": readiness_blockers[0],
            "severity": "medium",
            "category": "readiness",
            "recommended_action": "Resolve readiness blockers before progression.",
            "target_tab": "governance",
        }
    return None


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build_portfolio_reliability(
    db: Session,
    organization_id=None,
    project_id=None,
    include_archived: bool = False,
) -> dict:
    """Build the full portfolio reliability payload (plain dicts)."""
    now = datetime.now(timezone.utc)

    strategies = _enumerate_strategies(
        db,
        organization_id=organization_id,
        project_id=project_id,
        include_archived=include_archived,
    )
    resolved_org = _resolve_organization_id(
        db,
        organization_id=organization_id,
        project_id=project_id,
        strategies=strategies,
    )

    rows: list[dict] = []
    for s in strategies:
        try:
            rows.append(_aggregate_strategy(s, db))
        except Exception:
            # Defensive: a row should never break the whole portfolio.
            continue

    # ---- default ranking: reliability_score DESC, None last ----
    rows.sort(
        key=lambda r: (
            0 if r["reliability_score"] is not None else 1,
            -(r["reliability_score"] or 0.0),
            r["name"],
        )
    )

    # ---- summary ----
    summary = _build_summary(db, rows, strategies, resolved_org)

    # ---- sections ----
    worst_blockers = _section_worst_blockers(rows)
    stale_evidence = _section_stale_evidence(rows)
    missing_reports = _section_missing_reports(rows)
    recent_score_changes = _section_recent_score_changes(rows)

    return {
        "generated_at": now,
        "summary": summary,
        "strategies": rows,
        "worst_blockers": worst_blockers,
        "stale_evidence": stale_evidence,
        "missing_reports": missing_reports,
        "recent_score_changes": recent_score_changes,
        "disclaimer": DISCLAIMER,
    }


def _build_summary(db: Session, rows: list[dict], strategies, resolved_org) -> dict:
    total = len(rows)
    healthy = sum(1 for r in rows if r["health_classification"] == "healthy")
    review = sum(1 for r in rows if r["health_classification"] == "review")
    blocked = sum(1 for r in rows if r["health_classification"] == "blocked")

    rel_scores = [r["reliability_score"] for r in rows if r["reliability_score"] is not None]
    average_reliability = round(sum(rel_scores) / len(rel_scores), 1) if rel_scores else None

    strategies_with_stale = sum(1 for r in rows if r["stale_evidence_count"] > 0)
    strategies_missing_reports = sum(1 for r in rows if r["missing_report"])

    open_high_critical_alerts = 0
    if resolved_org is not None:
        try:
            from app.services.alerts import get_high_critical_alert_count

            open_high_critical_alerts = get_high_critical_alert_count(
                db, str(resolved_org)
            )
        except Exception:
            open_high_critical_alerts = 0

    # ---- ready for paper candidate ----
    ready_for_paper = sum(
        1
        for r in rows
        if r.get("promotion_verdict") in ("pass", "conditional_pass")
    )

    # ---- ready for production candidate (only re-evaluate those who passed paper) ----
    ready_for_production = 0
    for r in rows:
        if r.get("promotion_verdict") not in ("pass", "conditional_pass"):
            continue
        try:
            from app.services.promotion_gates import evaluate_promotion_gates

            prod_gate = evaluate_promotion_gates(
                r["strategy_id"], "production_candidate", db
            )
            if prod_gate.promotion_verdict in ("pass", "conditional_pass"):
                ready_for_production += 1
        except Exception:
            continue

    return {
        "total_strategies": total,
        "healthy_count": healthy,
        "review_count": review,
        "blocked_count": blocked,
        "average_reliability": average_reliability,
        "strategies_with_stale_evidence": strategies_with_stale,
        "strategies_missing_reports": strategies_missing_reports,
        "open_high_critical_alerts": open_high_critical_alerts,
        "ready_for_paper_candidate": ready_for_paper,
        "ready_for_production_candidate": ready_for_production,
    }


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _section_worst_blockers(rows: list[dict]) -> list[dict]:
    candidates = [r for r in rows if r["top_blocker"] is not None]

    def _key(r: dict):
        tb = r["top_blocker"]
        sev_rank = SEVERITY_RANK.get(tb.get("severity"), 99)
        return (sev_rank, -(r["promotion_blocker_count"] or 0))

    candidates.sort(key=_key)
    out = []
    for r in candidates[:5]:
        tb = r["top_blocker"]
        out.append(
            {
                "strategy_id": r["strategy_id"],
                "strategy_name": r["name"],
                "blocker_title": tb["title"],
                "severity": tb["severity"],
                "recommended_action": tb["recommended_action"],
                "category": tb["category"],
                "target_tab": tb["target_tab"],
            }
        )
    return out


def _section_stale_evidence(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        if r["stale_evidence_count"] > 0:
            out.append(
                {
                    "strategy_id": r["strategy_id"],
                    "strategy_name": r["name"],
                    "stale_count": r["stale_count"],
                    "missing_count": r["missing_count"],
                    "aging_count": r["aging_count"],
                }
            )
    return out


def _section_missing_reports(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        if r["missing_report"]:
            out.append(
                {
                    "strategy_id": r["strategy_id"],
                    "strategy_name": r["name"],
                    "latest_run_at": r["latest_run_at"],
                }
            )
    return out


def _section_recent_score_changes(rows: list[dict]) -> list[dict]:
    candidates = [r for r in rows if r["recent_score_change"] is not None]
    candidates.sort(key=lambda r: r["recent_score_change"]["delta"])
    out = []
    for r in candidates:
        rsc = r["recent_score_change"]
        out.append(
            {
                "strategy_id": r["strategy_id"],
                "strategy_name": r["name"],
                "delta": rsc["delta"],
                "latest": rsc["latest"],
                "previous": rsc["previous"],
                "direction": rsc["direction"],
            }
        )
    return out


# ---------------------------------------------------------------------------
# Markdown renderer (export + weekly review pack)
# ---------------------------------------------------------------------------

def _fmt(v) -> str:
    if v is None:
        return "—"
    return str(v)


def render_portfolio_reliability_markdown(payload: dict) -> str:
    """Render the portfolio reliability payload as a Markdown document."""
    lines: list[str] = []
    generated_at = payload.get("generated_at")
    summary = payload.get("summary", {})
    strategies = payload.get("strategies", [])

    lines.append("# Portfolio Reliability Summary")
    lines.append("")
    lines.append(f"_Generated at: {_fmt(generated_at)}_")
    lines.append("")

    # ---- Portfolio summary ----
    lines.append("## Portfolio Summary")
    lines.append("")
    lines.append(f"- Total strategies: {_fmt(summary.get('total_strategies'))}")
    lines.append(f"- Healthy: {_fmt(summary.get('healthy_count'))}")
    lines.append(f"- Review: {_fmt(summary.get('review_count'))}")
    lines.append(f"- Blocked: {_fmt(summary.get('blocked_count'))}")
    lines.append(f"- Average reliability: {_fmt(summary.get('average_reliability'))}")
    lines.append(
        f"- Strategies with stale evidence: "
        f"{_fmt(summary.get('strategies_with_stale_evidence'))}"
    )
    lines.append(
        f"- Strategies missing reports: "
        f"{_fmt(summary.get('strategies_missing_reports'))}"
    )
    lines.append(
        f"- Open high/critical alerts: {_fmt(summary.get('open_high_critical_alerts'))}"
    )
    lines.append(
        f"- Ready for paper candidate: {_fmt(summary.get('ready_for_paper_candidate'))}"
    )
    lines.append(
        f"- Ready for production candidate: "
        f"{_fmt(summary.get('ready_for_production_candidate'))}"
    )
    lines.append("")

    # ---- Ranked strategy table ----
    lines.append("## Ranked Strategies")
    lines.append("")
    lines.append(
        "| Rank | Strategy | Project | Reliability | Status | Classification | "
        "Stage | Open Alerts | Stale Evidence | Owner |"
    )
    lines.append(
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    for i, r in enumerate(strategies, start=1):
        lines.append(
            f"| {i} | {_fmt(r.get('name'))} | {_fmt(r.get('project_name'))} | "
            f"{_fmt(r.get('reliability_score'))} | {_fmt(r.get('reliability_status'))} | "
            f"{_fmt(r.get('health_classification'))} | {_fmt(r.get('promotion_stage'))} | "
            f"{_fmt(r.get('open_alert_count'))} | {_fmt(r.get('stale_evidence_count'))} | "
            f"{_fmt(r.get('owner_name'))} |"
        )
    lines.append("")

    # ---- Top blockers ----
    lines.append("## Top Blockers")
    lines.append("")
    worst = payload.get("worst_blockers", [])
    if worst:
        for b in worst:
            lines.append(
                f"- **{_fmt(b.get('strategy_name'))}** "
                f"({_fmt(b.get('severity'))}): {_fmt(b.get('blocker_title'))} — "
                f"{_fmt(b.get('recommended_action'))}"
            )
    else:
        lines.append("- No blockers detected.")
    lines.append("")

    # ---- Stale evidence ----
    lines.append("## Stale Evidence")
    lines.append("")
    stale = payload.get("stale_evidence", [])
    if stale:
        for s in stale:
            lines.append(
                f"- **{_fmt(s.get('strategy_name'))}**: "
                f"{_fmt(s.get('stale_count'))} stale, "
                f"{_fmt(s.get('missing_count'))} missing, "
                f"{_fmt(s.get('aging_count'))} aging"
            )
    else:
        lines.append("- No stale evidence.")
    lines.append("")

    # ---- Missing reports ----
    lines.append("## Missing Reports")
    lines.append("")
    missing = payload.get("missing_reports", [])
    if missing:
        for m in missing:
            lines.append(
                f"- **{_fmt(m.get('strategy_name'))}** "
                f"(latest run: {_fmt(m.get('latest_run_at'))})"
            )
    else:
        lines.append("- No missing reports.")
    lines.append("")

    # ---- Recent score changes ----
    lines.append("## Recent Score Changes")
    lines.append("")
    changes = payload.get("recent_score_changes", [])
    if changes:
        for c in changes:
            lines.append(
                f"- **{_fmt(c.get('strategy_name'))}**: "
                f"{_fmt(c.get('previous'))} → {_fmt(c.get('latest'))} "
                f"(delta {_fmt(c.get('delta'))}, {_fmt(c.get('direction'))})"
            )
    else:
        lines.append("- No recent score changes (insufficient history).")
    lines.append("")

    # ---- Strategies ready for next stage ----
    lines.append("## Strategies Ready for Next Stage")
    lines.append("")
    ready_rows = [
        r
        for r in strategies
        if r.get("promotion_verdict") in ("pass", "conditional_pass")
    ]
    if ready_rows:
        for r in ready_rows:
            lines.append(
                f"- **{_fmt(r.get('name'))}**: paper-candidate verdict "
                f"{_fmt(r.get('promotion_verdict'))} "
                f"(current stage: {_fmt(r.get('promotion_stage'))})"
            )
    else:
        lines.append("- No strategies currently ready for promotion.")
    lines.append("")

    # ---- Disclaimer ----
    lines.append("---")
    lines.append("")
    lines.append(f"_{payload.get('disclaimer', DISCLAIMER)}_")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Refresh — persist a fresh reliability score for every in-scope strategy.
# Reuses the exact compute+store path used by
# POST /api/strategies/{id}/reliability-score.
# ---------------------------------------------------------------------------

def refresh_portfolio_reliability(
    db: Session,
    organization_id=None,
    project_id=None,
    include_archived: bool = False,
) -> dict:
    """Recompute and persist a reliability score for every in-scope strategy.

    Mirrors the per-strategy POST path: compute_reliability_score -> insert a
    StrategyReliabilityScore row -> AuditTimelineEvent -> commit.
    """
    from app.core.constants import EventType, Severity
    from app.models.audit_timeline_event import AuditTimelineEvent
    from app.models.project import Project
    from app.models.strategy_reliability_score import StrategyReliabilityScore
    from app.services.strategy_reliability import compute_reliability_score

    now = datetime.now(timezone.utc)
    strategies = _enumerate_strategies(
        db,
        organization_id=organization_id,
        project_id=project_id,
        include_archived=include_archived,
    )

    refreshed = 0
    for strategy in strategies:
        try:
            score_data = compute_reliability_score(str(strategy.id), db)
            score_row = StrategyReliabilityScore(**score_data)
            db.add(score_row)
            db.flush()

            project = (
                db.query(Project).filter(Project.id == strategy.project_id).first()
            )
            org_id = project.organization_id if project else None

            event = AuditTimelineEvent(
                organization_id=org_id,
                project_id=strategy.project_id,
                strategy_id=strategy.id,
                event_type=EventType.strategy_reliability_scored,
                title=f"Reliability scored: {score_row.status}",
                description=(
                    f"Reliability score computed for strategy '{strategy.name}' "
                    f"via portfolio reliability refresh. "
                    f"Overall: "
                    f"{score_row.overall_score if score_row.overall_score is not None else 'N/A'}/100. "
                    f"Status: {score_row.status}."
                ),
                source_type="strategy_reliability_score",
                source_id=str(score_row.id),
                severity=Severity.info,
                metadata_json={
                    "overall_score": score_row.overall_score,
                    "status": score_row.status,
                    "strategy_name": strategy.name,
                    "source": "portfolio_reliability_refresh",
                },
            )
            db.add(event)
            refreshed += 1
        except Exception:
            # One bad strategy cannot abort the whole refresh.
            continue

    db.commit()
    return {"strategies_refreshed": refreshed, "generated_at": now}
