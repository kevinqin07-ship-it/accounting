from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel

from ._common import _dollars


class InvoiceLineIn(BaseModel):
    description: str
    revenue_account_code: str
    amount: Decimal


class InvoiceCreate(BaseModel):
    invoice_no: str
    customer_id: int
    issue_date: date
    lines: List[InvoiceLineIn]
    shipment_id: Optional[int] = None
    due_date: Optional[date] = None


class InvoiceLineOut(BaseModel):
    id: int
    description: str
    revenue_account_code: str
    amount: Decimal


class InvoiceOut(BaseModel):
    id: int
    invoice_no: str
    customer_id: int
    shipment_id: Optional[int] = None
    issue_date: date
    due_date: date
    status: str
    total: Decimal
    lines: List[InvoiceLineOut]

    @classmethod
    def from_model(cls, inv) -> "InvoiceOut":
        return cls(
            id=inv.id,
            invoice_no=inv.invoice_no,
            customer_id=inv.customer_id,
            shipment_id=inv.shipment_id,
            issue_date=inv.issue_date,
            due_date=inv.due_date,
            status=inv.status.value,
            total=_dollars(inv.total_cents),
            lines=[
                InvoiceLineOut(
                    id=line.id,
                    description=line.description,
                    revenue_account_code=line.revenue_account.code,
                    amount=_dollars(line.amount_cents),
                )
                for line in inv.lines
            ],
        )
