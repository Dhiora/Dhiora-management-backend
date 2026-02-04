from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import (
    AdmissionRequestCreate,
    AdmissionRequestApprove,
    AdmissionRequestReject,
    AdmissionRequestResponse,
    AdmissionStudentActivate,
    AdmissionStudentResponse,
)
from . import service

router = APIRouter(prefix="/api/v1/admissions", tags=["admissions"])


# ----- Admission requests -----

@router.post(
    "/requests",
    response_model=AdmissionRequestResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("admissions", "create"))],
)
async def create_admission_request(
    payload: AdmissionRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AdmissionRequestResponse:
    """Raise an admission request. Track is set by backend (teacher/referral/website/admin/parent_direct)."""
    try:
        return await service.create_admission_request(
            db,
            current_user.tenant_id,
            payload,
            raised_by_user_id=current_user.id,
            raised_by_role=current_user.role,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/requests/my",
    response_model=List[AdmissionRequestResponse],
    dependencies=[Depends(check_permission("admissions", "read"))],
)
async def list_my_admission_requests(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[AdmissionRequestResponse]:
    """List admission requests raised by the current user."""
    return await service.list_my_admission_requests(
        db,
        current_user.tenant_id,
        current_user.id,
    )


@router.get(
    "/requests",
    response_model=List[AdmissionRequestResponse],
    dependencies=[Depends(check_permission("admissions", "read"))],
)
async def list_admission_requests(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: PENDING_APPROVAL, APPROVED, REJECTED"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[AdmissionRequestResponse]:
    """List all admission requests for the tenant, optionally filter by status."""
    return await service.list_admission_requests(
        db,
        current_user.tenant_id,
        status_filter=status_filter,
    )


@router.post(
    "/requests/{request_id}/approve",
    response_model=AdmissionRequestResponse,
    dependencies=[Depends(check_permission("admissions", "update"))],
)
async def approve_admission_request(
    request_id: UUID,
    payload: AdmissionRequestApprove,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AdmissionRequestResponse:
    """Approve an admission request. Creates an admission student with INACTIVE status. Requires admissions.update permission."""
    try:
        return await service.approve_admission_request(
            db,
            current_user.tenant_id,
            request_id,
            payload,
            approved_by_user_id=current_user.id,
            approved_by_role=current_user.role,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/requests/{request_id}/reject",
    response_model=AdmissionRequestResponse,
    dependencies=[Depends(check_permission("admissions", "update"))],
)
async def reject_admission_request(
    request_id: UUID,
    payload: AdmissionRequestReject,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AdmissionRequestResponse:
    """Reject an admission request. Requires admissions.update permission."""
    try:
        return await service.reject_admission_request(
            db,
            current_user.tenant_id,
            request_id,
            payload,
            rejected_by_user_id=current_user.id,
            rejected_by_role=current_user.role,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Admission students (created on approval; activate = create User + profile + academic record) -----

@router.get(
    "/students",
    response_model=List[AdmissionStudentResponse],
    dependencies=[Depends(check_permission("students", "read"))],
)
async def list_admission_students(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: INACTIVE, ACTIVE"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[AdmissionStudentResponse]:
    """List admission students (approved requests). Use status=INACTIVE for approval queue / activation list."""
    return await service.list_admission_students(
        db,
        current_user.tenant_id,
        status_filter=status_filter,
    )


@router.post(
    "/students/{student_id}/activate",
    response_model=AdmissionStudentResponse,
    dependencies=[Depends(check_permission("students", "update"))],
)
async def activate_student(
    student_id: UUID,
    payload: AdmissionStudentActivate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AdmissionStudentResponse:
    """Activate an admission student: create auth user + student profile + academic record. Requires students.update permission."""
    try:
        return await service.activate_admission_student(
            db,
            current_user.tenant_id,
            student_id,
            password=payload.password,
            joined_date=payload.joined_date,
            activated_by_user_id=current_user.id,
            activated_by_role=current_user.role,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
