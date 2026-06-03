"""Shared response schemas for the M1 foundation endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class ApiInfoResponse(BaseModel):
    name: str
    version: str
    environment: str
    api_version: str
    docs_url: str


class DeploymentHealthResponse(BaseModel):
    """M70: lightweight deployment health check — safe to expose publicly.

    Does not include secret values. ``database_reachable`` performs a live
    connection probe so callers can distinguish "URL configured" from
    "database actually reachable".
    """

    status: str
    environment: str
    version: str
    database_configured: bool
    database_reachable: bool
    database_driver: str
    migrations_note: str
    auth_enabled: bool
    rbac_enabled: bool
    cors_configured: bool
    # True when running in production with an unsafe (dev-default) JWT secret.
    # Never exposes the secret itself.
    jwt_secret_safe: bool
    # Production-safety note for operators.
    production_warnings: list[str]
