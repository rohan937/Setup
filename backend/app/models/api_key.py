"""ApiKey ORM model — M24 API Key Foundation."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.project import Project
    from app.models.sdk_ingestion_batch import SdkIngestionBatch


class ApiKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An API key for SDK / programmatic access to QuantFidelity.

    The raw key is NEVER stored — only a SHA-256 (or HMAC-SHA-256) hash.
    The key_prefix (e.g. ``qf_local_abcd1234``) is safe to display in the UI.
    """

    __tablename__ = "api_keys"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scopes_json: Mapped[list | None] = mapped_column(JSON(), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active", index=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="api_keys"
    )
    project: Mapped["Project | None"] = relationship(
        "Project", back_populates="api_keys"
    )
    # M25: SDK ingestion batches linked to this key.
    sdk_ingestion_batches: Mapped[list["SdkIngestionBatch"]] = relationship(  # noqa: F821
        "SdkIngestionBatch", back_populates="api_key"
    )

    def __repr__(self) -> str:
        return f"<ApiKey prefix={self.key_prefix!r} status={self.status!r}>"
