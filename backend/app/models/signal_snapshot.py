"""ORM model for signal snapshots (M17)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.models.base import GUID as Uuid

from app.db.base import Base


class SignalSnapshot(Base):
    __tablename__ = "signal_snapshots"

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
    universe_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("universe_snapshots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    signal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="manual_json"
    )
    source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Signal rows stored verbatim as a JSON array of objects.
    rows_json: Mapped[list] = mapped_column(JSON, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    symbol_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Sorted distinct symbol strings.
    symbols_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    min_timestamp: Mapped[str | None] = mapped_column(String(100), nullable=True)
    max_timestamp: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Signal statistics.
    signal_value_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mean_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    stddev_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Deterministic SHA-256 hex of (sorted rows + optional metadata). 64 chars.
    signal_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    quality_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    # Optional metadata dict; stored verbatim.
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # M38: Signal quality drilldown JSON fields.
    signal_distribution_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    symbol_quality_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    signal_row_quality_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    signal_quality_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

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
        "Strategy", back_populates="signal_snapshots"
    )
    strategy_version: Mapped["StrategyVersion | None"] = relationship(  # noqa: F821
        "StrategyVersion", back_populates="signal_snapshots"
    )
    universe_snapshot: Mapped["UniverseSnapshot | None"] = relationship(  # noqa: F821
        "UniverseSnapshot", back_populates="signal_snapshots"
    )
    strategy_runs: Mapped[list["StrategyRun"]] = relationship(  # noqa: F821
        "StrategyRun",
        back_populates="signal_snapshot",
        foreign_keys="[StrategyRun.signal_snapshot_id]",
    )

    def __repr__(self) -> str:
        return (
            f"<SignalSnapshot label={self.label!r} "
            f"rows={self.row_count} quality={self.quality_score}>"
        )
