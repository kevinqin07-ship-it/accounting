from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.api.deps import get_session
from accounting.api.schemas import JournalEntryIn, JournalEntryOut
from accounting.models import JournalEntry
from accounting.money import to_cents
from accounting.services import ledger
from accounting.services.ledger import LineSpec

router = APIRouter(prefix="/journal-entries", tags=["journal"])


@router.get("", response_model=List[JournalEntryOut])
def list_entries(
    limit: int = Query(50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> List[JournalEntryOut]:
    rows = session.scalars(
        select(JournalEntry).order_by(JournalEntry.id.desc()).limit(limit)
    )
    return [JournalEntryOut.from_model(e) for e in rows]


@router.post("", response_model=JournalEntryOut, status_code=201)
def post_entry(
    payload: JournalEntryIn, session: Session = Depends(get_session)
) -> JournalEntryOut:
    specs = [
        LineSpec(
            account_code=line.account_code,
            debit_cents=to_cents(line.debit),
            credit_cents=to_cents(line.credit),
            memo=line.memo,
        )
        for line in payload.lines
    ]
    entry = ledger.post_entry(
        session,
        entry_date=payload.entry_date,
        memo=payload.memo,
        reference=payload.reference,
        lines=specs,
    )
    return JournalEntryOut.from_model(entry)


@router.get("/{entry_id}", response_model=JournalEntryOut)
def get_entry(
    entry_id: int, session: Session = Depends(get_session)
) -> JournalEntryOut:
    entry = session.get(JournalEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found.")
    return JournalEntryOut.from_model(entry)
