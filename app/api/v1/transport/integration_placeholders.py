"""Placeholder hooks for fee and payroll integration. Do not implement external modules."""

from decimal import Decimal
from uuid import UUID


async def create_student_fee_item(
    tenant_id: UUID,
    academic_year_id: UUID,
    student_id: UUID,
    amount: Decimal,
    description: str,
) -> None:
    """Placeholder: create student fee item when person_type=STUDENT and fee_mode=STUDENT_FEE."""
    pass


async def create_salary_deduction_entry(
    tenant_id: UUID,
    academic_year_id: UUID,
    person_id: UUID,
    person_type: str,
    amount: Decimal,
    description: str,
) -> None:
    """Placeholder: create salary deduction when person_type in (TEACHER, STAFF) and fee_mode=SALARY_DEDUCTION."""
    pass
