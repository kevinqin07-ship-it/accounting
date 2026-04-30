"""End-to-end HTTP tests for the FastAPI app. Uses the same temp database
as the `session` fixture so we can also peek at state directly when useful."""

from __future__ import annotations


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_install_chart_and_list_accounts(client):
    r = client.post("/accounts/install-default-chart")
    assert r.status_code == 200
    accounts = r.json()
    codes = {a["code"] for a in accounts}
    assert "1000" in codes  # Operating Cash
    assert "4000" in codes  # Freight Revenue

    r2 = client.get("/accounts")
    assert r2.status_code == 200
    assert len(r2.json()) == len(accounts)


def test_full_invoice_to_payment_flow(client):
    client.post("/accounts/install-default-chart")
    cust = client.post(
        "/customers",
        json={"code": "ACME", "name": "Acme Manufacturing", "payment_terms_days": 30},
    ).json()

    inv = client.post(
        "/invoices",
        json={
            "invoice_no": "INV-API-1",
            "customer_id": cust["id"],
            "issue_date": "2026-04-01",
            "lines": [
                {
                    "description": "Line haul",
                    "revenue_account_code": "4000",
                    "amount": "1500.00",
                },
                {
                    "description": "Fuel surcharge",
                    "revenue_account_code": "4010",
                    "amount": "200.00",
                },
            ],
        },
    ).json()
    assert inv["status"] == "draft"
    assert inv["total"] == "1700.00"

    issued = client.post(f"/invoices/{inv['id']}/issue").json()
    assert issued["status"] == "open"

    pay = client.post(
        "/payments/receive",
        json={
            "invoice_id": inv["id"],
            "payment_date": "2026-04-15",
            "amount": "1700.00",
            "method": "ach",
        },
    ).json()
    assert pay["direction"] == "received"
    assert pay["amount"] == "1700.00"

    final = client.get(f"/invoices/{inv['id']}").json()
    assert final["status"] == "paid"


def test_full_bill_to_payment_flow(client):
    client.post("/accounts/install-default-chart")
    vend = client.post(
        "/vendors",
        json={"code": "PILOT", "name": "Pilot", "category": "fuel"},
    ).json()

    bill = client.post(
        "/bills",
        json={
            "bill_no": "B-API-1",
            "vendor_id": vend["id"],
            "issue_date": "2026-04-01",
            "lines": [
                {
                    "description": "Diesel",
                    "expense_account_code": "5100",
                    "amount": "880.00",
                }
            ],
        },
    ).json()
    assert bill["total"] == "880.00"

    approved = client.post(f"/bills/{bill['id']}/approve").json()
    assert approved["status"] == "open"

    pay = client.post(
        "/payments/send",
        json={
            "bill_id": bill["id"],
            "payment_date": "2026-04-10",
            "amount": "880.00",
        },
    ).json()
    assert pay["direction"] == "sent"

    final = client.get(f"/bills/{bill['id']}").json()
    assert final["status"] == "paid"


def test_value_error_maps_to_400(client):
    client.post("/accounts/install-default-chart")
    cust = client.post("/customers", json={"code": "X", "name": "X"}).json()
    inv = client.post(
        "/invoices",
        json={
            "invoice_no": "INV-X",
            "customer_id": cust["id"],
            "issue_date": "2026-04-01",
            "lines": [
                {
                    "description": "L",
                    "revenue_account_code": "4000",
                    "amount": "10.00",
                }
            ],
        },
    ).json()
    client.post(f"/invoices/{inv['id']}/issue")
    # Now try to issue again — the service will raise ValueError.
    r = client.post(f"/invoices/{inv['id']}/issue")
    assert r.status_code == 400
    assert "DRAFT" in r.json()["detail"]


def test_lookup_error_maps_to_404(client):
    r = client.get("/shipments/NOPE")
    assert r.status_code == 404


def test_reports_after_activity(client):
    client.post("/accounts/install-default-chart")
    cust = client.post("/customers", json={"code": "A", "name": "A"}).json()
    vend = client.post("/vendors", json={"code": "V", "name": "V"}).json()

    inv = client.post(
        "/invoices",
        json={
            "invoice_no": "INV-R",
            "customer_id": cust["id"],
            "issue_date": "2026-04-01",
            "lines": [
                {
                    "description": "Line haul",
                    "revenue_account_code": "4000",
                    "amount": "5000.00",
                }
            ],
        },
    ).json()
    client.post(f"/invoices/{inv['id']}/issue")

    bill = client.post(
        "/bills",
        json={
            "bill_no": "B-R",
            "vendor_id": vend["id"],
            "issue_date": "2026-04-05",
            "lines": [
                {
                    "description": "Fuel",
                    "expense_account_code": "5100",
                    "amount": "1500.00",
                }
            ],
        },
    ).json()
    client.post(f"/bills/{bill['id']}/approve")

    pnl = client.get(
        "/reports/income-statement?start=2026-01-01&end=2026-12-31"
    ).json()
    assert pnl["total_revenue"] == "5000.00"
    assert pnl["total_expense"] == "1500.00"
    assert pnl["net_income"] == "3500.00"

    bs = client.get("/reports/balance-sheet?as_of=2026-12-31").json()
    # Identity must hold.
    total_assets = float(bs["total_assets"])
    assert abs(total_assets - (float(bs["total_liabilities"]) + float(bs["total_equity"]))) < 0.005

    tb = client.get("/reports/trial-balance").json()
    assert tb["total_debit"] == tb["total_credit"]


def test_shipment_pnl_endpoint(client):
    client.post("/accounts/install-default-chart")
    cust = client.post("/customers", json={"code": "A", "name": "A"}).json()
    vend = client.post("/vendors", json={"code": "V", "name": "V"}).json()
    shipment = client.post(
        "/shipments",
        json={
            "shipment_no": "SHP-API",
            "customer_id": cust["id"],
            "origin": "DFW",
            "destination": "ATL",
            "quoted_revenue": "1000.00",
        },
    ).json()
    inv = client.post(
        "/invoices",
        json={
            "invoice_no": "INV-S",
            "customer_id": cust["id"],
            "shipment_id": shipment["id"],
            "issue_date": "2026-04-01",
            "lines": [
                {
                    "description": "Line haul",
                    "revenue_account_code": "4000",
                    "amount": "1000.00",
                }
            ],
        },
    ).json()
    client.post(f"/invoices/{inv['id']}/issue")
    bill = client.post(
        "/bills",
        json={
            "bill_no": "B-S",
            "vendor_id": vend["id"],
            "shipment_id": shipment["id"],
            "issue_date": "2026-04-02",
            "lines": [
                {
                    "description": "Fuel",
                    "expense_account_code": "5100",
                    "amount": "300.00",
                }
            ],
        },
    ).json()
    client.post(f"/bills/{bill['id']}/approve")

    pnl = client.get("/reports/shipment-pnl/SHP-API").json()
    assert pnl["revenue"] == "1000.00"
    assert pnl["cost"] == "300.00"
    assert pnl["margin"] == "700.00"
    assert abs(pnl["margin_pct"] - 0.7) < 1e-6


def test_journal_post_and_unbalanced_400(client):
    client.post("/accounts/install-default-chart")
    r = client.post(
        "/journal-entries",
        json={
            "entry_date": "2026-04-01",
            "memo": "Owner equity",
            "lines": [
                {"account_code": "1000", "debit": "10000.00"},
                {"account_code": "3000", "credit": "10000.00"},
            ],
        },
    )
    assert r.status_code == 201
    bs = client.get("/reports/balance-sheet?as_of=2026-12-31").json()
    assert bs["total_assets"] == "10000.00"

    bad = client.post(
        "/journal-entries",
        json={
            "entry_date": "2026-04-02",
            "memo": "Bad",
            "lines": [
                {"account_code": "1000", "debit": "100.00"},
                {"account_code": "3000", "credit": "99.00"},
            ],
        },
    )
    assert bad.status_code == 400


def test_period_close_via_api(client):
    client.post("/accounts/install-default-chart")
    cust = client.post("/customers", json={"code": "A", "name": "A"}).json()
    inv = client.post(
        "/invoices",
        json={
            "invoice_no": "INV-C",
            "customer_id": cust["id"],
            "issue_date": "2026-01-15",
            "lines": [
                {
                    "description": "L",
                    "revenue_account_code": "4000",
                    "amount": "1000.00",
                }
            ],
        },
    ).json()
    client.post(f"/invoices/{inv['id']}/issue")

    status = client.get("/period-close").json()
    assert status["closed_through"] is None

    r = client.post(
        "/period-close",
        json={"close_through": "2026-01-31"},
    )
    assert r.status_code == 201
    assert r.json()["close_through_date"] == "2026-01-31"

    after = client.get("/period-close").json()
    assert after["closed_through"] == "2026-01-31"

    # Posting in the closed window now fails with 400.
    bad = client.post(
        "/journal-entries",
        json={
            "entry_date": "2026-01-15",
            "memo": "Late entry",
            "lines": [
                {"account_code": "1000", "debit": "1.00"},
                {"account_code": "3000", "credit": "1.00"},
            ],
        },
    )
    assert bad.status_code == 400
    assert "closed through" in bad.json()["detail"]
