from datetime import date

import pytest

from accounting.models import BillStatus, InvoiceStatus
from accounting.services import billing, invoicing, ledger, parties, payments, shipments
from accounting.services.billing import BillLineInput
from accounting.services.invoicing import InvoiceLineInput


def _bootstrap(session):
    ledger.install_chart(session)
    customer = parties.upsert_customer(session, code="ACME", name="Acme")
    vendor = parties.upsert_vendor(session, code="PILOT", name="Pilot", category="fuel")
    return customer, vendor


def test_invoice_lifecycle_posts_balanced_entries(session):
    customer, _ = _bootstrap(session)
    inv = invoicing.create_invoice(
        session,
        invoice_no="INV-1",
        customer=customer,
        issue_date=date(2026, 4, 1),
        lines=[
            InvoiceLineInput("Line haul", "4000", 1000.00),
            InvoiceLineInput("Fuel surcharge", "4010", 100.00),
        ],
    )
    assert inv.total_cents == 110_000
    assert inv.status == InvoiceStatus.DRAFT

    invoicing.issue_invoice(session, inv)
    assert inv.status == InvoiceStatus.OPEN
    assert ledger.account_balance(session, "1100") == 110_000  # AR
    assert ledger.account_balance(session, "4000") == 100_000  # Freight revenue
    assert ledger.account_balance(session, "4010") == 10_000


def test_bill_lifecycle_posts_balanced_entries(session):
    _, vendor = _bootstrap(session)
    bill = billing.create_bill(
        session,
        bill_no="BILL-1",
        vendor=vendor,
        issue_date=date(2026, 4, 1),
        lines=[BillLineInput("Diesel", "5100", 800.00)],
    )
    billing.approve_bill(session, bill)
    assert bill.status == BillStatus.OPEN
    assert ledger.account_balance(session, "5100") == 80_000
    assert ledger.account_balance(session, "2000") == 80_000  # AP


def test_full_payment_marks_paid(session):
    customer, _ = _bootstrap(session)
    inv = invoicing.create_invoice(
        session,
        invoice_no="INV-2",
        customer=customer,
        issue_date=date(2026, 4, 1),
        lines=[InvoiceLineInput("Line haul", "4000", 500.00)],
    )
    invoicing.issue_invoice(session, inv)

    payments.receive_payment(
        session, invoice=inv, payment_date=date(2026, 4, 10), amount=500.00
    )
    assert inv.status == InvoiceStatus.PAID
    assert ledger.account_balance(session, "1000") == 50_000  # Cash
    assert ledger.account_balance(session, "1100") == 0  # AR cleared


def test_partial_payment_marks_partial(session):
    customer, _ = _bootstrap(session)
    inv = invoicing.create_invoice(
        session,
        invoice_no="INV-3",
        customer=customer,
        issue_date=date(2026, 4, 1),
        lines=[InvoiceLineInput("Line haul", "4000", 1000.00)],
    )
    invoicing.issue_invoice(session, inv)
    payments.receive_payment(session, invoice=inv, payment_date=date(2026, 4, 5), amount=400.00)
    assert inv.status == InvoiceStatus.PARTIAL
    assert invoicing.amount_outstanding(session, inv) == 60_000


def test_overpayment_rejected(session):
    customer, _ = _bootstrap(session)
    inv = invoicing.create_invoice(
        session,
        invoice_no="INV-4",
        customer=customer,
        issue_date=date(2026, 4, 1),
        lines=[InvoiceLineInput("Line haul", "4000", 100.00)],
    )
    invoicing.issue_invoice(session, inv)
    with pytest.raises(ValueError, match="exceeds outstanding"):
        payments.receive_payment(
            session, invoice=inv, payment_date=date(2026, 4, 5), amount=200.00
        )


def test_shipment_pnl(session):
    from accounting.services.reports import shipment_pnl

    customer, vendor = _bootstrap(session)
    shipment = shipments.create_shipment(
        session,
        shipment_no="SHP-X",
        customer_id=customer.id,
        origin="A",
        destination="B",
        quoted_revenue=1000.00,
    )
    inv = invoicing.create_invoice(
        session,
        invoice_no="INV-S",
        customer=customer,
        issue_date=date(2026, 4, 1),
        shipment=shipment,
        lines=[InvoiceLineInput("Line haul", "4000", 1000.00)],
    )
    invoicing.issue_invoice(session, inv)
    bill = billing.create_bill(
        session,
        bill_no="BILL-S",
        vendor=vendor,
        issue_date=date(2026, 4, 1),
        shipment=shipment,
        lines=[BillLineInput("Fuel", "5100", 300.00)],
    )
    billing.approve_bill(session, bill)

    pnl = shipment_pnl(session, shipment)
    assert pnl.revenue_cents == 100_000
    assert pnl.cost_cents == 30_000
    assert pnl.margin_cents == 70_000
    assert pnl.margin_pct == pytest.approx(0.7)
