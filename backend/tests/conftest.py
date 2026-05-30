"""Pytest fixtures for QuantFidelity backend tests.

All database tests use an in-memory SQLite database with StaticPool so that:
- No external PostgreSQL is required.
- All operations share one connection (avoids SQLite in-memory isolation issues).
- Tables are created once per session and seeded once per session.
- The FastAPI dependency ``get_db`` is overridden to yield the test session.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# Import models before Base so metadata is fully populated.
import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app

_TEST_DB_URL = "sqlite+pysqlite:///:memory:"


@pytest.fixture(scope="session")
def test_engine():
    """Create an in-memory SQLite engine shared for the whole test session."""
    engine = create_engine(
        _TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="session")
def db(test_engine):
    """Single session open for the whole test session (read-mostly)."""
    session = Session(test_engine)
    yield session
    session.close()


@pytest.fixture(scope="session", autouse=True)
def seed_data(db):
    """Seed the test database once before any test runs."""
    from app.services.seed import run_seed

    ids = run_seed(db)
    return ids


@pytest.fixture(scope="session")
def client(db):
    """FastAPI TestClient with get_db overridden to use the test session."""

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
