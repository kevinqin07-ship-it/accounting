from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from ._common import _dollars


class JournalLineIn(BaseModel):
    account_code: str
    debit: Decimal = Field(default=Decimal("0.00"))
    credit: Decimal = Field(default=Decimal("0.00"))
    memo: Optional[str] = None


class JournalEntryIn(BaseModel):
    entry_date: date
    memo: str
    reference: Optional[str] = None
    lines: List[JournalLineIn]


class JournalLineOut(BaseModel):
    id: int
    account_code: str
    debit: Decimal
    credit: Decimal
    memo: Optional[str] = None


class JournalEntryOut(BaseModel):
    id: int
    entry_date: date
    memo: Optional[str] = None
    reference: Optional[str] = None
    posted_at: datetime
    lines: List[JournalLineOut]

    @classmethod
    def from_model(cls, e) -> "JournalEntryOut":
        return cls(
            id=e.id,
            entry_date=e.entry_date,
            memo=e.memo,
            reference=e.reference,
            posted_at=e.posted_at,
            lines=[
                JournalLineOut(
                    id=line.id,
                    account_code=line.account.code,
                    debit=_dollars(line.debit_cents),
                    credit=_dollars(line.credit_cents),
                    memo=line.memo,
                )
                for line in e.lines
            ],
        )
