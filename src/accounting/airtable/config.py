"""Configuration for the Drayage Command Center -> accounting sync.

Field IDs are stable across renames in Airtable, so we use them directly.
The defaults below were captured from the live base
(`appFOrEfSmre47N1a`) on 2026-04-30.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass(frozen=True)
class InvoiceLineMapping:
    """Maps one Revenue Tracker currency column to one invoice line."""

    field_id: str
    field_name: str  # for logging only
    revenue_account_code: str
    description: str


@dataclass
class DrayageSyncConfig:
    base_id: str = "appFOrEfSmre47N1a"

    # --- Tables -----------------------------------------------------------
    customer_master_table_id: str = "tbleCYkqo8BD3ZBR4"
    revenue_tracker_table_id: str = "tblcUcTcF6b5BWOxU"
    driver_roster_table_id: str = "tblUFz8bS9PLF0OOp"
    move_log_table_id: str = "tblEWKV8eHfIQ7cnm"

    # --- Customer Master fields ------------------------------------------
    cm_name_field: str = "fldKX9rz9iRcGXKpu"          # Customer
    cm_email_field: str = "fldBn0xUdGY3gyIM5"         # Email
    cm_phone_field: str = "fldffNXJyfo25P6jP"         # Phone
    cm_billing_contact_field: str = "fldgcDSUaJEnhdC02"  # Billing Contact

    # --- Move Log fields (driver pay aggregate) -------------------------
    ml_actual_date_field: str = "fldLevSpO4XNdJF1g"   # Actual Date
    ml_driver_pay_field: str = "fldoBmjAm45iS7REd"    # Driver Pay ($)

    # --- Driver Roster fields --------------------------------------------
    dr_name_field: str = "fld15rcXPP5drV56b"          # Driver Name
    dr_id_field: str = "fldg6KPS4UulCqlR5"            # Driver ID (formula)
    dr_truck_field: str = "fld3k4i27f5vocajA"         # Truck #
    dr_email_field: str = "fldcjKDs2p6uE0EXb"         # Email
    dr_phone_field: str = "fld4kkuSSo9ITrG13"         # Phone

    # --- Revenue Tracker structural fields -------------------------------
    rt_load_id_field: str = "fldPCJ8Om67pF3KZs"       # Load ID (lookup)
    rt_customers_field: str = "fldejvtrOeA8OFk8G"     # Customers (lookup -> Customer Master rec)
    rt_billing_status_field: str = "fldqop4Y2B5Sw8sfa"
    rt_payment_status_field: str = "fldh2cGMGZmYq1FJC"
    rt_invoice_date_field: str = "fldk5ytrqlZYda7Ap"
    rt_invoice_no_field: str = "fldEp2n6mD11w3eou"
    rt_total_billed_field: str = "fldz5GMJSxbcGbjuV"
    rt_collected_amount_field: str = "fldR427s1jzkBE0Q1"
    rt_balance_due_field: str = "fldrhXI5GV89a9KC7"

    # Choice values used as filters / triggers.
    billing_status_billed: str = "Billed"
    payment_status_paid: str = "Paid"

    # --- Currency-column -> revenue account mapping ---------------------
    # Order matters only for log readability. Empty / zero columns are
    # skipped automatically.
    rt_invoice_lines: List[InvoiceLineMapping] = field(
        default_factory=lambda: [
            InvoiceLineMapping("fldp1SIicRtCcxFkB", "Quoted Rate ($)", "4000", "Linehaul (quoted rate)"),
            InvoiceLineMapping("fldHOxl8ckmqeX4ju", "FSC ($)", "4010", "Fuel surcharge"),
            InvoiceLineMapping("fld4sP4OqOLd9XLxj", "Detention Billed ($)", "4030", "Detention"),
            InvoiceLineMapping("fldfcfX8T3HOOdhij", "Layover Billed ($)", "4030", "Layover"),
            InvoiceLineMapping("fldExdiLJLsdQgV49", "Per Diem Billed ($)", "4040", "Container per diem"),
            InvoiceLineMapping("fldjK3N6hYLPqACDA", "Demurrage Billed ($)", "4040", "Demurrage"),
            InvoiceLineMapping("fldmwJJ69RqiSiChr", "Rail Detention Billed ($)", "4040", "Rail detention"),
            InvoiceLineMapping("fldaaJcCCwlrAh3DV", "Rail Storage Billed ($)", "4040", "Rail storage"),
            InvoiceLineMapping("fld3PyYNk4DDORMuK", "Yard Storage Billed ($)", "4040", "Yard storage"),
            InvoiceLineMapping("fld7L78MhQcrrIieC", "Chassis Split ($)", "4050", "Chassis split"),
            InvoiceLineMapping("fldTAlMvriPSLscCd", "Chassis Flip ($)", "4050", "Chassis flip"),
            InvoiceLineMapping("fldc1xkHRib6mmyJ4", "Pre-Pull Billed ($)", "4070", "Pre-pull"),
            InvoiceLineMapping("flddJR5BMA0RO6v2q", "Dry Run Billed ($)", "4070", "Dry run"),
            InvoiceLineMapping("fldNo63rDMaRLmIX2", "TONU Billed ($)", "4070", "Truck order not used"),
            InvoiceLineMapping("fldHiTWwPz7VKh5ba", "Drop Charge ($)", "4070", "Drop charge"),
            InvoiceLineMapping("fldxAmGjlAvJXjPoU", "Bobtail/Deadhead ($)", "4070", "Bobtail / deadhead"),
            InvoiceLineMapping("fldQLg2RIyjK0RtW1", "Residential Delivery ($)", "4070", "Residential delivery"),
            InvoiceLineMapping("fldagaxsk1Eaf8Qtj", "Scale Tickets ($)", "4070", "Scale tickets"),
            InvoiceLineMapping("fldjSAD2ISuDsNyTY", "Overweight ($)", "4070", "Overweight"),
            InvoiceLineMapping("fldXnB40IHefXeM4r", "Triaxle ($)", "4070", "Triaxle"),
            InvoiceLineMapping("fld0DQjkQL73mTH80", "Cancellation ($)", "4070", "Cancellation"),
            InvoiceLineMapping("fldWjXbjCWvZz0nQE", "Hazmat ($)", "4070", "Hazmat"),
            InvoiceLineMapping("fldUSS6sCAfN5TZ5L", "Reefer Services ($)", "4070", "Reefer services"),
            InvoiceLineMapping("fldWpxxKg8fft9cbZ", "Stop Off ($)", "4070", "Stop off"),
            InvoiceLineMapping("fldKodGu8L3iYQLNB", "Weekend/Holiday/After Hour ($)", "4070", "Weekend/after hours"),
            InvoiceLineMapping("fldohlCbpvv4YFll7", "Traffic Congestion (4th Qtr) ($)", "4070", "Traffic congestion"),
            InvoiceLineMapping("fldY86nFGKJEFMFHz", "Cleaning / Sweeping Trailer ($)", "4070", "Trailer cleaning"),
        ]
    )

    # --- Code prefixes ---------------------------------------------------
    customer_code_prefix: str = "AT-"
    driver_code_prefix: str = "AT-"
    shipment_no_prefix: str = "SHP-"
    invoice_no_prefix: str = "RT-"


DEFAULT_DRAYAGE_CONFIG = DrayageSyncConfig()
