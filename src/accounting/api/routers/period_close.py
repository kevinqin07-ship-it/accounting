from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from accounting.api.deps import get_session
from accounting.api.schemas import CloseIn, CloseOut, CloseStatusOut
from accounting.services import period_close

router = APIRouter(prefix="/period-close", tags=["period-close"])


@router.get("", response_model=CloseStatusOut)
def status(session: Session = Depends(get_session)) -> CloseStatusOut:
    return CloseStatusOut(closed_through=period_close.closed_through(session))


@router.post("", response_model=CloseOut, status_code=201)
def close(payload: CloseIn, session: Session = Depends(get_session)) -> CloseOut:
    rec = period_close.close_period(
        session,
        close_through=payload.close_through,
        retained_earnings_code=payload.retained_earnings_code,
        note=payload.note,
    )
    return CloseOut.model_validate(rec)
