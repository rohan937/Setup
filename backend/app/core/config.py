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
* Alternatively set ``QF_FRONTEND_URL`` to a single frontend URL — it is
  automatically appended to ``QF_CORS_ORIGINS`` so you don't have to repeat
  the localhost defaults when adding a production domain.
  Example: ``QF_FRONTEND_URL=https://quantfidelity.vercel.app``
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
    # Production: set QF_CORS_ORIGINS to exact frontend origin, never "*".
    # Alternatively set QF_FRONTEND_URL and it will be appended automatically.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Optional single frontend URL added to CORS origins automatically.
    # Useful on Render: set QF_FRONTEND_URL=https://quantfidelity.vercel.app
    # so the Vercel frontend can reach the API without editing cors_origins.
    frontend_url: str = ""

    # Database
    # SQLite for local dev / CI (no external service required).
    # PostgreSQL for staging / production: postgresql+psycopg2://user:pass@host/db
    # Render provides postgres:// URLs — this class normalises them automatically.
    database_url: str = _DEFAULT_DB_URL

    # M24: API Key authentication
    # Set to True to require valid API keys for evidence bundle ingestion.
    # Env var: QF_REQUIRE_API_KEY_FOR_INGESTION
    require_api_key_for_ingestion: bool = False
    # Optional secret pepper for HMAC-SHA256 key hashing. Leave empty for local dev.
    # Env var: QF_API_KEY_HASH_SECRET
    api_key_hash_secret: str = ""
    # API key prefix environment token: "local" or "live"
    # Env var: QF_API_KEY_ENV
    api_key_env: str = "local"

    # M68: JWT / User Auth
    # Env vars: QF_AUTH_ENABLED, QF_JWT_SECRET_KEY, QF_JWT_ALGORITHM,
    #           QF_ACCESS_TOKEN_EXPIRE_MINUTES
    # Note: field names omit the "QF_" prefix because pydantic-settings
    # prepends env_prefix="QF_" automatically. Using QF_ in the field name
    # would produce the double-prefixed env var QF_QF_* (incorrect).
    auth_enabled: bool = True
    jwt_secret_key: str = _DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    # Default: 7 days (10080 minutes). A demo SaaS app should keep users logged
    # in across typical usage gaps. Set QF_ACCESS_TOKEN_EXPIRE_MINUTES on Render
    # (or locally) to override — e.g. 1440 (24 h) for stricter production.
    # Previous default was 1440 (24 h) which caused auto-sign-out for users who
    # didn't revisit the app daily.
    access_token_expire_minutes: int = 10080

    # M69: RBAC + Workspace/Project Access Control
    # Env var: QF_RBAC_ENABLED
    # When True, workspace role is enforced for authenticated callers.
    # When False, enforcement is skipped (permissive local dev).
    # Note: even when True, requests with no bearer token are treated as a
    # local-dev pseudo-owner so existing unauthenticated flows keep working.
    rbac_enabled: bool = True

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
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        # Automatically include QF_FRONTEND_URL when set (e.g. the Vercel URL on Render).
        if self.frontend_url:
            url = self.frontend_url.rstrip("/")
            if url not in origins:
                origins.append(url)
        return origins

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def jwt_secret_is_dev_default(self) -> bool:
        """True when the JWT secret has not been changed from the insecure dev value."""
        return self.jwt_secret_key == _DEV_JWT_SECRET

    @property
    def production_jwt_secret_unsafe(self) -> bool:
        """True when running in production with an unsafe (dev-default) JWT secret."""
        return self.is_production and self.jwt_secret_is_dev_default

    @property
    def database_persistent_safe(self) -> bool:
        """True when the database will persist data across restarts/redeploys.

        SQLite on Render's ephemeral filesystem loses all data on every deploy.
        PostgreSQL (and any non-SQLite URL) is considered persistent-safe.
        """
        return not self.is_sqlite

    def assert_production_safe(self) -> None:
        """Raise RuntimeError if critical production config guards are not met.

        Called at application startup. Two hard failures are enforced:

        1. SQLite in production — Render's ephemeral disk destroys SQLite
           files on every deploy. Every user account, strategy, and piece of
           evidence would be permanently lost. Require a real database URL.

        2. Dev-default JWT secret in production — anyone who knows the default
           value can forge tokens and impersonate any user. Require a strong
           secret before serving real traffic.

        Deliberately raises RuntimeError (not a soft warning) so the process
        exits and Render shows the error in deploy logs, making the fix obvious.
        """
        if not self.is_production:
            return  # Only enforce in production mode

        errors: list[str] = []

        if self.is_sqlite:
            errors.append(
                "QF_DATABASE_URL is SQLite, which uses Render's ephemeral "
                "filesystem. All accounts and data are destroyed on every "
                "deploy. Set QF_DATABASE_URL to your Render Postgres internal "
                "URL (e.g. postgresql://user:pass@host/db) before starting."
            )

        if self.jwt_secret_is_dev_default:
            errors.append(
                "QF_JWT_SECRET_KEY is the insecure dev default. Anyone who "
                "knows this value can forge authentication tokens and "
                "impersonate any user. Generate a strong random secret "
                "(e.g. openssl rand -hex 32) and set it as QF_JWT_SECRET_KEY "
                "before starting in production."
            )

        if errors:
            header = (
                f"[QuantFidelity] Production startup blocked — "
                f"{len(errors)} configuration error(s) must be fixed:\n"
            )
            body = "\n".join(f"  {i+1}. {e}" for i, e in enumerate(errors))
            raise RuntimeError(header + body)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
