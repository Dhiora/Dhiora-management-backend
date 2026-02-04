"""Leave apply, my, pending, approve, reject with resolver and audit."""

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.core.models import LeaveRequest, LeaveType, Tenant
from app.core.models.leave_audit_log import LeaveAuditLog
from app.core.models.leave_request import (
    APPLICANT_TYPE_EMPLOYEE,
    APPLICANT_TYPE_STUDENT,
    LEAVE_STATUS_APPROVED,
    LEAVE_STATUS_PENDING,
    LEAVE_STATUS_REJECTED,
)

from .resolver import _normalize_tenant_type, resolve_leave_approver
from .schemas import LeaveApply, LeaveRequestResponse, LeaveTypeCreate, LeaveTypeResponse, LeaveTypeUpdate


def _to_uuid(val):
    if val is None:
        return None
    return val if isinstance(val, UUID) else UUID(str(val))


def _request_to_response(r: LeaveRequest) -> LeaveRequestResponse:
    return LeaveRequestResponse(
        id=r.id,
        tenant_id=r.tenant_id,
        tenant_type=r.tenant_type,
        applicant_type=r.applicant_type,
        employee_id=r.employee_id,
        student_id=r.student_id,
        leave_type_id=r.leave_type_id,
        custom_reason=r.custom_reason,
        from_date=r.from_date,
        to_date=r.to_date,
        total_days=r.total_days,
        status=r.status,
        assigned_to_user_id=r.assigned_to_user_id,
        approved_by_user_id=r.approved_by_user_id,
        approved_at=r.approved_at,
        created_by=r.created_by,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


async def _log_leave_audit(
    db: AsyncSession,
    leave_request_id: UUID,
    action: str,
    performed_by: UUID,
    performed_by_role: str,
    remarks: Optional[str] = None,
) -> None:
    entry = LeaveAuditLog(
        leave_request_id=leave_request_id,
        action=action,
        performed_by=performed_by,
        performed_by_role=performed_by_role,
        remarks=remarks,
    )
    db.add(entry)


async def _get_tenant_type(db: AsyncSession, tenant_id: UUID) -> str:
    t = await db.get(Tenant, tenant_id)
    if not t:
        return "SCHOOL"
    return _normalize_tenant_type(getattr(t, "organization_type", "") or "")


def _applicant_type_from_user(user_type: Optional[str]) -> str:
    if user_type == "student":
        return APPLICANT_TYPE_STUDENT
    return APPLICANT_TYPE_EMPLOYEE


async def apply_leave(
    db: AsyncSession,
    tenant_id: UUID,
    current_user_id: UUID,
    current_user_role: str,
    applicant_type: str,
    payload: LeaveApply,
) -> LeaveRequestResponse:
    """Apply for leave; resolve approver, validate dates and overlap."""
    if payload.to_date < payload.from_date:
        raise ServiceError("to_date must be on or after from_date", status.HTTP_400_BAD_REQUEST)
    if payload.total_days < 1:
        raise ServiceError("total_days must be at least 1", status.HTTP_400_BAD_REQUEST)
    if not payload.leave_type_id and not (payload.custom_reason and payload.custom_reason.strip()):
        raise ServiceError("Either leave_type_id or custom_reason is required", status.HTTP_400_BAD_REQUEST)

    # Overlapping leave check
    employee_id = current_user_id if applicant_type == APPLICANT_TYPE_EMPLOYEE else None
    student_id = current_user_id if applicant_type == APPLICANT_TYPE_STUDENT else None
    overlap = await db.execute(
        select(LeaveRequest.id).where(
            LeaveRequest.tenant_id == tenant_id,
            LeaveRequest.status == LEAVE_STATUS_PENDING,
            (LeaveRequest.employee_id == employee_id) if employee_id else (LeaveRequest.student_id == student_id),
            LeaveRequest.from_date <= payload.to_date,
            LeaveRequest.to_date >= payload.from_date,
        ).limit(1)
    )
    if overlap.scalar_one_or_none():
        raise ServiceError("Overlapping leave request exists for this period", status.HTTP_400_BAD_REQUEST)

    tenant_type = await _get_tenant_type(db, tenant_id)
    approver_id = await resolve_leave_approver(
        db, tenant_id, tenant_type, applicant_type,
        employee_id=employee_id,
        student_id=student_id,
    )
    if not approver_id:
        # Fallback: first user in tenant with leave_approve (handled by role) or same tenant admin
        from app.auth.models import User
        r = await db.execute(
            select(User.id).where(
                User.tenant_id == tenant_id,
                User.role.in_(["ADMIN", "SUPER_ADMIN", "PLATFORM_ADMIN"]),
                User.status == "ACTIVE",
            ).limit(1)
        )
        approver_id = r.scalar_one_or_none()
    if not approver_id:
        raise ServiceError("No approver could be assigned for this leave. Contact administrator.", status.HTTP_400_BAD_REQUEST)

    leave_type_id = payload.leave_type_id
    if leave_type_id:
        lt = await db.get(LeaveType, leave_type_id)
        if not lt or lt.tenant_id != tenant_id or not lt.is_active:
            raise ServiceError("Invalid or inactive leave type", status.HTTP_400_BAD_REQUEST)

    req = LeaveRequest(
        tenant_id=tenant_id,
        tenant_type=tenant_type,
        applicant_type=applicant_type,
        employee_id=employee_id,
        student_id=student_id,
        leave_type_id=leave_type_id,
        custom_reason=payload.custom_reason.strip() if payload.custom_reason else None,
        from_date=payload.from_date,
        to_date=payload.to_date,
        total_days=payload.total_days,
        status=LEAVE_STATUS_PENDING,
        assigned_to_user_id=approver_id,
        created_by=current_user_id,
    )
    db.add(req)
    await db.flush()
    await _log_leave_audit(db, req.id, "APPLIED", current_user_id, current_user_role)
    await db.commit()
    await db.refresh(req)
    return _request_to_response(req)


async def list_my_leaves(
    db: AsyncSession,
    tenant_id: UUID,
    current_user_id: UUID,
    applicant_type: str,
) -> List[LeaveRequestResponse]:
    """Leaves applied by the current user (as employee or student)."""
    q = select(LeaveRequest).where(LeaveRequest.tenant_id == tenant_id)
    if applicant_type == APPLICANT_TYPE_EMPLOYEE:
        q = q.where(LeaveRequest.employee_id == current_user_id)
    else:
        q = q.where(LeaveRequest.student_id == current_user_id)
    q = q.order_by(LeaveRequest.created_at.desc())
    result = await db.execute(q)
    rows = result.scalars().all()
    return [_request_to_response(r) for r in rows]


async def list_pending_leaves(
    db: AsyncSession,
    tenant_id: UUID,
    assigned_to_user_id: UUID,
) -> List[LeaveRequestResponse]:
    """Leaves pending for the current user (as approver)."""
    result = await db.execute(
        select(LeaveRequest)
        .where(
            LeaveRequest.tenant_id == tenant_id,
            LeaveRequest.assigned_to_user_id == assigned_to_user_id,
            LeaveRequest.status == LEAVE_STATUS_PENDING,
        )
        .order_by(LeaveRequest.created_at.desc())
    )
    rows = result.scalars().all()
    return [_request_to_response(r) for r in rows]


async def list_all_leaves(
    db: AsyncSession,
    tenant_id: UUID,
) -> List[LeaveRequestResponse]:
    """All leaves in tenant (LEAVE_VIEW_ALL)."""
    result = await db.execute(
        select(LeaveRequest)
        .where(LeaveRequest.tenant_id == tenant_id)
        .order_by(LeaveRequest.created_at.desc())
    )
    rows = result.scalars().all()
    return [_request_to_response(r) for r in rows]


async def list_leave_types(
    db: AsyncSession,
    tenant_id: UUID,
    active_only: bool = True,
) -> List[LeaveTypeResponse]:
    """List leave types for tenant (for apply form dropdown)."""
    q = select(LeaveType).where(LeaveType.tenant_id == tenant_id)
    if active_only:
        q = q.where(LeaveType.is_active.is_(True))
    q = q.order_by(LeaveType.name)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        LeaveTypeResponse(
            id=lt.id,
            tenant_id=lt.tenant_id,
            name=lt.name,
            code=lt.code,
            is_active=lt.is_active,
            created_at=lt.created_at,
        )
        for lt in rows
    ]


async def create_leave_type(
    db: AsyncSession,
    tenant_id: UUID,
    payload: LeaveTypeCreate,
) -> LeaveTypeResponse:
    """Create a leave type for the tenant. Code must be unique per tenant. Caller must be Super Admin or have leave.manage_types."""
    existing = (
        await db.execute(
            select(LeaveType).where(
                LeaveType.tenant_id == tenant_id,
                LeaveType.code == payload.code.strip(),
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise ServiceError(
            f"Leave type with code '{payload.code}' already exists for this tenant",
            status.HTTP_400_BAD_REQUEST,
        )
    code = payload.code.strip()
    name = payload.name.strip()
    lt = LeaveType(
        tenant_id=tenant_id,
        code=code,
        name=name,
        is_active=payload.is_active,
    )
    db.add(lt)
    await db.commit()
    await db.refresh(lt)
    return LeaveTypeResponse(
        id=lt.id,
        tenant_id=lt.tenant_id,
        name=lt.name,
        code=lt.code,
        is_active=lt.is_active,
        created_at=lt.created_at,
    )


async def update_leave_type(
    db: AsyncSession,
    tenant_id: UUID,
    type_id: UUID,
    payload: LeaveTypeUpdate,
) -> LeaveTypeResponse:
    """Update a leave type. Only for same tenant. Caller must be Super Admin or have leave.manage_types."""
    lt = await db.get(LeaveType, type_id)
    if not lt or lt.tenant_id != tenant_id:
        raise ServiceError("Leave type not found", status.HTTP_404_NOT_FOUND)
    if payload.name is not None:
        lt.name = payload.name.strip()
    if payload.code is not None:
        new_code = payload.code.strip()
        if new_code != lt.code:
            existing = (
                await db.execute(
                    select(LeaveType).where(
                        LeaveType.tenant_id == tenant_id,
                        LeaveType.code == new_code,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                raise ServiceError(
                    f"Leave type with code '{new_code}' already exists for this tenant",
                    status.HTTP_400_BAD_REQUEST,
                )
            lt.code = new_code
    if payload.is_active is not None:
        lt.is_active = payload.is_active
    await db.commit()
    await db.refresh(lt)
    return LeaveTypeResponse(
        id=lt.id,
        tenant_id=lt.tenant_id,
        name=lt.name,
        code=lt.code,
        is_active=lt.is_active,
        created_at=lt.created_at,
    )


async def get_leave_request(
    db: AsyncSession,
    tenant_id: UUID,
    leave_id: UUID,
) -> Optional[LeaveRequest]:
    return (await db.execute(
        select(LeaveRequest).where(
            LeaveRequest.id == leave_id,
            LeaveRequest.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()


async def approve_leave(
    db: AsyncSession,
    tenant_id: UUID,
    leave_id: UUID,
    approved_by_user_id: UUID,
    approved_by_role: str,
    remarks: Optional[str] = None,
) -> LeaveRequestResponse:
    req = await get_leave_request(db, tenant_id, leave_id)
    if not req:
        raise ServiceError("Leave request not found", status.HTTP_404_NOT_FOUND)
    if req.status != LEAVE_STATUS_PENDING:
        raise ServiceError("Only PENDING leave can be approved", status.HTTP_400_BAD_REQUEST)
    # Only assigned approver or Super Admin
    is_assigned = req.assigned_to_user_id == approved_by_user_id
    is_super_admin = approved_by_role in ("SUPER_ADMIN", "PLATFORM_ADMIN")
    if not is_assigned and not is_super_admin:
        raise ServiceError("Only the assigned approver or Super Admin can approve this leave", status.HTTP_403_FORBIDDEN)

    req.status = LEAVE_STATUS_APPROVED
    req.approved_by_user_id = approved_by_user_id
    req.approved_at = datetime.utcnow()
    await _log_leave_audit(db, req.id, "APPROVED", approved_by_user_id, approved_by_role, remarks=remarks)
    await db.commit()
    await db.refresh(req)
    return _request_to_response(req)


async def reject_leave(
    db: AsyncSession,
    tenant_id: UUID,
    leave_id: UUID,
    rejected_by_user_id: UUID,
    rejected_by_role: str,
    remarks: Optional[str] = None,
) -> LeaveRequestResponse:
    req = await get_leave_request(db, tenant_id, leave_id)
    if not req:
        raise ServiceError("Leave request not found", status.HTTP_404_NOT_FOUND)
    if req.status != LEAVE_STATUS_PENDING:
        raise ServiceError("Only PENDING leave can be rejected", status.HTTP_400_BAD_REQUEST)
    is_assigned = req.assigned_to_user_id == rejected_by_user_id
    is_super_admin = rejected_by_role in ("SUPER_ADMIN", "PLATFORM_ADMIN")
    if not is_assigned and not is_super_admin:
        raise ServiceError("Only the assigned approver or Super Admin can reject this leave", status.HTTP_403_FORBIDDEN)

    req.status = LEAVE_STATUS_REJECTED
    req.approved_by_user_id = rejected_by_user_id
    req.approved_at = datetime.utcnow()
    await _log_leave_audit(db, req.id, "REJECTED", rejected_by_user_id, rejected_by_role, remarks=remarks)
    await db.commit()
    await db.refresh(req)
    return _request_to_response(req)
