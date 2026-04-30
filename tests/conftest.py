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
def admin_key(session) -> str:
    """Create an admin API key in the test database and return the raw token."""
    from accounting.models import ApiKeyRole
    from accounting.services import auth as auth_svc

    issued = auth_svc.create_key(session, name="test-admin", role=ApiKeyRole.ADMIN)
    session.commit()
    return issued.raw_key


@pytest.fixture
def readonly_key(session) -> str:
    from accounting.models import ApiKeyRole
    from accounting.services import auth as auth_svc

    issued = auth_svc.create_key(session, name="test-ro", role=ApiKeyRole.READONLY)
    session.commit()
    return issued.raw_key


@pytest.fixture
def client(session, admin_key):
    """A FastAPI TestClient pre-authenticated as admin against the same
    database the `session` fixture uses. Tests that need to verify auth
    behavior should use `unauthed_client`."""
    from fastapi.testclient import TestClient
    from accounting.api.app import create_app

    c = TestClient(create_app())
    c.headers["Authorization"] = f"Bearer {admin_key}"
    return c


@pytest.fixture
def unauthed_client(session):
    """A FastAPI TestClient with no auth header set."""
    from fastapi.testclient import TestClient
    from accounting.api.app import create_app

    return TestClient(create_app())
