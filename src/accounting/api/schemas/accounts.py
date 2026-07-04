from __future__ import annotations

from typing import Optional

from ._common import _ORM


class AccountOut(_ORM):
    id: int
    code: str
    name: str
    type: str
    parent_id: Optional[int] = None
    description: Optional[str] = None
    is_active: bool
