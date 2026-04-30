from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.api.deps import get_session
from accounting.api.security import read_required
from accounting.api.schemas import (
    AgingRowOut,
    BalanceSheetOut,
    IncomeStatementOut,
    ReportLineOut,
    ShipmentPnLOut,
    TrialBalanceOut,
    TrialBalanceRow,
)
from accounting.models import Shipment
from accounting.money import from_cents
from accounting.services import ledger, reports

router = APIRouter(
    prefix="/reports", tags=["reports"], dependencies=[Depends(read_required)]
)


@router.get("/trial-balance", response_model=TrialBalanceOut)
def trial_balance(
    as_of: Optional[date] = None, session: Session = Depends(get_session)
) -> TrialBalanceOut:
    rows = ledger.trial_balance(session, as_of=as_of)
    out_rows = [
        TrialBalanceRow(
            code=acc.code,
            name=acc.name,
            type=acc.type.value,
            debit=from_cents(d),
            credit=from_cents(c),
        )
        for acc, d, c in rows
    ]
    return TrialBalanceOut(
        as_of=as_of,
        rows=out_rows,
        total_debit=from_cents(sum(d for _, d, _ in rows)),
        total_credit=from_cents(sum(c for _, _, c in rows)),
    )


@router.get("/income-statement", response_model=IncomeStatementOut)
def income_statement(
    start: date = Query(...),
    end: date = Query(...),
    session: Session = Depends(get_session),
) -> IncomeStatementOut:
    stmt = reports.income_statement(session, start, end)
    return IncomeStatementOut(
        start=start,
        end=end,
        revenue=[
            ReportLineOut(
                code=line.account.code,
                name=line.account.name,
                amount=from_cents(line.amount_cents),
            )
            for line in stmt.revenue
        ],
        expense=[
            ReportLineOut(
                code=line.account.code,
                name=line.account.name,
                amount=from_cents(line.amount_cents),
            )
            for line in stmt.expense
        ],
        total_revenue=from_cents(stmt.total_revenue),
        total_expense=from_cents(stmt.total_expense),
        net_income=from_cents(stmt.net_income),
    )


@router.get("/balance-sheet", response_model=BalanceSheetOut)
def balance_sheet(
    as_of: date = Query(...), session: Session = Depends(get_session)
) -> BalanceSheetOut:
    sheet = reports.balance_sheet(session, as_of)
    def _lines(items):
        return [
            ReportLineOut(
                code=line.account.code,
                name=line.account.name,
                amount=from_cents(line.amount_cents),
            )
            for line in items
        ]

    return BalanceSheetOut(
        as_of=as_of,
        assets=_lines(sheet.assets),
        liabilities=_lines(sheet.liabilities),
        equity=_lines(sheet.equity),
        retained_earnings=from_cents(sheet.retained_earnings),
        total_assets=from_cents(sheet.total_assets),
        total_liabilities=from_cents(sheet.total_liabilities),
        total_equity=from_cents(sheet.total_equity),
    )


def _aging_to_out(rows) -> List[AgingRowOut]:
    return [
        AgingRowOut(
            party_name=r.party_name,
            invoice_or_bill_no=r.invoice_or_bill_no,
            issue_date=r.issue_date,
            due_date=r.due_date,
            total=from_cents(r.total_cents),
            outstanding=from_cents(r.outstanding_cents),
            days_past_due=r.days_past_due,
        )
        for r in rows
    ]


@router.get("/ar-aging", response_model=List[AgingRowOut])
def ar_aging(
    as_of: Optional[date] = None, session: Session = Depends(get_session)
) -> List[AgingRowOut]:
    return _aging_to_out(reports.ar_aging(session, as_of=as_of))


@router.get("/ap-aging", response_model=List[AgingRowOut])
def ap_aging(
    as_of: Optional[date] = None, session: Session = Depends(get_session)
) -> List[AgingRowOut]:
    return _aging_to_out(reports.ap_aging(session, as_of=as_of))


@router.get("/shipment-pnl/{shipment_no}", response_model=ShipmentPnLOut)
def shipment_pnl(
    shipment_no: str, session: Session = Depends(get_session)
) -> ShipmentPnLOut:
    shipment = session.scalar(select(Shipment).where(Shipment.shipment_no == shipment_no))
    if shipment is None:
        raise HTTPException(status_code=404, detail=f"Shipment {shipment_no} not found.")
    pnl = reports.shipment_pnl(session, shipment)
    return ShipmentPnLOut(
        shipment_no=shipment.shipment_no,
        revenue=from_cents(pnl.revenue_cents),
        cost=from_cents(pnl.cost_cents),
        margin=from_cents(pnl.margin_cents),
        margin_pct=pnl.margin_pct,
    )
