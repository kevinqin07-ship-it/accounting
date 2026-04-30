"""API key creation, validation, and revocation."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.models import ApiKey, ApiKeyRole


def hash_key(raw: str) -> str:
    """sha256 of the raw key. Sufficient for high-entropy random tokens —
    we don't need bcrypt-style cost since these aren't user-chosen passwords."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class IssuedKey:
    api_key: ApiKey
    raw_key: str  # only returned once at creation time


def create_key(session: Session, *, name: str, role: ApiKeyRole) -> IssuedKey:
    raw = secrets.token_urlsafe(32)
    api_key = ApiKey(name=name, key_hash=hash_key(raw), role=role)
    session.add(api_key)
    session.flush()
    return IssuedKey(api_key=api_key, raw_key=raw)


def validate(session: Session, raw: str) -> Optional[ApiKey]:
    """Look up an active key by raw token. Updates last_used_at on hit."""
    if not raw:
        return None
    api_key = session.scalar(
        select(ApiKey).where(ApiKey.key_hash == hash_key(raw))
    )
    if api_key is None or api_key.revoked_at is not None:
        return None
    api_key.last_used_at = datetime.utcnow()
    session.flush()
    return api_key


def list_keys(session: Session, *, include_revoked: bool = False) -> List[ApiKey]:
    stmt = select(ApiKey).order_by(ApiKey.id)
    if not include_revoked:
        stmt = stmt.where(ApiKey.revoked_at.is_(None))
    return list(session.scalars(stmt))


def revoke(session: Session, key_id: int) -> ApiKey:
    api_key = session.get(ApiKey, key_id)
    if api_key is None:
        raise LookupError(f"API key {key_id} not found.")
    if api_key.revoked_at is not None:
        return api_key
    api_key.revoked_at = datetime.utcnow()
    session.flush()
    return api_key
