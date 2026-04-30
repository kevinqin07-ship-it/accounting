from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from accounting.api.deps import get_session
from accounting.api.schemas import ARAgingNotifyIn, ARAgingNotifyOut
from accounting.api.security import admin_required
from accounting.money import from_cents
from accounting.services import notifications

router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(admin_required)],
)


@router.post("/ar-aging", response_model=ARAgingNotifyOut)
def send_ar_aging(
    payload: ARAgingNotifyIn, session: Session = Depends(get_session)
) -> ARAgingNotifyOut:
    digest = notifications.send_ar_aging_digest(
        session,
        recipients=payload.recipients,
        min_days_past_due=payload.min_days_past_due,
        as_of=payload.as_of,
    )
    return ARAgingNotifyOut(
        as_of=digest.as_of,
        recipients=list(payload.recipients),
        bucket_totals={
            label: str(from_cents(cents))
            for label, cents in digest.bucket_totals_cents.items()
        },
        grand_total=from_cents(digest.grand_total_cents),
        invoice_count=len(digest.rows),
    )
