from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ._common import _ORM


class CustomerCreate(BaseModel):
    code: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[str] = None
    payment_terms_days: int = 30


class CustomerOut(_ORM):
    id: int
    code: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[str] = None
    payment_terms_days: int


class VendorCreate(BaseModel):
    code: str
    name: str
    category: str = "general"
    email: Optional[str] = None
    phone: Optional[str] = None
    remit_address: Optional[str] = None
    payment_terms_days: int = 30


class VendorOut(_ORM):
    id: int
    code: str
    name: str
    category: str
    email: Optional[str] = None
    phone: Optional[str] = None
    remit_address: Optional[str] = None
    payment_terms_days: int
