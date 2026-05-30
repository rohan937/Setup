"""Database layer: engine, session, and declarative base.

Public re-exports so callers can do ``from app.db import Base, get_db``.
"""

from app.db.base import Base
from app.db.session import SessionLocal, engine, get_db

__all__ = ["Base", "engine", "SessionLocal", "get_db"]
