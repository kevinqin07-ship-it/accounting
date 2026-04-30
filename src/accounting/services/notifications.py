"""Email notifications. Pluggable transport so tests don't actually send."""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass, field
from datetime import date
from email.message import EmailMessage
from typing import List, Optional, Protocol, Sequence

from sqlalchemy.orm import Session

from accounting.money import fmt
from accounting.services import reports


# --- Transports ----------------------------------------------------------

class Transport(Protocol):
    def send(self, message: EmailMessage) -> None: ...


@dataclass
class SmtpConfig:
    host: str
    port: int
    user: Optional[str] = None
    password: Optional[str] = None
    use_tls: bool = True
    from_addr: str = "accounting@example.com"

    @classmethod
    def from_env(cls) -> "SmtpConfig":
        return cls(
            host=os.environ.get("SMTP_HOST", "localhost"),
            port=int(os.environ.get("SMTP_PORT", "587")),
            user=os.environ.get("SMTP_USER") or None,
            password=os.environ.get("SMTP_PASS") or None,
            use_tls=os.environ.get("SMTP_USE_TLS", "1") not in ("0", "false", "False", ""),
            from_addr=os.environ.get("SMTP_FROM", "accounting@example.com"),
        )


@dataclass
class SmtpTransport:
    config: SmtpConfig

    def send(self, message: EmailMessage) -> None:
        if self.config.use_tls:
            with smtplib.SMTP(self.config.host, self.config.port, timeout=30) as s:
                s.starttls()
                if self.config.user:
                    s.login(self.config.user, self.config.password or "")
                s.send_message(message)
        else:
            with smtplib.SMTP(self.config.host, self.config.port, timeout=30) as s:
                if self.config.user:
                    s.login(self.config.user, self.config.password or "")
                s.send_message(message)


@dataclass
class StubTransport:
    """Captures messages instead of sending. For tests and dry runs."""

    sent: List[EmailMessage] = field(default_factory=list)

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


def default_transport() -> Transport:
    """Return a stub if SMTP_DRY_RUN is set, else an SMTP transport."""
    if os.environ.get("SMTP_DRY_RUN") in ("1", "true", "True"):
        return StubTransport()
    return SmtpTransport(SmtpConfig.from_env())


# --- AR aging digest -----------------------------------------------------

# Standard accountant buckets, days past due. (low, high) inclusive.
AGING_BUCKETS = [
    ("Current", -10**6, 0),  # not yet past due
    ("1–30 days", 1, 30),
    ("31–60 days", 31, 60),
    ("61–90 days", 61, 90),
    ("Over 90 days", 91, 10**6),
]


@dataclass
class ARDigest:
    as_of: date
    rows: list  # accounting.services.reports.AgingRow
    bucket_totals_cents: dict[str, int]
    grand_total_cents: int


def build_ar_digest(
    session: Session, *, as_of: Optional[date] = None, min_days_past_due: int = 0
) -> ARDigest:
    today = as_of or date.today()
    rows = reports.ar_aging(session, as_of=today)
    rows = [r for r in rows if r.days_past_due >= min_days_past_due]
    rows.sort(key=lambda r: (-r.days_past_due, r.party_name))

    bucket_totals = {label: 0 for label, _, _ in AGING_BUCKETS}
    for row in rows:
        for label, low, high in AGING_BUCKETS:
            if low <= row.days_past_due <= high:
                bucket_totals[label] += row.outstanding_cents
                break
    grand_total = sum(r.outstanding_cents for r in rows)
    return ARDigest(
        as_of=today,
        rows=rows,
        bucket_totals_cents=bucket_totals,
        grand_total_cents=grand_total,
    )


def _render_text(digest: ARDigest) -> str:
    lines = [
        f"AR Aging Digest — as of {digest.as_of.isoformat()}",
        "",
        "Bucket totals:",
    ]
    for label, _, _ in AGING_BUCKETS:
        lines.append(f"  {label:<14} {fmt(digest.bucket_totals_cents[label]):>14}")
    lines.append(f"  {'TOTAL':<14} {fmt(digest.grand_total_cents):>14}")
    lines.append("")
    if not digest.rows:
        lines.append("(no outstanding invoices match this filter)")
    else:
        lines.append(
            f"{'Customer':<28} {'Invoice':<18} {'Due':<12} {'Outstanding':>14} {'Days late':>10}"
        )
        for row in digest.rows:
            lines.append(
                f"{row.party_name[:28]:<28} {row.invoice_or_bill_no:<18} "
                f"{row.due_date.isoformat():<12} {fmt(row.outstanding_cents):>14} "
                f"{row.days_past_due:>10}"
            )
    return "\n".join(lines) + "\n"


def _render_html(digest: ARDigest) -> str:
    bucket_rows = "".join(
        f"<tr><td>{label}</td><td style='text-align:right'>{fmt(digest.bucket_totals_cents[label])}</td></tr>"
        for label, _, _ in AGING_BUCKETS
    )
    if digest.rows:
        invoice_rows = "".join(
            f"<tr>"
            f"<td>{row.party_name}</td>"
            f"<td>{row.invoice_or_bill_no}</td>"
            f"<td>{row.due_date.isoformat()}</td>"
            f"<td style='text-align:right'>{fmt(row.outstanding_cents)}</td>"
            f"<td style='text-align:right'>{row.days_past_due}</td>"
            f"</tr>"
            for row in digest.rows
        )
        invoice_table = (
            "<h3>Outstanding invoices</h3>"
            "<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse'>"
            "<tr><th>Customer</th><th>Invoice</th><th>Due</th>"
            "<th>Outstanding</th><th>Days late</th></tr>"
            f"{invoice_rows}</table>"
        )
    else:
        invoice_table = "<p>No outstanding invoices match this filter.</p>"

    return (
        f"<h2>AR Aging — as of {digest.as_of.isoformat()}</h2>"
        f"<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse'>"
        f"<tr><th>Bucket</th><th>Total</th></tr>"
        f"{bucket_rows}"
        f"<tr><th>TOTAL</th><th style='text-align:right'>{fmt(digest.grand_total_cents)}</th></tr>"
        f"</table>"
        f"{invoice_table}"
    )


def build_ar_email(
    digest: ARDigest, *, from_addr: str, recipients: Sequence[str], subject: Optional[str] = None
) -> EmailMessage:
    if not recipients:
        raise ValueError("At least one recipient is required.")
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject or (
        f"AR Aging — {fmt(digest.grand_total_cents)} outstanding "
        f"({digest.as_of.isoformat()})"
    )
    msg.set_content(_render_text(digest))
    msg.add_alternative(_render_html(digest), subtype="html")
    return msg


def send_ar_aging_digest(
    session: Session,
    *,
    recipients: Sequence[str],
    min_days_past_due: int = 0,
    as_of: Optional[date] = None,
    transport: Optional[Transport] = None,
    config: Optional[SmtpConfig] = None,
) -> ARDigest:
    """Build and send the AR aging digest. Returns the digest summary so
    callers can log totals or surface them in HTTP responses."""
    digest = build_ar_digest(session, as_of=as_of, min_days_past_due=min_days_past_due)
    cfg = config or SmtpConfig.from_env()
    msg = build_ar_email(digest, from_addr=cfg.from_addr, recipients=recipients)
    t = transport or default_transport()
    t.send(msg)
    return digest
