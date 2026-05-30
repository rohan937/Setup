"""SQLAlchemy declarative base.

All ORM models import Base from here. The single Base instance is also used
by Alembic's autogenerate and by test fixtures that call create_all().
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all QuantFidelity models."""
    pass
