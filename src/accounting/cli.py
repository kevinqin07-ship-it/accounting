"""Command-line interface for the accounting module."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import click
from sqlalchemy import select

from accounting.db import Session, init_db
from accounting.money import fmt
from accounting.models import Account, Invoice, Bill, Shipment
from accounting.services import ledger, reports, shipments as ship_svc
from accounting.services.reports import shipment_pnl


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


@click.group()
def cli() -> None:
    """Logistics accounting CLI."""


@cli.command("init")
def init_cmd() -> None:
    """Create database tables and install the default chart of accounts."""
    init_db()
    with Session() as session:
        ledger.install_chart(session)
    click.echo("Database initialized with default chart of accounts.")


@cli.command("seed")
def seed_cmd() -> None:
    """Reset the database and load sample data."""
    from accounting.seed import seed

    seed()


@cli.command("accounts")
def accounts_cmd() -> None:
    """List the chart of accounts."""
    with Session() as session:
        for account in session.scalars(select(Account).order_by(Account.code)):
            click.echo(f"  {account.code:<6} {account.type.value:<10} {account.name}")


@cli.command("balance")
@click.argument("code")
@click.option("--as-of", type=str, default=None, help="YYYY-MM-DD")
def balance_cmd(code: str, as_of: str | None) -> None:
    """Show the running balance for one account."""
    as_of_date = _parse_date(as_of) if as_of else None
    with Session() as session:
        bal = ledger.account_balance(session, code, as_of=as_of_date)
        account = ledger.get_account(session, code)
        click.echo(f"{account.code} {account.name}: {fmt(bal)}")


@cli.command("trial-balance")
@click.option("--as-of", type=str, default=None, help="YYYY-MM-DD")
def trial_balance_cmd(as_of: str | None) -> None:
    """Print the trial balance."""
    as_of_date = _parse_date(as_of) if as_of else None
    with Session() as session:
        rows = ledger.trial_balance(session, as_of=as_of_date)
        click.echo(f"Trial Balance{' as of ' + as_of if as_of else ''}")
        click.echo(f"{'Code':<6} {'Account':<40} {'Debit':>14} {'Credit':>14}")
        click.echo("-" * 78)
        td = tc = 0
        for account, debit, credit in rows:
            click.echo(f"{account.code:<6} {account.name:<40} {fmt(debit):>14} {fmt(credit):>14}")
            td += debit
            tc += credit
        click.echo("-" * 78)
        click.echo(f"{'TOTAL':<47} {fmt(td):>14} {fmt(tc):>14}")


@cli.command("pnl")
@click.option("--start", type=str, required=True, help="YYYY-MM-DD")
@click.option("--end", type=str, required=True, help="YYYY-MM-DD")
def pnl_cmd(start: str, end: str) -> None:
    """Print a profit-and-loss statement."""
    s, e = _parse_date(start), _parse_date(end)
    with Session() as session:
        stmt = reports.income_statement(session, s, e)
        click.echo(f"Income Statement {start} to {end}")
        click.echo("\nRevenue:")
        for line in stmt.revenue:
            click.echo(f"  {line.account.code} {line.account.name:<35} {fmt(line.amount_cents):>14}")
        click.echo(f"  {'Total revenue':<42} {fmt(stmt.total_revenue):>14}")
        click.echo("\nExpenses:")
        for line in stmt.expense:
            click.echo(f"  {line.account.code} {line.account.name:<35} {fmt(line.amount_cents):>14}")
        click.echo(f"  {'Total expenses':<42} {fmt(stmt.total_expense):>14}")
        click.echo(f"\n{'Net income':<42} {fmt(stmt.net_income):>14}")


@cli.command("balance-sheet")
@click.option("--as-of", type=str, required=True, help="YYYY-MM-DD")
def balance_sheet_cmd(as_of: str) -> None:
    """Print a balance sheet as of a given date."""
    d = _parse_date(as_of)
    with Session() as session:
        sheet = reports.balance_sheet(session, d)
        click.echo(f"Balance Sheet as of {as_of}")
        click.echo("\nAssets:")
        for line in sheet.assets:
            click.echo(f"  {line.account.code} {line.account.name:<35} {fmt(line.amount_cents):>14}")
        click.echo(f"  {'Total assets':<42} {fmt(sheet.total_assets):>14}")
        click.echo("\nLiabilities:")
        for line in sheet.liabilities:
            click.echo(f"  {line.account.code} {line.account.name:<35} {fmt(line.amount_cents):>14}")
        click.echo(f"  {'Total liabilities':<42} {fmt(sheet.total_liabilities):>14}")
        click.echo("\nEquity:")
        for line in sheet.equity:
            click.echo(f"  {line.account.code} {line.account.name:<35} {fmt(line.amount_cents):>14}")
        click.echo(f"  {'Retained earnings':<42} {fmt(sheet.retained_earnings):>14}")
        click.echo(f"  {'Total equity':<42} {fmt(sheet.total_equity):>14}")
        click.echo(
            f"\n{'Liabilities + equity':<42} {fmt(sheet.total_liabilities + sheet.total_equity):>14}"
        )


@cli.command("ar-aging")
def ar_aging_cmd() -> None:
    """Show outstanding customer invoices."""
    with Session() as session:
        rows = reports.ar_aging(session)
        click.echo(f"{'Customer':<25} {'Invoice':<18} {'Due':<12} {'Outstanding':>14} {'Days late':>10}")
        for row in rows:
            click.echo(
                f"{row.party_name:<25} {row.invoice_or_bill_no:<18} {row.due_date.isoformat():<12} "
                f"{fmt(row.outstanding_cents):>14} {row.days_past_due:>10}"
            )


@cli.command("ap-aging")
def ap_aging_cmd() -> None:
    """Show outstanding vendor bills."""
    with Session() as session:
        rows = reports.ap_aging(session)
        click.echo(f"{'Vendor':<25} {'Bill':<18} {'Due':<12} {'Outstanding':>14} {'Days late':>10}")
        for row in rows:
            click.echo(
                f"{row.party_name:<25} {row.invoice_or_bill_no:<18} {row.due_date.isoformat():<12} "
                f"{fmt(row.outstanding_cents):>14} {row.days_past_due:>10}"
            )


@cli.command("shipment-pnl")
@click.argument("shipment_no")
def shipment_pnl_cmd(shipment_no: str) -> None:
    """Show revenue, cost, and margin for a shipment."""
    with Session() as session:
        shipment = session.scalar(select(Shipment).where(Shipment.shipment_no == shipment_no))
        if shipment is None:
            raise click.ClickException(f"Shipment {shipment_no} not found.")
        result = shipment_pnl(session, shipment)
        click.echo(f"Shipment {shipment.shipment_no}: {shipment.origin} -> {shipment.destination}")
        click.echo(f"  Revenue: {fmt(result.revenue_cents)}")
        click.echo(f"  Cost:    {fmt(result.cost_cents)}")
        click.echo(f"  Margin:  {fmt(result.margin_cents)} ({result.margin_pct * 100:.1f}%)")


if __name__ == "__main__":
    cli()
