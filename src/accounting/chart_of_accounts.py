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
    AccountSpec("4020", "Accessorial Revenue", AccountType.REVENUE, "Generic accessorials (lumper, etc.)."),
    AccountSpec("4030", "Detention Revenue", AccountType.REVENUE, "Detention, layover, and wait time billed to the customer."),
    AccountSpec("4040", "Demurrage & Per Diem Revenue", AccountType.REVENUE, "Container demurrage, per diem, rail/yard storage billed to the customer."),
    AccountSpec("4050", "Chassis Revenue", AccountType.REVENUE, "Chassis split, flip, and rental rebilled to the customer."),
    AccountSpec("4060", "Port Pass-Through Revenue", AccountType.REVENUE, "TMF, pier pass, and other port fees rebilled to the customer."),
    AccountSpec("4070", "Drayage Accessorial Revenue", AccountType.REVENUE, "Pre-pull, drop, dry run, TONU, hazmat, reefer, residential, weekend/after-hours, scale, stop-off, etc."),
    AccountSpec("4100", "Brokerage Revenue", AccountType.REVENUE, "Margin on brokered loads."),
    AccountSpec("4900", "Interest Income", AccountType.REVENUE, "Bank account interest."),

    # --- Direct cost of services ---
    AccountSpec("5000", "Driver Wages", AccountType.EXPENSE, "Company-driver wages and per-diem."),
    AccountSpec("5010", "Owner-Operator Settlements", AccountType.EXPENSE, "Pay to owner-operators."),
    AccountSpec("5020", "Purchased Transportation", AccountType.EXPENSE, "Carrier pay on brokered loads."),
    AccountSpec("5100", "Fuel", AccountType.EXPENSE, "Diesel and DEF."),
    AccountSpec("5200", "Tolls", AccountType.EXPENSE, "Tolls and weigh-station fees."),
    AccountSpec("5210", "Port & Pier Pass Fees", AccountType.EXPENSE, "TMF, pier pass, and other port fees we pay."),
    AccountSpec("5220", "Chassis Rental", AccountType.EXPENSE, "Chassis pool / steamship-line chassis usage."),
    AccountSpec("5230", "Container Per Diem & Demurrage", AccountType.EXPENSE, "Per diem and demurrage we owe the steamship line / port."),
    AccountSpec("5260", "Drayage Accessorial Costs", AccountType.EXPENSE, "Pre-pull, drop, bobtail/deadhead, repositioning, scale, and other drayage-specific costs."),
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
    FUEL_SURCHARGE_REVENUE = "4010"
    DETENTION_REVENUE = "4030"
    DEMURRAGE_PER_DIEM_REVENUE = "4040"
    CHASSIS_REVENUE = "4050"
    PORT_PASSTHROUGH_REVENUE = "4060"
    DRAYAGE_ACCESSORIAL_REVENUE = "4070"
    FUEL = "5100"
    TOLLS = "5200"
    PORT_FEES = "5210"
    CHASSIS_RENTAL = "5220"
    CONTAINER_PER_DIEM_DEMURRAGE = "5230"
    DRAYAGE_ACCESSORIAL_COSTS = "5260"
    MAINTENANCE = "5300"
    PURCHASED_TRANSPORTATION = "5020"
