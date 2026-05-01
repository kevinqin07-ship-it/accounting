"""Sync orchestration: read Airtable rows, post to the accounting API,
log what happened. Idempotent across runs.

Identifier conventions:

    accounting customer.code     = AT-{customer_master_record_id}
    accounting driver.code       = AT-{driver_roster_record_id}
    accounting shipment.shipment_no = SHP-{revenue_tracker_record_id}
    accounting invoice.invoice_no   = RT-{revenue_tracker_record_id}

Re-running is safe: customers/drivers upsert, and shipments/invoices are
keyed by the Airtable record id so the second post returns 'already
exists' which we treat as "already synced"."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Sequence

from accounting.airtable.accounting import AccountingClient
from accounting.airtable.airtable import AirtableClient
from accounting.airtable.config import DrayageSyncConfig

log = logging.getLogger(__name__)


# --- helpers -------------------------------------------------------------

def _cell(record: dict, field_id: str):
    """Return the raw value in a cell, or None if absent."""
    return record.get("fields", {}).get(field_id)


def _scalar_text(value) -> Optional[str]:
    """Many Airtable fields come back as either a plain str/number or a
    list (lookup/multipleLookupValues). Normalize to a single text value
    when possible."""
    if value is None or value == "":
        return None
    if isinstance(value, list):
        if not value:
            return None
        first = value[0]
        if isinstance(first, dict) and "name" in first:
            return first["name"]
        return str(first)
    if isinstance(value, dict):
        return value.get("name")
    return str(value)


def _scalar_number(value) -> Decimal:
    """Returns a Decimal; non-numeric values become 0."""
    if value is None:
        return Decimal("0")
    if isinstance(value, list):
        return _scalar_number(value[0] if value else None)
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _scalar_choice_name(value) -> Optional[str]:
    """singleSelect comes back as {id, name, color}."""
    if isinstance(value, dict):
        return value.get("name")
    if isinstance(value, list) and value:
        return _scalar_choice_name(value[0])
    return value if isinstance(value, str) else None


def _customer_link_record_id(record: dict, customers_field_id: str) -> Optional[str]:
    """Revenue Tracker's `Customers` is a multipleLookupValues that flattens
    to either a list of {id, name} (when linked record id is exposed) or a
    list of names. The Airtable REST shape we expect is the former when
    linked records are explicitly returned."""
    raw = _cell(record, customers_field_id)
    if not raw:
        return None
    if isinstance(raw, dict):
        # Some shapes wrap in {linkedRecordIds, valuesByLinkedRecordId}.
        ids = raw.get("linkedRecordIds")
        if ids:
            return ids[0]
    if isinstance(raw, list) and raw:
        first = raw[0]
        if isinstance(first, dict) and first.get("id"):
            return first["id"]
    return None


# --- sync report --------------------------------------------------------

@dataclass
class FlowReport:
    flow: str
    inserted: int = 0
    skipped_existing: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass
class SyncReport:
    flows: List[FlowReport] = field(default_factory=list)

    def add(self, flow: FlowReport) -> None:
        self.flows.append(flow)

    @property
    def total_errors(self) -> int:
        return sum(len(f.errors) for f in self.flows)

    def summary(self) -> str:
        lines = []
        for f in self.flows:
            lines.append(
                f"  {f.flow:<22} inserted={f.inserted:<4} skipped={f.skipped_existing:<4} "
                f"errors={len(f.errors)}"
            )
            for err in f.errors[:5]:
                lines.append(f"      ! {err}")
            if len(f.errors) > 5:
                lines.append(f"      ! (+{len(f.errors) - 5} more)")
        return "\n".join(lines)


# --- flows ---------------------------------------------------------------

def sync_customers(
    airtable: AirtableClient,
    accounting: AccountingClient,
    config: DrayageSyncConfig,
    *,
    dry_run: bool = True,
) -> FlowReport:
    rep = FlowReport(flow="customers")
    records = airtable.list_records(
        config.customer_master_table_id,
        fields=[
            config.cm_name_field,
            config.cm_email_field,
            config.cm_phone_field,
            config.cm_billing_contact_field,
        ],
    )
    for record in records:
        record_id = record["id"]
        name = _scalar_text(_cell(record, config.cm_name_field))
        if not name:
            continue
        code = f"{config.customer_code_prefix}{record_id}"
        payload = {
            "code": code,
            "name": name,
            "email": _scalar_text(_cell(record, config.cm_email_field)),
            "phone": _scalar_text(_cell(record, config.cm_phone_field)),
            "billing_address": _scalar_text(_cell(record, config.cm_billing_contact_field)),
        }
        if dry_run:
            log.info("[dry-run] customer %s -> %s", record_id, payload)
            rep.inserted += 1
            continue
        try:
            accounting.upsert_customer(**payload)
            rep.inserted += 1
        except Exception as e:
            rep.errors.append(f"{record_id}: {e}")
    return rep


def sync_drivers(
    airtable: AirtableClient,
    accounting: AccountingClient,
    config: DrayageSyncConfig,
    *,
    dry_run: bool = True,
    default_driver_type: str = "employee",
) -> FlowReport:
    rep = FlowReport(flow="drivers")
    records = airtable.list_records(
        config.driver_roster_table_id,
        fields=[
            config.dr_name_field,
            config.dr_id_field,
            config.dr_truck_field,
            config.dr_email_field,
            config.dr_phone_field,
        ],
    )
    for record in records:
        record_id = record["id"]
        name = _scalar_text(_cell(record, config.dr_name_field))
        if not name:
            continue
        code = f"{config.driver_code_prefix}{record_id}"
        truck = _scalar_text(_cell(record, config.dr_truck_field))
        payload = {
            "code": code,
            "name": name,
            "driver_type": default_driver_type,
            "truck_no": truck,
        }
        if dry_run:
            log.info("[dry-run] driver %s -> %s", record_id, payload)
            rep.inserted += 1
            continue
        try:
            accounting.upsert_driver(**payload)
            rep.inserted += 1
        except Exception as e:
            rep.errors.append(f"{record_id}: {e}")
    return rep


def _build_invoice_lines(
    record: dict, config: DrayageSyncConfig
) -> List[dict]:
    lines = []
    for mapping in config.rt_invoice_lines:
        amount = _scalar_number(_cell(record, mapping.field_id))
        if amount <= 0:
            continue
        lines.append(
            {
                "description": mapping.description,
                "revenue_account_code": mapping.revenue_account_code,
                "amount": str(amount),
            }
        )
    return lines


def sync_revenue_tracker(
    airtable: AirtableClient,
    accounting: AccountingClient,
    config: DrayageSyncConfig,
    *,
    dry_run: bool = True,
    require_billed_status: bool = True,
) -> FlowReport:
    """For each Revenue Tracker row that's marked Billed:
       1. Look up the customer by Airtable record id (sync_customers must
          have run first, or the customer must already exist).
       2. Create a shipment if SHP-{recordId} doesn't yet exist.
       3. Create + issue an invoice if RT-{recordId} doesn't yet exist.
       4. If Payment Status = Paid and Collected Amount > 0, post the
          payment."""
    rep = FlowReport(flow="revenue_tracker")
    field_ids = [
        config.rt_load_id_field,
        config.rt_customers_field,
        config.rt_billing_status_field,
        config.rt_payment_status_field,
        config.rt_invoice_date_field,
        config.rt_total_billed_field,
        config.rt_collected_amount_field,
        config.rt_balance_due_field,
    ] + [m.field_id for m in config.rt_invoice_lines]

    records = airtable.list_records(
        config.revenue_tracker_table_id, fields=field_ids
    )

    # Pre-fetch existing invoices to skip already-synced rows quickly.
    if not dry_run:
        existing_invoice_nos = {
            inv["invoice_no"] for inv in accounting.list_invoices()
        }
        existing_customer_codes = {c["code"] for c in accounting.list_customers()}
    else:
        existing_invoice_nos = set()
        existing_customer_codes = set()

    for record in records:
        record_id = record["id"]
        try:
            if require_billed_status:
                status = _scalar_choice_name(
                    _cell(record, config.rt_billing_status_field)
                )
                if status != config.billing_status_billed:
                    continue

            lines = _build_invoice_lines(record, config)
            if not lines:
                rep.errors.append(f"{record_id}: no non-zero rate columns")
                continue

            invoice_no = f"{config.invoice_no_prefix}{record_id}"
            if invoice_no in existing_invoice_nos:
                rep.skipped_existing += 1
                continue

            customer_record_id = _customer_link_record_id(
                record, config.rt_customers_field
            )
            if not customer_record_id:
                rep.errors.append(f"{record_id}: missing linked customer")
                continue
            customer_code = f"{config.customer_code_prefix}{customer_record_id}"

            issue_date = _cell(record, config.rt_invoice_date_field) or date.today().isoformat()
            shipment_no = f"{config.shipment_no_prefix}{record_id}"
            load_id = _scalar_text(_cell(record, config.rt_load_id_field)) or record_id
            origin_dest = f"Drayage / {load_id}"

            if dry_run:
                log.info(
                    "[dry-run] %s: %d lines, customer=%s, total~%s",
                    invoice_no,
                    len(lines),
                    customer_code,
                    sum(Decimal(line["amount"]) for line in lines),
                )
                rep.inserted += 1
                continue

            if customer_code not in existing_customer_codes:
                rep.errors.append(
                    f"{record_id}: customer {customer_code} not in accounting; "
                    "run sync_customers first"
                )
                continue
            customer = next(
                c for c in accounting.list_customers() if c["code"] == customer_code
            )

            shipment = accounting.get_shipment(shipment_no)
            if shipment is None:
                shipment = accounting.create_shipment(
                    shipment_no=shipment_no,
                    customer_id=customer["id"],
                    origin=origin_dest,
                    destination=origin_dest,
                    quoted_revenue=str(
                        sum(Decimal(line["amount"]) for line in lines)
                    ),
                )

            invoice = accounting.create_invoice(
                invoice_no=invoice_no,
                customer_id=customer["id"],
                shipment_id=shipment["id"],
                issue_date=issue_date,
                lines=lines,
            )
            accounting.issue_invoice(invoice["id"])
            existing_invoice_nos.add(invoice_no)
            rep.inserted += 1

            payment_status = _scalar_choice_name(
                _cell(record, config.rt_payment_status_field)
            )
            collected = _scalar_number(_cell(record, config.rt_collected_amount_field))
            if (
                payment_status == config.payment_status_paid
                and collected > 0
            ):
                accounting.receive_payment(
                    invoice_id=invoice["id"],
                    payment_date=issue_date,
                    amount=str(collected),
                )

        except Exception as e:
            rep.errors.append(f"{record_id}: {e}")

    return rep


def run_sync(
    airtable: AirtableClient,
    accounting: AccountingClient,
    config: Optional[DrayageSyncConfig] = None,
    *,
    dry_run: bool = True,
    flows: Optional[Sequence[str]] = None,
) -> SyncReport:
    """Run sync flows in order. Each flow's failures don't block the next.

    Default flows are customers + revenue_tracker. The drivers flow stays
    available behind an explicit opt-in (`flows=["drivers"]`) but isn't
    run by default — driver settlements live in Airtable, not in the
    accounting books, by design."""
    cfg = config or DrayageSyncConfig()
    requested = set(flows or ["customers", "revenue_tracker"])
    report = SyncReport()

    if "customers" in requested:
        report.add(sync_customers(airtable, accounting, cfg, dry_run=dry_run))
    if "drivers" in requested:
        report.add(sync_drivers(airtable, accounting, cfg, dry_run=dry_run))
    if "revenue_tracker" in requested:
        report.add(sync_revenue_tracker(airtable, accounting, cfg, dry_run=dry_run))

    return report
