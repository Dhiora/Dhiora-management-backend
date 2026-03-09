"""Dashboard service: aggregate counts and summaries by role."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
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
from app.core.models.school_subject import SchoolSubject
from app.core.models.payment_transaction import PaymentTransaction

from .schemas import (
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
)


def _to_decimal(val: Any) -> Decimal:
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


# ----- Counts (tenant-scoped) -----
async def _count_students(db: AsyncSession, tenant_id: UUID, active_only: bool = True) -> int:
    q = select(func.count(User.id)).where(
        User.tenant_id == tenant_id,
        User.user_type == "student",
    )
    if active_only:
        q = q.where(User.status == "ACTIVE")
    r = await db.execute(q)
    return r.scalar() or 0


async def _count_students_created_since(db: AsyncSession, tenant_id: UUID, since: date) -> int:
    q = select(func.count(User.id)).where(
        User.tenant_id == tenant_id,
        User.user_type == "student",
        User.created_at >= datetime.combine(since, datetime.min.time()).replace(tzinfo=timezone.utc),
    )
    r = await db.execute(q)
    return r.scalar() or 0


async def _count_employees(db: AsyncSession, tenant_id: UUID, active_only: bool = True) -> int:
    q = select(func.count(User.id)).where(
        User.tenant_id == tenant_id,
        User.user_type == "employee",
    )
    if active_only:
        q = q.where(User.status == "ACTIVE")
    r = await db.execute(q)
    return r.scalar() or 0


async def _count_employees_on_leave_today(db: AsyncSession, tenant_id: UUID, today: date) -> int:
    q = (
        select(func.count(LeaveRequest.id))
        .where(
            LeaveRequest.tenant_id == tenant_id,
            LeaveRequest.applicant_type == "EMPLOYEE",
            LeaveRequest.status == "APPROVED",
            LeaveRequest.from_date <= today,
            LeaveRequest.to_date >= today,
        )
    )
    r = await db.execute(q)
    return r.scalar() or 0


async def _count_departments(db: AsyncSession, tenant_id: UUID) -> int:
    q = select(func.count(Department.id)).where(
        Department.tenant_id == tenant_id,
        Department.is_active.is_(True),
    )
    r = await db.execute(q)
    return r.scalar() or 0


async def _count_classes(db: AsyncSession, tenant_id: UUID, active_only: bool = True) -> int:
    q = select(func.count(SchoolClass.id)).where(SchoolClass.tenant_id == tenant_id)
    if active_only:
        q = q.where(SchoolClass.is_active.is_(True))
    r = await db.execute(q)
    return r.scalar() or 0


async def _count_sections(db: AsyncSession, tenant_id: UUID, academic_year_id: Optional[UUID] = None) -> int:
    q = select(func.count(Section.id)).where(Section.tenant_id == tenant_id)
    if academic_year_id:
        # Sections linked to classes; we count distinct sections that have student records or timetable
        q = select(func.count(func.distinct(Section.id))).select_from(Section).where(Section.tenant_id == tenant_id)
    r = await db.execute(q)
    return r.scalar() or 0


# ----- Daily presence (today) -----
async def _get_daily_presence(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID],
    today: date,
) -> Optional[DailyPresence]:
    """Student present/absent from StudentDailyAttendance; staff from EmployeeAttendance."""
    student_present = 0
    student_absent = 0
    if academic_year_id:
        # All daily attendance masters for today
        q_masters = (
            select(StudentDailyAttendance.id)
            .where(
                StudentDailyAttendance.tenant_id == tenant_id,
                StudentDailyAttendance.academic_year_id == academic_year_id,
                StudentDailyAttendance.attendance_date == today,
            )
        )
        res = await db.execute(q_masters)
        master_ids = [r[0] for r in res.all()]
        if master_ids:
            q_rec = (
                select(StudentDailyAttendanceRecord.status, func.count(StudentDailyAttendanceRecord.id))
                .where(StudentDailyAttendanceRecord.daily_attendance_id.in_(master_ids))
                .group_by(StudentDailyAttendanceRecord.status)
            )
            rec_res = await db.execute(q_rec)
            for status_val, cnt in rec_res.all():
                if status_val == "PRESENT":
                    student_present += cnt
                else:
                    student_absent += cnt

    q_emp = (
        select(EmployeeAttendance.status, func.count(EmployeeAttendance.id))
        .join(User, EmployeeAttendance.employee_id == User.id)
        .where(User.tenant_id == tenant_id, EmployeeAttendance.date == today)
        .group_by(EmployeeAttendance.status)
    )
    emp_res = await db.execute(q_emp)
    staff_present = 0
    staff_absent = 0
    staff_leave = 0
    for status_val, cnt in emp_res.all():
        if status_val == "PRESENT":
            staff_present += cnt
        elif status_val == "LEAVE":
            staff_leave += cnt
        else:
            staff_absent += cnt

    return DailyPresence(
        date=today,
        student_present=student_present,
        student_absent=student_absent,
        staff_present=staff_present,
        staff_absent=staff_absent,
        staff_on_leave=staff_leave,
    )


# ----- Attendance trend (last 7 days) -----
async def _get_attendance_trend(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID],
    today: date,
) -> tuple[List[Dict], Optional[float]]:
    """Last 7 days: percentage present (student). Returns (list of days, overall percentage)."""
    days: List[Dict] = []
    total_present = 0
    total_expected = 0
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        day_name = d.strftime("%a")
        present = 0
        expected = 0
        if academic_year_id:
            q_m = (
                select(StudentDailyAttendance.id)
                .where(
                    StudentDailyAttendance.tenant_id == tenant_id,
                    StudentDailyAttendance.academic_year_id == academic_year_id,
                    StudentDailyAttendance.attendance_date == d,
                )
            )
            res = await db.execute(q_m)
            mids = [r[0] for r in res.all()]
            if mids:
                q_r = (
                    select(StudentDailyAttendanceRecord.status, func.count(StudentDailyAttendanceRecord.id))
                    .where(StudentDailyAttendanceRecord.daily_attendance_id.in_(mids))
                    .group_by(StudentDailyAttendanceRecord.status)
                )
                rres = await db.execute(q_r)
                for st, cnt in rres.all():
                    expected += cnt
                    if st == "PRESENT":
                        present += cnt
        pct = round(100 * present / expected, 1) if expected else None
        days.append({"date": day_name, "percentage": pct, "present": present})
        total_present += present
        total_expected += expected
    overall = round(100 * total_present / total_expected, 1) if total_expected else None
    return days, overall


# ----- Homework -----
async def _get_homework_status(db: AsyncSession, tenant_id: UUID) -> HomeworkStatus:
    from app.core.models.homework import Homework, HomeworkAssignment, HomeworkAttempt

    q_assign = (
        select(func.count(HomeworkAssignment.id))
        .select_from(HomeworkAssignment)
        .join(Homework, HomeworkAssignment.homework_id == Homework.id)
        .join(User, Homework.teacher_id == User.id)
        .where(User.tenant_id == tenant_id)
    )
    r_assign = await db.execute(q_assign)
    total_assigned = r_assign.scalar() or 0

    q_sub = (
        select(func.count(HomeworkAttempt.id))
        .select_from(HomeworkAttempt)
        .where(HomeworkAttempt.completed_at.isnot(None))
    )
    r_sub = await db.execute(q_sub)
    total_submitted = r_sub.scalar() or 0

    pending = max(0, total_assigned - total_submitted)  # approximate
    rate = round(100 * total_submitted / total_assigned, 1) if total_assigned else 0.0
    return HomeworkStatus(
        total_assigned=total_assigned,
        total_submitted=total_submitted,
        pending=pending,
        submission_rate_percent=rate,
    )


# ----- Upcoming exams -----
async def _get_upcoming_exams(
    db: AsyncSession,
    tenant_id: UUID,
    today: date,
    limit: int = 10,
) -> List[ExamScheduleItem]:
    q = (
        select(ExamSchedule, Exam, SchoolClass, Section)
        .join(Exam, ExamSchedule.exam_id == Exam.id)
        .join(SchoolClass, ExamSchedule.class_id == SchoolClass.id)
        .join(Section, ExamSchedule.section_id == Section.id)
        .where(
            ExamSchedule.tenant_id == tenant_id,
            ExamSchedule.exam_date >= today,
        )
        .order_by(ExamSchedule.exam_date)
        .limit(limit)
    )
    res = await db.execute(q)
    rows = res.all()
    return [
        ExamScheduleItem(
            id=row[0].id,
            name=row[1].name,
            exam_date=row[0].exam_date,
            class_name=row[2].name if row[2] else None,
            section_name=row[3].name if row[3] else None,
            exam_type=None,
        )
        for row in rows
    ]


# ----- Timetable today -----
async def _get_timetable_today(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID],
    today: date,
    teacher_id: Optional[UUID] = None,
    class_section_filter: Optional[tuple[UUID, UUID]] = None,
) -> List[TimetableSlotItem]:
    if not academic_year_id:
        return []
    day_of_week = today.weekday()  # Monday=0
    q = (
        select(Timetable, TimeSlot, SchoolClass, Section, SchoolSubject, User)
        .join(TimeSlot, Timetable.slot_id == TimeSlot.id)
        .join(SchoolClass, Timetable.class_id == SchoolClass.id)
        .join(Section, Timetable.section_id == Section.id)
        .join(SchoolSubject, Timetable.subject_id == SchoolSubject.id)
        .join(User, Timetable.teacher_id == User.id)
        .where(
            Timetable.tenant_id == tenant_id,
            Timetable.academic_year_id == academic_year_id,
            Timetable.day_of_week == day_of_week,
        )
    )
    if teacher_id:
        q = q.where(Timetable.teacher_id == teacher_id)
    if class_section_filter:
        cid, sid = class_section_filter
        q = q.where(Timetable.class_id == cid, Timetable.section_id == sid)
    q = q.order_by(TimeSlot.order_index, TimeSlot.start_time)
    res = await db.execute(q)
    rows = res.all()
    out = []
    for t, slot, cl, sec, subj, teacher in rows:
        start_str = slot.start_time.strftime("%H:%M") if hasattr(slot.start_time, "strftime") else str(slot.start_time)
        end_str = slot.end_time.strftime("%H:%M") if hasattr(slot.end_time, "strftime") else str(slot.end_time)
        out.append(
            TimetableSlotItem(
                subject_name=subj.name if subj else "",
                class_section=f"{cl.name if cl else ''}-{sec.name if sec else ''}",
                room_or_venue=None,
                start_time=start_str,
                end_time=end_str,
                teacher_name=teacher.full_name if teacher else None,
            )
        )
    return out


# ----- Fee status -----
async def _get_fee_status(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID],
) -> Optional[FeeStatus]:
    if not academic_year_id:
        return None
    q_paid = (
        select(func.coalesce(func.sum(PaymentTransaction.amount_paid), 0))
        .where(
            PaymentTransaction.tenant_id == tenant_id,
            PaymentTransaction.academic_year_id == academic_year_id,
            PaymentTransaction.payment_status == "success",
        )
    )
    r_paid = await db.execute(q_paid)
    collected = _to_decimal(r_paid.scalar() or 0)

    q_total = (
        select(func.coalesce(func.sum(StudentFeeAssignment.final_amount), 0))
        .where(
            StudentFeeAssignment.tenant_id == tenant_id,
            StudentFeeAssignment.academic_year_id == academic_year_id,
            StudentFeeAssignment.is_active.is_(True),
        )
    )
    r_total = await db.execute(q_total)
    total_due = _to_decimal(r_total.scalar() or 0)
    pending = total_due - collected
    rate = float(round(100 * collected / total_due, 1)) if total_due else 0.0
    return FeeStatus(
        collected_amount=collected,
        pending_amount=pending,
        collection_rate_percent=rate,
        currency="USD",
    )


# ----- Payroll status -----
async def _get_payroll_status(db: AsyncSession, tenant_id: UUID) -> Optional[PayrollStatus]:
    try:
        from modules.payroll.services import list_payroll_runs
    except ImportError:
        return None
    runs = await list_payroll_runs(db, tenant_id)
    if not runs:
        return PayrollStatus(message="No payroll run yet")
    latest = runs[0]
    return PayrollStatus(
        last_run_month=latest.month,
        last_run_year=latest.year,
        status=latest.status,
        paid_date=getattr(latest, "issued_at", None) or None,
        message=f"{latest.month}/{latest.year} - {latest.status}",
    )


# ----- Missing attendance (sections without daily attendance today) -----
async def _count_missing_attendance_sections(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID],
    today: date,
) -> int:
    if not academic_year_id:
        return 0
    # All class-section pairs that have active students in this academic year
    q_all = (
        select(StudentAcademicRecord.class_id, StudentAcademicRecord.section_id)
        .where(
            StudentAcademicRecord.tenant_id == tenant_id,
            StudentAcademicRecord.academic_year_id == academic_year_id,
            StudentAcademicRecord.status == "ACTIVE",
        )
        .distinct()
    )
    res = await db.execute(q_all)
    all_pairs = set((r[0], r[1]) for r in res.all())
    if not all_pairs:
        return 0
    q_marked = (
        select(StudentDailyAttendance.class_id, StudentDailyAttendance.section_id)
        .where(
            StudentDailyAttendance.tenant_id == tenant_id,
            StudentDailyAttendance.academic_year_id == academic_year_id,
            StudentDailyAttendance.attendance_date == today,
        )
        .distinct()
    )
    res2 = await db.execute(q_marked)
    marked_pairs = set((r[0], r[1]) for r in res2.all())
    missing = all_pairs - marked_pairs
    return len(missing)


# ----- Active academic year -----
async def _get_active_academic_year(db: AsyncSession, tenant_id: UUID) -> Optional[AcademicYear]:
    q = (
        select(AcademicYear)
        .where(
            AcademicYear.tenant_id == tenant_id,
            AcademicYear.status == "ACTIVE",
        )
        .order_by(AcademicYear.end_date.desc())
        .limit(1)
    )
    res = await db.execute(q)
    return res.scalar_one_or_none()


# ----- Main: get dashboard by role -----
async def get_dashboard_summary(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    role: str,
    user_type: Optional[str],
    academic_year_id: Optional[UUID],
) -> Dict[str, Any]:
    today = date.today()
    active_ay = await _get_active_academic_year(db, tenant_id)
    ay_id = academic_year_id or (active_ay.id if active_ay else None)
    ay_label = active_ay.name if active_ay else None

    # Super admin: platform-wide
    if role in ("SUPER_ADMIN", "PLATFORM_ADMIN"):
        return await _super_admin_summary(db)

    # Admin dashboard
    if role == "ADMIN" or (role in ("SUPER_ADMIN", "PLATFORM_ADMIN") and tenant_id):
        return await _admin_summary(db, tenant_id, ay_id, ay_label, today)

    # Teacher dashboard
    if user_type == "employee" and role != "ADMIN":
        return await _teacher_summary(db, tenant_id, user_id, ay_id, today)

    # Student dashboard
    if user_type == "student":
        return await _student_summary(db, tenant_id, user_id, ay_id, today)

    # Fallback: admin-style for other roles (e.g. HR)
    return await _admin_summary(db, tenant_id, ay_id, ay_label, today)


async def _super_admin_summary(db: AsyncSession) -> Dict[str, Any]:
    q_tenants = select(func.count(Tenant.id))
    r_t = await db.execute(q_tenants)
    total_tenants = r_t.scalar() or 0

    q_students = select(func.count(User.id)).where(User.user_type == "student", User.status == "ACTIVE")
    r_s = await db.execute(q_students)
    total_students = r_s.scalar() or 0

    q_emp = select(func.count(User.id)).where(User.user_type == "employee", User.status == "ACTIVE")
    r_e = await db.execute(q_emp)
    total_employees = r_e.scalar() or 0

    summary = SuperAdminDashboardSummary(
        role="super_admin",
        total_tenants=total_tenants,
        total_students=total_students,
        total_employees=total_employees,
        total_teachers=total_employees,  # or filter by role if needed
    )
    return summary.model_dump()


async def _admin_summary(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID],
    academic_year_label: Optional[str],
    today: date,
) -> Dict[str, Any]:
    students_total = await _count_students(db, tenant_id)
    students_new = await _count_students_created_since(
        db, tenant_id, today.replace(day=1)
    )
    employees_total = await _count_employees(db, tenant_id)
    teachers_on_leave = await _count_employees_on_leave_today(db, tenant_id, today)
    dept_count = await _count_departments(db, tenant_id)
    classes_total = await _count_classes(db, tenant_id)
    sections_total = await _count_sections(db, tenant_id)
    avg_per_class = round(sections_total / classes_total, 1) if classes_total else 0

    daily_presence = await _get_daily_presence(db, tenant_id, academic_year_id, today)
    trend_days_raw, trend_pct = await _get_attendance_trend(db, tenant_id, academic_year_id, today)
    attendance_trend_days = [
        AttendanceTrendDay(date=d["date"], percentage=d["percentage"], present=d["present"])
        for d in trend_days_raw
    ]
    homework_status = await _get_homework_status(db, tenant_id)
    upcoming_exams = await _get_upcoming_exams(db, tenant_id, today)
    timetable_today = await _get_timetable_today(db, tenant_id, academic_year_id, today)
    fee_status = await _get_fee_status(db, tenant_id, academic_year_id)
    payroll_status = await _get_payroll_status(db, tenant_id)
    missing_attendance = await _count_missing_attendance_sections(db, tenant_id, academic_year_id, today)

    alerts: List[AlertItem] = []
    if missing_attendance > 0:
        alerts.append(
            AlertItem(
                severity="warning",
                message=f"Missing records: {missing_attendance} sections haven't marked student attendance yet.",
            )
        )

    summary = AdminDashboardSummary(
        role="admin",
        students=CountCard(value=students_total, subtitle=f"+{students_new} new this month" if students_new else None, icon_key="groups"),
        teachers=CountCard(value=employees_total, subtitle=f"{teachers_on_leave} on leave" if teachers_on_leave else None, icon_key="school"),
        staff=CountCard(value=employees_total, subtitle=f"{dept_count} departments", icon_key="work"),
        classes=CountCard(value=classes_total, subtitle=f"6-12 standard", icon_key="menu_book"),
        sections=CountCard(value=sections_total, subtitle=f"Avg {avg_per_class} per class", icon_key="grid_view"),
        academic_year_label=academic_year_label,
        academic_year_id=academic_year_id,
        daily_presence=daily_presence,
        attendance_trend_days=attendance_trend_days,
        attendance_trend_percentage=trend_pct,
        homework_status=homework_status,
        upcoming_exams=upcoming_exams,
        timetable_today=timetable_today,
        fee_status=fee_status,
        payroll_status=payroll_status,
        alerts=alerts,
        missing_attendance_sections_count=missing_attendance,
    )
    return summary.model_dump()


async def _teacher_summary(
    db: AsyncSession,
    tenant_id: UUID,
    teacher_id: UUID,
    academic_year_id: Optional[UUID],
    today: date,
) -> Dict[str, Any]:
    from app.core.models import TeacherClassAssignment
    from app.core.models.homework import Homework, HomeworkAssignment

    q_classes = (
        select(func.count(func.distinct(TeacherClassAssignment.class_id)))
        .where(
            TeacherClassAssignment.teacher_id == teacher_id,
            TeacherClassAssignment.academic_year_id == academic_year_id,
        )
    )
    r = await db.execute(q_classes)
    my_classes_count = r.scalar() or 0

    q_hw = (
        select(func.count(HomeworkAssignment.id))
        .select_from(HomeworkAssignment)
        .join(Homework, HomeworkAssignment.homework_id == Homework.id)
        .where(Homework.teacher_id == teacher_id)
    )
    r_hw = await db.execute(q_hw)
    homework_assigned = r_hw.scalar() or 0

    timetable_today = await _get_timetable_today(db, tenant_id, academic_year_id, today, teacher_id=teacher_id)
    upcoming_exams = await _get_upcoming_exams(db, tenant_id, today, limit=5)

    summary = TeacherDashboardSummary(
        role="teacher",
        my_classes_count=my_classes_count,
        homework_assigned_by_me=homework_assigned,
        pending_submissions=0,
        timetable_today=timetable_today,
        upcoming_exams=upcoming_exams,
    )
    return summary.model_dump()


async def _student_summary(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    academic_year_id: Optional[UUID],
    today: date,
) -> Dict[str, Any]:
    from app.core.models.homework import HomeworkAssignment, HomeworkAttempt

    # Attendance today: check StudentDailyAttendanceRecord for this student
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
        res = await db.execute(q_sar)
        row = res.one_or_none()
        if row:
            cid, sid = row[0], row[1]
            q_da = (
                select(StudentDailyAttendance.id)
                .where(
                    StudentDailyAttendance.tenant_id == tenant_id,
                    StudentDailyAttendance.academic_year_id == academic_year_id,
                    StudentDailyAttendance.class_id == cid,
                    StudentDailyAttendance.section_id == sid,
                    StudentDailyAttendance.attendance_date == today,
                )
            )
            r_da = await db.execute(q_da)
            da_id = r_da.scalar_one_or_none()
            if da_id:
                q_rec = (
                    select(StudentDailyAttendanceRecord.status)
                    .where(
                        StudentDailyAttendanceRecord.daily_attendance_id == da_id[0],
                        StudentDailyAttendanceRecord.student_id == student_id,
                    )
                )
                r_rec = await db.execute(q_rec)
                rec = r_rec.one_or_none()
                if rec:
                    attendance_today = rec[0]

    from app.core.models.homework import Homework, HomeworkAssignment, HomeworkAttempt
    from app.core.models import StudentAcademicRecord as SAR

    q_pend = (
        select(HomeworkAssignment.id)
        .select_from(HomeworkAssignment)
        .join(Homework, HomeworkAssignment.homework_id == Homework.id)
        .join(User, Homework.teacher_id == User.id)
        .join(
            SAR,
            and_(
                SAR.academic_year_id == HomeworkAssignment.academic_year_id,
                SAR.class_id == HomeworkAssignment.class_id,
                (HomeworkAssignment.section_id.is_(None)) | (HomeworkAssignment.section_id == SAR.section_id),
            ),
        )
        .where(
            User.tenant_id == tenant_id,
            SAR.student_id == student_id,
            SAR.status == "ACTIVE",
        )
    )
    r_pend = await db.execute(q_pend)
    assignment_ids = [r[0] for r in r_pend.all()]
    submitted = 0
    if assignment_ids:
        q_sub = (
            select(func.count(func.distinct(HomeworkAttempt.homework_assignment_id)))
            .where(
                HomeworkAttempt.homework_assignment_id.in_(assignment_ids),
                HomeworkAttempt.student_id == student_id,
                HomeworkAttempt.completed_at.isnot(None),
            )
        )
        r_sub = await db.execute(q_sub)
        submitted = r_sub.scalar() or 0
    pending_count = len(assignment_ids) - submitted if assignment_ids else 0

    fee_status = None
    fee_pending = None
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
            if total_paid >= total_due:
                fee_status = "paid"
            elif total_paid > 0:
                fee_status = "partial"
            else:
                fee_status = "unpaid"

    q_sar2 = (
        select(SAR.class_id, SAR.section_id)
        .where(SAR.student_id == student_id, SAR.academic_year_id == academic_year_id, SAR.status == "ACTIVE")
        .limit(1)
    )
    r_sar2 = await db.execute(q_sar2)
    sar_row = r_sar2.one_or_none()
    class_section_filter = (sar_row[0], sar_row[1]) if sar_row else None
    timetable_today = await _get_timetable_today(
        db, tenant_id, academic_year_id, today, class_section_filter=class_section_filter
    )
    upcoming_exams = await _get_upcoming_exams(db, tenant_id, today, limit=5)

    summary = StudentDashboardSummary(
        role="student",
        attendance_today=attendance_today,
        homework_pending_count=pending_count,
        homework_submitted_count=submitted,
        fee_pending_amount=fee_pending,
        fee_status=fee_status,
        timetable_today=timetable_today,
        upcoming_exams=upcoming_exams,
    )
    return summary.model_dump()
