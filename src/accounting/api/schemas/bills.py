from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel

from ._common import _dollars


class BillLineIn(BaseModel):
    description: str
    expense_account_code: str
    amount: Decimal


class BillCreate(BaseModel):
    bill_no: str
    vendor_id: int
    issue_date: date
    lines: List[BillLineIn]
    shipment_id: Optional[int] = None
    due_date: Optional[date] = None


class BillLineOut(BaseModel):
    id: int
    description: str
    expense_account_code: str
    amount: Decimal


class BillOut(BaseModel):
    id: int
    bill_no: str
    vendor_id: int
    shipment_id: Optional[int] = None
    issue_date: date
    due_date: date
    status: str
    total: Decimal
    lines: List[BillLineOut]

    @classmethod
    def from_model(cls, bill) -> "BillOut":
        return cls(
            id=bill.id,
            bill_no=bill.bill_no,
            vendor_id=bill.vendor_id,
            shipment_id=bill.shipment_id,
            issue_date=bill.issue_date,
            due_date=bill.due_date,
            status=bill.status.value,
            total=_dollars(bill.total_cents),
            lines=[
                BillLineOut(
                    id=line.id,
                    description=line.description,
                    expense_account_code=line.expense_account.code,
                    amount=_dollars(line.amount_cents),
                )
                for line in bill.lines
            ],
        )
