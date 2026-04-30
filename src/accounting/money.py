"""Money helpers. Amounts are stored as integer cents to avoid float drift."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Union

Number = Union[int, float, str, Decimal]


def to_cents(amount: Number) -> int:
    """Convert a dollar amount to integer cents using banker-safe rounding."""
    if isinstance(amount, int) and not isinstance(amount, bool):
        return amount * 100
    quantized = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(quantized * 100)


def from_cents(cents: int) -> Decimal:
    """Convert integer cents back to a Decimal dollar amount."""
    return (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))


def fmt(cents: int) -> str:
    """Format integer cents as a human-readable currency string."""
    sign = "-" if cents < 0 else ""
    dollars = from_cents(abs(cents))
    return f"{sign}${dollars:,.2f}"
