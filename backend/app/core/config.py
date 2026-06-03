"""Application configuration loaded from environment variables.

All settings are prefixed with ``QF_`` and can be supplied via the process
environment or a local ``.env`` file (see ``.env.example``).

M70 production readiness notes
-------------------------------
* Set ``QF_ENVIRONMENT=production`` on Render.
* Set ``QF_DATABASE_URL`` to the Render PostgreSQL internal URL.
  Render may provide a ``postgres://`` URL — this config normalises it to
  ``postgresql://`` automatically for SQLAlchemy compatibility.
* Set ``QF_JWT_SECRET_KEY`` to a long random secret (never the dev default).
* Set ``QF_CORS_ORIGINS`` to your exact frontend origin, e.g.
  ``https://app.yourdomain.com``.
* Set ``QF_DEBUG=false`` in production.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default SQLite URL keeps local dev dependency-free.
# Set QF_DATABASE_URL to a PostgreSQL DSN (e.g. postgresql+psycopg2://...)
# when a real database is available.
_DEFAULT_DB_URL = "sqlite+pysqlite:///./quantfidelity.db"

# Dev-only JWT secret — never use this value in production.
_DEV_JWT_SECRET = "dev-secret-key-change-in-production-do-not-commit"


class Settings(BaseSettings):
    """Typed application settings."""

    model_config = SettingsConfigDict(
        env_prefix="QF_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "QuantFidelity"
    # Values: local | staging | production
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"
    debug: bool = True
    version: str = "0.1.0"
    # Logging level: debug | info | warning | error | critical
    log_level: str = "info"

    # Server — PORT env var (no prefix) respected for Render compatibility.
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS — comma-separated origins in the env var, parsed to a list.
    # Production: set to exact frontend origin, never "*".
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Database
    # SQLite for local dev / CI (no external service required).
    # PostgreSQL for staging / production: postgresql+psycopg2://user:pass@host/db
    # Render provides postgres:// URLs — this class normalises them automatically.
    database_url: str = _DEFAULT_DB_URL

    # M24: API Key authentication
    # Set to True to require valid API keys for evidence bundle ingestion.
    qf_require_api_key_for_ingestion: bool = False
    # Optional secret pepper for HMAC-SHA256 key hashing. Leave empty for local dev.
    qf_api_key_hash_secret: str = ""
    # API key prefix environment token: "local" or "live"
    qf_api_key_env: str = "local"

    # M68: JWT / User Auth
    QF_AUTH_ENABLED: bool = True
    QF_JWT_SECRET_KEY: str = _DEV_JWT_SECRET
    QF_JWT_ALGORITHM: str = "HS256"
    QF_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # M69: RBAC + Workspace/Project Access Control
    # When True, workspace role is enforced for authenticated callers.
    # When False, enforcement is skipped (permissive local dev).
    # Note: even when True, requests with no bearer token are treated as a
    # local-dev pseudo-owner so existing unauthenticated flows keep working.
    QF_RBAC_ENABLED: bool = True

    # ---------------------------------------------------------------------------
    # Validators
    # ---------------------------------------------------------------------------

    @field_validator("database_url", mode="before")
    @classmethod
    def normalise_postgres_url(cls, v: str) -> str:
        """Render provides ``postgres://`` URLs; SQLAlchemy requires ``postgresql://``.

        This validator silently rewrites the scheme so operators can paste the
        Render-provided connection string without modification.
        """
        if isinstance(v, str) and v.startswith("postgres://"):
            return "postgresql://" + v[len("postgres://"):]
        return v

    # ---------------------------------------------------------------------------
    # Computed properties
    # ---------------------------------------------------------------------------

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def jwt_secret_is_dev_default(self) -> bool:
        """True when the JWT secret has not been changed from the insecure dev value."""
        return self.QF_JWT_SECRET_KEY == _DEV_JWT_SECRET

    @property
    def production_jwt_secret_unsafe(self) -> bool:
        """True when running in production with an unsafe (dev-default) JWT secret."""
        return self.is_production and self.jwt_secret_is_dev_default


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
