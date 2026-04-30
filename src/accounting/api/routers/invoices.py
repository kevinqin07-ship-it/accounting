from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from accounting.api.deps import get_session
from accounting.api.schemas import InvoiceCreate, InvoiceOut
from accounting.models import Customer, Invoice, Shipment
from accounting.services import invoicing
from accounting.services.invoicing import InvoiceLineInput

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _get_invoice(session: Session, invoice_id: int) -> Invoice:
    inv = session.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found.")
    return inv


@router.get("", response_model=List[InvoiceOut])
def list_invoices(session: Session = Depends(get_session)) -> List[InvoiceOut]:
    from sqlalchemy import select

    return [
        InvoiceOut.from_model(inv)
        for inv in session.scalars(select(Invoice).order_by(Invoice.id))
    ]


@router.post("", response_model=InvoiceOut, status_code=201)
def create_invoice(
    payload: InvoiceCreate, session: Session = Depends(get_session)
) -> InvoiceOut:
    customer = session.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(
            status_code=404, detail=f"Customer {payload.customer_id} not found."
        )
    shipment = None
    if payload.shipment_id is not None:
        shipment = session.get(Shipment, payload.shipment_id)
        if shipment is None:
            raise HTTPException(
                status_code=404, detail=f"Shipment {payload.shipment_id} not found."
            )
    inv = invoicing.create_invoice(
        session,
        invoice_no=payload.invoice_no,
        customer=customer,
        issue_date=payload.issue_date,
        shipment=shipment,
        due_date=payload.due_date,
        lines=[
            InvoiceLineInput(
                description=line.description,
                revenue_account_code=line.revenue_account_code,
                amount=line.amount,
            )
            for line in payload.lines
        ],
    )
    return InvoiceOut.from_model(inv)


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, session: Session = Depends(get_session)) -> InvoiceOut:
    return InvoiceOut.from_model(_get_invoice(session, invoice_id))


@router.post("/{invoice_id}/issue", response_model=InvoiceOut)
def issue_invoice(invoice_id: int, session: Session = Depends(get_session)) -> InvoiceOut:
    inv = _get_invoice(session, invoice_id)
    invoicing.issue_invoice(session, inv)
    return InvoiceOut.from_model(inv)
