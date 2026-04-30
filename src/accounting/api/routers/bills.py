from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.api.deps import get_session
from accounting.api.schemas import BillCreate, BillOut
from accounting.models import Bill, Shipment, Vendor
from accounting.services import billing
from accounting.services.billing import BillLineInput

router = APIRouter(prefix="/bills", tags=["bills"])


def _get_bill(session: Session, bill_id: int) -> Bill:
    bill = session.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail=f"Bill {bill_id} not found.")
    return bill


@router.get("", response_model=List[BillOut])
def list_bills(session: Session = Depends(get_session)) -> List[BillOut]:
    return [BillOut.from_model(b) for b in session.scalars(select(Bill).order_by(Bill.id))]


@router.post("", response_model=BillOut, status_code=201)
def create_bill(
    payload: BillCreate, session: Session = Depends(get_session)
) -> BillOut:
    vendor = session.get(Vendor, payload.vendor_id)
    if vendor is None:
        raise HTTPException(
            status_code=404, detail=f"Vendor {payload.vendor_id} not found."
        )
    shipment = None
    if payload.shipment_id is not None:
        shipment = session.get(Shipment, payload.shipment_id)
        if shipment is None:
            raise HTTPException(
                status_code=404, detail=f"Shipment {payload.shipment_id} not found."
            )
    bill = billing.create_bill(
        session,
        bill_no=payload.bill_no,
        vendor=vendor,
        issue_date=payload.issue_date,
        shipment=shipment,
        due_date=payload.due_date,
        lines=[
            BillLineInput(
                description=line.description,
                expense_account_code=line.expense_account_code,
                amount=line.amount,
            )
            for line in payload.lines
        ],
    )
    return BillOut.from_model(bill)


@router.get("/{bill_id}", response_model=BillOut)
def get_bill(bill_id: int, session: Session = Depends(get_session)) -> BillOut:
    return BillOut.from_model(_get_bill(session, bill_id))


@router.post("/{bill_id}/approve", response_model=BillOut)
def approve_bill(bill_id: int, session: Session = Depends(get_session)) -> BillOut:
    bill = _get_bill(session, bill_id)
    billing.approve_bill(session, bill)
    return BillOut.from_model(bill)
