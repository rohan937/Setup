from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import GUID as Uuid

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_projects_org_slug"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship(  # noqa: F821
        "Organization", back_populates="projects"
    )
    strategies: Mapped[list["Strategy"]] = relationship(  # noqa: F821
        "Strategy", back_populates="project", cascade="all, delete-orphan"
    )
    datasets: Mapped[list["Dataset"]] = relationship(  # noqa: F821
        "Dataset", back_populates="project", cascade="all, delete-orphan"
    )
    audit_timeline_events: Mapped[list["AuditTimelineEvent"]] = relationship(  # noqa: F821
        "AuditTimelineEvent", back_populates="project"
    )
    reports: Mapped[list["Report"]] = relationship(  # noqa: F821
        "Report", back_populates="project"
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(  # noqa: F821
        "ApiKey", back_populates="project"
    )

    def __repr__(self) -> str:
        return f"<Project slug={self.slug!r}>"
