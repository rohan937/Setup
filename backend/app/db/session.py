"""Database engine and session factory.

The engine is built lazily from the application settings so that tests can
substitute a different URL before the first import. ``get_db`` is the FastAPI
dependency that yields a session per request and rolls back on exception.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

# Module-level engine and session factory, created once.
# Tests override by patching the dependency directly (see tests/conftest.py).
def _build_engine():
    settings = get_settings()
    kwargs: dict = {}
    if settings.is_sqlite:
        # SQLite needs check_same_thread disabled for use across FastAPI threads.
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(settings.database_url, **kwargs)


engine = _build_engine()

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _enable_sqlite_fk(dbapi_connection, _connection_record) -> None:
    """Enable foreign key enforcement for SQLite connections."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Attach the FK enforcement listener only when using SQLite.
if get_settings().is_sqlite:
    event.listen(engine, "connect", _enable_sqlite_fk)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a database session, close on exit."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
