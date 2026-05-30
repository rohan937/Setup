from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class StrategyVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "strategy_versions"

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_label: Mapped[str] = mapped_column(String(100), nullable=False)
    git_commit: Mapped[str | None] = mapped_column(String(255), nullable=True)
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    code_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    signal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signal_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    strategy: Mapped["Strategy"] = relationship(  # noqa: F821
        "Strategy", back_populates="versions"
    )
    runs: Mapped[list["StrategyRun"]] = relationship(  # noqa: F821
        "StrategyRun", back_populates="strategy_version"
    )

    def __repr__(self) -> str:
        return f"<StrategyVersion label={self.version_label!r}>"
