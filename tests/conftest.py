"""Test fixtures: each test gets a freshly migrated SQLite database in tempdir."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def session(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("ACCOUNTING_DB_URL", db_url)

    # Rebind the package-level engine so any code path (CLI, API, services)
    # using accounting.db hits this test's database.
    from accounting import db
    db.rebind()

    from alembic import command
    from alembic.config import Config

    here = Path(__file__).resolve().parents[1]
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

    s = db.make_session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(session):
    """A FastAPI TestClient wired to the same database as the `session`
    fixture. Tests can call HTTP endpoints and verify state with `session`."""
    from fastapi.testclient import TestClient
    from accounting.api.app import create_app

    return TestClient(create_app())
