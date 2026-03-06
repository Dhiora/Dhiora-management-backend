"""Exam management API: exam types, exams, schedule, invigilator."""

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
    ExamCreate,
    ExamResponse,
    ExamScheduleCreate,
    ExamScheduleResponse,
    ExamTypeCreate,
    ExamTypeResponse,
    InvigilatorUpdate,
)
from . import service

router = APIRouter(prefix="/api/v1", tags=["exams"])


# ----- Exam Types -----
@router.get(
    "/exam-types",
    response_model=List[ExamTypeResponse],
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def list_exam_types(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[ExamTypeResponse]:
    return await service.list_exam_types(db, current_user.tenant_id)


@router.post(
    "/exam-types",
    response_model=ExamTypeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("attendance", "create"))],
)
async def create_exam_type(
    payload: ExamTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ExamTypeResponse:
    return await service.create_exam_type(db, current_user.tenant_id, payload)


# ----- Exams -----
@router.get(
    "/exams",
    response_model=List[ExamResponse],
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def list_exams(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    class_id: Optional[UUID] = Query(None, description="Filter by class ID"),
    section_id: Optional[UUID] = Query(None, description="Filter by section ID"),
    status_filter: Optional[str] = Query(None, description="Filter by status: draft, scheduled, completed"),
) -> List[ExamResponse]:
    return await service.list_exams(
        db,
        current_user.tenant_id,
        class_id=class_id,
        section_id=section_id,
        status_filter=status_filter,
    )


@router.post(
    "/exams",
    response_model=ExamResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("attendance", "create"))],
)
async def create_exam(
    payload: ExamCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ExamResponse:
    try:
        return await service.create_exam(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Exam Schedule -----
@router.get(
    "/exams/{exam_id}/schedule",
    response_model=List[ExamScheduleResponse],
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def get_exam_schedule(
    exam_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[ExamScheduleResponse]:
    try:
        return await service.get_exam_schedule(db, current_user.tenant_id, exam_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/exams/{exam_id}/schedule",
    response_model=ExamScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("attendance", "create"))],
)
async def add_exam_schedule(
    exam_id: UUID,
    payload: ExamScheduleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ExamScheduleResponse:
    try:
        return await service.add_exam_schedule(
            db, current_user.tenant_id, exam_id, payload
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Invigilator -----
@router.patch(
    "/exam-schedule/{schedule_id}/invigilator",
    response_model=ExamScheduleResponse,
    dependencies=[Depends(check_permission("attendance", "update"))],
)
async def update_invigilator(
    schedule_id: UUID,
    payload: InvigilatorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ExamScheduleResponse:
    try:
        return await service.update_invigilator(
            db, current_user.tenant_id, schedule_id, payload
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
