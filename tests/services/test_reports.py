from datetime import date

from accounting.services import billing, invoicing, ledger, parties, reports
from accounting.services.billing import BillLineInput
from accounting.services.invoicing import InvoiceLineInput


def _bootstrap(session):
    ledger.install_chart(session)
    customer = parties.upsert_customer(session, code="ACME", name="Acme")
    vendor = parties.upsert_vendor(session, code="PILOT", name="Pilot", category="fuel")
    return customer, vendor


def test_income_statement_revenue_minus_expense(session):
    customer, vendor = _bootstrap(session)
    inv = invoicing.create_invoice(
        session,
        invoice_no="INV-R",
        customer=customer,
        issue_date=date(2026, 1, 15),
        lines=[InvoiceLineInput("Line haul", "4000", 5000.00)],
    )
    invoicing.issue_invoice(session, inv)
    bill = billing.create_bill(
        session,
        bill_no="BILL-R",
        vendor=vendor,
        issue_date=date(2026, 1, 20),
        lines=[BillLineInput("Diesel", "5100", 1500.00)],
    )
    billing.approve_bill(session, bill)

    stmt = reports.income_statement(session, date(2026, 1, 1), date(2026, 1, 31))
    assert stmt.total_revenue == 500_000
    assert stmt.total_expense == 150_000
    assert stmt.net_income == 350_000


def test_balance_sheet_balances(session):
    customer, vendor = _bootstrap(session)
    inv = invoicing.create_invoice(
        session,
        invoice_no="INV-B",
        customer=customer,
        issue_date=date(2026, 2, 1),
        lines=[InvoiceLineInput("Line haul", "4000", 1000.00)],
    )
    invoicing.issue_invoice(session, inv)
    bill = billing.create_bill(
        session,
        bill_no="BILL-B",
        vendor=vendor,
        issue_date=date(2026, 2, 5),
        lines=[BillLineInput("Diesel", "5100", 200.00)],
    )
    billing.approve_bill(session, bill)

    sheet = reports.balance_sheet(session, date(2026, 2, 28))
    # Accounting identity: Assets = Liabilities + Equity (incl. retained earnings).
    assert sheet.total_assets == sheet.total_liabilities + sheet.total_equity
    # Net income flows into retained earnings.
    assert sheet.retained_earnings == 80_000


def test_ar_aging_includes_open_invoice(session):
    customer, _ = _bootstrap(session)
    inv = invoicing.create_invoice(
        session,
        invoice_no="INV-AGE",
        customer=customer,
        issue_date=date(2026, 1, 1),
        due_date=date(2026, 1, 31),
        lines=[InvoiceLineInput("Line haul", "4000", 1000.00)],
    )
    invoicing.issue_invoice(session, inv)

    rows = reports.ar_aging(session, as_of=date(2026, 3, 1))
    assert len(rows) == 1
    assert rows[0].outstanding_cents == 100_000
    assert rows[0].days_past_due == 29
