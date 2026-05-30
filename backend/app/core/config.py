"""Application configuration loaded from environment variables.

All settings are prefixed with ``QF_`` and can be supplied via the process
environment or a local ``.env`` file (see ``.env.example``).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Default SQLite URL keeps local dev dependency-free.
# Set QF_DATABASE_URL to a PostgreSQL DSN (e.g. postgresql+psycopg2://...)
# when a real database is available.
_DEFAULT_DB_URL = "sqlite+pysqlite:///./quantfidelity.db"


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
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"
    debug: bool = True
    version: str = "0.1.0"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS — comma-separated origins in the env var, parsed to a list.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Database
    # SQLite for local dev / CI (no external service required).
    # PostgreSQL for staging / production: postgresql+psycopg2://user:pass@host/db
    database_url: str = _DEFAULT_DB_URL

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
