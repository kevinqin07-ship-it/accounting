"""Database engine, session factory, and declarative base."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session as _Session, sessionmaker


class Base(DeclarativeBase):
    pass


def _database_url() -> str:
    return os.environ.get("ACCOUNTING_DB_URL", "sqlite:///accounting.db")


_engine = create_engine(_database_url(), future=True)
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, future=True)


def _alembic_config():
    """Build an Alembic Config pointing at this project's alembic.ini.

    Imported lazily so the rest of the package doesn't pay the cost when
    callers only want a session.
    """
    from alembic.config import Config

    here = Path(__file__).resolve().parents[2]
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _database_url())
    return cfg


def init_db() -> None:
    """Bring the database schema up to head via Alembic. Idempotent."""
    from alembic import command

    # Importing models registers them on Base.metadata so any code that
    # introspects metadata after init_db sees the full schema.
    from accounting import models  # noqa: F401

    command.upgrade(_alembic_config(), "head")


def reset_db() -> None:
    """Drop everything and run migrations from scratch. Test/dev use only."""
    from alembic import command

    from accounting import models  # noqa: F401

    Base.metadata.drop_all(_engine)
    # In case the alembic version table survived (it's not in our metadata).
    with _engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    command.upgrade(_alembic_config(), "head")


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
