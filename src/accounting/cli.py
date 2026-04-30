"""Command-line interface for the accounting module."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import click
from sqlalchemy import select

from accounting.db import Session, init_db
from accounting.money import fmt
from accounting.models import Account, Bill, Invoice, Reconciliation, Shipment, Vendor
from accounting.services import (
    bank_rec,
    fuel_import,
    ledger,
    period_close,
    reports,
    shipments as ship_svc,
)
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


@cli.command("import-fuel")
@click.argument("vendor_code")
@click.argument("csv_path", type=click.Path(exists=True, dir_okay=False, readable=True))
@click.option("--bill-no", required=True, help="Bill number to create from this statement.")
@click.option("--issue-date", required=True, help="YYYY-MM-DD")
def import_fuel_cmd(vendor_code: str, csv_path: str, bill_no: str, issue_date: str) -> None:
    """Import a fuel-card CSV and create a vendor bill."""
    with open(csv_path, "r", newline="") as fh:
        rows = fuel_import.parse_csv(fh.read())
    issue = _parse_date(issue_date)
    with Session() as session:
        vendor = session.scalar(select(Vendor).where(Vendor.code == vendor_code))
        if vendor is None:
            raise click.ClickException(f"Vendor {vendor_code} not found.")
        result = fuel_import.import_statement(
            session,
            vendor=vendor,
            rows=rows,
            bill_no=bill_no,
            issue_date=issue,
        )
        click.echo(
            f"Imported {result.inserted} transactions, skipped {result.skipped_duplicates} duplicates."
        )
        click.echo(f"Bill {result.bill.bill_no}: {fmt(result.bill.total_cents)}")
        for truck, count in sorted(result.rows_per_truck.items()):
            click.echo(f"  {truck}: {count} txns")


@cli.command("import-bank")
@click.argument("cash_account_code")
@click.argument("csv_path", type=click.Path(exists=True, dir_okay=False, readable=True))
def import_bank_cmd(cash_account_code: str, csv_path: str) -> None:
    """Import a bank-statement CSV for a cash account."""
    with open(csv_path, "r", newline="") as fh:
        rows = bank_rec.parse_csv(fh.read())
    with Session() as session:
        result = bank_rec.import_rows(
            session, cash_account_code=cash_account_code, rows=rows
        )
    click.echo(
        f"Imported {result.inserted} bank lines, skipped {result.skipped_duplicates} duplicates."
    )


@cli.group("bank-rec")
def bank_rec_group() -> None:
    """Bank reconciliation commands."""


@bank_rec_group.command("open")
@click.argument("cash_account_code")
@click.option("--period-start", required=True, help="YYYY-MM-DD")
@click.option("--period-end", required=True, help="YYYY-MM-DD")
@click.option("--start-balance", required=True, type=float)
@click.option("--end-balance", required=True, type=float)
def bank_rec_open_cmd(
    cash_account_code: str,
    period_start: str,
    period_end: str,
    start_balance: float,
    end_balance: float,
) -> None:
    """Open a reconciliation period."""
    with Session() as session:
        rec = bank_rec.open_period(
            session,
            cash_account_code=cash_account_code,
            period_start=_parse_date(period_start),
            period_end=_parse_date(period_end),
            statement_start_balance=start_balance,
            statement_end_balance=end_balance,
        )
        click.echo(f"Opened reconciliation #{rec.id} for {cash_account_code}.")


@bank_rec_group.command("auto-match")
@click.argument("rec_id", type=int)
@click.option("--tolerance-days", type=int, default=5)
def bank_rec_auto_match_cmd(rec_id: int, tolerance_days: int) -> None:
    """Run auto-matching on an open reconciliation."""
    with Session() as session:
        rec = session.get(Reconciliation, rec_id)
        if rec is None:
            raise click.ClickException(f"Reconciliation {rec_id} not found.")
        created = bank_rec.auto_match(session, rec, date_tolerance_days=tolerance_days)
        click.echo(f"Created {created} matches.")


@bank_rec_group.command("status")
@click.argument("rec_id", type=int)
def bank_rec_status_cmd(rec_id: int) -> None:
    """Show the reconciliation summary."""
    with Session() as session:
        rec = session.get(Reconciliation, rec_id)
        if rec is None:
            raise click.ClickException(f"Reconciliation {rec_id} not found.")
        s = bank_rec.summary(session, rec)
        click.echo(
            f"Reconciliation #{rec.id} ({rec.cash_account.code}) "
            f"{rec.period_start}..{rec.period_end} [{rec.status.value}]"
        )
        click.echo(f"  Statement start balance:    {fmt(s.statement_start_balance_cents):>14}")
        click.echo(f"  Opening book balance:       {fmt(s.opening_book_balance_cents):>14}")
        click.echo(f"  Statement ending balance:   {fmt(s.statement_end_balance_cents):>14}")
        click.echo(f"  Book balance at period end: {fmt(s.book_balance_cents):>14}")
        click.echo(f"  - Outstanding deposits:     {fmt(s.outstanding_inflows_cents):>14}")
        click.echo(f"  + Outstanding checks:       {fmt(s.outstanding_outflows_cents):>14}")
        click.echo(f"  = Adjusted book balance:    {fmt(s.adjusted_book_balance_cents):>14}")
        click.echo(f"  Opening difference:         {fmt(s.opening_difference_cents):>14}")
        click.echo(f"  Ending difference:          {fmt(s.ending_difference_cents):>14}")
        click.echo(
            f"  Unmatched bank lines: {len(s.unmatched_bank_lines)}, "
            f"unmatched book lines: {len(s.unmatched_book_lines)}"
        )
        if s.unmatched_bank_lines:
            click.echo("\nUnmatched bank lines:")
            for line in s.unmatched_bank_lines:
                click.echo(
                    f"  id={line.id} {line.external_id} {line.txn_date} "
                    f"{fmt(line.amount_cents):>12} {line.description or ''}"
                )


@bank_rec_group.command("adjust")
@click.argument("rec_id", type=int)
@click.argument("bank_line_id", type=int)
@click.argument("offsetting_account_code")
@click.option("--memo", default=None)
def bank_rec_adjust_cmd(
    rec_id: int, bank_line_id: int, offsetting_account_code: str, memo: str | None
) -> None:
    """Post an adjusting JE for a bank-only item (fee, interest, NSF, ...)
    and match it to the originating bank line."""
    with Session() as session:
        rec = session.get(Reconciliation, rec_id)
        if rec is None:
            raise click.ClickException(f"Reconciliation {rec_id} not found.")
        try:
            match = bank_rec.post_adjustment(
                session,
                rec,
                bank_line_id=bank_line_id,
                offsetting_account_code=offsetting_account_code,
                memo=memo,
            )
        except (ValueError, LookupError) as e:
            raise click.ClickException(str(e))
        click.echo(f"Posted adjustment match #{match.id}.")


@bank_rec_group.command("finalize")
@click.argument("rec_id", type=int)
def bank_rec_finalize_cmd(rec_id: int) -> None:
    """Lock the reconciliation. Fails if it doesn't balance."""
    with Session() as session:
        rec = session.get(Reconciliation, rec_id)
        if rec is None:
            raise click.ClickException(f"Reconciliation {rec_id} not found.")
        try:
            bank_rec.finalize(session, rec)
        except ValueError as e:
            raise click.ClickException(str(e))
        click.echo(f"Reconciliation #{rec.id} finalized.")


@cli.command("close")
@click.option("--through", "through", required=True, help="YYYY-MM-DD")
@click.option("--retained-earnings", default="3100", help="Retained-earnings account code.")
@click.option("--note", default=None)
def close_cmd(through: str, retained_earnings: str, note: str | None) -> None:
    """Close revenue and expense activity through the given date into retained earnings."""
    cutoff = _parse_date(through)
    with Session() as session:
        try:
            rec = period_close.close_period(
                session,
                close_through=cutoff,
                retained_earnings_code=retained_earnings,
                note=note,
            )
        except (ValueError, LookupError) as e:
            raise click.ClickException(str(e))
        click.echo(
            f"Closed through {rec.close_through_date} (closing JE #{rec.closing_journal_entry_id})."
        )


@cli.group("notify")
def notify_group() -> None:
    """Send email notifications. Reads SMTP_* env vars; set SMTP_DRY_RUN=1 to print instead of send."""


@notify_group.command("ar-aging")
@click.option("--to", "recipients", multiple=True, required=True, help="Recipient email; pass once per address.")
@click.option("--min-days", type=int, default=0, help="Only include invoices at least this many days past due.")
@click.option("--as-of", default=None, help="YYYY-MM-DD; defaults to today.")
def notify_ar_aging_cmd(recipients: tuple[str, ...], min_days: int, as_of: str | None) -> None:
    from accounting.services import notifications as notif

    as_of_date = _parse_date(as_of) if as_of else None
    with Session() as session:
        digest = notif.send_ar_aging_digest(
            session,
            recipients=list(recipients),
            min_days_past_due=min_days,
            as_of=as_of_date,
        )
    click.echo(
        f"AR digest as of {digest.as_of}: {fmt(digest.grand_total_cents)} across "
        f"{len(digest.rows)} invoice(s) sent to {', '.join(recipients)}."
    )


@cli.group("auth")
def auth_group() -> None:
    """API key management. CLI runs locally and bypasses HTTP auth."""


@auth_group.command("create-key")
@click.option("--name", required=True, help="Human-readable label.")
@click.option(
    "--role",
    required=True,
    type=click.Choice(["admin", "bookkeeper", "readonly"]),
)
def auth_create_key_cmd(name: str, role: str) -> None:
    """Create a new API key. The raw key is printed only once; record it."""
    from accounting.models import ApiKeyRole
    from accounting.services import auth as auth_svc

    with Session() as session:
        issued = auth_svc.create_key(session, name=name, role=ApiKeyRole(role))
        click.echo(f"Created key #{issued.api_key.id} ({name}, {role}):")
        click.echo(f"  {issued.raw_key}")
        click.echo("  Save this now; it cannot be retrieved later.")


@auth_group.command("list-keys")
@click.option("--include-revoked/--no-include-revoked", default=False)
def auth_list_keys_cmd(include_revoked: bool) -> None:
    from accounting.services import auth as auth_svc

    with Session() as session:
        keys = auth_svc.list_keys(session, include_revoked=include_revoked)
        if not keys:
            click.echo("(no keys)")
            return
        for key in keys:
            status = "revoked" if key.revoked_at else "active"
            last = key.last_used_at.isoformat() if key.last_used_at else "never"
            click.echo(
                f"#{key.id:<3} {key.name:<24} {key.role.value:<11} {status:<8} last_used={last}"
            )


@auth_group.command("revoke")
@click.argument("key_id", type=int)
def auth_revoke_cmd(key_id: int) -> None:
    from accounting.services import auth as auth_svc

    with Session() as session:
        try:
            api_key = auth_svc.revoke(session, key_id)
        except LookupError as e:
            raise click.ClickException(str(e))
        click.echo(f"Revoked key #{api_key.id} ({api_key.name}).")


@cli.command("close-status")
def close_status_cmd() -> None:
    """Show the most recent close, if any."""
    with Session() as session:
        cutoff = period_close.closed_through(session)
        if cutoff is None:
            click.echo("Books are open (no period has been closed).")
        else:
            click.echo(f"Books are closed through {cutoff}.")


if __name__ == "__main__":
    cli()
