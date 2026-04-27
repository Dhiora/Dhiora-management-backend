"""Parent-facing endpoints. All routes under /api/v1/parent/."""

from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from app.api.v1.grades import service as grades_service
from app.api.v1.grades.schemas import ExamGradeSummary, ReportCard

from . import service
from .models import Parent
from .schemas import (
    AssessmentParentItem,
    AssessmentParentResult,
    AttendanceRecord,
    CreateThreadRequest,
    FeeAssignmentParentView,
    FeePayVerifyRequest,
    FeePayVerifyResponse,
    HomeworkParentDetail,
    HomeworkParentItem,
    MeResponse,
    MonthlyAttendanceResponse,
    NotificationItem,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    ParentLoginRequest,
    ParentLoginResponse,
    ParentUpdateRequest,
    PaymentHistoryItem,
    RazorpayOrderResponse,
    ReplyRequest,
    StudentDetail,
    ThreadDetail,
    ThreadPreview,
    WeeklyTimetable,
)

router = APIRouter(prefix="/api/v1/parent", tags=["parent-portal"])


# ─── Dependency: get authenticated Parent record ───────────────────────────────

async def get_current_parent(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Parent:
    if current_user.role != "PARENT":
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Parent access only")
    parent = await service._get_parent_by_user_id(db, current_user.id)
    if not parent or not parent.is_active:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Parent account not found or inactive")
    return parent


async def _assert_child(
    student_id: UUID,
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    """Returns student_id after validating the link. Use as Depends()."""
    try:
        await service.assert_child_access(db, parent.id, student_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return student_id


def _raise(e: ServiceError) -> None:
    raise HTTPException(status_code=e.status_code, detail=e.message)


# ─── Auth ─────────────────────────────────────────────────────────────────────

@router.post("/auth/login", response_model=ParentLoginResponse, summary="Parent login")
async def parent_login(payload: ParentLoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await service.parent_login(db, payload.email, payload.password)
    except ServiceError as e:
        _raise(e)


# ─── Profile ─────────────────────────────────────────────────────────────────

@router.get("/me", response_model=MeResponse, summary="Parent profile + linked children")
async def get_me(
    parent: Parent = Depends(get_current_parent),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_me(db, parent, current_user.academic_year_id)


@router.put("/me", response_model=dict, summary="Update parent contact info")
async def update_me(
    payload: ParentUpdateRequest,
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        updated = await service.update_me(db, parent, payload.phone, payload.email)
        return updated.model_dump()
    except ServiceError as e:
        _raise(e)


# ─── Children ─────────────────────────────────────────────────────────────────

@router.get("/children", response_model=MeResponse, summary="List linked children")
async def list_children(
    parent: Parent = Depends(get_current_parent),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_me(db, parent, current_user.academic_year_id)


@router.get("/children/{student_id}", response_model=StudentDetail, summary="Child profile")
async def get_child_profile(
    student_id: UUID = Path(...),
    parent: Parent = Depends(get_current_parent),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        return await service.get_student_detail(db, student_id, current_user.academic_year_id)
    except ServiceError as e:
        _raise(e)


@router.get("/children/{student_id}/summary", summary="Dashboard summary card for one child")
async def get_child_summary(
    student_id: UUID = Path(...),
    parent: Parent = Depends(get_current_parent),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        return await service.get_child_summary_card(
            db, student_id, parent.tenant_id, current_user.academic_year_id
        )
    except ServiceError as e:
        _raise(e)


# ─── Attendance ───────────────────────────────────────────────────────────────

@router.get(
    "/children/{student_id}/attendance",
    response_model=MonthlyAttendanceResponse,
    summary="Monthly attendance records",
)
async def get_attendance(
    student_id: UUID = Path(...),
    month: int = Query(default=None, ge=1, le=12),
    year: int = Query(default=None, ge=2000),
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        today = date.today()
        m = month or today.month
        y = year or today.year
        return await service.get_monthly_attendance(db, student_id, m, y)
    except ServiceError as e:
        _raise(e)


@router.get(
    "/children/{student_id}/attendance/stats",
    summary="Attendance statistics for a month",
)
async def get_attendance_stats(
    student_id: UUID = Path(...),
    month: int = Query(default=None, ge=1, le=12),
    year: int = Query(default=None, ge=2000),
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        today = date.today()
        m = month or today.month
        y = year or today.year
        return await service.get_attendance_stats(db, student_id, m, y)
    except ServiceError as e:
        _raise(e)


@router.get(
    "/children/{student_id}/attendance/{attendance_date}",
    response_model=Optional[AttendanceRecord],
    summary="Attendance for a specific date",
)
async def get_attendance_by_date(
    student_id: UUID = Path(...),
    attendance_date: date = Path(...),
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        record = await service.get_single_day_attendance(db, student_id, attendance_date)
        if record is None:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="No attendance record for this date")
        return record
    except ServiceError as e:
        _raise(e)


# ─── Fees ────────────────────────────────────────────────────────────────────

@router.get(
    "/children/{student_id}/fees",
    response_model=List[FeeAssignmentParentView],
    summary="All fee assignments",
)
async def get_all_fees(
    student_id: UUID = Path(...),
    parent: Parent = Depends(get_current_parent),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        return await service.get_all_fees(db, parent.tenant_id, student_id, current_user.academic_year_id)
    except ServiceError as e:
        _raise(e)


@router.get(
    "/children/{student_id}/fees/pending",
    response_model=List[FeeAssignmentParentView],
    summary="Pending / overdue fees only",
)
async def get_pending_fees(
    student_id: UUID = Path(...),
    parent: Parent = Depends(get_current_parent),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        return await service.get_pending_fees(db, parent.tenant_id, student_id, current_user.academic_year_id)
    except ServiceError as e:
        _raise(e)


@router.get(
    "/children/{student_id}/fees/history",
    response_model=List[PaymentHistoryItem],
    summary="Paid fee history",
)
async def get_fee_history(
    student_id: UUID = Path(...),
    parent: Parent = Depends(get_current_parent),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        return await service.get_fee_history(db, parent.tenant_id, student_id, current_user.academic_year_id)
    except ServiceError as e:
        _raise(e)


@router.post(
    "/children/{student_id}/fees/pay",
    response_model=RazorpayOrderResponse,
    summary="Create Razorpay order for fee payment",
)
async def initiate_fee_payment(
    student_id: UUID = Path(...),
    fee_assignment_id: UUID = Query(...),
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        result = await service.create_razorpay_order(db, parent.tenant_id, student_id, fee_assignment_id)
        return RazorpayOrderResponse(**result)
    except ServiceError as e:
        _raise(e)


@router.post(
    "/children/{student_id}/fees/pay/verify",
    response_model=FeePayVerifyResponse,
    summary="Verify Razorpay payment and mark fee paid",
)
async def verify_fee_payment(
    student_id: UUID = Path(...),
    payload: FeePayVerifyRequest = ...,
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        result = await service.verify_razorpay_payment(
            db,
            parent.tenant_id,
            student_id,
            payload.fee_assignment_id,
            payload.razorpay_order_id,
            payload.razorpay_payment_id,
            payload.razorpay_signature,
        )
        return FeePayVerifyResponse(**result)
    except ServiceError as e:
        _raise(e)


@router.get(
    "/children/{student_id}/fees/receipt/{payment_id}",
    summary="Fetch fee payment receipt details",
)
async def get_fee_receipt(
    student_id: UUID = Path(...),
    payment_id: UUID = Path(...),
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        return await service.get_payment_receipt_payload(
            db, parent.tenant_id, student_id, payment_id
        )
    except ServiceError as e:
        _raise(e)


# ─── Homework ─────────────────────────────────────────────────────────────────

@router.get(
    "/children/{student_id}/homework",
    response_model=List[HomeworkParentItem],
    summary="Homework list for child",
)
async def get_homework(
    student_id: UUID = Path(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    parent: Parent = Depends(get_current_parent),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        ay_id = current_user.academic_year_id
        sar = None
        if ay_id:
            sar = await service._get_student_record(db, student_id, ay_id)
        class_id = sar.class_id if sar else None
        section_id = sar.section_id if sar else None
        return await service.get_homework_list(db, student_id, class_id, section_id, ay_id, status_filter)
    except ServiceError as e:
        _raise(e)


@router.get(
    "/children/{student_id}/homework/{assignment_id}",
    response_model=HomeworkParentDetail,
    summary="Homework detail (no questions)",
)
async def get_homework_detail(
    student_id: UUID = Path(...),
    assignment_id: UUID = Path(...),
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        return await service.get_homework_detail(db, student_id, assignment_id)
    except ServiceError as e:
        _raise(e)


# ─── Assessments ─────────────────────────────────────────────────────────────

@router.get(
    "/children/{student_id}/assessments",
    response_model=List[AssessmentParentItem],
    summary="Online assessment list for child",
)
async def get_assessments(
    student_id: UUID = Path(...),
    parent: Parent = Depends(get_current_parent),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        ay_id = current_user.academic_year_id
        sar = None
        if ay_id:
            sar = await service._get_student_record(db, student_id, ay_id)
        class_id = sar.class_id if sar else None
        section_id = sar.section_id if sar else None
        return await service.get_assessments(db, parent.tenant_id, student_id, class_id, section_id, ay_id)
    except ServiceError as e:
        _raise(e)


@router.get(
    "/children/{student_id}/assessments/{assessment_id}/result",
    response_model=AssessmentParentResult,
    summary="Assessment result for child",
)
async def get_assessment_result(
    student_id: UUID = Path(...),
    assessment_id: UUID = Path(...),
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        return await service.get_assessment_result(db, parent.tenant_id, student_id, assessment_id)
    except ServiceError as e:
        _raise(e)


def _stub_503():
    raise HTTPException(
        status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="This feature is coming soon.",
    )


# ─── Exams & Grades ───────────────────────────────────────────────────────────

@router.get(
    "/children/{student_id}/grades",
    response_model=List[ExamGradeSummary],
    summary="List all exams with grade summary for a child",
)
async def get_grades(
    student_id: UUID = Path(...),
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        return await grades_service.get_parent_student_exam_list(db, parent.tenant_id, student_id)
    except ServiceError as e:
        _raise(e)


@router.get(
    "/children/{student_id}/grades/{exam_id}",
    response_model=ReportCard,
    summary="Grades for a child for a specific exam",
)
async def get_exam_grades(
    student_id: UUID = Path(...),
    exam_id: UUID = Path(...),
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        return await grades_service.get_parent_student_report_card(db, parent.tenant_id, student_id, exam_id)
    except ServiceError as e:
        _raise(e)


@router.get(
    "/children/{student_id}/report-card/{exam_id}",
    response_model=ReportCard,
    summary="Full report card for a child for a specific exam",
)
async def get_report_card(
    student_id: UUID = Path(...),
    exam_id: UUID = Path(...),
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        return await grades_service.get_parent_student_report_card(db, parent.tenant_id, student_id, exam_id)
    except ServiceError as e:
        _raise(e)


# ─── Timetable ────────────────────────────────────────────────────────────────

@router.get(
    "/children/{student_id}/timetable",
    response_model=WeeklyTimetable,
    summary="Weekly timetable for child's class",
)
async def get_timetable(
    student_id: UUID = Path(...),
    parent: Parent = Depends(get_current_parent),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        ay_id = current_user.academic_year_id
        sar = None
        if ay_id:
            sar = await service._get_student_record(db, student_id, ay_id)
        class_id = sar.class_id if sar else None
        section_id = sar.section_id if sar else None
        return await service.get_weekly_timetable(db, parent.tenant_id, class_id, section_id, ay_id)
    except ServiceError as e:
        _raise(e)


@router.get(
    "/children/{student_id}/timetable/{day}",
    summary="Single day timetable",
)
async def get_timetable_day(
    student_id: UUID = Path(...),
    day: str = Path(..., pattern="^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$"),
    parent: Parent = Depends(get_current_parent),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, student_id)
        ay_id = current_user.academic_year_id
        sar = None
        if ay_id:
            sar = await service._get_student_record(db, student_id, ay_id)
        class_id = sar.class_id if sar else None
        section_id = sar.section_id if sar else None
        weekly = await service.get_weekly_timetable(db, parent.tenant_id, class_id, section_id, ay_id)
        return getattr(weekly, day)
    except ServiceError as e:
        _raise(e)


# ─── Notifications ────────────────────────────────────────────────────────────

@router.get(
    "/notifications",
    response_model=List[NotificationItem],
    summary="Parent notifications",
)
async def get_notifications(
    is_read: Optional[bool] = Query(None),
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_notifications(db, parent.id, is_read)


@router.put("/notifications/{notification_id}/read", summary="Mark one notification read")
async def mark_read(
    notification_id: UUID = Path(...),
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.mark_notification_read(db, parent.id, notification_id)
        return {"success": True}
    except ServiceError as e:
        _raise(e)


@router.put("/notifications/read-all", summary="Mark all notifications read")
async def mark_all_read(
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    await service.mark_all_read(db, parent.id)
    return {"success": True}


@router.get(
    "/notifications/preferences",
    response_model=NotificationPreferenceResponse,
    summary="Get notification preferences",
)
async def get_preferences(
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_notification_preferences(db, parent.id)


@router.put(
    "/notifications/preferences",
    response_model=NotificationPreferenceResponse,
    summary="Update notification preferences",
)
async def update_preferences(
    payload: NotificationPreferenceUpdate,
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_notification_preferences(db, parent.id, payload)


@router.get("/circulars", summary="[STUB] School circulars")
async def get_circulars(parent: Parent = Depends(get_current_parent)):
    _stub_503()


@router.get("/circulars/{circular_id}", summary="[STUB] Circular detail")
async def get_circular(circular_id: UUID = Path(...), parent: Parent = Depends(get_current_parent)):
    _stub_503()


# ─── Messaging ────────────────────────────────────────────────────────────────

@router.get(
    "/messages",
    response_model=List[ThreadPreview],
    summary="List message threads",
)
async def list_threads(
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_message_threads(db, parent.id)


@router.get(
    "/messages/{thread_id}",
    response_model=ThreadDetail,
    summary="Thread messages (marks teacher messages as read)",
)
async def get_thread(
    thread_id: UUID = Path(...),
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.get_thread_detail(db, parent.id, thread_id)
    except ServiceError as e:
        _raise(e)


@router.post(
    "/messages",
    response_model=ThreadDetail,
    status_code=http_status.HTTP_201_CREATED,
    summary="Start a new message thread with a teacher",
)
async def create_thread(
    payload: CreateThreadRequest,
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.assert_child_access(db, parent.id, payload.student_id)
        return await service.create_thread(
            db, parent.tenant_id, parent,
            payload.teacher_id, payload.student_id,
            payload.subject, payload.first_message,
        )
    except ServiceError as e:
        _raise(e)


@router.post(
    "/messages/{thread_id}/reply",
    summary="Reply in a thread",
)
async def reply_thread(
    thread_id: UUID = Path(...),
    payload: ReplyRequest = ...,
    parent: Parent = Depends(get_current_parent),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.reply_to_thread(db, parent.id, thread_id, payload.body)
    except ServiceError as e:
        _raise(e)
