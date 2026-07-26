from datetime import date

import pytest

from accounting.services import ledger
from accounting.services.ledger import LineSpec


def test_install_chart_is_idempotent(session):
    ledger.install_chart(session)
    ledger.install_chart(session)
    cash = ledger.get_account(session, "1000")
    assert cash.name == "Operating Cash"


def test_post_balanced_entry(session):
    ledger.install_chart(session)
    entry = ledger.post_entry(
        session,
        entry_date=date(2026, 1, 15),
        memo="Owner contribution",
        lines=[
            LineSpec("1000", debit_cents=10_000_00),
            LineSpec("3000", credit_cents=10_000_00),
        ],
    )
    assert entry.total_debits == entry.total_credits == 10_000_00


def test_unbalanced_entry_rejected(session):
    ledger.install_chart(session)
    with pytest.raises(ValueError, match="unbalanced"):
        ledger.post_entry(
            session,
            entry_date=date(2026, 1, 15),
            memo="Bad entry",
            lines=[
                LineSpec("1000", debit_cents=100_00),
                LineSpec("3000", credit_cents=99_00),
            ],
        )


def test_line_cannot_be_both_debit_and_credit():
    with pytest.raises(ValueError):
        LineSpec("1000", debit_cents=100, credit_cents=100)


def test_line_cannot_be_zero():
    with pytest.raises(ValueError):
        LineSpec("1000")


def test_account_balance_signed_correctly(session):
    ledger.install_chart(session)
    ledger.post_entry(
        session,
        entry_date=date(2026, 1, 1),
        memo="Initial cash",
        lines=[
            LineSpec("1000", debit_cents=5_000_00),
            LineSpec("3000", credit_cents=5_000_00),
        ],
    )
    # Asset: positive debit balance.
    assert ledger.account_balance(session, "1000") == 5_000_00
    # Equity: positive credit balance.
    assert ledger.account_balance(session, "3000") == 5_000_00


def test_trial_balance_balances(session):
    ledger.install_chart(session)
    ledger.post_entry(
        session,
        entry_date=date(2026, 1, 1),
        memo="Equity",
        lines=[
            LineSpec("1000", debit_cents=10_000_00),
            LineSpec("3000", credit_cents=10_000_00),
        ],
    )
    ledger.post_entry(
        session,
        entry_date=date(2026, 1, 5),
        memo="Fuel purchase",
        lines=[
            LineSpec("5100", debit_cents=400_00),
            LineSpec("1000", credit_cents=400_00),
        ],
    )
    rows = ledger.trial_balance(session)
    total_debits = sum(d for _, d, _ in rows)
    total_credits = sum(c for _, _, c in rows)
    assert total_debits == total_credits
