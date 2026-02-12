"""Class Teacher Assignment API. One teacher per class-section per academic year.
RBAC: ADMIN full access; TEACHER read-only (own assignment)."""

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
    ClassTeacherAssignmentCreate,
    ClassTeacherAssignmentResponse,
    ClassTeacherAssignmentUpdate,
)
from . import service

router = APIRouter(prefix="/api/v1/class-teachers", tags=["class-teachers"])


def _is_admin(role: str) -> bool:
    return role in ("SUPER_ADMIN", "PLATFORM_ADMIN", "ADMIN")


async def require_class_teacher_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Only administrators can create/update/delete class teacher assignments."""
    if not _is_admin(current_user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can assign class teachers.",
        )


@router.post(
    "",
    response_model=ClassTeacherAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("attendance", "create")), Depends(require_class_teacher_admin)],
)
async def create_class_teacher_assignment(
    payload: ClassTeacherAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return await service.create_class_teacher_assignment(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "",
    response_model=List[ClassTeacherAssignmentResponse],
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def list_class_teacher_assignments(
    academic_year_id: Optional[UUID] = Query(None, description="Filter by academic year"),
    teacher_id: Optional[UUID] = Query(None, description="Filter by teacher"),
    class_id: Optional[UUID] = Query(None, description="Filter by class"),
    section_id: Optional[UUID] = Query(None, description="Filter by section"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    teacher_only_own = not _is_admin(current_user.role)
    return await service.list_class_teacher_assignments(
        db,
        current_user.tenant_id,
        academic_year_id=academic_year_id,
        teacher_id=teacher_id,
        class_id=class_id,
        section_id=section_id,
        teacher_only_see_own=teacher_only_own,
        current_user_id=current_user.id if teacher_only_own else None,
    )


@router.get(
    "/{assignment_id}",
    response_model=ClassTeacherAssignmentResponse,
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def get_class_teacher_assignment(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    teacher_only_own = not _is_admin(current_user.role)
    obj = await service.get_class_teacher_assignment(
        db,
        current_user.tenant_id,
        assignment_id,
        teacher_only_see_own=teacher_only_own,
        current_user_id=current_user.id if teacher_only_own else None,
    )
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return obj


@router.put(
    "/{assignment_id}",
    response_model=ClassTeacherAssignmentResponse,
    dependencies=[Depends(check_permission("attendance", "update")), Depends(require_class_teacher_admin)],
)
async def update_class_teacher_assignment(
    assignment_id: UUID,
    payload: ClassTeacherAssignmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        obj = await service.update_class_teacher_assignment(
            db, current_user.tenant_id, assignment_id, payload
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return obj


@router.delete(
    "/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("attendance", "delete")), Depends(require_class_teacher_admin)],
)
async def delete_class_teacher_assignment(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    deleted = await service.delete_class_teacher_assignment(db, current_user.tenant_id, assignment_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
