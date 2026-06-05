"""Health check endpoints — liveness and deployment health (M70)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.common import DeploymentHealthResponse, HealthResponse

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness probe. Returns service identity and environment."""
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.version,
        environment=settings.environment,
    )


@router.get("/api/health/deployment", response_model=DeploymentHealthResponse)
def deployment_health(
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> DeploymentHealthResponse:
    """M70: Deployment health check.

    Returns a structured report about the deployment configuration.
    Safe to expose publicly — never includes secret values.

    Useful to verify environment variable binding on a new Render deployment
    before routing production traffic.
    """
    # Determine database driver from URL scheme.
    db_url = settings.database_url
    if db_url.startswith("sqlite"):
        database_driver = "sqlite"
    elif "psycopg2" in db_url:
        database_driver = "postgresql+psycopg2"
    elif db_url.startswith("postgresql") or db_url.startswith("postgres"):
        database_driver = "postgresql"
    else:
        database_driver = "unknown"

    database_configured = not db_url.startswith("sqlite")

    # Live connectivity probe — fail gracefully so the endpoint stays up.
    database_reachable = False
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        database_reachable = True
    except Exception:
        database_reachable = False

    # For SQLite, always treat as "reachable" (file-based, no network).
    if settings.is_sqlite:
        database_reachable = True

    cors_configured = bool(settings.cors_origin_list)
    jwt_secret_safe = not settings.jwt_secret_is_dev_default

    # True when at least one non-localhost origin is allowed (i.e. a real frontend).
    _non_local_origins = [
        o for o in settings.cors_origin_list
        if "localhost" not in o and "127.0.0.1" not in o
    ]
    cors_has_public_origin = bool(_non_local_origins)

    # Collect production warnings without revealing secrets.
    warnings: list[str] = []
    if settings.is_production:
        if settings.jwt_secret_is_dev_default:
            warnings.append(
                "QF_JWT_SECRET_KEY is the insecure dev default — set a strong secret before serving real users."
            )
        if settings.is_sqlite:
            warnings.append(
                "QF_DATABASE_URL is SQLite — use PostgreSQL for production deployments."
            )
        if settings.debug:
            warnings.append(
                "QF_DEBUG=true in production — set to false to suppress debug output."
            )
        if not settings.require_api_key_for_ingestion:
            warnings.append(
                "QF_REQUIRE_API_KEY_FOR_INGESTION=false — consider enabling in production."
            )
        if not cors_has_public_origin:
            # Only localhost origins are allowed — the deployed frontend will be
            # blocked by CORS on every request. Set QF_FRONTEND_URL (or
            # QF_CORS_ORIGINS) to include the Vercel / production URL.
            warnings.append(
                "CORS origins only include localhost. "
                "Set QF_FRONTEND_URL=https://your-app.vercel.app (or QF_CORS_ORIGINS) "
                "so the deployed frontend can reach the API."
            )

    return DeploymentHealthResponse(
        status="ok",
        environment=settings.environment,
        version=settings.version,
        database_configured=database_configured,
        database_reachable=database_reachable,
        database_driver=database_driver,
        migrations_note="Run 'alembic upgrade head' before first start and after schema changes.",
        auth_enabled=settings.auth_enabled,
        rbac_enabled=settings.rbac_enabled,
        cors_configured=cors_configured,
        database_persistent_safe=settings.database_persistent_safe,
        jwt_secret_safe=jwt_secret_safe,
        production_warnings=warnings,
    )
