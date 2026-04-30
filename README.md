# Logistics Accounting Module

A double-entry accounting module tailored for a freight / logistics business. It models
the chart of accounts, journal entries, customers (shippers), vendors (fuel, maintenance,
carriers), shipments, invoices, vendor bills, payments, and produces standard financial
reports plus per-shipment profit and loss.

## Highlights

- **Strict double-entry**: every journal entry is validated to balance before it can be
  saved, and every business action (issue invoice, approve bill, receive/send payment)
  posts a balanced entry.
- **Logistics-aware chart of accounts**: freight revenue, fuel surcharge, accessorial
  revenue, brokerage revenue; cost-of-service buckets for fuel, tolls, maintenance,
  carrier pay, owner-operator settlements, and IFTA.
- **Shipment-level P&L**: tie invoices and bills to a shipment and pull margin out
  by load.
- **Reports**: trial balance, income statement, balance sheet, AR / AP aging.
- **CLI** for quick exploration.

## Layout

```
src/accounting/
  chart_of_accounts.py    default logistics CoA
  db.py                   SQLAlchemy engine + Session context manager
  models/                 ORM models (accounts, journal, parties, shipment, invoice, bill, payment)
  services/
    ledger.py             post journal entries; balances; trial balance
    parties.py            upsert customers and vendors
    shipments.py          shipment lifecycle helpers
    invoicing.py          create + issue customer invoices
    billing.py            create + approve vendor bills
    payments.py           receive / send payments and clear AR / AP
    reports.py            income statement, balance sheet, AR/AP aging, shipment P&L
  cli.py                  Click-based command line
  seed.py                 demo dataset
tests/                    pytest suite
```

## Quick start

```bash
pip install -e .[dev]
accounting init       # create tables and install the chart of accounts
accounting seed       # load a small demo dataset
accounting trial-balance
accounting pnl --start 2026-01-01 --end 2026-12-31
accounting balance-sheet --as-of 2026-12-31
accounting ar-aging
accounting shipment-pnl SHP-1001
```

The default database is `sqlite:///accounting.db` in the working directory; override
via `ACCOUNTING_DB_URL`.

## Programmatic use

```python
from datetime import date
from accounting.db import Session, init_db
from accounting.services import ledger, parties, invoicing
from accounting.services.invoicing import InvoiceLineInput

init_db()
with Session() as session:
    ledger.install_chart(session)
    cust = parties.upsert_customer(session, code="ACME", name="Acme")
    inv = invoicing.create_invoice(
        session,
        invoice_no="INV-1001",
        customer=cust,
        issue_date=date.today(),
        lines=[
            InvoiceLineInput("Line haul DFW->ATL", "4000", 4200.00),
            InvoiceLineInput("Fuel surcharge",     "4010",  300.00),
        ],
    )
    invoicing.issue_invoice(session, inv)
```

## Tests

```bash
pytest
```

The suite uses an in-memory SQLite database and verifies balanced postings, the
accounting identity (assets = liabilities + equity), aging, and shipment-level P&L.
