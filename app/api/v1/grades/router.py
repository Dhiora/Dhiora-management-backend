"""Grades and Report Cards API.

Access rules:
- SUPER_ADMIN / ADMIN / SCHOOL_ADMIN : full read + write
- TEACHER                            : enter marks for assigned subjects; read own class
- STUDENT                            : read own grades / report card only
- PARENT                             : via /api/v1/parent/ endpoints only
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from . import service
from .schemas import (
    BulkMarksRequest,
    BulkMarksResult,
    ExamGradeSummary,
    ExamMarksResponse,
    GradeScaleCreate,
    GradeScaleItem,
    GradeScaleUpdate,
    MarkUpdateRequest,
    ReportCard,
    SubjectMarkItem,
)

router = APIRouter(prefix="/api/v1/grades", tags=["grades"])

_ALLOWED_ROLES = {"SUPER_ADMIN", "ADMIN", "SCHOOL_ADMIN", "TEACHER", "STUDENT"}


def _require_access(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role not in _ALLOWED_ROLES:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, detail="Access denied")
    return current_user


def _require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role not in {"SUPER_ADMIN", "ADMIN", "SCHOOL_ADMIN"}:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def _require_write(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role not in {"SUPER_ADMIN", "ADMIN", "SCHOOL_ADMIN", "TEACHER"}:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, detail="Teachers and admins only")
    return current_user


def _raise(e: ServiceError) -> None:
    raise HTTPException(status_code=e.status_code, detail=e.message)


# ─── Grade Scales ─────────────────────────────────────────────────────────────

@router.get(
    "/scales",
    response_model=List[GradeScaleItem],
    summary="List grade scales for the tenant (falls back to built-in defaults if none configured)",
)
async def list_scales(
    current_user: CurrentUser = Depends(_require_access),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_grade_scales(db, current_user.tenant_id)


@router.post(
    "/scales",
    response_model=GradeScaleItem,
    status_code=http_status.HTTP_201_CREATED,
    summary="Create a grade scale entry (admin only)",
)
async def create_scale(
    payload: GradeScaleCreate,
    current_user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.create_grade_scale(db, current_user.tenant_id, payload)
    except ServiceError as e:
        _raise(e)


@router.put(
    "/scales/{scale_id}",
    response_model=GradeScaleItem,
    summary="Update a grade scale entry (admin only)",
)
async def update_scale(
    scale_id: UUID = Path(...),
    payload: GradeScaleUpdate = ...,
    current_user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.update_grade_scale(db, current_user.tenant_id, scale_id, payload)
    except ServiceError as e:
        _raise(e)


@router.delete(
    "/scales/{scale_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete a grade scale entry (admin only)",
)
async def delete_scale(
    scale_id: UUID = Path(...),
    current_user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.delete_grade_scale(db, current_user.tenant_id, scale_id)
    except ServiceError as e:
        _raise(e)


# ─── Marks Entry ─────────────────────────────────────────────────────────────

@router.get(
    "/exams/{exam_id}/marks",
    response_model=ExamMarksResponse,
    summary="Get marks for an exam. Admin/Teacher: all students. Student: self only.",
)
async def get_exam_marks(
    exam_id: UUID = Path(...),
    subject_id: Optional[UUID] = Query(None, description="Filter by subject"),
    current_user: CurrentUser = Depends(_require_access),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.get_exam_marks(db, current_user.tenant_id, exam_id, current_user, subject_id)
    except ServiceError as e:
        _raise(e)


@router.post(
    "/exams/{exam_id}/marks/bulk",
    response_model=BulkMarksResult,
    summary="Bulk enter or update marks for an exam. Teacher: assigned subjects only.",
)
async def bulk_enter_marks(
    exam_id: UUID = Path(...),
    payload: BulkMarksRequest = ...,
    current_user: CurrentUser = Depends(_require_write),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.bulk_enter_marks(db, current_user.tenant_id, exam_id, payload, current_user)
    except ServiceError as e:
        _raise(e)


@router.put(
    "/marks/{mark_id}",
    response_model=SubjectMarkItem,
    summary="Update a single mark record. Teacher: assigned subjects only.",
)
async def update_mark(
    mark_id: UUID = Path(...),
    payload: MarkUpdateRequest = ...,
    current_user: CurrentUser = Depends(_require_write),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.update_mark(db, current_user.tenant_id, mark_id, payload, current_user)
    except ServiceError as e:
        _raise(e)


@router.delete(
    "/marks/{mark_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete a mark record (admin only)",
)
async def delete_mark(
    mark_id: UUID = Path(...),
    current_user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.delete_mark(db, current_user.tenant_id, mark_id, current_user)
    except ServiceError as e:
        _raise(e)


# ─── Report Cards & Grade Lists ───────────────────────────────────────────────

@router.get(
    "/students/{student_id}/exams",
    response_model=List[ExamGradeSummary],
    summary="List all exams with grade summary for a student. Student: self only.",
)
async def get_student_exam_list(
    student_id: UUID = Path(...),
    current_user: CurrentUser = Depends(_require_access),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.get_student_exam_list(db, current_user.tenant_id, student_id, current_user)
    except ServiceError as e:
        _raise(e)


@router.get(
    "/students/{student_id}/report-card/{exam_id}",
    response_model=ReportCard,
    summary="Full report card for a student for an exam. Student: self only.",
)
async def get_report_card(
    student_id: UUID = Path(...),
    exam_id: UUID = Path(...),
    current_user: CurrentUser = Depends(_require_access),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.get_report_card(db, current_user.tenant_id, student_id, exam_id, current_user)
    except ServiceError as e:
        _raise(e)


@router.get(
    "/exams/{exam_id}/class-report",
    response_model=ExamMarksResponse,
    summary="Full class-wide marks report for an exam (admin/teacher only)",
)
async def get_class_report(
    exam_id: UUID = Path(...),
    current_user: CurrentUser = Depends(_require_write),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.get_class_report(db, current_user.tenant_id, exam_id, current_user)
    except ServiceError as e:
        _raise(e)
