"""Top-level API router aggregation.

M1 routes: /health, /api (meta)
M2 routes: /api/projects, /api/strategies, /api/timeline
M6 routes: /api/datasets, /api/dataset-snapshots
M8 routes: /api/strategy-runs/{id}/backtest-audit, /api/backtests/audits
M9 routes: /api/dashboard/summary
M11 routes: /api/alerts/generate, /api/alerts
M14 routes: /api/reports
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import alerts, backtests, dashboard, datasets, health, meta, projects, reports, strategies, timeline

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
