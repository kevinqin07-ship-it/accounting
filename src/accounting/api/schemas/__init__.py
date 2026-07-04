"""Pydantic schemas. Money on the wire is Decimal dollars; cents stay
internal to the service layer.

Split into one module per resource, mirroring `api/routers/*.py`; every
class is re-exported here so existing `from accounting.api.schemas import X`
imports keep working unchanged."""

from __future__ import annotations

from .accounts import AccountOut
from .auth import ApiKeyCreate, ApiKeyIssued, ApiKeyOut, LoginIn
from .bills import BillCreate, BillLineIn, BillLineOut, BillOut
from .drivers import DriverCreate, DriverOut
from .invoices import InvoiceCreate, InvoiceLineIn, InvoiceLineOut, InvoiceOut
from .journal import JournalEntryIn, JournalEntryOut, JournalLineIn, JournalLineOut
from .notifications import ARAgingNotifyIn, ARAgingNotifyOut
from .parties import CustomerCreate, CustomerOut, VendorCreate, VendorOut
from .payments import PaymentOut, PaymentReceiveIn, PaymentSendIn
from .period_close import CloseIn, CloseOut, CloseStatusOut
from .reports import (
    AgingRowOut,
    BalanceSheetOut,
    IncomeStatementOut,
    ReportLineOut,
    ShipmentPnLOut,
    TrialBalanceOut,
    TrialBalanceRow,
)
from .settlements import (
    DeductionLineIn,
    EarningLineIn,
    SettlementCreate,
    SettlementLineOut,
    SettlementOut,
    SettlementPayIn,
)
from .shipments import ShipmentCreate, ShipmentOut

__all__ = [
    "AccountOut",
    "ApiKeyCreate",
    "ApiKeyIssued",
    "ApiKeyOut",
    "LoginIn",
    "BillCreate",
    "BillLineIn",
    "BillLineOut",
    "BillOut",
    "DriverCreate",
    "DriverOut",
    "InvoiceCreate",
    "InvoiceLineIn",
    "InvoiceLineOut",
    "InvoiceOut",
    "JournalEntryIn",
    "JournalEntryOut",
    "JournalLineIn",
    "JournalLineOut",
    "ARAgingNotifyIn",
    "ARAgingNotifyOut",
    "CustomerCreate",
    "CustomerOut",
    "VendorCreate",
    "VendorOut",
    "PaymentOut",
    "PaymentReceiveIn",
    "PaymentSendIn",
    "CloseIn",
    "CloseOut",
    "CloseStatusOut",
    "AgingRowOut",
    "BalanceSheetOut",
    "IncomeStatementOut",
    "ReportLineOut",
    "ShipmentPnLOut",
    "TrialBalanceOut",
    "TrialBalanceRow",
    "DeductionLineIn",
    "EarningLineIn",
    "SettlementCreate",
    "SettlementLineOut",
    "SettlementOut",
    "SettlementPayIn",
    "ShipmentCreate",
    "ShipmentOut",
]
