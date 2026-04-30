from datetime import date

import pytest

from accounting.models import ReconciliationStatus
from accounting.services import bank_rec, ledger
from accounting.services.bank_rec import BankRow
from accounting.services.ledger import LineSpec


CSV = """transaction_id,date,description,amount,balance
B-1,2026-04-02,Customer ACH ACME,5000.00,15000.00
B-2,2026-04-05,Fuel card ACH PILOT,-880.00,14120.00
B-3,2026-04-10,Office rent,-2200.00,11920.00
"""


def _bootstrap(session):
    """Open the period with $10,000 starting cash and post entries that
    correspond to the bank lines above plus one extra outstanding check."""
    ledger.install_chart(session)
    # Opening cash: $10,000
    ledger.post_entry(
        session,
        entry_date=date(2026, 3, 31),
        memo="Opening balance",
        lines=[
            LineSpec("1000", debit_cents=10_000_00),
            LineSpec("3000", credit_cents=10_000_00),
        ],
    )
    # Customer payment that should match B-1.
    ledger.post_entry(
        session,
        entry_date=date(2026, 4, 2),
        memo="Customer payment",
        lines=[
            LineSpec("1000", debit_cents=5_000_00),
            LineSpec("1100", credit_cents=5_000_00),
        ],
    )
    # Fuel-card payment that should match B-2 (date offset by 2 days).
    ledger.post_entry(
        session,
        entry_date=date(2026, 4, 3),
        memo="Pay fuel card",
        lines=[
            LineSpec("2000", debit_cents=880_00),
            LineSpec("1000", credit_cents=880_00),
        ],
    )
    # Rent payment that should match B-3.
    ledger.post_entry(
        session,
        entry_date=date(2026, 4, 10),
        memo="Office rent",
        lines=[
            LineSpec("6100", debit_cents=2_200_00),
            LineSpec("1000", credit_cents=2_200_00),
        ],
    )
    # Outstanding check (in book, not on bank).
    ledger.post_entry(
        session,
        entry_date=date(2026, 4, 28),
        memo="Vendor check #1099 (still floating)",
        lines=[
            LineSpec("2000", debit_cents=500_00),
            LineSpec("1000", credit_cents=500_00),
        ],
    )


def test_parse_csv_signed_amount(session):
    rows = bank_rec.parse_csv(CSV)
    assert len(rows) == 3
    assert rows[0].amount_cents == 500_000
    assert rows[1].amount_cents == -88_000
    assert rows[0].running_balance_cents == 1_500_000


def test_parse_csv_with_debit_credit_columns(session):
    csv_text = (
        "id,date,description,debit,credit\n"
        "X1,2026-04-01,deposit,,1000.00\n"
        "X2,2026-04-02,check 105,250.00,\n"
    )
    rows = bank_rec.parse_csv(csv_text)
    assert rows[0].amount_cents == 100_000
    assert rows[1].amount_cents == -25_000


def test_import_dedupes(session):
    _bootstrap(session)
    rows = bank_rec.parse_csv(CSV)
    r1 = bank_rec.import_rows(session, cash_account_code="1000", rows=rows)
    assert r1.inserted == 3 and r1.skipped_duplicates == 0

    r2 = bank_rec.import_rows(session, cash_account_code="1000", rows=rows)
    assert r2.inserted == 0 and r2.skipped_duplicates == 3


def test_auto_match_pairs_amount_and_date(session):
    _bootstrap(session)
    bank_rec.import_rows(
        session, cash_account_code="1000", rows=bank_rec.parse_csv(CSV)
    )
    rec = bank_rec.open_period(
        session,
        cash_account_code="1000",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        statement_start_balance=10_000.00,
        statement_end_balance=11_920.00,
    )
    created = bank_rec.auto_match(session, rec)
    assert created == 3

    s = bank_rec.summary(session, rec)
    assert len(s.unmatched_bank_lines) == 0
    # Outstanding $500 check on the books, not on the bank.
    assert len(s.unmatched_book_lines) == 1
    assert s.outstanding_outflows_cents == 50_000
    assert s.outstanding_inflows_cents == 0


def test_finalize_balances_against_statement(session):
    _bootstrap(session)
    bank_rec.import_rows(
        session, cash_account_code="1000", rows=bank_rec.parse_csv(CSV)
    )
    rec = bank_rec.open_period(
        session,
        cash_account_code="1000",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        statement_start_balance=10_000.00,
        statement_end_balance=11_920.00,
    )
    bank_rec.auto_match(session, rec)

    s = bank_rec.summary(session, rec)
    # Book balance: 10000 + 5000 - 880 - 2200 - 500 = 11420
    assert s.book_balance_cents == 1_142_000
    # Adjusted: 11420 - 0 + 500 = 11920 = bank ending
    assert s.is_balanced

    bank_rec.finalize(session, rec)
    assert rec.status == ReconciliationStatus.FINALIZED
    assert rec.finalized_at is not None


def test_finalize_refuses_when_unbalanced(session):
    _bootstrap(session)
    bank_rec.import_rows(
        session, cash_account_code="1000", rows=bank_rec.parse_csv(CSV)
    )
    rec = bank_rec.open_period(
        session,
        cash_account_code="1000",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        statement_start_balance=10_000.00,
        statement_end_balance=99_999.99,  # wrong on purpose
    )
    bank_rec.auto_match(session, rec)
    with pytest.raises(ValueError, match="does not balance"):
        bank_rec.finalize(session, rec)


def test_finalize_refuses_when_bank_lines_unmatched(session):
    _bootstrap(session)
    bank_rec.import_rows(
        session,
        cash_account_code="1000",
        rows=[
            BankRow(
                external_id="UNK-1",
                txn_date=date(2026, 4, 15),
                amount_cents=-1_000,
                description="Mystery fee",
            )
        ]
        + bank_rec.parse_csv(CSV),
    )
    rec = bank_rec.open_period(
        session,
        cash_account_code="1000",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        statement_start_balance=10_000.00,
        statement_end_balance=11_910.00,
    )
    bank_rec.auto_match(session, rec)
    with pytest.raises(ValueError, match="unmatched"):
        bank_rec.finalize(session, rec)


def test_manual_match_validates_amount(session):
    _bootstrap(session)
    bank_rec.import_rows(
        session,
        cash_account_code="1000",
        rows=[
            BankRow(
                external_id="X-1",
                txn_date=date(2026, 4, 15),
                amount_cents=12_345,
                description="weird",
            )
        ],
    )
    rec = bank_rec.open_period(
        session,
        cash_account_code="1000",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        statement_start_balance=10_000.00,
        statement_end_balance=10_000.00,
    )
    s = bank_rec.summary(session, rec)
    book_line = s.unmatched_book_lines[0]
    bank_line = s.unmatched_bank_lines[0]
    with pytest.raises(ValueError, match="Amounts disagree"):
        bank_rec.match_manually(
            session,
            rec,
            journal_line_id=book_line.id,
            bank_line_id=bank_line.id,
        )
