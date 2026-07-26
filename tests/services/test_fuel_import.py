from datetime import date

import pytest
from sqlalchemy import select

from accounting.models import DriverType, FuelTransaction
from accounting.services import fuel_import, ledger, parties, settlements
from accounting.services.fuel_import import FuelRow


CSV = """transaction_id,date,unit,merchant,gallons,amount
PILOT-1,2026-04-10,T-17,Pilot #281 Dallas TX,120.5,455.00
PILOT-2,2026-04-11,T-17,Loves #44 Memphis TN,100.0,378.00
PILOT-3,2026-04-12,T-22,Pilot #19 Atlanta GA,90.0,342.00
PILOT-4,2026-04-12,,Loves #44 Memphis TN,30.0,114.00
"""


def _bootstrap(session):
    ledger.install_chart(session)
    vendor = parties.upsert_vendor(session, code="PILOT", name="Pilot", category="fuel")
    return vendor


def test_parse_csv_handles_aliases(session):
    rows = fuel_import.parse_csv(CSV)
    assert len(rows) == 4
    assert rows[0].external_id == "PILOT-1"
    assert rows[0].truck_no == "T-17"
    assert rows[0].gallons == pytest.approx(120.5)
    assert rows[0].amount == pytest.approx(455.00)
    assert rows[3].truck_no is None


def test_import_creates_per_truck_bill(session):
    vendor = _bootstrap(session)
    rows = fuel_import.parse_csv(CSV)
    result = fuel_import.import_statement(
        session,
        vendor=vendor,
        rows=rows,
        bill_no="PILOT-STMT-APR",
        issue_date=date(2026, 4, 15),
    )
    assert result.inserted == 4
    assert result.skipped_duplicates == 0
    # Three trucks total: T-17, T-22, unassigned.
    assert set(result.rows_per_truck) == {"T-17", "T-22", "unassigned"}
    # Bill total = sum of amounts.
    assert result.bill.total_cents == 128_900
    # Three lines, one per truck group.
    assert len(result.bill.lines) == 3
    # Fuel expense and AP both moved.
    assert ledger.account_balance(session, "5100") == 128_900
    assert ledger.account_balance(session, "2000") == 128_900


def test_import_dedupes_on_external_id(session):
    vendor = _bootstrap(session)
    rows = fuel_import.parse_csv(CSV)
    fuel_import.import_statement(
        session,
        vendor=vendor,
        rows=rows,
        bill_no="PILOT-STMT-1",
        issue_date=date(2026, 4, 15),
    )

    # Second import with three duplicates and one new row.
    second_batch = rows + [
        FuelRow(
            external_id="PILOT-5",
            txn_date=date(2026, 4, 13),
            truck_no="T-17",
            location="Pilot #99",
            gallons=50.0,
            amount=190.00,
        )
    ]
    result = fuel_import.import_statement(
        session,
        vendor=vendor,
        rows=second_batch,
        bill_no="PILOT-STMT-2",
        issue_date=date(2026, 4, 22),
    )
    assert result.inserted == 1
    assert result.skipped_duplicates == 4
    # Only the new row hits the second bill.
    assert result.bill.total_cents == 19_000


def test_import_attaches_driver_by_truck_no(session):
    vendor = _bootstrap(session)
    settlements.upsert_driver(
        session,
        code="DRV1",
        name="Pat Trucker",
        driver_type=DriverType.EMPLOYEE,
        truck_no="T-17",
    )
    rows = fuel_import.parse_csv(CSV)
    fuel_import.import_statement(
        session,
        vendor=vendor,
        rows=rows,
        bill_no="PILOT-STMT-APR",
        issue_date=date(2026, 4, 15),
    )
    txns = session.scalars(
        select(FuelTransaction).where(FuelTransaction.truck_no == "T-17")
    ).all()
    assert len(txns) == 2
    assert all(t.driver_id is not None for t in txns)


def test_import_rejects_empty(session):
    vendor = _bootstrap(session)
    with pytest.raises(ValueError, match="No fuel rows"):
        fuel_import.import_statement(
            session, vendor=vendor, rows=[], bill_no="X", issue_date=date(2026, 4, 1)
        )
