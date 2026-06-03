"""Pydantic schemas for M68 auth endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class UserRegisterRequest(BaseModel):
    email: str
    display_name: str
    password: str


class UserLoginRequest(BaseModel):
    email: str
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str
    status: str
    is_superuser: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id(cls, v: Any) -> str:
        return str(v)


class CurrentUserWorkspaceMembership(BaseModel):
    member_id: str
    organization_id: str
    workspace_name: str
    role: str
    status: str
    linked: bool


class CurrentUserResponse(BaseModel):
    user: UserRead
    workspace_memberships: list[CurrentUserWorkspaceMembership] = []


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class AuthStatusResponse(BaseModel):
    auth_enabled: bool
    has_users: bool
    registration_enabled: bool
