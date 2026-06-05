from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class ProjectCreate(BaseModel):
    """Request body for creating a project.

    ``organization_id`` is optional: when omitted the server resolves the
    default (earliest) organization, matching the single-workspace product.
    """

    name: str
    slug: str | None = None
    description: str | None = None
    organization_id: uuid.UUID | None = None
