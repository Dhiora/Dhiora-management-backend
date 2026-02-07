from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ----- Student Attendance -----
STUDENT_STATUSES = ("PRESENT", "ABSENT", "LATE", "HALF_DAY")
EMPLOYEE_STATUSES = ("PRESENT", "ABSENT", "LATE", "HALF_DAY", "LEAVE")


class StudentAttendanceMark(BaseModel):
    """Mark attendance for a single student."""

    student_id: UUID
    status: str = Field(..., description="PRESENT, ABSENT, LATE, HALF_DAY")


class StudentAttendanceBulkMark(BaseModel):
    """Bulk mark student attendance for a date."""

    academic_year_id: UUID
    date: date
    records: List[StudentAttendanceMark] = Field(..., min_length=1)


class StudentAttendanceRecord(BaseModel):
    """Single student attendance record."""

    id: UUID
    student_id: UUID
    student_name: str
    roll_number: Optional[str] = None
    class_id: UUID
    class_name: str
    section_id: UUID
    section_name: str
    date: date
    status: str
    marked_by: UUID
    marked_by_name: Optional[str] = None
    created_at: datetime


class StudentAttendanceDaySummary(BaseModel):
    """Day-wise summary for students."""

    total_present: int
    total_absent: int
    total_late: int
    total_half_day: int
    records: List[StudentAttendanceRecord]


# ----- Employee Attendance -----
class EmployeeAttendanceMark(BaseModel):
    """Mark attendance for a single employee."""

    employee_id: UUID
    status: str = Field(..., description="PRESENT, ABSENT, LATE, HALF_DAY, LEAVE")


class EmployeeAttendanceBulkMark(BaseModel):
    """Bulk mark employee attendance for a date."""

    date: date
    records: List[EmployeeAttendanceMark] = Field(..., min_length=1)


class EmployeeAttendanceRecord(BaseModel):
    """Single employee attendance record."""

    id: UUID
    employee_id: UUID
    employee_name: str
    role: str
    date: date
    status: str
    marked_by: UUID
    marked_by_name: Optional[str] = None
    created_at: datetime


class EmployeeAttendanceDaySummary(BaseModel):
    """Day-wise summary for employees."""

    total_present: int
    total_absent: int
    total_late: int
    total_half_day: int
    total_leave: int
    records: List[EmployeeAttendanceRecord]


# ----- Monthly reports -----
class MonthlyAttendanceSummary(BaseModel):
    """Monthly attendance summary for one person."""

    present_days: int
    absent_days: int
    late_days: int
    half_day_days: int
    leave_days: Optional[int] = None  # employees only
    total_working_days: int


class TeacherClassAssignmentCreate(BaseModel):
    """Assign teacher to class-section (and optionally subject for override scope)."""

    teacher_id: UUID
    class_id: UUID
    section_id: UUID
    academic_year_id: UUID
    subject_id: Optional[UUID] = None


# ----- Daily + Subject Override Attendance -----
DAILY_STATUSES = ("DRAFT", "SUBMITTED", "LOCKED")
DAILY_RECORD_STATUSES = ("PRESENT", "ABSENT", "LATE", "HALF_DAY", "LEAVE")


class DailyAttendanceRecordItem(BaseModel):
    """One student record for daily mark."""

    student_id: UUID
    status: str = Field(..., description="PRESENT, ABSENT, LATE, HALF_DAY, LEAVE")


class DailyAttendanceMarkRequest(BaseModel):
    """Bulk mark daily attendance for a class-section. Creates master + records in one transaction."""

    academic_year_id: UUID
    class_id: UUID
    section_id: UUID
    attendance_date: date
    records: List[DailyAttendanceRecordItem] = Field(..., min_length=1)


class DailyAttendanceSubmitRequest(BaseModel):
    """Body for submit: daily_attendance_id (or identify by class/section/date)."""

    daily_attendance_id: UUID


class SubjectOverrideRequest(BaseModel):
    """Create or update subject override for one student."""

    daily_attendance_id: UUID
    subject_id: UUID
    student_id: UUID
    override_status: str = Field(..., description="PRESENT, ABSENT, LATE, HALF_DAY, LEAVE")
    reason: Optional[str] = None


class DailyAttendanceMasterResponse(BaseModel):
    """Daily attendance master (no records)."""

    id: UUID
    tenant_id: UUID
    academic_year_id: UUID
    class_id: UUID
    section_id: UUID
    attendance_date: date
    marked_by: UUID
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class DailyAttendanceRecordResponse(BaseModel):
    """Single record under a daily master."""

    id: UUID
    daily_attendance_id: UUID
    student_id: UUID
    student_name: Optional[str] = None
    roll_number: Optional[str] = None
    status: str

    class Config:
        from_attributes = True


class DailyAttendanceDayResponse(BaseModel):
    """Daily attendance for a class-section-date (ignores overrides)."""

    master: DailyAttendanceMasterResponse
    records: List[DailyAttendanceRecordResponse]


class ResolvedAttendanceItem(BaseModel):
    """Resolved status for one student (override if present else daily)."""

    student_id: UUID
    student_name: Optional[str] = None
    roll_number: Optional[str] = None
    daily_status: str
    override_status: Optional[str] = None
    resolved_status: str  # COALESCE(override, daily)


class SubjectWiseAttendanceResponse(BaseModel):
    """Subject-wise view: optional subject_id filter; resolved status per student."""

    master: DailyAttendanceMasterResponse
    subject_id: Optional[UUID] = None
    subject_name: Optional[str] = None
    items: List[ResolvedAttendanceItem]


class MonthlyAttendanceExtendedResponse(BaseModel):
    """Monthly summary with daily percentage and subject-wise percentage(s)."""

    student_id: UUID
    academic_year_id: UUID
    year: int
    month: int
    daily_present_days: int
    daily_absent_days: int
    daily_late_days: int
    daily_half_day_days: int
    daily_leave_days: int
    daily_total_days: int
    daily_percentage: float
    subject_percentages: List[dict] = Field(default_factory=list)  # [{ subject_id, subject_name, present_days, total_days, percentage }]
    total_working_days: int
