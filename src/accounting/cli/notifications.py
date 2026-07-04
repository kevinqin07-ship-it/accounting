"""Email notification CLI commands."""

from __future__ import annotations

from datetime import datetime, date

import click

from accounting.db import Session
from accounting.money import fmt


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


@click.group("notify")
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
