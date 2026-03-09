"""Payroll business logic: salary calculation, payroll run, issue payslips, template CRUD."""

from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import ServiceError

from .enums import PaymentMode, PayrollStatus
from .models import (
    EmployeeSalaryComponent,
    PayrollComponent,
    PayrollEmployeeRecord,
    PayrollRun,
    Payslip,
    PayslipTemplate,
)
from .schemas import (
    EmployeeWithAssignmentsResponse,
    EmployeeAssignmentItem,
    PayrollComponentCreate,
    PayrollComponentUpdate,
    PayrollRunCreate,
    PayslipTemplateCreate,
    PayslipTemplateUpdate,
    SalaryCalculationResult,
)

MAX_TEMPLATES_PER_TENANT = 5
DEFAULT_PAYMENT_MODE = PaymentMode.bank.value


async def get_active_employee_ids(db: AsyncSession, tenant_id: UUID) -> List[UUID]:
    """Return list of active employee user IDs for the tenant."""
    q = (
        select(User.id)
        .where(
            User.tenant_id == tenant_id,
            User.user_type == "employee",
            User.status == "ACTIVE",
        )
    )
    result = await db.execute(q)
    return [r[0] for r in result.all()]


async def calculate_employee_salary(
    db: AsyncSession,
    tenant_id: UUID,
    employee_id: UUID,
) -> SalaryCalculationResult:
    """
    Fetch employee salary components, separate earnings and deductions, return gross, total_deductions, net.
    """
    stmt = (
        select(EmployeeSalaryComponent, PayrollComponent)
        .join(PayrollComponent, EmployeeSalaryComponent.component_id == PayrollComponent.id)
        .where(
            EmployeeSalaryComponent.tenant_id == tenant_id,
            EmployeeSalaryComponent.employee_id == employee_id,
            PayrollComponent.is_active.is_(True),
        )
    )
    result = await db.execute(stmt)
    rows = result.all()

    total_earnings = Decimal("0")
    total_deductions = Decimal("0")
    for esc, comp in rows:
        amt = esc.amount or Decimal("0")
        if comp.type == "earning":
            total_earnings += amt
        elif comp.type == "deduction":
            total_deductions += amt

    gross_salary = total_earnings
    net_salary = gross_salary - total_deductions
    return SalaryCalculationResult(
        gross_salary=gross_salary,
        total_deductions=total_deductions,
        net_salary=net_salary,
    )


def _month_start_end(month: str, year: str) -> tuple[date, date]:
    """Parse month/year and return (start_date, end_date) for the month."""
    try:
        m = int(month) if month.isdigit() else _month_name_to_num(month)
        y = int(year)
    except (ValueError, KeyError):
        raise ServiceError("Invalid month or year", status.HTTP_400_BAD_REQUEST)
    _, last_day = monthrange(y, m)
    return date(y, m, 1), date(y, m, last_day)


def _month_name_to_num(name: str) -> int:
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    }
    return months[name.strip().lower()]


async def create_payroll_run(
    db: AsyncSession,
    tenant_id: UUID,
    payload: PayrollRunCreate,
) -> PayrollRun:
    """
    Create payroll run, fetch all active employees, calculate salary for each, bulk insert payroll_employee_records.
    Raises ServiceError if duplicate (tenant_id, month, year).
    """
    start_date, end_date = _month_start_end(payload.month, payload.year)

    existing = await db.execute(
        select(PayrollRun).where(
            PayrollRun.tenant_id == tenant_id,
            PayrollRun.month == payload.month,
            PayrollRun.year == payload.year,
        )
    )
    if existing.scalar_one_or_none():
        raise ServiceError(
            "A payroll run already exists for this month and year",
            status.HTTP_409_CONFLICT,
        )

    run = PayrollRun(
        tenant_id=tenant_id,
        month=payload.month,
        year=payload.year,
        start_date=start_date,
        end_date=end_date,
        status=PayrollStatus.draft.value,
    )
    db.add(run)
    await db.flush()

    employee_ids = await get_active_employee_ids(db, tenant_id)
    records: List[PayrollEmployeeRecord] = []
    for emp_id in employee_ids:
        calc = await calculate_employee_salary(db, tenant_id, emp_id)
        records.append(
            PayrollEmployeeRecord(
                tenant_id=tenant_id,
                payroll_run_id=run.id,
                employee_id=emp_id,
                gross_salary=calc.gross_salary,
                total_deductions=calc.total_deductions,
                net_salary=calc.net_salary,
                payment_mode=DEFAULT_PAYMENT_MODE,
                status=PayrollStatus.draft.value,
            )
        )

    if records:
        db.add_all(records)
    await db.commit()
    await db.refresh(run)
    return run


async def issue_payslips(db: AsyncSession, tenant_id: UUID, run_id: UUID) -> PayrollRun:
    """
    Check payroll status; generate payslip for each employee record; store payslip; set run status to issued.
    """
    run = await db.get(PayrollRun, run_id)
    if not run or run.tenant_id != tenant_id:
        raise ServiceError("Payroll run not found", status.HTTP_404_NOT_FOUND)
    if run.status == PayrollStatus.issued.value:
        raise ServiceError("Payroll run is already issued", status.HTTP_400_BAD_REQUEST)

    default_template = await db.execute(
        select(PayslipTemplate).where(
            PayslipTemplate.tenant_id == tenant_id,
            PayslipTemplate.is_default.is_(True),
            PayslipTemplate.is_active.is_(True),
        )
    )
    template = default_template.scalar_one_or_none()

    records_q = await db.execute(
        select(PayrollEmployeeRecord).where(
            PayrollEmployeeRecord.payroll_run_id == run_id,
            PayrollEmployeeRecord.tenant_id == tenant_id,
        )
    )
    records = records_q.scalars().all()

    from datetime import datetime
    issued_at = datetime.utcnow()
    payslips: List[Payslip] = []
    for rec in records:
        payslips.append(
            Payslip(
                tenant_id=tenant_id,
                employee_id=rec.employee_id,
                payroll_run_id=run_id,
                template_id=template.id if template else None,
                month=run.month,
                year=run.year,
                gross_salary=rec.gross_salary,
                deductions=rec.total_deductions,
                net_salary=rec.net_salary,
                payment_mode=rec.payment_mode,
                issued_at=issued_at,
                pdf_url=None,
            )
        )

    if payslips:
        db.add_all(payslips)
    run.status = PayrollStatus.issued.value
    await db.commit()
    await db.refresh(run)
    return run


# ----- Payroll Components -----
async def create_component(
    db: AsyncSession,
    tenant_id: UUID,
    payload: PayrollComponentCreate,
) -> PayrollComponent:
    comp = PayrollComponent(
        tenant_id=tenant_id,
        name=payload.name,
        code=payload.code.strip().upper(),
        type=payload.type,
        calculation_type=payload.calculation_type,
        default_value=payload.default_value,
        is_active=payload.is_active,
    )
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return comp


async def list_components(
    db: AsyncSession,
    tenant_id: UUID,
    active_only: bool = True,
) -> List[PayrollComponent]:
    q = select(PayrollComponent).where(PayrollComponent.tenant_id == tenant_id)
    if active_only:
        q = q.where(PayrollComponent.is_active.is_(True))
    q = q.order_by(PayrollComponent.name)
    result = await db.execute(q)
    return list(result.scalars().all())


async def update_component(
    db: AsyncSession,
    tenant_id: UUID,
    component_id: UUID,
    payload: PayrollComponentUpdate,
) -> PayrollComponent:
    comp = await db.get(PayrollComponent, component_id)
    if not comp or comp.tenant_id != tenant_id:
        raise ServiceError("Payroll component not found", status.HTTP_404_NOT_FOUND)
    if payload.name is not None:
        comp.name = payload.name
    if payload.code is not None:
        comp.code = payload.code.strip().upper()
    if payload.type is not None:
        comp.type = payload.type
    if payload.calculation_type is not None:
        comp.calculation_type = payload.calculation_type
    if payload.default_value is not None:
        comp.default_value = payload.default_value
    if payload.is_active is not None:
        comp.is_active = payload.is_active
    await db.commit()
    await db.refresh(comp)
    return comp


async def get_component(db: AsyncSession, tenant_id: UUID, component_id: UUID) -> Optional[PayrollComponent]:
    comp = await db.get(PayrollComponent, component_id)
    return comp if comp and comp.tenant_id == tenant_id else None


# ----- Payslip Templates -----
async def count_templates(db: AsyncSession, tenant_id: UUID) -> int:
    q = select(func.count(PayslipTemplate.id)).where(PayslipTemplate.tenant_id == tenant_id)
    result = await db.execute(q)
    return result.scalar() or 0


async def create_payslip_template(
    db: AsyncSession,
    tenant_id: UUID,
    payload: PayslipTemplateCreate,
) -> PayslipTemplate:
    n = await count_templates(db, tenant_id)
    if n >= MAX_TEMPLATES_PER_TENANT:
        raise ServiceError("Maximum 5 templates allowed per tenant", status.HTTP_400_BAD_REQUEST)

    if payload.is_default:
        existing = (await db.execute(select(PayslipTemplate).where(PayslipTemplate.tenant_id == tenant_id))).scalars().all()
        for x in existing:
            x.is_default = False

    t = PayslipTemplate(
        tenant_id=tenant_id,
        name=payload.name,
        template_json=payload.template_json or {},
        is_default=payload.is_default,
        is_active=True,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def list_payslip_templates(
    db: AsyncSession,
    tenant_id: UUID,
    active_only: bool = True,
) -> List[PayslipTemplate]:
    q = select(PayslipTemplate).where(PayslipTemplate.tenant_id == tenant_id)
    if active_only:
        q = q.where(PayslipTemplate.is_active.is_(True))
    q = q.order_by(PayslipTemplate.name)
    result = await db.execute(q)
    return list(result.scalars().all())


async def update_payslip_template(
    db: AsyncSession,
    tenant_id: UUID,
    template_id: UUID,
    payload: PayslipTemplateUpdate,
) -> PayslipTemplate:
    t = await db.get(PayslipTemplate, template_id)
    if not t or t.tenant_id != tenant_id:
        raise ServiceError("Payslip template not found", status.HTTP_404_NOT_FOUND)

    if payload.name is not None:
        t.name = payload.name
    if payload.template_json is not None:
        t.template_json = payload.template_json
    if payload.is_default is not None:
        if payload.is_default:
            existing = (await db.execute(select(PayslipTemplate).where(PayslipTemplate.tenant_id == tenant_id))).scalars().all()
            for x in existing:
                x.is_default = False
        t.is_default = payload.is_default
    if payload.is_active is not None:
        t.is_active = payload.is_active
    await db.commit()
    await db.refresh(t)
    return t


async def delete_payslip_template(
    db: AsyncSession,
    tenant_id: UUID,
    template_id: UUID,
) -> None:
    t = await db.get(PayslipTemplate, template_id)
    if not t or t.tenant_id != tenant_id:
        raise ServiceError("Payslip template not found", status.HTTP_404_NOT_FOUND)
    await db.delete(t)
    await db.commit()


# ----- Payroll runs list / get -----
async def list_payroll_runs(
    db: AsyncSession,
    tenant_id: UUID,
) -> List[PayrollRun]:
    q = select(PayrollRun).where(PayrollRun.tenant_id == tenant_id).order_by(PayrollRun.year.desc(), PayrollRun.month.desc())
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_payroll_run(db: AsyncSession, tenant_id: UUID, run_id: UUID) -> Optional[PayrollRun]:
    run = await db.get(PayrollRun, run_id)
    return run if run and run.tenant_id == tenant_id else None


# ----- Employee salary component assignment -----
async def create_employee_salary_component(
    db: AsyncSession,
    tenant_id: UUID,
    employee_id: UUID,
    component_id: UUID,
    amount: Decimal,
) -> EmployeeSalaryComponent:
    comp = await get_component(db, tenant_id, component_id)
    if not comp:
        raise ServiceError("Payroll component not found", status.HTTP_404_NOT_FOUND)
    esc = EmployeeSalaryComponent(
        tenant_id=tenant_id,
        employee_id=employee_id,
        component_id=component_id,
        amount=amount,
    )
    db.add(esc)
    try:
        await db.commit()
        await db.refresh(esc)
        return esc
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Employee already has this component assigned", status.HTTP_409_CONFLICT)


async def list_employee_salary_components(
    db: AsyncSession,
    tenant_id: UUID,
    employee_id: UUID,
) -> List[EmployeeSalaryComponent]:
    q = (
        select(EmployeeSalaryComponent)
        .where(
            EmployeeSalaryComponent.tenant_id == tenant_id,
            EmployeeSalaryComponent.employee_id == employee_id,
        )
    )
    result = await db.execute(q)
    return list(result.scalars().all())


async def list_employees_with_assignments(
    db: AsyncSession,
    tenant_id: UUID,
) -> List[EmployeeWithAssignmentsResponse]:
    """
    List all active employees with their assigned salary components (name, code, type, amount)
    and calculated gross_salary, total_deductions, net_salary. Used for list view with edit/delete.
    """
    # All active employees
    users_q = (
        select(User.id, User.full_name)
        .where(
            User.tenant_id == tenant_id,
            User.user_type == "employee",
            User.status == "ACTIVE",
        )
        .order_by(User.full_name)
    )
    users_result = await db.execute(users_q)
    users = list(users_result.all())

    # All assignments with component details for this tenant
    assign_q = (
        select(EmployeeSalaryComponent, PayrollComponent)
        .join(PayrollComponent, EmployeeSalaryComponent.component_id == PayrollComponent.id)
        .where(
            EmployeeSalaryComponent.tenant_id == tenant_id,
            PayrollComponent.is_active.is_(True),
        )
    )
    assign_result = await db.execute(assign_q)
    rows = assign_result.all()

    # Group by employee_id
    by_employee: dict[UUID, List[tuple]] = defaultdict(list)
    for esc, comp in rows:
        by_employee[esc.employee_id].append((esc, comp))

    out: List[EmployeeWithAssignmentsResponse] = []
    for emp_id, full_name in users:
        items = by_employee.get(emp_id, [])
        assignments = [
            EmployeeAssignmentItem(
                id=esc.id,
                component_id=comp.id,
                component_name=comp.name,
                component_code=comp.code,
                component_type=comp.type,
                amount=esc.amount or Decimal("0"),
            )
            for esc, comp in items
        ]
        gross = Decimal("0")
        total_deductions = Decimal("0")
        for esc, comp in items:
            amt = esc.amount or Decimal("0")
            if comp.type == "earning":
                gross += amt
            elif comp.type == "deduction":
                total_deductions += amt
        net = gross - total_deductions
        out.append(
            EmployeeWithAssignmentsResponse(
                employee_id=emp_id,
                employee_name=full_name or "",
                salary_components=assignments,
                gross_salary=gross,
                total_deductions=total_deductions,
                net_salary=net,
            )
        )
    return out


async def get_employee_salary_component(
    db: AsyncSession,
    tenant_id: UUID,
    assignment_id: UUID,
) -> Optional[EmployeeSalaryComponent]:
    """Get a single assignment by id; returns None if not found or wrong tenant."""
    esc = await db.get(EmployeeSalaryComponent, assignment_id)
    return esc if esc and esc.tenant_id == tenant_id else None


async def update_employee_salary_component(
    db: AsyncSession,
    tenant_id: UUID,
    assignment_id: UUID,
    amount: Decimal,
) -> EmployeeSalaryComponent:
    """Update the amount of an employee salary component assignment."""
    esc = await get_employee_salary_component(db, tenant_id, assignment_id)
    if not esc:
        raise ServiceError("Employee salary component assignment not found", status.HTTP_404_NOT_FOUND)
    esc.amount = amount
    await db.commit()
    await db.refresh(esc)
    return esc


async def delete_employee_salary_component(
    db: AsyncSession,
    tenant_id: UUID,
    assignment_id: UUID,
) -> None:
    """Remove an employee salary component assignment."""
    esc = await get_employee_salary_component(db, tenant_id, assignment_id)
    if not esc:
        raise ServiceError("Employee salary component assignment not found", status.HTTP_404_NOT_FOUND)
    await db.delete(esc)
    await db.commit()


async def list_payroll_employee_records(
    db: AsyncSession,
    tenant_id: UUID,
    payroll_run_id: UUID,
) -> List[PayrollEmployeeRecord]:
    q = (
        select(PayrollEmployeeRecord)
        .where(
            PayrollEmployeeRecord.tenant_id == tenant_id,
            PayrollEmployeeRecord.payroll_run_id == payroll_run_id,
        )
    )
    result = await db.execute(q)
    return list(result.scalars().all())
