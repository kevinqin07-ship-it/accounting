"""AR-aging email notification tests."""

from __future__ import annotations

from datetime import date

import pytest

from accounting.services import invoicing, ledger, notifications, parties
from accounting.services.invoicing import InvoiceLineInput
from accounting.services.notifications import StubTransport


def _bootstrap(session, *, count: int = 3):
    """Create N customers each with one open invoice. Inv #1: 60 days late,
    Inv #2: 15 days late, Inv #3: not yet due."""
    ledger.install_chart(session)
    today = date(2026, 5, 1)

    def add(code, name, days_late):
        cust = parties.upsert_customer(session, code=code, name=name)
        issue_date = today - (
            __import__("datetime").timedelta(days=30 + days_late)
            if days_late >= 0
            else __import__("datetime").timedelta(days=30 + days_late)
        )
        # due_date = today - days_late so positive days_late => past due.
        due = today - __import__("datetime").timedelta(days=days_late)
        inv = invoicing.create_invoice(
            session,
            invoice_no=f"INV-{code}",
            customer=cust,
            issue_date=due - __import__("datetime").timedelta(days=30),
            due_date=due,
            lines=[InvoiceLineInput("Line haul", "4000", 1000.00 + len(code))],
        )
        invoicing.issue_invoice(session, inv)

    add("A", "Alpha Co", 60)
    add("B", "Bravo Co", 15)
    add("C", "Charlie Co", -5)  # not yet due
    return today


def test_build_digest_filters_and_buckets(session):
    today = _bootstrap(session)
    digest = notifications.build_ar_digest(
        session, as_of=today, min_days_past_due=0
    )
    # All three invoices included.
    assert len(digest.rows) == 3
    # Bucket totals: not-yet-due in Current, 15 -> 1-30, 60 -> 31-60.
    assert digest.bucket_totals_cents["Current"] > 0
    assert digest.bucket_totals_cents["1–30 days"] > 0
    assert digest.bucket_totals_cents["31–60 days"] > 0
    assert digest.bucket_totals_cents["Over 90 days"] == 0


def test_build_digest_min_days_filter(session):
    today = _bootstrap(session)
    # Only show invoices at least 30 days past due.
    digest = notifications.build_ar_digest(
        session, as_of=today, min_days_past_due=30
    )
    assert len(digest.rows) == 1
    assert digest.rows[0].invoice_or_bill_no == "INV-A"


def test_send_uses_stub_transport_and_builds_email(session):
    today = _bootstrap(session)
    transport = StubTransport()
    digest = notifications.send_ar_aging_digest(
        session,
        recipients=["ops@example.com", "owner@example.com"],
        min_days_past_due=0,
        as_of=today,
        transport=transport,
        config=notifications.SmtpConfig(
            host="x", port=25, from_addr="noreply@example.com"
        ),
    )

    assert digest.grand_total_cents > 0
    assert len(transport.sent) == 1
    msg = transport.sent[0]
    assert msg["From"] == "noreply@example.com"
    assert msg["To"] == "ops@example.com, owner@example.com"
    assert "AR Aging" in msg["Subject"]
    # multipart/alternative with text and html parts
    body_text = msg.get_body(preferencelist=("plain",)).get_content()
    body_html = msg.get_body(preferencelist=("html",)).get_content()
    assert "INV-A" in body_text
    assert "INV-A" in body_html
    assert "Bucket totals" in body_text


def test_empty_digest_still_sends_friendly_message(session):
    ledger.install_chart(session)
    transport = StubTransport()
    digest = notifications.send_ar_aging_digest(
        session,
        recipients=["ops@example.com"],
        min_days_past_due=0,
        as_of=date(2026, 5, 1),
        transport=transport,
        config=notifications.SmtpConfig(host="x", port=25),
    )
    assert digest.grand_total_cents == 0
    assert len(transport.sent) == 1
    text = transport.sent[0].get_body(preferencelist=("plain",)).get_content()
    assert "no outstanding invoices" in text


def test_recipients_required(session):
    _bootstrap(session)
    with pytest.raises(ValueError, match="At least one recipient"):
        notifications.send_ar_aging_digest(
            session,
            recipients=[],
            transport=StubTransport(),
            config=notifications.SmtpConfig(host="x", port=25),
        )


def test_api_endpoint_admin_only(client, unauthed_client, readonly_key, monkeypatch):
    """Admin can hit the endpoint; readonly can't."""
    monkeypatch.setenv("SMTP_DRY_RUN", "1")  # so default_transport doesn't try SMTP
    client.post("/accounts/install-default-chart")

    r = unauthed_client.post(
        "/notifications/ar-aging",
        json={"recipients": ["ops@example.com"]},
        headers={"Authorization": f"Bearer {readonly_key}"},
    )
    assert r.status_code == 403


def test_api_endpoint_returns_totals(client, monkeypatch):
    monkeypatch.setenv("SMTP_DRY_RUN", "1")
    client.post("/accounts/install-default-chart")

    cust = client.post("/customers", json={"code": "A", "name": "Acme"}).json()
    inv = client.post(
        "/invoices",
        json={
            "invoice_no": "INV-AR-1",
            "customer_id": cust["id"],
            "issue_date": "2026-01-01",
            "due_date": "2026-01-31",
            "lines": [
                {
                    "description": "L",
                    "revenue_account_code": "4000",
                    "amount": "1234.56",
                }
            ],
        },
    ).json()
    client.post(f"/invoices/{inv['id']}/issue")

    r = client.post(
        "/notifications/ar-aging",
        json={"recipients": ["ops@example.com"], "as_of": "2026-05-01"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["invoice_count"] == 1
    assert body["grand_total"] == "1234.56"
    assert body["recipients"] == ["ops@example.com"]


def test_cli_dry_run(session, monkeypatch):
    from click.testing import CliRunner

    from accounting.cli import cli

    _bootstrap(session)
    session.commit()

    monkeypatch.setenv("SMTP_DRY_RUN", "1")
    runner = CliRunner()
    r = runner.invoke(
        cli,
        [
            "notify",
            "ar-aging",
            "--to",
            "ops@example.com",
            "--min-days",
            "30",
            "--as-of",
            "2026-05-01",
        ],
    )
    assert r.exit_code == 0, r.output
    assert "AR digest as of 2026-05-01" in r.output
