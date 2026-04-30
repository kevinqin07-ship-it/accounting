"""Pydantic schemas. Money on the wire is Decimal dollars; cents stay
internal to the service layer."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from accounting.money import from_cents


def _dollars(cents: int) -> Decimal:
    return from_cents(cents)


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Accounts ------------------------------------------------------------

class AccountOut(_ORM):
    id: int
    code: str
    name: str
    type: str
    parent_id: Optional[int] = None
    description: Optional[str] = None
    is_active: bool


# --- Parties -------------------------------------------------------------

class CustomerCreate(BaseModel):
    code: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[str] = None
    payment_terms_days: int = 30


class CustomerOut(_ORM):
    id: int
    code: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[str] = None
    payment_terms_days: int


class VendorCreate(BaseModel):
    code: str
    name: str
    category: str = "general"
    email: Optional[str] = None
    phone: Optional[str] = None
    remit_address: Optional[str] = None
    payment_terms_days: int = 30


class VendorOut(_ORM):
    id: int
    code: str
    name: str
    category: str
    email: Optional[str] = None
    phone: Optional[str] = None
    remit_address: Optional[str] = None
    payment_terms_days: int


# --- Shipments -----------------------------------------------------------

class ShipmentCreate(BaseModel):
    shipment_no: str
    customer_id: int
    origin: str
    destination: str
    quoted_revenue: Decimal
    pickup_date: Optional[date] = None
    delivery_date: Optional[date] = None
    weight_lbs: Optional[int] = None
    miles: Optional[int] = None


class ShipmentOut(BaseModel):
    id: int
    shipment_no: str
    customer_id: int
    origin: str
    destination: str
    pickup_date: Optional[date] = None
    delivery_date: Optional[date] = None
    weight_lbs: Optional[int] = None
    miles: Optional[int] = None
    status: str
    quoted_revenue: Decimal

    @classmethod
    def from_model(cls, s) -> "ShipmentOut":
        return cls(
            id=s.id,
            shipment_no=s.shipment_no,
            customer_id=s.customer_id,
            origin=s.origin,
            destination=s.destination,
            pickup_date=s.pickup_date,
            delivery_date=s.delivery_date,
            weight_lbs=s.weight_lbs,
            miles=s.miles,
            status=s.status.value,
            quoted_revenue=_dollars(s.quoted_revenue_cents),
        )


# --- Invoices ------------------------------------------------------------

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


# --- Bills ---------------------------------------------------------------

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


# --- Payments ------------------------------------------------------------

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


# --- Journal -------------------------------------------------------------

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


# --- Reports -------------------------------------------------------------

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


# --- Period close --------------------------------------------------------

class CloseIn(BaseModel):
    close_through: date
    retained_earnings_code: str = "3100"
    note: Optional[str] = None


class CloseOut(BaseModel):
    id: int
    close_through_date: date
    closing_journal_entry_id: Optional[int]
    closed_at: datetime
    note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CloseStatusOut(BaseModel):
    closed_through: Optional[date]


# --- Auth ---------------------------------------------------------------

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
