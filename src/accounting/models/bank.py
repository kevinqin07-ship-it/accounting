"""Bank statement lines, reconciliations, and book/bank matches."""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from accounting.db import Base


class ReconciliationStatus(str, enum.Enum):
    OPEN = "open"
    FINALIZED = "finalized"


class BankStatementLine(Base):
    """A single transaction as reported by the bank.

    `amount_cents` is signed: positive for credits to our account (deposits,
    interest), negative for debits (checks, fees, withdrawals).
    """

    __tablename__ = "bank_statement_lines"
    __table_args__ = (
        UniqueConstraint("cash_account_id", "external_id", name="uq_bank_line_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cash_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    txn_date: Mapped[date] = mapped_column(Date, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    description: Mapped[Optional[str]] = mapped_column(String(256))
    running_balance_cents: Mapped[Optional[int]] = mapped_column(Integer)

    cash_account: Mapped["Account"] = relationship()  # type: ignore[name-defined]
    match: Mapped[Optional["BankMatch"]] = relationship(
        back_populates="bank_line", uselist=False, cascade="all, delete-orphan"
    )


class Reconciliation(Base):
    __tablename__ = "reconciliations"

    id: Mapped[int] = mapped_column(primary_key=True)
    cash_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    statement_start_balance_cents: Mapped[int] = mapped_column(Integer)
    statement_end_balance_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus), default=ReconciliationStatus.OPEN
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    cash_account: Mapped["Account"] = relationship()  # type: ignore[name-defined]
    matches: Mapped[List["BankMatch"]] = relationship(
        back_populates="reconciliation", cascade="all, delete-orphan"
    )


class BankMatch(Base):
    """A confirmed pairing of a book journal line with a bank statement line."""

    __tablename__ = "bank_matches"
    __table_args__ = (
        UniqueConstraint("journal_line_id", name="uq_bank_match_journal_line"),
        UniqueConstraint("bank_statement_line_id", name="uq_bank_match_bank_line"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reconciliation_id: Mapped[int] = mapped_column(
        ForeignKey("reconciliations.id", ondelete="CASCADE")
    )
    journal_line_id: Mapped[int] = mapped_column(ForeignKey("journal_lines.id"))
    bank_statement_line_id: Mapped[int] = mapped_column(ForeignKey("bank_statement_lines.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    note: Mapped[Optional[str]] = mapped_column(String(256))

    reconciliation: Mapped[Reconciliation] = relationship(back_populates="matches")
    journal_line: Mapped["JournalLine"] = relationship()  # type: ignore[name-defined]
    bank_line: Mapped[BankStatementLine] = relationship(back_populates="match")
