"""Fuel-card transactions imported from a card provider's statement."""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from accounting.db import Base


class FuelTransaction(Base):
    __tablename__ = "fuel_transactions"
    __table_args__ = (
        UniqueConstraint("vendor_id", "external_id", name="uq_fuel_vendor_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    txn_date: Mapped[date] = mapped_column(Date, index=True)
    truck_no: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    driver_id: Mapped[Optional[int]] = mapped_column(ForeignKey("drivers.id"))
    location: Mapped[Optional[str]] = mapped_column(String(128))
    gallons: Mapped[Optional[float]] = mapped_column(Numeric(10, 3))
    amount_cents: Mapped[int] = mapped_column(Integer)
    bill_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bills.id"))

    vendor: Mapped["Vendor"] = relationship()  # type: ignore[name-defined]
    driver: Mapped[Optional["Driver"]] = relationship()  # type: ignore[name-defined]
    bill: Mapped[Optional["Bill"]] = relationship()  # type: ignore[name-defined]
