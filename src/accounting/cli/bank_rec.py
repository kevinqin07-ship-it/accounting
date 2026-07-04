"""Bank reconciliation CLI commands."""

from __future__ import annotations

from datetime import datetime, date

import click

from accounting.db import Session
from accounting.models import Reconciliation
from accounting.money import fmt
from accounting.services import bank_rec


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


@click.group("bank-rec")
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


@bank_rec_group.command("settle-disbursements")
@click.argument("rec_id", type=int)
@click.option(
    "--account",
    "payable_account_code",
    default="2100",
    help="Liability account being cleared (default 2100 Driver Wages Payable).",
)
@click.option(
    "--patterns",
    default="PAYROLL,DRIVER PAY,ACH SETTLE,SETTLEMENT",
    help="Comma-separated description substrings to match.",
)
@click.option("--case-sensitive/--ignore-case", default=False)
def bank_rec_settle_disbursements_cmd(rec_id, payable_account_code, patterns, case_sensitive):
    """Bulk-clear unmatched bank outflows whose description matches one of
    the patterns. Posts DR <account> / CR cash and pairs each new cash
    JE line with the bank line in one shot. Designed for driver-pay
    disbursements paired with the weekly accrual sync."""
    pats = [p.strip() for p in patterns.split(",") if p.strip()]
    with Session() as session:
        rec = session.get(Reconciliation, rec_id)
        if rec is None:
            raise click.ClickException(f"Reconciliation {rec_id} not found.")
        try:
            matches = bank_rec.settle_disbursements(
                session,
                rec,
                payable_account_code=payable_account_code,
                description_patterns=pats,
                case_sensitive=case_sensitive,
            )
        except (ValueError, LookupError) as e:
            raise click.ClickException(str(e))
    click.echo(f"Cleared {len(matches)} bank line(s) against {payable_account_code}.")


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
