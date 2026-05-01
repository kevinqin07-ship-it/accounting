"""Drayage chart-of-accounts additions and idempotent install behavior."""

from __future__ import annotations

from accounting.chart_of_accounts import Codes
from accounting.services import ledger


DRAYAGE_REVENUE_CODES = ["4030", "4040", "4050", "4060", "4070"]
DRAYAGE_EXPENSE_CODES = ["5210", "5220", "5230", "5260"]


def test_drayage_revenue_accounts_present(session):
    ledger.install_chart(session)
    for code in DRAYAGE_REVENUE_CODES:
        acct = ledger.get_account(session, code)
        assert acct.type.value == "revenue"


def test_drayage_expense_accounts_present(session):
    ledger.install_chart(session)
    for code in DRAYAGE_EXPENSE_CODES:
        acct = ledger.get_account(session, code)
        assert acct.type.value == "expense"


def test_codes_helpers_resolve(session):
    """The Codes constants resolve to real accounts, so callers using
    ledger.get_account(session, Codes.X) work."""
    ledger.install_chart(session)
    for code in [
        Codes.DETENTION_REVENUE,
        Codes.DEMURRAGE_PER_DIEM_REVENUE,
        Codes.CHASSIS_REVENUE,
        Codes.PORT_PASSTHROUGH_REVENUE,
        Codes.DRAYAGE_ACCESSORIAL_REVENUE,
        Codes.PORT_FEES,
        Codes.CHASSIS_RENTAL,
        Codes.CONTAINER_PER_DIEM_DEMURRAGE,
        Codes.DRAYAGE_ACCESSORIAL_COSTS,
    ]:
        ledger.get_account(session, code)


def test_install_chart_is_still_idempotent_with_new_accounts(session):
    ledger.install_chart(session)
    initial = sum(1 for _ in ledger.trial_balance(session))  # zero, nothing posted
    # Second install should add nothing and not raise.
    ledger.install_chart(session)
    assert sum(1 for _ in ledger.trial_balance(session)) == initial
