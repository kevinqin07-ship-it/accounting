"""Driver settlement (pay run) CLI commands."""

from __future__ import annotations

from datetime import datetime, date

import click

from accounting.db import Session
from accounting.money import fmt


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


@click.group("settlements")
def settlements_group() -> None:
    """Driver settlements (pay runs)."""


@settlements_group.command("list")
def settlements_list_cmd():
    from sqlalchemy import select

    from accounting.models import Settlement

    with Session() as session:
        for s in session.scalars(select(Settlement).order_by(Settlement.id)):
            click.echo(
                f"#{s.id:<3} {s.settlement_no:<18} driver={s.driver_id:<3} "
                f"{s.period_start}..{s.period_end} {s.status.value:<10} "
                f"net={fmt(s.net_cents)}"
            )


@settlements_group.command("approve")
@click.argument("settlement_id", type=int)
def settlements_approve_cmd(settlement_id):
    from accounting.models import Settlement
    from accounting.services import settlements as svc

    with Session() as session:
        s = session.get(Settlement, settlement_id)
        if s is None:
            raise click.ClickException(f"Settlement {settlement_id} not found.")
        try:
            svc.approve_settlement(session, s)
        except ValueError as e:
            raise click.ClickException(str(e))
    click.echo(f"Approved settlement #{settlement_id}.")


@settlements_group.command("pay")
@click.argument("settlement_id", type=int)
@click.option("--date", "payment_date", required=True, help="YYYY-MM-DD")
@click.option("--cash-account", default="1000")
@click.option("--method", default="ach")
@click.option("--reference", default=None)
def settlements_pay_cmd(settlement_id, payment_date, cash_account, method, reference):
    from accounting.models import Settlement
    from accounting.services import settlements as svc

    with Session() as session:
        s = session.get(Settlement, settlement_id)
        if s is None:
            raise click.ClickException(f"Settlement {settlement_id} not found.")
        try:
            svc.pay_settlement(
                session,
                s,
                payment_date=_parse_date(payment_date),
                cash_account_code=cash_account,
                method=method,
                reference=reference,
            )
        except ValueError as e:
            raise click.ClickException(str(e))
    click.echo(f"Paid settlement #{settlement_id}.")
