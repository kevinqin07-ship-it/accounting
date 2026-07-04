# Airtable sync

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

## Weekly schedule

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

Pair this with bank reconciliation to close the loop:

1. Weekly accrual sync posts `DR 5000, CR 2100`. Liability sits in 2100
   Driver Wages Payable.
2. ACH actually clears a few days later. Import the bank statement:
   `accounting import-bank 1000 statement.csv`.
3. Open a reconciliation: `accounting bank-rec open ...`.
4. Bulk-clear the disbursements: `accounting bank-rec
   settle-disbursements <rec_id>`. Scans unmatched outflows whose
   description contains `PAYROLL`, `DRIVER PAY`, `ACH SETTLE`, or
   `SETTLEMENT` (configurable via `--patterns`); for each, posts a
   `DR 2100, CR 1000` adjustment and matches the bank line to the new
   cash JE line in one shot. After this 2100 is back to zero.
5. `accounting bank-rec auto-match <rec_id>` for the remaining lines,
   then `accounting bank-rec finalize <rec_id>`.

The same `settle-disbursements` flow handles other accruals — pass
`--account 2000 --patterns "CARRIER PAY"` for purchased-transportation
disbursements, or any other pattern + account combo.

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
