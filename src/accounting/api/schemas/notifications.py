from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class ARAgingNotifyIn(BaseModel):
    recipients: List[str]
    min_days_past_due: int = 0
    as_of: Optional[date] = None


class ARAgingNotifyOut(BaseModel):
    as_of: date
    recipients: List[str]
    bucket_totals: dict
    grand_total: Decimal
    invoice_count: int
