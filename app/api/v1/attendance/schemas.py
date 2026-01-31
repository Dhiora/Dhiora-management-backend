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
    """Assign teacher to class-section."""

    teacher_id: UUID
    class_id: UUID
    section_id: UUID
    academic_year_id: UUID
