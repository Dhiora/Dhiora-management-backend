"""Dashboard service layer.

Combines the repository (raw DB queries) with Redis caching and
light business logic (rate calculations, alert generation).

Cache keys follow the pattern:
  dhiora:dashboard:<widget>:<tenant_id>[:<extra>]
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.config import settings
from app.core.models import (
    AcademicYear,
    Department,
    EmployeeAttendance,
    Exam,
    ExamSchedule,
    LeaveRequest,
    SchoolClass,
    Section,
    StudentAcademicRecord,
    StudentDailyAttendance,
    StudentDailyAttendanceRecord,
    StudentFeeAssignment,
    Tenant,
    Timetable,
    TimeSlot,
)
from app.core.models.homework import Homework, HomeworkAssignment, HomeworkAttempt
from app.core.models.payment_transaction import PaymentTransaction
from app.core.models.school_subject import SchoolSubject
from app.core.redis_client import cache_get, cache_set

from .repository import DashboardRepository
from .schemas import (
    # legacy
    AdminDashboardSummary,
    AlertItem,
    AttendanceTrendDay,
    CountCard,
    DailyPresence,
    ExamScheduleItem,
    FeeStatus,
    HomeworkStatus,
    PayrollStatus,
    TeacherDashboardSummary,
    StudentDashboardSummary,
    SuperAdminDashboardSummary,
    TimetableSlotItem,
    # new widget schemas
    AdminSummaryResponse,
    AcademicYearBlock,
    ClassSummaryBlock,
    SectionSummaryBlock,
    StaffSummaryBlock,
    StudentSummaryBlock,
    TeacherSummaryBlock,
    AttendanceTodayResponse,
    AttendanceGroup,
    AttendanceTrendsResponse,
    TrendDataPoint,
    DashboardAlertItem,
    FeeTermResponse,
    GradeProgressItem,
    HomeworkStatusResponse,
    LessonProgressResponse,
    PayrollStatusResponse,
    TimetableEntryResponse,
    UpcomingExamItem,
)

logger = logging.getLogger(__name__)

_TTL = settings.redis_cache_ttl_seconds  # default 300 s

# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _pct(part: int | float, total: int | float) -> float:
    return round(100 * part / total, 1) if total else 0.0


def _to_decimal(val: Any) -> Decimal:
    if val is None:
        return Decimal("0")
    return val if isinstance(val, Decimal) else Decimal(str(val))


# ══════════════════════════════════════════════════════════════════════════════
#  1. ADMIN STRUCTURED SUMMARY  (GET /dashboard/summary)
# ══════════════════════════════════════════════════════════════════════════════

async def get_admin_summary(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID],
) -> AdminSummaryResponse:
    cache_key = f"dhiora:dashboard:summary:{tenant_id}"
    cached = await cache_get(cache_key)
    if cached:
        return AdminSummaryResponse(**cached)

    today = date.today()
    first_of_month = today.replace(day=1)

    students_total = await DashboardRepository.count_students(db, tenant_id)
    students_new = await DashboardRepository.count_students(db, tenant_id, since=first_of_month)
    teachers_total = await DashboardRepository.count_teachers(db, tenant_id)
    on_leave = await DashboardRepository.count_employees_on_leave(db, tenant_id, today)
    dept_count = await DashboardRepository.count_departments(db, tenant_id)
    classes_total, grade_range = await DashboardRepository.count_classes(db, tenant_id)
    sections_total, avg_per_section = await DashboardRepository.count_sections(
        db, tenant_id, academic_year_id
    )

    ay: Optional[AcademicYear] = await DashboardRepository.get_active_academic_year(db, tenant_id)
    ay_block = AcademicYearBlock()
    if ay:
        ay_block.year = ay.start_date.year if hasattr(ay, "start_date") and ay.start_date else None
        ay_block.term = ay.name  # e.g. "2025-2026 Term 1"

    result = AdminSummaryResponse(
        students=StudentSummaryBlock(total=students_total, new_this_month=students_new),
        teachers=TeacherSummaryBlock(total=teachers_total, on_leave=on_leave),
        staff=StaffSummaryBlock(total=teachers_total, departments=dept_count),
        classes=ClassSummaryBlock(total=classes_total, range=grade_range),
        sections=SectionSummaryBlock(
            total=sections_total, avg_students_per_class=avg_per_section
        ),
        academic_year=ay_block,
    )

    await cache_set(cache_key, result.model_dump(), ttl=_TTL)
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  2. ATTENDANCE TODAY  (GET /dashboard/attendance/today)
# ══════════════════════════════════════════════════════════════════════════════

async def get_attendance_today(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID],
) -> AttendanceTodayResponse:
    today = date.today()
    cache_key = f"dhiora:dashboard:attendance:today:{tenant_id}:{today.isoformat()}"
    cached = await cache_get(cache_key)
    if cached:
        return AttendanceTodayResponse(**cached)

    s_present, s_absent = await DashboardRepository.get_student_attendance_today(
        db, tenant_id, academic_year_id, today
    )
    st_present, st_absent = await DashboardRepository.get_staff_attendance_today(
        db, tenant_id, today
    )
    missing = await DashboardRepository.count_missing_attendance_sections(
        db, tenant_id, academic_year_id, today
    )

    result = AttendanceTodayResponse(
        students=AttendanceGroup(present=s_present, absent=s_absent),
        staff=AttendanceGroup(present=st_present, absent=st_absent),
        missing_attendance_sections=missing,
    )

    await cache_set(cache_key, result.model_dump(), ttl=_TTL)
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  3. ATTENDANCE TRENDS  (GET /dashboard/attendance/trends?days=7)
# ══════════════════════════════════════════════════════════════════════════════

async def get_attendance_trends(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID],
    days: int = 7,
) -> AttendanceTrendsResponse:
    days = max(1, min(days, 90))  # clamp to safe range
    today = date.today()
    cache_key = f"dhiora:dashboard:attendance:trends:{tenant_id}:{days}"
    cached = await cache_get(cache_key)
    if cached:
        return AttendanceTrendsResponse(**cached)

    raw = await DashboardRepository.get_attendance_trend(
        db, tenant_id, academic_year_id, today, days
    )

    values = [r["value"] for r in raw if r["value"] > 0]
    average = round(sum(values) / len(values), 1) if values else 0.0

    # Compare last day to previous day for the change indicator
    change = "0%"
    if len(raw) >= 2:
        diff = raw[-1]["value"] - raw[-2]["value"]
        change = f"+{diff}%" if diff >= 0 else f"{diff}%"

    result = AttendanceTrendsResponse(
        average=average,
        change=change,
        data=[TrendDataPoint(day=r["day"], value=r["value"]) for r in raw],
    )

    await cache_set(cache_key, result.model_dump(), ttl=_TTL)
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  4. HOMEWORK  (GET /dashboard/homework)
# ══════════════════════════════════════════════════════════════════════════════

async def get_homework_status(
    db: AsyncSession, tenant_id: UUID
) -> HomeworkStatusResponse:
    total_assigned, total_submitted = await DashboardRepository.get_homework_stats(
        db, tenant_id
    )
    pending = max(0, total_assigned - total_submitted)
    rate = int(_pct(total_submitted, total_assigned))
    return HomeworkStatusResponse(
        total_assigned=total_assigned,
        total_submitted=total_submitted,
        pending=pending,
        submission_rate=rate,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  5. UPCOMING EXAMS  (GET /dashboard/exams/upcoming)
# ══════════════════════════════════════════════════════════════════════════════

async def get_upcoming_exams(
    db: AsyncSession, tenant_id: UUID, limit: int = 10
) -> List[UpcomingExamItem]:
    today = date.today()
    rows = await DashboardRepository.get_upcoming_exams(db, tenant_id, today, limit)
    return [
        UpcomingExamItem(
            date=r["date"],
            title=r["title"],
            **{"class": r["class"]},
            subject=r["subject"],
        )
        for r in rows
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  6. LESSON PROGRESS  (GET /dashboard/lesson-progress)
# ══════════════════════════════════════════════════════════════════════════════

async def get_lesson_progress(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID],
) -> LessonProgressResponse:
    overall, grades = await DashboardRepository.get_lesson_progress(
        db, tenant_id, academic_year_id
    )
    return LessonProgressResponse(
        overall=overall,
        grades=[GradeProgressItem(name=g["name"], value=g["value"]) for g in grades],
    )


# ══════════════════════════════════════════════════════════════════════════════
#  7. TIMETABLE TODAY  (GET /dashboard/timetable/today)
# ══════════════════════════════════════════════════════════════════════════════

async def get_timetable_today(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID],
) -> List[TimetableEntryResponse]:
    today = date.today()
    rows = await DashboardRepository.get_timetable_today(
        db, tenant_id, academic_year_id, today
    )
    return [
        TimetableEntryResponse(
            subject=r["subject"],
            **{"class": r["class"]},
            room=r.get("room"),
            start=r["start"],
            end=r["end"],
        )
        for r in rows
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  8. FEE STATUS  (GET /dashboard/fees/term)
# ══════════════════════════════════════════════════════════════════════════════

async def get_fee_term_status(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID],
) -> FeeTermResponse:
    collected, total_due = await DashboardRepository.get_fee_term_status(
        db, tenant_id, academic_year_id
    )
    pending = total_due - collected
    rate = int(_pct(float(collected), float(total_due)))
    return FeeTermResponse(collected=collected, pending=pending, collection_rate=rate)


# ══════════════════════════════════════════════════════════════════════════════
#  9. PAYROLL STATUS  (GET /dashboard/payroll/status)
# ══════════════════════════════════════════════════════════════════════════════

async def get_payroll_status(
    db: AsyncSession, tenant_id: UUID
) -> PayrollStatusResponse:
    run = await DashboardRepository.get_latest_payroll_run(db, tenant_id)
    if not run:
        return PayrollStatusResponse(status="no_data", message="No payroll run recorded yet.")

    paid_on: Optional[str] = None
    issued_at = getattr(run, "issued_at", None)
    if issued_at:
        paid_on = issued_at.date().isoformat() if hasattr(issued_at, "date") else str(issued_at)

    return PayrollStatusResponse(
        status=getattr(run, "status", "unknown"),
        message=f"{getattr(run, 'month', '')} {getattr(run, 'year', '')} salaries processed".strip(),
        paid_on=paid_on,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  10. ALERTS  (GET /dashboard/alerts)
# ══════════════════════════════════════════════════════════════════════════════

async def get_alerts(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID],
) -> List[DashboardAlertItem]:
    """Return persisted alerts PLUS auto-generated system alerts."""
    today = date.today()
    alerts: List[DashboardAlertItem] = []

    # --- Persisted alerts from DB ---
    db_alerts = await DashboardRepository.get_active_alerts(db, tenant_id)
    for a in db_alerts:
        alerts.append(DashboardAlertItem(type=a["type"], message=a["message"], action_url=a.get("action_url")))

    # --- Auto: missing attendance sections ---
    missing = await DashboardRepository.count_missing_attendance_sections(
        db, tenant_id, academic_year_id, today
    )
    if missing > 0:
        alerts.append(
            DashboardAlertItem(
                type="warning",
                message=f"{missing} section{'s' if missing != 1 else ''} haven't marked attendance today.",
            )
        )

    return alerts


# ══════════════════════════════════════════════════════════════════════════════
#  LEGACY ROLE-BASED SUMMARY  (GET /dashboard/summary – original endpoint)
# ══════════════════════════════════════════════════════════════════════════════

async def get_dashboard_summary(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    role: str,
    user_type: Optional[str],
    academic_year_id: Optional[UUID],
) -> Dict[str, Any]:
    today = date.today()
    active_ay = await DashboardRepository.get_active_academic_year(db, tenant_id)
    ay_id = academic_year_id or (active_ay.id if active_ay else None)
    ay_label = active_ay.name if active_ay else None

    if role in ("SUPER_ADMIN", "PLATFORM_ADMIN"):
        return await _super_admin_summary(db)

    if role == "ADMIN" or (role in ("SUPER_ADMIN", "PLATFORM_ADMIN") and tenant_id):
        return await _admin_summary(db, tenant_id, ay_id, ay_label, today)

    if user_type == "employee" and role != "ADMIN":
        return await _teacher_summary(db, tenant_id, user_id, ay_id, today)

    if user_type == "student":
        return await _student_summary(db, tenant_id, user_id, ay_id, today)

    return await _admin_summary(db, tenant_id, ay_id, ay_label, today)


# ── Private helpers for legacy summary ──────────────────────────────────────

async def _super_admin_summary(db: AsyncSession) -> Dict[str, Any]:
    q_t = select(func.count(Tenant.id))
    total_tenants = (await db.execute(q_t)).scalar() or 0

    q_s = select(func.count(User.id)).where(User.user_type == "student", User.status == "ACTIVE")
    total_students = (await db.execute(q_s)).scalar() or 0

    q_e = select(func.count(User.id)).where(User.user_type == "employee", User.status == "ACTIVE")
    total_employees = (await db.execute(q_e)).scalar() or 0

    return SuperAdminDashboardSummary(
        role="super_admin",
        total_tenants=total_tenants,
        total_students=total_students,
        total_employees=total_employees,
        total_teachers=total_employees,
    ).model_dump()


async def _admin_summary(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID],
    academic_year_label: Optional[str],
    today: date,
) -> Dict[str, Any]:
    students_total = await DashboardRepository.count_students(db, tenant_id)
    students_new = await DashboardRepository.count_students(db, tenant_id, since=today.replace(day=1))
    employees_total = await DashboardRepository.count_teachers(db, tenant_id)
    teachers_on_leave = await DashboardRepository.count_employees_on_leave(db, tenant_id, today)
    dept_count = await DashboardRepository.count_departments(db, tenant_id)
    classes_total, grade_range = await DashboardRepository.count_classes(db, tenant_id)
    sections_total, avg_per_section = await DashboardRepository.count_sections(db, tenant_id, academic_year_id)

    s_present, s_absent = await DashboardRepository.get_student_attendance_today(db, tenant_id, academic_year_id, today)
    st_present, st_absent = await DashboardRepository.get_staff_attendance_today(db, tenant_id, today)
    daily_presence = DailyPresence(
        date=today,
        student_present=s_present,
        student_absent=s_absent,
        staff_present=st_present,
        staff_absent=st_absent,
    )

    trend_raw = await DashboardRepository.get_attendance_trend(db, tenant_id, academic_year_id, today, 7)
    trend_days = [AttendanceTrendDay(date=r["day"], percentage=float(r["value"]), present=r["value"]) for r in trend_raw]
    values = [r["value"] for r in trend_raw if r["value"]]
    trend_pct = round(sum(values) / len(values), 1) if values else None

    total_assigned, total_submitted = await DashboardRepository.get_homework_stats(db, tenant_id)
    pending = max(0, total_assigned - total_submitted)
    homework_status = HomeworkStatus(
        total_assigned=total_assigned,
        total_submitted=total_submitted,
        pending=pending,
        submission_rate_percent=_pct(total_submitted, total_assigned),
    )

    exams_raw = await DashboardRepository.get_upcoming_exams(db, tenant_id, today, 10)
    # For legacy schema we need UUID-based items; return simplified without id
    upcoming_exams: list = []

    timetable_raw = await DashboardRepository.get_timetable_today(db, tenant_id, academic_year_id, today)
    timetable_today = [
        TimetableSlotItem(
            subject_name=r["subject"],
            class_section=r["class"],
            room_or_venue=r.get("room"),
            start_time=r["start"],
            end_time=r["end"],
        )
        for r in timetable_raw
    ]

    collected, total_due = await DashboardRepository.get_fee_term_status(db, tenant_id, academic_year_id)
    pending_fee = total_due - collected
    fee_status = FeeStatus(
        collected_amount=collected,
        pending_amount=pending_fee,
        collection_rate_percent=_pct(float(collected), float(total_due)),
    ) if total_due else None

    missing = await DashboardRepository.count_missing_attendance_sections(db, tenant_id, academic_year_id, today)
    alerts: List[AlertItem] = []
    if missing > 0:
        alerts.append(AlertItem(severity="warning", message=f"Missing records: {missing} sections haven't marked student attendance yet."))

    return AdminDashboardSummary(
        role="admin",
        students=CountCard(value=students_total, subtitle=f"+{students_new} new this month" if students_new else None, icon_key="groups"),
        teachers=CountCard(value=employees_total, subtitle=f"{teachers_on_leave} on leave" if teachers_on_leave else None, icon_key="school"),
        staff=CountCard(value=employees_total, subtitle=f"{dept_count} departments", icon_key="work"),
        classes=CountCard(value=classes_total, subtitle=grade_range, icon_key="menu_book"),
        sections=CountCard(value=sections_total, subtitle=f"Avg {avg_per_section} per class", icon_key="grid_view"),
        academic_year_label=academic_year_label,
        academic_year_id=academic_year_id,
        daily_presence=daily_presence,
        attendance_trend_days=trend_days,
        attendance_trend_percentage=trend_pct,
        homework_status=homework_status,
        upcoming_exams=upcoming_exams,
        timetable_today=timetable_today,
        fee_status=fee_status,
        alerts=alerts,
        missing_attendance_sections_count=missing,
    ).model_dump()


async def _teacher_summary(
    db: AsyncSession,
    tenant_id: UUID,
    teacher_id: UUID,
    academic_year_id: Optional[UUID],
    today: date,
) -> Dict[str, Any]:
    from app.core.models import TeacherClassAssignment

    q_classes = (
        select(func.count(func.distinct(TeacherClassAssignment.class_id)))
        .where(
            TeacherClassAssignment.teacher_id == teacher_id,
            TeacherClassAssignment.academic_year_id == academic_year_id,
        )
    )
    my_classes = (await db.execute(q_classes)).scalar() or 0

    q_hw = (
        select(func.count(HomeworkAssignment.id))
        .join(Homework, HomeworkAssignment.homework_id == Homework.id)
        .where(Homework.teacher_id == teacher_id)
    )
    hw_assigned = (await db.execute(q_hw)).scalar() or 0

    timetable_raw = await DashboardRepository.get_timetable_today(db, tenant_id, academic_year_id, today)
    timetable_today = [
        TimetableSlotItem(
            subject_name=r["subject"],
            class_section=r["class"],
            room_or_venue=r.get("room"),
            start_time=r["start"],
            end_time=r["end"],
        )
        for r in timetable_raw
    ]

    return TeacherDashboardSummary(
        role="teacher",
        my_classes_count=my_classes,
        homework_assigned_by_me=hw_assigned,
        pending_submissions=0,
        timetable_today=timetable_today,
        upcoming_exams=[],
    ).model_dump()


async def _student_summary(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    academic_year_id: Optional[UUID],
    today: date,
) -> Dict[str, Any]:
    from app.core.models import StudentAcademicRecord as SAR

    attendance_today = None
    if academic_year_id:
        q_sar = (
            select(StudentAcademicRecord.class_id, StudentAcademicRecord.section_id)
            .where(
                StudentAcademicRecord.student_id == student_id,
                StudentAcademicRecord.academic_year_id == academic_year_id,
                StudentAcademicRecord.status == "ACTIVE",
            )
            .limit(1)
        )
        row = (await db.execute(q_sar)).one_or_none()
        if row:
            q_da = select(StudentDailyAttendance.id).where(
                StudentDailyAttendance.tenant_id == tenant_id,
                StudentDailyAttendance.academic_year_id == academic_year_id,
                StudentDailyAttendance.class_id == row[0],
                StudentDailyAttendance.section_id == row[1],
                StudentDailyAttendance.attendance_date == today,
            )
            da_id = (await db.execute(q_da)).scalar_one_or_none()
            if da_id:
                q_rec = select(StudentDailyAttendanceRecord.status).where(
                    StudentDailyAttendanceRecord.daily_attendance_id == da_id,
                    StudentDailyAttendanceRecord.student_id == student_id,
                )
                rec = (await db.execute(q_rec)).one_or_none()
                if rec:
                    attendance_today = rec[0]

    q_pend = (
        select(HomeworkAssignment.id)
        .join(Homework, HomeworkAssignment.homework_id == Homework.id)
        .join(User, Homework.teacher_id == User.id)
        .join(
            SAR,
            and_(
                SAR.academic_year_id == HomeworkAssignment.academic_year_id,
                SAR.class_id == HomeworkAssignment.class_id,
                (HomeworkAssignment.section_id.is_(None))
                | (HomeworkAssignment.section_id == SAR.section_id),
            ),
        )
        .where(User.tenant_id == tenant_id, SAR.student_id == student_id, SAR.status == "ACTIVE")
    )
    assignment_ids = [r[0] for r in (await db.execute(q_pend)).all()]
    submitted = 0
    if assignment_ids:
        q_sub = select(func.count(func.distinct(HomeworkAttempt.homework_assignment_id))).where(
            HomeworkAttempt.homework_assignment_id.in_(assignment_ids),
            HomeworkAttempt.student_id == student_id,
            HomeworkAttempt.completed_at.isnot(None),
        )
        submitted = (await db.execute(q_sub)).scalar() or 0

    pending_count = max(0, len(assignment_ids) - submitted)

    fee_status = fee_pending = None
    if academic_year_id:
        r_fee = await db.execute(
            select(
                func.coalesce(func.sum(StudentFeeAssignment.final_amount), 0),
                func.coalesce(func.sum(PaymentTransaction.amount_paid), 0),
            )
            .select_from(StudentFeeAssignment)
            .outerjoin(
                PaymentTransaction,
                and_(
                    PaymentTransaction.student_fee_assignment_id == StudentFeeAssignment.id,
                    PaymentTransaction.payment_status == "success",
                ),
            )
            .where(
                StudentFeeAssignment.student_id == student_id,
                StudentFeeAssignment.academic_year_id == academic_year_id,
                StudentFeeAssignment.is_active.is_(True),
            )
        )
        row_fee = r_fee.one_or_none()
        if row_fee and row_fee[0]:
            total_due = _to_decimal(row_fee[0])
            total_paid = _to_decimal(row_fee[1])
            fee_pending = total_due - total_paid
            fee_status = "paid" if total_paid >= total_due else ("partial" if total_paid > 0 else "unpaid")

    timetable_raw = await DashboardRepository.get_timetable_today(db, tenant_id, academic_year_id, today)
    timetable_today = [
        TimetableSlotItem(
            subject_name=r["subject"],
            class_section=r["class"],
            room_or_venue=r.get("room"),
            start_time=r["start"],
            end_time=r["end"],
        )
        for r in timetable_raw
    ]

    return StudentDashboardSummary(
        role="student",
        attendance_today=attendance_today,
        homework_pending_count=pending_count,
        homework_submitted_count=submitted,
        fee_pending_amount=fee_pending,
        fee_status=fee_status,
        timetable_today=timetable_today,
        upcoming_exams=[],
    ).model_dump()
