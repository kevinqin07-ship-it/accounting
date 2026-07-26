from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from ._common import _dollars


class EarningLineIn(BaseModel):
    description: str
    amount: Decimal
    expense_account_code: Optional[str] = None  # defaults from driver type
    shipment_id: Optional[int] = None


class DeductionLineIn(BaseModel):
    description: str
    amount: Decimal
    recovery_account_code: str


class SettlementCreate(BaseModel):
    settlement_no: str
    driver_id: int
    period_start: date
    period_end: date
    issue_date: date
    earnings: List[EarningLineIn]
    deductions: List[DeductionLineIn] = Field(default_factory=list)


class SettlementLineOut(BaseModel):
    id: int
    kind: str
    description: str
    expense_account_code: str
    amount: Decimal
    shipment_id: Optional[int] = None


class SettlementOut(BaseModel):
    id: int
    settlement_no: str
    driver_id: int
    period_start: date
    period_end: date
    issue_date: date
    status: str
    gross: Decimal
    deductions_total: Decimal
    net: Decimal
    lines: List[SettlementLineOut]

    @classmethod
    def from_model(cls, s) -> "SettlementOut":
        return cls(
            id=s.id,
            settlement_no=s.settlement_no,
            driver_id=s.driver_id,
            period_start=s.period_start,
            period_end=s.period_end,
            issue_date=s.issue_date,
            status=s.status.value,
            gross=_dollars(s.gross_cents),
            deductions_total=_dollars(s.deductions_cents),
            net=_dollars(s.net_cents),
            lines=[
                SettlementLineOut(
                    id=line.id,
                    kind=line.kind,
                    description=line.description,
                    expense_account_code=line.expense_account.code,
                    amount=_dollars(line.amount_cents),
                    shipment_id=line.shipment_id,
                )
                for line in s.lines
            ],
        )


class SettlementPayIn(BaseModel):
    payment_date: date
    cash_account_code: str = "1000"
    method: str = "ach"
    reference: Optional[str] = None
