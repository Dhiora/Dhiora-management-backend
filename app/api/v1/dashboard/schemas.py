"""Dashboard response schemas (camelCase for frontend)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ----- Shared blocks -----
class CountCard(BaseModel):
    """Generic count with optional subtitle (e.g. '12 new this month', '4 on leave')."""
    value: int = Field(..., description="Main count")
    subtitle: Optional[str] = None
    icon_key: Optional[str] = None  # e.g. 'groups', 'school', 'menu_book'


class DailyPresence(BaseModel):
    """Today's attendance summary."""
    date: date
    student_present: int = 0
    student_absent: int = 0
    staff_present: int = 0
    staff_absent: int = 0
    staff_on_leave: int = 0


class AttendanceTrendDay(BaseModel):
    """Single day for attendance trend."""
    date: str  # e.g. "Mon", or ISO date
    percentage: Optional[float] = None
    present: int = 0


class HomeworkStatus(BaseModel):
    """Homework assignment and submission summary."""
    total_assigned: int = 0
    total_submitted: int = 0
    pending: int = 0
    submission_rate_percent: float = 0.0


class ExamScheduleItem(BaseModel):
    """Upcoming exam entry."""
    id: UUID
    name: str
    exam_date: date
    class_name: Optional[str] = None
    section_name: Optional[str] = None
    exam_type: Optional[str] = None


class TimetableSlotItem(BaseModel):
    """Single slot for today's timetable."""
    subject_name: str
    class_section: str  # e.g. "Grade 12-A"
    room_or_venue: Optional[str] = None
    start_time: str  # e.g. "08:00"
    end_time: str
    teacher_name: Optional[str] = None


class FeeStatus(BaseModel):
    """Fee collection summary for active academic year."""
    collected_amount: Decimal = Decimal("0")
    pending_amount: Decimal = Decimal("0")
    collection_rate_percent: float = 0.0
    currency: str = "USD"


class PayrollStatus(BaseModel):
    """Last payroll run status."""
    last_run_month: Optional[str] = None
    last_run_year: Optional[str] = None
    status: Optional[str] = None  # draft, issued
    paid_date: Optional[date] = None
    message: Optional[str] = None


class AlertItem(BaseModel):
    """Critical action or warning."""
    severity: str = "warning"  # info, warning, critical
    message: str
    action_url: Optional[str] = None
    deadline: Optional[datetime] = None


# ----- Role-specific summary -----
class AdminDashboardSummary(BaseModel):
    """Full dashboard for admin (tenant-scoped)."""
    role: str = "admin"
    # Counts
    students: CountCard = Field(default_factory=lambda: CountCard(value=0))
    teachers: CountCard = Field(default_factory=lambda: CountCard(value=0))
    staff: CountCard = Field(default_factory=lambda: CountCard(value=0))
    classes: CountCard = Field(default_factory=lambda: CountCard(value=0))
    sections: CountCard = Field(default_factory=lambda: CountCard(value=0))
    # Academic context
    academic_year_label: Optional[str] = None
    academic_year_id: Optional[UUID] = None
    # Daily presence
    daily_presence: Optional[DailyPresence] = None
    # Trends
    attendance_trend_days: List[AttendanceTrendDay] = Field(default_factory=list)
    attendance_trend_percentage: Optional[float] = None
    # Homework
    homework_status: Optional[HomeworkStatus] = None
    # Exams
    upcoming_exams: List[ExamScheduleItem] = Field(default_factory=list)
    # Timetable today
    timetable_today: List[TimetableSlotItem] = Field(default_factory=list)
    # Fee & payroll
    fee_status: Optional[FeeStatus] = None
    payroll_status: Optional[PayrollStatus] = None
    # Alerts
    alerts: List[AlertItem] = Field(default_factory=list)
    # Missing records (e.g. sections not marked attendance)
    missing_attendance_sections_count: int = 0


class TeacherDashboardSummary(BaseModel):
    """Dashboard for teacher (own classes, homework, timetable)."""
    role: str = "teacher"
    my_classes_count: int = 0
    homework_assigned_by_me: int = 0
    pending_submissions: int = 0
    timetable_today: List[TimetableSlotItem] = Field(default_factory=list)
    upcoming_exams: List[ExamScheduleItem] = Field(default_factory=list)
    my_leave_status: Optional[str] = None  # e.g. "On leave today"
    alerts: List[AlertItem] = Field(default_factory=list)


class StudentDashboardSummary(BaseModel):
    """Dashboard for student (attendance, homework, fee, timetable)."""
    role: str = "student"
    attendance_today: Optional[str] = None  # PRESENT, ABSENT, etc.
    homework_pending_count: int = 0
    homework_submitted_count: int = 0
    fee_pending_amount: Optional[Decimal] = None
    fee_status: Optional[str] = None  # paid, partial, unpaid
    timetable_today: List[TimetableSlotItem] = Field(default_factory=list)
    upcoming_exams: List[ExamScheduleItem] = Field(default_factory=list)
    alerts: List[AlertItem] = Field(default_factory=list)


class SuperAdminDashboardSummary(BaseModel):
    """Platform-wide dashboard for super admin."""
    role: str = "super_admin"
    total_tenants: int = 0
    total_students: int = 0
    total_employees: int = 0
    total_teachers: int = 0  # subset of employees if distinguishable
    # Optional: per-tenant breakdown (light)
    tenants_summary: List[Dict[str, Any]] = Field(default_factory=list)


# ----- Union response -----
class DashboardSummaryResponse(BaseModel):
    """Single endpoint returns one of the role summaries."""
    success: bool = True
    data: Dict[str, Any] = Field(..., description="AdminDashboardSummary | TeacherDashboardSummary | StudentDashboardSummary | SuperAdminDashboardSummary")
