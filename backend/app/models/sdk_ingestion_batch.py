"""SdkIngestionBatch ORM model — M25 Idempotency / SDK Ingestion Batches."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import GUID as Uuid
from app.models.base import GUIDString

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.api_key import ApiKey
    from app.models.strategy import Strategy


class SdkIngestionBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tracks a single SDK evidence-bundle ingestion request for idempotency.

    The idempotency_key + strategy_id pair is unique. On replay (same key,
    same payload hash) the stored response_json is returned directly without
    re-running ingestion. Retries after failure are allowed.
    """

    __tablename__ = "sdk_ingestion_batches"

    organization_id: Mapped[str | None] = mapped_column(
        GUIDString(),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[str | None] = mapped_column(
        GUIDString(),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="received", index=True
    )
    response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_object_refs_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    strategy: Mapped["Strategy"] = relationship(
        "Strategy", back_populates="sdk_ingestion_batches"
    )
    api_key: Mapped["ApiKey | None"] = relationship(
        "ApiKey", back_populates="sdk_ingestion_batches"
    )

    __table_args__ = (UniqueConstraint("strategy_id", "idempotency_key"),)

    def __repr__(self) -> str:
        return (
            f"<SdkIngestionBatch key={self.idempotency_key!r} status={self.status!r}>"
        )
