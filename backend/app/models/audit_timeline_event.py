from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import GUID as Uuid

from app.db.base import Base
from app.models.base import UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditTimelineEvent(UUIDPrimaryKeyMixin, Base):
    """Chronological audit record generated from underlying objects.

    Does not carry ``updated_at`` — events are append-only and immutable.
    """

    __tablename__ = "audit_timeline_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # See constants.EventType for valid values.
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # See constants.Severity for valid values.
    severity: Mapped[str] = mapped_column(
        String(50), nullable=False, default="info"
    )
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(  # noqa: F821
        "Organization", back_populates="audit_timeline_events"
    )
    project: Mapped["Project | None"] = relationship(  # noqa: F821
        "Project", back_populates="audit_timeline_events"
    )
    strategy: Mapped["Strategy | None"] = relationship(  # noqa: F821
        "Strategy", back_populates="audit_timeline_events"
    )

    def __repr__(self) -> str:
        return f"<AuditTimelineEvent type={self.event_type!r} title={self.title!r}>"
