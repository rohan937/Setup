"""Portfolio endpoints (M32).

GET /api/portfolio/overview — aggregated portfolio snapshot across strategies.

Design rules:
  - Deterministic — no AI, no live market data, no external calls.
  - Read-only: no db.commit(), no AuditTimelineEvent creation.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.portfolio_overview import (
    PortfolioOverviewResponse,
    PortfolioStrategyItem,
    PortfolioTrendFlags,
    PortfolioRecentActivityItem,
)
from app.services.portfolio_overview import get_portfolio_overview

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio/overview", response_model=PortfolioOverviewResponse)
def get_portfolio_overview_endpoint(
    project_id: uuid.UUID | None = Query(default=None),
    organization_id: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit_per_section: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> PortfolioOverviewResponse:
    result = get_portfolio_overview(
        db,
        project_id=project_id,
        organization_id=organization_id,
        include_archived=include_archived,
        limit_per_section=limit_per_section,
    )

    def _item(i) -> PortfolioStrategyItem:
        return PortfolioStrategyItem(
            strategy_id=i.strategy_id,
            name=i.name,
            slug=i.slug,
            asset_class=i.asset_class,
            status=i.status,
            health_score=i.health_score,
            health_status=i.health_status,
            primary_concern=i.primary_concern,
            reliability_score=i.reliability_score,
            reliability_status=i.reliability_status,
            evidence_coverage_score=i.evidence_coverage_score,
            open_alert_count=i.open_alert_count,
            high_critical_alert_count=i.high_critical_alert_count,
            latest_run_at=i.latest_run_at,
            days_since_latest_run=i.days_since_latest_run,
            trend_flags=PortfolioTrendFlags(
                reliability_deteriorating=i.trend_flags.reliability_deteriorating,
                data_health_deteriorating=i.trend_flags.data_health_deteriorating,
                backtest_trust_deteriorating=i.trend_flags.backtest_trust_deteriorating,
                signal_quality_deteriorating=i.trend_flags.signal_quality_deteriorating,
            ),
            missing_evidence_count=i.missing_evidence_count,
            review_reason=i.review_reason,
        )

    return PortfolioOverviewResponse(
        generated_at=result.generated_at,
        strategy_count=result.strategy_count,
        active_strategy_count=result.active_strategy_count,
        archived_strategy_count=result.archived_strategy_count,
        average_health_score=result.average_health_score,
        average_reliability_score=result.average_reliability_score,
        average_evidence_coverage_score=result.average_evidence_coverage_score,
        open_alert_count=result.open_alert_count,
        high_critical_alert_count=result.high_critical_alert_count,
        strategies_by_health_status=result.strategies_by_health_status,
        strategies_by_reliability_status=result.strategies_by_reliability_status,
        strategies_by_asset_class=result.strategies_by_asset_class,
        all_items=[_item(i) for i in result.all_items],
        top_review_strategies=[_item(i) for i in result.top_review_strategies],
        most_under_instrumented_strategies=[_item(i) for i in result.most_under_instrumented_strategies],
        strongest_evidence_strategies=[_item(i) for i in result.strongest_evidence_strategies],
        deteriorating_trend_strategies=[_item(i) for i in result.deteriorating_trend_strategies],
        recent_activity=[],
        suggested_next_steps=result.suggested_next_steps,
        deterministic_summary=result.deterministic_summary,
    )
