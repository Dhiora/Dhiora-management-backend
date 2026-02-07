from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_writable_academic_year
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import ClassSubjectCreate, ClassSubjectResponse, ClassSubjectBulkCreate
from . import service

router = APIRouter(prefix="/api/v1/class-subjects", tags=["class-subjects"])


@router.post(
    "",
    response_model=ClassSubjectResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("attendance", "create")), Depends(require_writable_academic_year)],
)
async def create_class_subject(
    payload: ClassSubjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return await service.create_class_subject(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/bulk",
    response_model=List[ClassSubjectResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("attendance", "create")), Depends(require_writable_academic_year)],
)
async def create_class_subjects_bulk(
    payload: ClassSubjectBulkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return await service.create_class_subjects_bulk(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "",
    response_model=List[ClassSubjectResponse],
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def list_class_subjects(
    academic_year_id: UUID,
    class_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await service.list_class_subjects(
        db, current_user.tenant_id, academic_year_id, class_id=class_id
    )


@router.delete(
    "/{class_subject_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("attendance", "delete")), Depends(require_writable_academic_year)],
)
async def delete_class_subject(
    class_subject_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    deleted = await service.delete_class_subject(db, current_user.tenant_id, class_subject_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class-subject assignment not found")
