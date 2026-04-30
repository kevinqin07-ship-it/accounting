from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.api.deps import get_session
from accounting.api.schemas import ShipmentCreate, ShipmentOut
from accounting.api.security import read_required, write_required
from accounting.models import Shipment
from accounting.services import shipments as shipments_svc

router = APIRouter(
    prefix="/shipments", tags=["shipments"], dependencies=[Depends(read_required)]
)


@router.get("", response_model=List[ShipmentOut])
def list_shipments(session: Session = Depends(get_session)) -> List[ShipmentOut]:
    return [
        ShipmentOut.from_model(s)
        for s in session.scalars(select(Shipment).order_by(Shipment.id))
    ]


@router.post(
    "",
    response_model=ShipmentOut,
    status_code=201,
    dependencies=[Depends(write_required)],
)
def create_shipment(
    payload: ShipmentCreate, session: Session = Depends(get_session)
) -> ShipmentOut:
    s = shipments_svc.create_shipment(
        session,
        shipment_no=payload.shipment_no,
        customer_id=payload.customer_id,
        origin=payload.origin,
        destination=payload.destination,
        quoted_revenue=payload.quoted_revenue,
        pickup_date=payload.pickup_date,
        delivery_date=payload.delivery_date,
        weight_lbs=payload.weight_lbs,
        miles=payload.miles,
    )
    return ShipmentOut.from_model(s)


@router.get("/{shipment_no}", response_model=ShipmentOut)
def get_shipment(
    shipment_no: str, session: Session = Depends(get_session)
) -> ShipmentOut:
    s = session.scalar(select(Shipment).where(Shipment.shipment_no == shipment_no))
    if s is None:
        raise HTTPException(status_code=404, detail=f"Shipment {shipment_no} not found.")
    return ShipmentOut.from_model(s)
