"""Vendor bills: fuel, maintenance, tolls, carrier pay, insurance, etc."""

from __future__ import annotations

import enum
from datetime import date
from typing import List, Optional

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from accounting.db import Base


class BillStatus(str, enum.Enum):
    DRAFT = "draft"
    OPEN = "open"
    PARTIAL = "partial"
    PAID = "paid"
    VOID = "void"


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (UniqueConstraint("bill_no", name="uq_bill_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_no: Mapped[str] = mapped_column(String(32), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    shipment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shipments.id"))
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[BillStatus] = mapped_column(Enum(BillStatus), default=BillStatus.DRAFT)
    journal_entry_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"))

    vendor: Mapped["Vendor"] = relationship()  # type: ignore[name-defined]
    shipment: Mapped[Optional["Shipment"]] = relationship()  # type: ignore[name-defined]
    lines: Mapped[List["BillLine"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan", order_by="BillLine.id"
    )

    @property
    def total_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines)


class BillLine(Base):
    __tablename__ = "bill_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(String(256))
    expense_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    amount_cents: Mapped[int] = mapped_column(Integer)

    bill: Mapped[Bill] = relationship(back_populates="lines")
    expense_account: Mapped["Account"] = relationship()  # type: ignore[name-defined]
