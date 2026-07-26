from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class DriverCreate(BaseModel):
    code: str
    name: str
    driver_type: str  # "employee" | "owner_operator"
    cents_per_mile: Optional[int] = None
    truck_no: Optional[str] = None


class DriverOut(BaseModel):
    id: int
    code: str
    name: str
    driver_type: str
    cents_per_mile: Optional[int] = None
    truck_no: Optional[str] = None
    is_active: bool

    @classmethod
    def from_model(cls, d) -> "DriverOut":
        return cls(
            id=d.id,
            code=d.code,
            name=d.name,
            driver_type=d.driver_type.value,
            cents_per_mile=d.cents_per_mile,
            truck_no=d.truck_no,
            is_active=d.is_active,
        )
