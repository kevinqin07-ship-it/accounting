"""API key authentication."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from accounting.db import Base


class ApiKeyRole(str, enum.Enum):
    ADMIN = "admin"
    BOOKKEEPER = "bookkeeper"
    READONLY = "readonly"


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("key_hash", name="uq_api_key_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    key_hash: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[ApiKeyRole] = mapped_column(Enum(ApiKeyRole))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None
