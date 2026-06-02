"""Top-level API router aggregation.

M1 routes: /health, /api (meta)
M2 routes: /api/projects, /api/strategies, /api/timeline
M6 routes: /api/datasets, /api/dataset-snapshots
M8 routes: /api/strategy-runs/{id}/backtest-audit, /api/backtests/audits
M9 routes: /api/dashboard/summary
M11 routes: /api/alerts/generate, /api/alerts
M14 routes: /api/reports
M24 routes: /api/api-keys
M32 routes: /api/portfolio/overview
M45 routes: /api/admin/system-health
M53 routes: /api/strategies/{id}/regression-tests, /api/regression-test-runs/{id}
M54 routes: /api/strategies/{id}/config-policies, /api/config-policy-evaluations/{id}
M55 routes: /api/strategies/{id}/review-cases, /api/review-cases/{id}
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import admin, alerts, api_keys, backtests, config_policies, dashboard, datasets, evidence, health, meta, portfolio, projects, regression, reliability, reports, review_cases, strategies, timeline

api_router = APIRouter()

# Liveness at the root: GET /health
api_router.include_router(health.router)

# All /api/* routes share the /api prefix.
api_router.include_router(meta.router, prefix="/api")
api_router.include_router(projects.router, prefix="/api")
api_router.include_router(strategies.router, prefix="/api")
api_router.include_router(timeline.router, prefix="/api")
api_router.include_router(datasets.router, prefix="/api")
api_router.include_router(backtests.router, prefix="/api")
api_router.include_router(dashboard.router, prefix="/api")
api_router.include_router(alerts.router, prefix="/api")
api_router.include_router(reports.router, prefix="/api")
api_router.include_router(reliability.router, prefix="/api")
api_router.include_router(evidence.router, prefix="/api")
api_router.include_router(api_keys.router, prefix="/api")
api_router.include_router(portfolio.router, prefix="/api")
api_router.include_router(admin.router, prefix="/api")
api_router.include_router(regression.router, prefix="/api")
api_router.include_router(config_policies.router, prefix="/api")
api_router.include_router(review_cases.router, prefix="/api")
