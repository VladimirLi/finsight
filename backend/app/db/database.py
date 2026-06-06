"""SQLAlchemy engine / session setup."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


def get_db() -> Iterator[Session]:
    """Yield a database session and ensure it is closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables for the dev/SQLite path.

    This is the convenience bootstrap used in development and tests. The
    production / docker-compose path instead runs ``alembic upgrade head`` so
    schema changes are versioned and reviewable.
    """
    from app.db import (
        models,  # noqa: F401  # pyright: ignore[reportUnusedImport]  (register models via side-effect)
    )

    Base.metadata.create_all(bind=engine)
