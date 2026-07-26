"""Driver master data CLI commands."""

from __future__ import annotations

import click

from accounting.db import Session
from accounting.money import fmt


@click.group("drivers")
def drivers_group() -> None:
    """Driver master data."""


@drivers_group.command("upsert")
@click.option("--code", required=True)
@click.option("--name", required=True)
@click.option(
    "--type", "driver_type", required=True, type=click.Choice(["employee", "owner_operator"])
)
@click.option("--cents-per-mile", type=int, default=None)
@click.option("--truck", "truck_no", default=None)
def drivers_upsert_cmd(code, name, driver_type, cents_per_mile, truck_no):
    from accounting.models import DriverType
    from accounting.services import settlements as svc

    with Session() as session:
        d = svc.upsert_driver(
            session,
            code=code,
            name=name,
            driver_type=DriverType(driver_type),
            cents_per_mile=cents_per_mile,
            truck_no=truck_no,
        )
    click.echo(f"Upserted driver #{d.id} {d.code} ({d.driver_type.value}).")


@drivers_group.command("list")
def drivers_list_cmd():
    from sqlalchemy import select

    from accounting.models import Driver

    with Session() as session:
        for d in session.scalars(select(Driver).order_by(Driver.code)):
            click.echo(
                f"#{d.id:<3} {d.code:<16} {d.name:<24} {d.driver_type.value:<14} truck={d.truck_no or '—'}"
            )
