from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Strategy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "strategies"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # See constants.AssetClass for valid values.
    asset_class: Mapped[str] = mapped_column(
        String(50), nullable=False, default="equity"
    )
    # See constants.StrategyStatus for valid values.
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active"
    )

    # Relationships
    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="strategies"
    )
    versions: Mapped[list["StrategyVersion"]] = relationship(  # noqa: F821
        "StrategyVersion",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyVersion.created_at",
    )
    runs: Mapped[list["StrategyRun"]] = relationship(  # noqa: F821
        "StrategyRun",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyRun.created_at",
    )
    audit_timeline_events: Mapped[list["AuditTimelineEvent"]] = relationship(  # noqa: F821
        "AuditTimelineEvent", back_populates="strategy"
    )
    alerts: Mapped[list["Alert"]] = relationship(  # noqa: F821
        "Alert", back_populates="strategy"
    )

    def __repr__(self) -> str:
        return f"<Strategy slug={self.slug!r} status={self.status!r}>"
