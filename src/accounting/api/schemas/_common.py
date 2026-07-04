"""Shared base classes/helpers for the schema modules."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from accounting.money import from_cents


def _dollars(cents: int) -> Decimal:
    return from_cents(cents)


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)
