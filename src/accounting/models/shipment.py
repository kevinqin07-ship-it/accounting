"""Shipments: the unit of work for a logistics business."""

from __future__ import annotations

import enum
from datetime import date
from typing import Optional

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from accounting.db import Base


class ShipmentStatus(str, enum.Enum):
    QUOTED = "quoted"
    BOOKED = "booked"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    INVOICED = "invoiced"
    CANCELLED = "cancelled"


class Shipment(Base):
    __tablename__ = "shipments"
    __table_args__ = (UniqueConstraint("shipment_no", name="uq_shipment_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_no: Mapped[str] = mapped_column(String(32), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    origin: Mapped[str] = mapped_column(String(128))
    destination: Mapped[str] = mapped_column(String(128))
    pickup_date: Mapped[Optional[date]] = mapped_column(Date)
    delivery_date: Mapped[Optional[date]] = mapped_column(Date)
    weight_lbs: Mapped[Optional[int]] = mapped_column(Integer)
    miles: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[ShipmentStatus] = mapped_column(Enum(ShipmentStatus), default=ShipmentStatus.QUOTED)
    quoted_revenue_cents: Mapped[int] = mapped_column(Integer, default=0)

    customer: Mapped["Customer"] = relationship()  # type: ignore[name-defined]
