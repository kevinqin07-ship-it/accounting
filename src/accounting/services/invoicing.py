"""Customer invoicing. Posts AR / Revenue journal entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Sequence

from sqlalchemy.orm import Session

from accounting.chart_of_accounts import Codes
from accounting.money import Number, to_cents
from accounting.models import Customer, Invoice, InvoiceLine, InvoiceStatus, Shipment, ShipmentStatus
from accounting.services import ledger
from accounting.services.ledger import LineSpec


@dataclass
class InvoiceLineInput:
    description: str
    revenue_account_code: str
    amount: Number


def create_invoice(
    session: Session,
    *,
    invoice_no: str,
    customer: Customer,
    issue_date: date,
    lines: Sequence[InvoiceLineInput],
    shipment: Optional[Shipment] = None,
    due_date: Optional[date] = None,
    ar_account_code: str = Codes.ACCOUNTS_RECEIVABLE,
) -> Invoice:
    if not lines:
        raise ValueError("An invoice needs at least one line.")
    due = due_date or (issue_date + timedelta(days=customer.payment_terms_days))

    invoice = Invoice(
        invoice_no=invoice_no,
        customer_id=customer.id,
        shipment_id=shipment.id if shipment else None,
        issue_date=issue_date,
        due_date=due,
        status=InvoiceStatus.DRAFT,
    )
    for line in lines:
        revenue_account = ledger.get_account(session, line.revenue_account_code)
        invoice.lines.append(
            InvoiceLine(
                description=line.description,
                revenue_account_id=revenue_account.id,
                amount_cents=to_cents(line.amount),
            )
        )
    session.add(invoice)
    session.flush()
    return invoice


def issue_invoice(session: Session, invoice: Invoice) -> Invoice:
    """Post the journal entry: debit AR, credit each revenue account."""
    if invoice.status != InvoiceStatus.DRAFT:
        raise ValueError(f"Invoice {invoice.invoice_no} is not in DRAFT (status={invoice.status}).")
    if invoice.total_cents <= 0:
        raise ValueError("Cannot issue an invoice with non-positive total.")

    entry_lines: List[LineSpec] = [
        LineSpec(
            account_code=Codes.ACCOUNTS_RECEIVABLE,
            debit_cents=invoice.total_cents,
            memo=f"AR - Invoice {invoice.invoice_no}",
        )
    ]
    for line in invoice.lines:
        entry_lines.append(
            LineSpec(
                account_code=line.revenue_account.code,
                credit_cents=line.amount_cents,
                memo=line.description,
            )
        )
    entry = ledger.post_entry(
        session,
        entry_date=invoice.issue_date,
        memo=f"Invoice {invoice.invoice_no}",
        reference=f"INV:{invoice.invoice_no}",
        lines=entry_lines,
    )
    invoice.journal_entry_id = entry.id
    invoice.status = InvoiceStatus.OPEN
    if invoice.shipment is not None:
        invoice.shipment.status = ShipmentStatus.INVOICED
    session.flush()
    return invoice


def amount_outstanding(session: Session, invoice: Invoice) -> int:
    """Total minus payments applied so far, in cents."""
    from accounting.models import Payment, PaymentDirection

    paid = sum(
        p.amount_cents
        for p in session.query(Payment).filter(
            Payment.invoice_id == invoice.id,
            Payment.direction == PaymentDirection.RECEIVED,
        )
    )
    return invoice.total_cents - paid
