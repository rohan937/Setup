"""M78 — Advanced demo strategy seed: "US Equity Quality-Momentum Rotation".

Creates ONE realistic, multi-version equity strategy with a full historical
evidence trail (versions, configs, universes, signals, datasets, runs, audits,
reliability scores, reports, alerts, review cases, governance, timeline) so the
whole product can be demoed end-to-end.

Deterministic synthetic data only — NOT real trading performance, no AI, no
external market data. Idempotent: re-running reuses existing artifacts (deduped
by natural keys) and never duplicates the strategy.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.constants import EventType, RunType, Severity
# Reuse the battle-tested construction helpers from the clean-demo seed.
from app.services.demo_seed import (
    _dt,
    _date_str,
    _get_or_create_strategy,
    _make_audit,
    _make_config,
    _make_dataset_snapshot,
    _make_review_case,
    _make_run,
    _make_signal,
    _make_universe,
    _make_version,
    _utcnow,
    DEMO_ORG_NAME,
    DEMO_ORG_SLUG,
    DEMO_PROJECT_NAME,
    DEMO_PROJECT_SLUG,
)

STRATEGY_NAME = "US Equity Quality-Momentum Rotation"
STRATEGY_SLUG = "us-equity-quality-momentum-rotation"
STRATEGY_DESC = (
    "Systematic long/flat US large-cap rotation. Ranks a liquid universe by "
    "quality, 12-month momentum, and a volatility filter, rebalancing monthly. "
    "Demo strategy with deterministic synthetic evidence — not real performance."
)

# 20-symbol liquid US large-cap universe.
_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "XOM", "UNH", "COST",
    "HD", "LLY", "AVGO", "MA", "V", "PG", "JNJ", "WMT", "ORCL", "ADBE",
]

# ---------------------------------------------------------------------------
# Per-version specs (the story: high Sharpe ≠ reliable)
# ---------------------------------------------------------------------------

_VERSIONS = [
    {
        "label": "v1 Research Prototype",
        "git": "qmr1a01",
        "code": "strategies/quality_momentum_rotation.py",
        "signal_name": "quality_momentum_score",
        # v1 — weak assumptions: same-close fill, zero costs, no guardrails.
        "config": {
            "params": {"rebalance_frequency": "monthly", "rank_top_n": 15, "momentum_lookback_months": 12},
            "assumptions": {
                "transaction_cost_bps": 0,
                "fill_model": "same_close",
                "max_leverage": 2.0,
            },
        },
        "univ_meta": {"universe_type": "US_LARGE_CAP", "liquidity_filter": "none", "sector_cap": "none"},
        "metrics": {"sharpe": 1.80, "annual_return": 0.160, "volatility": 0.120,
                    "max_drawdown": -0.180, "turnover": 8.5, "trade_count": 2140, "win_rate": 0.55},
        "rel_score": 48, "rel_status": "weak", "report_score": 48,
        "run_offset": -300,
    },
    {
        "label": "v2 Cost-Aware Backtest",
        "git": "qmr2b14",
        "code": "strategies/quality_momentum_rotation_v2.py",
        "signal_name": "quality_momentum_score_v2",
        "config": {
            "params": {"rebalance_frequency": "monthly", "rank_top_n": 15, "momentum_lookback_months": 12},
            "assumptions": {
                "transaction_cost_bps": 6,
                "slippage_bps": 3,
                "fill_model": "next_bar_open",
                "max_leverage": 1.0,
                "max_position_weight": 0.10,
            },
        },
        "univ_meta": {"universe_type": "US_LARGE_CAP", "liquidity_filter": "adv_1m_gt_20m", "sector_cap": "none"},
        "metrics": {"sharpe": 1.35, "annual_return": 0.120, "volatility": 0.110,
                    "max_drawdown": -0.150, "turnover": 5.2, "trade_count": 1310, "win_rate": 0.54},
        "rel_score": 69, "rel_status": "review", "report_score": 68,
        "run_offset": -210,
    },
    {
        "label": "v3 Liquidity + Turnover Controls",
        "git": "qmr3c27",
        "code": "strategies/quality_momentum_rotation_v3.py",
        "signal_name": "quality_momentum_score_v3",
        "config": {
            "params": {"rebalance_frequency": "monthly", "rank_top_n": 12, "momentum_lookback_months": 12,
                       "turnover_target": 2.5},
            "assumptions": {
                "transaction_cost_bps": 6,
                "slippage_bps": 3,
                "fill_model": "next_bar_open",
                "max_leverage": 1.0,
                "max_position_weight": 0.08,
                "liquidity_filter": "adv_1m_gt_25m",
                "sector_cap": 0.30,
            },
        },
        "univ_meta": {"universe_type": "US_LARGE_CAP", "liquidity_filter": "adv_1m_gt_25m", "sector_cap": "0.30"},
        "metrics": {"sharpe": 1.25, "annual_return": 0.105, "volatility": 0.095,
                    "max_drawdown": -0.100, "turnover": 2.4, "trade_count": 610, "win_rate": 0.56},
        "rel_score": 83, "rel_status": "good", "report_score": 83,
        "run_offset": -120,
    },
    {
        "label": "v4 Paper Candidate",
        "git": "qmr4d39",
        "code": "strategies/quality_momentum_rotation_v4.py",
        "signal_name": "quality_momentum_score_v4",
        "config": {
            "params": {"rebalance_frequency": "monthly", "rank_top_n": 12, "momentum_lookback_months": 12,
                       "turnover_target": 2.0},
            "assumptions": {
                "transaction_cost_bps": 7,
                "slippage_bps": 4,
                "fill_model": "next_bar_open",
                "max_leverage": 1.0,
                "max_position_weight": 0.08,
                "liquidity_filter": "adv_1m_gt_30m",
                "sector_cap": 0.30,
                "turnover_target": 2.0,
            },
        },
        "univ_meta": {"universe_type": "US_LARGE_CAP", "liquidity_filter": "adv_1m_gt_30m", "sector_cap": "0.30"},
        "metrics": {"sharpe": 1.18, "annual_return": 0.098, "volatility": 0.090,
                    "max_drawdown": -0.085, "turnover": 1.9, "trade_count": 470, "win_rate": 0.57},
        "rel_score": 86, "rel_status": "good", "report_score": 87,
        "run_offset": -35,
    },
]


# ---------------------------------------------------------------------------
# Synthetic evidence-row builders (deterministic)
# ---------------------------------------------------------------------------

def _ohlcv_rows(symbols, base_price, day_offset, health="clean"):
    """Build a compact deterministic OHLCV snapshot (1 date per symbol)."""
    rows = []
    for i, sym in enumerate(symbols):
        p = base_price + i * 7.5
        o, h, lo, c = p, p * 1.012, p * 0.991, p * 1.004
        vol = 20_000_000 + i * 1_500_000
        if health == "gap" and i == 3:
            vol = None  # intentional missing-volume quality issue
        rows.append({
            "symbol": sym, "timestamp": _date_str(day_offset),
            "open": round(o, 2), "high": round(h, 2), "low": round(lo, 2),
            "close": round(c, 2), "volume": vol,
        })
    return rows


def _signal_rows(symbols, day_offset, sparse=False):
    """Build a deterministic quality-momentum signal snapshot."""
    rows = []
    n = len(symbols)
    for i, sym in enumerate(symbols):
        # Deterministic pseudo-rank score in [-1.5, 1.5].
        val = round(1.5 - (3.0 * i / max(1, n - 1)), 3)
        if sparse and i % 4 == 0:
            val = None  # incomplete coverage for the early (weak) versions
        rows.append({"symbol": sym, "timestamp": _date_str(day_offset), "signal": val})
    return rows


# ---------------------------------------------------------------------------
# Idempotent direct-construct helpers
# ---------------------------------------------------------------------------

def _reliability_score(db, strategy_id, *, overall, status, generated_at) -> bool:
    from app.models.strategy_reliability_score import StrategyReliabilityScore
    exists = (
        db.query(StrategyReliabilityScore)
        .filter(
            StrategyReliabilityScore.strategy_id == strategy_id,
            StrategyReliabilityScore.generated_at == generated_at,
        )
        .first()
    )
    if exists:
        return False
    db.add(StrategyReliabilityScore(
        strategy_id=strategy_id,
        generated_at=generated_at,
        overall_score=float(overall),
        status=status,
        backtest_trust_score=float(overall),
        data_evidence_score=float(min(100, overall + 4)),
        config_evidence_score=float(overall),
    ))
    db.flush()
    return True


def _report(db, org_id, strategy_id, *, title, score, generated_at, summary) -> bool:
    from app.models.report import Report
    exists = (
        db.query(Report)
        .filter(Report.strategy_id == strategy_id, Report.title == title)
        .first()
    )
    if exists:
        return False
    db.add(Report(
        organization_id=org_id,
        strategy_id=strategy_id,
        report_type="strategy_reliability",
        title=title,
        status="generated",
        summary=summary,
        score=int(score),
        generated_at=generated_at,
        source_type="strategy",
        source_id=str(strategy_id),
        report_json={"demo": True, "headline": summary},
    ))
    db.flush()
    return True


def _alert(db, org_id, strategy_id, *, rule_type, severity, status, title, description,
           triggered_at, resolved_at=None) -> bool:
    from app.models.alert import Alert
    # alerts.organization_id / strategy_id are String(36) FKs to Uuid PKs stored
    # as 32-char hex — match the real generate_alerts convention (.hex).
    sid_hex = strategy_id.hex
    org_hex = org_id.hex
    exists = (
        db.query(Alert)
        .filter(Alert.strategy_id == sid_hex, Alert.rule_type == rule_type,
                Alert.title == title)
        .first()
    )
    if exists:
        return False
    db.add(Alert(
        organization_id=org_hex,
        strategy_id=sid_hex,
        rule_type=rule_type,
        status=status,
        severity=severity,
        title=title,
        description=description,
        source_type="backtest_audit",
        triggered_at=triggered_at,
        resolved_at=resolved_at,
        metadata_json={"demo": True},
    ))
    db.flush()
    return True


def _timeline(db, org_id, project_id, strategy_id, *, event_type, title, description,
              severity, event_time, source_type="strategy", source_id=None) -> bool:
    from app.models.audit_timeline_event import AuditTimelineEvent
    exists = (
        db.query(AuditTimelineEvent)
        .filter(
            AuditTimelineEvent.strategy_id == strategy_id,
            AuditTimelineEvent.event_type == event_type,
            AuditTimelineEvent.title == title,
        )
        .first()
    )
    if exists:
        return False
    db.add(AuditTimelineEvent(
        organization_id=org_id,
        project_id=project_id,
        strategy_id=strategy_id,
        event_type=event_type,
        title=title,
        description=description,
        source_type=source_type,
        source_id=source_id or str(strategy_id),
        severity=severity,
        event_time=event_time,
        metadata_json={"demo": True},
    ))
    db.flush()
    return True


# ---------------------------------------------------------------------------
# Org / project
# ---------------------------------------------------------------------------

def _get_or_create_org_project(db) -> tuple:
    from app.models.organization import Organization
    from app.models.project import Project

    org = db.query(Organization).first()
    if org is None:
        org = Organization(name=DEMO_ORG_NAME, slug=DEMO_ORG_SLUG)
        db.add(org)
        db.flush()

    project = db.query(Project).filter(Project.organization_id == org.id).first()
    if project is None:
        project = Project(
            organization_id=org.id,
            name=DEMO_PROJECT_NAME,
            slug=DEMO_PROJECT_SLUG,
            description="Demo portfolio for QuantFidelity product walkthroughs.",
        )
        db.add(project)
        db.flush()
    return org, project


def _final_counts(db, strategy_id) -> dict:
    """Query the actual resulting artifact counts for the strategy."""
    from app.models.strategy_version import StrategyVersion
    from app.models.strategy_config_snapshot import StrategyConfigSnapshot
    from app.models.universe_snapshot import UniverseSnapshot
    from app.models.signal_snapshot import SignalSnapshot
    from app.models.strategy_run import StrategyRun
    from app.models.backtest_audit import BacktestAudit
    from app.models.strategy_reliability_score import StrategyReliabilityScore
    from app.models.report import Report
    from app.models.alert import Alert
    from app.models.review_case import ResearchReviewCase
    from app.models.audit_timeline_event import AuditTimelineEvent

    def c(model, *crit):
        return db.query(model).filter(*crit).count()

    return {
        "versions": c(StrategyVersion, StrategyVersion.strategy_id == strategy_id),
        "configs": c(StrategyConfigSnapshot, StrategyConfigSnapshot.strategy_id == strategy_id),
        "universes": c(UniverseSnapshot, UniverseSnapshot.strategy_id == strategy_id),
        "signals": c(SignalSnapshot, SignalSnapshot.strategy_id == strategy_id),
        "runs": c(StrategyRun, StrategyRun.strategy_id == strategy_id),
        "audits": db.query(BacktestAudit)
        .join(StrategyRun, BacktestAudit.strategy_run_id == StrategyRun.id)
        .filter(StrategyRun.strategy_id == strategy_id)
        .count(),
        "reliability_scores": c(StrategyReliabilityScore, StrategyReliabilityScore.strategy_id == strategy_id),
        "reports": c(Report, Report.strategy_id == strategy_id),
        "alerts": c(Alert, Alert.strategy_id == strategy_id.hex),
        "review_cases": c(ResearchReviewCase, ResearchReviewCase.strategy_id == strategy_id.hex),
        "timeline_events": c(AuditTimelineEvent, AuditTimelineEvent.strategy_id == strategy_id),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def seed_advanced_demo_strategy(db: Session) -> dict:
    """Create (or idempotently refresh) the advanced demo strategy.

    Returns a result dict with status (created|refreshed), strategy_id, name,
    and artifact counts.
    """
    org, project = _get_or_create_org_project(db)
    strategy, created = _get_or_create_strategy(
        db, project.id, STRATEGY_NAME, STRATEGY_SLUG, "equity", "active",
    )
    if not strategy.description:
        strategy.description = STRATEGY_DESC
    else:
        strategy.description = STRATEGY_DESC
    db.flush()

    counts = {
        "versions": 0, "configs": 0, "universes": 0, "signals": 0, "datasets": 0,
        "runs": 0, "audits": 0, "reliability_scores": 0, "reports": 0,
        "alerts": 0, "review_cases": 0, "timeline_events": 0, "governance": 0,
    }

    version_objs = []
    run_objs = []

    # --- Versions, evidence, runs ---------------------------------------
    for i, spec in enumerate(_VERSIONS):
        v, v_created = _make_version(
            db, strategy.id, spec["label"], spec["git"], "main", spec["code"], spec["signal_name"],
        )
        if v_created:
            counts["versions"] += 1
        version_objs.append(v)

        cfg = _make_config(db, strategy.id, v.id, f"{spec['label']} Config", spec["config"])
        if cfg is not None:
            counts["configs"] += 1

        uni = _make_universe(
            db, strategy.id, v.id, f"{spec['label']} Universe", _UNIVERSE, spec["univ_meta"],
        )
        if uni is not None:
            counts["universes"] += 1

        sparse = i < 2  # v1/v2 have incomplete signal coverage
        sig = _make_signal(
            db, strategy.id, v.id, uni.id if uni else None,
            f"{spec['label']} Signal", spec["signal_name"],
            _signal_rows(_UNIVERSE, spec["run_offset"] + 2, sparse=sparse),
        )
        if sig is not None:
            counts["signals"] += 1

        dsnap = _make_dataset_snapshot(
            db, project.id,
            f"US Equity OHLCV — {STRATEGY_NAME}",
            "Synthetic daily OHLCV for the quality-momentum universe.",
            _ohlcv_rows(_UNIVERSE, 100.0, spec["run_offset"], health="gap" if i == 0 else "clean"),
            version_label=spec["label"].split()[0],  # v1/v2/v3/v4
        )
        if dsnap is not None:
            counts["datasets"] += 1

        # Research run only for v1; every version gets a backtest run.
        if i == 0:
            research = _make_run(
                db, strategy.id, v.id, dsnap.id if dsnap else None,
                uni.id if uni else None, sig.id if sig else None,
                f"{STRATEGY_NAME} — Research", RunType.research,
                spec["config"]["params"], spec["config"]["assumptions"],
                {"sharpe": 1.9, "annual_return": 0.171, "volatility": 0.124,
                 "max_drawdown": -0.205, "turnover": 9.1, "trade_count": 2300, "win_rate": 0.55},
                "Initial research run — strong headline Sharpe on unrealistic assumptions.",
                _dt(spec["run_offset"] - 5),
            )
            if research:
                run_objs.append(("research", research))
                counts["runs"] += 1

        bt = _make_run(
            db, strategy.id, v.id, dsnap.id if dsnap else None,
            uni.id if uni else None, sig.id if sig else None,
            f"{STRATEGY_NAME} — Backtest {spec['label'].split()[0]}", RunType.backtest,
            spec["config"]["params"], spec["config"]["assumptions"], spec["metrics"],
            f"Backtest for {spec['label']}.",
            _dt(spec["run_offset"]),
        )
        if bt:
            run_objs.append((spec["label"].split()[0], bt))
            counts["runs"] += 1
            if _make_audit(db, bt, True) is not None:
                counts["audits"] += 1

        # Reliability score snapshot per version (progression).
        if _reliability_score(db, strategy.id, overall=spec["rel_score"],
                              status=spec["rel_status"], generated_at=_dt(spec["run_offset"] + 1)):
            counts["reliability_scores"] += 1

        # Report per version.
        _REPORT_TITLES = [
            "Initial Research Review", "Cost Model Review",
            "Regression Improvement Review", "Paper Candidate Readiness Review",
        ]
        _REPORT_SUMMARIES = [
            "v1 shows a high headline Sharpe (1.8) but relies on same-close fills and zero "
            "transaction costs. Trust is low; do not progress.",
            "v2 adds realistic transaction costs and next-bar-open fills. Sharpe falls to 1.35 "
            "but the result is far more trustworthy. Turnover and drawdown still need work.",
            "v3 adds liquidity filters, a sector cap, and turnover control. Turnover drops to 2.4x, "
            "drawdown improves to -10%, and audit trust rises markedly.",
            "v4 is close to a paper candidate: high evidence coverage and audit trust, low turnover. "
            "Not yet production-clean — the paper run is new and the SLA needs a review.",
        ]
        if _report(db, org.id, strategy.id, title=_REPORT_TITLES[i],
                   score=spec["report_score"], generated_at=_dt(spec["run_offset"] + 2),
                   summary=_REPORT_SUMMARIES[i]):
            counts["reports"] += 1

        # Timeline: version + run.
        if _timeline(db, org.id, project.id, strategy.id,
                     event_type=EventType.strategy_version_created,
                     title=f"Version created: {spec['label']}",
                     description=f"{spec['label']} registered.",
                     severity=Severity.info, event_time=_dt(spec["run_offset"] - 1)):
            counts["timeline_events"] += 1

    # Current reliability score (5th point, most recent).
    if _reliability_score(db, strategy.id, overall=86, status="good", generated_at=_dt(-2)):
        counts["reliability_scores"] += 1

    # --- Paper + live-like runs (v4) ------------------------------------
    v4 = version_objs[-1]
    paper = _make_run(
        db, strategy.id, v4.id, None, None, None,
        f"{STRATEGY_NAME} — Paper Candidate", RunType.paper,
        _VERSIONS[-1]["config"]["params"], _VERSIONS[-1]["config"]["assumptions"],
        {"sharpe": 1.12, "annual_return": 0.091, "volatility": 0.088,
         "max_drawdown": -0.079, "turnover": 1.8, "trade_count": 38, "win_rate": 0.58},
        "First paper run — too recent to fully confirm live behavior.",
        _dt(-18),
    )
    if paper:
        run_objs.append(("paper", paper))
        counts["runs"] += 1
        if _make_audit(db, paper, True) is not None:
            counts["audits"] += 1

    live = _make_run(
        db, strategy.id, v4.id, None, None, None,
        f"{STRATEGY_NAME} — Shadow (live-like)", RunType.live,
        _VERSIONS[-1]["config"]["params"], _VERSIONS[-1]["config"]["assumptions"],
        {"sharpe": 1.05, "annual_return": 0.084, "volatility": 0.087,
         "max_drawdown": -0.071, "turnover": 1.7, "trade_count": 9, "win_rate": 0.56},
        "Shadow / live-like monitoring run alongside the paper candidate.",
        _dt(-6),
    )
    if live:
        run_objs.append(("live", live))
        counts["runs"] += 1

    # --- Alerts (mix of resolved + open) --------------------------------
    _ALERTS = [
        ("fill_model_unrealistic", "high", "resolved", "Same-close fill model (v1)",
         "v1 used a same-close fill model that ignores execution slippage.", -300, -210),
        ("missing_transaction_costs", "high", "resolved", "Missing transaction costs (v1)",
         "v1 assumed zero transaction costs, inflating returns.", -300, -210),
        ("high_turnover", "high", "resolved", "Excessive turnover (v1)",
         "v1 turnover of 8.5x is unrealistic for a monthly rotation.", -300, -120),
        ("drawdown_review", "medium", "resolved", "Drawdown review (v2)",
         "v2 max drawdown of -15% flagged for review.", -210, -120),
        ("turnover_elevated", "medium", "resolved", "Turnover still elevated (v2)",
         "v2 turnover of 5.2x remained above target.", -210, -120),
        ("dataset_health", "low", "resolved", "Dataset health warning (v3)",
         "One symbol was missing a volume value in the v3 dataset snapshot.", -120, -35),
        ("liquidity_coverage", "low", "resolved", "Liquidity coverage note (v3)",
         "Liquidity filter excluded thinly-traded names; coverage confirmed adequate.", -120, -35),
        ("stale_report", "medium", "open", "Reliability report aging (v4)",
         "The latest reliability report is approaching the freshness limit.", -10, None),
        ("paper_run_coverage", "medium", "open", "Paper run coverage too new (v4)",
         "The paper run is recent; more live-like coverage is needed before promotion.", -8, None),
        ("sla_review_due", "low", "open", "Evidence SLA review due (v4)",
         "An evidence SLA review is due for the paper-candidate stage.", -4, None),
    ]
    for rule, sev, status, title, desc, t_off, r_off in _ALERTS:
        if _alert(db, org.id, strategy.id, rule_type=rule, severity=sev, status=status,
                  title=title, description=desc, triggered_at=_dt(t_off),
                  resolved_at=_dt(r_off) if r_off is not None else None):
            counts["alerts"] += 1
            if _timeline(db, org.id, project.id, strategy.id, event_type=EventType.alert_raised,
                         title=f"Alert: {title}", description=desc,
                         severity=Severity.info, event_time=_dt(t_off), source_type="alert"):
                counts["timeline_events"] += 1

    # --- Review cases ----------------------------------------------------
    rc1 = _make_review_case(
        db, strategy.id, "Unrealistic Execution Assumptions",
        "unrealistic_execution_assumptions", "high", "backtest_audit",
        "v1 used same-close fills and zero costs. Resolved after v3 added realistic costs, "
        "next-bar-open fills, and liquidity filters.",
    )
    if rc1 is not None:
        rc1.status = "resolved"
        rc1.acknowledged_at = _dt(-280)
        rc1.resolved_at = _dt(-120)
        counts["review_cases"] += 1
    rc2 = _make_review_case(
        db, strategy.id, "Turnover and Cost Sensitivity Review",
        "turnover_cost_sensitivity_review", "medium", "assumptions",
        "Turnover and cost-sensitivity review across v2/v3. Acknowledged; turnover controls "
        "in v3/v4 substantially reduced sensitivity.",
    )
    if rc2 is not None:
        rc2.status = "acknowledged"
        rc2.acknowledged_at = _dt(-100)
        counts["review_cases"] += 1
    rc3 = _make_review_case(
        db, strategy.id, "Paper Candidate Evidence Finalization",
        "paper_candidate_evidence_finalization", "medium", "evidence_quality",
        "Finalize paper-candidate evidence: refresh the reliability report, confirm SLA "
        "evaluation, and extend paper-run coverage before promotion.",
    )
    if rc3 is not None:
        counts["review_cases"] += 1
    db.flush()

    if counts["review_cases"]:
        if _timeline(db, org.id, project.id, strategy.id,
                     event_type=EventType.research_review_cases_generated,
                     title="Review cases generated",
                     description="Execution-assumptions, turnover, and evidence-finalization cases.",
                     severity=Severity.info, event_time=_dt(-280), source_type="review_case"):
            counts["timeline_events"] += 1

    # --- Governance (guarded — optional) --------------------------------
    counts["governance"] += _seed_governance(db, strategy, version_objs, run_objs)

    # Persist all seeded artifacts BEFORE the best-effort cache refresh so a
    # refresh failure can never roll back the seed.
    db.commit()

    # --- Reliability snapshot cache (best effort, isolated, idempotent) -
    try:
        from app.models.reliability_snapshot import StrategyReliabilitySnapshot
        from app.services.reliability_snapshots import refresh_strategy_reliability_snapshot
        # Only build the cache once — the refresh service emits a timeline event
        # on every call, so guard on existence to keep the seed idempotent.
        existing_snap = (
            db.query(StrategyReliabilitySnapshot)
            .filter(StrategyReliabilitySnapshot.strategy_id == strategy.id.hex)
            .first()
        )
        if existing_snap is None:
            # The service stores str(strategy_id); pass .hex so the String(36) FK
            # to the 32-char-hex strategies.id primary key matches.
            refresh_strategy_reliability_snapshot(db, strategy.id.hex, force=False)
            db.commit()
    except Exception:
        db.rollback()

    # Report the actual resulting artifact set (accurate on create + refresh).
    counts = _final_counts(db, strategy.id)
    total_artifacts = sum(counts.values())
    return {
        "status": "created" if created else "refreshed",
        "strategy_id": str(strategy.id),
        "strategy_name": strategy.name,
        "strategy_slug": strategy.slug,
        "organization_id": str(org.id),
        "project_id": str(project.id),
        "counts": counts,
        "total_artifacts": total_artifacts,
        "summary": (
            f"{'Created' if created else 'Refreshed'} '{strategy.name}': "
            f"{counts['versions']} versions, {counts['runs']} runs, {counts['audits']} audits, "
            f"{counts['reports']} reports, {counts['alerts']} alerts, "
            f"{counts['review_cases']} review cases."
        ),
        "disclaimer": "Deterministic synthetic demo data — not real trading performance.",
    }


def _seed_governance(db, strategy, version_objs, run_objs) -> int:
    """Best-effort regression tests, config policy, and SLA — guarded."""
    n = 0
    sid = strategy.id

    # Regression tests + one run comparing the weakest vs latest backtest.
    try:
        from app.models.regression import StrategyRegressionTest, StrategyRegressionTestRun
        from app.services.regression_tests import (
            create_default_regression_tests, run_regression_tests,
        )
        if db.query(StrategyRegressionTest).filter_by(strategy_id=sid).first() is None:
            create_default_regression_tests(sid, db)
            n += 1
        # Idempotent: only run the suite once.
        if db.query(StrategyRegressionTestRun).filter_by(strategy_id=sid).first() is None:
            backtests = [r for tag, r in run_objs if tag in ("v1", "v2", "v3", "v4")]
            if len(backtests) >= 2:
                run_regression_tests(
                    strategy_id=sid, db=db, mode="selected_runs",
                    baseline_run_id=backtests[0].id, comparison_run_id=backtests[-1].id,
                    suite_label="v1 → v4 improvement",
                )
                n += 1
    except Exception:
        pass

    # Config policy + evaluations against the weak (v1) and strong (v4) configs.
    try:
        from app.models.config_policy import StrategyConfigPolicy, StrategyConfigPolicyEvaluation
        from app.models.strategy_config_snapshot import StrategyConfigSnapshot
        from app.services import config_policies as cp
        policy = db.query(StrategyConfigPolicy).filter_by(strategy_id=sid).first()
        if policy is None:
            policy = cp.create_default_config_policy(db, str(sid))
            n += 1
        # Idempotent: only evaluate when no evaluations exist yet.
        if db.query(StrategyConfigPolicyEvaluation).filter_by(strategy_id=sid).first() is None:
            snaps = (
                db.query(StrategyConfigSnapshot)
                .filter_by(strategy_id=sid)
                .order_by(StrategyConfigSnapshot.created_at)
                .all()
            )
            for snap in (snaps[:1] + snaps[-1:]) if len(snaps) >= 2 else snaps:
                try:
                    cp.evaluate_config_policy(db, strategy_id=str(sid), policy_id=str(policy.id),
                                              config_snapshot_id=str(snap.id))
                    n += 1
                except Exception:
                    pass
    except Exception:
        pass

    # Evidence SLA policy + evaluation.
    try:
        from app.models.evidence_sla import EvidenceSLAPolicy, EvidenceSLAEvaluation
        from app.services import evidence_sla as sla
        spolicy = db.query(EvidenceSLAPolicy).filter_by(strategy_id=sid).first()
        if spolicy is None:
            spolicy = sla.create_default_evidence_sla_policy(db, str(sid))
            n += 1
        if db.query(EvidenceSLAEvaluation).filter_by(strategy_id=sid).first() is None:
            sla.evaluate_evidence_sla_policy(db, strategy_id=str(sid), policy_id=str(spolicy.id))
            n += 1
    except Exception:
        pass

    return n
