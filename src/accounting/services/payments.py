"""Payment recording: cash in (against invoices) or cash out (against bills)."""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from accounting.chart_of_accounts import Codes
from accounting.money import Number, to_cents
from accounting.models import (
    Bill,
    BillStatus,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentDirection,
)
from accounting.services import billing, invoicing, ledger
from accounting.services.ledger import LineSpec


def receive_payment(
    session: Session,
    *,
    invoice: Invoice,
    payment_date: date,
    amount: Number,
    method: str = "ach",
    reference: Optional[str] = None,
    cash_account_code: str = Codes.OPERATING_CASH,
) -> Payment:
    if invoice.status not in (InvoiceStatus.OPEN, InvoiceStatus.PARTIAL):
        raise ValueError(f"Cannot receive payment for invoice in status {invoice.status}.")

    amount_cents = to_cents(amount)
    if amount_cents <= 0:
        raise ValueError("Payment amount must be positive.")

    outstanding = invoicing.amount_outstanding(session, invoice)
    if amount_cents > outstanding:
        raise ValueError(
            f"Payment ${amount_cents/100:.2f} exceeds outstanding ${outstanding/100:.2f}."
        )

    cash_account = ledger.get_account(session, cash_account_code)
    entry = ledger.post_entry(
        session,
        entry_date=payment_date,
        memo=f"Payment received for invoice {invoice.invoice_no}",
        reference=f"PMT:INV:{invoice.invoice_no}",
        lines=[
            LineSpec(account_code=cash_account_code, debit_cents=amount_cents, memo="Cash receipt"),
            LineSpec(
                account_code=Codes.ACCOUNTS_RECEIVABLE,
                credit_cents=amount_cents,
                memo=f"AR clear - {invoice.invoice_no}",
            ),
        ],
    )
    payment = Payment(
        direction=PaymentDirection.RECEIVED,
        payment_date=payment_date,
        amount_cents=amount_cents,
        method=method,
        reference=reference,
        cash_account_id=cash_account.id,
        invoice_id=invoice.id,
        journal_entry_id=entry.id,
    )
    session.add(payment)

    new_outstanding = outstanding - amount_cents
    invoice.status = InvoiceStatus.PAID if new_outstanding == 0 else InvoiceStatus.PARTIAL
    session.flush()
    return payment


def send_payment(
    session: Session,
    *,
    bill: Bill,
    payment_date: date,
    amount: Number,
    method: str = "ach",
    reference: Optional[str] = None,
    cash_account_code: str = Codes.OPERATING_CASH,
) -> Payment:
    if bill.status not in (BillStatus.OPEN, BillStatus.PARTIAL):
        raise ValueError(f"Cannot pay bill in status {bill.status}.")

    amount_cents = to_cents(amount)
    if amount_cents <= 0:
        raise ValueError("Payment amount must be positive.")

    outstanding = billing.amount_outstanding(session, bill)
    if amount_cents > outstanding:
        raise ValueError(
            f"Payment ${amount_cents/100:.2f} exceeds outstanding ${outstanding/100:.2f}."
        )

    cash_account = ledger.get_account(session, cash_account_code)
    entry = ledger.post_entry(
        session,
        entry_date=payment_date,
        memo=f"Payment sent for bill {bill.bill_no}",
        reference=f"PMT:BILL:{bill.bill_no}",
        lines=[
            LineSpec(
                account_code=Codes.ACCOUNTS_PAYABLE,
                debit_cents=amount_cents,
                memo=f"AP clear - {bill.bill_no}",
            ),
            LineSpec(
                account_code=cash_account_code,
                credit_cents=amount_cents,
                memo="Cash disbursement",
            ),
        ],
    )
    payment = Payment(
        direction=PaymentDirection.SENT,
        payment_date=payment_date,
        amount_cents=amount_cents,
        method=method,
        reference=reference,
        cash_account_id=cash_account.id,
        bill_id=bill.id,
        journal_entry_id=entry.id,
    )
    session.add(payment)

    new_outstanding = outstanding - amount_cents
    bill.status = BillStatus.PAID if new_outstanding == 0 else BillStatus.PARTIAL
    session.flush()
    return payment
