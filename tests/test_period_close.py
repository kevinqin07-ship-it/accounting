from datetime import date

import pytest

from accounting.services import ledger, period_close, reports
from accounting.services.ledger import LineSpec


def _bootstrap(session):
    ledger.install_chart(session)
    # Opening cash + equity contribution.
    ledger.post_entry(
        session,
        entry_date=date(2025, 12, 31),
        memo="Opening",
        lines=[
            LineSpec("1000", debit_cents=20_000_00),
            LineSpec("3000", credit_cents=20_000_00),
        ],
    )


def _post_revenue(session, d, amount_cents):
    ledger.post_entry(
        session,
        entry_date=d,
        memo="Revenue",
        lines=[
            LineSpec("1100", debit_cents=amount_cents),
            LineSpec("4000", credit_cents=amount_cents),
        ],
    )


def _post_expense(session, d, amount_cents):
    ledger.post_entry(
        session,
        entry_date=d,
        memo="Expense",
        lines=[
            LineSpec("5100", debit_cents=amount_cents),
            LineSpec("2000", credit_cents=amount_cents),
        ],
    )


def test_first_close_zeros_pl_and_credits_re(session):
    _bootstrap(session)
    _post_revenue(session, date(2026, 3, 15), 1_000_00)  # $1000 revenue
    _post_expense(session, date(2026, 3, 20), 300_00)  # $300 expense
    # Net income for the period = $700.

    rec = period_close.close_period(session, close_through=date(2026, 3, 31))
    assert rec.close_through_date == date(2026, 3, 31)
    # P&L accounts are now zero.
    assert ledger.account_balance(session, "4000") == 0
    assert ledger.account_balance(session, "5100") == 0
    # Retained earnings credited with $700.
    assert ledger.account_balance(session, "3100") == 70_000


def test_close_locks_post_entry_for_dates_in_period(session):
    _bootstrap(session)
    _post_revenue(session, date(2026, 3, 15), 500_00)
    period_close.close_period(session, close_through=date(2026, 3, 31))

    # On or before the close date is rejected.
    with pytest.raises(ValueError, match="closed through"):
        ledger.post_entry(
            session,
            entry_date=date(2026, 3, 31),
            memo="Late entry",
            lines=[
                LineSpec("1000", debit_cents=100),
                LineSpec("3000", credit_cents=100),
            ],
        )
    # After the close date is fine.
    ledger.post_entry(
        session,
        entry_date=date(2026, 4, 1),
        memo="Next day",
        lines=[
            LineSpec("1000", debit_cents=100),
            LineSpec("3000", credit_cents=100),
        ],
    )


def test_loss_period_debits_retained_earnings(session):
    _bootstrap(session)
    _post_revenue(session, date(2026, 3, 15), 200_00)  # $200 revenue
    _post_expense(session, date(2026, 3, 20), 800_00)  # $800 expense
    # Net loss = $600.
    period_close.close_period(session, close_through=date(2026, 3, 31))
    # Retained earnings should reflect a $600 loss (negative credit balance).
    assert ledger.account_balance(session, "3100") == -60_000


def test_consecutive_closes_only_close_new_activity(session):
    _bootstrap(session)
    _post_revenue(session, date(2026, 1, 15), 1_000_00)
    period_close.close_period(session, close_through=date(2026, 1, 31))
    # First close moved $1000 net income to RE.
    assert ledger.account_balance(session, "3100") == 100_000

    _post_revenue(session, date(2026, 2, 10), 500_00)
    _post_expense(session, date(2026, 2, 12), 200_00)
    period_close.close_period(session, close_through=date(2026, 2, 28))
    # Second close adds another $300 to RE; total $1300.
    assert ledger.account_balance(session, "3100") == 130_000
    # P&L still zero.
    assert ledger.account_balance(session, "4000") == 0
    assert ledger.account_balance(session, "5100") == 0


def test_cannot_close_backwards_or_overlap(session):
    _bootstrap(session)
    _post_revenue(session, date(2026, 1, 15), 1_000_00)
    period_close.close_period(session, close_through=date(2026, 1, 31))
    with pytest.raises(ValueError, match="already closed"):
        period_close.close_period(session, close_through=date(2026, 1, 31))
    with pytest.raises(ValueError, match="already closed"):
        period_close.close_period(session, close_through=date(2026, 1, 15))


def test_close_with_no_activity_in_window_rejects(session):
    _bootstrap(session)
    with pytest.raises(ValueError, match="No revenue or expense activity"):
        period_close.close_period(session, close_through=date(2026, 1, 31))


def test_balance_sheet_after_close_still_balances(session):
    _bootstrap(session)
    _post_revenue(session, date(2026, 1, 15), 1_000_00)
    _post_expense(session, date(2026, 1, 20), 400_00)
    period_close.close_period(session, close_through=date(2026, 1, 31))

    sheet = reports.balance_sheet(session, date(2026, 1, 31))
    # Accounting identity holds.
    assert sheet.total_assets == sheet.total_liabilities + sheet.total_equity


def test_closed_through_helper(session):
    _bootstrap(session)
    assert period_close.closed_through(session) is None
    _post_revenue(session, date(2026, 1, 15), 100_00)
    period_close.close_period(session, close_through=date(2026, 1, 31))
    assert period_close.closed_through(session) == date(2026, 1, 31)
