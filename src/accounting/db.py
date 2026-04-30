"""Database engine, session factory, and declarative base."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session as _Session, sessionmaker


class Base(DeclarativeBase):
    pass


def _database_url() -> str:
    return os.environ.get("ACCOUNTING_DB_URL", "sqlite:///accounting.db")


_engine = create_engine(_database_url(), future=True)
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create all tables. Safe to call repeatedly."""
    # Import models so they register with Base.metadata.
    from accounting import models  # noqa: F401

    Base.metadata.create_all(_engine)


def reset_db() -> None:
    """Drop and recreate all tables. Useful for tests and seeding."""
    from accounting import models  # noqa: F401

    Base.metadata.drop_all(_engine)
    Base.metadata.create_all(_engine)


@contextmanager
def Session() -> Iterator[_Session]:
    """Context-managed session that commits on success and rolls back on error."""
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
