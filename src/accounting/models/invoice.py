"""Customer invoices for freight and accessorial services."""

from __future__ import annotations

import enum
from datetime import date
from typing import List, Optional

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from accounting.db import Base


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    OPEN = "open"
    PARTIAL = "partial"
    PAID = "paid"
    VOID = "void"


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("invoice_no", name="uq_invoice_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_no: Mapped[str] = mapped_column(String(32), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    shipment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shipments.id"))
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus), default=InvoiceStatus.DRAFT)
    journal_entry_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"))

    customer: Mapped["Customer"] = relationship()  # type: ignore[name-defined]
    shipment: Mapped[Optional["Shipment"]] = relationship()  # type: ignore[name-defined]
    lines: Mapped[List["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.id"
    )

    @property
    def total_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines)


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(String(256))
    revenue_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    amount_cents: Mapped[int] = mapped_column(Integer)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")
    revenue_account: Mapped["Account"] = relationship()  # type: ignore[name-defined]
