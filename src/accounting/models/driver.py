"""Drivers (employees and owner-operators) and their settlement runs."""

from __future__ import annotations

import enum
from datetime import date
from typing import List, Optional

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from accounting.db import Base


class DriverType(str, enum.Enum):
    EMPLOYEE = "employee"
    OWNER_OPERATOR = "owner_operator"


class SettlementStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    PAID = "paid"
    VOID = "void"


class Driver(Base):
    __tablename__ = "drivers"
    __table_args__ = (UniqueConstraint("code", name="uq_driver_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    driver_type: Mapped[DriverType] = mapped_column(Enum(DriverType))
    cents_per_mile: Mapped[Optional[int]] = mapped_column(Integer)
    truck_no: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    is_active: Mapped[bool] = mapped_column(default=True)


class Settlement(Base):
    """A pay run: a set of earnings and deductions, posted as one journal entry."""

    __tablename__ = "settlements"
    __table_args__ = (UniqueConstraint("settlement_no", name="uq_settlement_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_no: Mapped[str] = mapped_column(String(32), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    issue_date: Mapped[date] = mapped_column(Date)
    status: Mapped[SettlementStatus] = mapped_column(
        Enum(SettlementStatus), default=SettlementStatus.DRAFT
    )
    journal_entry_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"))

    driver: Mapped[Driver] = relationship()
    lines: Mapped[List["SettlementLine"]] = relationship(
        back_populates="settlement", cascade="all, delete-orphan", order_by="SettlementLine.id"
    )

    @property
    def gross_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines if line.kind == "earning")

    @property
    def deductions_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines if line.kind == "deduction")

    @property
    def net_cents(self) -> int:
        return self.gross_cents - self.deductions_cents


class SettlementLine(Base):
    __tablename__ = "settlement_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey("settlements.id", ondelete="CASCADE"))
    # 'earning' (per-mile, per-load, accessorial pay) or 'deduction' (advances,
    # equipment lease, fuel-card recovery, garnishments).
    kind: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(String(256))
    expense_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    amount_cents: Mapped[int] = mapped_column(Integer)
    shipment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shipments.id"))

    settlement: Mapped[Settlement] = relationship(back_populates="lines")
    expense_account: Mapped["Account"] = relationship()  # type: ignore[name-defined]
