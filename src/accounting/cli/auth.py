"""API key management CLI commands."""

from __future__ import annotations

import click

from accounting.db import Session


@click.group("auth")
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
