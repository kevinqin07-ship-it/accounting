"""Auth boundary tests."""

from __future__ import annotations


def test_no_auth_returns_401(unauthed_client):
    r = unauthed_client.get("/accounts")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"


def test_invalid_key_returns_401(unauthed_client):
    r = unauthed_client.get(
        "/accounts", headers={"Authorization": "Bearer not-a-real-key"}
    )
    assert r.status_code == 401


def test_healthz_is_public(unauthed_client):
    r = unauthed_client.get("/healthz")
    assert r.status_code == 200


def test_readonly_can_read_but_not_write(unauthed_client, readonly_key, admin_key):
    # admin sets up data
    unauthed_client.post(
        "/accounts/install-default-chart",
        headers={"Authorization": f"Bearer {admin_key}"},
    )
    # readonly can read
    r = unauthed_client.get(
        "/accounts", headers={"Authorization": f"Bearer {readonly_key}"}
    )
    assert r.status_code == 200
    # readonly CANNOT create a customer (write_required)
    r = unauthed_client.post(
        "/customers",
        json={"code": "X", "name": "X"},
        headers={"Authorization": f"Bearer {readonly_key}"},
    )
    assert r.status_code == 403


def test_bookkeeper_can_write_but_not_close(unauthed_client, session, admin_key):
    from accounting.models import ApiKeyRole
    from accounting.services import auth as auth_svc

    issued = auth_svc.create_key(session, name="bk", role=ApiKeyRole.BOOKKEEPER)
    session.commit()
    headers = {"Authorization": f"Bearer {issued.raw_key}"}

    # admin installs chart (bookkeeper can't install chart — admin_required)
    unauthed_client.post(
        "/accounts/install-default-chart",
        headers={"Authorization": f"Bearer {admin_key}"},
    )

    # bookkeeper can create a customer
    r = unauthed_client.post(
        "/customers", json={"code": "BK", "name": "BK"}, headers=headers
    )
    assert r.status_code == 201

    # bookkeeper cannot close period (admin_required)
    r = unauthed_client.post(
        "/period-close", json={"close_through": "2026-01-31"}, headers=headers
    )
    assert r.status_code == 403


def test_install_chart_requires_admin(unauthed_client, readonly_key):
    r = unauthed_client.post(
        "/accounts/install-default-chart",
        headers={"Authorization": f"Bearer {readonly_key}"},
    )
    assert r.status_code == 403


def test_login_sets_cookie_and_authenticates(unauthed_client, admin_key):
    r = unauthed_client.post("/auth/login", json={"key": admin_key})
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    # Cookie was set; the next call uses it without an Authorization header.
    r2 = unauthed_client.get("/accounts")
    assert r2.status_code == 200


def test_login_with_bad_key_fails(unauthed_client):
    r = unauthed_client.post("/auth/login", json={"key": "garbage"})
    assert r.status_code == 401


def test_logout_clears_cookie(unauthed_client, admin_key):
    unauthed_client.post("/auth/login", json={"key": admin_key})
    unauthed_client.post("/auth/logout")
    r = unauthed_client.get("/accounts")
    assert r.status_code == 401


def test_revoked_key_rejected(unauthed_client, session, admin_key):
    from accounting.models import ApiKeyRole
    from accounting.services import auth as auth_svc

    issued = auth_svc.create_key(session, name="temp", role=ApiKeyRole.READONLY)
    session.commit()
    raw = issued.raw_key
    headers = {"Authorization": f"Bearer {raw}"}

    # works first
    assert unauthed_client.get("/accounts", headers=headers).status_code == 200

    # revoke via admin
    unauthed_client.delete(
        f"/auth/keys/{issued.api_key.id}",
        headers={"Authorization": f"Bearer {admin_key}"},
    )

    # now rejected
    assert unauthed_client.get("/accounts", headers=headers).status_code == 401


def test_create_key_via_api(client):
    r = client.post(
        "/auth/keys", json={"name": "ops", "role": "bookkeeper"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "ops"
    assert body["role"] == "bookkeeper"
    assert body["raw_key"]  # raw key returned exactly once

    # Listing keys should show at least the test admin and the new one.
    listed = client.get("/auth/keys").json()
    assert any(k["name"] == "ops" for k in listed)


def test_create_key_validates_role(client):
    r = client.post("/auth/keys", json={"name": "x", "role": "wizard"})
    assert r.status_code == 400


def test_cli_auth_commands(session, monkeypatch, capsys):
    """Smoke test: create-key writes to the same DB the API uses."""
    from click.testing import CliRunner

    from accounting.cli import cli

    runner = CliRunner()
    r = runner.invoke(cli, ["auth", "create-key", "--name", "cli-key", "--role", "admin"])
    assert r.exit_code == 0, r.output
    assert "Save this now" in r.output

    r = runner.invoke(cli, ["auth", "list-keys"])
    assert r.exit_code == 0
    assert "cli-key" in r.output
