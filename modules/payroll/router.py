"""Payroll API router: components, runs, issue payslips, payslip templates."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from . import services
from .schemas import (
    PayrollAPIResponse,
    PayrollComponentCreate,
    PayrollComponentResponse,
    PayrollComponentUpdate,
    PayrollEmployeeRecordResponse,
    PayrollRunCreate,
    PayrollRunResponse,
    EmployeeSalaryComponentCreate,
    EmployeeSalaryComponentResponse,
    EmployeeSalaryComponentUpdate,
    EmployeeWithAssignmentsResponse,
    PayslipTemplateCreate,
    PayslipTemplateResponse,
    PayslipTemplateUpdate,
    SalaryCalculationResult,
)

router = APIRouter(prefix="/api/v1/payroll", tags=["payroll"])


def _ok(message: str, data=None):
    if data is None:
        return PayrollAPIResponse(success=True, message=message, data=None)
    if isinstance(data, list):
        return PayrollAPIResponse(success=True, message=message, data={"items": [x.model_dump() if hasattr(x, "model_dump") else x for x in data]})
    return PayrollAPIResponse(success=True, message=message, data=data.model_dump() if hasattr(data, "model_dump") else data)


# ----- Employee assignments (list all + edit/delete) - registered first so they appear in /docs -----
@router.get(
    "/employee-assignments",
    response_model=PayrollAPIResponse,
    dependencies=[Depends(check_permission("payroll", "read"))],
    summary="List employees with assigned salary components",
    operation_id="list_employee_assignments",
)
async def list_employee_assignments(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """List all employees with their assigned salary components (name, code, amount) and calculated salary. Use assignment id for edit/delete."""
    items = await services.list_employees_with_assignments(db, current_user.tenant_id)
    return _ok(
        "Employee assignments retrieved",
        [EmployeeWithAssignmentsResponse.model_validate(x) for x in items],
    )


@router.put(
    "/employee-components/{assignment_id}",
    response_model=PayrollAPIResponse,
    dependencies=[Depends(check_permission("payroll", "update"))],
    summary="Update employee salary component amount",
    operation_id="update_employee_salary_component",
)
async def update_employee_salary_component(
    assignment_id: UUID,
    payload: EmployeeSalaryComponentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """Update the amount of an employee salary component assignment."""
    if payload.amount is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="amount is required")
    try:
        esc = await services.update_employee_salary_component(
            db, current_user.tenant_id, assignment_id, payload.amount
        )
        return _ok("Employee salary component updated", EmployeeSalaryComponentResponse.model_validate(esc))
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/employee-components/{assignment_id}",
    response_model=PayrollAPIResponse,
    dependencies=[Depends(check_permission("payroll", "delete"))],
    summary="Delete employee salary component assignment",
    operation_id="delete_employee_salary_component",
)
async def delete_employee_salary_component(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """Remove an employee salary component assignment."""
    try:
        await services.delete_employee_salary_component(db, current_user.tenant_id, assignment_id)
        return PayrollAPIResponse(success=True, message="Employee salary component removed", data=None)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Payroll Run -----
@router.post(
    "/run",
    response_model=PayrollAPIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("payroll", "create"))],
)
async def create_payroll_run(
    payload: PayrollRunCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """Create a payroll run for the given month/year; fetches active employees and creates payroll records."""
    try:
        run = await services.create_payroll_run(db, current_user.tenant_id, payload)
        return _ok("Payroll run created", PayrollRunResponse.model_validate(run))
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/run",
    response_model=PayrollAPIResponse,
    dependencies=[Depends(check_permission("payroll", "read"))],
)
async def list_payroll_runs(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """List all payroll runs for the tenant."""
    runs = await services.list_payroll_runs(db, current_user.tenant_id)
    return _ok("Payroll runs retrieved", [PayrollRunResponse.model_validate(r) for r in runs])


@router.get(
    "/run/{run_id}",
    response_model=PayrollAPIResponse,
    dependencies=[Depends(check_permission("payroll", "read"))],
)
async def get_payroll_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """Get a single payroll run by ID."""
    run = await services.get_payroll_run(db, current_user.tenant_id, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll run not found")
    return _ok("Payroll run retrieved", PayrollRunResponse.model_validate(run))


@router.post(
    "/run/{run_id}/issue",
    response_model=PayrollAPIResponse,
    dependencies=[Depends(check_permission("payroll", "create"))],
)
async def issue_payslips(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """Issue payslips for the payroll run; generates payslip records and sets run status to issued."""
    try:
        run = await services.issue_payslips(db, current_user.tenant_id, run_id)
        return _ok("Payslips issued", PayrollRunResponse.model_validate(run))
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/run/{run_id}/records",
    response_model=PayrollAPIResponse,
    dependencies=[Depends(check_permission("payroll", "read"))],
)
async def list_payroll_run_records(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """List employee records for a payroll run."""
    records = await services.list_payroll_employee_records(db, current_user.tenant_id, run_id)
    return _ok("Payroll records retrieved", [PayrollEmployeeRecordResponse.model_validate(r) for r in records])


# ----- Employee salary component assignment -----
@router.post(
    "/employee-components",
    response_model=PayrollAPIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("payroll", "create"))],
)
async def create_employee_salary_component(
    payload: EmployeeSalaryComponentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """Assign a salary component to an employee with amount."""
    try:
        esc = await services.create_employee_salary_component(
            db, current_user.tenant_id, payload.employee_id, payload.component_id, payload.amount
        )
        return _ok("Employee salary component assigned", EmployeeSalaryComponentResponse.model_validate(esc))
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/employees/{employee_id}/salary-components",
    response_model=PayrollAPIResponse,
    dependencies=[Depends(check_permission("payroll", "read"))],
)
async def list_employee_salary_components(
    employee_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """List salary components assigned to an employee."""
    items = await services.list_employee_salary_components(db, current_user.tenant_id, employee_id)
    return _ok("Employee salary components retrieved", [EmployeeSalaryComponentResponse.model_validate(x) for x in items])


# ----- Salary calculation -----
@router.get(
    "/salary/calculate/{employee_id}",
    response_model=PayrollAPIResponse,
    dependencies=[Depends(check_permission("payroll", "read"))],
)
async def calculate_salary(
    employee_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """Calculate gross, deductions, and net salary for an employee from assigned components."""
    result = await services.calculate_employee_salary(db, current_user.tenant_id, employee_id)
    return _ok("Salary calculated", result)


# ----- Payroll Components -----
@router.post(
    "/components",
    response_model=PayrollAPIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("payroll", "create"))],
)
async def create_component(
    payload: PayrollComponentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """Create a payroll component (earning or deduction)."""
    comp = await services.create_component(db, current_user.tenant_id, payload)
    return _ok("Payroll component created", PayrollComponentResponse.model_validate(comp))


@router.get(
    "/components",
    response_model=PayrollAPIResponse,
    dependencies=[Depends(check_permission("payroll", "read"))],
)
async def list_components(
    active_only: bool = Query(True, description="Return only active components"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """List payroll components for the tenant."""
    comps = await services.list_components(db, current_user.tenant_id, active_only=active_only)
    return _ok("Payroll components retrieved", [PayrollComponentResponse.model_validate(c) for c in comps])


@router.put(
    "/components/{component_id}",
    response_model=PayrollAPIResponse,
    dependencies=[Depends(check_permission("payroll", "update"))],
)
async def update_component(
    component_id: UUID,
    payload: PayrollComponentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """Update a payroll component."""
    try:
        comp = await services.update_component(db, current_user.tenant_id, component_id, payload)
        return _ok("Payroll component updated", PayrollComponentResponse.model_validate(comp))
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Payslip Templates -----
@router.post(
    "/payslip-templates",
    response_model=PayrollAPIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("payroll", "create"))],
)
async def create_payslip_template(
    payload: PayslipTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """Create a payslip template. Maximum 5 templates per tenant."""
    try:
        t = await services.create_payslip_template(db, current_user.tenant_id, payload)
        return _ok("Payslip template created", PayslipTemplateResponse.model_validate(t))
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/payslip-templates",
    response_model=PayrollAPIResponse,
    dependencies=[Depends(check_permission("payroll", "read"))],
)
async def list_payslip_templates(
    active_only: bool = Query(True, description="Return only active templates"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """List payslip templates for the tenant."""
    templates = await services.list_payslip_templates(db, current_user.tenant_id, active_only=active_only)
    return _ok("Payslip templates retrieved", [PayslipTemplateResponse.model_validate(t) for t in templates])


@router.put(
    "/payslip-templates/{template_id}",
    response_model=PayrollAPIResponse,
    dependencies=[Depends(check_permission("payroll", "update"))],
)
async def update_payslip_template(
    template_id: UUID,
    payload: PayslipTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """Update a payslip template."""
    try:
        t = await services.update_payslip_template(db, current_user.tenant_id, template_id, payload)
        return _ok("Payslip template updated", PayslipTemplateResponse.model_validate(t))
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/payslip-templates/{template_id}",
    response_model=PayrollAPIResponse,
    dependencies=[Depends(check_permission("payroll", "delete"))],
)
async def delete_payslip_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollAPIResponse:
    """Delete a payslip template."""
    try:
        await services.delete_payslip_template(db, current_user.tenant_id, template_id)
        return PayrollAPIResponse(success=True, message="Payslip template deleted", data=None)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
