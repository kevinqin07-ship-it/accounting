"""FastAPI app factory and uvicorn entry point."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from accounting.api.routers import (
    accounts,
    auth,
    bills,
    invoices,
    journal,
    notifications,
    parties,
    payments,
    period_close,
    reports,
    shipments,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Logistics Accounting API",
        version="0.1.0",
        description=(
            "HTTP layer over the accounting service modules. "
            "Auth is intentionally out of scope for v1."
        ),
    )

    # Service-layer errors map to HTTP 400 / 404. Keeps domain code free of
    # web-framework imports.
    @app.exception_handler(LookupError)
    async def _not_found(_: Request, exc: LookupError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _bad_request(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(auth.router)
    app.include_router(accounts.router)
    app.include_router(parties.customers_router)
    app.include_router(parties.vendors_router)
    app.include_router(shipments.router)
    app.include_router(invoices.router)
    app.include_router(bills.router)
    app.include_router(payments.router)
    app.include_router(journal.router)
    app.include_router(reports.router)
    app.include_router(period_close.router)
    app.include_router(notifications.router)

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


# Module-level app for uvicorn discovery: `uvicorn accounting.api.app:app`.
app = create_app()


def run() -> None:
    """Console-script entry point: `accounting-api`."""
    import uvicorn

    uvicorn.run("accounting.api.app:app", host="0.0.0.0", port=8000, reload=False)
