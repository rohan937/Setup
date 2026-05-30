"""Application configuration loaded from environment variables.

All settings are prefixed with ``QF_`` and can be supplied via the process
environment or a local ``.env`` file (see ``.env.example``). No product or
database logic lives here in M1 — this is purely the config surface that later
milestones build on.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Database (PostgreSQL-ready; unused in M1).
    database_url: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
