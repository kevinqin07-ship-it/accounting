from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ApiKeyCreate(BaseModel):
    name: str
    role: str


class ApiKeyOut(BaseModel):
    id: int
    name: str
    role: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class ApiKeyIssued(ApiKeyOut):
    raw_key: str  # returned once at creation time


class LoginIn(BaseModel):
    key: str
