"""Placeholder hooks for payroll / payslip integration related to holidays.

These functions are intentionally left unimplemented. The payroll module (when
introduced) should implement the logic to remove holiday references from
generated payslips or cached payroll calculations.
"""

from uuid import UUID


async def remove_holiday_references_from_payroll(
    tenant_id: UUID,
    academic_year_id: UUID,
    holiday_id: UUID,
) -> None:
    """Placeholder: remove holiday usage from payroll / payslip attachments."""
    # Implement this in the payroll module when available.
    return None

