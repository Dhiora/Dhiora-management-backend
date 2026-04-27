"""Parent Portal Pydantic schemas."""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator


# ─── Auth ────────────────────────────────────────────────────────────────────

class ParentLoginRequest(BaseModel):
    email: EmailStr
    password: str


class ParentLoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    parent_id: UUID
    linked_children: List["ChildSummary"]


class ParentRefreshRequest(BaseModel):
    refresh_token: str


class ParentRefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ─── Profile ─────────────────────────────────────────────────────────────────

class ChildSummary(BaseModel):
    student_id: UUID
    full_name: str
    class_name: Optional[str] = None
    section_name: Optional[str] = None
    roll_number: Optional[str] = None
    relation: str
    is_primary: bool


class ParentProfile(BaseModel):
    id: UUID
    full_name: str
    phone: Optional[str]
    email: str


class MeResponse(BaseModel):
    parent: ParentProfile
    children: List[ChildSummary]


class ParentUpdateRequest(BaseModel):
    phone: Optional[str] = None
    email: Optional[EmailStr] = None


# ─── Student detail ──────────────────────────────────────────────────────────

class StudentDetail(BaseModel):
    id: UUID
    full_name: str
    email: Optional[str] = None
    mobile: Optional[str] = None
    roll_number: Optional[str] = None
    class_id: Optional[UUID] = None
    class_name: Optional[str] = None
    section_id: Optional[UUID] = None
    section_name: Optional[str] = None
    academic_year_name: Optional[str] = None


class ChildSummaryCard(BaseModel):
    student_id: UUID
    full_name: str
    class_name: Optional[str] = None
    section_name: Optional[str] = None
    attendance_this_month: "AttendanceStats"
    fees_pending: "FeesPendingSummary"
    homework_pending: int
    next_exam: Optional["NextExam"] = None


class AttendanceStats(BaseModel):
    total_days: int
    present: int
    absent: int
    late: int
    percentage: float


class FeesPendingSummary(BaseModel):
    count: int
    total_amount: Decimal


class NextExam(BaseModel):
    name: str
    date: Optional[date] = None
    subjects: List[str] = []


# ─── Attendance ───────────────────────────────────────────────────────────────

class AttendanceRecord(BaseModel):
    date: date
    status: str
    marked_by_name: Optional[str] = None
    marked_at: Optional[datetime] = None


class MonthlyAttendanceResponse(BaseModel):
    month: int
    year: int
    records: List[AttendanceRecord]
    stats: AttendanceStats


# ─── Fees ────────────────────────────────────────────────────────────────────

class FeeAssignmentParentView(BaseModel):
    id: UUID
    fee_name: str
    base_amount: Decimal
    total_discount: Decimal
    final_amount: Decimal
    amount_paid: Decimal
    balance: Decimal
    status: str
    due_date: Optional[date] = None


class PaymentHistoryItem(BaseModel):
    id: UUID
    fee_name: str
    amount_paid: Decimal
    payment_mode: str
    transaction_reference: Optional[str] = None
    paid_at: datetime


class RazorpayOrderResponse(BaseModel):
    razorpay_order_id: str
    amount: int
    currency: str
    key_id: str
    fee_assignment_id: UUID


class FeePayVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    fee_assignment_id: UUID


class FeePayVerifyResponse(BaseModel):
    success: bool
    payment_id: UUID


# ─── Homework ─────────────────────────────────────────────────────────────────

class HomeworkParentItem(BaseModel):
    homework_id: UUID
    assignment_id: UUID
    title: str
    description: Optional[str] = None
    subject_name: Optional[str] = None
    due_date: datetime
    submission_status: str  # not_started | in_progress | submitted | graded
    score: Optional[int] = None
    teacher_remarks: Optional[str] = None


class HomeworkParentDetail(BaseModel):
    homework_id: UUID
    assignment_id: UUID
    title: str
    description: Optional[str] = None
    subject_name: Optional[str] = None
    due_date: datetime
    submission_status: str
    score: Optional[int] = None
    teacher_remarks: Optional[str] = None
    total_questions: int


# ─── Assessments ─────────────────────────────────────────────────────────────

class AssessmentParentItem(BaseModel):
    assessment_id: UUID
    title: str
    subject_name: Optional[str] = None
    due_date: Optional[date] = None
    status: str
    attempt_status: Optional[str] = None
    score: Optional[int] = None
    total_marks: int
    percentage: Optional[float] = None


class AssessmentParentResult(BaseModel):
    assessment_id: UUID
    title: str
    total_marks: int
    score: Optional[int] = None
    percentage: Optional[float] = None
    correct_count: Optional[int] = None
    wrong_count: Optional[int] = None
    skipped_count: Optional[int] = None
    time_taken_seconds: Optional[int] = None
    submitted_at: Optional[datetime] = None


# ─── Timetable ────────────────────────────────────────────────────────────────

class TimetableSlot(BaseModel):
    period: int
    subject_name: str
    teacher_name: str
    start_time: time
    end_time: time
    slot_type: str


class WeeklyTimetable(BaseModel):
    monday: List[TimetableSlot] = []
    tuesday: List[TimetableSlot] = []
    wednesday: List[TimetableSlot] = []
    thursday: List[TimetableSlot] = []
    friday: List[TimetableSlot] = []
    saturday: List[TimetableSlot] = []
    sunday: List[TimetableSlot] = []


# ─── Notifications ────────────────────────────────────────────────────────────

class NotificationItem(BaseModel):
    id: UUID
    type: str
    title: str
    body: str
    is_read: bool
    sent_at: datetime
    student_id: Optional[UUID] = None


class NotificationPreferenceResponse(BaseModel):
    sms_enabled: bool
    email_enabled: bool
    push_enabled: bool
    types_muted: List[str]


class NotificationPreferenceUpdate(BaseModel):
    sms_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    push_enabled: Optional[bool] = None
    types_muted: Optional[List[str]] = None


# ─── Messaging ────────────────────────────────────────────────────────────────

class MessageItem(BaseModel):
    id: UUID
    sender_role: str
    sender_id: UUID
    body: str
    sent_at: datetime
    is_read: bool


class ThreadPreview(BaseModel):
    id: UUID
    teacher_id: UUID
    teacher_name: str
    student_id: UUID
    student_name: str
    subject: str
    last_message_at: datetime
    unread_count: int
    last_message_preview: Optional[str] = None


class ThreadDetail(BaseModel):
    id: UUID
    teacher_id: UUID
    teacher_name: str
    student_id: UUID
    student_name: str
    subject: str
    created_at: datetime
    messages: List[MessageItem]


class CreateThreadRequest(BaseModel):
    teacher_id: UUID
    student_id: UUID
    subject: str = Field(..., min_length=3, max_length=255)
    first_message: str = Field(..., min_length=1)


class ReplyRequest(BaseModel):
    body: str = Field(..., min_length=1)


# ─── Admin ────────────────────────────────────────────────────────────────────

class ChildLinkInput(BaseModel):
    student_id: UUID
    relation: str = Field(..., pattern="^(father|mother|guardian)$")
    is_primary: bool = False


class CreateParentRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    phone: Optional[str] = None
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)
    children: List[ChildLinkInput] = Field(..., min_length=1)

    @model_validator(mode="after")
    def passwords_must_match(self) -> "CreateParentRequest":
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match")
        return self


class UpdateParentRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8)
    confirm_password: Optional[str] = Field(None, min_length=8)
    children: Optional[List[ChildLinkInput]] = None

    @model_validator(mode="after")
    def validate_optional_passwords(self) -> "UpdateParentRequest":
        if self.password is None and self.confirm_password is None:
            return self
        if not self.password or not self.confirm_password:
            raise ValueError("Both password and confirm_password are required when updating password")
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match")
        return self


class AdminResetParentPasswordRequest(BaseModel):
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)

    @model_validator(mode="after")
    def passwords_must_match(self) -> "AdminResetParentPasswordRequest":
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match")
        return self


class ParentListItem(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    children: List[ChildSummary]
    created_at: datetime


class ParentDetail(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: Optional[str] = None
    is_active: bool
    children: List[ChildSummary]
    created_at: datetime
    last_login: Optional[datetime] = None


class CreateParentResponse(BaseModel):
    parent_id: UUID
    invite_sent: bool
    invite_token: Optional[str] = None


class BulkImportRow(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None
    student_admission_number: str
    relation: str
    is_primary: bool = False


class BulkImportResponse(BaseModel):
    created: int
    failed: List[Dict[str, Any]]


# Forward references
ParentLoginResponse.model_rebuild()
ChildSummaryCard.model_rebuild()
