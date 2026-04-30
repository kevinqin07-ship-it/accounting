"""FastAPI dependencies."""

from __future__ import annotations

from typing import Iterator

from sqlalchemy.orm import Session

from accounting import db


def get_session() -> Iterator[Session]:
    """Yields a session, commits on success, rolls back on exception.

    Looks up the session factory at call time so tests that rebind the
    engine after import (via accounting.db.rebind()) take effect."""
    s = db.make_session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
