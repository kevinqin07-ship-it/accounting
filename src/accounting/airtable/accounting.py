"""Thin wrapper around the accounting HTTP API. Accepts any object that
quacks like httpx.Client (so FastAPI's TestClient works in tests)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


class _HttpClient(Protocol):
    def request(self, method: str, url: str, **kwargs) -> Any: ...
    def get(self, url: str, **kwargs) -> Any: ...
    def post(self, url: str, **kwargs) -> Any: ...


@dataclass
class AccountingClient:
    http: _HttpClient

    @classmethod
    def for_url(cls, base_url: str, api_key: str) -> "AccountingClient":
        import httpx

        return cls(
            http=httpx.Client(
                base_url=base_url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30.0,
            )
        )

    # --- helpers ---------------------------------------------------------

    def _ok(self, response, *, expect: Optional[set[int]] = None) -> dict:
        if expect is None:
            expect = {200, 201}
        if response.status_code not in expect:
            raise RuntimeError(
                f"{response.request.method} {response.request.url} -> "
                f"{response.status_code}: {response.text[:300]}"
            )
        return response.json()

    # --- customers ------------------------------------------------------

    def list_customers(self) -> List[dict]:
        return self._ok(self.http.get("/customers"))

    def upsert_customer(self, **fields) -> dict:
        return self._ok(self.http.post("/customers", json=fields))

    # --- drivers --------------------------------------------------------

    def list_drivers(self) -> List[dict]:
        return self._ok(self.http.get("/drivers"))

    def upsert_driver(self, **fields) -> dict:
        return self._ok(self.http.post("/drivers", json=fields))

    # --- shipments ------------------------------------------------------

    def get_shipment(self, shipment_no: str) -> Optional[dict]:
        r = self.http.get(f"/shipments/{shipment_no}")
        if r.status_code == 404:
            return None
        return self._ok(r)

    def create_shipment(self, **fields) -> dict:
        return self._ok(self.http.post("/shipments", json=fields))

    # --- invoices -------------------------------------------------------

    def list_invoices(self) -> List[dict]:
        return self._ok(self.http.get("/invoices"))

    def find_invoice_by_no(self, invoice_no: str) -> Optional[dict]:
        for inv in self.list_invoices():
            if inv["invoice_no"] == invoice_no:
                return inv
        return None

    def create_invoice(self, **fields) -> dict:
        return self._ok(self.http.post("/invoices", json=fields))

    def issue_invoice(self, invoice_id: int) -> dict:
        return self._ok(self.http.post(f"/invoices/{invoice_id}/issue"))

    # --- payments -------------------------------------------------------

    def receive_payment(self, **fields) -> dict:
        return self._ok(self.http.post("/payments/receive", json=fields))
