"""Vendor bills. Posts Expense / AP journal entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Sequence

from sqlalchemy.orm import Session

from accounting.chart_of_accounts import Codes
from accounting.money import Number, to_cents
from accounting.models import Bill, BillLine, BillStatus, Shipment, Vendor
from accounting.services import ledger
from accounting.services.ledger import LineSpec


@dataclass
class BillLineInput:
    description: str
    expense_account_code: str
    amount: Number


def create_bill(
    session: Session,
    *,
    bill_no: str,
    vendor: Vendor,
    issue_date: date,
    lines: Sequence[BillLineInput],
    shipment: Optional[Shipment] = None,
    due_date: Optional[date] = None,
) -> Bill:
    if not lines:
        raise ValueError("A bill needs at least one line.")
    due = due_date or (issue_date + timedelta(days=vendor.payment_terms_days))

    bill = Bill(
        bill_no=bill_no,
        vendor_id=vendor.id,
        shipment_id=shipment.id if shipment else None,
        issue_date=issue_date,
        due_date=due,
        status=BillStatus.DRAFT,
    )
    for line in lines:
        expense_account = ledger.get_account(session, line.expense_account_code)
        bill.lines.append(
            BillLine(
                description=line.description,
                expense_account_id=expense_account.id,
                amount_cents=to_cents(line.amount),
            )
        )
    session.add(bill)
    session.flush()
    return bill


def approve_bill(session: Session, bill: Bill) -> Bill:
    """Post the journal entry: debit expenses, credit AP."""
    if bill.status != BillStatus.DRAFT:
        raise ValueError(f"Bill {bill.bill_no} is not in DRAFT (status={bill.status}).")
    if bill.total_cents <= 0:
        raise ValueError("Cannot approve a bill with non-positive total.")

    entry_lines: List[LineSpec] = []
    for line in bill.lines:
        entry_lines.append(
            LineSpec(
                account_code=line.expense_account.code,
                debit_cents=line.amount_cents,
                memo=line.description,
            )
        )
    entry_lines.append(
        LineSpec(
            account_code=Codes.ACCOUNTS_PAYABLE,
            credit_cents=bill.total_cents,
            memo=f"AP - Bill {bill.bill_no}",
        )
    )
    entry = ledger.post_entry(
        session,
        entry_date=bill.issue_date,
        memo=f"Bill {bill.bill_no}",
        reference=f"BILL:{bill.bill_no}",
        lines=entry_lines,
    )
    bill.journal_entry_id = entry.id
    bill.status = BillStatus.OPEN
    session.flush()
    return bill


def amount_outstanding(session: Session, bill: Bill) -> int:
    from accounting.models import Payment, PaymentDirection

    paid = sum(
        p.amount_cents
        for p in session.query(Payment).filter(
            Payment.bill_id == bill.id,
            Payment.direction == PaymentDirection.SENT,
        )
    )
    return bill.total_cents - paid
