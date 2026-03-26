"""DashboardRepository – all raw async DB queries for dashboard endpoints.

Each method issues a single optimised query (aggregation / JOIN) and returns
plain Python values ready for the service layer.  No business logic here.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.models import (
    AcademicYear,
    DashboardAlert,
    Department,
    EmployeeAttendance,
    Exam,
    ExamSchedule,
    LeaveRequest,
    LessonPlanProgress,
    SchoolClass,
    Section,
    StudentAcademicRecord,
    StudentDailyAttendance,
    StudentDailyAttendanceRecord,
    StudentFeeAssignment,
    Timetable,
    TimeSlot,
)
from app.core.models.homework import Homework, HomeworkAssignment, HomeworkAttempt
from app.core.models.payment_transaction import PaymentTransaction
from app.core.models.school_subject import SchoolSubject


class DashboardRepository:
    """Stateless repository – pass db session per call."""

    # ------------------------------------------------------------------ #
    #  SUMMARY STATS                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def count_students(
        db: AsyncSession,
        tenant_id: UUID,
        since: Optional[date] = None,
    ) -> int:
        """Total active students, optionally filtered to those created since *since*."""
        q = select(func.count(User.id)).where(
            User.tenant_id == tenant_id,
            User.user_type == "student",
            User.status == "ACTIVE",
        )
        if since:
            q = q.where(
                User.created_at
                >= datetime.combine(since, datetime.min.time()).replace(tzinfo=timezone.utc)
            )
        return (await db.execute(q)).scalar() or 0

    @staticmethod
    async def count_teachers(db: AsyncSession, tenant_id: UUID) -> int:
        """Count active users whose job title / designation marks them as teachers.

        In the current model, teachers are employees with role 'EMPLOYEE' who have
        at least one teacher-class assignment.  As a fast proxy we count active
        employee users and let the service layer refine if required.
        """
        q = select(func.count(User.id)).where(
            User.tenant_id == tenant_id,
            User.user_type == "employee",
            User.status == "ACTIVE",
        )
        return (await db.execute(q)).scalar() or 0

    @staticmethod
    async def count_employees_on_leave(
        db: AsyncSession, tenant_id: UUID, on_date: date
    ) -> int:
        q = select(func.count(LeaveRequest.id)).where(
            LeaveRequest.tenant_id == tenant_id,
            LeaveRequest.applicant_type == "EMPLOYEE",
            LeaveRequest.status == "APPROVED",
            LeaveRequest.from_date <= on_date,
            LeaveRequest.to_date >= on_date,
        )
        return (await db.execute(q)).scalar() or 0

    @staticmethod
    async def count_departments(db: AsyncSession, tenant_id: UUID) -> int:
        q = select(func.count(Department.id)).where(
            Department.tenant_id == tenant_id,
            Department.is_active.is_(True),
        )
        return (await db.execute(q)).scalar() or 0

    @staticmethod
    async def count_classes(db: AsyncSession, tenant_id: UUID) -> Tuple[int, str]:
        """Return (total_active_classes, grade_range_label) e.g. (24, '1-12')."""
        from sqlalchemy import cast, Integer as SAInt, text

        q = select(func.count(SchoolClass.id)).where(
            SchoolClass.tenant_id == tenant_id,
            SchoolClass.is_active.is_(True),
        )
        total: int = (await db.execute(q)).scalar() or 0

        # Try to derive a numeric grade range from class names
        q_names = select(SchoolClass.name).where(
            SchoolClass.tenant_id == tenant_id,
            SchoolClass.is_active.is_(True),
        )
        res = await db.execute(q_names)
        names = [r[0] for r in res.all()]
        nums = []
        for n in names:
            for part in n.split():
                if part.isdigit():
                    nums.append(int(part))
        grade_range = f"{min(nums)}-{max(nums)}" if nums else "N/A"
        return total, grade_range

    @staticmethod
    async def count_sections(
        db: AsyncSession, tenant_id: UUID, academic_year_id: Optional[UUID]
    ) -> Tuple[int, float]:
        """Return (total_sections, avg_students_per_section)."""
        q_sec = select(func.count(Section.id)).where(Section.tenant_id == tenant_id)
        total_sections: int = (await db.execute(q_sec)).scalar() or 0

        avg = 0.0
        if academic_year_id and total_sections:
            # StudentAcademicRecord doesn't have tenant_id; scope via the student user.
            q_avg = (
                select(func.count(StudentAcademicRecord.id))
                .join(User, StudentAcademicRecord.student_id == User.id)
                .where(
                    User.tenant_id == tenant_id,
                    StudentAcademicRecord.academic_year_id == academic_year_id,
                    StudentAcademicRecord.status == "ACTIVE",
                )
            )
            total_students: int = (await db.execute(q_avg)).scalar() or 0
            avg = round(total_students / total_sections, 1)

        return total_sections, avg

    @staticmethod
    async def get_active_academic_year(
        db: AsyncSession, tenant_id: UUID
    ) -> Optional[AcademicYear]:
        q = (
            select(AcademicYear)
            .where(
                AcademicYear.tenant_id == tenant_id,
                AcademicYear.status == "ACTIVE",
            )
            .order_by(AcademicYear.end_date.desc())
            .limit(1)
        )
        return (await db.execute(q)).scalar_one_or_none()

    # ------------------------------------------------------------------ #
    #  ATTENDANCE                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def get_student_attendance_today(
        db: AsyncSession,
        tenant_id: UUID,
        academic_year_id: Optional[UUID],
        on_date: date,
    ) -> Tuple[int, int]:
        """Return (present, absent) student counts for today."""
        if not academic_year_id:
            return 0, 0

        # One query: JOIN masters → records, GROUP BY status
        q = (
            select(
                StudentDailyAttendanceRecord.status,
                func.count(StudentDailyAttendanceRecord.id).label("cnt"),
            )
            .join(
                StudentDailyAttendance,
                StudentDailyAttendanceRecord.daily_attendance_id == StudentDailyAttendance.id,
            )
            .where(
                StudentDailyAttendance.tenant_id == tenant_id,
                StudentDailyAttendance.academic_year_id == academic_year_id,
                StudentDailyAttendance.attendance_date == on_date,
            )
            .group_by(StudentDailyAttendanceRecord.status)
        )
        res = await db.execute(q)
        present = absent = 0
        for status_val, cnt in res.all():
            if status_val == "PRESENT":
                present += cnt
            else:
                absent += cnt
        return present, absent

    @staticmethod
    async def get_staff_attendance_today(
        db: AsyncSession, tenant_id: UUID, on_date: date
    ) -> Tuple[int, int]:
        """Return (present, absent) staff counts for today."""
        q = (
            select(
                EmployeeAttendance.status,
                func.count(EmployeeAttendance.id).label("cnt"),
            )
            .join(User, EmployeeAttendance.employee_id == User.id)
            .where(
                User.tenant_id == tenant_id,
                EmployeeAttendance.date == on_date,
            )
            .group_by(EmployeeAttendance.status)
        )
        res = await db.execute(q)
        present = absent = 0
        for status_val, cnt in res.all():
            if status_val == "PRESENT":
                present += cnt
            else:
                absent += cnt
        return present, absent

    @staticmethod
    async def count_missing_attendance_sections(
        db: AsyncSession,
        tenant_id: UUID,
        academic_year_id: Optional[UUID],
        on_date: date,
    ) -> int:
        """Sections that have active students but no attendance master record today."""
        if not academic_year_id:
            return 0

        q_all = (
            select(
                StudentAcademicRecord.class_id,
                StudentAcademicRecord.section_id,
            )
            .join(User, StudentAcademicRecord.student_id == User.id)
            .where(
                User.tenant_id == tenant_id,
                StudentAcademicRecord.academic_year_id == academic_year_id,
                StudentAcademicRecord.status == "ACTIVE",
            )
            .distinct()
        )
        all_pairs = set((r[0], r[1]) for r in (await db.execute(q_all)).all())
        if not all_pairs:
            return 0

        q_marked = (
            select(
                StudentDailyAttendance.class_id,
                StudentDailyAttendance.section_id,
            )
            .where(
                StudentDailyAttendance.tenant_id == tenant_id,
                StudentDailyAttendance.academic_year_id == academic_year_id,
                StudentDailyAttendance.attendance_date == on_date,
            )
            .distinct()
        )
        marked_pairs = set((r[0], r[1]) for r in (await db.execute(q_marked)).all())
        return len(all_pairs - marked_pairs)

    @staticmethod
    async def get_attendance_trend(
        db: AsyncSession,
        tenant_id: UUID,
        academic_year_id: Optional[UUID],
        end_date: date,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """Aggregate daily student attendance percentages over the last *days* days.

        Returns a list of dicts: {"day": "Mon", "value": 89, "date": "2026-03-24"}
        """
        if not academic_year_id:
            return []

        start_date = end_date - timedelta(days=days - 1)

        # Single aggregation query across all days in range
        q = (
            select(
                StudentDailyAttendance.attendance_date,
                StudentDailyAttendanceRecord.status,
                func.count(StudentDailyAttendanceRecord.id).label("cnt"),
            )
            .join(
                StudentDailyAttendanceRecord,
                StudentDailyAttendanceRecord.daily_attendance_id == StudentDailyAttendance.id,
            )
            .where(
                StudentDailyAttendance.tenant_id == tenant_id,
                StudentDailyAttendance.academic_year_id == academic_year_id,
                StudentDailyAttendance.attendance_date >= start_date,
                StudentDailyAttendance.attendance_date <= end_date,
            )
            .group_by(
                StudentDailyAttendance.attendance_date,
                StudentDailyAttendanceRecord.status,
            )
            .order_by(StudentDailyAttendance.attendance_date)
        )
        res = await db.execute(q)
        rows = res.all()

        # Bucket by date
        buckets: Dict[date, Dict[str, int]] = {}
        for att_date, status_val, cnt in rows:
            b = buckets.setdefault(att_date, {"present": 0, "total": 0})
            b["total"] += cnt
            if status_val == "PRESENT":
                b["present"] += cnt

        result: List[Dict[str, Any]] = []
        for i in range(days):
            d = start_date + timedelta(days=i)
            b = buckets.get(d, {"present": 0, "total": 0})
            pct = round(100 * b["present"] / b["total"]) if b["total"] else 0
            result.append({"day": d.strftime("%a"), "date": d.isoformat(), "value": pct})
        return result

    # ------------------------------------------------------------------ #
    #  HOMEWORK                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def get_homework_stats(
        db: AsyncSession, tenant_id: UUID
    ) -> Tuple[int, int]:
        """Return (total_assigned, total_submitted) scoped to tenant."""
        # total_assigned = HomeworkAssignments whose homework belongs to this tenant
        q_assigned = (
            select(func.count(HomeworkAssignment.id))
            .join(Homework, HomeworkAssignment.homework_id == Homework.id)
            .join(User, Homework.teacher_id == User.id)
            .where(User.tenant_id == tenant_id)
        )
        total_assigned: int = (await db.execute(q_assigned)).scalar() or 0

        # total_submitted = completed attempts for those assignments
        q_submitted = (
            select(func.count(HomeworkAttempt.id))
            .join(
                HomeworkAssignment,
                HomeworkAttempt.homework_assignment_id == HomeworkAssignment.id,
            )
            .join(Homework, HomeworkAssignment.homework_id == Homework.id)
            .join(User, Homework.teacher_id == User.id)
            .where(
                User.tenant_id == tenant_id,
                HomeworkAttempt.completed_at.isnot(None),
            )
        )
        total_submitted: int = (await db.execute(q_submitted)).scalar() or 0
        return total_assigned, total_submitted

    # ------------------------------------------------------------------ #
    #  EXAMS                                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def get_upcoming_exams(
        db: AsyncSession,
        tenant_id: UUID,
        from_date: date,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Upcoming exam schedules with class name and subject name (no N+1)."""
        q = (
            select(
                ExamSchedule.exam_date,
                Exam.name.label("exam_title"),
                SchoolClass.name.label("class_name"),
                SchoolSubject.name.label("subject_name"),
            )
            .join(Exam, ExamSchedule.exam_id == Exam.id)
            .join(SchoolClass, ExamSchedule.class_id == SchoolClass.id)
            .join(SchoolSubject, ExamSchedule.subject_id == SchoolSubject.id)
            .where(
                ExamSchedule.tenant_id == tenant_id,
                ExamSchedule.exam_date >= from_date,
            )
            .order_by(ExamSchedule.exam_date)
            .limit(limit)
        )
        res = await db.execute(q)
        return [
            {
                "date": row.exam_date.isoformat(),
                "title": row.exam_title,
                "class": row.class_name,
                "subject": row.subject_name,
            }
            for row in res.all()
        ]

    # ------------------------------------------------------------------ #
    #  LESSON PROGRESS                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def get_lesson_progress(
        db: AsyncSession,
        tenant_id: UUID,
        academic_year_id: Optional[UUID],
    ) -> Tuple[Optional[int], List[Dict[str, Any]]]:
        """Return (overall_percent, grade_breakdown_list)."""
        if not academic_year_id:
            return None, []

        q = (
            select(LessonPlanProgress.grade_group, LessonPlanProgress.progress_percent)
            .where(
                LessonPlanProgress.tenant_id == tenant_id,
                LessonPlanProgress.academic_year_id == academic_year_id,
                LessonPlanProgress.is_active.is_(True),
            )
            .order_by(LessonPlanProgress.progress_percent.desc())
        )
        try:
            res = await db.execute(q)
        except SQLAlchemyError:
            # Table might not be migrated yet in some environments.
            await db.rollback()
            return None, []
        rows = res.all()
        if not rows:
            return None, []

        grades = [{"name": r[0], "value": r[1]} for r in rows]
        overall = round(sum(r[1] for r in rows) / len(rows))
        return overall, grades

    # ------------------------------------------------------------------ #
    #  TIMETABLE                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def get_timetable_today(
        db: AsyncSession,
        tenant_id: UUID,
        academic_year_id: Optional[UUID],
        on_date: date,
    ) -> List[Dict[str, Any]]:
        """All timetable slots for today across the tenant (admin view)."""
        if not academic_year_id:
            return []

        day_of_week = on_date.weekday()  # 0=Monday
        q = (
            select(
                SchoolSubject.name.label("subject_name"),
                SchoolClass.name.label("class_name"),
                Section.name.label("section_name"),
                TimeSlot.start_time,
                TimeSlot.end_time,
                Timetable.slot_id,  # room info not in current model; kept for extension
            )
            .join(TimeSlot, Timetable.slot_id == TimeSlot.id)
            .join(SchoolClass, Timetable.class_id == SchoolClass.id)
            .join(Section, Timetable.section_id == Section.id)
            .join(SchoolSubject, Timetable.subject_id == SchoolSubject.id)
            .where(
                Timetable.tenant_id == tenant_id,
                Timetable.academic_year_id == academic_year_id,
                Timetable.day_of_week == day_of_week,
            )
            .order_by(TimeSlot.order_index, TimeSlot.start_time)
        )
        res = await db.execute(q)
        rows = res.all()

        def _fmt(t: Any) -> str:
            return t.strftime("%H:%M") if hasattr(t, "strftime") else str(t)

        return [
            {
                "subject": row.subject_name,
                "class": f"{row.class_name}-{row.section_name}",
                "room": None,
                "start": _fmt(row.start_time),
                "end": _fmt(row.end_time),
            }
            for row in rows
        ]

    # ------------------------------------------------------------------ #
    #  FEES                                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def get_fee_term_status(
        db: AsyncSession,
        tenant_id: UUID,
        academic_year_id: Optional[UUID],
    ) -> Tuple[Decimal, Decimal]:
        """Return (collected, total_due) for the current academic year."""
        if not academic_year_id:
            return Decimal("0"), Decimal("0")

        q_collected = select(
            func.coalesce(func.sum(PaymentTransaction.amount_paid), 0)
        ).where(
            PaymentTransaction.tenant_id == tenant_id,
            PaymentTransaction.academic_year_id == academic_year_id,
            PaymentTransaction.payment_status == "success",
        )
        collected = Decimal(str((await db.execute(q_collected)).scalar() or 0))

        q_total = select(
            func.coalesce(func.sum(StudentFeeAssignment.final_amount), 0)
        ).where(
            StudentFeeAssignment.tenant_id == tenant_id,
            StudentFeeAssignment.academic_year_id == academic_year_id,
            StudentFeeAssignment.is_active.is_(True),
        )
        total_due = Decimal(str((await db.execute(q_total)).scalar() or 0))
        return collected, total_due

    # ------------------------------------------------------------------ #
    #  PAYROLL                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def get_latest_payroll_run(
        db: AsyncSession, tenant_id: UUID
    ) -> Optional[Any]:
        """Return the most recent payroll run object, or None if module unavailable."""
        try:
            from modules.payroll.services import list_payroll_runs

            runs = await list_payroll_runs(db, tenant_id)
            return runs[0] if runs else None
        except (ImportError, Exception):
            return None

    # ------------------------------------------------------------------ #
    #  ALERTS                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def get_active_alerts(
        db: AsyncSession, tenant_id: UUID
    ) -> List[Dict[str, Any]]:
        """Return all non-expired active alerts for the tenant."""
        now = datetime.now(tz=timezone.utc)
        q = (
            select(DashboardAlert.alert_type, DashboardAlert.message, DashboardAlert.action_url)
            .where(
                DashboardAlert.tenant_id == tenant_id,
                DashboardAlert.is_active.is_(True),
                (DashboardAlert.expires_at.is_(None)) | (DashboardAlert.expires_at > now),
            )
            .order_by(DashboardAlert.created_at.desc())
        )
        try:
            res = await db.execute(q)
        except SQLAlchemyError:
            # Table might not be migrated yet in some environments.
            await db.rollback()
            return []
        return [
            {"type": row[0], "message": row[1], "action_url": row[2]}
            for row in res.all()
        ]
