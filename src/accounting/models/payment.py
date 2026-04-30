"""Payments: cash flowing in (against invoices) or out (against bills)."""

from __future__ import annotations

import enum
from datetime import date
from typing import Optional

from sqlalchemy import Date, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from accounting.db import Base


class PaymentDirection(str, enum.Enum):
    RECEIVED = "received"
    SENT = "sent"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    direction: Mapped[PaymentDirection] = mapped_column(Enum(PaymentDirection))
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(32), default="ach")
    reference: Mapped[Optional[str]] = mapped_column(String(64))
    cash_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    invoice_id: Mapped[Optional[int]] = mapped_column(ForeignKey("invoices.id"))
    bill_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bills.id"))
    journal_entry_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"))

    cash_account: Mapped["Account"] = relationship()  # type: ignore[name-defined]
    invoice: Mapped[Optional["Invoice"]] = relationship()  # type: ignore[name-defined]
    bill: Mapped[Optional["Bill"]] = relationship()  # type: ignore[name-defined]
