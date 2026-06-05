"""ORM model for universe snapshots (M16)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.models.base import GUID as Uuid

from app.db.base import Base


class UniverseSnapshot(Base):
    __tablename__ = "universe_snapshots"

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

    # Normalized (sorted, uppercased, deduped) symbol list stored as JSON array.
    symbols_json: Mapped[list] = mapped_column(JSON, nullable=False)
    symbol_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Optional metadata: universe_type, liquidity_filter, rebalance_freq, etc.
    # No analytics computed here — stored verbatim.
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Deterministic SHA-256 hex of (sorted symbols + optional metadata). 64 chars.
    universe_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # M39: Universe coverage analysis JSON columns.
    coverage_analysis_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    symbol_quality_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    universe_delta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    universe_quality_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

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
        "Strategy", back_populates="universe_snapshots"
    )
    strategy_version: Mapped["StrategyVersion | None"] = relationship(  # noqa: F821
        "StrategyVersion", back_populates="universe_snapshots"
    )
    # Runs that reference this universe snapshot.
    strategy_runs: Mapped[list["StrategyRun"]] = relationship(  # noqa: F821
        "StrategyRun",
        back_populates="universe_snapshot",
        foreign_keys="[StrategyRun.universe_snapshot_id]",
    )
    # M17: signal snapshots linked to this universe snapshot.
    signal_snapshots: Mapped[list["SignalSnapshot"]] = relationship(  # noqa: F821
        "SignalSnapshot",
        back_populates="universe_snapshot",
        order_by="SignalSnapshot.created_at.desc()",
    )

    def __repr__(self) -> str:
        return (
            f"<UniverseSnapshot label={self.label!r} "
            f"symbols={self.symbol_count} hash={self.universe_hash[:8]}>"
        )
