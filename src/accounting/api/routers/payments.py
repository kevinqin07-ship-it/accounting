from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from accounting.api.deps import get_session
from accounting.api.schemas import PaymentOut, PaymentReceiveIn, PaymentSendIn
from accounting.models import Bill, Invoice
from accounting.services import payments as payments_svc

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/receive", response_model=PaymentOut, status_code=201)
def receive_payment(
    payload: PaymentReceiveIn, session: Session = Depends(get_session)
) -> PaymentOut:
    invoice = session.get(Invoice, payload.invoice_id)
    if invoice is None:
        raise HTTPException(
            status_code=404, detail=f"Invoice {payload.invoice_id} not found."
        )
    p = payments_svc.receive_payment(
        session,
        invoice=invoice,
        payment_date=payload.payment_date,
        amount=payload.amount,
        method=payload.method,
        reference=payload.reference,
        cash_account_code=payload.cash_account_code,
    )
    return PaymentOut.from_model(p)


@router.post("/send", response_model=PaymentOut, status_code=201)
def send_payment(
    payload: PaymentSendIn, session: Session = Depends(get_session)
) -> PaymentOut:
    bill = session.get(Bill, payload.bill_id)
    if bill is None:
        raise HTTPException(
            status_code=404, detail=f"Bill {payload.bill_id} not found."
        )
    p = payments_svc.send_payment(
        session,
        bill=bill,
        payment_date=payload.payment_date,
        amount=payload.amount,
        method=payload.method,
        reference=payload.reference,
        cash_account_code=payload.cash_account_code,
    )
    return PaymentOut.from_model(p)
