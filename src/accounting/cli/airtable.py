"""Airtable sync CLI commands."""

from __future__ import annotations

from datetime import date

import click


@click.group("airtable")
def airtable_group() -> None:
    """Sync from an Airtable base into the accounting API."""


@airtable_group.command("sync")
@click.option(
    "--base-url", default="http://127.0.0.1:8000", help="Accounting API base URL."
)
@click.option(
    "--api-key",
    envvar="ACCOUNTING_API_KEY",
    required=True,
    help="Admin API key (env: ACCOUNTING_API_KEY).",
)
@click.option(
    "--airtable-key",
    envvar="AIRTABLE_API_KEY",
    required=True,
    help="Airtable PAT (env: AIRTABLE_API_KEY).",
)
@click.option(
    "--base-id",
    default=None,
    help="Override the Airtable base id. Defaults to the Drayage Command Center base.",
)
@click.option(
    "--flows",
    default="customers,revenue_tracker",
    help=(
        "Comma-separated flows to run. Default omits 'drivers' since "
        "settlements live in Airtable, not in the accounting books."
    ),
)
@click.option(
    "--dry-run/--commit",
    default=True,
    help="Dry-run prints what would happen without posting. Default: dry-run.",
)
def airtable_sync_cmd(base_url, api_key, airtable_key, base_id, flows, dry_run):
    """Run the Airtable -> accounting sync."""
    from accounting.airtable import DrayageSyncConfig, run_sync
    from accounting.airtable.accounting import AccountingClient
    from accounting.airtable.airtable import HttpxAirtableClient

    cfg = DrayageSyncConfig()
    if base_id:
        cfg.base_id = base_id
    air = HttpxAirtableClient(base_id=cfg.base_id, api_key=airtable_key)
    acct = AccountingClient.for_url(base_url, api_key)
    report = run_sync(
        air,
        acct,
        cfg,
        dry_run=dry_run,
        flows=[f.strip() for f in flows.split(",") if f.strip()],
    )
    click.echo(f"Sync {'(dry-run)' if dry_run else '(committed)'}:")
    click.echo(report.summary())
    if report.total_errors:
        raise click.ClickException(f"{report.total_errors} error(s); see log above.")


@airtable_group.command("sync-settlements")
@click.option("--base-url", default="http://127.0.0.1:8000")
@click.option("--api-key", envvar="ACCOUNTING_API_KEY", required=True)
@click.option("--airtable-key", envvar="AIRTABLE_API_KEY", required=True)
@click.option("--base-id", default=None)
@click.option("--period-start", required=True, help="YYYY-MM-DD")
@click.option("--period-end", required=True, help="YYYY-MM-DD")
@click.option(
    "--expense-account",
    default="5000",
    help="Driver wages account (5000 employees, 5010 owner-ops, etc.).",
)
@click.option(
    "--cash-account",
    default="1000",
    help="Account to credit. Use 2100 for the accrual model (Driver Wages Payable).",
)
@click.option("--dry-run/--commit", default=True)
def airtable_sync_settlements_cmd(
    base_url,
    api_key,
    airtable_key,
    base_id,
    period_start,
    period_end,
    expense_account,
    cash_account,
    dry_run,
):
    """Aggregate Airtable Move Log driver pay into a single periodic JE."""
    from datetime import datetime

    from accounting.airtable import DrayageSyncConfig, sync_settlements_aggregate
    from accounting.airtable.accounting import AccountingClient
    from accounting.airtable.airtable import HttpxAirtableClient

    def _parse_date(s: str) -> date:
        return datetime.strptime(s, "%Y-%m-%d").date()

    cfg = DrayageSyncConfig()
    if base_id:
        cfg.base_id = base_id
    air = HttpxAirtableClient(base_id=cfg.base_id, api_key=airtable_key)
    acct = AccountingClient.for_url(base_url, api_key)
    rep = sync_settlements_aggregate(
        air,
        acct,
        cfg,
        period_start=_parse_date(period_start),
        period_end=_parse_date(period_end),
        expense_account_code=expense_account,
        cash_account_code=cash_account,
        dry_run=dry_run,
    )
    click.echo(
        f"settlements_aggregate {'(dry-run)' if dry_run else '(committed)'}: "
        f"inserted={rep.inserted} skipped_existing={rep.skipped_existing} "
        f"errors={len(rep.errors)}"
    )
    for err in rep.errors:
        click.echo(f"  ! {err}")
    if rep.errors:
        raise click.ClickException("Errors during sync.")


@airtable_group.command("sync-settlements-weekly")
@click.option("--base-url", default="http://127.0.0.1:8000")
@click.option("--api-key", envvar="ACCOUNTING_API_KEY", required=True)
@click.option("--airtable-key", envvar="AIRTABLE_API_KEY", required=True)
@click.option("--base-id", default=None)
@click.option(
    "--week-ends-on",
    type=click.IntRange(0, 6),
    default=6,
    help="Day-of-week the pay week ends on. 0=Mon, ..., 6=Sun. Default 6.",
)
@click.option(
    "--expense-account",
    default="5000",
    help="5000 employees, 5010 owner-ops, etc.",
)
@click.option(
    "--cash-account",
    default="2100",
    help="Default 2100 Driver Wages Payable (accrual). Use 1000 for direct cash.",
)
@click.option("--dry-run/--commit", default=True)
def airtable_sync_settlements_weekly_cmd(
    base_url, api_key, airtable_key, base_id,
    week_ends_on, expense_account, cash_account, dry_run,
):
    """Aggregate last full week's Move Log driver pay into one JE.

    Designed for cron: pick a day-of-week and time after week_ends_on
    (e.g. Monday 6am if week_ends_on=6). Re-runs of the same week are
    no-ops thanks to the deterministic JE reference."""
    from accounting.airtable import (
        DrayageSyncConfig,
        last_full_week,
        sync_settlements_last_week,
    )
    from accounting.airtable.accounting import AccountingClient
    from accounting.airtable.airtable import HttpxAirtableClient

    cfg = DrayageSyncConfig()
    if base_id:
        cfg.base_id = base_id
    air = HttpxAirtableClient(base_id=cfg.base_id, api_key=airtable_key)
    acct = AccountingClient.for_url(base_url, api_key)

    start, end = last_full_week(date.today(), week_ends_on=week_ends_on)
    rep = sync_settlements_last_week(
        air, acct, cfg,
        week_ends_on=week_ends_on,
        expense_account_code=expense_account,
        cash_account_code=cash_account,
        dry_run=dry_run,
    )
    mode = "(dry-run)" if dry_run else "(committed)"
    click.echo(
        f"weekly settlements for {start}..{end} {mode}: "
        f"inserted={rep.inserted} skipped={rep.skipped_existing} "
        f"errors={len(rep.errors)}"
    )
    for err in rep.errors:
        click.echo(f"  ! {err}", err=True)
    if rep.errors:
        raise click.ClickException("Errors during sync.")
