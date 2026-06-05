"""Alert ORM model — M11 Alerts Engine."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import GUIDString, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.strategy import Strategy


class Alert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single alert instance raised by the alerts engine.

    Deduplication: while an alert with the same ``rule_type`` + ``source_type``
    + ``source_id`` is open/acknowledged/snoozed, no duplicate is created.
    Resolved alerts can be re-triggered by a new generation run.
    """

    __tablename__ = "alerts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUIDString(),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="open", index=True
    )
    severity: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # Evidence source that triggered the alert (e.g. "dataset_snapshot", "backtest_audit")
    source_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(String(36), nullable=True)

    # Optional link to the strategy this alert concerns
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        GUIDString(),
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    snoozed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    metadata_json: Mapped[dict | None] = mapped_column(JSON(), nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="alerts")
    strategy: Mapped[Strategy | None] = relationship("Strategy", back_populates="alerts")
