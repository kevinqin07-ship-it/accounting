from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.api.deps import get_session
from accounting.api.schemas import AccountOut
from accounting.models import Account
from accounting.services import ledger

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=List[AccountOut])
def list_accounts(session: Session = Depends(get_session)) -> List[Account]:
    return list(session.scalars(select(Account).order_by(Account.code)))


@router.post("/install-default-chart", response_model=List[AccountOut])
def install_default_chart(session: Session = Depends(get_session)) -> List[Account]:
    ledger.install_chart(session)
    return list(session.scalars(select(Account).order_by(Account.code)))
