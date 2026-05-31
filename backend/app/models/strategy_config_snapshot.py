"""ORM model for strategy config snapshots (M15)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.db.base import Base


class StrategyConfigSnapshot(Base):
    __tablename__ = "strategy_config_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    strategy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategy_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="manual_json"
    )
    source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Deterministic SHA-256 hex of normalised config_json (sort_keys=True).
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    param_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assumption_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    strategy: Mapped["Strategy"] = relationship(  # noqa: F821
        "Strategy", back_populates="config_snapshots"
    )
    strategy_version: Mapped["StrategyVersion | None"] = relationship(  # noqa: F821
        "StrategyVersion", back_populates="config_snapshots"
    )

    def __repr__(self) -> str:
        return f"<StrategyConfigSnapshot label={self.label!r} hash={self.config_hash[:8]}>"
