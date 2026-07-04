from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from ._common import _dollars


class PaymentReceiveIn(BaseModel):
    invoice_id: int
    payment_date: date
    amount: Decimal
    method: str = "ach"
    reference: Optional[str] = None
    cash_account_code: str = "1000"


class PaymentSendIn(BaseModel):
    bill_id: int
    payment_date: date
    amount: Decimal
    method: str = "ach"
    reference: Optional[str] = None
    cash_account_code: str = "1000"


class PaymentOut(BaseModel):
    id: int
    direction: str
    payment_date: date
    amount: Decimal
    method: str
    reference: Optional[str] = None
    invoice_id: Optional[int] = None
    bill_id: Optional[int] = None

    @classmethod
    def from_model(cls, p) -> "PaymentOut":
        return cls(
            id=p.id,
            direction=p.direction.value,
            payment_date=p.payment_date,
            amount=_dollars(p.amount_cents),
            method=p.method,
            reference=p.reference,
            invoice_id=p.invoice_id,
            bill_id=p.bill_id,
        )
