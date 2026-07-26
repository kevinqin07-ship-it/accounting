from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class TrialBalanceRow(BaseModel):
    code: str
    name: str
    type: str
    debit: Decimal
    credit: Decimal


class TrialBalanceOut(BaseModel):
    as_of: Optional[date] = None
    rows: List[TrialBalanceRow]
    total_debit: Decimal
    total_credit: Decimal


class ReportLineOut(BaseModel):
    code: str
    name: str
    amount: Decimal


class IncomeStatementOut(BaseModel):
    start: date
    end: date
    revenue: List[ReportLineOut]
    expense: List[ReportLineOut]
    total_revenue: Decimal
    total_expense: Decimal
    net_income: Decimal


class BalanceSheetOut(BaseModel):
    as_of: date
    assets: List[ReportLineOut]
    liabilities: List[ReportLineOut]
    equity: List[ReportLineOut]
    retained_earnings: Decimal
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal


class AgingRowOut(BaseModel):
    party_name: str
    invoice_or_bill_no: str
    issue_date: date
    due_date: date
    total: Decimal
    outstanding: Decimal
    days_past_due: int


class ShipmentPnLOut(BaseModel):
    shipment_no: str
    revenue: Decimal
    cost: Decimal
    margin: Decimal
    margin_pct: float
