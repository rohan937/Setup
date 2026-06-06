"""Strategy Risk Narrative Generator service (M100).

A deterministic, READ-ONLY composition layer that turns the already-computed
QuantFidelity scorecards (reliability, backtest trust, backtest reality,
evidence verification, readiness, shadow monitor) plus readiness blockers and
open alerts into a plain-language *governance* narrative: a headline, a short
templated paragraph, ranked strengths and risks, and recommended next actions.

Design notes
------------
* READ-ONLY: this module never calls db.add / db.commit / db.flush. It only
  reads via other read-only services and the strategy lookup.
* Deterministic: NO LLM, no live market data, no randomness. Same inputs always
  produce the same output. The narrative is templated, not generated.
* Evidence-grounded: every strength and risk maps to an actual scorecard item,
  readiness blocker, alert condition, or missing-evidence signal. Nothing is
  invented.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.services.readiness_simulator import (
    _normalize_target_stage,
    get_current_readiness,
)
from app.services.score_explainability import explain_strategy_scores


DISCLAIMER = (
    "This narrative summarizes research evidence quality and governance "
    "readiness. It is not trading advice."
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class NarrativeStrength:
    key: str
    label: str
    evidence: str


@dataclass
class NarrativeRisk:
    key: str
    label: str
    severity: str  # low | medium | high | critical
    evidence: str
    recommended_action: str | None


@dataclass
class RiskNarrativeData:
    strategy_id: uuid.UUID
    strategy_name: str
    target_stage: str
    headline: str
    narrative: str
    verdict: str  # ready | review | blocked | insufficient_data
    confidence: str  # high | medium | low
    primary_strengths: list[NarrativeStrength]
    primary_risks: list[NarrativeRisk]
    recommended_next_actions: list[str]
    source_scores: dict[str, float | None]
    disclaimer: str
    generated_at: datetime


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Scorecard verdict strings that we treat as a "good standing" score.
_STRONG_VERDICTS = {"strong", "good", "pass", "ready", "trustworthy", "verified"}

_STAGE_LABELS = {
    "idea": "idea",
    "research": "research",
    "backtest_review": "backtest review",
    "paper_candidate": "paper-trading",
    "shadow_production": "shadow-production",
    "production_candidate": "production",
}


def _stage_phrase(stage: str) -> str:
    return _STAGE_LABELS.get(stage, stage.replace("_", " "))


def _points_to_severity(points: float) -> str:
    """Map an (absolute) negative driver magnitude onto a risk severity."""
    mag = abs(points)
    if mag >= 25:
        return "critical"
    if mag >= 15:
        return "high"
    if mag >= 8:
        return "medium"
    return "low"


def _clean(text: str | None, limit: int = 160) -> str:
    if not text:
        return ""
    text = " ".join(str(text).split())
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


# ---------------------------------------------------------------------------
# Input gathering
# ---------------------------------------------------------------------------


def build_risk_narrative_inputs(
    strategy_id: uuid.UUID,
    db: Session,
    target_stage: str | None = None,
) -> dict:
    """Gather the read-only inputs for the risk narrative.

    Each upstream service call is guarded so that one failing service does not
    break the whole narrative. Returns a dict with the raw explanation, the
    readiness state, the alert summary, a normalized ``source_scores`` map, a
    ``scorecards_by_key`` index, and the resolved ``target_stage``.
    """
    try:
        explanation = explain_strategy_scores(strategy_id, db)
    except Exception:
        explanation = None

    try:
        readiness = get_current_readiness(strategy_id, db, target_stage)
    except Exception:
        readiness = None

    try:
        from app.services.alerts import get_strategy_alert_summary

        alerts = get_strategy_alert_summary(db, str(strategy_id))
    except Exception:
        alerts = None

    scorecards_by_key: dict = {}
    if explanation is not None:
        for card in explanation.scorecards:
            scorecards_by_key[card.score_key] = card

    def _score_of(key: str) -> float | None:
        card = scorecards_by_key.get(key)
        return card.score if card is not None else None

    source_scores: dict[str, float | None] = {
        "reliability_score": _score_of("reliability"),
        "backtest_reality_score": _score_of("backtest_reality"),
        "evidence_verification_score": _score_of("evidence_verification"),
        "readiness_score": _score_of("readiness"),
        "backtest_trust_score": _score_of("backtest_trust"),
        "shadow_drift_score": _score_of("shadow_monitor"),
    }

    # Resolved target stage: prefer the readiness-resolved stage; otherwise
    # normalize the requested one.
    if readiness is not None:
        resolved_target = readiness.target_stage
    else:
        resolved_target = _normalize_target_stage(target_stage) or "backtest_review"

    return {
        "explanation": explanation,
        "readiness": readiness,
        "alerts": alerts,
        "source_scores": source_scores,
        "scorecards_by_key": scorecards_by_key,
        "target_stage": resolved_target,
    }


# ---------------------------------------------------------------------------
# Strength classification
# ---------------------------------------------------------------------------


def classify_primary_strengths(inputs: dict) -> list[NarrativeStrength]:
    """Surface up to ~5 evidence-grounded strengths from the scorecards."""
    explanation = inputs.get("explanation")
    if explanation is None:
        return []

    strengths: list[NarrativeStrength] = []
    seen: set[str] = set()

    def _emit(key: str, label: str, evidence: str) -> None:
        if key in seen or not evidence:
            return
        seen.add(key)
        strengths.append(
            NarrativeStrength(key=key, label=label, evidence=_clean(evidence))
        )

    for card in explanation.scorecards:
        if card.score is None:
            continue
        is_strong = (card.verdict in _STRONG_VERDICTS) or (card.score >= 70)
        if not is_strong:
            continue

        positive_items = [i for i in card.items if i.direction == "positive"]

        # Card-level strength (anchored on its strongest positive item evidence).
        if card.primary_positive or positive_items:
            top_item = (
                max(positive_items, key=lambda i: i.points)
                if positive_items
                else None
            )
            evidence = (
                top_item.explanation
                if top_item is not None
                else f"{card.label} is {card.score:.0f}/100 ({card.verdict})."
            )
            label = card.primary_positive or f"Strong {card.label.lower()}"
            _emit(f"card_{card.score_key}", label, evidence)

        # Strong reliability sub-components (positive items with material points).
        if card.score_key == "reliability":
            strong_components = sorted(
                (i for i in positive_items if i.points >= 10),
                key=lambda i: i.points,
                reverse=True,
            )
            for item in strong_components:
                _emit(f"reliability_{item.key}", item.label, item.explanation)

    return strengths[:5]


# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------


def classify_primary_risks(inputs: dict) -> list[NarrativeRisk]:
    """Aggregate evidence-grounded risks from scorecards, blockers, and alerts."""
    explanation = inputs.get("explanation")
    readiness = inputs.get("readiness")
    alerts = inputs.get("alerts")
    by_key = inputs.get("scorecards_by_key") or {}

    risks: list[NarrativeRisk] = []
    seen: set[str] = set()
    # Track the magnitude used for ranking within the same severity.
    rank_points: dict[str, float] = {}

    def _emit(
        key: str,
        label: str,
        severity: str,
        evidence: str,
        action: str | None,
        points: float = 0.0,
    ) -> None:
        if key in seen or not evidence:
            return
        seen.add(key)
        rank_points[key] = abs(points)
        risks.append(
            NarrativeRisk(
                key=key,
                label=label,
                severity=severity,
                evidence=_clean(evidence),
                recommended_action=_clean(action) or None,
            )
        )

    # 1. Negative drivers across ALL scorecards.
    if explanation is not None:
        for card in explanation.scorecards:
            for item in card.items:
                if item.direction != "negative":
                    continue
                # Skip pure-coverage neutral-magnitude placeholders that carry
                # no real penalty AND no explanation worth surfacing.
                severity = _points_to_severity(item.points)
                key = f"{card.score_key}:{item.key}"
                label = item.label or card.label
                _emit(
                    key=key,
                    label=label,
                    severity=severity,
                    evidence=item.explanation,
                    action=item.recommended_action,
                    points=item.points,
                )

    # 2. Backtest reality weak verdict -> high risk.
    reality_card = by_key.get("backtest_reality")
    if reality_card is not None and reality_card.verdict in ("weak", "fail"):
        _emit(
            key="backtest_reality_weak",
            label="Backtest reality is weak",
            severity="high",
            evidence=(
                reality_card.primary_drag
                or "The backtest reality check flags low-confidence assumptions."
            ),
            action="Review and strengthen the backtest assumptions.",
            points=-15.0,
        )

    # 3. Shadow card with no paper/shadow run.
    shadow_card = by_key.get("shadow_monitor")
    if shadow_card is not None and (
        shadow_card.verdict == "insufficient_data" or shadow_card.score is None
    ):
        drag = shadow_card.primary_drag or (
            shadow_card.items[0].explanation if shadow_card.items else ""
        )
        _emit(
            key="no_paper_run",
            label="No paper/shadow run",
            severity="medium",
            evidence=drag
            or "No paper or shadow run exists to validate the backtest baseline.",
            action="Upload a paper run.",
            points=-8.0,
        )

    # 4. Missing reliability report (reliability card negative item).
    reliability_card = by_key.get("reliability")
    if reliability_card is not None:
        for item in reliability_card.items:
            if item.category == "report_coverage" and item.direction == "negative":
                _emit(
                    key="no_reliability_report",
                    label="No reliability report",
                    severity="medium",
                    evidence=item.explanation,
                    action=item.recommended_action
                    or "Generate a reliability report for this strategy.",
                    points=-8.0,
                )

    # 5. Readiness blockers (medium/high).
    if readiness is not None:
        for idx, blocker in enumerate(readiness.current_blockers or []):
            b_lower = blocker.lower()
            severity = (
                "high"
                if any(
                    t in b_lower
                    for t in ("paper", "live", "alert", "coverage", "missing")
                )
                else "medium"
            )
            points = -15.0 if severity == "high" else -8.0
            _emit(
                key=f"blocker_{idx}",
                label="Promotion blocker",
                severity=severity,
                evidence=blocker,
                action=None,
                points=points,
            )

    # 6. Open high/critical alerts.
    if alerts is not None:
        by_severity = alerts.get("by_severity", {}) if isinstance(alerts, dict) else {}
        high = int(by_severity.get("high", 0) or 0)
        critical = int(by_severity.get("critical", 0) or 0)
        if high + critical > 0:
            severity = "critical" if critical > 0 else "high"
            parts = []
            if critical:
                parts.append(f"{critical} critical")
            if high:
                parts.append(f"{high} high")
            _emit(
                key="open_high_alerts",
                label="Open high/critical alerts",
                severity=severity,
                evidence=(
                    f"There are {' and '.join(parts)} open alert(s) that flag "
                    "reliability issues blocking progression."
                ),
                action="Resolve the open high/critical alerts.",
                points=-20.0 if critical else -15.0,
            )

    # Rank by severity, then by magnitude, then by key for stability.
    risks.sort(
        key=lambda r: (
            _SEVERITY_RANK.get(r.severity, 9),
            -rank_points.get(r.key, 0.0),
            r.key,
        )
    )
    return risks[:6]


# ---------------------------------------------------------------------------
# Next actions
# ---------------------------------------------------------------------------


def classify_next_actions(
    strengths: list[NarrativeStrength],
    risks: list[NarrativeRisk],
    inputs: dict,
) -> list[str]:
    """Deterministic, deduped next actions ordered by risk severity."""
    readiness = inputs.get("readiness")

    actions: list[str] = []
    seen: set[str] = set()

    def _add(text: str | None) -> None:
        if not text:
            return
        text = _clean(text)
        norm = text.lower().rstrip(".")
        if norm in seen:
            return
        seen.add(norm)
        actions.append(text)

    # Risks are already severity-ordered.
    for risk in risks:
        _add(risk.recommended_action)

    # Then readiness recommended-action titles.
    if readiness is not None:
        for action in readiness.recommended_actions or []:
            _add(getattr(action, "title", None))

    return actions[:6]


# ---------------------------------------------------------------------------
# Verdict + confidence
# ---------------------------------------------------------------------------


def _resolve_verdict_and_confidence(
    inputs: dict,
    risks: list[NarrativeRisk],
) -> tuple[str, str]:
    by_key = inputs.get("scorecards_by_key") or {}
    readiness = inputs.get("readiness")
    source_scores = inputs.get("source_scores") or {}

    reliability_card = by_key.get("reliability")
    trust_card = by_key.get("backtest_trust")

    reliability_score = (
        reliability_card.score if reliability_card is not None else None
    )

    reliability_insufficient = (
        reliability_card is not None
        and reliability_card.verdict == "insufficient_data"
    ) or reliability_card is None
    trust_insufficient = (
        trust_card is not None and trust_card.verdict == "insufficient_data"
    ) or trust_card is None

    # --- Verdict ---
    if reliability_score is None and reliability_insufficient and trust_insufficient:
        verdict = "insufficient_data"
    else:
        has_high_risk = any(r.severity in ("critical", "high") for r in risks)
        readiness_verdict = (
            readiness.current_verdict if readiness is not None else "review"
        )
        if has_high_risk and readiness_verdict == "blocked":
            verdict = "blocked"
        elif readiness_verdict == "blocked":
            verdict = "blocked"
        elif readiness_verdict == "ready" and not has_high_risk:
            verdict = "ready"
        else:
            verdict = "review"

    # --- Confidence ---
    non_none = sum(1 for v in source_scores.values() if v is not None)
    if reliability_score is not None and non_none >= 4:
        confidence = "high"
    elif non_none >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    if verdict == "insufficient_data":
        confidence = "low"

    return verdict, confidence


# ---------------------------------------------------------------------------
# Headline + narrative
# ---------------------------------------------------------------------------


def _build_headline(verdict: str, stage_phrase: str) -> str:
    if verdict == "ready":
        return f"Strong research foundation; suitable for {stage_phrase} consideration."
    if verdict == "review":
        return f"Promising but incomplete; key gaps remain before {stage_phrase}."
    if verdict == "blocked":
        return f"Not ready for {stage_phrase}; critical blockers remain."
    return "Too little evidence exists to form a reliable governance summary."


def _join_natural(items: list[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _build_narrative(
    verdict: str,
    confidence: str,
    strengths: list[NarrativeStrength],
    risks: list[NarrativeRisk],
    next_actions: list[str],
    stage_phrase: str,
) -> str:
    if verdict == "insufficient_data":
        return (
            "Too little evidence has been logged to assess this strategy's research "
            "quality or governance readiness. Log a backtest run and link its "
            "dataset, signal, and universe evidence first to enable a reliable "
            "governance summary."
        )

    sentences: list[str] = []

    # Sentence 1: strongest 1-2 strengths.
    if strengths:
        strength_labels = [s.label.rstrip(".") for s in strengths[:2]]
        sentences.append(
            f"This strategy has {_join_natural(strength_labels).lower()}."
        )
    else:
        sentences.append(
            "This strategy has limited positive evidence on record so far."
        )

    # Sentence 2: top 2-3 risks named naturally.
    if risks:
        risk_labels = [r.label.rstrip(".").lower() for r in risks[:3]]
        sentences.append(
            f"The main research risks are {_join_natural(risk_labels)}."
        )

    # Sentence 3: readiness conclusion tied to stage + top next action.
    if verdict == "ready":
        conclusion = (
            f"It is suitable for {stage_phrase} consideration based on the current "
            "evidence."
        )
    elif verdict == "blocked":
        conclusion = (
            f"It is not ready for {stage_phrase} until the critical blockers above "
            "are cleared."
        )
    else:
        conclusion = (
            f"It is suitable for {stage_phrase} consideration"
        )
        if next_actions:
            conclusion += f" after {next_actions[0].rstrip('.').lower()} is completed"
        conclusion += "."
    sentences.append(conclusion)

    return " ".join(sentences)


# ---------------------------------------------------------------------------
# Top-level generation
# ---------------------------------------------------------------------------


def generate_strategy_risk_narrative(
    strategy_id: uuid.UUID,
    db: Session,
    target_stage: str | None = None,
) -> RiskNarrativeData:
    """Build the full deterministic risk narrative for a strategy (read-only)."""
    from app.models.strategy import Strategy

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    now = _utcnow()

    inputs = build_risk_narrative_inputs(strategy_id, db, target_stage)
    resolved_stage = inputs["target_stage"]
    stage_phrase = _stage_phrase(resolved_stage)

    strengths = classify_primary_strengths(inputs)
    risks = classify_primary_risks(inputs)
    next_actions = classify_next_actions(strengths, risks, inputs)

    verdict, confidence = _resolve_verdict_and_confidence(inputs, risks)

    headline = _build_headline(verdict, stage_phrase)
    narrative = _build_narrative(
        verdict, confidence, strengths, risks, next_actions, stage_phrase
    )

    return RiskNarrativeData(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        target_stage=resolved_stage,
        headline=headline,
        narrative=narrative,
        verdict=verdict,
        confidence=confidence,
        primary_strengths=strengths,
        primary_risks=risks,
        recommended_next_actions=next_actions,
        source_scores=inputs["source_scores"],
        disclaimer=DISCLAIMER,
        generated_at=now,
    )


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _strength_dict(s: NarrativeStrength) -> dict:
    return {"key": s.key, "label": s.label, "evidence": s.evidence}


def _risk_dict(r: NarrativeRisk) -> dict:
    return {
        "key": r.key,
        "label": r.label,
        "severity": r.severity,
        "evidence": r.evidence,
        "recommended_action": r.recommended_action,
    }


def render_risk_narrative_report(
    strategy_id: uuid.UUID,
    db: Session,
    target_stage: str | None = None,
    format: str = "json",
) -> str:
    """Render the risk narrative as JSON or Markdown."""
    data = generate_strategy_risk_narrative(strategy_id, db, target_stage)

    if format == "markdown":
        lines: list[str] = [
            f"# Research Risk Narrative — {data.strategy_name}",
            "",
            f"**Strategy ID:** {data.strategy_id}  ",
            f"**Target stage:** {data.target_stage}  ",
            f"**Generated:** {data.generated_at.isoformat()}  ",
            "",
            f"**{data.headline}**",
            "",
            f"_Verdict: {data.verdict} · Confidence: {data.confidence}_",
            "",
            data.narrative,
            "",
            "## Primary Strengths",
            "",
        ]
        if data.primary_strengths:
            for s in data.primary_strengths:
                lines.append(f"- **{s.label}** — {s.evidence}")
        else:
            lines.append("- None identified from the current evidence.")
        lines += ["", "## Primary Risks", ""]
        if data.primary_risks:
            for r in data.primary_risks:
                action = (
                    f" _Recommended action: {r.recommended_action}_"
                    if r.recommended_action
                    else ""
                )
                lines.append(
                    f"- **[{r.severity.upper()}] {r.label}** — {r.evidence}{action}"
                )
        else:
            lines.append("- None identified from the current evidence.")
        lines += ["", "## Recommended Next Actions", ""]
        if data.recommended_next_actions:
            for a in data.recommended_next_actions:
                lines.append(f"- {a}")
        else:
            lines.append("- None.")
        lines += [
            "",
            "## Source Scores",
            "",
            "| Score | Value |",
            "|-------|------:|",
        ]
        for key, value in data.source_scores.items():
            val = f"{value:.1f}" if value is not None else "N/A"
            lines.append(f"| {key} | {val} |")
        lines += ["", "---", "", f"*{data.disclaimer}*"]
        return "\n".join(lines)

    # Default: JSON
    payload = {
        "strategy_id": str(data.strategy_id),
        "strategy_name": data.strategy_name,
        "target_stage": data.target_stage,
        "headline": data.headline,
        "narrative": data.narrative,
        "verdict": data.verdict,
        "confidence": data.confidence,
        "primary_strengths": [_strength_dict(s) for s in data.primary_strengths],
        "primary_risks": [_risk_dict(r) for r in data.primary_risks],
        "recommended_next_actions": data.recommended_next_actions,
        "source_scores": data.source_scores,
        "disclaimer": data.disclaimer,
        "generated_at": data.generated_at.isoformat(),
    }
    return json.dumps(payload, indent=2, default=str)
