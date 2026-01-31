"""Attendance service with role-based permission checks."""

from datetime import date, datetime
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import ServiceError
from app.core.models import (
    AcademicYear,
    EmployeeAttendance,
    SchoolClass,
    Section,
    StudentAcademicRecord,
    StudentAttendance,
    TeacherClassAssignment,
)

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


# ----- Permission helpers -----
def _is_admin(user_role: str) -> bool:
    return user_role in ("SUPER_ADMIN", "PLATFORM_ADMIN", "ADMIN")


def _can_mark_student_attendance_any(user_role: str) -> bool:
    return _is_admin(user_role)


def _can_mark_employee_attendance_any(user_role: str) -> bool:
    return _is_admin(user_role)


async def _teacher_can_mark_for_student(
    db: AsyncSession,
    teacher_id: UUID,
    student_id: UUID,
    academic_year_id: UUID,
) -> bool:
    """True if teacher is assigned to the student's class-section."""
    stmt = (
        select(TeacherClassAssignment.id)
        .join(StudentAcademicRecord, (
            StudentAcademicRecord.class_id == TeacherClassAssignment.class_id
            and StudentAcademicRecord.section_id == TeacherClassAssignment.section_id
            and StudentAcademicRecord.academic_year_id == TeacherClassAssignment.academic_year_id
        ))
        .where(
            TeacherClassAssignment.teacher_id == teacher_id,
            TeacherClassAssignment.academic_year_id == academic_year_id,
            StudentAcademicRecord.student_id == student_id,
            StudentAcademicRecord.academic_year_id == academic_year_id,
            StudentAcademicRecord.status == "ACTIVE",
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _validate_academic_year_for_attendance(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    att_date: date,
) -> AcademicYear:
    """Validate academic year is ACTIVE and date is in range."""
    result = await db.execute(
        select(AcademicYear).where(
            AcademicYear.id == academic_year_id,
            AcademicYear.tenant_id == tenant_id,
        )
    )
    ay = result.scalar_one_or_none()
    if not ay:
        raise ServiceError("Academic year not found", status.HTTP_404_NOT_FOUND)
    if ay.status == "CLOSED":
        raise ServiceError("Cannot mark attendance for a CLOSED academic year", status.HTTP_400_BAD_REQUEST)
    if att_date < ay.start_date or att_date > ay.end_date:
        raise ServiceError(
            f"Date {att_date} is outside academic year range ({ay.start_date} to {ay.end_date})",
            status.HTTP_400_BAD_REQUEST,
        )
    return ay


# ----- Student Attendance -----
async def mark_student_attendance_bulk(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    payload: StudentAttendanceBulkMark,
) -> int:
    """Mark student attendance. Admin: any; Teacher: assigned classes only."""
    if payload.date > date.today():
        raise ServiceError("Cannot mark attendance for future dates", status.HTTP_400_BAD_REQUEST)
    await _validate_academic_year_for_attendance(db, tenant_id, payload.academic_year_id, payload.date)
    count = 0
    for rec in payload.records:
        if rec.status not in ("PRESENT", "ABSENT", "LATE", "HALF_DAY"):
            raise ServiceError(f"Invalid status: {rec.status}", status.HTTP_400_BAD_REQUEST)
        if _can_mark_student_attendance_any(user_role):
            pass
        elif user_role == "TEACHER":
            if not await _teacher_can_mark_for_student(db, user_id, rec.student_id, payload.academic_year_id):
                raise ServiceError(
                    f"You can only mark attendance for students in your assigned classes",
                    status.HTTP_403_FORBIDDEN,
                )
        else:
            raise ServiceError("Insufficient permissions to mark student attendance", status.HTTP_403_FORBIDDEN)
        existing = await db.execute(
            select(StudentAttendance).where(
                StudentAttendance.student_id == rec.student_id,
                StudentAttendance.academic_year_id == payload.academic_year_id,
                StudentAttendance.date == payload.date,
            )
        )
        if existing.scalar_one_or_none():
            raise ServiceError(
                f"Attendance already marked for student {rec.student_id} on {payload.date}",
                status.HTTP_409_CONFLICT,
            )
        sa = StudentAttendance(
            student_id=rec.student_id,
            academic_year_id=payload.academic_year_id,
            date=payload.date,
            status=rec.status,
            marked_by=user_id,
        )
        db.add(sa)
        count += 1
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Duplicate attendance or invalid student", status.HTTP_409_CONFLICT)
    return count


async def get_student_attendance_day(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    academic_year_id: UUID,
    att_date: date,
) -> StudentAttendanceDaySummary:
    """Admin: full day view. Teacher: only assigned classes."""
    base_stmt = (
        select(StudentAttendance)
        .join(User, StudentAttendance.student_id == User.id)
        .where(
            User.tenant_id == tenant_id,
            StudentAttendance.academic_year_id == academic_year_id,
            StudentAttendance.date == att_date,
        )
    )
    if not _can_mark_student_attendance_any(user_role) and user_role == "TEACHER":
        base_stmt = (
            base_stmt
            .join(StudentAcademicRecord, (
                StudentAcademicRecord.student_id == StudentAttendance.student_id
                and StudentAcademicRecord.academic_year_id == StudentAttendance.academic_year_id
                and StudentAcademicRecord.status == "ACTIVE"
            ))
            .join(TeacherClassAssignment, (
                TeacherClassAssignment.class_id == StudentAcademicRecord.class_id
                and TeacherClassAssignment.section_id == StudentAcademicRecord.section_id
                and TeacherClassAssignment.academic_year_id == StudentAcademicRecord.academic_year_id
                and TeacherClassAssignment.teacher_id == user_id
            ))
        )
    result = await db.execute(base_stmt)
    attendance_list = result.scalars().unique().all()
    records = []
    counts = {"PRESENT": 0, "ABSENT": 0, "LATE": 0, "HALF_DAY": 0}
    for sa in attendance_list:
        counts[sa.status] = counts.get(sa.status, 0) + 1
        student = await db.get(User, sa.student_id)
        marker = await db.get(User, sa.marked_by)
        sar = (await db.execute(
            select(StudentAcademicRecord).where(
                StudentAcademicRecord.student_id == sa.student_id,
                StudentAcademicRecord.academic_year_id == sa.academic_year_id,
                StudentAcademicRecord.status == "ACTIVE",
            )
        )).scalar_one_or_none()
        class_name = ""
        section_name = ""
        class_id = UUID("00000000-0000-0000-0000-000000000000")
        section_id = UUID("00000000-0000-0000-0000-000000000000")
        roll_number = None
        if sar:
            class_id = sar.class_id
            section_id = sar.section_id
            roll_number = sar.roll_number
            sc = await db.get(SchoolClass, sar.class_id)
            sec = await db.get(Section, sar.section_id)
            class_name = sc.name if sc else ""
            section_name = sec.name if sec else ""
        records.append(StudentAttendanceRecord(
            id=sa.id,
            student_id=sa.student_id,
            student_name=student.full_name if student else "",
            roll_number=roll_number,
            class_id=class_id,
            class_name=class_name,
            section_id=section_id,
            section_name=section_name,
            date=sa.date,
            status=sa.status,
            marked_by=sa.marked_by,
            marked_by_name=marker.full_name if marker else None,
            created_at=sa.created_at,
        ))
    return StudentAttendanceDaySummary(
        total_present=counts.get("PRESENT", 0),
        total_absent=counts.get("ABSENT", 0),
        total_late=counts.get("LATE", 0),
        total_half_day=counts.get("HALF_DAY", 0),
        records=records,
    )


# ----- Employee Attendance -----
async def mark_employee_attendance_bulk(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    payload: EmployeeAttendanceBulkMark,
) -> int:
    """Mark employee attendance. Admin: any; Teacher/Staff: self only."""
    if payload.date > date.today():
        raise ServiceError("Cannot mark attendance for future dates", status.HTTP_400_BAD_REQUEST)
    count = 0
    for rec in payload.records:
        if rec.status not in ("PRESENT", "ABSENT", "LATE", "HALF_DAY", "LEAVE"):
            raise ServiceError(f"Invalid status: {rec.status}", status.HTTP_400_BAD_REQUEST)
        if not _can_mark_employee_attendance_any(user_role):
            if rec.employee_id != user_id:
                raise ServiceError("You can only mark your own attendance", status.HTTP_403_FORBIDDEN)
        emp = await db.get(User, rec.employee_id)
        if not emp or emp.tenant_id != tenant_id or emp.user_type != "employee":
            raise ServiceError(f"Invalid employee: {rec.employee_id}", status.HTTP_400_BAD_REQUEST)
        existing = await db.execute(
            select(EmployeeAttendance).where(
                EmployeeAttendance.employee_id == rec.employee_id,
                EmployeeAttendance.date == payload.date,
            )
        )
        if existing.scalar_one_or_none():
            raise ServiceError(
                f"Attendance already marked for employee {rec.employee_id} on {payload.date}",
                status.HTTP_409_CONFLICT,
            )
        ea = EmployeeAttendance(
            employee_id=rec.employee_id,
            date=payload.date,
            status=rec.status,
            marked_by=user_id,
        )
        db.add(ea)
        count += 1
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Duplicate attendance or invalid employee", status.HTTP_409_CONFLICT)
    return count


async def get_employee_attendance_day(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    att_date: date,
) -> EmployeeAttendanceDaySummary:
    """Admin: full day view. Teacher/Staff: own only."""
    stmt = (
        select(EmployeeAttendance)
        .join(User, EmployeeAttendance.employee_id == User.id)
        .where(User.tenant_id == tenant_id, EmployeeAttendance.date == att_date)
    )
    if not _can_mark_employee_attendance_any(user_role):
        stmt = stmt.where(EmployeeAttendance.employee_id == user_id)
    result = await db.execute(stmt)
    attendance_list = result.scalars().unique().all()
    records = []
    counts = {"PRESENT": 0, "ABSENT": 0, "LATE": 0, "HALF_DAY": 0, "LEAVE": 0}
    for ea in attendance_list:
        counts[ea.status] = counts.get(ea.status, 0) + 1
        emp = await db.get(User, ea.employee_id)
        marker = await db.get(User, ea.marked_by)
        records.append(EmployeeAttendanceRecord(
            id=ea.id,
            employee_id=ea.employee_id,
            employee_name=emp.full_name if emp else "",
            role=emp.role if emp else "",
            date=ea.date,
            status=ea.status,
            marked_by=ea.marked_by,
            marked_by_name=marker.full_name if marker else None,
            created_at=ea.created_at,
        ))
    return EmployeeAttendanceDaySummary(
        total_present=counts.get("PRESENT", 0),
        total_absent=counts.get("ABSENT", 0),
        total_late=counts.get("LATE", 0),
        total_half_day=counts.get("HALF_DAY", 0),
        total_leave=counts.get("LEAVE", 0),
        records=records,
    )


# ----- Monthly reports -----
async def get_student_monthly_attendance(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    student_id: UUID,
    academic_year_id: UUID,
    year: int,
    month: int,
) -> MonthlyAttendanceSummary:
    """Admin: any student. Teacher: only assigned. Student: own only (permission-based)."""
    if not _can_mark_student_attendance_any(user_role):
        if user_role == "TEACHER":
            if not await _teacher_can_mark_for_student(db, user_id, student_id, academic_year_id):
                raise ServiceError("Cannot view this student's attendance", status.HTTP_403_FORBIDDEN)
        elif user_id != student_id:
            raise ServiceError("Cannot view other students' attendance", status.HTTP_403_FORBIDDEN)
    from calendar import monthrange
    start_dt = date(year, month, 1)
    end_dt = date(year, month, monthrange(year, month)[1])
    stmt = select(StudentAttendance.status, func.count(StudentAttendance.id)).where(
        StudentAttendance.student_id == student_id,
        StudentAttendance.academic_year_id == academic_year_id,
        StudentAttendance.date >= start_dt,
        StudentAttendance.date <= end_dt,
    ).group_by(StudentAttendance.status)
    result = await db.execute(stmt)
    rows = result.all()
    counts = {"PRESENT": 0, "ABSENT": 0, "LATE": 0, "HALF_DAY": 0}
    for status_val, cnt in rows:
        counts[status_val] = cnt
    total_days = (end_dt - start_dt).days + 1
    return MonthlyAttendanceSummary(
        present_days=counts.get("PRESENT", 0),
        absent_days=counts.get("ABSENT", 0),
        late_days=counts.get("LATE", 0),
        half_day_days=counts.get("HALF_DAY", 0),
        total_working_days=total_days,
    )


async def get_employee_monthly_attendance(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    employee_id: UUID,
    year: int,
    month: int,
) -> MonthlyAttendanceSummary:
    """Admin: any. Teacher/Staff: own only."""
    if not _can_mark_employee_attendance_any(user_role) and employee_id != user_id:
        raise ServiceError("You can only view your own attendance", status.HTTP_403_FORBIDDEN)
    from calendar import monthrange
    start_dt = date(year, month, 1)
    end_dt = date(year, month, monthrange(year, month)[1])
    stmt = select(EmployeeAttendance.status, func.count(EmployeeAttendance.id)).where(
        EmployeeAttendance.employee_id == employee_id,
        EmployeeAttendance.date >= start_dt,
        EmployeeAttendance.date <= end_dt,
    ).group_by(EmployeeAttendance.status)
    result = await db.execute(stmt)
    rows = result.all()
    counts = {"PRESENT": 0, "ABSENT": 0, "LATE": 0, "HALF_DAY": 0, "LEAVE": 0}
    for status_val, cnt in rows:
        counts[status_val] = cnt
    total_days = (end_dt - start_dt).days + 1
    return MonthlyAttendanceSummary(
        present_days=counts.get("PRESENT", 0),
        absent_days=counts.get("ABSENT", 0),
        late_days=counts.get("LATE", 0),
        half_day_days=counts.get("HALF_DAY", 0),
        leave_days=counts.get("LEAVE", 0),
        total_working_days=total_days,
    )


# ----- Teacher Class Assignments (Admin only) -----
async def create_teacher_class_assignment(
    db: AsyncSession,
    tenant_id: UUID,
    payload: TeacherClassAssignmentCreate,
) -> TeacherClassAssignment:
    """Assign teacher to class-section for academic year. Admin only."""
    teacher = await db.get(User, payload.teacher_id)
    if not teacher or teacher.tenant_id != tenant_id or teacher.user_type != "employee":
        raise ServiceError("Invalid teacher", status.HTTP_400_BAD_REQUEST)
    from app.api.v1.classes import service as class_service
    from app.api.v1.sections import service as section_service
    if not await class_service.get_class_by_id_for_tenant(db, tenant_id, payload.class_id, active_only=True):
        raise ServiceError("Invalid class", status.HTTP_400_BAD_REQUEST)
    section = await section_service.get_section_by_id_for_tenant(db, tenant_id, payload.section_id, active_only=True)
    if not section or section.class_id != payload.class_id:
        raise ServiceError("Section does not belong to class", status.HTTP_400_BAD_REQUEST)
    existing = await db.execute(
        select(TeacherClassAssignment).where(
            TeacherClassAssignment.teacher_id == payload.teacher_id,
            TeacherClassAssignment.class_id == payload.class_id,
            TeacherClassAssignment.section_id == payload.section_id,
            TeacherClassAssignment.academic_year_id == payload.academic_year_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ServiceError("Assignment already exists", status.HTTP_409_CONFLICT)
    tca = TeacherClassAssignment(
        teacher_id=payload.teacher_id,
        class_id=payload.class_id,
        section_id=payload.section_id,
        academic_year_id=payload.academic_year_id,
    )
    db.add(tca)
    await db.commit()
    await db.refresh(tca)
    return tca