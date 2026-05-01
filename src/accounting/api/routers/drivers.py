from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.api.deps import get_session
from accounting.api.schemas import DriverCreate, DriverOut
from accounting.api.security import read_required, write_required
from accounting.models import Driver, DriverType
from accounting.services import settlements as settlements_svc

router = APIRouter(
    prefix="/drivers", tags=["drivers"], dependencies=[Depends(read_required)]
)


@router.get("", response_model=List[DriverOut])
def list_drivers(session: Session = Depends(get_session)) -> List[DriverOut]:
    return [
        DriverOut.from_model(d)
        for d in session.scalars(select(Driver).order_by(Driver.code))
    ]


@router.post(
    "",
    response_model=DriverOut,
    status_code=201,
    dependencies=[Depends(write_required)],
)
def upsert_driver(
    payload: DriverCreate, session: Session = Depends(get_session)
) -> DriverOut:
    try:
        driver_type = DriverType(payload.driver_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown driver_type {payload.driver_type!r}; allowed: "
            f"{[t.value for t in DriverType]}",
        )
    d = settlements_svc.upsert_driver(
        session,
        code=payload.code,
        name=payload.name,
        driver_type=driver_type,
        cents_per_mile=payload.cents_per_mile,
        truck_no=payload.truck_no,
    )
    return DriverOut.from_model(d)


@router.get("/{driver_id}", response_model=DriverOut)
def get_driver(driver_id: int, session: Session = Depends(get_session)) -> DriverOut:
    d = session.get(Driver, driver_id)
    if d is None:
        raise HTTPException(status_code=404, detail=f"Driver {driver_id} not found.")
    return DriverOut.from_model(d)
