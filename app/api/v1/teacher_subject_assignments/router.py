from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_writable_academic_year
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import TeacherSubjectAssignmentCreate, TeacherSubjectAssignmentResponse
from . import service

router = APIRouter(prefix="/api/v1/teacher-subject-assignments", tags=["teacher-subject-assignments"])


@router.post(
    "",
    response_model=TeacherSubjectAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("attendance", "create")), Depends(require_writable_academic_year)],
)
async def create_teacher_subject_assignment(
    payload: TeacherSubjectAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return await service.create_teacher_subject_assignment(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "",
    response_model=List[TeacherSubjectAssignmentResponse],
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def list_teacher_subject_assignments(
    academic_year_id: UUID,
    teacher_id: Optional[UUID] = Query(None),
    class_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await service.list_teacher_subject_assignments(
        db, current_user.tenant_id, academic_year_id, teacher_id=teacher_id, class_id=class_id
    )


@router.delete(
    "/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("attendance", "delete")), Depends(require_writable_academic_year)],
)
async def delete_teacher_subject_assignment(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    deleted = await service.delete_teacher_subject_assignment(db, current_user.tenant_id, assignment_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
