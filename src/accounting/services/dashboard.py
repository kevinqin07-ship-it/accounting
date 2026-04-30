"""Dashboard data aggregator. Pulls a snapshot from the existing services
into a single dataclass that templates can render directly."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.chart_of_accounts import Codes
from accounting.models import Reconciliation, ReconciliationStatus, Shipment
from accounting.services import bank_rec as bank_rec_svc
from accounting.services import ledger, notifications, period_close, reports


@dataclass
class ShipmentRow:
    shipment_no: str
    customer_name: str
    origin: str
    destination: str
    revenue_cents: int
    cost_cents: int
    margin_cents: int


@dataclass
class DashboardSnapshot:
    as_of: date
    ytd_start: date
    cash_cents: int
    ar_cents: int
    ap_cents: int
    ar_overdue_cents: int  # subset of ar_cents, days_past_due > 0
    revenue_ytd_cents: int
    expense_ytd_cents: int
    net_income_ytd_cents: int
    aging_buckets: dict[str, int]
    recent_shipments: List[ShipmentRow] = field(default_factory=list)
    open_reconciliations: int = 0
    last_reconciliation_finalized: Optional[date] = None
    closed_through: Optional[date] = None


def build_snapshot(
    session: Session,
    *,
    as_of: Optional[date] = None,
    cash_account_code: str = Codes.OPERATING_CASH,
    recent_shipment_limit: int = 10,
) -> DashboardSnapshot:
    today = as_of or date.today()
    ytd_start = today.replace(month=1, day=1)

    cash = ledger.account_balance(session, cash_account_code, as_of=today)
    ar = ledger.account_balance(session, Codes.ACCOUNTS_RECEIVABLE, as_of=today)
    ap = ledger.account_balance(session, Codes.ACCOUNTS_PAYABLE, as_of=today)

    digest = notifications.build_ar_digest(session, as_of=today)
    overdue = sum(
        digest.bucket_totals_cents[label]
        for label in digest.bucket_totals_cents
        if label != "Current"
    )

    pnl = reports.income_statement(session, ytd_start, today)

    # Recent shipments — most recent N by id, with their attached invoice
    # revenue and bill costs (mirrors reports.shipment_pnl).
    shipments = list(
        session.scalars(
            select(Shipment).order_by(Shipment.id.desc()).limit(recent_shipment_limit)
        )
    )
    recent: List[ShipmentRow] = []
    for s in shipments:
        pnl_row = reports.shipment_pnl(session, s)
        recent.append(
            ShipmentRow(
                shipment_no=s.shipment_no,
                customer_name=s.customer.name if s.customer else "—",
                origin=s.origin,
                destination=s.destination,
                revenue_cents=pnl_row.revenue_cents,
                cost_cents=pnl_row.cost_cents,
                margin_cents=pnl_row.margin_cents,
            )
        )

    open_rec = session.scalar(
        select(__import__("sqlalchemy").func.count(Reconciliation.id)).where(
            Reconciliation.status == ReconciliationStatus.OPEN
        )
    ) or 0
    last_rec = session.scalar(
        select(Reconciliation.period_end)
        .where(Reconciliation.status == ReconciliationStatus.FINALIZED)
        .order_by(Reconciliation.period_end.desc())
        .limit(1)
    )

    return DashboardSnapshot(
        as_of=today,
        ytd_start=ytd_start,
        cash_cents=cash,
        ar_cents=ar,
        ap_cents=ap,
        ar_overdue_cents=overdue,
        revenue_ytd_cents=pnl.total_revenue,
        expense_ytd_cents=pnl.total_expense,
        net_income_ytd_cents=pnl.net_income,
        aging_buckets=dict(digest.bucket_totals_cents),
        recent_shipments=recent,
        open_reconciliations=int(open_rec),
        last_reconciliation_finalized=last_rec,
        closed_through=period_close.closed_through(session),
    )
