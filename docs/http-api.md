# HTTP API

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

## Authentication

Every endpoint except `/healthz`, `/login`, and `/logout` requires an API
key. Keys are managed locally via the CLI (`accounting auth
create-key|list-keys|revoke`) and authenticated either via `Authorization:
Bearer <key>` or via an HTTP-only cookie set by `POST /auth/login`. Three
roles: `admin` (everything), `bookkeeper` (writes except period close +
key management), `readonly` (GETs only).

## Dashboard

Browser dashboard at `/dashboard`. Unauthenticated requests redirect to
`/login`, which accepts an API key and sets the session cookie. Renders
operating cash, AR/AP, YTD P&L, AR aging buckets, recent shipments with
margin, books status, and bank reconciliation status.

## Email notifications

`POST /notifications/ar-aging` (admin) sends an AR aging digest email to
the configured recipients. SMTP config via `SMTP_HOST`, `SMTP_PORT`,
`SMTP_USER`, `SMTP_PASS`, `SMTP_USE_TLS`, `SMTP_FROM`. Set
`SMTP_DRY_RUN=1` to capture the message instead of sending. Also
available via CLI: `accounting notify ar-aging --to ops@example.com
--min-days 1`.

## Resource groups

`/accounts`, `/customers`, `/vendors`, `/shipments`, `/invoices`,
`/bills`, `/payments`, `/drivers`, `/settlements`, `/journal-entries`,
`/period-close`, `/notifications/ar-aging`,
`/auth/{login,logout,keys}`, `/dashboard`, `/login`, `/logout`,
`/reports/{trial-balance,income-statement,balance-sheet,ar-aging,ap-aging,shipment-pnl/{no}}`.
