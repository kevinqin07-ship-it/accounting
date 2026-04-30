"""Customers (shippers/consignees) and vendors (carriers, fuel, maintenance)."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from accounting.db import Base


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("code", name="uq_customer_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    email: Mapped[Optional[str]] = mapped_column(String(128))
    phone: Mapped[Optional[str]] = mapped_column(String(32))
    billing_address: Mapped[Optional[str]] = mapped_column(String(256))
    payment_terms_days: Mapped[int] = mapped_column(default=30)


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (UniqueConstraint("code", name="uq_vendor_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    email: Mapped[Optional[str]] = mapped_column(String(128))
    phone: Mapped[Optional[str]] = mapped_column(String(32))
    remit_address: Mapped[Optional[str]] = mapped_column(String(256))
    payment_terms_days: Mapped[int] = mapped_column(default=30)
    # 'fuel', 'maintenance', 'tolls', 'carrier', 'insurance', 'general'
    category: Mapped[str] = mapped_column(String(32), default="general")
