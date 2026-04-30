"""Seed an example dataset for demos and manual exploration."""

from __future__ import annotations

from datetime import date, timedelta

from accounting.db import Session, reset_db
from accounting.services import (
    billing,
    invoicing,
    ledger,
    parties,
    payments,
    shipments,
)
from accounting.services.billing import BillLineInput
from accounting.services.invoicing import InvoiceLineInput


def seed() -> None:
    """Reset the database and load demo data. Destroys ALL existing data,
    including API keys; create keys after running seed, not before."""
    reset_db()
    today = date.today()
    with Session() as session:
        ledger.install_chart(session)

        acme = parties.upsert_customer(
            session,
            code="ACME",
            name="Acme Manufacturing",
            email="ap@acme.test",
            payment_terms_days=30,
        )
        globex = parties.upsert_customer(
            session,
            code="GLBX",
            name="Globex Distribution",
            email="payables@globex.test",
            payment_terms_days=45,
        )
        pilot = parties.upsert_vendor(
            session, code="PILOT", name="Pilot Travel Centers", category="fuel"
        )
        ta = parties.upsert_vendor(
            session, code="TA", name="TA Maintenance", category="maintenance"
        )
        carrier = parties.upsert_vendor(
            session, code="SWIFTCO", name="Swift Co Trucking", category="carrier"
        )

        # Two shipments
        s1 = shipments.create_shipment(
            session,
            shipment_no="SHP-1001",
            customer_id=acme.id,
            origin="Dallas, TX",
            destination="Atlanta, GA",
            quoted_revenue=4500.00,
            pickup_date=today - timedelta(days=10),
            delivery_date=today - timedelta(days=7),
            miles=780,
            weight_lbs=42000,
        )
        s2 = shipments.create_shipment(
            session,
            shipment_no="SHP-1002",
            customer_id=globex.id,
            origin="Chicago, IL",
            destination="Newark, NJ",
            quoted_revenue=3200.00,
            pickup_date=today - timedelta(days=5),
            delivery_date=today - timedelta(days=2),
            miles=790,
            weight_lbs=38000,
        )

        # Invoices
        inv1 = invoicing.create_invoice(
            session,
            invoice_no="INV-2026-0001",
            customer=acme,
            issue_date=today - timedelta(days=7),
            shipment=s1,
            lines=[
                InvoiceLineInput("Line haul DFW->ATL", "4000", 4200.00),
                InvoiceLineInput("Fuel surcharge", "4010", 300.00),
            ],
        )
        invoicing.issue_invoice(session, inv1)

        inv2 = invoicing.create_invoice(
            session,
            invoice_no="INV-2026-0002",
            customer=globex,
            issue_date=today - timedelta(days=2),
            shipment=s2,
            lines=[
                InvoiceLineInput("Line haul CHI->EWR", "4000", 2950.00),
                InvoiceLineInput("Detention - 2 hrs", "4020", 250.00),
            ],
        )
        invoicing.issue_invoice(session, inv2)

        # Bills tied to shipments (cost of service)
        bill_fuel = billing.create_bill(
            session,
            bill_no="PILOT-9912",
            vendor=pilot,
            issue_date=today - timedelta(days=8),
            shipment=s1,
            lines=[BillLineInput("Diesel - 220 gal", "5100", 880.00)],
        )
        billing.approve_bill(session, bill_fuel)

        bill_maint = billing.create_bill(
            session,
            bill_no="TA-44210",
            vendor=ta,
            issue_date=today - timedelta(days=20),
            lines=[
                BillLineInput("Brake job - tractor 17", "5300", 1450.00),
                BillLineInput("Oil & filters", "5300", 220.00),
            ],
        )
        billing.approve_bill(session, bill_maint)

        bill_carrier = billing.create_bill(
            session,
            bill_no="SWIFT-7781",
            vendor=carrier,
            issue_date=today - timedelta(days=2),
            shipment=s2,
            lines=[BillLineInput("Brokered haul CHI->EWR", "5020", 2400.00)],
        )
        billing.approve_bill(session, bill_carrier)

        # A receipt and a payment
        payments.receive_payment(
            session,
            invoice=inv1,
            payment_date=today - timedelta(days=1),
            amount=2500.00,
            method="ach",
            reference="ACH-55512",
        )
        payments.send_payment(
            session,
            bill=bill_fuel,
            payment_date=today,
            amount=880.00,
            method="fuel_card",
            reference="FC-22198",
        )

    print("Seeded sample data.")


if __name__ == "__main__":
    seed()
