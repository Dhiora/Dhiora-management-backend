from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import LeaveApply, LeaveApproveReject, LeaveRequestResponse, LeaveTypeCreate, LeaveTypeResponse, LeaveTypeUpdate
from . import service

router = APIRouter(prefix="/api/v1/leaves", tags=["leaves"])


@router.get(
    "/types",
    response_model=List[LeaveTypeResponse],
    dependencies=[Depends(check_permission("leave", "read"))],
)
async def list_leave_types(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[LeaveTypeResponse]:
    """List leave types for the tenant (for apply form dropdown). Teachers and employees use this when applying leave."""
    return await service.list_leave_types(db, current_user.tenant_id, active_only=active_only)


@router.post(
    "/types",
    response_model=LeaveTypeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("leave", "manage_types"))],
)
async def create_leave_type(
    payload: LeaveTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> LeaveTypeResponse:
    """Create a leave type for the current tenant. Super Admin only (or users with leave.manage_types). Each tenant has its own leave types."""
    try:
        return await service.create_leave_type(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put(
    "/types/{type_id}",
    response_model=LeaveTypeResponse,
    dependencies=[Depends(check_permission("leave", "manage_types"))],
)
async def update_leave_type(
    type_id: UUID,
    payload: LeaveTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> LeaveTypeResponse:
    """Update a leave type (name, code, is_active). Super Admin only (or users with leave.manage_types)."""
    try:
        return await service.update_leave_type(db, current_user.tenant_id, type_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


def _applicant_type(user_type: Optional[str]) -> str:
    if user_type == "student":
        return "STUDENT"
    return "EMPLOYEE"


@router.post(
    "/apply",
    response_model=LeaveRequestResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("leave", "create"))],
)
async def apply_leave(
    payload: LeaveApply,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> LeaveRequestResponse:
    """Apply for leave. Applicant type and approver are determined from current user and tenant."""
    user = await db.get(User, current_user.id)
    user_type = getattr(user, "user_type", None) if user else None
    applicant_type = _applicant_type(user_type)
    try:
        return await service.apply_leave(
            db,
            current_user.tenant_id,
            current_user.id,
            current_user.role,
            applicant_type,
            payload,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/my",
    response_model=List[LeaveRequestResponse],
    dependencies=[Depends(check_permission("leave", "read"))],
)
async def list_my_leaves(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[LeaveRequestResponse]:
    """List leave requests applied by the current user."""
    user = await db.get(User, current_user.id)
    user_type = getattr(user, "user_type", None) if user else None
    applicant_type = _applicant_type(user_type)
    return await service.list_my_leaves(db, current_user.tenant_id, current_user.id, applicant_type)


@router.get(
    "/pending",
    response_model=List[LeaveRequestResponse],
    dependencies=[Depends(check_permission("leave", "update"))],
)
async def list_pending_leaves(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[LeaveRequestResponse]:
    """List leave requests assigned to the current user (pending approval)."""
    return await service.list_pending_leaves(db, current_user.tenant_id, current_user.id)


@router.get(
    "",
    response_model=List[LeaveRequestResponse],
    dependencies=[Depends(check_permission("leave", "read"))],
)
async def list_all_leaves(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[LeaveRequestResponse]:
    """List all leave requests in the tenant. Requires leave.view_all or same as pending for approvers."""
    # If they have view_all permission (stored as key "view_all" under "leave"), return all; else return pending only
    has_view_all = (current_user.permissions or {}).get("leave", {}).get("view_all", False)
    if has_view_all or current_user.role in ("SUPER_ADMIN", "PLATFORM_ADMIN"):
        return await service.list_all_leaves(db, current_user.tenant_id)
    # Else return only pending assigned to them (same as /pending)
    return await service.list_pending_leaves(db, current_user.tenant_id, current_user.id)


@router.post(
    "/{leave_id}/approve",
    response_model=LeaveRequestResponse,
    dependencies=[Depends(check_permission("leave", "update"))],
)
async def approve_leave(
    leave_id: UUID,
    payload: LeaveApproveReject,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> LeaveRequestResponse:
    """Approve a leave request. Only assigned approver or Super Admin."""
    try:
        return await service.approve_leave(
            db,
            current_user.tenant_id,
            leave_id,
            current_user.id,
            current_user.role,
            remarks=payload.remarks,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/{leave_id}/reject",
    response_model=LeaveRequestResponse,
    dependencies=[Depends(check_permission("leave", "update"))],
)
async def reject_leave(
    leave_id: UUID,
    payload: LeaveApproveReject,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> LeaveRequestResponse:
    """Reject a leave request. Only assigned approver or Super Admin."""
    try:
        return await service.reject_leave(
            db,
            current_user.tenant_id,
            leave_id,
            current_user.id,
            current_user.role,
            remarks=payload.remarks,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
