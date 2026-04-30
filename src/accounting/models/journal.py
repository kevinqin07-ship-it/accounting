"""Journal entries and lines: the immutable record of every transaction."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from accounting.db import Base


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    memo: Mapped[Optional[str]] = mapped_column(String(256))
    reference: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    posted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    lines: Mapped[List["JournalLine"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="JournalLine.id",
    )

    @property
    def total_debits(self) -> int:
        return sum(line.debit_cents for line in self.lines)

    @property
    def total_credits(self) -> int:
        return sum(line.credit_cents for line in self.lines)

    def assert_balanced(self) -> None:
        """Raise ValueError unless debits equal credits and at least two lines exist."""
        if len(self.lines) < 2:
            raise ValueError("A journal entry must have at least two lines.")
        if self.total_debits != self.total_credits:
            raise ValueError(
                f"Journal entry is unbalanced: debits={self.total_debits} credits={self.total_credits}"
            )
        if self.total_debits == 0:
            raise ValueError("A journal entry cannot have zero total amount.")


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    debit_cents: Mapped[int] = mapped_column(Integer, default=0)
    credit_cents: Mapped[int] = mapped_column(Integer, default=0)
    memo: Mapped[Optional[str]] = mapped_column(String(256))

    entry: Mapped[JournalEntry] = relationship(back_populates="lines")
    account: Mapped["Account"] = relationship(back_populates="lines")  # type: ignore[name-defined]

    @validates("debit_cents", "credit_cents")
    def _non_negative(self, key: str, value: int) -> int:
        if value < 0:
            raise ValueError(f"{key} cannot be negative")
        return value

    def signed_amount(self) -> int:
        """Positive cents on the debit side, negative on the credit side."""
        return self.debit_cents - self.credit_cents
