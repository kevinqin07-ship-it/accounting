"""End-to-end Airtable sync tests using FakeAirtableClient + the real
accounting API (via TestClient)."""

from __future__ import annotations

from datetime import date

from accounting.airtable import (
    DrayageSyncConfig,
    last_full_week,
    run_sync,
    sync_settlements_aggregate,
    sync_settlements_last_week,
)
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


def _seed_move_log() -> FakeAirtableClient:
    """Three legs: two inside the period (April 1-15), one outside."""
    air = FakeAirtableClient()
    air.add_record(
        CFG.move_log_table_id,
        "recML0001",
        {
            CFG.ml_actual_date_field: "2026-04-03",
            CFG.ml_driver_pay_field: 250.00,
        },
    )
    air.add_record(
        CFG.move_log_table_id,
        "recML0002",
        {
            CFG.ml_actual_date_field: "2026-04-12T08:30:00.000Z",  # datetime form
            CFG.ml_driver_pay_field: 175.50,
        },
    )
    air.add_record(
        CFG.move_log_table_id,
        "recML0003",  # outside period
        {
            CFG.ml_actual_date_field: "2026-04-20",
            CFG.ml_driver_pay_field: 300.00,
        },
    )
    air.add_record(
        CFG.move_log_table_id,
        "recML0004",  # zero pay, ignored
        {
            CFG.ml_actual_date_field: "2026-04-08",
            CFG.ml_driver_pay_field: 0,
        },
    )
    return air


def test_settlements_aggregate_posts_one_je(client):
    client.post("/accounts/install-default-chart")
    air = _seed_move_log()
    acct = AccountingClient(http=client)
    rep = sync_settlements_aggregate(
        air,
        acct,
        CFG,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 15),
        dry_run=False,
    )
    assert rep.errors == []
    assert rep.inserted == 1

    # One JE posted with the right reference and total.
    entries = client.get("/journal-entries").json()
    settle_entries = [
        e for e in entries if e.get("reference", "").startswith("SETTLE-AGG:")
    ]
    assert len(settle_entries) == 1
    je = settle_entries[0]
    # 250 + 175.50 = 425.50
    debit_line = next(line for line in je["lines"] if line["account_code"] == "5000")
    credit_line = next(line for line in je["lines"] if line["account_code"] == "1000")
    assert debit_line["debit"] == "425.50"
    assert credit_line["credit"] == "425.50"

    # Cash decreased; driver wages expense recognized.
    bs = client.get("/reports/balance-sheet?as_of=2099-12-31").json()
    cash = next((line for line in bs["assets"] if line["code"] == "1000"), None)
    assert cash["amount"] == "-425.50"


def test_settlements_aggregate_idempotent(client):
    client.post("/accounts/install-default-chart")
    air = _seed_move_log()
    acct = AccountingClient(http=client)
    sync_settlements_aggregate(
        air, acct, CFG,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 15),
        dry_run=False,
    )
    # Second run skips.
    rep = sync_settlements_aggregate(
        air, acct, CFG,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 15),
        dry_run=False,
    )
    assert rep.inserted == 0
    assert rep.skipped_existing == 1


def test_settlements_aggregate_dry_run_no_post(client):
    client.post("/accounts/install-default-chart")
    air = _seed_move_log()
    acct = AccountingClient(http=client)
    rep = sync_settlements_aggregate(
        air, acct, CFG,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 15),
        dry_run=True,
    )
    assert rep.inserted == 1
    assert rep.errors == []
    # But nothing was actually posted.
    entries = client.get("/journal-entries").json()
    assert not any(e.get("reference", "").startswith("SETTLE-AGG:") for e in entries)


def test_settlements_aggregate_accrual_model_uses_2100(client):
    """Pass cash_account='2100' to defer disbursement to bank rec."""
    client.post("/accounts/install-default-chart")
    air = _seed_move_log()
    acct = AccountingClient(http=client)
    sync_settlements_aggregate(
        air, acct, CFG,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 15),
        cash_account_code="2100",
        dry_run=False,
    )
    # Liability increased; cash untouched.
    bs = client.get("/reports/balance-sheet?as_of=2099-12-31").json()
    payable = next((l for l in bs["liabilities"] if l["code"] == "2100"), None)
    assert payable["amount"] == "425.50"
    cash = next((l for l in bs["assets"] if l["code"] == "1000"), None)
    assert cash is None  # zero-balance accounts excluded


def test_settlements_aggregate_owner_op_account(client):
    """Caller can route to 5010 Owner-Operator Settlements instead of 5000."""
    client.post("/accounts/install-default-chart")
    air = _seed_move_log()
    acct = AccountingClient(http=client)
    sync_settlements_aggregate(
        air, acct, CFG,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 15),
        expense_account_code="5010",
        dry_run=False,
    )
    pnl = client.get("/reports/income-statement?start=2026-01-01&end=2026-12-31").json()
    expense = next(line for line in pnl["expense"] if line["code"] == "5010")
    assert expense["amount"] == "425.50"


def test_settlements_aggregate_empty_period_reports_error(client):
    client.post("/accounts/install-default-chart")
    air = _seed_move_log()
    acct = AccountingClient(http=client)
    rep = sync_settlements_aggregate(
        air, acct, CFG,
        period_start=date(2026, 5, 1),  # outside the seeded data
        period_end=date(2026, 5, 31),
        dry_run=False,
    )
    assert rep.inserted == 0
    assert rep.errors and "No matched legs" in rep.errors[0]


def test_last_full_week_midweek_returns_prior_mon_sun():
    # Wed 2026-05-06 -> Mon 2026-04-27 .. Sun 2026-05-03
    start, end = last_full_week(date(2026, 5, 6))  # week_ends_on=6 (Sun)
    assert start == date(2026, 4, 27)
    assert end == date(2026, 5, 3)
    assert (end - start).days == 6


def test_last_full_week_on_end_day_returns_prior_week():
    # Sun 2026-05-03 IS the end-day; we still want the PRIOR week.
    start, end = last_full_week(date(2026, 5, 3))
    assert start == date(2026, 4, 20)
    assert end == date(2026, 4, 26)


def test_last_full_week_day_after_end_returns_just_completed_week():
    # Mon 2026-05-04 -> the week that just ended (Apr 27 .. May 3).
    start, end = last_full_week(date(2026, 5, 4))
    assert start == date(2026, 4, 27)
    assert end == date(2026, 5, 3)


def test_last_full_week_with_saturday_end():
    # Saturday-ending pay week (week_ends_on=5).
    start, end = last_full_week(date(2026, 5, 6), week_ends_on=5)  # Wed
    assert start == date(2026, 4, 26)  # Sun
    assert end == date(2026, 5, 2)     # Sat


def test_sync_settlements_last_week_uses_accrual_by_default(client):
    """Default cash_account is 2100 (Driver Wages Payable), not cash."""
    client.post("/accounts/install-default-chart")

    air = FakeAirtableClient()
    # Two legs in the last full Mon-Sun before today=2026-05-06.
    air.add_record(
        CFG.move_log_table_id,
        "recML-W1",
        {CFG.ml_actual_date_field: "2026-04-28", CFG.ml_driver_pay_field: 200.00},
    )
    air.add_record(
        CFG.move_log_table_id,
        "recML-W2",
        {CFG.ml_actual_date_field: "2026-05-02", CFG.ml_driver_pay_field: 150.00},
    )
    # One leg outside that week.
    air.add_record(
        CFG.move_log_table_id,
        "recML-OUT",
        {CFG.ml_actual_date_field: "2026-05-04", CFG.ml_driver_pay_field: 999.00},
    )
    acct = AccountingClient(http=client)
    rep = sync_settlements_last_week(
        air, acct, CFG, today=date(2026, 5, 6), dry_run=False
    )
    assert rep.errors == []
    assert rep.inserted == 1

    # Liability went up by $350; cash unchanged.
    bs = client.get("/reports/balance-sheet?as_of=2099-12-31").json()
    payable = next((l for l in bs["liabilities"] if l["code"] == "2100"), None)
    assert payable["amount"] == "350.00"
    cash = next((l for l in bs["assets"] if l["code"] == "1000"), None)
    assert cash is None  # zero balance not displayed


def test_sync_settlements_last_week_idempotent_across_runs(client):
    client.post("/accounts/install-default-chart")
    air = FakeAirtableClient()
    air.add_record(
        CFG.move_log_table_id,
        "recML-W3",
        {CFG.ml_actual_date_field: "2026-04-29", CFG.ml_driver_pay_field: 100.00},
    )
    acct = AccountingClient(http=client)
    sync_settlements_last_week(air, acct, CFG, today=date(2026, 5, 6), dry_run=False)
    # Second run on the same "today" -> no-op.
    rep = sync_settlements_last_week(
        air, acct, CFG, today=date(2026, 5, 6), dry_run=False
    )
    assert rep.skipped_existing == 1
    assert rep.inserted == 0


def test_unauthenticated_accounting_client_fails_clearly(unauthed_client):
    """If the AccountingClient lacks a key, every call fails. The sync
    surfaces those as per-row errors, not a top-level crash."""
    air = _seed_airtable()
    acct = AccountingClient(http=unauthed_client)
    report = run_sync(air, acct, CFG, dry_run=False, flows=["customers"])
    customers_flow = next(f for f in report.flows if f.flow == "customers")
    assert customers_flow.inserted == 0
    assert len(customers_flow.errors) >= 1
