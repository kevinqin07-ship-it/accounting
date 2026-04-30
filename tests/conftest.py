"""Test fixtures: an isolated in-memory SQLite engine for each test."""

from __future__ import annotations

import os

# Force in-memory SQLite before importing any module that creates the engine.
os.environ["ACCOUNTING_DB_URL"] = "sqlite:///:memory:"

import pytest
from sqlalchemy.orm import sessionmaker

from accounting import db as db_module
from accounting.db import Base


@pytest.fixture
def session():
    Base.metadata.drop_all(db_module._engine)
    # Importing models registers them on Base.metadata.
    from accounting import models  # noqa: F401

    Base.metadata.create_all(db_module._engine)
    SessionLocal = sessionmaker(bind=db_module._engine, autoflush=False, expire_on_commit=False)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
