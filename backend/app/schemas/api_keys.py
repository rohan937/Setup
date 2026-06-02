"""Pydantic schemas for API key management — M24."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApiKeyCreateRequest(BaseModel):
    """Request body for creating a new API key."""

    name: str
    organization_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    scopes: list[str] = ["evidence:write"]


class ApiKeyRead(BaseModel):
    """Safe read representation of an API key — never includes raw key or hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: str
    project_id: str | None
    project_name: str | None = None
    name: str
    key_prefix: str
    scopes_json: list[str] | None
    status: str
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApiKeyCreateResponse(BaseModel):
    """Response for a newly-created API key.

    ``raw_key`` is returned ONCE here and never again.
    """

    api_key: ApiKeyRead
    raw_key: str
    warning: str = "Store this key now. QuantFidelity will not show it again."


class ApiKeyListResponse(BaseModel):
    """Paginated list of API keys."""

    items: list[ApiKeyRead]
    total: int


class ApiKeyRevokeResponse(BaseModel):
    """Confirmation of API key revocation."""

    id: uuid.UUID
    status: str
    revoked_at: datetime
