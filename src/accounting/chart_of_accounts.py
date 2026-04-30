"""Default chart of accounts for a logistics / freight brokerage business.

Numbering convention (US GAAP-ish):
  1000-1999  Assets
  2000-2999  Liabilities
  3000-3999  Equity
  4000-4999  Revenue
  5000-5999  Cost of services (direct freight costs)
  6000-7999  Operating expenses
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from accounting.models.account import AccountType


@dataclass(frozen=True)
class AccountSpec:
    code: str
    name: str
    type: AccountType
    description: str = ""


DEFAULT_CHART: List[AccountSpec] = [
    # --- Assets ---
    AccountSpec("1000", "Operating Cash", AccountType.ASSET, "Primary checking account."),
    AccountSpec("1010", "Payroll Cash", AccountType.ASSET, "Driver and staff payroll account."),
    AccountSpec("1020", "Fuel Card Clearing", AccountType.ASSET, "Fuel card float pending settlement."),
    AccountSpec("1100", "Accounts Receivable", AccountType.ASSET, "Amounts owed by customers/shippers."),
    AccountSpec("1200", "Prepaid Insurance", AccountType.ASSET, "Auto liability and cargo insurance prepaid."),
    AccountSpec("1300", "Tires & Parts Inventory", AccountType.ASSET, "Spare parts and tires on hand."),
    AccountSpec("1500", "Tractors & Trailers", AccountType.ASSET, "Revenue equipment at cost."),
    AccountSpec("1510", "Accumulated Depreciation - Equipment", AccountType.ASSET, "Contra-asset; accumulated depreciation."),

    # --- Liabilities ---
    AccountSpec("2000", "Accounts Payable", AccountType.LIABILITY, "Amounts owed to vendors and carriers."),
    AccountSpec("2100", "Driver Wages Payable", AccountType.LIABILITY, "Accrued but unpaid driver wages."),
    AccountSpec("2200", "Payroll Taxes Payable", AccountType.LIABILITY, "Withheld and employer payroll taxes."),
    AccountSpec("2300", "Sales Tax Payable", AccountType.LIABILITY, "Where applicable on accessorials."),
    AccountSpec("2400", "Equipment Loans", AccountType.LIABILITY, "Tractor / trailer financing."),
    AccountSpec("2500", "Fuel Tax (IFTA) Payable", AccountType.LIABILITY, "Quarterly IFTA liability."),

    # --- Equity ---
    AccountSpec("3000", "Owner's Equity", AccountType.EQUITY),
    AccountSpec("3100", "Retained Earnings", AccountType.EQUITY),

    # --- Revenue ---
    AccountSpec("4000", "Freight Revenue", AccountType.REVENUE, "Line-haul revenue from shipments."),
    AccountSpec("4010", "Fuel Surcharge Revenue", AccountType.REVENUE, "Fuel surcharges billed to customers."),
    AccountSpec("4020", "Accessorial Revenue", AccountType.REVENUE, "Detention, layover, lumper, etc."),
    AccountSpec("4100", "Brokerage Revenue", AccountType.REVENUE, "Margin on brokered loads."),

    # --- Direct cost of services ---
    AccountSpec("5000", "Driver Wages", AccountType.EXPENSE, "Company-driver wages and per-diem."),
    AccountSpec("5010", "Owner-Operator Settlements", AccountType.EXPENSE, "Pay to owner-operators."),
    AccountSpec("5020", "Purchased Transportation", AccountType.EXPENSE, "Carrier pay on brokered loads."),
    AccountSpec("5100", "Fuel", AccountType.EXPENSE, "Diesel and DEF."),
    AccountSpec("5200", "Tolls", AccountType.EXPENSE, "Tolls and weigh-station fees."),
    AccountSpec("5300", "Vehicle Maintenance & Repairs", AccountType.EXPENSE),
    AccountSpec("5400", "Tires", AccountType.EXPENSE),
    AccountSpec("5500", "Cargo & Auto Insurance", AccountType.EXPENSE),
    AccountSpec("5600", "Permits, Licenses & IFTA", AccountType.EXPENSE),
    AccountSpec("5700", "Lumper & Loading Fees", AccountType.EXPENSE),

    # --- Operating expenses ---
    AccountSpec("6000", "Office Salaries", AccountType.EXPENSE),
    AccountSpec("6100", "Rent", AccountType.EXPENSE),
    AccountSpec("6200", "Utilities", AccountType.EXPENSE),
    AccountSpec("6300", "Telecom & ELD/Telematics", AccountType.EXPENSE),
    AccountSpec("6400", "Software & Subscriptions", AccountType.EXPENSE),
    AccountSpec("6500", "Professional Fees", AccountType.EXPENSE),
    AccountSpec("6600", "Bank & Factoring Fees", AccountType.EXPENSE),
    AccountSpec("6700", "Depreciation Expense", AccountType.EXPENSE),
    AccountSpec("6800", "Bad Debt Expense", AccountType.EXPENSE),
    AccountSpec("6900", "Other Operating Expense", AccountType.EXPENSE),
]


# Well-known account codes referenced by services. Centralized so callers don't
# pepper the codebase with magic strings.
class Codes:
    OPERATING_CASH = "1000"
    ACCOUNTS_RECEIVABLE = "1100"
    ACCOUNTS_PAYABLE = "2000"
    FREIGHT_REVENUE = "4000"
    FUEL = "5100"
    TOLLS = "5200"
    MAINTENANCE = "5300"
    PURCHASED_TRANSPORTATION = "5020"
