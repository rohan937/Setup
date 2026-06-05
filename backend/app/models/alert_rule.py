"""AlertRule ORM model — M11 Alerts Engine."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import GUIDString, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization


class AlertRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A configured rule that the alert-generation service evaluates.

    Rules are organisation-scoped.  ``threshold`` is an integer (0-100) used
    by score-based rules; other rule types may store extra config in
    ``config_json``.
    """

    __tablename__ = "alert_rules"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUIDString(),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    threshold: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    config_json: Mapped[dict | None] = mapped_column(JSON(), nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="alert_rules")
