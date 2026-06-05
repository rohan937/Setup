"""QuantFidelity FastAPI application entrypoint.

M1 foundation only: app initialization, config, CORS, and meta/health routes.
No database access and no product logic yet.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings


@asynccontextmanager
async def _lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Application lifespan: assert production safety, then serve, then shutdown.

    Two hard failures are enforced before the app accepts any traffic:
      1. Production + SQLite  → data is permanently lost on every Render deploy.
      2. Production + dev JWT → anyone can forge tokens and impersonate users.

    Both raise RuntimeError with actionable guidance so Render's deploy logs
    show the fix immediately.
    """
    get_settings().assert_production_safe()
    yield  # application is running


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Quant strategy reliability and observability infrastructure.",
        debug=settings.debug,
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    return app


app = create_app()
