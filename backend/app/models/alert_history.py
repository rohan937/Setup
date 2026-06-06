"""AlertHistory ORM model — M85 Alert Lifecycle."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import GUIDString, UUIDPrimaryKeyMixin, _utcnow


class AlertHistory(UUIDPrimaryKeyMixin, Base):
    """An immutable audit-log entry for a lifecycle action taken on an alert.

    ``actor_user_id`` is ``str(auth_user.id)`` of whoever performed the action,
    or ``None`` for system / automatic transitions (e.g. ``auto_resolved`` or
    ``snooze_expired``).  ``action`` is one of the values in ``AlertAction``.
    """

    __tablename__ = "alert_history"

    alert_id: Mapped[str] = mapped_column(
        GUIDString(),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
