"""Dashboard data aggregator + HTML route tests."""

from __future__ import annotations

from datetime import date


def _seed_activity(client):
    """Install chart, create one customer/vendor/shipment/invoice/bill so the
    dashboard has something to render."""
    client.post("/accounts/install-default-chart")
    cust = client.post("/customers", json={"code": "ACME", "name": "Acme"}).json()
    vend = client.post("/vendors", json={"code": "PILOT", "name": "Pilot"}).json()
    shipment = client.post(
        "/shipments",
        json={
            "shipment_no": "SHP-D",
            "customer_id": cust["id"],
            "origin": "DFW",
            "destination": "ATL",
            "quoted_revenue": "1000.00",
        },
    ).json()
    inv = client.post(
        "/invoices",
        json={
            "invoice_no": "INV-D",
            "customer_id": cust["id"],
            "shipment_id": shipment["id"],
            "issue_date": "2026-01-15",
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
            "bill_no": "B-D",
            "vendor_id": vend["id"],
            "shipment_id": shipment["id"],
            "issue_date": "2026-01-20",
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
    client.post(
        "/payments/receive",
        json={
            "invoice_id": inv["id"],
            "payment_date": "2026-01-25",
            "amount": "1000.00",
        },
    )


def test_build_snapshot_pulls_all_metrics(client, session):
    _seed_activity(client)
    from accounting.services import dashboard

    snap = dashboard.build_snapshot(session, as_of=date(2026, 12, 31))
    assert snap.cash_cents == 100_000  # $1000 received
    assert snap.ar_cents == 0  # invoice fully paid
    assert snap.ap_cents == 30_000  # $300 fuel bill unpaid
    assert snap.revenue_ytd_cents == 100_000
    assert snap.expense_ytd_cents == 30_000
    assert snap.net_income_ytd_cents == 70_000
    assert len(snap.recent_shipments) == 1
    assert snap.recent_shipments[0].margin_cents == 70_000
    assert snap.closed_through is None


def test_login_form_unauthenticated(unauthed_client):
    r = unauthed_client.get("/login")
    assert r.status_code == 200
    assert "API key" in r.text


def test_dashboard_redirects_when_unauthenticated(unauthed_client):
    r = unauthed_client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_login_with_bad_key_renders_error(unauthed_client):
    r = unauthed_client.post("/login", data={"key": "garbage"})
    assert r.status_code == 401
    assert "Invalid or revoked" in r.text


def test_login_form_redirects_to_dashboard(unauthed_client, admin_key):
    r = unauthed_client.post(
        "/login", data={"key": admin_key}, follow_redirects=False
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/dashboard"
    # Cookie was set
    assert any("accounting_api_key" in c for c in r.headers.get_list("set-cookie"))


def test_dashboard_renders_snapshot_after_login(unauthed_client, admin_key):
    # Need some data for the dashboard to actually populate sections.
    unauthed_client.headers["Authorization"] = f"Bearer {admin_key}"
    _seed_activity(unauthed_client)
    del unauthed_client.headers["Authorization"]

    # Sign in via the form.
    unauthed_client.post("/login", data={"key": admin_key})
    r = unauthed_client.get("/dashboard")
    assert r.status_code == 200
    body = r.text
    assert "Operating cash" in body
    assert "Year-to-date P&L" in body
    assert "SHP-D" in body  # shipment renders in recent activity
    # Cash $1000.00 should appear
    assert "$1,000.00" in body


def test_logout_redirects_and_clears_cookie(unauthed_client, admin_key):
    unauthed_client.post("/login", data={"key": admin_key})
    r = unauthed_client.get("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
    # And the dashboard now redirects to login.
    r2 = unauthed_client.get("/dashboard", follow_redirects=False)
    assert r2.status_code == 303
    assert r2.headers["location"] == "/login"


def test_readonly_can_view_dashboard(unauthed_client, readonly_key, admin_key):
    # Admin seeds; readonly views.
    unauthed_client.headers["Authorization"] = f"Bearer {admin_key}"
    _seed_activity(unauthed_client)
    del unauthed_client.headers["Authorization"]

    unauthed_client.post("/login", data={"key": readonly_key})
    r = unauthed_client.get("/dashboard")
    assert r.status_code == 200
    assert "(readonly)" in r.text
