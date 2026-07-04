from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from ._common import _dollars


class ShipmentCreate(BaseModel):
    shipment_no: str
    customer_id: int
    origin: str
    destination: str
    quoted_revenue: Decimal
    pickup_date: Optional[date] = None
    delivery_date: Optional[date] = None
    weight_lbs: Optional[int] = None
    miles: Optional[int] = None


class ShipmentOut(BaseModel):
    id: int
    shipment_no: str
    customer_id: int
    origin: str
    destination: str
    pickup_date: Optional[date] = None
    delivery_date: Optional[date] = None
    weight_lbs: Optional[int] = None
    miles: Optional[int] = None
    status: str
    quoted_revenue: Decimal

    @classmethod
    def from_model(cls, s) -> "ShipmentOut":
        return cls(
            id=s.id,
            shipment_no=s.shipment_no,
            customer_id=s.customer_id,
            origin=s.origin,
            destination=s.destination,
            pickup_date=s.pickup_date,
            delivery_date=s.delivery_date,
            weight_lbs=s.weight_lbs,
            miles=s.miles,
            status=s.status.value,
            quoted_revenue=_dollars(s.quoted_revenue_cents),
        )
