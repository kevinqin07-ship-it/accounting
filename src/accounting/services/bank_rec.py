"""Bank statement import and reconciliation against cash-account ledger lines.

Workflow:

  1. import_csv()   - load a bank statement CSV. Dedup on external_id.
  2. open_period()  - start a Reconciliation for a cash account and date range.
  3. auto_match()   - greedy 1:1 match by exact amount + date proximity.
  4. (optional) match_manually() / unmatch() to clean up edge cases.
  5. summary()      - see the standard reconciliation arithmetic.
  6. finalize()     - lock the period; refuses if it doesn't balance.

Sign convention for BankStatementLine.amount_cents:
    +N  = credit on the bank = inflow to our cash    (matches a JournalLine debit)
    -N  = debit on the bank  = outflow from our cash (matches a JournalLine credit)

So we compare bank `amount_cents` to journal-line `signed_amount()` directly.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import StringIO
from typing import IO, Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounting.money import to_cents
from accounting.models import (
    Account,
    BankMatch,
    BankStatementLine,
    JournalEntry,
    JournalLine,
    Reconciliation,
    ReconciliationStatus,
)
from accounting.services import ledger


# --- CSV parsing ---------------------------------------------------------

@dataclass
class BankRow:
    external_id: str
    txn_date: date
    amount_cents: int  # signed
    description: Optional[str] = None
    running_balance_cents: Optional[int] = None


_COLUMNS = {
    "external_id": ("external_id", "transaction_id", "txn_id", "id", "reference"),
    "txn_date": ("txn_date", "date", "posted_date", "transaction_date"),
    "description": ("description", "memo", "details", "payee"),
    "amount": ("amount", "net_amount", "value"),
    "debit": ("debit", "withdrawal"),
    "credit": ("credit", "deposit"),
    "balance": ("balance", "running_balance"),
}


def _pick(row: dict[str, str], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _parse_date(s: str) -> date:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Could not parse date: {s!r}")


def parse_csv(text: str | IO[str]) -> List[BankRow]:
    """Parse a bank CSV. Accepts either a single signed `amount` column or
    separate `debit`/`credit` columns (we then sign appropriately)."""
    if isinstance(text, str):
        reader = csv.DictReader(StringIO(text))
    else:
        reader = csv.DictReader(text)

    out: List[BankRow] = []
    for raw in reader:
        norm = {
            k.strip().lower(): (v.strip() if isinstance(v, str) else v)
            for k, v in raw.items()
            if k
        }
        external_id = _pick(norm, _COLUMNS["external_id"])
        txn_date_str = _pick(norm, _COLUMNS["txn_date"])
        if not (external_id and txn_date_str):
            raise ValueError(f"Bank row missing required fields: {raw!r}")

        signed_amount = _pick(norm, _COLUMNS["amount"])
        if signed_amount is not None:
            amount = to_cents(signed_amount)
        else:
            debit = _pick(norm, _COLUMNS["debit"])
            credit = _pick(norm, _COLUMNS["credit"])
            if not (debit or credit):
                raise ValueError(f"Bank row has no amount/debit/credit: {raw!r}")
            amount = (to_cents(credit) if credit else 0) - (to_cents(debit) if debit else 0)

        balance = _pick(norm, _COLUMNS["balance"])
        out.append(
            BankRow(
                external_id=external_id,
                txn_date=_parse_date(txn_date_str),
                amount_cents=amount,
                description=_pick(norm, _COLUMNS["description"]) or None,
                running_balance_cents=to_cents(balance) if balance else None,
            )
        )
    return out


# --- Import --------------------------------------------------------------

@dataclass
class ImportResult:
    inserted: int
    skipped_duplicates: int


def import_rows(
    session: Session,
    *,
    cash_account_code: str,
    rows: Sequence[BankRow],
) -> ImportResult:
    cash = ledger.get_account(session, cash_account_code)
    existing = {
        ext for (ext,) in session.execute(
            select(BankStatementLine.external_id).where(
                BankStatementLine.cash_account_id == cash.id
            )
        )
    }
    inserted = skipped = 0
    for row in rows:
        if row.external_id in existing:
            skipped += 1
            continue
        session.add(
            BankStatementLine(
                cash_account_id=cash.id,
                external_id=row.external_id,
                txn_date=row.txn_date,
                amount_cents=row.amount_cents,
                description=row.description,
                running_balance_cents=row.running_balance_cents,
            )
        )
        existing.add(row.external_id)
        inserted += 1
    session.flush()
    return ImportResult(inserted=inserted, skipped_duplicates=skipped)


# --- Reconciliation lifecycle -------------------------------------------

def open_period(
    session: Session,
    *,
    cash_account_code: str,
    period_start: date,
    period_end: date,
    statement_start_balance,
    statement_end_balance,
) -> Reconciliation:
    cash = ledger.get_account(session, cash_account_code)
    rec = Reconciliation(
        cash_account_id=cash.id,
        period_start=period_start,
        period_end=period_end,
        statement_start_balance_cents=to_cents(statement_start_balance),
        statement_end_balance_cents=to_cents(statement_end_balance),
        status=ReconciliationStatus.OPEN,
    )
    session.add(rec)
    session.flush()
    return rec


def _book_lines_through(session: Session, rec: Reconciliation) -> List[JournalLine]:
    """All journal lines on this cash account dated <= period_end. These are
    the candidates for matching: a check written before period_start may
    still clear in the period."""
    return list(
        session.scalars(
            select(JournalLine)
            .join(JournalEntry)
            .where(
                JournalLine.account_id == rec.cash_account_id,
                JournalEntry.entry_date <= rec.period_end,
            )
            .order_by(JournalEntry.entry_date, JournalLine.id)
        )
    )


def _book_lines_in_period(session: Session, rec: Reconciliation) -> List[JournalLine]:
    """Journal lines dated within the reconciliation period. Only these are
    counted as 'outstanding' if they remain unmatched at finalize time;
    anything before period_start is presumed reflected in
    statement_start_balance."""
    return list(
        session.scalars(
            select(JournalLine)
            .join(JournalEntry)
            .where(
                JournalLine.account_id == rec.cash_account_id,
                JournalEntry.entry_date >= rec.period_start,
                JournalEntry.entry_date <= rec.period_end,
            )
            .order_by(JournalEntry.entry_date, JournalLine.id)
        )
    )


def _bank_lines_in_period(session: Session, rec: Reconciliation) -> List[BankStatementLine]:
    return list(
        session.scalars(
            select(BankStatementLine)
            .where(
                BankStatementLine.cash_account_id == rec.cash_account_id,
                BankStatementLine.txn_date >= rec.period_start,
                BankStatementLine.txn_date <= rec.period_end,
            )
            .order_by(BankStatementLine.txn_date, BankStatementLine.id)
        )
    )


def _matched_journal_line_ids(session: Session, rec: Reconciliation) -> set[int]:
    return {
        m.journal_line_id
        for m in session.scalars(
            select(BankMatch).where(BankMatch.reconciliation_id == rec.id)
        )
    }


def _matched_bank_line_ids(session: Session, rec: Reconciliation) -> set[int]:
    return {
        m.bank_statement_line_id
        for m in session.scalars(
            select(BankMatch).where(BankMatch.reconciliation_id == rec.id)
        )
    }


def auto_match(
    session: Session,
    rec: Reconciliation,
    *,
    date_tolerance_days: int = 5,
) -> int:
    """Greedy 1:1 match by signed amount and date proximity. Returns the
    number of matches created. Already-matched lines on either side are
    excluded; ambiguous matches (same amount, multiple candidates) are
    resolved by smallest date difference, then earliest journal line id."""
    if rec.status != ReconciliationStatus.OPEN:
        raise ValueError("Cannot match against a finalized reconciliation.")

    matched_book = _matched_journal_line_ids(session, rec)
    matched_bank = _matched_bank_line_ids(session, rec)

    book_candidates = [
        line
        for line in _book_lines_through(session, rec)
        if line.id not in matched_book
    ]
    bank_candidates = [
        line
        for line in _bank_lines_in_period(session, rec)
        if line.id not in matched_bank
    ]

    # Index book lines by signed amount for O(1) candidate lookup.
    book_by_amount: dict[int, list[JournalLine]] = {}
    for line in book_candidates:
        book_by_amount.setdefault(line.signed_amount(), []).append(line)

    created = 0
    used_book_ids: set[int] = set()
    for bank_line in bank_candidates:
        candidates = [
            book
            for book in book_by_amount.get(bank_line.amount_cents, [])
            if book.id not in used_book_ids
        ]
        if not candidates:
            continue
        # Score by absolute date difference and prefer earliest journal line
        # if there's still a tie.
        candidates.sort(
            key=lambda b: (
                abs((b.entry.entry_date - bank_line.txn_date).days),
                b.id,
            )
        )
        best = candidates[0]
        delta = abs((best.entry.entry_date - bank_line.txn_date).days)
        if delta > date_tolerance_days:
            continue
        session.add(
            BankMatch(
                reconciliation_id=rec.id,
                journal_line_id=best.id,
                bank_statement_line_id=bank_line.id,
            )
        )
        used_book_ids.add(best.id)
        created += 1
    session.flush()
    return created


def match_manually(
    session: Session,
    rec: Reconciliation,
    *,
    journal_line_id: int,
    bank_line_id: int,
    note: Optional[str] = None,
) -> BankMatch:
    if rec.status != ReconciliationStatus.OPEN:
        raise ValueError("Cannot match against a finalized reconciliation.")

    journal_line = session.get(JournalLine, journal_line_id)
    bank_line = session.get(BankStatementLine, bank_line_id)
    if journal_line is None:
        raise LookupError(f"JournalLine {journal_line_id} not found.")
    if bank_line is None:
        raise LookupError(f"BankStatementLine {bank_line_id} not found.")
    if journal_line.account_id != rec.cash_account_id:
        raise ValueError("Journal line is not on this reconciliation's cash account.")
    if bank_line.cash_account_id != rec.cash_account_id:
        raise ValueError("Bank line is not on this reconciliation's cash account.")
    if journal_line.signed_amount() != bank_line.amount_cents:
        raise ValueError(
            f"Amounts disagree: book={journal_line.signed_amount()} bank={bank_line.amount_cents}"
        )

    match = BankMatch(
        reconciliation_id=rec.id,
        journal_line_id=journal_line_id,
        bank_statement_line_id=bank_line_id,
        note=note,
    )
    session.add(match)
    session.flush()
    return match


def unmatch(session: Session, match_id: int) -> None:
    match = session.get(BankMatch, match_id)
    if match is None:
        raise LookupError(f"BankMatch {match_id} not found.")
    if match.reconciliation.status != ReconciliationStatus.OPEN:
        raise ValueError("Cannot unmatch on a finalized reconciliation.")
    session.delete(match)
    session.flush()


# --- Summary and finalize -----------------------------------------------

@dataclass
class ReconciliationSummary:
    rec: Reconciliation
    opening_book_balance_cents: int
    book_balance_cents: int
    statement_start_balance_cents: int
    statement_end_balance_cents: int
    outstanding_inflows_cents: int   # in-period book debits not yet on the bank
    outstanding_outflows_cents: int  # in-period book credits not yet on the bank
    unmatched_bank_lines: List[BankStatementLine]
    unmatched_book_lines: List[JournalLine]

    @property
    def opening_difference_cents(self) -> int:
        return self.opening_book_balance_cents - self.statement_start_balance_cents

    @property
    def adjusted_book_balance_cents(self) -> int:
        return (
            self.book_balance_cents
            - self.outstanding_inflows_cents
            + self.outstanding_outflows_cents
        )

    @property
    def ending_difference_cents(self) -> int:
        return self.adjusted_book_balance_cents - self.statement_end_balance_cents

    @property
    def is_balanced(self) -> bool:
        return self.opening_difference_cents == 0 and self.ending_difference_cents == 0


def summary(session: Session, rec: Reconciliation) -> ReconciliationSummary:
    cash_code = rec.cash_account.code
    book_balance = ledger.account_balance(session, cash_code, as_of=rec.period_end)
    opening_balance = ledger.account_balance(
        session, cash_code, as_of=rec.period_start - timedelta(days=1)
    )

    matched_book = _matched_journal_line_ids(session, rec)
    matched_bank = _matched_bank_line_ids(session, rec)

    in_period_unmatched_book = [
        line
        for line in _book_lines_in_period(session, rec)
        if line.id not in matched_book
    ]
    unmatched_bank = [
        line
        for line in _bank_lines_in_period(session, rec)
        if line.id not in matched_bank
    ]

    outstanding_inflows = sum(
        line.debit_cents for line in in_period_unmatched_book if line.debit_cents > 0
    )
    outstanding_outflows = sum(
        line.credit_cents for line in in_period_unmatched_book if line.credit_cents > 0
    )

    return ReconciliationSummary(
        rec=rec,
        opening_book_balance_cents=opening_balance,
        book_balance_cents=book_balance,
        statement_start_balance_cents=rec.statement_start_balance_cents,
        statement_end_balance_cents=rec.statement_end_balance_cents,
        outstanding_inflows_cents=outstanding_inflows,
        outstanding_outflows_cents=outstanding_outflows,
        unmatched_bank_lines=unmatched_bank,
        unmatched_book_lines=in_period_unmatched_book,
    )


def finalize(session: Session, rec: Reconciliation) -> ReconciliationSummary:
    """Lock the reconciliation. Refuses to finalize if:
       - any bank line in the period is unmatched,
       - the opening book balance doesn't agree with the statement start, or
       - the standard reconciliation arithmetic doesn't balance at the end.
    """
    if rec.status != ReconciliationStatus.OPEN:
        raise ValueError("Reconciliation is already finalized.")

    s = summary(session, rec)
    if s.unmatched_bank_lines:
        raise ValueError(
            f"{len(s.unmatched_bank_lines)} bank line(s) in the period are unmatched. "
            "Either match them to book entries or post adjusting journal entries (for fees, interest, etc.)."
        )
    if s.opening_difference_cents != 0:
        raise ValueError(
            f"Opening book balance {s.opening_book_balance_cents} does not match "
            f"statement start balance {s.statement_start_balance_cents} "
            f"(difference {s.opening_difference_cents} cents)."
        )
    if s.ending_difference_cents != 0:
        raise ValueError(
            f"Reconciliation does not balance: difference = {s.ending_difference_cents} cents. "
            f"Book {s.book_balance_cents} - in-transit deposits {s.outstanding_inflows_cents} "
            f"+ outstanding checks {s.outstanding_outflows_cents} != bank {s.statement_end_balance_cents}."
        )
    rec.status = ReconciliationStatus.FINALIZED
    rec.finalized_at = datetime.utcnow()
    session.flush()
    return s
