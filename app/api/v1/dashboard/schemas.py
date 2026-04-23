"""Dashboard response schemas.

Contains both the original role-based summary types and the new
per-widget endpoint response types required by the admin dashboard spec.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════════════════
#  SHARED / PRIMITIVE BLOCKS  (used by legacy role-based summary)
# ══════════════════════════════════════════════════════════════════════════════

class CountCard(BaseModel):
    """Generic count with optional subtitle (e.g. '12 new this month', '4 on leave')."""
    value: int = Field(..., description="Main count")
    subtitle: Optional[str] = None
    icon_key: Optional[str] = None


class DailyPresence(BaseModel):
    """Today's attendance summary (legacy role-based format)."""
    date: date
    student_present: int = 0
    student_absent: int = 0
    staff_present: int = 0
    staff_absent: int = 0
    staff_on_leave: int = 0


class AttendanceTrendDay(BaseModel):
    """Single day for attendance trend (legacy format)."""
    date: str
    percentage: Optional[float] = None
    present: int = 0


class HomeworkStatus(BaseModel):
    """Homework assignment and submission summary (legacy format)."""
    total_assigned: int = 0
    total_submitted: int = 0
    pending: int = 0
    submission_rate_percent: float = 0.0


class ExamScheduleItem(BaseModel):
    """Upcoming exam entry (legacy format)."""
    id: UUID
    name: str
    exam_date: date
    class_name: Optional[str] = None
    section_name: Optional[str] = None
    exam_type: Optional[str] = None


class TimetableSlotItem(BaseModel):
    """Single slot for today's timetable (legacy format)."""
    subject_name: str
    class_section: str
    room_or_venue: Optional[str] = None
    start_time: str
    end_time: str
    teacher_name: Optional[str] = None


class FeeStatus(BaseModel):
    """Fee collection summary for active academic year (legacy format)."""
    collected_amount: Decimal = Decimal("0")
    pending_amount: Decimal = Decimal("0")
    collection_rate_percent: float = 0.0
    currency: str = "USD"


class PayrollStatus(BaseModel):
    """Last payroll run status (legacy format)."""
    last_run_month: Optional[str] = None
    last_run_year: Optional[str] = None
    status: Optional[str] = None
    paid_date: Optional[date] = None
    message: Optional[str] = None


class AlertItem(BaseModel):
    """Critical action or warning (legacy format)."""
    severity: str = "warning"
    message: str
    action_url: Optional[str] = None
    deadline: Optional[datetime] = None


# ══════════════════════════════════════════════════════════════════════════════
#  LEGACY ROLE-BASED SUMMARIES  (returned by GET /dashboard/summary)
# ══════════════════════════════════════════════════════════════════════════════

class AdminDashboardSummary(BaseModel):
    """Full dashboard for admin (tenant-scoped)."""
    role: str = "admin"
    students: CountCard = Field(default_factory=lambda: CountCard(value=0))
    teachers: CountCard = Field(default_factory=lambda: CountCard(value=0))
    staff: CountCard = Field(default_factory=lambda: CountCard(value=0))
    classes: CountCard = Field(default_factory=lambda: CountCard(value=0))
    sections: CountCard = Field(default_factory=lambda: CountCard(value=0))
    academic_year_label: Optional[str] = None
    academic_year_id: Optional[UUID] = None
    daily_presence: Optional[DailyPresence] = None
    attendance_trend_days: List[AttendanceTrendDay] = Field(default_factory=list)
    attendance_trend_percentage: Optional[float] = None
    homework_status: Optional[HomeworkStatus] = None
    upcoming_exams: List[ExamScheduleItem] = Field(default_factory=list)
    timetable_today: List[TimetableSlotItem] = Field(default_factory=list)
    fee_status: Optional[FeeStatus] = None
    payroll_status: Optional[PayrollStatus] = None
    alerts: List[AlertItem] = Field(default_factory=list)
    missing_attendance_sections_count: int = 0


class TeacherDashboardSummary(BaseModel):
    """Dashboard for teacher (own classes, homework, timetable)."""
    role: str = "teacher"
    my_classes_count: int = 0
    homework_assigned_by_me: int = 0
    pending_submissions: int = 0
    timetable_today: List[TimetableSlotItem] = Field(default_factory=list)
    upcoming_exams: List[ExamScheduleItem] = Field(default_factory=list)
    my_leave_status: Optional[str] = None
    alerts: List[AlertItem] = Field(default_factory=list)


class StudentDashboardSummary(BaseModel):
    """Dashboard for student (attendance, homework, fee, timetable)."""
    role: str = "student"
    attendance_today: Optional[str] = None
    homework_pending_count: int = 0
    homework_submitted_count: int = 0
    fee_pending_amount: Optional[Decimal] = None
    fee_status: Optional[str] = None
    timetable_today: List[TimetableSlotItem] = Field(default_factory=list)
    upcoming_exams: List[ExamScheduleItem] = Field(default_factory=list)
    alerts: List[AlertItem] = Field(default_factory=list)


class SuperAdminDashboardSummary(BaseModel):
    """Platform-wide dashboard for super admin."""
    role: str = "super_admin"
    total_tenants: int = 0
    total_students: int = 0
    total_employees: int = 0
    total_teachers: int = 0
    tenants_summary: List[Dict[str, Any]] = Field(default_factory=list)


class DashboardSummaryResponse(BaseModel):
    """Generic wrapper returned by GET /dashboard/summary."""
    success: bool = True
    data: Dict[str, Any]


# ══════════════════════════════════════════════════════════════════════════════
#  NEW PER-WIDGET RESPONSE SCHEMAS  (one per endpoint)
# ══════════════════════════════════════════════════════════════════════════════

# ── 1. Summary (admin structured view) ──────────────────────────────────────

class StudentSummaryBlock(BaseModel):
    total: int = 0
    new_this_month: int = 0


class TeacherSummaryBlock(BaseModel):
    total: int = 0
    on_leave: int = 0


class StaffSummaryBlock(BaseModel):
    total: int = 0
    departments: int = 0


class ClassSummaryBlock(BaseModel):
    total: int = 0
    range: str = "N/A"


class SectionSummaryBlock(BaseModel):
    total: int = 0
    avg_students_per_class: float = 0.0


class AcademicYearBlock(BaseModel):
    year: Optional[int] = None
    term: Optional[str] = None


class AdminSummaryResponse(BaseModel):
    """Response for GET /dashboard/summary (admin structured format)."""
    students: StudentSummaryBlock = Field(default_factory=StudentSummaryBlock)
    teachers: TeacherSummaryBlock = Field(default_factory=TeacherSummaryBlock)
    staff: StaffSummaryBlock = Field(default_factory=StaffSummaryBlock)
    classes: ClassSummaryBlock = Field(default_factory=ClassSummaryBlock)
    sections: SectionSummaryBlock = Field(default_factory=SectionSummaryBlock)
    academic_year: AcademicYearBlock = Field(default_factory=AcademicYearBlock)


# ── Setup progress (frontend onboarding wizard) ──────────────────────────────

class SetupStepStatus(BaseModel):
    """Single setup step status used by GET /dashboard/setup-progress."""

    key: str
    title: str
    required: bool = True
    completed: bool = False
    count: int = 0


class SetupProgressResponse(BaseModel):
    """Tenant setup completion status and current paused step."""

    is_completed: bool = False
    paused_at_step: Optional[str] = None
    paused_at_title: Optional[str] = None
    completed_required_steps: int = 0
    total_required_steps: int = 0
    steps: List[SetupStepStatus] = Field(default_factory=list)


# ── 2. Attendance today ──────────────────────────────────────────────────────

class AttendanceGroup(BaseModel):
    present: int = 0
    absent: int = 0


class AttendanceTodayResponse(BaseModel):
    """Response for GET /dashboard/attendance/today."""
    students: AttendanceGroup = Field(default_factory=AttendanceGroup)
    staff: AttendanceGroup = Field(default_factory=AttendanceGroup)
    missing_attendance_sections: int = 0


# ── 3. Attendance trends ─────────────────────────────────────────────────────

class TrendDataPoint(BaseModel):
    day: str   # "Mon", "Tue" …
    value: int = 0


class AttendanceTrendsResponse(BaseModel):
    """Response for GET /dashboard/attendance/trends."""
    average: float = 0.0
    change: str = "0%"
    data: List[TrendDataPoint] = Field(default_factory=list)


# ── 4. Homework ──────────────────────────────────────────────────────────────

class HomeworkStatusResponse(BaseModel):
    """Response for GET /dashboard/homework."""
    total_assigned: int = 0
    total_submitted: int = 0
    pending: int = 0
    submission_rate: int = 0  # integer percentage e.g. 89


# ── 5. Upcoming exams ────────────────────────────────────────────────────────

class UpcomingExamItem(BaseModel):
    date: str                  # ISO date string
    title: str
    class_: str = Field(..., alias="class")
    subject: str

    class Config:
        populate_by_name = True


# ── 6. Lesson progress ───────────────────────────────────────────────────────

class GradeProgressItem(BaseModel):
    name: str
    value: int = 0


class LessonProgressResponse(BaseModel):
    """Response for GET /dashboard/lesson-progress."""
    overall: Optional[int] = None
    grades: List[GradeProgressItem] = Field(default_factory=list)


# ── 7. Timetable today ───────────────────────────────────────────────────────

class TimetableEntryResponse(BaseModel):
    """Single timetable entry for GET /dashboard/timetable/today."""
    subject: str
    class_: str = Field(..., alias="class")
    room: Optional[str] = None
    start: str
    end: str

    class Config:
        populate_by_name = True


# ── 8. Fee status ────────────────────────────────────────────────────────────

class FeeTermResponse(BaseModel):
    """Response for GET /dashboard/fees/term."""
    collected: Decimal = Decimal("0")
    pending: Decimal = Decimal("0")
    collection_rate: int = 0  # integer percentage


# ── 9. Payroll status ────────────────────────────────────────────────────────

class PayrollStatusResponse(BaseModel):
    """Response for GET /dashboard/payroll/status."""
    status: str = "unknown"
    message: str = ""
    paid_on: Optional[str] = None  # ISO date string


# ── 10. Alerts ───────────────────────────────────────────────────────────────

class DashboardAlertItem(BaseModel):
    """Single alert item for GET /dashboard/alerts."""
    type: str = "warning"     # "info" | "warning" | "critical"
    message: str
    action_url: Optional[str] = None
