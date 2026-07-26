from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CloseIn(BaseModel):
    close_through: date
    retained_earnings_code: str = "3100"
    note: Optional[str] = None


class CloseOut(BaseModel):
    id: int
    close_through_date: date
    closing_journal_entry_id: Optional[int]
    closed_at: datetime
    note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CloseStatusOut(BaseModel):
    closed_through: Optional[date]
