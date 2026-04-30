"""Test fixtures: each test gets a freshly migrated SQLite database in tempdir."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def session(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("ACCOUNTING_DB_URL", db_url)

    # Build a dedicated engine + session bound to this URL. We avoid module-
    # level state in accounting.db (which captured the URL at import time)
    # so each test gets a clean database.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from alembic import command
    from alembic.config import Config

    here = Path(__file__).resolve().parents[1]
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()
