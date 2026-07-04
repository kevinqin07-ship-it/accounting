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
  db.py                   SQLAlchemy engine, Session context manager, init/reset via Alembic
  models/                 ORM models (accounts, journal, parties, shipment, invoice, bill,
                          payment, drivers + settlements, fuel transactions)
  services/
    ledger.py             post journal entries; balances; trial balance
    parties.py            upsert customers and vendors
    shipments.py          shipment lifecycle helpers
    invoicing.py          create + issue customer invoices
    billing.py            create + approve vendor bills
    payments.py           receive / send payments and clear AR / AP
    settlements.py        driver pay runs (employees + owner-operators) with deductions
    fuel_import.py        parse fuel-card CSV; create per-truck rolled-up vendor bill
    bank_rec.py           bank-statement import, auto-match, finalize a reconciliation
    reports.py            income statement, balance sheet, AR/AP aging, shipment P&L
  api/
    routers/              one FastAPI router per resource
    schemas/               one Pydantic schema module per resource, mirroring routers/
  cli/                    Click-based command line, one module per command group,
                          mirroring api/routers/ (bank_rec, drivers, settlements,
                          notifications, airtable, auth); core commands + root group
                          live in cli/__init__.py
  airtable/               Airtable -> accounting sync (see docs/airtable-sync.md)
  seed.py                 demo dataset
alembic/                  migrations; env.py reads ACCOUNTING_DB_URL
tests/
  api/                    tests that exercise the HTTP layer (FastAPI TestClient)
  services/               tests against the service layer directly
  airtable/               Airtable sync tests (FakeAirtableClient + real API)
```

## Quick start

```bash
pip install -e .[dev]
accounting init       # run migrations and install the chart of accounts
accounting seed       # load a small demo dataset
accounting trial-balance
accounting pnl --start 2026-01-01 --end 2026-12-31
accounting balance-sheet --as-of 2026-12-31
accounting ar-aging
accounting shipment-pnl SHP-1001
accounting import-fuel PILOT statement.csv --bill-no PILOT-APR --issue-date 2026-04-30
accounting import-bank 1000 chase-april.csv
accounting bank-rec open 1000 --period-start 2026-04-01 --period-end 2026-04-30 \
    --start-balance 10000 --end-balance 11920
accounting bank-rec auto-match 1
accounting bank-rec status 1
accounting bank-rec finalize 1
```

The default database is `sqlite:///accounting.db` in the working directory; override
via `ACCOUNTING_DB_URL`. `accounting init` runs Alembic migrations on whichever URL
is configured.

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

## See also

- [`docs/http-api.md`](docs/http-api.md) — the FastAPI layer: auth, dashboard, email
  notifications, resource groups.
- [`docs/airtable-sync.md`](docs/airtable-sync.md) — Airtable -> accounting sync, the
  weekly driver-pay cron, and pairing it with bank reconciliation.
- [`docs/migrations.md`](docs/migrations.md) — Alembic migration workflow.
