from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import SubjectCreate, SubjectDropdownItem, SubjectResponse, SubjectUpdate
from . import service

router = APIRouter(prefix="/api/v1/subjects", tags=["subjects"])


@router.post(
    "",
    response_model=SubjectResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("attendance", "create"))],
)
async def create_subject(
    payload: SubjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a subject for the tenant (used for subject-wise attendance overrides)."""
    try:
        return await service.create_subject(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "",
    response_model=List[SubjectResponse],
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def list_subjects(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await service.list_subjects(db, current_user.tenant_id, active_only=active_only)


@router.get(
    "/dropdown",
    response_model=List[SubjectDropdownItem],
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def subject_dropdown(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await service.get_subject_dropdown(db, current_user.tenant_id)


@router.get(
    "/{subject_id}",
    response_model=SubjectResponse,
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def get_subject(
    subject_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    obj = await service.get_subject(db, current_user.tenant_id, subject_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    return obj


@router.put(
    "/{subject_id}",
    response_model=SubjectResponse,
    dependencies=[Depends(check_permission("attendance", "update"))],
)
async def update_subject(
    subject_id: UUID,
    payload: SubjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        obj = await service.update_subject(db, current_user.tenant_id, subject_id, payload)
        if not obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
        return obj
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
