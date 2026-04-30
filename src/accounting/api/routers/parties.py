from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.api.deps import get_session
from accounting.api.schemas import (
    CustomerCreate,
    CustomerOut,
    VendorCreate,
    VendorOut,
)
from accounting.api.security import read_required, write_required
from accounting.models import Customer, Vendor
from accounting.services import parties as parties_svc

customers_router = APIRouter(
    prefix="/customers", tags=["customers"], dependencies=[Depends(read_required)]
)
vendors_router = APIRouter(
    prefix="/vendors", tags=["vendors"], dependencies=[Depends(read_required)]
)


@customers_router.get("", response_model=List[CustomerOut])
def list_customers(session: Session = Depends(get_session)) -> List[Customer]:
    return list(session.scalars(select(Customer).order_by(Customer.code)))


@customers_router.post(
    "",
    response_model=CustomerOut,
    status_code=201,
    dependencies=[Depends(write_required)],
)
def create_customer(
    payload: CustomerCreate, session: Session = Depends(get_session)
) -> Customer:
    return parties_svc.upsert_customer(
        session,
        code=payload.code,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        billing_address=payload.billing_address,
        payment_terms_days=payload.payment_terms_days,
    )


@vendors_router.get("", response_model=List[VendorOut])
def list_vendors(session: Session = Depends(get_session)) -> List[Vendor]:
    return list(session.scalars(select(Vendor).order_by(Vendor.code)))


@vendors_router.post(
    "",
    response_model=VendorOut,
    status_code=201,
    dependencies=[Depends(write_required)],
)
def create_vendor(
    payload: VendorCreate, session: Session = Depends(get_session)
) -> Vendor:
    return parties_svc.upsert_vendor(
        session,
        code=payload.code,
        name=payload.name,
        category=payload.category,
        email=payload.email,
        phone=payload.phone,
        remit_address=payload.remit_address,
        payment_terms_days=payload.payment_terms_days,
    )
