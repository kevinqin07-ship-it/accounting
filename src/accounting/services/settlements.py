"""Driver settlements (pay runs).

A settlement bundles a driver's earnings (per-mile pay, per-load pay, accessorials)
and deductions (advances, fuel-card recovery, equipment lease) for a pay period
and posts them as one balanced journal entry:

  DR  wage / contractor expense (per earning line)
      CR  Driver Wages Payable (net amount owed to the driver)
      CR  deduction recovery accounts (e.g. recover fuel from the fuel expense)

The CR-side recoveries reduce the original expense or clear an advance. When
the settlement is paid, Driver Wages Payable is debited and cash is credited
through the standard payment flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Sequence

from sqlalchemy.orm import Session

from accounting.chart_of_accounts import Codes
from accounting.money import Number, to_cents
from accounting.models import (
    Driver,
    DriverType,
    Settlement,
    SettlementLine,
    SettlementStatus,
    Shipment,
)
from accounting.services import ledger
from accounting.services.ledger import LineSpec


# Driver-type-specific defaults. Employees go to driver wages (5000); owner-
# operators are independent contractors and go to the owner-operator
# settlements account (5010).
DEFAULT_EARNING_ACCOUNT_FOR: dict[DriverType, str] = {
    DriverType.EMPLOYEE: "5000",
    DriverType.OWNER_OPERATOR: "5010",
}

# Account 2100 is "Driver Wages Payable". For 1099 contractors we still credit
# the same payable account as a generic amount-owed-to-driver bucket; in a
# more elaborate system you'd split AP for contractors out separately.
DRIVER_PAYABLE_CODE = "2100"


@dataclass
class EarningLine:
    description: str
    amount: Number
    expense_account_code: Optional[str] = None  # defaults from driver type
    shipment: Optional[Shipment] = None


@dataclass
class DeductionLine:
    """A deduction reduces the driver's net pay. The 'recovery_account_code'
    is the account that gets credited (typically the original expense account
    you're recovering, like 5100 Fuel for a fuel-card recovery)."""

    description: str
    amount: Number
    recovery_account_code: str


def upsert_driver(
    session: Session,
    *,
    code: str,
    name: str,
    driver_type: DriverType,
    cents_per_mile: Optional[int] = None,
    truck_no: Optional[str] = None,
) -> Driver:
    from sqlalchemy import select

    driver = session.scalar(select(Driver).where(Driver.code == code))
    if driver is None:
        driver = Driver(code=code, name=name, driver_type=driver_type)
        session.add(driver)
    driver.name = name
    driver.driver_type = driver_type
    driver.cents_per_mile = cents_per_mile
    driver.truck_no = truck_no
    session.flush()
    return driver


def create_settlement(
    session: Session,
    *,
    settlement_no: str,
    driver: Driver,
    period_start: date,
    period_end: date,
    issue_date: date,
    earnings: Sequence[EarningLine],
    deductions: Sequence[DeductionLine] = (),
) -> Settlement:
    if not earnings:
        raise ValueError("A settlement needs at least one earning line.")

    settlement = Settlement(
        settlement_no=settlement_no,
        driver_id=driver.id,
        period_start=period_start,
        period_end=period_end,
        issue_date=issue_date,
        status=SettlementStatus.DRAFT,
    )

    default_expense = DEFAULT_EARNING_ACCOUNT_FOR[driver.driver_type]

    for earning in earnings:
        code = earning.expense_account_code or default_expense
        account = ledger.get_account(session, code)
        settlement.lines.append(
            SettlementLine(
                kind="earning",
                description=earning.description,
                expense_account_id=account.id,
                amount_cents=to_cents(earning.amount),
                shipment_id=earning.shipment.id if earning.shipment else None,
            )
        )

    for deduction in deductions:
        recovery = ledger.get_account(session, deduction.recovery_account_code)
        settlement.lines.append(
            SettlementLine(
                kind="deduction",
                description=deduction.description,
                expense_account_id=recovery.id,
                amount_cents=to_cents(deduction.amount),
            )
        )

    session.add(settlement)
    session.flush()
    return settlement


def approve_settlement(session: Session, settlement: Settlement) -> Settlement:
    """Post the journal entry. Net pay lands in Driver Wages Payable."""
    if settlement.status != SettlementStatus.DRAFT:
        raise ValueError(
            f"Settlement {settlement.settlement_no} is not in DRAFT (status={settlement.status})."
        )
    if settlement.gross_cents <= 0:
        raise ValueError("Settlement gross must be positive.")
    if settlement.deductions_cents > settlement.gross_cents:
        raise ValueError("Settlement deductions cannot exceed gross earnings.")

    entry_lines: List[LineSpec] = []
    for line in settlement.lines:
        if line.kind == "earning":
            entry_lines.append(
                LineSpec(
                    account_code=line.expense_account.code,
                    debit_cents=line.amount_cents,
                    memo=line.description,
                )
            )
        else:  # deduction
            entry_lines.append(
                LineSpec(
                    account_code=line.expense_account.code,
                    credit_cents=line.amount_cents,
                    memo=f"Deduction recovery - {line.description}",
                )
            )
    # Net pay owed to the driver.
    entry_lines.append(
        LineSpec(
            account_code=DRIVER_PAYABLE_CODE,
            credit_cents=settlement.net_cents,
            memo=f"Settlement {settlement.settlement_no} - net pay",
        )
    )

    entry = ledger.post_entry(
        session,
        entry_date=settlement.issue_date,
        memo=f"Settlement {settlement.settlement_no}",
        reference=f"STL:{settlement.settlement_no}",
        lines=entry_lines,
    )
    settlement.journal_entry_id = entry.id
    settlement.status = SettlementStatus.APPROVED
    session.flush()
    return settlement


def pay_settlement(
    session: Session,
    settlement: Settlement,
    *,
    payment_date: date,
    cash_account_code: str = Codes.OPERATING_CASH,
    method: str = "ach",
    reference: Optional[str] = None,
) -> Settlement:
    """Disburse the net pay: DR Driver Wages Payable, CR cash."""
    if settlement.status != SettlementStatus.APPROVED:
        raise ValueError(
            f"Settlement {settlement.settlement_no} must be APPROVED before payment."
        )
    if settlement.net_cents <= 0:
        # Fully offset by deductions; nothing to disburse.
        settlement.status = SettlementStatus.PAID
        session.flush()
        return settlement

    ledger.post_entry(
        session,
        entry_date=payment_date,
        memo=f"Pay settlement {settlement.settlement_no}",
        reference=f"PMT:STL:{settlement.settlement_no}",
        lines=[
            LineSpec(
                account_code=DRIVER_PAYABLE_CODE,
                debit_cents=settlement.net_cents,
                memo=f"Clear payable - {settlement.settlement_no}",
            ),
            LineSpec(
                account_code=cash_account_code,
                credit_cents=settlement.net_cents,
                memo=f"Driver pay - {method}{(' ' + reference) if reference else ''}",
            ),
        ],
    )
    settlement.status = SettlementStatus.PAID
    session.flush()
    return settlement
