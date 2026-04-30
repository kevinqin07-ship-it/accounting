"""Fiscal period closes.

Each row represents one period-close event. The latest row's
`close_through_date` defines the lock cutoff: no journal entry may be posted
with `entry_date <= close_through_date`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from accounting.db import Base


class PeriodClose(Base):
    __tablename__ = "period_closes"
    __table_args__ = (
        UniqueConstraint("close_through_date", name="uq_period_close_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    close_through_date: Mapped[date] = mapped_column(Date, index=True)
    closing_journal_entry_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("journal_entries.id")
    )
    closed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    note: Mapped[Optional[str]] = mapped_column(String(256))

    closing_journal_entry: Mapped[Optional["JournalEntry"]] = relationship()  # type: ignore[name-defined]
