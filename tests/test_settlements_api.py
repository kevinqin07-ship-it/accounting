"""HTTP tests for /drivers and /settlements."""

from __future__ import annotations


def test_upsert_driver_and_list(client):
    client.post("/accounts/install-default-chart")
    r = client.post(
        "/drivers",
        json={
            "code": "DRV1",
            "name": "Pat Trucker",
            "driver_type": "employee",
            "cents_per_mile": 60,
            "truck_no": "T-17",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["code"] == "DRV1"
    assert body["driver_type"] == "employee"
    assert body["cents_per_mile"] == 60

    r2 = client.post(
        "/drivers",
        json={
            "code": "DRV1",
            "name": "Pat T.",
            "driver_type": "employee",
            "truck_no": "T-18",
        },
    )
    assert r2.status_code == 201
    assert r2.json()["truck_no"] == "T-18"

    listing = client.get("/drivers").json()
    assert len(listing) == 1


def test_unknown_driver_type_400(client):
    client.post("/accounts/install-default-chart")
    r = client.post(
        "/drivers", json={"code": "X", "name": "X", "driver_type": "wizard"}
    )
    assert r.status_code == 400


def test_settlement_full_lifecycle(client):
    client.post("/accounts/install-default-chart")
    driver = client.post(
        "/drivers",
        json={"code": "DRV2", "name": "Owner Op", "driver_type": "owner_operator"},
    ).json()

    create = client.post(
        "/settlements",
        json={
            "settlement_no": "STL-API-1",
            "driver_id": driver["id"],
            "period_start": "2026-04-01",
            "period_end": "2026-04-07",
            "issue_date": "2026-04-08",
            "earnings": [{"description": "Linehaul", "amount": "1500.00"}],
            "deductions": [
                {
                    "description": "Fuel-card recovery",
                    "amount": "100.00",
                    "recovery_account_code": "5100",
                }
            ],
        },
    )
    assert create.status_code == 201, create.text
    s = create.json()
    assert s["status"] == "draft"
    assert s["gross"] == "1500.00"
    assert s["deductions_total"] == "100.00"
    assert s["net"] == "1400.00"

    approved = client.post(f"/settlements/{s['id']}/approve").json()
    assert approved["status"] == "approved"

    paid = client.post(
        f"/settlements/{s['id']}/pay",
        json={"payment_date": "2026-04-12", "method": "ach"},
    ).json()
    assert paid["status"] == "paid"

    # Cash decreased by net pay; OO settlements account hit gross.
    bs = client.get("/reports/balance-sheet?as_of=2099-12-31").json()
    cash = next((line for line in bs["assets"] if line["code"] == "1000"), None)
    assert cash is not None
    assert cash["amount"] == "-1400.00"


def test_settlement_create_unknown_driver_404(client):
    client.post("/accounts/install-default-chart")
    r = client.post(
        "/settlements",
        json={
            "settlement_no": "STL-X",
            "driver_id": 99999,
            "period_start": "2026-04-01",
            "period_end": "2026-04-07",
            "issue_date": "2026-04-08",
            "earnings": [{"description": "L", "amount": "100.00"}],
        },
    )
    assert r.status_code == 404


def test_double_approve_400(client):
    client.post("/accounts/install-default-chart")
    driver = client.post(
        "/drivers",
        json={"code": "DRV3", "name": "X", "driver_type": "employee"},
    ).json()
    s = client.post(
        "/settlements",
        json={
            "settlement_no": "STL-DBL",
            "driver_id": driver["id"],
            "period_start": "2026-04-01",
            "period_end": "2026-04-07",
            "issue_date": "2026-04-08",
            "earnings": [{"description": "L", "amount": "500.00"}],
        },
    ).json()
    client.post(f"/settlements/{s['id']}/approve")
    r = client.post(f"/settlements/{s['id']}/approve")
    assert r.status_code == 400


def test_readonly_cannot_create_settlement(unauthed_client, readonly_key, admin_key):
    unauthed_client.post(
        "/accounts/install-default-chart",
        headers={"Authorization": f"Bearer {admin_key}"},
    )
    driver = unauthed_client.post(
        "/drivers",
        json={"code": "DRV4", "name": "X", "driver_type": "employee"},
        headers={"Authorization": f"Bearer {admin_key}"},
    ).json()
    r = unauthed_client.post(
        "/settlements",
        json={
            "settlement_no": "STL-RO",
            "driver_id": driver["id"],
            "period_start": "2026-04-01",
            "period_end": "2026-04-07",
            "issue_date": "2026-04-08",
            "earnings": [{"description": "L", "amount": "500.00"}],
        },
        headers={"Authorization": f"Bearer {readonly_key}"},
    )
    assert r.status_code == 403


def test_settlement_with_shipment_linked(client):
    client.post("/accounts/install-default-chart")
    cust = client.post("/customers", json={"code": "C", "name": "C"}).json()
    shipment = client.post(
        "/shipments",
        json={
            "shipment_no": "SHP-S1",
            "customer_id": cust["id"],
            "origin": "DFW",
            "destination": "ATL",
            "quoted_revenue": "1000.00",
        },
    ).json()
    driver = client.post(
        "/drivers", json={"code": "DRV5", "name": "X", "driver_type": "employee"}
    ).json()
    s = client.post(
        "/settlements",
        json={
            "settlement_no": "STL-SHIP",
            "driver_id": driver["id"],
            "period_start": "2026-04-01",
            "period_end": "2026-04-07",
            "issue_date": "2026-04-08",
            "earnings": [
                {
                    "description": "Per-mile",
                    "amount": "200.00",
                    "shipment_id": shipment["id"],
                }
            ],
        },
    ).json()
    assert s["lines"][0]["shipment_id"] == shipment["id"]
