"""Shared model mixins and column types used across all ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GUID(TypeDecorator):
    """UUID column stored as a VARCHAR string on every backend.

    **Why this exists.** All Alembic migrations create id / FK columns as
    ``sa.String(36)`` (``VARCHAR`` on PostgreSQL).  The ORM, however, used
    ``sqlalchemy.types.Uuid(as_uuid=True)``.  On PostgreSQL that type treats the
    column as the *native* ``UUID`` type and casts every bind parameter, e.g.::

        UPDATE auth_users SET ... WHERE auth_users.id = %(id)s::UUID

    Because the real column is ``VARCHAR``, PostgreSQL rejects the comparison
    with ``operator does not exist: character varying = uuid`` → HTTP 500.  It
    happened to work on SQLite (no native UUID type, no strict typing).

    ``GUID`` is a drop-in replacement that renders as ``String(36)`` on *every*
    dialect, so it NEVER emits a ``::UUID`` cast.  To stay byte-compatible with
    data already written by the old ``Uuid`` type, the stored string format is
    chosen per dialect:

    * **SQLite**     → ``uuid.hex``  (32-char, no hyphens) — what the old
      ``Uuid`` non-native path wrote.
    * **PostgreSQL** → ``str(uuid)`` (36-char hyphenated) — what psycopg2's
      implicit ``uuid → text`` assignment cast wrote into the VARCHAR column.

    The Python side always returns ``uuid.UUID`` objects, so calling code that
    treats ids as UUIDs (``str(user.id)``, ``uuid.UUID(sub) == user.id``, …) is
    unchanged.  Binds accept either ``uuid.UUID`` or ``str``.

    This mirrors the per-dialect logic in
    ``app.services.auth_users._uuid_to_fk_str`` used by the ``String(36)`` FK
    columns, so PK and FK formats stay consistent on both dialects.
    """

    impl = String(36)
    cache_ok = True

    def __init__(self, *args, **kwargs):
        # Accept and ignore ``Uuid``-style kwargs (``as_uuid``, ``native_uuid``)
        # so this is a drop-in import swap for ``sqlalchemy.types.Uuid``.
        super().__init__()

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            try:
                value = uuid.UUID(str(value))
            except (ValueError, AttributeError, TypeError):
                # Not a UUID — store the raw string so callers can still filter
                # on non-UUID sentinel values without raising.
                return str(value)
        return value.hex if dialect.name == "sqlite" else str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(value)
        except (ValueError, AttributeError, TypeError):
            return value


class GUIDString(GUID):
    """A ``GUID`` whose Python value is the stored VARCHAR **string**.

    Used for foreign-key columns that reference a ``GUID`` primary key but are
    exposed as plain ``str`` in API schemas (e.g. ``ApiKeyRead.organization_id``)
    and populated as strings by service code (via ``_uuid_to_fk_str``).

    Binding behaves exactly like ``GUID``: it accepts a ``uuid.UUID`` *or* a
    ``str`` and emits the dialect-correct string with **no** ``::UUID`` cast.
    This matters for ORM relationship loads (selectin / lazy / joined): the
    parent key value is a ``uuid.UUID`` and SQLAlchemy binds it against this FK
    column, so without per-dialect string conversion the load would fail with
    ``type 'UUID' is not supported`` (SQLite) or an un-adaptable ``UUID``
    (psycopg2 / PostgreSQL).

    Reading returns the raw stored string unchanged, preserving backward
    compatibility with ``str``-typed Pydantic schemas and equality checks that
    compare against the literal stored value.
    """

    cache_ok = True

    def process_result_value(self, value, dialect):
        # Already a VARCHAR string in the DB — keep it as-is so str-typed
        # schemas and stored-value comparisons continue to work.
        return value


class UUIDPrimaryKeyMixin:
    """Adds a UUID primary key column ``id`` (stored as VARCHAR, see ``GUID``)."""

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` timestamp columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
