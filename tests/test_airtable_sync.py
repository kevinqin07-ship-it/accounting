"""End-to-end Airtable sync tests using FakeAirtableClient + the real
accounting API (via TestClient)."""

from __future__ import annotations

from accounting.airtable import DrayageSyncConfig, run_sync
from accounting.airtable.accounting import AccountingClient
from accounting.airtable.airtable import FakeAirtableClient


CFG = DrayageSyncConfig()


def _seed_airtable() -> FakeAirtableClient:
    air = FakeAirtableClient()

    # Two customers
    air.add_record(
        CFG.customer_master_table_id,
        "rec8E8WdYhnTWbJcu",
        {
            CFG.cm_name_field: "PRO METAL INC",
            CFG.cm_email_field: "ap@prometal.test",
            CFG.cm_phone_field: "555-0101",
            CFG.cm_billing_contact_field: "Jane",
        },
    )
    air.add_record(
        CFG.customer_master_table_id,
        "recO8hbuJrEaPBHoG",
        {CFG.cm_name_field: "E-CARGO INC"},
    )

    # One driver
    air.add_record(
        CFG.driver_roster_table_id,
        "recDRV0001",
        {
            CFG.dr_name_field: "Pat Trucker",
            CFG.dr_truck_field: "T-17",
            CFG.dr_phone_field: "555-0202",
        },
    )

    # Two Revenue Tracker rows; one Billed (sync target), one Draft (skip).
    air.add_record(
        CFG.revenue_tracker_table_id,
        "recRT00001",
        {
            CFG.rt_load_id_field: ["LD18013"],
            CFG.rt_customers_field: [
                {"id": "rec8E8WdYhnTWbJcu", "name": "PRO METAL INC"}
            ],
            CFG.rt_billing_status_field: {"id": "selBilled", "name": "Billed"},
            CFG.rt_payment_status_field: {"id": "selOpen", "name": "Open"},
            CFG.rt_invoice_date_field: "2026-04-15",
            # Line haul + FSC + detention
            "fldp1SIicRtCcxFkB": 4500.00,  # Quoted Rate
            "fldHOxl8ckmqeX4ju": 250.00,   # FSC
            "fld4sP4OqOLd9XLxj": 175.00,   # Detention
        },
    )
    air.add_record(
        CFG.revenue_tracker_table_id,
        "recRT00002",
        {
            CFG.rt_load_id_field: ["LD18014"],
            CFG.rt_customers_field: [
                {"id": "recO8hbuJrEaPBHoG", "name": "E-CARGO INC"}
            ],
            CFG.rt_billing_status_field: {"id": "selDraft", "name": "Draft"},
            "fldp1SIicRtCcxFkB": 1000.00,
        },
    )
    # Third row: paid with a collected amount.
    air.add_record(
        CFG.revenue_tracker_table_id,
        "recRT00003",
        {
            CFG.rt_load_id_field: ["LD18015"],
            CFG.rt_customers_field: [
                {"id": "rec8E8WdYhnTWbJcu", "name": "PRO METAL INC"}
            ],
            CFG.rt_billing_status_field: {"id": "selBilled", "name": "Billed"},
            CFG.rt_payment_status_field: {"id": "selPaid", "name": "Paid"},
            CFG.rt_invoice_date_field: "2026-04-20",
            CFG.rt_collected_amount_field: 2200.00,
            "fldp1SIicRtCcxFkB": 2200.00,
        },
    )
    return air


def test_dry_run_default_flows_skip_drivers(client):
    """Default flows are customers + revenue_tracker; drivers stays opt-in."""
    client.post("/accounts/install-default-chart")
    air = _seed_airtable()
    acct = AccountingClient(http=client)
    report = run_sync(air, acct, CFG, dry_run=True)
    assert {f.flow for f in report.flows} == {"customers", "revenue_tracker"}
    # No actual writes.
    assert client.get("/customers").json() == []
    assert client.get("/invoices").json() == []
    assert client.get("/drivers").json() == []


def test_full_default_sync_creates_customers_invoices_payments(client):
    """Default sync (no drivers) hits customers + revenue_tracker only."""
    client.post("/accounts/install-default-chart")
    air = _seed_airtable()
    acct = AccountingClient(http=client)
    report = run_sync(air, acct, CFG, dry_run=False)
    assert report.total_errors == 0, report.summary()

    customers = client.get("/customers").json()
    assert {c["code"] for c in customers} == {
        "AT-rec8E8WdYhnTWbJcu",
        "AT-recO8hbuJrEaPBHoG",
    }

    # Drivers were NOT touched by the default sync.
    assert client.get("/drivers").json() == []

    invoices = client.get("/invoices").json()
    invoice_nos = {inv["invoice_no"] for inv in invoices}
    # Only the two Billed rows produced invoices; the Draft row was skipped.
    assert invoice_nos == {"RT-recRT00001", "RT-recRT00003"}

    rt1 = next(inv for inv in invoices if inv["invoice_no"] == "RT-recRT00001")
    assert rt1["status"] == "open"  # issued, not yet paid
    assert rt1["total"] == "4925.00"  # 4500 + 250 + 175
    accounts_hit = {line["revenue_account_code"] for line in rt1["lines"]}
    assert accounts_hit == {"4000", "4010", "4030"}

    rt3 = next(inv for inv in invoices if inv["invoice_no"] == "RT-recRT00003")
    assert rt3["status"] == "paid"
    assert rt3["total"] == "2200.00"


def test_drivers_flow_runs_when_explicitly_requested(client):
    """Opt-in still works for users who DO want drivers in accounting."""
    client.post("/accounts/install-default-chart")
    air = _seed_airtable()
    acct = AccountingClient(http=client)
    run_sync(air, acct, CFG, dry_run=False, flows=["drivers"])
    drivers = client.get("/drivers").json()
    assert any(d["code"] == "AT-recDRV0001" for d in drivers)


def test_second_run_is_idempotent(client):
    client.post("/accounts/install-default-chart")
    air = _seed_airtable()
    acct = AccountingClient(http=client)
    run_sync(air, acct, CFG, dry_run=False)
    invoices_after_first = client.get("/invoices").json()

    # Second run: every Revenue Tracker row should be skipped as already
    # synced; customers upsert (no new rows).
    report = run_sync(air, acct, CFG, dry_run=False)
    rt_flow = next(f for f in report.flows if f.flow == "revenue_tracker")
    assert rt_flow.inserted == 0
    assert rt_flow.skipped_existing == 2
    assert rt_flow.errors == []

    invoices_after_second = client.get("/invoices").json()
    assert len(invoices_after_first) == len(invoices_after_second)


def test_missing_customer_link_is_an_error_not_a_crash(client):
    client.post("/accounts/install-default-chart")
    air = FakeAirtableClient()
    air.add_record(
        CFG.revenue_tracker_table_id,
        "recRTBROKEN",
        {
            CFG.rt_billing_status_field: {"id": "selBilled", "name": "Billed"},
            CFG.rt_invoice_date_field: "2026-04-01",
            "fldp1SIicRtCcxFkB": 1000.00,
            # No CFG.rt_customers_field!
        },
    )
    acct = AccountingClient(http=client)
    report = run_sync(air, acct, CFG, dry_run=False, flows=["revenue_tracker"])
    rt = next(f for f in report.flows if f.flow == "revenue_tracker")
    assert rt.inserted == 0
    assert any("missing linked customer" in e for e in rt.errors)


def test_zero_dollar_row_is_an_error_not_a_crash(client):
    client.post("/accounts/install-default-chart")
    air = FakeAirtableClient()
    air.add_record(
        CFG.customer_master_table_id,
        "recCUST0",
        {CFG.cm_name_field: "Acme"},
    )
    air.add_record(
        CFG.revenue_tracker_table_id,
        "recRTZERO",
        {
            CFG.rt_billing_status_field: {"id": "selBilled", "name": "Billed"},
            CFG.rt_invoice_date_field: "2026-04-01",
            CFG.rt_customers_field: [{"id": "recCUST0", "name": "Acme"}],
            # No currency columns
        },
    )
    acct = AccountingClient(http=client)
    report = run_sync(air, acct, CFG, dry_run=False)
    rt = next(f for f in report.flows if f.flow == "revenue_tracker")
    assert rt.inserted == 0
    assert any("no non-zero rate columns" in e for e in rt.errors)
    # Customers still synced fine.
    customers = client.get("/customers").json()
    assert any(c["code"] == "AT-recCUST0" for c in customers)


def test_sync_subset_flows_only(client):
    client.post("/accounts/install-default-chart")
    air = _seed_airtable()
    acct = AccountingClient(http=client)
    report = run_sync(air, acct, CFG, dry_run=False, flows=["customers"])
    assert {f.flow for f in report.flows} == {"customers"}
    assert client.get("/customers").json()
    assert client.get("/drivers").json() == []
    assert client.get("/invoices").json() == []


def test_unauthenticated_accounting_client_fails_clearly(unauthed_client):
    """If the AccountingClient lacks a key, every call fails. The sync
    surfaces those as per-row errors, not a top-level crash."""
    air = _seed_airtable()
    acct = AccountingClient(http=unauthed_client)
    report = run_sync(air, acct, CFG, dry_run=False, flows=["customers"])
    customers_flow = next(f for f in report.flows if f.flow == "customers")
    assert customers_flow.inserted == 0
    assert len(customers_flow.errors) >= 1
