"""Attendance API router."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_writable_academic_year
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from . import service
from .schemas import (
    TeacherClassAssignmentCreate,
    EmployeeAttendanceBulkMark,
    EmployeeAttendanceDaySummary,
    EmployeeAttendanceMark,
    EmployeeAttendanceRecord,
    MonthlyAttendanceSummary,
    StudentAttendanceBulkMark,
    StudentAttendanceDaySummary,
    StudentAttendanceRecord,
)

router = APIRouter(prefix="/api/v1/attendance", tags=["attendance"])


# ----- Student Attendance -----
@router.post(
    "/students/mark",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("attendance", "create")), Depends(require_writable_academic_year)],
)
async def mark_student_attendance(
    payload: StudentAttendanceBulkMark,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Mark student attendance. Admin: any; Teacher: assigned classes only."""
    try:
        count = await service.mark_student_attendance_bulk(
            db,
            current_user.tenant_id,
            current_user.id,
            current_user.role,
            payload,
        )
        return {"marked": count, "message": f"Attendance marked for {count} students"}
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/students/day",
    response_model=StudentAttendanceDaySummary,
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def get_student_attendance_day(
    academic_year_id: UUID,
    att_date: date = Query(..., alias="date", description="Attendance date"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Day-wise student attendance. Admin: all; Teacher: assigned classes only."""
    try:
        return await service.get_student_attendance_day(
            db,
            current_user.tenant_id,
            current_user.id,
            current_user.role,
            academic_year_id,
            att_date,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/students/monthly/{student_id}",
    response_model=MonthlyAttendanceSummary,
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def get_student_monthly_attendance(
    student_id: UUID,
    academic_year_id: UUID,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Monthly attendance for a student."""
    try:
        return await service.get_student_monthly_attendance(
            db,
            current_user.tenant_id,
            current_user.id,
            current_user.role,
            student_id,
            academic_year_id,
            year,
            month,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Employee Attendance -----
@router.post(
    "/employees/mark",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("attendance", "create")), Depends(require_writable_academic_year)],
)
async def mark_employee_attendance(
    payload: EmployeeAttendanceBulkMark,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Mark employee attendance. Admin: any; Teacher/Staff: self only."""
    try:
        count = await service.mark_employee_attendance_bulk(
            db,
            current_user.tenant_id,
            current_user.id,
            current_user.role,
            payload,
        )
        return {"marked": count, "message": f"Attendance marked for {count} employees"}
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/employees/day",
    response_model=EmployeeAttendanceDaySummary,
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def get_employee_attendance_day(
    att_date: date = Query(..., alias="date", description="Attendance date"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Day-wise employee attendance. Admin: all; Teacher/Staff: own only."""
    try:
        return await service.get_employee_attendance_day(
            db,
            current_user.tenant_id,
            current_user.id,
            current_user.role,
            att_date,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/employees/monthly/{employee_id}",
    response_model=MonthlyAttendanceSummary,
    dependencies=[Depends(check_permission("attendance", "read"))],
)
async def get_employee_monthly_attendance(
    employee_id: UUID,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Monthly attendance for an employee. Admin: any; Teacher/Staff: own only."""
    try:
        return await service.get_employee_monthly_attendance(
            db,
            current_user.tenant_id,
            current_user.id,
            current_user.role,
            employee_id,
            year,
            month,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/teacher-assignments",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("attendance", "create")), Depends(require_writable_academic_year)],
)
async def create_teacher_assignment(
    payload: TeacherClassAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Assign teacher to class-section for academic year. Required for teachers to mark student attendance."""
    try:
        tca = await service.create_teacher_class_assignment(db, current_user.tenant_id, payload)
        return {"id": str(tca.id), "message": "Teacher assigned to class-section"}
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
