"""Bulk-import fuel-card transactions and roll them up into a vendor bill.

A fuel-card statement typically arrives as a CSV with one row per swipe.
We:

  1. Parse the rows (a generic schema callers can adapt their providers to).
  2. Insert each as a FuelTransaction, deduped on (vendor, external_id).
  3. Group by truck (or 'unassigned') and create one bill line per truck so
     the AP / fuel expense entry stays human-scannable.
  4. Approve the bill, posting DR Fuel / CR AP.

If a transaction is later traced to a specific shipment, that's a separate
adjustment (not modeled here).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from io import StringIO
from typing import IO, Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.chart_of_accounts import Codes
from accounting.money import to_cents
from accounting.models import Bill, Driver, FuelTransaction, Vendor
from accounting.services import billing
from accounting.services.billing import BillLineInput


@dataclass
class FuelRow:
    external_id: str
    txn_date: date
    truck_no: Optional[str]
    location: Optional[str]
    gallons: Optional[float]
    amount: float  # dollars


@dataclass
class ImportResult:
    bill: Bill
    inserted: int
    skipped_duplicates: int
    rows_per_truck: dict[str, int]


# CSV column aliases. Real-world providers vary; we keep this small and
# explicit so callers can normalize beforehand if they need to.
_COLUMNS = {
    "external_id": ("external_id", "transaction_id", "txn_id", "id"),
    "txn_date": ("txn_date", "date", "transaction_date"),
    "truck_no": ("truck_no", "unit", "unit_no", "vehicle"),
    "location": ("location", "merchant", "site"),
    "gallons": ("gallons", "qty", "quantity"),
    "amount": ("amount", "total", "net_amount"),
}


def _pick(row: dict[str, str], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        if key in row and row[key] != "":
            return row[key]
    return None


def parse_csv(text: str | IO[str]) -> List[FuelRow]:
    """Parse a fuel-card CSV. Headers are matched case-insensitively against
    a short list of common aliases per field."""
    if isinstance(text, str):
        reader = csv.DictReader(StringIO(text))
    else:
        reader = csv.DictReader(text)

    rows: List[FuelRow] = []
    for raw in reader:
        # Normalize header case so the alias lookup works regardless of source.
        norm = {k.strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items() if k}
        external_id = _pick(norm, _COLUMNS["external_id"])
        txn_date_str = _pick(norm, _COLUMNS["txn_date"])
        amount_str = _pick(norm, _COLUMNS["amount"])
        if not (external_id and txn_date_str and amount_str):
            raise ValueError(f"Fuel row missing required fields: {raw!r}")

        try:
            txn_date = datetime.strptime(txn_date_str, "%Y-%m-%d").date()
        except ValueError:
            txn_date = datetime.strptime(txn_date_str, "%m/%d/%Y").date()

        gallons_str = _pick(norm, _COLUMNS["gallons"])
        gallons = float(gallons_str) if gallons_str else None

        rows.append(
            FuelRow(
                external_id=external_id,
                txn_date=txn_date,
                truck_no=_pick(norm, _COLUMNS["truck_no"]) or None,
                location=_pick(norm, _COLUMNS["location"]) or None,
                gallons=gallons,
                amount=float(amount_str),
            )
        )
    return rows


def import_statement(
    session: Session,
    *,
    vendor: Vendor,
    rows: Sequence[FuelRow],
    bill_no: str,
    issue_date: date,
    fuel_account_code: str = Codes.FUEL,
) -> ImportResult:
    """Import fuel rows and create one rolled-up vendor bill.

    Returns the created bill (already approved) plus stats on what was
    inserted vs deduplicated."""
    if not rows:
        raise ValueError("No fuel rows provided.")

    # Dedupe against anything already imported for this vendor.
    existing = {
        ext for (ext,) in session.execute(
            select(FuelTransaction.external_id).where(FuelTransaction.vendor_id == vendor.id)
        )
    }

    fresh: List[FuelRow] = []
    skipped = 0
    for row in rows:
        if row.external_id in existing:
            skipped += 1
            continue
        fresh.append(row)

    if not fresh:
        raise ValueError("All rows were duplicates; nothing to import.")

    # Lookup drivers by truck_no so we can attach them when known.
    truck_to_driver: dict[str, Driver] = {}
    truck_nos = {r.truck_no for r in fresh if r.truck_no}
    if truck_nos:
        for d in session.scalars(select(Driver).where(Driver.truck_no.in_(truck_nos))):
            truck_to_driver[d.truck_no] = d  # type: ignore[index]

    # Group rows by truck (or 'unassigned') for the bill lines.
    by_truck: dict[str, List[FuelRow]] = {}
    for row in fresh:
        key = row.truck_no or "unassigned"
        by_truck.setdefault(key, []).append(row)

    bill_lines: List[BillLineInput] = []
    for truck_key in sorted(by_truck):
        truck_rows = by_truck[truck_key]
        total = sum(r.amount for r in truck_rows)
        gallons = sum(r.gallons for r in truck_rows if r.gallons is not None)
        label = f"Fuel - truck {truck_key}" if truck_key != "unassigned" else "Fuel - unassigned"
        if gallons:
            label += f" ({gallons:.1f} gal, {len(truck_rows)} txns)"
        else:
            label += f" ({len(truck_rows)} txns)"
        bill_lines.append(
            BillLineInput(description=label, expense_account_code=fuel_account_code, amount=total)
        )

    bill = billing.create_bill(
        session,
        bill_no=bill_no,
        vendor=vendor,
        issue_date=issue_date,
        lines=bill_lines,
    )
    billing.approve_bill(session, bill)

    for row in fresh:
        session.add(
            FuelTransaction(
                vendor_id=vendor.id,
                external_id=row.external_id,
                txn_date=row.txn_date,
                truck_no=row.truck_no,
                driver_id=truck_to_driver[row.truck_no].id if row.truck_no in truck_to_driver else None,
                location=row.location,
                gallons=row.gallons,
                amount_cents=to_cents(row.amount),
                bill_id=bill.id,
            )
        )
    session.flush()

    return ImportResult(
        bill=bill,
        inserted=len(fresh),
        skipped_duplicates=skipped,
        rows_per_truck={k: len(v) for k, v in by_truck.items()},
    )
