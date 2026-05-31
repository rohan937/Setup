from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Dataset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datasets"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # See constants.DatasetType for valid values.  Defaults to ohlcv.
    dataset_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="ohlcv"
    )
    # See constants.DatasetSourceType for valid values.  Defaults to manual.
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual"
    )

    # Relationships
    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="datasets"
    )
    snapshots: Mapped[list["DatasetSnapshot"]] = relationship(  # noqa: F821
        "DatasetSnapshot",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetSnapshot.created_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<Dataset name={self.name!r} type={self.dataset_type!r}>"
