"""Backtest Reality Score service (M93).

High-level Backtest Reality Score that WRAPS the existing M8/M13/M36 audit
(backtest_reality.py) and adds new integration checks including evidence
verification and shadow monitoring signals.

Language policy:
  Use: "logged", "observed", "noted", "not declared"
  Never: "fraud", "falsified", "better strategy", "should trade"
  Always include disclaimer.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.models.backtest_audit import BacktestAudit
from app.models.backtest_issue import BacktestIssue
from app.models.strategy import Strategy
from app.models.strategy_run import StrategyRun

# ---------------------------------------------------------------------------
# Disclaimer
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "Backtest Reality Check evaluates research assumptions and evidence quality. "
    "It is not trading advice."
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class BacktestRealityCheck:
    key: str
    title: str
    status: str  # pass | watch | fail | missing
    severity: str  # low | medium | high | critical
    explanation: str
    recommended_fix: str | None
    evidence_type: str  # assumptions | metrics | shadow | evidence | audit | oos | bias
    evidence_id: str | None = None


@dataclass
class BacktestRealityData:
    strategy_id: uuid.UUID
    run_id: uuid.UUID | None
    strategy_name: str
    backtest_reality_score: float  # 0-100
    verdict: str  # realistic | acceptable | review | weak | insufficient_data
    severity: str  # low | medium | high | critical
    primary_concern: str | None
    checks: list[BacktestRealityCheck]
    top_concerns: list[str]
    suggested_actions: list[str]
    generated_at: datetime
    disclaimer: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def get_latest_backtest_run(strategy_id: uuid.UUID, db: Session) -> StrategyRun | None:
    """Return the most recent backtest run for the given strategy, or None."""
    return (
        db.query(StrategyRun)
        .filter(
            StrategyRun.strategy_id == strategy_id,
            StrategyRun.run_type == "backtest",
        )
        .order_by(StrategyRun.created_at.desc())
        .first()
    )


def _verdict_from_score(score: float) -> str:
    if score >= 85:
        return "realistic"
    if score >= 70:
        return "acceptable"
    if score >= 50:
        return "review"
    if score >= 30:
        return "weak"
    return "insufficient_data"


def _severity_from_score(score: float) -> str:
    if score >= 70:
        return "low"
    if score >= 50:
        return "medium"
    if score >= 30:
        return "high"
    return "critical"


# ---------------------------------------------------------------------------
# Public: core compute function
# ---------------------------------------------------------------------------


def compute_backtest_reality_check(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    run_id: uuid.UUID | None = None,
) -> BacktestRealityData:
    """Compute the M93 Backtest Reality Score for a strategy.

    Wraps the existing M8/M13/M36 audit (BacktestAudit + BacktestIssue rows)
    and adds new integration checks from evidence verification and shadow
    monitoring services.

    Parameters
    ----------
    strategy_id:
        UUID of the strategy to evaluate.
    db:
        SQLAlchemy session.
    run_id:
        Optional specific run UUID. Must belong to this strategy.
        If None, the latest backtest run is used.

    Returns
    -------
    BacktestRealityData
        Dataclass with score, verdict, checks, concerns, actions, and disclaimer.
    """
    now = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Load strategy name
    # ------------------------------------------------------------------
    strategy = db.get(Strategy, strategy_id)
    strategy_name = strategy.name if strategy else str(strategy_id)

    # ------------------------------------------------------------------
    # Resolve backtest run
    # ------------------------------------------------------------------
    run: StrategyRun | None = None
    if run_id is not None:
        run = (
            db.query(StrategyRun)
            .filter(
                StrategyRun.id == run_id,
                StrategyRun.strategy_id == strategy_id,
            )
            .first()
        )
    else:
        run = get_latest_backtest_run(strategy_id, db)

    # No run at all -> insufficient data
    if run is None:
        return BacktestRealityData(
            strategy_id=strategy_id,
            run_id=None,
            strategy_name=strategy_name,
            backtest_reality_score=0.0,
            verdict="insufficient_data",
            severity="critical",
            primary_concern="No backtest run has been logged for this strategy.",
            checks=[
                BacktestRealityCheck(
                    key="no_backtest_run",
                    title="No Backtest Run Found",
                    status="missing",
                    severity="critical",
                    explanation="No backtest run has been logged for this strategy.",
                    recommended_fix="Log a backtest run to enable the Backtest Reality Score.",
                    evidence_type="audit",
                )
            ],
            top_concerns=["No backtest run has been logged for this strategy."],
            suggested_actions=["Log a backtest run to enable the Backtest Reality Score."],
            generated_at=now,
            disclaimer=DISCLAIMER,
        )

    # ------------------------------------------------------------------
    # Load existing BacktestAudit for the run (if any)
    # ------------------------------------------------------------------
    audit: BacktestAudit | None = (
        db.query(BacktestAudit)
        .filter(BacktestAudit.strategy_run_id == run.id)
        .order_by(BacktestAudit.created_at.desc())
        .first()
    )

    # Base score from audit trust_score, or 80 when no audit exists yet
    base_score: float = float(audit.trust_score) if audit is not None else 80.0

    # Score caps (collected, applied at the end with min())
    score_caps: list[float] = []

    checks: list[BacktestRealityCheck] = []

    # ------------------------------------------------------------------
    # Map existing BacktestIssue records to BacktestRealityCheck
    # ------------------------------------------------------------------
    if audit is not None:
        for issue in audit.issues:
            if issue.severity in ("critical", "high"):
                chk_status = "fail"
            elif issue.severity == "medium":
                chk_status = "watch"
            else:
                chk_status = "pass"
            checks.append(
                BacktestRealityCheck(
                    key=issue.issue_type,
                    title=issue.title,
                    status=chk_status,
                    severity=issue.severity,
                    explanation=issue.description,
                    recommended_fix=issue.suggested_check,
                    evidence_type="assumptions",
                    evidence_id=str(issue.id),
                )
            )

    # ------------------------------------------------------------------
    # M93 new checks
    # ------------------------------------------------------------------
    assumptions: dict = run.assumptions_json or {}
    params: dict = run.params_json or {}

    # CHECK: no_backtest_audit
    if audit is None:
        checks.append(
            BacktestRealityCheck(
                key="no_backtest_audit",
                title="No Backtest Audit Run",
                status="watch",
                severity="high",
                explanation=(
                    "No backtest audit has been run. Run Backtest Audit to assess "
                    "cost and fill realism."
                ),
                recommended_fix=(
                    "Submit a backtest audit via POST /api/strategy-runs/{run_id}/backtest-audit."
                ),
                evidence_type="audit",
            )
        )

    # CHECK: survivorship_bias_unaddressed
    if (
        "survivorship_bias" not in assumptions
        and "universe_construction" not in assumptions
    ):
        checks.append(
            BacktestRealityCheck(
                key="survivorship_bias_unaddressed",
                title="Survivorship Bias Not Declared",
                status="watch",
                severity="medium",
                explanation=(
                    "Survivorship bias assumption not declared. Add survivorship_bias "
                    "key to run assumptions."
                ),
                recommended_fix=(
                    "Add survivorship_bias (e.g. true/false) or universe_construction "
                    "to assumptions_json to document universe inclusion rules."
                ),
                evidence_type="bias",
            )
        )

    # CHECK: lookahead_bias_unaddressed
    if assumptions and (
        "lookahead_control" not in assumptions
        and "data_snooping" not in assumptions
    ):
        checks.append(
            BacktestRealityCheck(
                key="lookahead_bias_unaddressed",
                title="Lookahead Bias Control Not Declared",
                status="watch",
                severity="medium",
                explanation="Lookahead bias control not declared.",
                recommended_fix=(
                    "Add lookahead_control or data_snooping key to assumptions_json "
                    "to document how look-ahead bias is prevented."
                ),
                evidence_type="bias",
            )
        )

    # CHECK: no_out_of_sample_marker
    if params and (
        "oos_start" not in params
        and "out_of_sample_start" not in params
        and "test_start" not in params
    ):
        checks.append(
            BacktestRealityCheck(
                key="no_out_of_sample_marker",
                title="No Out-of-Sample Split Marker Found",
                status="watch",
                severity="medium",
                explanation="No out-of-sample split marker found.",
                recommended_fix=(
                    "Add oos_start, out_of_sample_start, or test_start to params_json "
                    "to document the train/test split boundary."
                ),
                evidence_type="oos",
            )
        )

    # CHECK: only_one_run
    total_backtest_count: int = (
        db.query(StrategyRun)
        .filter(
            StrategyRun.strategy_id == strategy_id,
            StrategyRun.run_type == "backtest",
        )
        .count()
    )
    if total_backtest_count == 1:
        checks.append(
            BacktestRealityCheck(
                key="only_one_run",
                title="Only One Backtest Run Logged",
                status="watch",
                severity="medium",
                explanation=(
                    "Only one backtest run logged. Multiple runs improve confidence."
                ),
                recommended_fix=(
                    "Log additional backtest runs with different parameter sets or "
                    "time periods to increase confidence in the results."
                ),
                evidence_type="metrics",
            )
        )

    # CHECK: no_paper_or_shadow_run
    paper_run_exists: bool = (
        db.query(StrategyRun)
        .filter(
            StrategyRun.strategy_id == strategy_id,
            StrategyRun.run_type.in_(["paper", "live", "shadow"]),
        )
        .first()
        is not None
    )
    shadow_check_already_added = False
    if not paper_run_exists:
        shadow_check_already_added = True
        checks.append(
            BacktestRealityCheck(
                key="no_paper_or_shadow_run",
                title="No Paper or Shadow Run Logged",
                status="watch",
                severity="medium",
                explanation=(
                    "No paper or shadow run logged. Shadow monitoring not enabled."
                ),
                recommended_fix=(
                    "Log a paper or shadow run to enable drift comparison via "
                    "shadow monitoring."
                ),
                evidence_type="shadow",
            )
        )

    # ------------------------------------------------------------------
    # Evidence Verification integration
    # ------------------------------------------------------------------
    try:
        from app.services.evidence_verification import verify_strategy_evidence

        ev_data = verify_strategy_evidence(strategy_id, db)

        if ev_data.verdict == "failed":
            checks.append(
                BacktestRealityCheck(
                    key="evidence_verification_failed",
                    title="Evidence Verification Failed",
                    status="fail",
                    severity="high",
                    explanation=(
                        f"Evidence verification returned verdict 'failed' "
                        f"(score: {ev_data.verification_score:.1f}/100). "
                        "Critical evidence chain issues were detected."
                    ),
                    recommended_fix=(
                        "Review evidence verification findings and resolve all "
                        "failed checks before drawing conclusions from this run."
                    ),
                    evidence_type="evidence",
                )
            )
            score_caps.append(60.0)

        elif ev_data.verdict == "warning":
            checks.append(
                BacktestRealityCheck(
                    key="evidence_verification_warning",
                    title="Evidence Verification Warning",
                    status="watch",
                    severity="medium",
                    explanation=(
                        f"Evidence verification returned verdict 'warning' "
                        f"(score: {ev_data.verification_score:.1f}/100). "
                        "Some evidence chain issues were noted."
                    ),
                    recommended_fix=(
                        "Review evidence verification warnings and resolve link "
                        "inconsistencies to improve evidence chain integrity."
                    ),
                    evidence_type="evidence",
                )
            )
            score_caps.append(70.0)

        if ev_data.time_consistency_warnings:
            checks.append(
                BacktestRealityCheck(
                    key="evidence_time_inconsistency",
                    title="Evidence Time-Consistency Issue",
                    status="fail",
                    severity="high",
                    explanation=(
                        f"{len(ev_data.time_consistency_warnings)} time-consistency "
                        f"issue(s) detected in evidence chain: "
                        f"{ev_data.time_consistency_warnings[0]}"
                    ),
                    recommended_fix=(
                        "Confirm that all linked snapshots were recorded before or "
                        "during the run. Re-link with correctly dated snapshots if needed."
                    ),
                    evidence_type="evidence",
                )
            )
            score_caps.append(65.0)

    except Exception:
        pass  # Skip if evidence verification fails

    # ------------------------------------------------------------------
    # Shadow Monitor integration
    # ------------------------------------------------------------------
    try:
        from app.services.shadow_monitor import compare_backtest_to_paper

        shadow_data = compare_backtest_to_paper(strategy_id, db)

        if shadow_data.verdict == "drifted" and shadow_data.severity in ("high", "critical"):
            checks.append(
                BacktestRealityCheck(
                    key="shadow_high_drift",
                    title="High Drift vs Shadow/Paper Run",
                    status="fail",
                    severity="high",
                    explanation=(
                        f"Shadow monitoring found significant drift "
                        f"(verdict: drifted, severity: {shadow_data.severity}, "
                        f"drift score: {shadow_data.drift_score:.1f}/100). "
                        f"{shadow_data.primary_concern or ''}"
                    ).strip(),
                    recommended_fix=(
                        "Investigate logged drift between backtest and paper/live runs. "
                        "Review parameter changes and execution assumptions."
                    ),
                    evidence_type="shadow",
                )
            )
            score_caps.append(55.0)

        elif shadow_data.verdict == "watch":
            checks.append(
                BacktestRealityCheck(
                    key="shadow_watch_drift",
                    title="Elevated Drift vs Shadow/Paper Run",
                    status="watch",
                    severity="medium",
                    explanation=(
                        f"Shadow monitoring noted elevated metric drift "
                        f"(verdict: watch, drift score: "
                        f"{shadow_data.drift_score:.1f}/100). "
                        f"{shadow_data.primary_concern or ''}"
                    ).strip(),
                    recommended_fix=(
                        "Monitor elevated logged change in key metrics. "
                        "Consider logging additional comparison runs."
                    ),
                    evidence_type="shadow",
                )
            )

        elif shadow_data.verdict == "insufficient_data" and not shadow_check_already_added:
            checks.append(
                BacktestRealityCheck(
                    key="no_shadow_run",
                    title="No Shadow/Paper Run Available",
                    status="watch",
                    severity="medium",
                    explanation=(
                        "Shadow monitoring could not run: no paper or shadow run "
                        "found for this strategy."
                    ),
                    recommended_fix=(
                        "Upload a paper or live-like run with metrics_json populated "
                        "to enable drift comparison."
                    ),
                    evidence_type="shadow",
                )
            )

    except Exception:
        pass  # Skip if shadow monitor fails

    # ------------------------------------------------------------------
    # Apply score caps (ordered by priority, use min())
    # ------------------------------------------------------------------
    # Check existing issues for specific cap conditions
    issue_types_present: set[str] = {c.key for c in checks}

    if (
        "missing_transaction_cost" in issue_types_present
        or "zero_transaction_cost" in issue_types_present
    ) and (
        "high_turnover" in issue_types_present
        or "high_turnover_low_cost" in issue_types_present
    ):
        score_caps.append(50.0)

    if run.dataset_snapshot_id is None and run.universe_snapshot_id is None:
        score_caps.append(65.0)

    # Apply all caps
    final_score: float = base_score
    if score_caps:
        final_score = min(final_score, min(score_caps))
    final_score = max(0.0, round(final_score, 1))

    # ------------------------------------------------------------------
    # Verdict and severity
    # ------------------------------------------------------------------
    verdict = _verdict_from_score(final_score)
    severity = _severity_from_score(final_score)

    # ------------------------------------------------------------------
    # Primary concern: first fail/high explanation, else first watch
    # ------------------------------------------------------------------
    primary_concern: str | None = None
    for chk in checks:
        if chk.status == "fail" and chk.severity in ("high", "critical"):
            primary_concern = chk.explanation[:100]
            break
    if primary_concern is None:
        for chk in checks:
            if chk.status == "watch":
                primary_concern = chk.explanation[:100]
                break

    # ------------------------------------------------------------------
    # Top concerns and suggested actions
    # ------------------------------------------------------------------
    fail_and_watch = [c for c in checks if c.status in ("fail", "watch")]
    top_concerns: list[str] = [c.explanation for c in fail_and_watch[:5]]

    seen_fixes: set[str] = set()
    suggested_actions: list[str] = []
    for chk in fail_and_watch:
        if chk.recommended_fix and chk.recommended_fix not in seen_fixes:
            seen_fixes.add(chk.recommended_fix)
            suggested_actions.append(chk.recommended_fix)
            if len(suggested_actions) >= 5:
                break

    return BacktestRealityData(
        strategy_id=strategy_id,
        run_id=run.id,
        strategy_name=strategy_name,
        backtest_reality_score=final_score,
        verdict=verdict,
        severity=severity,
        primary_concern=primary_concern,
        checks=checks,
        top_concerns=top_concerns,
        suggested_actions=suggested_actions,
        generated_at=now,
        disclaimer=DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Public: report generation
# ---------------------------------------------------------------------------


def generate_backtest_reality_report(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    run_id: uuid.UUID | None = None,
    format: str = "json",
) -> str:
    """Generate a formatted Backtest Reality Report.

    Parameters
    ----------
    strategy_id:
        UUID of the strategy to evaluate.
    db:
        SQLAlchemy session.
    run_id:
        Optional specific run UUID to evaluate.
    format:
        "json" (default) or "markdown".

    Returns
    -------
    str
        Report as a JSON or Markdown string.
    """
    data = compute_backtest_reality_check(strategy_id, db, run_id=run_id)

    if format == "markdown":
        lines: list[str] = [
            f"# Backtest Reality Report: {data.strategy_name}",
            "",
            f"**Strategy ID:** {data.strategy_id}  ",
            f"**Run ID:** {data.run_id or 'N/A'}  ",
            f"**Generated:** {data.generated_at.isoformat()}  ",
            f"**Score:** {data.backtest_reality_score:.1f} / 100  ",
            f"**Verdict:** {data.verdict.upper()}  ",
            f"**Severity:** {data.severity}  ",
            "",
            "---",
            "",
            "## Checks",
            "",
            "| # | Key | Title | Status | Severity | Evidence Type | Explanation |",
            "|---|-----|-------|--------|----------|---------------|-------------|",
        ]
        for i, chk in enumerate(data.checks, 1):
            expl = chk.explanation[:80] + "..." if len(chk.explanation) > 80 else chk.explanation
            lines.append(
                f"| {i} | `{chk.key}` | {chk.title} | **{chk.status}** | "
                f"{chk.severity} | {chk.evidence_type} | {expl} |"
            )

        if data.top_concerns:
            lines += [
                "",
                "## Top Concerns",
                "",
            ]
            for concern in data.top_concerns:
                lines.append(f"- {concern}")

        if data.suggested_actions:
            lines += [
                "",
                "## Suggested Actions",
                "",
            ]
            for i, action in enumerate(data.suggested_actions, 1):
                lines.append(f"{i}. {action}")

        lines += [
            "",
            "---",
            "",
            f"*{data.disclaimer}*",
        ]
        return "\n".join(lines)

    # Default: JSON
    payload = {
        "strategy_id": str(data.strategy_id),
        "run_id": str(data.run_id) if data.run_id else None,
        "strategy_name": data.strategy_name,
        "backtest_reality_score": data.backtest_reality_score,
        "verdict": data.verdict,
        "severity": data.severity,
        "primary_concern": data.primary_concern,
        "checks": [
            {
                "key": c.key,
                "title": c.title,
                "status": c.status,
                "severity": c.severity,
                "explanation": c.explanation,
                "recommended_fix": c.recommended_fix,
                "evidence_type": c.evidence_type,
                "evidence_id": c.evidence_id,
            }
            for c in data.checks
        ],
        "top_concerns": data.top_concerns,
        "suggested_actions": data.suggested_actions,
        "generated_at": data.generated_at.isoformat(),
        "disclaimer": data.disclaimer,
    }
    return json.dumps(payload, indent=2, default=str)
