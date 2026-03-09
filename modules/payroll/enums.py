"""Payroll enums for component types, calculation, payment mode, and run status."""

from enum import Enum


class PayrollComponentType(str, Enum):
    earning = "earning"
    deduction = "deduction"


class PayrollCalculationType(str, Enum):
    fixed = "fixed"
    percentage = "percentage"


class PaymentMode(str, Enum):
    bank = "bank"
    cash = "cash"
    upi = "upi"
    cheque = "cheque"


class PayrollStatus(str, Enum):
    draft = "draft"
    processed = "processed"
    issued = "issued"
