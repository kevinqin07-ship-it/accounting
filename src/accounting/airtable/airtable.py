"""Airtable client: a thin Protocol so production hits the real REST API
and tests inject an in-memory fake."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Protocol


class AirtableClient(Protocol):
    """Subset of Airtable's REST API the sync needs."""

    def list_records(self, table_id: str, *, fields: Optional[List[str]] = None) -> List[dict]: ...

    def update_record(self, table_id: str, record_id: str, fields: dict) -> dict: ...


# --- Real client ---------------------------------------------------------

@dataclass
class HttpxAirtableClient:
    """Production client. Reads AIRTABLE_API_KEY from env if not provided."""

    base_id: str
    api_key: Optional[str] = None
    base_url: str = "https://api.airtable.com/v0"
    page_size: int = 100

    def __post_init__(self) -> None:
        import httpx  # imported lazily so tests don't pay the cost

        token = self.api_key or os.environ.get("AIRTABLE_API_KEY")
        if not token:
            raise RuntimeError("AIRTABLE_API_KEY is required for HttpxAirtableClient.")
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )

    def list_records(self, table_id: str, *, fields: Optional[List[str]] = None) -> List[dict]:
        out: List[dict] = []
        params: dict = {"pageSize": self.page_size}
        if fields:
            # Airtable repeats the fields[] param.
            params["fields[]"] = fields
        offset: Optional[str] = None
        while True:
            if offset:
                params["offset"] = offset
            r = self._http.get(f"/{self.base_id}/{table_id}", params=params)
            r.raise_for_status()
            payload = r.json()
            out.extend(payload.get("records", []))
            offset = payload.get("offset")
            if not offset:
                break
        return out

    def update_record(self, table_id: str, record_id: str, fields: dict) -> dict:
        r = self._http.patch(
            f"/{self.base_id}/{table_id}/{record_id}",
            json={"fields": fields, "typecast": False},
        )
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        self._http.close()


# --- Fake for tests ------------------------------------------------------

@dataclass
class FakeAirtableClient:
    """In-memory fake. Tables are dict[table_id, list[record-dict]]."""

    tables: dict = field(default_factory=dict)
    updates: List[tuple] = field(default_factory=list)  # (table_id, record_id, fields)

    def add_record(self, table_id: str, record_id: str, fields: dict) -> None:
        self.tables.setdefault(table_id, []).append({"id": record_id, "fields": fields})

    def list_records(self, table_id: str, *, fields: Optional[List[str]] = None) -> List[dict]:
        records = self.tables.get(table_id, [])
        if fields is None:
            return [dict(r) for r in records]
        out = []
        for r in records:
            filtered = {k: v for k, v in r["fields"].items() if k in fields}
            out.append({"id": r["id"], "fields": filtered})
        return out

    def update_record(self, table_id: str, record_id: str, fields: dict) -> dict:
        self.updates.append((table_id, record_id, dict(fields)))
        for r in self.tables.get(table_id, []):
            if r["id"] == record_id:
                r["fields"].update(fields)
                return r
        raise LookupError(f"Record {record_id} not found in table {table_id}.")
