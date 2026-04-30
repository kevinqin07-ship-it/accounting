from datetime import date

import pytest

from accounting.models import DriverType, SettlementStatus
from accounting.services import ledger, settlements
from accounting.services.settlements import DeductionLine, EarningLine


def _bootstrap(session, *, driver_type=DriverType.EMPLOYEE):
    ledger.install_chart(session)
    return settlements.upsert_driver(
        session,
        code="DRV1",
        name="Pat Trucker",
        driver_type=driver_type,
        cents_per_mile=60,
        truck_no="T-17",
    )


def test_employee_settlement_posts_balanced(session):
    driver = _bootstrap(session)
    s = settlements.create_settlement(
        session,
        settlement_no="STL-1",
        driver=driver,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 7),
        issue_date=date(2026, 4, 8),
        earnings=[EarningLine("Per-mile pay - 1000 mi", 600.00)],
        deductions=[DeductionLine("Fuel-card recovery", 50.00, recovery_account_code="5100")],
    )
    settlements.approve_settlement(session, s)

    assert s.status == SettlementStatus.APPROVED
    # Driver wages debit, fuel credit (recovery), wages payable credit.
    assert ledger.account_balance(session, "5000") == 60_000
    assert ledger.account_balance(session, "5100") == -5_000  # negative because we credited it
    assert ledger.account_balance(session, "2100") == 55_000  # net pay payable


def test_owner_operator_uses_5010(session):
    driver = _bootstrap(session, driver_type=DriverType.OWNER_OPERATOR)
    s = settlements.create_settlement(
        session,
        settlement_no="STL-2",
        driver=driver,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 7),
        issue_date=date(2026, 4, 8),
        earnings=[EarningLine("Linehaul", 1500.00)],
    )
    settlements.approve_settlement(session, s)
    assert ledger.account_balance(session, "5010") == 150_000
    assert ledger.account_balance(session, "5000") == 0
    assert ledger.account_balance(session, "2100") == 150_000


def test_pay_settlement_clears_payable(session):
    driver = _bootstrap(session)
    s = settlements.create_settlement(
        session,
        settlement_no="STL-3",
        driver=driver,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 7),
        issue_date=date(2026, 4, 8),
        earnings=[EarningLine("Per-mile", 800.00)],
    )
    settlements.approve_settlement(session, s)
    settlements.pay_settlement(session, s, payment_date=date(2026, 4, 12))
    assert s.status == SettlementStatus.PAID
    assert ledger.account_balance(session, "2100") == 0
    assert ledger.account_balance(session, "1000") == -80_000  # cash decreased


def test_deductions_cannot_exceed_gross(session):
    driver = _bootstrap(session)
    s = settlements.create_settlement(
        session,
        settlement_no="STL-4",
        driver=driver,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 7),
        issue_date=date(2026, 4, 8),
        earnings=[EarningLine("Per-mile", 100.00)],
        deductions=[DeductionLine("Big advance", 200.00, recovery_account_code="5100")],
    )
    with pytest.raises(ValueError, match="deductions cannot exceed"):
        settlements.approve_settlement(session, s)
