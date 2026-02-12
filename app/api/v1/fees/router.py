"""Fees router: class structure, assign, student fees, discount, payment, report."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_writable_academic_year
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import (
    AddCustomStudentFeeRequest,
    AssignTemplateFeesRequest,
    ClassFeeStructureCreate,
    ClassFeeStructureByClassResponse,
    ClassFeeStructureResponse,
    FeeReportItem,
    PaymentCreate,
    PaymentResponse,
    StudentFeeAssignmentResponse,
    StudentFeeAssignmentWithDetails,
    StudentFeeDiscountCreate,
    StudentFeeDiscountResponse,
)
from . import service

router = APIRouter(prefix="/api/v1/fees", tags=["fees"])


# --- Class Fee Structure ---
@router.post(
    "/class",
    response_model=ClassFeeStructureResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(check_permission("fees", "create")),
        Depends(require_writable_academic_year),
    ],
)
async def create_class_fee_structure(
    payload: ClassFeeStructureCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ClassFeeStructureResponse:
    try:
        return await service.create_class_fee_structure(
            db, current_user.tenant_id, payload
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/class/all",
    response_model=List[ClassFeeStructureByClassResponse],
    dependencies=[Depends(check_permission("fees", "read"))],
)
async def read_all_class_fees(
    academic_year_id: UUID,
    active_only: bool = Query(True, description="Return only active structures/components by default"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[ClassFeeStructureByClassResponse]:
    return await service.list_all_class_fees(
        db,
        current_user.tenant_id,
        academic_year_id,
        active_only=active_only,
    )


@router.get(
    "/class",
    response_model=List[ClassFeeStructureResponse],
    dependencies=[Depends(check_permission("fees", "read"))],
)
async def list_class_fee_structures(
    academic_year_id: UUID,
    class_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[ClassFeeStructureResponse]:
    return await service.list_class_fee_structures(
        db, current_user.tenant_id, academic_year_id, class_id=class_id
    )


# --- Student Fee Assignment ---
@router.post(
    "/assign/{student_id}",
    response_model=List[StudentFeeAssignmentResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(check_permission("fees", "create")),
        Depends(require_writable_academic_year),
    ],
)
async def assign_fee_to_student(
    student_id: UUID,
    payload: AssignTemplateFeesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[StudentFeeAssignmentResponse]:
    try:
        return await service.assign_template_fees_to_student(
            db,
            current_user.tenant_id,
            student_id,
            payload,
            changed_by=current_user.id,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/custom/{student_id}",
    response_model=StudentFeeAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(check_permission("fees", "create")),
        Depends(require_writable_academic_year),
    ],
)
async def add_custom_student_fee(
    student_id: UUID,
    payload: AddCustomStudentFeeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StudentFeeAssignmentResponse:
    try:
        return await service.add_custom_student_fee(
            db,
            current_user.tenant_id,
            student_id,
            payload,
            changed_by=current_user.id,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/student/{student_id}",
    response_model=List[StudentFeeAssignmentWithDetails],
    dependencies=[Depends(check_permission("fees", "read"))],
)
async def get_student_fees(
    student_id: UUID,
    academic_year_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[StudentFeeAssignmentWithDetails]:
    return await service.get_student_fees(
        db,
        current_user.tenant_id,
        student_id,
        academic_year_id=academic_year_id,
    )


# --- Discount ---
@router.post(
    "/discount/{student_fee_assignment_id}",
    response_model=StudentFeeDiscountResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(check_permission("fees", "update")),
        Depends(require_writable_academic_year),
    ],
)
async def add_discount(
    student_fee_assignment_id: UUID,
    payload: StudentFeeDiscountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StudentFeeDiscountResponse:
    try:
        return await service.add_discount(
            db,
            current_user.tenant_id,
            student_fee_assignment_id,
            payload,
            approved_by=current_user.id,
            current_user_role=current_user.role,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.patch(
    "/discount/{discount_id}/deactivate",
    response_model=StudentFeeDiscountResponse,
    dependencies=[
        Depends(check_permission("fees", "update")),
        Depends(require_writable_academic_year),
    ],
)
async def deactivate_discount(
    discount_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StudentFeeDiscountResponse:
    result = await service.deactivate_discount(
        db, current_user.tenant_id, discount_id, changed_by=current_user.id
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discount not found",
        )
    return result


# --- Payment ---
@router.post(
    "/pay/{student_fee_assignment_id}",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(check_permission("fees", "create")),
        Depends(require_writable_academic_year),
    ],
)
async def record_payment(
    student_fee_assignment_id: UUID,
    payload: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PaymentResponse:
    try:
        return await service.record_payment(
            db,
            current_user.tenant_id,
            student_fee_assignment_id,
            payload,
            collected_by=current_user.id,
            changed_by=current_user.id,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/payment-history/{student_id}",
    response_model=List[PaymentResponse],
    dependencies=[Depends(check_permission("fees", "read"))],
)
async def get_payment_history(
    student_id: UUID,
    academic_year_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[PaymentResponse]:
    return await service.get_payment_history(
        db,
        current_user.tenant_id,
        student_id,
        academic_year_id=academic_year_id,
    )


# --- Report ---
@router.get(
    "/report",
    response_model=List[FeeReportItem],
    dependencies=[Depends(check_permission("fees", "read"))],
)
async def get_fee_report(
    academic_year_id: UUID,
    class_id: Optional[UUID] = Query(None),
    fee_status: Optional[str] = Query(None, description="Filter by status: unpaid, partial, paid"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[FeeReportItem]:
    return await service.get_fee_report(
        db,
        current_user.tenant_id,
        academic_year_id,
        class_id=class_id,
        status_filter=fee_status,
    )
