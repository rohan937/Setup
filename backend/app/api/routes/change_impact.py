"""API routes for M57 Strategy Change Impact Analysis."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.strategy import Strategy
from app.schemas.change_impact import (
    AssumptionImpactSummary,
    ChangeImpactFocusNode,
    GraphBlastRadiusSummary,
    ImpactedArtifact,
    QualityImpactSummary,
    ReadinessImpactSummary,
    RecommendedRecheck,
    StrategyChangeImpactResponse,
)
from app.services.change_impact import analyze_strategy_change_impact

router = APIRouter()


def _parse_strategy_uuid(strategy_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(strategy_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Strategy not found")


def _build_response(data: dict) -> StrategyChangeImpactResponse:
    """Convert the service dict output into the Pydantic response model."""

    focus_raw = data.get("focus_node")
    focus_node = ChangeImpactFocusNode(**focus_raw) if focus_raw else None

    blast_raw = data.get("graph_blast_radius")
    graph_blast = GraphBlastRadiusSummary(**blast_raw) if blast_raw else None

    ai_raw = data.get("assumption_impacts") or {}
    assumption_impacts = AssumptionImpactSummary(
        has_assumption_change=ai_raw.get("has_assumption_change", False),
        positive_change_count=ai_raw.get("positive_change_count", 0),
        weakening_change_count=ai_raw.get("weakening_change_count", 0),
        review_change_count=ai_raw.get("review_change_count", 0),
        key_changes=ai_raw.get("key_changes", []),
        impact_level=ai_raw.get("impact_level", "none"),
        suggested_checks=ai_raw.get("suggested_checks", []),
    )

    qi_raw = data.get("quality_impacts") or {}
    quality_impacts = QualityImpactSummary(
        quality_impact_count=qi_raw.get("quality_impact_count", 0),
        degraded_quality_count=qi_raw.get("degraded_quality_count", 0),
        missing_quality_count=qi_raw.get("missing_quality_count", 0),
        key_quality_findings=qi_raw.get("key_quality_findings", []),
    )

    ri_raw = data.get("readiness_impacts") or {}
    readiness_impacts = ReadinessImpactSummary(
        readiness_verdict=ri_raw.get("readiness_verdict"),
        promotion_risk_count=ri_raw.get("promotion_risk_count", 0),
        failed_regression_count=ri_raw.get("failed_regression_count", 0),
        failed_policy_count=ri_raw.get("failed_policy_count", 0),
        sla_violation_count=ri_raw.get("sla_violation_count", 0),
        open_review_case_count=ri_raw.get("open_review_case_count", 0),
        impact_level=ri_raw.get("impact_level", "none"),
        suggested_checks=ri_raw.get("suggested_checks", []),
    )

    impacted_artifacts = [
        ImpactedArtifact(**a) for a in (data.get("impacted_artifacts") or [])
    ]

    recommended_rechecks = [
        RecommendedRecheck(**r) for r in (data.get("recommended_rechecks") or [])
    ]

    return StrategyChangeImpactResponse(
        strategy_id=data["strategy_id"],
        strategy_name=data["strategy_name"],
        generated_at=data["generated_at"],
        mode=data["mode"],
        focus_node=focus_node,
        impact_score=data.get("impact_score", 100.0),
        impact_status=data.get("impact_status", "no_change_detected"),
        assumption_impacts=assumption_impacts,
        quality_impacts=quality_impacts,
        readiness_impacts=readiness_impacts,
        graph_blast_radius=graph_blast,
        impacted_artifacts=impacted_artifacts,
        recommended_rechecks=recommended_rechecks,
        suggested_actions=data.get("suggested_actions", []),
        deterministic_summary=data.get("deterministic_summary", ""),
    )


@router.get(
    "/strategies/{strategy_id}/change-impact",
    response_model=StrategyChangeImpactResponse,
    summary="Analyse downstream impact of the most recent strategy change",
    description=(
        "Read-only, deterministic analysis of how a recent change "
        "(config update, new signal, new run, etc.) may affect downstream "
        "evidence artefacts.  No AuditTimelineEvent is created."
    ),
)
def get_change_impact(
    strategy_id: str,
    mode: str = Query(
        default="latest_change",
        description=(
            "Scope of change detection.  One of: "
            "latest_change, latest_config_change, latest_evidence_change, focus_node."
        ),
    ),
    focus_node_id: Optional[str] = Query(
        default=None,
        description="Node UUID when mode=focus_node.",
    ),
    focus_node_type: Optional[str] = Query(
        default=None,
        description=(
            "Node type when mode=focus_node.  "
            "One of: config_snapshot, signal_snapshot, universe_snapshot, "
            "strategy_run, backtest_audit."
        ),
    ),
    db: Session = Depends(get_db),
) -> StrategyChangeImpactResponse:
    """Return the change impact analysis for a strategy."""
    sid = _parse_strategy_uuid(strategy_id)

    strategy = db.query(Strategy).filter(Strategy.id == sid).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    data = analyze_strategy_change_impact(
        db,
        sid,
        focus_node_id=focus_node_id,
        focus_node_type=focus_node_type,
        mode=mode,
    )

    return _build_response(data)
