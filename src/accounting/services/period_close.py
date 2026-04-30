"""Fiscal period close.

Closing a period:
  1. Asserts the close_through date is after every previous close.
  2. Computes per-account net activity for revenue and expense accounts
     in the window (last_close_date + 1 day .. close_through), inclusive.
  3. Posts a balanced closing journal entry that zeros out each non-zero
     revenue and expense account by reversing its net side, then routes
     the residual into retained earnings (CR for profit, DR for loss).
  4. Records a PeriodClose row pointing at the closing JE.

After the close, ledger.post_entry refuses any entry dated <= close_through.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.models import (
    Account,
    AccountType,
    JournalEntry,
    JournalLine,
    PeriodClose,
)
from accounting.services import ledger
from accounting.services.ledger import LineSpec


# Default retained-earnings account from the seeded chart of accounts.
DEFAULT_RETAINED_EARNINGS_CODE = "3100"

# Earliest date used as the "since" bound when no prior close exists.
_EPOCH = date(1900, 1, 1)


def latest_close(session: Session) -> Optional[PeriodClose]:
    """Most recent PeriodClose, or None if the books have never been closed."""
    return session.scalar(
        select(PeriodClose).order_by(PeriodClose.close_through_date.desc()).limit(1)
    )


def closed_through(session: Session) -> Optional[date]:
    rec = latest_close(session)
    return rec.close_through_date if rec is not None else None


def is_locked(session: Session, entry_date: date) -> bool:
    """Whether the given date falls inside a closed period."""
    cutoff = closed_through(session)
    return cutoff is not None and entry_date <= cutoff


def _activity_in_window(
    session: Session, account: Account, start: date, end: date
) -> tuple[int, int]:
    """Return (debit_total, credit_total) for an account over [start, end]."""
    rows = session.scalars(
        select(JournalLine)
        .join(JournalEntry)
        .where(
            JournalLine.account_id == account.id,
            JournalEntry.entry_date >= start,
            JournalEntry.entry_date <= end,
        )
    )
    d = c = 0
    for line in rows:
        d += line.debit_cents
        c += line.credit_cents
    return d, c


def close_period(
    session: Session,
    *,
    close_through: date,
    retained_earnings_code: str = DEFAULT_RETAINED_EARNINGS_CODE,
    note: Optional[str] = None,
) -> PeriodClose:
    """Close revenue and expense activity through `close_through` into
    retained earnings. Idempotent guards prevent re-closing or going
    backwards in time."""
    prior = latest_close(session)
    if prior is not None:
        if close_through <= prior.close_through_date:
            raise ValueError(
                f"Cannot close through {close_through}: already closed through "
                f"{prior.close_through_date}."
            )
        window_start = prior.close_through_date + timedelta(days=1)
    else:
        window_start = _EPOCH

    # Make sure the retained-earnings account exists before we try to use it.
    ledger.get_account(session, retained_earnings_code)

    pl_accounts = session.scalars(
        select(Account)
        .where(Account.type.in_([AccountType.REVENUE, AccountType.EXPENSE]))
        .order_by(Account.code)
    ).all()

    lines: List[LineSpec] = []
    net_credit_to_re = 0  # positive = credit retained earnings (profit)

    for account in pl_accounts:
        debit, credit = _activity_in_window(session, account, window_start, close_through)
        if account.type == AccountType.REVENUE:
            # Revenue normally has a credit balance. Net credit - debit.
            net = credit - debit
            if net == 0:
                continue
            # To zero it out, debit the account by `net` (or credit, if net is
            # negative due to refunds/contras dominating).
            if net > 0:
                lines.append(
                    LineSpec(account.code, debit_cents=net, memo=f"Close {account.name}")
                )
            else:
                lines.append(
                    LineSpec(account.code, credit_cents=-net, memo=f"Close {account.name}")
                )
            net_credit_to_re += net
        else:  # EXPENSE
            # Expense normally has a debit balance. Net debit - credit.
            net = debit - credit
            if net == 0:
                continue
            if net > 0:
                lines.append(
                    LineSpec(account.code, credit_cents=net, memo=f"Close {account.name}")
                )
            else:
                lines.append(
                    LineSpec(account.code, debit_cents=-net, memo=f"Close {account.name}")
                )
            net_credit_to_re -= net

    if not lines:
        raise ValueError(
            f"No revenue or expense activity to close in window "
            f"{window_start}..{close_through}."
        )

    # Route the residual to retained earnings. Profit (net_credit_to_re > 0)
    # becomes a credit on retained earnings; loss becomes a debit.
    if net_credit_to_re > 0:
        lines.append(
            LineSpec(
                retained_earnings_code,
                credit_cents=net_credit_to_re,
                memo="Net income to retained earnings",
            )
        )
    elif net_credit_to_re < 0:
        lines.append(
            LineSpec(
                retained_earnings_code,
                debit_cents=-net_credit_to_re,
                memo="Net loss to retained earnings",
            )
        )
    else:
        # Activity netted to zero (revenue exactly equalled expense). Add an
        # explicit zero-net line so the entry still has a retained-earnings
        # marker; assert_balanced will reject zero-amount lines, so just skip.
        pass

    closing_entry = ledger.post_entry(
        session,
        entry_date=close_through,
        memo=f"Period close through {close_through}",
        reference=f"CLOSE:{close_through.isoformat()}",
        lines=lines,
        # The closing entry itself is dated on the close-through day, which is
        # technically inside the locked range. Allow it via the bypass.
        _allow_locked=True,
    )

    rec = PeriodClose(
        close_through_date=close_through,
        closing_journal_entry_id=closing_entry.id,
        note=note,
    )
    session.add(rec)
    session.flush()
    return rec
