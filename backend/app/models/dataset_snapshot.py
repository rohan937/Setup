from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class DatasetSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dataset_snapshots"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_label: Mapped[str] = mapped_column(String(100), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 0–100 deterministic health score computed at ingestion time.
    health_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    # Raw ingested rows (list of row dicts).  Stored for auditability.
    rows_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Relationships
    dataset: Mapped["Dataset"] = relationship(  # noqa: F821
        "Dataset", back_populates="snapshots"
    )
    issues: Mapped[list["DataQualityIssue"]] = relationship(  # noqa: F821
        "DataQualityIssue",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by="DataQualityIssue.created_at",
    )
    # M7: strategy runs that are linked to this snapshot.
    strategy_runs: Mapped[list["StrategyRun"]] = relationship(  # noqa: F821
        "StrategyRun",
        back_populates="snapshot",
        foreign_keys="[StrategyRun.dataset_snapshot_id]",
    )

    def __repr__(self) -> str:
        return (
            f"<DatasetSnapshot version={self.version_label!r} "
            f"rows={self.row_count} health={self.health_score}>"
        )
