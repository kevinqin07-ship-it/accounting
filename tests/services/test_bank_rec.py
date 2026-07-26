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


def test_post_adjustment_for_bank_fee(session):
    _bootstrap(session)
    bank_rec.import_rows(
        session,
        cash_account_code="1000",
        rows=[
            BankRow(
                external_id="FEE-1",
                txn_date=date(2026, 4, 30),
                amount_cents=-1_500,
                description="Monthly bank fee",
            )
        ],
    )
    rec = bank_rec.open_period(
        session,
        cash_account_code="1000",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        statement_start_balance=10_000.00,
        statement_end_balance=9_985.00,
    )
    s_before = bank_rec.summary(session, rec)
    bank_line = s_before.unmatched_bank_lines[0]

    match = bank_rec.post_adjustment(
        session,
        rec,
        bank_line_id=bank_line.id,
        offsetting_account_code="6600",
        memo="April bank fee",
    )

    # Match links the new cash JE line to the bank line.
    assert match.bank_statement_line_id == bank_line.id
    # The bank line is no longer unmatched.
    s_after = bank_rec.summary(session, rec)
    assert all(b.id != bank_line.id for b in s_after.unmatched_bank_lines)
    # Cash decreased by $15 (bootstrap leaves 11420; after fee = 11405)
    # and bank-fee expense increased by $15.
    assert ledger.account_balance(session, "1000") == 1_140_500
    assert ledger.account_balance(session, "6600") == 1_500


def test_post_adjustment_for_interest_income(session):
    _bootstrap(session)
    bank_rec.import_rows(
        session,
        cash_account_code="1000",
        rows=[
            BankRow(
                external_id="INT-1",
                txn_date=date(2026, 4, 30),
                amount_cents=750,
                description="Interest paid",
            )
        ],
    )
    rec = bank_rec.open_period(
        session,
        cash_account_code="1000",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        statement_start_balance=10_000.00,
        statement_end_balance=10_007.50,
    )
    bank_line = bank_rec.summary(session, rec).unmatched_bank_lines[0]

    bank_rec.post_adjustment(
        session,
        rec,
        bank_line_id=bank_line.id,
        offsetting_account_code="4900",
    )
    # Bootstrap leaves 11420; after $7.50 interest credit = 11427.50.
    assert ledger.account_balance(session, "1000") == 1_142_750
    assert ledger.account_balance(session, "4900") == 750


def test_post_adjustment_rejects_already_matched(session):
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
    # B-1 is now matched. Trying to adjust it should fail.
    from accounting.models import BankStatementLine
    from sqlalchemy import select

    bank_line = session.scalar(
        select(BankStatementLine).where(BankStatementLine.external_id == "B-1")
    )
    with pytest.raises(ValueError, match="already matched"):
        bank_rec.post_adjustment(
            session,
            rec,
            bank_line_id=bank_line.id,
            offsetting_account_code="6600",
        )


def test_post_adjustment_rejects_self_offset(session):
    _bootstrap(session)
    bank_rec.import_rows(
        session,
        cash_account_code="1000",
        rows=[
            BankRow(
                external_id="FEE-X",
                txn_date=date(2026, 4, 30),
                amount_cents=-100,
                description="x",
            )
        ],
    )
    rec = bank_rec.open_period(
        session,
        cash_account_code="1000",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        statement_start_balance=10_000.00,
        statement_end_balance=9_999.00,
    )
    bank_line = bank_rec.summary(session, rec).unmatched_bank_lines[0]
    with pytest.raises(ValueError, match="cannot be the cash account"):
        bank_rec.post_adjustment(
            session,
            rec,
            bank_line_id=bank_line.id,
            offsetting_account_code="1000",
        )


def test_adjustment_lets_finalize_succeed(session):
    """End-to-end: bank statement has a fee that's nowhere on the books.
    Posting an adjustment for it should let the period finalize cleanly."""
    _bootstrap(session)
    bank_rec.import_rows(
        session,
        cash_account_code="1000",
        rows=bank_rec.parse_csv(CSV)
        + [
            BankRow(
                external_id="FEE-A",
                txn_date=date(2026, 4, 30),
                amount_cents=-1_500,
                description="Monthly fee",
            )
        ],
    )
    rec = bank_rec.open_period(
        session,
        cash_account_code="1000",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        statement_start_balance=10_000.00,
        statement_end_balance=11_905.00,  # 11920 - 15 fee
    )
    bank_rec.auto_match(session, rec)
    fee_line = next(
        b for b in bank_rec.summary(session, rec).unmatched_bank_lines
        if b.external_id == "FEE-A"
    )
    bank_rec.post_adjustment(
        session,
        rec,
        bank_line_id=fee_line.id,
        offsetting_account_code="6600",
        memo="April bank fee",
    )
    bank_rec.finalize(session, rec)
    from accounting.models import ReconciliationStatus

    assert rec.status == ReconciliationStatus.FINALIZED


def test_settle_disbursements_clears_payable_against_bank_outflow(session):
    """End-to-end: weekly accrual + bank disbursement match closes the
    loop. After both, 2100 returns to zero and the bank line is matched."""
    ledger.install_chart(session)
    # Opening cash so the reconciliation has a sensible start balance.
    ledger.post_entry(
        session,
        entry_date=date(2026, 4, 30),
        memo="Opening",
        lines=[
            LineSpec("1000", debit_cents=10_000_00),
            LineSpec("3000", credit_cents=10_000_00),
        ],
    )
    # Weekly accrual JE: DR 5000, CR 2100 for $1,500.
    ledger.post_entry(
        session,
        entry_date=date(2026, 5, 3),
        memo="Driver pay aggregate",
        reference="SETTLE-AGG:2026-04-27..2026-05-03",
        lines=[
            LineSpec("5000", debit_cents=1_500_00),
            LineSpec("2100", credit_cents=1_500_00),
        ],
    )
    assert ledger.account_balance(session, "2100") == 150_000

    # Bank statement: one ACH PAYROLL withdrawal for $1,500.
    bank_rec.import_rows(
        session,
        cash_account_code="1000",
        rows=[
            bank_rec.BankRow(
                external_id="ACH-PR-99",
                txn_date=date(2026, 5, 5),
                amount_cents=-1_500_00,
                description="ACH PAYROLL DRIVER PAY week 18",
            )
        ],
    )
    rec = bank_rec.open_period(
        session,
        cash_account_code="1000",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        statement_start_balance=10_000.00,
        statement_end_balance=8_500.00,
    )

    matches = bank_rec.settle_disbursements(session, rec)
    assert len(matches) == 1

    # Payable cleared, cash decreased.
    assert ledger.account_balance(session, "2100") == 0
    assert ledger.account_balance(session, "1000") == 850_000

    # Bank line is matched; reconciliation balances.
    s = bank_rec.summary(session, rec)
    assert s.unmatched_bank_lines == []
    assert s.is_balanced

    bank_rec.finalize(session, rec)


def test_settle_disbursements_skips_non_matching_lines(session):
    ledger.install_chart(session)
    ledger.post_entry(
        session,
        entry_date=date(2026, 4, 30),
        memo="Opening",
        lines=[
            LineSpec("1000", debit_cents=10_000_00),
            LineSpec("3000", credit_cents=10_000_00),
        ],
    )
    bank_rec.import_rows(
        session,
        cash_account_code="1000",
        rows=[
            bank_rec.BankRow(
                external_id="UTIL-1",
                txn_date=date(2026, 5, 4),
                amount_cents=-100_00,
                description="ELECTRIC COMPANY MONTHLY",
            ),
            bank_rec.BankRow(
                external_id="DEP-1",
                txn_date=date(2026, 5, 5),
                amount_cents=500_00,
                description="ACH PAYROLL deposit refund",  # inflow despite pattern
            ),
        ],
    )
    rec = bank_rec.open_period(
        session,
        cash_account_code="1000",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        statement_start_balance=10_000.00,
        statement_end_balance=10_400.00,
    )
    matches = bank_rec.settle_disbursements(session, rec)
    assert matches == []
    s = bank_rec.summary(session, rec)
    assert len(s.unmatched_bank_lines) == 2  # both untouched


def test_settle_disbursements_custom_patterns_and_account(session):
    """The same flow can clear other accruals (e.g. carrier pay)."""
    ledger.install_chart(session)
    ledger.post_entry(
        session,
        entry_date=date(2026, 4, 30),
        memo="Opening",
        lines=[
            LineSpec("1000", debit_cents=10_000_00),
            LineSpec("3000", credit_cents=10_000_00),
        ],
    )
    # Pretend an AP balance exists.
    ledger.post_entry(
        session,
        entry_date=date(2026, 5, 3),
        memo="Carrier accrual",
        lines=[
            LineSpec("5020", debit_cents=2_000_00),
            LineSpec("2000", credit_cents=2_000_00),
        ],
    )
    bank_rec.import_rows(
        session,
        cash_account_code="1000",
        rows=[
            bank_rec.BankRow(
                external_id="ACH-CARRIER",
                txn_date=date(2026, 5, 7),
                amount_cents=-2_000_00,
                description="WIRE CARRIER PAY swift",
            )
        ],
    )
    rec = bank_rec.open_period(
        session,
        cash_account_code="1000",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        statement_start_balance=10_000.00,
        statement_end_balance=8_000.00,
    )
    matches = bank_rec.settle_disbursements(
        session,
        rec,
        payable_account_code="2000",
        description_patterns=["CARRIER PAY"],
    )
    assert len(matches) == 1
    assert ledger.account_balance(session, "2000") == 0


def test_settle_disbursements_refuses_after_finalize(session):
    ledger.install_chart(session)
    ledger.post_entry(
        session,
        entry_date=date(2026, 4, 30),
        memo="Opening",
        lines=[
            LineSpec("1000", debit_cents=10_000_00),
            LineSpec("3000", credit_cents=10_000_00),
        ],
    )
    rec = bank_rec.open_period(
        session,
        cash_account_code="1000",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        statement_start_balance=10_000.00,
        statement_end_balance=10_000.00,
    )
    bank_rec.finalize(session, rec)
    with pytest.raises(ValueError, match="finalized"):
        bank_rec.settle_disbursements(session, rec)


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
