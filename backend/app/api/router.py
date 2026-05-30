"""Top-level API router aggregation.

Wires the M1 foundation routes. Product routers (strategies, datasets,
backtests, drift, alerts) are added in later milestones.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import health, meta

api_router = APIRouter()

# Liveness at the root: GET /health
api_router.include_router(health.router)

# API root metadata: GET /api
api_router.include_router(meta.router, prefix="/api")
