"""Fees schemas."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import StudentFeeSourceType, StudentFeeStatus


# --- Class Fee Structure ---
class ClassFeeStructureItem(BaseModel):
    """Fee component row inside a class fee structure (nested read-all response)."""

    id: UUID
    fee_component_id: UUID
    fee_component_name: str
    fee_component_code: str
    amount: Decimal
    frequency: str
    due_date: Optional[date] = None
    is_mandatory: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ClassFeeStructureByClassResponse(BaseModel):
    """Read all fees grouped by class."""

    academic_year_id: UUID
    class_id: UUID
    class_name: str
    items: List[ClassFeeStructureItem]


class ClassFeeStructureCreate(BaseModel):
    academic_year_id: UUID
    class_id: UUID
    fee_component_id: UUID
    amount: Decimal = Field(..., ge=0)
    frequency: str = Field(..., description="one_time, monthly, term_wise")
    due_date: Optional[date] = None
    is_mandatory: bool = True


class ClassFeeStructureUpdate(BaseModel):
    amount: Optional[Decimal] = Field(None, ge=0)
    frequency: Optional[str] = Field(None, description="one_time, monthly, term_wise")
    due_date: Optional[date] = None
    is_mandatory: Optional[bool] = None
    is_active: Optional[bool] = None


class ClassFeeStructureResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    academic_year_id: UUID
    class_id: UUID
    fee_component_id: UUID
    amount: Decimal
    frequency: str
    due_date: Optional[date] = None
    is_mandatory: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Student Fee Assignment ---
class AssignOptionalComponent(BaseModel):
    class_fee_structure_id: UUID
    custom_amount: Optional[Decimal] = Field(None, ge=0)


class AssignTemplateFeesRequest(BaseModel):
    academic_year_id: UUID
    optional_components: List[AssignOptionalComponent] = Field(default_factory=list)


class AddCustomStudentFeeRequest(BaseModel):
    academic_year_id: UUID
    custom_name: str = Field(..., max_length=255)
    amount: Decimal = Field(..., ge=0)
    reason: Optional[str] = None


class StudentFeeAssignmentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    academic_year_id: UUID
    student_id: UUID
    source_type: StudentFeeSourceType
    class_fee_structure_id: Optional[UUID] = None
    custom_name: Optional[str] = None
    base_amount: Decimal
    total_discount: Decimal
    final_amount: Decimal
    status: StudentFeeStatus
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StudentFeeAssignmentWithDetails(StudentFeeAssignmentResponse):
    fee_component_name: Optional[str] = None
    fee_component_code: Optional[str] = None
    class_name: Optional[str] = None


# --- Discount ---
class StudentFeeDiscountCreate(BaseModel):
    discount_name: str = Field(..., max_length=100)
    discount_category: str = Field(..., description="MASTER, CUSTOM, SYSTEM")
    discount_type: str = Field(..., description="fixed, percentage")
    discount_value: Decimal = Field(..., ge=0)
    reason: Optional[str] = None


class StudentFeeDiscountResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    academic_year_id: UUID
    student_fee_assignment_id: UUID
    discount_name: str
    discount_category: str
    discount_type: str
    discount_value: Decimal
    calculated_discount_amount: Decimal
    reason: Optional[str] = None
    approved_by: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Payment ---
class PaymentCreate(BaseModel):
    amount_paid: Decimal = Field(..., gt=0)
    payment_mode: str = Field(..., description="UPI, CARD, CASH, BANK")
    transaction_reference: Optional[str] = None
    paid_at: Optional[datetime] = None


class PaymentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    academic_year_id: UUID
    student_fee_assignment_id: UUID
    amount_paid: Decimal
    payment_mode: str
    transaction_reference: Optional[str] = None
    payment_status: str
    paid_at: datetime
    collected_by: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


# --- Report ---
class FeeReportItem(BaseModel):
    student_id: UUID
    student_name: Optional[str] = None
    class_id: UUID
    class_name: Optional[str] = None
    section_id: Optional[UUID] = None
    section_name: Optional[str] = None
    assignment_id: UUID
    fee_component_name: Optional[str] = None
    base_amount: Decimal
    total_discount: Decimal
    final_amount: Decimal
    amount_paid: Decimal
    balance: Decimal
    status: str
