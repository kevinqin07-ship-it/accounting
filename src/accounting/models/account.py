"""Chart-of-accounts model."""

from __future__ import annotations

import enum
from typing import List, Optional

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from accounting.db import Base


class AccountType(str, enum.Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


class NormalSide(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"


# Assets and expenses increase on the debit side; liabilities, equity, and
# revenue increase on the credit side. This is fixed accounting convention.
NORMAL_SIDE_FOR: dict[AccountType, NormalSide] = {
    AccountType.ASSET: NormalSide.DEBIT,
    AccountType.EXPENSE: NormalSide.DEBIT,
    AccountType.LIABILITY: NormalSide.CREDIT,
    AccountType.EQUITY: NormalSide.CREDIT,
    AccountType.REVENUE: NormalSide.CREDIT,
}


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("code", name="uq_account_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[AccountType] = mapped_column(Enum(AccountType))
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id"))
    description: Mapped[Optional[str]] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(default=True)

    parent: Mapped[Optional["Account"]] = relationship(remote_side="Account.id", backref="children")
    lines: Mapped[List["JournalLine"]] = relationship(back_populates="account")  # type: ignore[name-defined]

    @property
    def normal_side(self) -> NormalSide:
        return NORMAL_SIDE_FOR[self.type]

    def __repr__(self) -> str:
        return f"<Account {self.code} {self.name} ({self.type.value})>"
