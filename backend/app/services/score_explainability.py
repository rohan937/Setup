"""Score Explainability service (M99).

A deterministic, READ-ONLY layer that explains *why* each QuantFidelity score
landed where it did. It reuses the already-computed outputs of the reliability,
backtest-trust, backtest-reality, evidence-verification, readiness, and
shadow-monitor services and decomposes them into per-driver "scorecards".

Design notes
------------
* READ-ONLY: this module never calls db.add / db.commit / db.flush. It only
  issues db.query reads and calls other read-only services.
* Deterministic: no AI, no live market data, no randomness.
* Where a score is *exactly* reconstructible from its inputs (reliability), the
  contributions are reproduced exactly. Where the underlying scoring uses caps
  or non-additive logic (reality / verification / readiness / shadow), items are
  labelled as "score drivers" rather than exact reconstructions.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.backtest_audit import BacktestAudit
from app.models.strategy import Strategy
from app.models.strategy_reliability_score import StrategyReliabilityScore
from app.models.strategy_run import StrategyRun
from app.services.strategy_reliability import WEIGHTS


DISCLAIMER = (
    "Score explanations describe research evidence quality. "
    "They are not trading advice."
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ScoreDriverItem:
    key: str
    label: str
    points: float
    direction: str  # positive | negative | neutral
    category: str
    evidence_type: str | None
    evidence_id: str | None
    explanation: str
    recommended_action: str | None


@dataclass
class ScoreCard:
    score_key: str
    label: str
    score: float | None
    max_score: float
    verdict: str
    primary_positive: str | None
    primary_drag: str | None
    items: list[ScoreDriverItem]
    formula_note: str
    generated_at: datetime


@dataclass
class StrategyScoreExplanation:
    strategy_id: uuid.UUID
    strategy_name: str
    overall_summary: str
    scorecards: list[ScoreCard]
    disclaimer: str
    generated_at: datetime


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Human-readable component names used in reliability driver labels.
_COMPONENT_DISPLAY: dict[str, str] = {
    "backtest_trust_score": "Backtest trust",
    "data_evidence_score": "Data evidence",
    "signal_evidence_score": "Signal evidence",
    "universe_evidence_score": "Universe evidence",
    "config_evidence_score": "Config evidence",
    "strategy_activity_score": "Strategy activity",
    "alert_penalty_score": "Alert penalty",
}

# Severity -> penalty magnitude (used for backtest-trust issues, expressed as
# negative driver points).
_TRUST_ISSUE_PENALTY: dict[str, float] = {
    "critical": 25.0,
    "high": 15.0,
    "medium": 8.0,
    "low": 3.0,
}

# Severity -> negative driver points for status-based checks (reality /
# verification / shadow).
_CHECK_SEVERITY_POINTS: dict[str, float] = {
    "critical": -25.0,
    "high": -15.0,
    "medium": -8.0,
    "low": -3.0,
    "info": -1.0,
}


def _quality_word(value: float) -> str:
    """A one-word quality descriptor for a 0-100 component value."""
    if value >= 85:
        return "strong"
    if value >= 70:
        return "good"
    if value >= 55:
        return "fair"
    return "weak"


def _empty_card(
    score_key: str,
    label: str,
    item_key: str,
    item_label: str,
    item_explanation: str,
    formula_note: str,
    recommended_action: str | None = None,
) -> ScoreCard:
    """Build a standard insufficient_data scorecard with a single neutral item."""
    return ScoreCard(
        score_key=score_key,
        label=label,
        score=None,
        max_score=100.0,
        verdict="insufficient_data",
        primary_positive=None,
        primary_drag=item_label,
        items=[
            ScoreDriverItem(
                key=item_key,
                label=item_label,
                points=0.0,
                direction="neutral",
                category="coverage",
                evidence_type=None,
                evidence_id=None,
                explanation=item_explanation,
                recommended_action=recommended_action,
            )
        ],
        formula_note=formula_note,
        generated_at=_utcnow(),
    )


# ---------------------------------------------------------------------------
# Reliability score explanation (EXACT reconstruction)
# ---------------------------------------------------------------------------


def explain_reliability_score(
    strategy_id: uuid.UUID,
    db: Session,
    score_id: uuid.UUID | None = None,
) -> ScoreCard:
    """Explain the latest (or a specific) StrategyReliabilityScore.

    Reliability is a weighted average of available component scores, so each
    component's contribution is *exactly* reconstructible:
        contribution_i = round(weight_i * component_i / available_weight_sum, 1)
    """
    now = _utcnow()

    if score_id is not None:
        score = (
            db.query(StrategyReliabilityScore)
            .filter(
                StrategyReliabilityScore.id == score_id,
                StrategyReliabilityScore.strategy_id == strategy_id,
            )
            .first()
        )
    else:
        score = (
            db.query(StrategyReliabilityScore)
            .filter(StrategyReliabilityScore.strategy_id == strategy_id)
            .order_by(StrategyReliabilityScore.generated_at.desc())
            .first()
        )

    if score is None:
        return _empty_card(
            score_key="reliability",
            label="Reliability Score",
            item_key="no_reliability_score",
            item_label="No reliability score computed yet",
            item_explanation=(
                "No reliability score has been computed for this strategy yet."
            ),
            formula_note=(
                "Reliability is a weighted average of component scores. Compute one "
                "via POST /api/strategies/{id}/reliability-score to enable this "
                "explanation."
            ),
            recommended_action="Compute a reliability score for this strategy.",
        )

    # --- Component contributions (exact reconstruction) ---
    components: dict[str, float | None] = {
        key: getattr(score, key, None) for key in WEIGHTS
    }
    available_weight_sum = sum(
        WEIGHTS[k] for k, v in components.items() if v is not None
    )

    items: list[ScoreDriverItem] = []
    positive_items: list[ScoreDriverItem] = []
    negative_items: list[ScoreDriverItem] = []

    for key, value in components.items():
        if value is None:
            continue
        weight = WEIGHTS[key]
        if available_weight_sum > 0:
            contribution = round(weight * value / available_weight_sum, 1)
        else:
            contribution = 0.0
        display = _COMPONENT_DISPLAY.get(key, key)
        is_positive = value >= 70
        direction = "positive" if is_positive else "negative"
        quality = "good" if is_positive else "weak"
        label = f"{display} {quality}"
        explanation = (
            f"{display} component is {value:.1f}/100 (weight {weight:.2f}). "
            f"It contributes {contribution:.1f} points to the overall score "
            f"(weight x component / total available weight {available_weight_sum:.2f})."
        )
        item = ScoreDriverItem(
            key=key,
            label=label,
            points=contribution,
            direction=direction,
            category=key,
            evidence_type=None,
            evidence_id=None,
            explanation=explanation,
            recommended_action=None,
        )
        items.append(item)
        if is_positive:
            positive_items.append(item)
        else:
            negative_items.append(item)

    # --- Negative driver items from missing evidence ---
    suggested_checks: list[str] = list(score.suggested_checks_json or [])
    missing_evidence: list[str] = list(score.missing_evidence_json or [])

    def _suggested_for(missing: str) -> str | None:
        """Best-effort match of a missing-evidence string to a suggested check."""
        m = missing.lower()
        for check in suggested_checks:
            c = check.lower()
            if "dataset" in m and "dataset" in c:
                return check
            if "backtest audit" in m and "backtest" in c:
                return check
            if "universe" in m and "universe" in c:
                return check
            if "signal" in m and "signal" in c:
                return check
            if "report" in m and "report" in c:
                return check
        return None

    for idx, missing in enumerate(missing_evidence):
        action = _suggested_for(missing)
        item = ScoreDriverItem(
            key=f"missing_evidence_{idx}",
            label="Missing evidence",
            points=0.0,
            direction="negative",
            category="missing_evidence",
            evidence_type=None,
            evidence_id=None,
            explanation=missing,
            recommended_action=action,
        )
        items.append(item)
        negative_items.append(item)

    # --- report coverage gap (component is part of suggested checks, not WEIGHTS) ---
    if score.report_coverage_score is None:
        item = ScoreDriverItem(
            key="report_coverage_missing",
            label="No reliability report generated",
            points=0.0,
            direction="negative",
            category="report_coverage",
            evidence_type=None,
            evidence_id=None,
            explanation=(
                "No reliability report has been generated yet, so report coverage "
                "could not be scored."
            ),
            recommended_action="Generate a reliability report for this strategy.",
        )
        items.append(item)
        negative_items.append(item)

    # --- run-count signal from suggested checks ---
    for check in suggested_checks:
        c = check.lower()
        if "one more" in c and "run" in c:
            item = ScoreDriverItem(
                key="only_one_run",
                label="Only one run exists",
                points=0.0,
                direction="negative",
                category="strategy_activity",
                evidence_type=None,
                evidence_id=None,
                explanation=(
                    "Only one strategy run has been logged. Additional runs "
                    "strengthen the evidence base."
                ),
                recommended_action=check,
            )
            items.append(item)
            negative_items.append(item)
            break

    # --- primary positive / drag ---
    primary_positive: str | None = None
    if positive_items:
        primary_positive = max(positive_items, key=lambda i: i.points).label

    primary_drag: str | None = None
    # Prefer a missing-evidence drag; otherwise lowest-contribution component.
    missing_drag = next(
        (i for i in negative_items if i.category == "missing_evidence"), None
    )
    if missing_drag is not None:
        primary_drag = missing_drag.explanation[:80]
    else:
        component_negatives = [
            i for i in negative_items if i.category in WEIGHTS
        ]
        if component_negatives:
            primary_drag = min(component_negatives, key=lambda i: i.points).label
        elif negative_items:
            primary_drag = negative_items[0].label

    formula_note = (
        "Reliability is a weighted average of component scores. Contributions are "
        "exact: each component contributes (weight x component) / total available "
        "weight. This scorecard reconstructs the published score exactly."
    )

    return ScoreCard(
        score_key="reliability",
        label="Reliability Score",
        score=score.overall_score,
        max_score=100.0,
        verdict=score.status,
        primary_positive=primary_positive,
        primary_drag=primary_drag,
        items=items,
        formula_note=formula_note,
        generated_at=now,
    )


# ---------------------------------------------------------------------------
# Backtest trust explanation
# ---------------------------------------------------------------------------


def explain_backtest_trust(
    strategy_id: uuid.UUID,
    db: Session,
    run_id: uuid.UUID | None = None,
) -> ScoreCard:
    """Explain the BacktestAudit trust score for the latest (or given) backtest run."""
    now = _utcnow()

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
        run = (
            db.query(StrategyRun)
            .filter(
                StrategyRun.strategy_id == strategy_id,
                StrategyRun.run_type == "backtest",
            )
            .order_by(StrategyRun.created_at.desc())
            .first()
        )

    audit: BacktestAudit | None = None
    if run is not None:
        audit = (
            db.query(BacktestAudit)
            .filter(BacktestAudit.strategy_run_id == run.id)
            .order_by(BacktestAudit.created_at.desc())
            .first()
        )

    if audit is None:
        return _empty_card(
            score_key="backtest_trust",
            label="Backtest Trust",
            item_key="no_backtest_audit",
            item_label="No backtest audit run",
            item_explanation=(
                "No backtest audit has been run for this strategy, so trust cannot "
                "be explained."
            ),
            formula_note=(
                "Backtest trust starts at 100; each detected issue deducts a penalty "
                "by severity. Run a backtest audit to enable this explanation."
            ),
            recommended_action="Run a backtest audit on the latest backtest run.",
        )

    items: list[ScoreDriverItem] = []
    positive_items: list[ScoreDriverItem] = []
    negative_items: list[ScoreDriverItem] = []

    # --- Positive drivers: subscores >= 80 ---
    subscores = {
        "lookahead_risk_score": "Lookahead risk control",
        "cost_realism_score": "Cost realism",
        "fill_realism_score": "Fill realism",
        "liquidity_realism_score": "Liquidity realism",
        "borrow_realism_score": "Borrow realism",
        "data_quality_score": "Data quality",
    }
    for attr, display in subscores.items():
        value = getattr(audit, attr, None)
        if value is None:
            continue
        if value >= 80:
            item = ScoreDriverItem(
                key=attr,
                label=f"{display} strong",
                points=float(value),
                direction="positive",
                category=attr,
                evidence_type="audit",
                evidence_id=str(audit.id),
                explanation=(
                    f"{display} subscore is {value}/100, indicating this dimension "
                    "is realistically modelled."
                ),
                recommended_action=None,
            )
            items.append(item)
            positive_items.append(item)

    # --- Negative drivers: each BacktestIssue ---
    for issue in audit.issues:
        penalty = _TRUST_ISSUE_PENALTY.get(issue.severity, 3.0)
        item = ScoreDriverItem(
            key=issue.issue_type,
            label=issue.title,
            points=-penalty,
            direction="negative",
            category=issue.issue_type,
            evidence_type="backtest_issue",
            evidence_id=str(issue.id),
            explanation=issue.description,
            recommended_action=issue.suggested_check,
        )
        items.append(item)
        negative_items.append(item)

    primary_positive = (
        max(positive_items, key=lambda i: i.points).label if positive_items else None
    )
    primary_drag = (
        min(negative_items, key=lambda i: i.points).label if negative_items else None
    )

    return ScoreCard(
        score_key="backtest_trust",
        label="Backtest Trust",
        score=float(audit.trust_score),
        max_score=100.0,
        verdict=audit.overall_status,
        primary_positive=primary_positive,
        primary_drag=primary_drag,
        items=items,
        formula_note=(
            "Backtest trust starts at 100; each detected issue deducts a penalty by "
            "severity. These are score drivers (the displayed points reflect issue "
            "penalties)."
        ),
        generated_at=now,
    )


# ---------------------------------------------------------------------------
# Backtest reality explanation
# ---------------------------------------------------------------------------


def explain_backtest_reality(
    strategy_id: uuid.UUID,
    db: Session,
    run_id: uuid.UUID | None = None,
) -> ScoreCard:
    """Explain the Backtest Reality Score (wraps compute_backtest_reality_check)."""
    from app.services.backtest_reality_score import compute_backtest_reality_check

    now = _utcnow()
    data = compute_backtest_reality_check(strategy_id, db, run_id=run_id)

    items: list[ScoreDriverItem] = []
    positive_items: list[ScoreDriverItem] = []
    negative_items: list[ScoreDriverItem] = []

    for chk in data.checks:
        if chk.status == "pass":
            item = ScoreDriverItem(
                key=chk.key,
                label=chk.title,
                points=2.0,
                direction="positive",
                category=chk.evidence_type,
                evidence_type=chk.evidence_type,
                evidence_id=chk.evidence_id,
                explanation=chk.explanation,
                recommended_action=chk.recommended_fix,
            )
            positive_items.append(item)
        else:  # watch | fail | missing
            points = _CHECK_SEVERITY_POINTS.get(chk.severity, -3.0)
            item = ScoreDriverItem(
                key=chk.key,
                label=chk.title,
                points=points,
                direction="negative",
                category=chk.evidence_type,
                evidence_type=chk.evidence_type,
                evidence_id=chk.evidence_id,
                explanation=chk.explanation,
                recommended_action=chk.recommended_fix,
            )
            negative_items.append(item)
        items.append(item)

    primary_positive = (
        max(positive_items, key=lambda i: i.points).label if positive_items else None
    )

    return ScoreCard(
        score_key="backtest_reality",
        label="Backtest Reality",
        score=data.backtest_reality_score,
        max_score=100.0,
        verdict=data.verdict,
        primary_positive=primary_positive,
        primary_drag=data.primary_concern,
        items=items,
        formula_note=(
            "Backtest reality wraps the audit trust score and applies caps for "
            "evidence/shadow issues. Items are score drivers, not an exact "
            "reconstruction, because the caps are non-additive."
        ),
        generated_at=now,
    )


# ---------------------------------------------------------------------------
# Evidence verification explanation
# ---------------------------------------------------------------------------


def explain_evidence_verification(
    strategy_id: uuid.UUID,
    db: Session,
) -> ScoreCard:
    """Explain the evidence verification score (wraps verify_strategy_evidence)."""
    from app.services.evidence_verification import verify_strategy_evidence

    now = _utcnow()
    data = verify_strategy_evidence(strategy_id, db)

    items: list[ScoreDriverItem] = []
    positive_items: list[ScoreDriverItem] = []
    negative_items: list[ScoreDriverItem] = []

    for chk in data.checks:
        if chk.status == "pass":
            item = ScoreDriverItem(
                key=chk.key,
                label=chk.title,
                points=2.0,
                direction="positive",
                category=chk.evidence_type,
                evidence_type=chk.evidence_type,
                evidence_id=chk.evidence_id,
                explanation=chk.explanation,
                recommended_action=chk.recommended_fix,
            )
            positive_items.append(item)
        else:  # warning | fail | missing
            points = _CHECK_SEVERITY_POINTS.get(chk.severity, -3.0)
            item = ScoreDriverItem(
                key=chk.key,
                label=chk.title,
                points=points,
                direction="negative",
                category=chk.evidence_type,
                evidence_type=chk.evidence_type,
                evidence_id=chk.evidence_id,
                explanation=chk.explanation,
                recommended_action=chk.recommended_fix,
            )
            negative_items.append(item)
        items.append(item)

    # --- warnings as additional negative drivers ---
    def _add_warning(prefix: str, warnings: list[str], category: str) -> None:
        for idx, warning in enumerate(warnings):
            item = ScoreDriverItem(
                key=f"{prefix}_{idx}",
                label=prefix.replace("_", " ").title(),
                points=-3.0,
                direction="negative",
                category=category,
                evidence_type=None,
                evidence_id=None,
                explanation=warning,
                recommended_action=None,
            )
            items.append(item)
            negative_items.append(item)

    _add_warning(
        "time_consistency_warning", data.time_consistency_warnings, "time_consistency"
    )
    _add_warning(
        "link_consistency_warning", data.link_consistency_warnings, "link_consistency"
    )
    _add_warning("tamper_warning", data.tamper_warnings, "tamper")

    primary_positive = (
        max(positive_items, key=lambda i: i.points).label if positive_items else None
    )
    primary_drag = (
        min(negative_items, key=lambda i: i.points).explanation[:80]
        if negative_items
        else None
    )

    return ScoreCard(
        score_key="evidence_verification",
        label="Evidence Verification",
        score=data.verification_score,
        max_score=100.0,
        verdict=data.verdict,
        primary_positive=primary_positive,
        primary_drag=primary_drag,
        items=items,
        formula_note=(
            "Evidence verification starts at 100 and deducts by check severity, then "
            f"applies chain caps (chain status: {data.chain_status}; "
            f"root hash: {data.root_hash or 'N/A'}). Items are score drivers, not an "
            "exact reconstruction."
        ),
        generated_at=now,
    )


# ---------------------------------------------------------------------------
# Readiness explanation
# ---------------------------------------------------------------------------


def explain_readiness_score(
    strategy_id: uuid.UUID,
    db: Session,
    target_stage: str | None = None,
) -> ScoreCard:
    """Explain the strategy readiness score (wraps get_current_readiness)."""
    from app.services.readiness_simulator import get_current_readiness

    now = _utcnow()
    data = get_current_readiness(strategy_id, db, target_stage)

    items: list[ScoreDriverItem] = []
    positive_items: list[ScoreDriverItem] = []
    negative_items: list[ScoreDriverItem] = []

    # --- Negative items from current blockers ---
    for idx, blocker in enumerate(data.current_blockers):
        item = ScoreDriverItem(
            key=f"blocker_{idx}",
            label="Readiness blocker",
            points=-10.0,
            direction="negative",
            category="blocker",
            evidence_type=None,
            evidence_id=None,
            explanation=blocker,
            recommended_action=None,
        )
        items.append(item)
        negative_items.append(item)

    # --- Positive item if score high ---
    score = data.current_readiness_score
    if score is not None and score >= 80:
        item = ScoreDriverItem(
            key="readiness_strong",
            label="Readiness on track",
            points=float(score),
            direction="positive",
            category="readiness",
            evidence_type=None,
            evidence_id=None,
            explanation=(
                f"Readiness score is {score:.1f}/100 for target stage "
                f"'{data.target_stage}', with no remaining hard blockers expected."
            ),
            recommended_action=None,
        )
        items.append(item)
        positive_items.append(item)

    # --- Recommended improvement items ---
    for action in data.recommended_actions:
        item = ScoreDriverItem(
            key=action.key,
            label=action.title,
            points=float(action.impact_points),
            direction="positive",
            category=action.category,
            evidence_type=None,
            evidence_id=action.cta_target,
            explanation=action.why_it_matters,
            recommended_action=action.cta_label,
        )
        items.append(item)

    primary_positive = (
        max(positive_items, key=lambda i: i.points).label if positive_items else None
    )
    primary_drag = (
        data.current_blockers[0][:80] if data.current_blockers else None
    )

    return ScoreCard(
        score_key="readiness",
        label="Promotion Readiness",
        score=data.current_readiness_score,
        max_score=100.0,
        verdict=data.current_verdict,
        primary_positive=primary_positive,
        primary_drag=primary_drag,
        items=items,
        formula_note=(
            "Readiness is a weighted multi-dimensional governance score for target "
            f"stage '{data.target_stage}'. Negative items are current blockers; "
            "positive items list recommended improvements with their projected "
            "impact points. Items are drivers and projected improvements, not an "
            "exact reconstruction."
        ),
        generated_at=now,
    )


# ---------------------------------------------------------------------------
# Shadow monitor explanation
# ---------------------------------------------------------------------------


def explain_shadow_monitor(
    strategy_id: uuid.UUID,
    db: Session,
) -> ScoreCard:
    """Explain the shadow-monitor drift score (wraps compare_backtest_to_paper)."""
    from app.services.shadow_monitor import compare_backtest_to_paper

    now = _utcnow()
    data = compare_backtest_to_paper(strategy_id, db)

    if data.verdict == "insufficient_data" or data.drift_score is None:
        card = _empty_card(
            score_key="shadow_monitor",
            label="Shadow Drift",
            item_key="no_shadow_run",
            item_label="No paper/shadow run logged",
            item_explanation=(
                data.primary_concern
                or "No paper or shadow run is available to compare against the "
                "backtest baseline."
            ),
            formula_note=(
                "Shadow drift compares backtest baseline metrics against a paper/live "
                "run. A paper or shadow run is required to compute drift."
            ),
            recommended_action="Upload a paper run",
        )
        return card

    items: list[ScoreDriverItem] = []
    positive_items: list[ScoreDriverItem] = []
    negative_items: list[ScoreDriverItem] = []

    for metric in data.metrics:
        if metric.status in ("fail", "watch"):
            points = _CHECK_SEVERITY_POINTS.get(metric.severity, -3.0)
            item = ScoreDriverItem(
                key=metric.key,
                label=f"{metric.label} drifted",
                points=points,
                direction="negative",
                category="drift",
                evidence_type="metric",
                evidence_id=None,
                explanation=metric.explanation,
                recommended_action=None,
            )
            negative_items.append(item)
            items.append(item)
        elif metric.status == "pass":
            item = ScoreDriverItem(
                key=metric.key,
                label=f"{metric.label} stable",
                points=2.0,
                direction="positive",
                category="drift",
                evidence_type="metric",
                evidence_id=None,
                explanation=metric.explanation,
                recommended_action=None,
            )
            positive_items.append(item)
            items.append(item)
        else:  # missing
            item = ScoreDriverItem(
                key=metric.key,
                label=f"{metric.label} not logged",
                points=0.0,
                direction="neutral",
                category="drift",
                evidence_type="metric",
                evidence_id=None,
                explanation=metric.explanation,
                recommended_action=None,
            )
            items.append(item)

    primary_positive = (
        max(positive_items, key=lambda i: i.points).label if positive_items else None
    )

    return ScoreCard(
        score_key="shadow_monitor",
        label="Shadow Drift",
        score=data.drift_score,
        max_score=100.0,
        verdict=data.verdict,
        primary_positive=primary_positive,
        primary_drag=data.primary_concern,
        items=items,
        formula_note=(
            "Shadow drift scores how far paper/live metrics diverge from the backtest "
            "baseline (higher means more drift). Drifted metrics are negative drivers; "
            "stable metrics are positive. Items are score drivers."
        ),
        generated_at=now,
    )


# ---------------------------------------------------------------------------
# Top-level explanation
# ---------------------------------------------------------------------------


def explain_strategy_scores(
    strategy_id: uuid.UUID,
    db: Session,
) -> StrategyScoreExplanation:
    """Build a full, multi-scorecard explanation for a strategy.

    Each explain_* call is guarded so that one failing service does not break
    the whole explanation.
    """
    now = _utcnow()

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")
    strategy_name = strategy.name

    scorecards: list[ScoreCard] = []

    def _safe(card_fn, *args) -> ScoreCard | None:
        try:
            return card_fn(*args)
        except Exception:
            return None

    reliability_card = _safe(explain_reliability_score, strategy_id, db)
    backtest_trust_card = _safe(explain_backtest_trust, strategy_id, db)
    backtest_reality_card = _safe(explain_backtest_reality, strategy_id, db)
    evidence_card = _safe(explain_evidence_verification, strategy_id, db)
    readiness_card = _safe(explain_readiness_score, strategy_id, db)
    shadow_card = _safe(explain_shadow_monitor, strategy_id, db)

    for card in (
        reliability_card,
        backtest_trust_card,
        backtest_reality_card,
        evidence_card,
        readiness_card,
        shadow_card,
    ):
        if card is not None:
            scorecards.append(card)

    # --- Deterministic overall summary ---
    if reliability_card is not None and reliability_card.score is not None:
        verdict_phrase = reliability_card.verdict.replace("_", " ")
        summary = (
            f"Reliability for '{strategy_name}' is "
            f"{reliability_card.score:.1f}/100 ({verdict_phrase})."
        )
    elif reliability_card is not None:
        summary = (
            f"Reliability for '{strategy_name}' has insufficient evidence for an "
            "overall score."
        )
    else:
        summary = f"Score explanation for '{strategy_name}'."

    # Biggest drag across all cards: pick the most negative driver item.
    biggest_drag: ScoreDriverItem | None = None
    for card in scorecards:
        for item in card.items:
            if item.direction != "negative":
                continue
            if biggest_drag is None or item.points < biggest_drag.points:
                biggest_drag = item
    if biggest_drag is not None and biggest_drag.points < 0:
        summary += (
            f" The biggest drag is '{biggest_drag.label}' "
            f"({biggest_drag.explanation[:80]})."
        )

    return StrategyScoreExplanation(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        overall_summary=summary,
        scorecards=scorecards,
        disclaimer=DISCLAIMER,
        generated_at=now,
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _item_dict(item: ScoreDriverItem) -> dict:
    return {
        "key": item.key,
        "label": item.label,
        "points": item.points,
        "direction": item.direction,
        "category": item.category,
        "evidence_type": item.evidence_type,
        "evidence_id": item.evidence_id,
        "explanation": item.explanation,
        "recommended_action": item.recommended_action,
    }


def _card_dict(card: ScoreCard) -> dict:
    return {
        "score_key": card.score_key,
        "label": card.label,
        "score": card.score,
        "max_score": card.max_score,
        "verdict": card.verdict,
        "primary_positive": card.primary_positive,
        "primary_drag": card.primary_drag,
        "items": [_item_dict(i) for i in card.items],
        "formula_note": card.formula_note,
        "generated_at": card.generated_at.isoformat(),
    }


def generate_score_explainability_report(
    strategy_id: uuid.UUID,
    db: Session,
    format: str = "json",
) -> str:
    """Generate a Score Explainability report as JSON or Markdown."""
    explanation = explain_strategy_scores(strategy_id, db)

    if format == "markdown":
        lines: list[str] = [
            f"# Score Explainability — {explanation.strategy_name}",
            "",
            f"**Strategy ID:** {explanation.strategy_id}  ",
            f"**Generated:** {explanation.generated_at.isoformat()}  ",
            "",
            explanation.overall_summary,
            "",
        ]

        for card in explanation.scorecards:
            score_str = (
                f"{card.score:.1f} / {card.max_score:.0f}"
                if card.score is not None
                else "N/A"
            )
            lines += [
                "---",
                "",
                f"## {card.label}",
                "",
                f"**Score:** {score_str}  ",
                f"**Verdict:** {card.verdict}  ",
                "",
                f"_{card.formula_note}_",
                "",
            ]

            positives = [i for i in card.items if i.direction == "positive"]
            negatives = [i for i in card.items if i.direction == "negative"]

            if positives:
                lines += [
                    "### What helped this score",
                    "",
                    "| Driver | Points | Explanation |",
                    "|--------|-------:|-------------|",
                ]
                for i in positives:
                    expl = i.explanation.replace("|", "\\|")
                    lines.append(f"| {i.label} | {i.points:+.1f} | {expl} |")
                lines.append("")

            if negatives:
                lines += [
                    "### What hurt this score",
                    "",
                    "| Driver | Points | Explanation |",
                    "|--------|-------:|-------------|",
                ]
                for i in negatives:
                    expl = i.explanation.replace("|", "\\|")
                    lines.append(f"| {i.label} | {i.points:+.1f} | {expl} |")
                lines.append("")

            recs = [
                i.recommended_action
                for i in card.items
                if i.recommended_action
            ]
            # Deduplicate, preserve order.
            recs = list(dict.fromkeys(recs))
            if recs:
                lines += [
                    "### Recommended actions",
                    "",
                ]
                for r in recs:
                    lines.append(f"- {r}")
                lines.append("")

        lines += [
            "---",
            "",
            f"*{explanation.disclaimer}*",
        ]
        return "\n".join(lines)

    # Default: JSON
    payload = {
        "strategy_id": str(explanation.strategy_id),
        "strategy_name": explanation.strategy_name,
        "overall_summary": explanation.overall_summary,
        "scorecards": [_card_dict(c) for c in explanation.scorecards],
        "disclaimer": explanation.disclaimer,
        "generated_at": explanation.generated_at.isoformat(),
    }
    return json.dumps(payload, indent=2, default=str)
