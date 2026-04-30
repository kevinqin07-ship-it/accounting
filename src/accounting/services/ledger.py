"""General-ledger operations: posting entries, fetching balances."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.chart_of_accounts import DEFAULT_CHART, AccountSpec
from accounting.models import Account, AccountType, JournalEntry, JournalLine
from accounting.models.account import NORMAL_SIDE_FOR, NormalSide


@dataclass
class LineSpec:
    """One side of a journal entry, expressed by account code."""
    account_code: str
    debit_cents: int = 0
    credit_cents: int = 0
    memo: Optional[str] = None

    def __post_init__(self) -> None:
        if self.debit_cents < 0 or self.credit_cents < 0:
            raise ValueError("Debit and credit amounts must be non-negative.")
        if self.debit_cents and self.credit_cents:
            raise ValueError("A line cannot have both a debit and a credit.")
        if not self.debit_cents and not self.credit_cents:
            raise ValueError("A line must have either a debit or a credit.")


def install_chart(session: Session, specs: Sequence[AccountSpec] = DEFAULT_CHART) -> None:
    """Insert any missing accounts from the given chart. Idempotent."""
    existing = {code for (code,) in session.execute(select(Account.code)).all()}
    for spec in specs:
        if spec.code in existing:
            continue
        session.add(
            Account(
                code=spec.code,
                name=spec.name,
                type=spec.type,
                description=spec.description or None,
            )
        )
    session.flush()


def get_account(session: Session, code: str) -> Account:
    account = session.scalar(select(Account).where(Account.code == code))
    if account is None:
        raise LookupError(f"No account with code {code!r}. Did you call install_chart()?")
    return account


def post_entry(
    session: Session,
    *,
    entry_date: date,
    memo: str,
    lines: Iterable[LineSpec],
    reference: Optional[str] = None,
    _allow_locked: bool = False,
) -> JournalEntry:
    """Create and persist a balanced journal entry. Raises if unbalanced or
    if the entry date falls inside a closed period.

    `_allow_locked` is an internal bypass for the closing journal entry
    itself (which is dated on the close-through day); ordinary callers must
    not set it.
    """
    if not _allow_locked:
        # Imported lazily to avoid a circular import: period_close depends on
        # ledger.
        from accounting.services import period_close

        if period_close.is_locked(session, entry_date):
            cutoff = period_close.closed_through(session)
            raise ValueError(
                f"Cannot post entry dated {entry_date}: books are closed through {cutoff}."
            )

    entry = JournalEntry(entry_date=entry_date, memo=memo, reference=reference)
    for spec in lines:
        account = get_account(session, spec.account_code)
        entry.lines.append(
            JournalLine(
                account=account,
                debit_cents=spec.debit_cents,
                credit_cents=spec.credit_cents,
                memo=spec.memo,
            )
        )
    entry.assert_balanced()
    session.add(entry)
    session.flush()
    return entry


def account_balance(session: Session, code: str, as_of: Optional[date] = None) -> int:
    """Signed balance for an account in cents, as of a given date.

    Positive return = balance on the account's normal side. So an asset with
    a positive return has a debit balance (money you have); an expense with
    a positive return has been incurred.
    """
    account = get_account(session, code)
    stmt = select(JournalLine).join(JournalEntry).where(JournalLine.account_id == account.id)
    if as_of is not None:
        stmt = stmt.where(JournalEntry.entry_date <= as_of)
    debit = credit = 0
    for line in session.scalars(stmt):
        debit += line.debit_cents
        credit += line.credit_cents
    if NORMAL_SIDE_FOR[account.type] == NormalSide.DEBIT:
        return debit - credit
    return credit - debit


def trial_balance(session: Session, as_of: Optional[date] = None) -> list[tuple[Account, int, int]]:
    """Return (account, debit_total, credit_total) for every active account."""
    rows: list[tuple[Account, int, int]] = []
    for account in session.scalars(select(Account).order_by(Account.code)):
        stmt = select(JournalLine).join(JournalEntry).where(JournalLine.account_id == account.id)
        if as_of is not None:
            stmt = stmt.where(JournalEntry.entry_date <= as_of)
        d = c = 0
        for line in session.scalars(stmt):
            d += line.debit_cents
            c += line.credit_cents
        if d == 0 and c == 0:
            continue
        # Net to one side based on the account's normal side. A non-zero raw
        # debit and credit can still net to zero (e.g. a P&L account after
        # a period close); skip those too.
        if NORMAL_SIDE_FOR[account.type] == NormalSide.DEBIT:
            net = d - c
        else:
            net = c - d
        if net == 0:
            continue
        if NORMAL_SIDE_FOR[account.type] == NormalSide.DEBIT:
            rows.append((account, max(net, 0), max(-net, 0)))
        else:
            rows.append((account, max(-net, 0), max(net, 0)))
    return rows
