"""Top-level API router aggregation.

M1 routes: /health, /api (meta)
M2 routes: /api/projects, /api/strategies, /api/timeline
Product routers for lineage, data integrity, backtests, drift, alerts, etc.
are added in later milestones.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import health, meta, projects, strategies, timeline

api_router = APIRouter()

# Liveness at the root: GET /health
api_router.include_router(health.router)

# All /api/* routes share the /api prefix.
api_router.include_router(meta.router, prefix="/api")
api_router.include_router(projects.router, prefix="/api")
api_router.include_router(strategies.router, prefix="/api")
api_router.include_router(timeline.router, prefix="/api")
