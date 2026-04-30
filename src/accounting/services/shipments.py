"""Shipment lifecycle helpers."""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.money import to_cents, Number
from accounting.models import Shipment, ShipmentStatus


def create_shipment(
    session: Session,
    *,
    shipment_no: str,
    customer_id: int,
    origin: str,
    destination: str,
    quoted_revenue: Number,
    pickup_date: Optional[date] = None,
    delivery_date: Optional[date] = None,
    weight_lbs: Optional[int] = None,
    miles: Optional[int] = None,
) -> Shipment:
    if session.scalar(select(Shipment).where(Shipment.shipment_no == shipment_no)):
        raise ValueError(f"Shipment {shipment_no} already exists.")
    shipment = Shipment(
        shipment_no=shipment_no,
        customer_id=customer_id,
        origin=origin,
        destination=destination,
        pickup_date=pickup_date,
        delivery_date=delivery_date,
        weight_lbs=weight_lbs,
        miles=miles,
        quoted_revenue_cents=to_cents(quoted_revenue),
        status=ShipmentStatus.QUOTED,
    )
    session.add(shipment)
    session.flush()
    return shipment


def set_status(session: Session, shipment_id: int, status: ShipmentStatus) -> Shipment:
    shipment = session.get(Shipment, shipment_id)
    if shipment is None:
        raise LookupError(f"Shipment id={shipment_id} not found.")
    shipment.status = status
    session.flush()
    return shipment
