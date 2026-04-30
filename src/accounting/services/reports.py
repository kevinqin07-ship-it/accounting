"""Financial reports: trial balance, P&L, balance sheet, AR/AP aging, shipment P&L."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.models import (
    Account,
    AccountType,
    Bill,
    BillStatus,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    JournalEntry,
    JournalLine,
    Shipment,
)
from accounting.services import ledger
from accounting.services.billing import amount_outstanding as bill_outstanding
from accounting.services.invoicing import amount_outstanding as inv_outstanding


@dataclass
class ReportLine:
    account: Account
    amount_cents: int


@dataclass
class IncomeStatement:
    start: date
    end: date
    revenue: List[ReportLine] = field(default_factory=list)
    expense: List[ReportLine] = field(default_factory=list)

    @property
    def total_revenue(self) -> int:
        return sum(line.amount_cents for line in self.revenue)

    @property
    def total_expense(self) -> int:
        return sum(line.amount_cents for line in self.expense)

    @property
    def net_income(self) -> int:
        return self.total_revenue - self.total_expense


@dataclass
class BalanceSheet:
    as_of: date
    assets: List[ReportLine] = field(default_factory=list)
    liabilities: List[ReportLine] = field(default_factory=list)
    equity: List[ReportLine] = field(default_factory=list)
    retained_earnings: int = 0

    @property
    def total_assets(self) -> int:
        return sum(line.amount_cents for line in self.assets)

    @property
    def total_liabilities(self) -> int:
        return sum(line.amount_cents for line in self.liabilities)

    @property
    def total_equity(self) -> int:
        return sum(line.amount_cents for line in self.equity) + self.retained_earnings


def income_statement(session: Session, start: date, end: date) -> IncomeStatement:
    """Activity in revenue and expense accounts between start and end (inclusive)."""
    statement = IncomeStatement(start=start, end=end)
    accounts = session.scalars(
        select(Account)
        .where(Account.type.in_([AccountType.REVENUE, AccountType.EXPENSE]))
        .order_by(Account.code)
    ).all()
    for account in accounts:
        rows = session.scalars(
            select(JournalLine)
            .join(JournalEntry)
            .where(
                JournalLine.account_id == account.id,
                JournalEntry.entry_date >= start,
                JournalEntry.entry_date <= end,
            )
        ).all()
        debit = sum(r.debit_cents for r in rows)
        credit = sum(r.credit_cents for r in rows)
        if account.type == AccountType.REVENUE:
            amount = credit - debit  # revenue increases on credit
            if amount:
                statement.revenue.append(ReportLine(account=account, amount_cents=amount))
        else:
            amount = debit - credit  # expense increases on debit
            if amount:
                statement.expense.append(ReportLine(account=account, amount_cents=amount))
    return statement


def balance_sheet(session: Session, as_of: date) -> BalanceSheet:
    sheet = BalanceSheet(as_of=as_of)
    accounts = session.scalars(
        select(Account)
        .where(Account.type.in_([AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY]))
        .order_by(Account.code)
    ).all()
    for account in accounts:
        bal = ledger.account_balance(session, account.code, as_of=as_of)
        if bal == 0:
            continue
        line = ReportLine(account=account, amount_cents=bal)
        if account.type == AccountType.ASSET:
            sheet.assets.append(line)
        elif account.type == AccountType.LIABILITY:
            sheet.liabilities.append(line)
        else:
            sheet.equity.append(line)

    # Retained earnings from cumulative net income (not yet closed to equity).
    # Accumulate revenue minus expense across all time up to as_of.
    cumulative = income_statement(session, date(1900, 1, 1), as_of)
    sheet.retained_earnings = cumulative.net_income
    return sheet


@dataclass
class AgingBucket:
    label: str
    amount_cents: int = 0


@dataclass
class AgingRow:
    party_name: str
    invoice_or_bill_no: str
    issue_date: date
    due_date: date
    total_cents: int
    outstanding_cents: int
    days_past_due: int


def ar_aging(session: Session, as_of: Optional[date] = None) -> List[AgingRow]:
    today = as_of or date.today()
    rows: List[AgingRow] = []
    invoices = session.scalars(
        select(Invoice).where(Invoice.status.in_([InvoiceStatus.OPEN, InvoiceStatus.PARTIAL]))
    )
    for inv in invoices:
        outstanding = inv_outstanding(session, inv)
        if outstanding <= 0:
            continue
        rows.append(
            AgingRow(
                party_name=inv.customer.name,
                invoice_or_bill_no=inv.invoice_no,
                issue_date=inv.issue_date,
                due_date=inv.due_date,
                total_cents=inv.total_cents,
                outstanding_cents=outstanding,
                days_past_due=max((today - inv.due_date).days, 0),
            )
        )
    return rows


def ap_aging(session: Session, as_of: Optional[date] = None) -> List[AgingRow]:
    today = as_of or date.today()
    rows: List[AgingRow] = []
    bills = session.scalars(
        select(Bill).where(Bill.status.in_([BillStatus.OPEN, BillStatus.PARTIAL]))
    )
    for bill in bills:
        outstanding = bill_outstanding(session, bill)
        if outstanding <= 0:
            continue
        rows.append(
            AgingRow(
                party_name=bill.vendor.name,
                invoice_or_bill_no=bill.bill_no,
                issue_date=bill.issue_date,
                due_date=bill.due_date,
                total_cents=bill.total_cents,
                outstanding_cents=outstanding,
                days_past_due=max((today - bill.due_date).days, 0),
            )
        )
    return rows


@dataclass
class ShipmentPnL:
    shipment: Shipment
    revenue_cents: int
    cost_cents: int

    @property
    def margin_cents(self) -> int:
        return self.revenue_cents - self.cost_cents

    @property
    def margin_pct(self) -> float:
        if self.revenue_cents == 0:
            return 0.0
        return self.margin_cents / self.revenue_cents


def shipment_pnl(session: Session, shipment: Shipment) -> ShipmentPnL:
    """Sum invoice revenue and bill costs that reference the given shipment."""
    revenue = sum(
        line.amount_cents
        for line in session.scalars(
            select(InvoiceLine).join(Invoice).where(Invoice.shipment_id == shipment.id)
        )
    )
    cost = 0
    for bill in session.scalars(select(Bill).where(Bill.shipment_id == shipment.id)):
        cost += bill.total_cents
    return ShipmentPnL(shipment=shipment, revenue_cents=revenue, cost_cents=cost)
