"""Pydantic schemas for payroll API and consistent response wrapper."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ----- API response wrapper -----
class PayrollAPIResponse(BaseModel):
    success: bool = True
    message: str = ""
    data: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def ok(cls, message: str, data: Optional[Any] = None) -> "PayrollAPIResponse":
        return cls(success=True, message=message, data=data if isinstance(data, dict) else (data.model_dump() if data is not None and hasattr(data, "model_dump") else (data if isinstance(data, dict) else None)))


def wrap_data(data: Any) -> Optional[Dict[str, Any]]:
    if data is None:
        return None
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {"items": [x.model_dump() if hasattr(x, "model_dump") else x for x in data]}
    if hasattr(data, "model_dump"):
        return data.model_dump()
    return {"value": data}


# ----- Payroll Component -----
class PayrollComponentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    type: str = Field(..., pattern="^(earning|deduction)$")
    calculation_type: str = Field(..., pattern="^(fixed|percentage)$")
    default_value: Optional[Decimal] = None
    is_active: bool = True


class PayrollComponentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    type: Optional[str] = Field(None, pattern="^(earning|deduction)$")
    calculation_type: Optional[str] = Field(None, pattern="^(fixed|percentage)$")
    default_value: Optional[Decimal] = None
    is_active: Optional[bool] = None


class PayrollComponentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    code: str
    type: str
    calculation_type: str
    default_value: Optional[Decimal] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ----- Employee Salary Component -----
class EmployeeSalaryComponentCreate(BaseModel):
    employee_id: UUID
    component_id: UUID
    amount: Decimal = Field(..., ge=0)


class EmployeeSalaryComponentUpdate(BaseModel):
    amount: Optional[Decimal] = Field(None, ge=0)


class EmployeeSalaryComponentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    employee_id: UUID
    component_id: UUID
    amount: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ----- Employee assignments list (employee name + assigned components, for list + edit/delete) -----
class EmployeeAssignmentItem(BaseModel):
    """Single salary component assignment; id is used for PUT/DELETE."""
    id: UUID  # assignment (EmployeeSalaryComponent) id
    component_id: UUID
    component_name: str
    component_code: str
    component_type: str  # earning | deduction
    amount: Decimal

    model_config = ConfigDict(from_attributes=False)


class EmployeeWithAssignmentsResponse(BaseModel):
    """One employee with their assigned salary components and calculated totals."""
    employee_id: UUID
    employee_name: str
    salary_components: List[EmployeeAssignmentItem] = Field(default_factory=list)
    gross_salary: Decimal = Field(default=Decimal("0"))
    total_deductions: Decimal = Field(default=Decimal("0"))
    net_salary: Decimal = Field(default=Decimal("0"))

    model_config = ConfigDict(from_attributes=False)


# ----- Salary calculation result -----
class SalaryCalculationResult(BaseModel):
    gross_salary: Decimal
    total_deductions: Decimal
    net_salary: Decimal


# ----- Payroll Run -----
class PayrollRunCreate(BaseModel):
    month: str = Field(..., min_length=1, max_length=20)
    year: str = Field(..., min_length=1, max_length=10)


class PayrollRunResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    month: str
    year: str
    start_date: date
    end_date: date
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ----- Payroll Employee Record -----
class PayrollEmployeeRecordResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    payroll_run_id: UUID
    employee_id: UUID
    gross_salary: Decimal
    total_deductions: Decimal
    net_salary: Decimal
    payment_mode: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ----- Payslip Template -----
# Supported template_json variables when rendering: {{organization_name}}, {{employee_name}},
# {{employee_code}}, {{designation}}, {{period_start}}, {{period_end}}, {{gross_salary}}, {{net_salary}},
# plus per-component placeholders (e.g. {{basic_salary}}, {{hra}}, {{pf}}) as defined in the template.
class PayslipTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    template_json: Dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


class PayslipTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    template_json: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class PayslipTemplateResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    is_default: bool
    template_json: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ----- Payslip -----
class PayslipResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    employee_id: UUID
    payroll_run_id: UUID
    template_id: Optional[UUID] = None
    month: str
    year: str
    gross_salary: Decimal
    deductions: Decimal
    net_salary: Decimal
    payment_mode: str
    issued_at: Optional[datetime] = None
    pdf_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
