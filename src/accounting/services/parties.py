"""Customer and vendor management."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.models import Customer, Vendor


def upsert_customer(
    session: Session,
    *,
    code: str,
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    billing_address: Optional[str] = None,
    payment_terms_days: int = 30,
) -> Customer:
    customer = session.scalar(select(Customer).where(Customer.code == code))
    if customer is None:
        customer = Customer(code=code, name=name)
        session.add(customer)
    customer.name = name
    customer.email = email
    customer.phone = phone
    customer.billing_address = billing_address
    customer.payment_terms_days = payment_terms_days
    session.flush()
    return customer


def upsert_vendor(
    session: Session,
    *,
    code: str,
    name: str,
    category: str = "general",
    email: Optional[str] = None,
    phone: Optional[str] = None,
    remit_address: Optional[str] = None,
    payment_terms_days: int = 30,
) -> Vendor:
    vendor = session.scalar(select(Vendor).where(Vendor.code == code))
    if vendor is None:
        vendor = Vendor(code=code, name=name)
        session.add(vendor)
    vendor.name = name
    vendor.category = category
    vendor.email = email
    vendor.phone = phone
    vendor.remit_address = remit_address
    vendor.payment_terms_days = payment_terms_days
    session.flush()
    return vendor
