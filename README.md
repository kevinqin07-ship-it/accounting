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
  cli.py                  Click-based command line
  seed.py                 demo dataset
alembic/                  migrations; env.py reads ACCOUNTING_DB_URL
tests/                    pytest suite (each test gets a freshly migrated SQLite db)
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

## HTTP API

A FastAPI layer over the service modules lives in `accounting.api`.

```bash
accounting init                                              # migrate + install chart
accounting auth create-key --name ops --role admin           # save the printed key!
accounting-api                                               # uvicorn on 0.0.0.0:8000
# or: uvicorn accounting.api.app:app --reload
```

OpenAPI docs at `/docs`. Money on the wire is `Decimal` dollars; cents
stay internal. Service-layer `ValueError`s map to 400; `LookupError`s
map to 404, so domain code stays web-framework-free.

### Authentication

Every endpoint except `/healthz`, `/login`, and `/logout` requires an API
key. Keys are managed locally via the CLI (`accounting auth
create-key|list-keys|revoke`) and authenticated either via `Authorization:
Bearer <key>` or via an HTTP-only cookie set by `POST /auth/login`. Three
roles: `admin` (everything), `bookkeeper` (writes except period close +
key management), `readonly` (GETs only).

### Dashboard

Browser dashboard at `/dashboard`. Unauthenticated requests redirect to
`/login`, which accepts an API key and sets the session cookie. Renders
operating cash, AR/AP, YTD P&L, AR aging buckets, recent shipments with
margin, books status, and bank reconciliation status.

### Email notifications

`POST /notifications/ar-aging` (admin) sends an AR aging digest email to
the configured recipients. SMTP config via `SMTP_HOST`, `SMTP_PORT`,
`SMTP_USER`, `SMTP_PASS`, `SMTP_USE_TLS`, `SMTP_FROM`. Set
`SMTP_DRY_RUN=1` to capture the message instead of sending. Also
available via CLI: `accounting notify ar-aging --to ops@example.com
--min-days 1`.

### Airtable sync

`accounting.airtable` syncs from an Airtable base (default: the Drayage
Command Center) into the accounting API. One-way; Airtable stays the
operational source of truth. Idempotent across runs:

  - Customer Master rows -> POST /customers (upsert by `AT-{recordId}`).
  - Revenue Tracker rows where `Billing Status = Billed` -> POST
    /shipments + /invoices + /invoices/{id}/issue, with each currency
    column mapped to the appropriate revenue account. Re-runs skip rows
    where the invoice already exists.
  - Revenue Tracker rows where `Payment Status = Paid` also POST
    /payments/receive for the Collected Amount.

  Driver settlements live in Airtable, not in the accounting books, so
  the drivers flow is opt-in (run with `--flows drivers` if you want to
  populate `/drivers`).

  Per-period driver pay still has to land in the books, even though
  individual settlements stay in Airtable. Two CLI commands:

  - `accounting airtable sync-settlements --period-start ... --period-end ...`
    sums Move Log Driver Pay over the explicit range and posts one JE:
    DR 5000 Driver Wages, CR 1000 Operating Cash by default. Override
    with `--expense-account 5010` for owner-ops or `--cash-account 2100`
    for the accrual model.

  - `accounting airtable sync-settlements-weekly` is the same thing
    wrapped for cron: it picks the last fully-completed week, defaults
    to the accrual model (CR 2100 Driver Wages Payable), and is a
    no-op on re-runs (the JE reference is `SETTLE-AGG:{start}..{end}`).
    Adjust `--week-ends-on` (0=Mon..6=Sun, default Sun) to match your
    pay period.

#### Weekly schedule

The repo includes `.github/workflows/sync-settlements-weekly.yml` that
runs every Monday at 06:00 UTC and supports manual `workflow_dispatch`.
You'll need three repository configurations:

- secret `ACCOUNTING_API_KEY` — admin-role accounting key
- secret `AIRTABLE_API_KEY` — Airtable PAT with read access to the base
- variable `ACCOUNTING_BASE_URL` — public URL of the accounting API

For a self-hosted setup, equivalent cron line on the accounting host
(after `pip install -e .` and exporting the same env vars):

```
0 6 * * 1  /usr/local/bin/accounting airtable sync-settlements-weekly --commit
```

Pair this with bank reconciliation: at week-end the JE accrues a
liability against 2100 Driver Wages Payable; when the actual ACH
disbursement clears, post a DR 2100 / CR 1000 entry (or use the bank
rec adjustment endpoint) so 2100 returns to zero and the bank line is
matched.

Run via the CLI:

```bash
export AIRTABLE_API_KEY=patXXXX
export ACCOUNTING_API_KEY=adminKey  # admin-role accounting key
accounting airtable sync --dry-run                 # preview
accounting airtable sync --commit                  # actually post
accounting airtable sync --commit --flows customers,revenue_tracker
```

Per-row errors are reported but don't abort the batch. The
AirtableClient is a thin Protocol with an httpx-backed production
implementation and a FakeAirtableClient for tests, so sync flows are
verifiable end-to-end without hitting the Airtable API.

### Resource groups

`/accounts`, `/customers`, `/vendors`, `/shipments`, `/invoices`,
`/bills`, `/payments`, `/drivers`, `/settlements`, `/journal-entries`,
`/period-close`, `/notifications/ar-aging`,
`/auth/{login,logout,keys}`, `/dashboard`, `/login`, `/logout`,
`/reports/{trial-balance,income-statement,balance-sheet,ar-aging,ap-aging,shipment-pnl/{no}}`.

## Migrations

The schema is managed by Alembic. To create a new migration after changing models:

```bash
alembic revision --autogenerate -m "add fancy new column"
alembic upgrade head
```

CI runs `alembic check` to fail PRs that change models without a matching migration.

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
