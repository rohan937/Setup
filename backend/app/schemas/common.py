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
