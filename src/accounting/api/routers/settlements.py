from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.api.deps import get_session
from accounting.api.schemas import (
    SettlementCreate,
    SettlementOut,
    SettlementPayIn,
)
from accounting.api.security import read_required, write_required
from accounting.models import Driver, Settlement, Shipment
from accounting.services import settlements as settlements_svc
from accounting.services.settlements import DeductionLine, EarningLine

router = APIRouter(
    prefix="/settlements", tags=["settlements"], dependencies=[Depends(read_required)]
)


def _get_settlement(session: Session, settlement_id: int) -> Settlement:
    s = session.get(Settlement, settlement_id)
    if s is None:
        raise HTTPException(
            status_code=404, detail=f"Settlement {settlement_id} not found."
        )
    return s


@router.get("", response_model=List[SettlementOut])
def list_settlements(session: Session = Depends(get_session)) -> List[SettlementOut]:
    return [
        SettlementOut.from_model(s)
        for s in session.scalars(select(Settlement).order_by(Settlement.id))
    ]


@router.post(
    "",
    response_model=SettlementOut,
    status_code=201,
    dependencies=[Depends(write_required)],
)
def create_settlement(
    payload: SettlementCreate, session: Session = Depends(get_session)
) -> SettlementOut:
    driver = session.get(Driver, payload.driver_id)
    if driver is None:
        raise HTTPException(
            status_code=404, detail=f"Driver {payload.driver_id} not found."
        )

    earning_lines = []
    for line in payload.earnings:
        shipment = None
        if line.shipment_id is not None:
            shipment = session.get(Shipment, line.shipment_id)
            if shipment is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Shipment {line.shipment_id} not found.",
                )
        earning_lines.append(
            EarningLine(
                description=line.description,
                amount=line.amount,
                expense_account_code=line.expense_account_code,
                shipment=shipment,
            )
        )

    deduction_lines = [
        DeductionLine(
            description=line.description,
            amount=line.amount,
            recovery_account_code=line.recovery_account_code,
        )
        for line in payload.deductions
    ]

    settlement = settlements_svc.create_settlement(
        session,
        settlement_no=payload.settlement_no,
        driver=driver,
        period_start=payload.period_start,
        period_end=payload.period_end,
        issue_date=payload.issue_date,
        earnings=earning_lines,
        deductions=deduction_lines,
    )
    return SettlementOut.from_model(settlement)


@router.get("/{settlement_id}", response_model=SettlementOut)
def get_settlement(
    settlement_id: int, session: Session = Depends(get_session)
) -> SettlementOut:
    return SettlementOut.from_model(_get_settlement(session, settlement_id))


@router.post(
    "/{settlement_id}/approve",
    response_model=SettlementOut,
    dependencies=[Depends(write_required)],
)
def approve_settlement(
    settlement_id: int, session: Session = Depends(get_session)
) -> SettlementOut:
    s = _get_settlement(session, settlement_id)
    settlements_svc.approve_settlement(session, s)
    return SettlementOut.from_model(s)


@router.post(
    "/{settlement_id}/pay",
    response_model=SettlementOut,
    dependencies=[Depends(write_required)],
)
def pay_settlement(
    settlement_id: int,
    payload: SettlementPayIn,
    session: Session = Depends(get_session),
) -> SettlementOut:
    s = _get_settlement(session, settlement_id)
    settlements_svc.pay_settlement(
        session,
        s,
        payment_date=payload.payment_date,
        cash_account_code=payload.cash_account_code,
        method=payload.method,
        reference=payload.reference,
    )
    return SettlementOut.from_model(s)
