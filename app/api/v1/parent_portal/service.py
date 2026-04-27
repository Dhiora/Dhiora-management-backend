"""Parent Portal service layer. All reads are tenant-scoped and child-link validated."""

import calendar
import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import status
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import PasswordResetToken, RefreshToken, User
from app.auth.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.core.config import settings
from app.core.exceptions import ServiceError
from app.core.models import AcademicYear, Tenant, TenantModule
from app.core.models.class_fee_structure import ClassFeeStructure
from app.core.models.class_model import SchoolClass
from app.core.models.fee_component import FeeComponent
from app.core.models.homework import Homework, HomeworkAssignment, HomeworkAttempt, HomeworkSubmission
from app.core.models.online_assessment import AssessmentAttempt, OnlineAssessment
from app.core.models.payment_transaction import PaymentTransaction
from app.core.models.section_model import Section
from app.core.models.student_academic_record import StudentAcademicRecord
from app.core.models.student_daily_attendance import StudentDailyAttendance, StudentDailyAttendanceRecord
from app.core.models.student_fee_assignment import StudentFeeAssignment
from app.core.models.subject import Subject as SchoolSubject
from app.core.models.time_slot import TimeSlot
from app.core.models.timetable import Timetable
from app.core.models.class_teacher_assignment import ClassTeacherAssignment

from .models import (
    Message,
    MessageThread,
    NotificationPreference,
    Parent,
    ParentNotification,
    ParentStudentLink,
)
from .schemas import (
    AssessmentParentItem,
    AssessmentParentResult,
    AttendanceRecord,
    AttendanceStats,
    BulkImportRow,
    ChildLinkInput,
    ChildSummary,
    CreateParentRequest,
    CreateParentResponse,
    FeeAssignmentParentView,
    FeesPendingSummary,
    HomeworkParentDetail,
    HomeworkParentItem,
    MessageItem,
    MonthlyAttendanceResponse,
    NextExam,
    NotificationItem,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    ParentDetail,
    ParentListItem,
    ParentProfile,
    PaymentHistoryItem,
    ReplyRequest,
    StudentDetail,
    ThreadDetail,
    ThreadPreview,
    TimetableSlot,
    UpdateParentRequest,
    WeeklyTimetable,
)

_DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _to_uuid(val) -> Optional[UUID]:
    if val is None:
        return None
    return val if isinstance(val, UUID) else UUID(str(val))


async def _get_active_academic_year(db: AsyncSession, tenant_id: UUID) -> Optional[AcademicYear]:
    result = await db.execute(
        select(AcademicYear).where(
            AcademicYear.tenant_id == tenant_id,
            AcademicYear.is_current.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def _get_student_record(
    db: AsyncSession, student_id: UUID, academic_year_id: UUID
) -> Optional[StudentAcademicRecord]:
    result = await db.execute(
        select(StudentAcademicRecord).where(
            StudentAcademicRecord.student_id == student_id,
            StudentAcademicRecord.academic_year_id == academic_year_id,
            StudentAcademicRecord.status == "ACTIVE",
        )
    )
    return result.scalar_one_or_none()


async def _get_parent_by_user_id(db: AsyncSession, user_id: UUID) -> Optional[Parent]:
    result = await db.execute(
        select(Parent).where(Parent.user_id == user_id, Parent.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def _get_parent_by_id(db: AsyncSession, parent_id: UUID, tenant_id: UUID) -> Optional[Parent]:
    result = await db.execute(
        select(Parent).where(Parent.id == parent_id, Parent.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def assert_child_access(db: AsyncSession, parent_id: UUID, student_id: UUID) -> None:
    """Raises 403 if student is not linked to this parent."""
    result = await db.execute(
        select(ParentStudentLink).where(
            ParentStudentLink.parent_id == parent_id,
            ParentStudentLink.student_id == student_id,
        )
    )
    if not result.scalar_one_or_none():
        raise ServiceError("Child not linked to this parent", status.HTTP_403_FORBIDDEN)


async def _build_child_summaries(
    db: AsyncSession, parent_id: UUID, ay_id: Optional[UUID]
) -> List[ChildSummary]:
    links_result = await db.execute(
        select(ParentStudentLink).where(ParentStudentLink.parent_id == parent_id)
    )
    links = links_result.scalars().all()
    summaries = []
    for link in links:
        student = await db.get(User, link.student_id)
        if not student:
            continue
        class_name, section_name, roll_number = None, None, None
        if ay_id:
            sar = await _get_student_record(db, link.student_id, ay_id)
            if sar:
                sc = await db.get(SchoolClass, sar.class_id)
                sec = await db.get(Section, sar.section_id)
                class_name = sc.name if sc else None
                section_name = sec.name if sec else None
                roll_number = sar.roll_number
        summaries.append(
            ChildSummary(
                student_id=link.student_id,
                full_name=student.full_name,
                class_name=class_name,
                section_name=section_name,
                roll_number=roll_number,
                relation=link.relation,
                is_primary=link.is_primary,
            )
        )
    return summaries


# ─── Auth ─────────────────────────────────────────────────────────────────────

async def parent_login(db: AsyncSession, email: str, password: str):
    from .schemas import ParentLoginResponse

    user_result = await db.execute(
        select(User).where(func.lower(User.email) == func.lower(email))
    )
    user: Optional[User] = user_result.scalars().first()
    if not user or user.user_type != "parent":
        raise ServiceError("Invalid credentials", status.HTTP_401_UNAUTHORIZED)
    if not verify_password(password, user.password_hash):
        raise ServiceError("Invalid credentials", status.HTTP_401_UNAUTHORIZED)
    if user.status != "ACTIVE":
        raise ServiceError("Account is inactive", status.HTTP_403_FORBIDDEN)

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant: Optional[Tenant] = tenant_result.scalar_one_or_none()
    if not tenant or tenant.status != "ACTIVE":
        raise ServiceError("Tenant not found or inactive", status.HTTP_403_FORBIDDEN)

    parent = await _get_parent_by_user_id(db, user.id)
    if not parent:
        raise ServiceError("Parent record not found", status.HTTP_403_FORBIDDEN)

    ay = await _get_active_academic_year(db, user.tenant_id)

    modules_result = await db.execute(
        select(TenantModule.module_key).where(
            TenantModule.tenant_id == tenant.id,
            TenantModule.is_enabled.is_(True),
        )
    )
    modules = [r[0] for r in modules_result.all()]

    issued_at = datetime.now(timezone.utc)
    access_payload = {
        "sub": str(user.id),
        "user_id": str(user.id),
        "tenant_id": str(user.tenant_id),
        "organization_code": tenant.organization_code,
        "role": "PARENT",
        "parent_id": str(parent.id),
        "modules": modules,
        "permissions": {},
        "academic_year_id": str(ay.id) if ay else None,
        "academic_year_status": ay.status if ay else None,
        "iat": int(issued_at.timestamp()),
    }
    access_token = create_access_token(
        subject=access_payload,
        expires_minutes=settings.parent_jwt_expiry_minutes,
    )
    refresh_token_str, refresh_expires_at = create_refresh_token()

    db.add(RefreshToken(user_id=user.id, token=refresh_token_str, expires_at=refresh_expires_at))
    await db.commit()

    children = await _build_child_summaries(db, parent.id, ay.id if ay else None)
    return ParentLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        parent_id=parent.id,
        linked_children=children,
    )


async def parent_refresh_token(db: AsyncSession, refresh_token: str):
    from .schemas import ParentRefreshResponse

    token_result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == refresh_token)
    )
    token_row = token_result.scalar_one_or_none()
    if not token_row:
        raise ServiceError("Invalid refresh token", status.HTTP_401_UNAUTHORIZED)
    if token_row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise ServiceError("Refresh token expired", status.HTTP_401_UNAUTHORIZED)

    user = await db.get(User, token_row.user_id)
    if not user or user.status != "ACTIVE" or user.user_type != "parent":
        raise ServiceError("Parent account not found or inactive", status.HTTP_403_FORBIDDEN)

    parent = await _get_parent_by_user_id(db, user.id)
    if not parent:
        raise ServiceError("Parent record not found", status.HTTP_403_FORBIDDEN)

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant or tenant.status != "ACTIVE":
        raise ServiceError("Tenant not found or inactive", status.HTTP_403_FORBIDDEN)

    ay = await _get_active_academic_year(db, user.tenant_id)
    modules_result = await db.execute(
        select(TenantModule.module_key).where(
            TenantModule.tenant_id == tenant.id,
            TenantModule.is_enabled.is_(True),
        )
    )
    modules = [r[0] for r in modules_result.all()]

    issued_at = datetime.now(timezone.utc)
    access_payload = {
        "sub": str(user.id),
        "user_id": str(user.id),
        "tenant_id": str(user.tenant_id),
        "organization_code": tenant.organization_code,
        "role": "PARENT",
        "parent_id": str(parent.id),
        "modules": modules,
        "permissions": {},
        "academic_year_id": str(ay.id) if ay else None,
        "academic_year_status": ay.status if ay else None,
        "iat": int(issued_at.timestamp()),
    }
    access_token = create_access_token(
        subject=access_payload,
        expires_minutes=settings.parent_jwt_expiry_minutes,
    )
    return ParentRefreshResponse(access_token=access_token)


async def parent_forgot_password(db: AsyncSession, email: str) -> dict:
    user_result = await db.execute(
        select(User).where(func.lower(User.email) == func.lower(email))
    )
    user = user_result.scalar_one_or_none()
    if not user or user.user_type != "parent":
        raise ServiceError("No parent account found with this email", status.HTTP_404_NOT_FOUND)

    existing_result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    )
    for old_token in existing_result.scalars().all():
        await db.delete(old_token)

    raw_token = secrets.token_urlsafe(48)
    expiry_hours = getattr(settings, "parent_invite_token_expiry_hours", 48)
    reset_token = PasswordResetToken(
        user_id=user.id,
        token=raw_token,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
    )
    db.add(reset_token)
    await db.commit()
    return {"message": "Password reset token generated", "reset_token": raw_token}


async def parent_reset_password(db: AsyncSession, token: str, new_password: str) -> dict:
    token_result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == token)
    )
    reset_token = token_result.scalar_one_or_none()
    if not reset_token or reset_token.used_at is not None:
        raise ServiceError("Invalid or used reset token", status.HTTP_400_BAD_REQUEST)
    if reset_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise ServiceError("Reset token expired", status.HTTP_400_BAD_REQUEST)

    user = await db.get(User, reset_token.user_id)
    if not user or user.user_type != "parent":
        raise ServiceError("Parent account not found", status.HTTP_404_NOT_FOUND)

    user.password_hash = hash_password(new_password)
    reset_token.used_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Password reset successful"}


# ─── Profile ─────────────────────────────────────────────────────────────────

async def get_me(db: AsyncSession, parent: Parent, ay_id: Optional[UUID]):
    from .schemas import MeResponse

    children = await _build_child_summaries(db, parent.id, ay_id)
    return MeResponse(
        parent=ParentProfile(id=parent.id, full_name=parent.full_name, phone=parent.phone, email=parent.email),
        children=children,
    )


async def update_me(db: AsyncSession, parent: Parent, phone: Optional[str], email: Optional[str]) -> ParentProfile:
    if phone is not None:
        parent.phone = phone
    if email is not None:
        existing = await db.execute(
            select(Parent).where(
                Parent.tenant_id == parent.tenant_id,
                func.lower(Parent.email) == func.lower(email),
                Parent.id != parent.id,
            )
        )
        if existing.scalar_one_or_none():
            raise ServiceError("Email already in use", status.HTTP_409_CONFLICT)
        parent.email = email
    await db.commit()
    await db.refresh(parent)
    return ParentProfile(id=parent.id, full_name=parent.full_name, phone=parent.phone, email=parent.email)


# ─── Student detail ──────────────────────────────────────────────────────────

async def get_student_detail(db: AsyncSession, student_id: UUID, ay_id: Optional[UUID]) -> StudentDetail:
    student = await db.get(User, student_id)
    if not student:
        raise ServiceError("Student not found", status.HTTP_404_NOT_FOUND)

    class_name, section_name, roll_number, ay_name = None, None, None, None
    if ay_id:
        sar = await _get_student_record(db, student_id, ay_id)
        if sar:
            sc = await db.get(SchoolClass, sar.class_id)
            sec = await db.get(Section, sar.section_id)
            ay = await db.get(AcademicYear, ay_id)
            class_name = sc.name if sc else None
            section_name = sec.name if sec else None
            roll_number = sar.roll_number
            ay_name = ay.name if ay else None

    return StudentDetail(
        id=student.id,
        full_name=student.full_name,
        email=student.email,
        mobile=student.mobile,
        roll_number=roll_number,
        class_name=class_name,
        section_name=section_name,
        academic_year_name=ay_name,
    )


async def get_child_summary_card(
    db: AsyncSession,
    student_id: UUID,
    tenant_id: UUID,
    ay_id: Optional[UUID],
) -> dict:
    student = await db.get(User, student_id)
    class_name, section_name = None, None
    class_id, section_id = None, None

    if ay_id:
        sar = await _get_student_record(db, student_id, ay_id)
        if sar:
            sc = await db.get(SchoolClass, sar.class_id)
            sec = await db.get(Section, sar.section_id)
            class_name = sc.name if sc else None
            section_name = sec.name if sec else None
            class_id = sar.class_id
            section_id = sar.section_id

    # Attendance this month
    today = date.today()
    att_stats = await get_attendance_stats(db, student_id, today.month, today.year)

    # Pending fees
    pending_fees = await _count_pending_fees(db, tenant_id, student_id, ay_id)

    # Pending homework
    hw_count = await _count_pending_homework(db, student_id, class_id, section_id, ay_id)

    return {
        "student_id": student_id,
        "full_name": student.full_name if student else "",
        "class_name": class_name,
        "section_name": section_name,
        "attendance_this_month": att_stats,
        "fees_pending": pending_fees,
        "homework_pending": hw_count,
        "next_exam": None,
    }


async def _count_pending_fees(
    db: AsyncSession, tenant_id: UUID, student_id: UUID, ay_id: Optional[UUID]
) -> FeesPendingSummary:
    stmt = select(StudentFeeAssignment).where(
        StudentFeeAssignment.tenant_id == tenant_id,
        StudentFeeAssignment.student_id == student_id,
        StudentFeeAssignment.is_active.is_(True),
        StudentFeeAssignment.status.in_(["unpaid", "partial"]),
    )
    if ay_id:
        stmt = stmt.where(StudentFeeAssignment.academic_year_id == ay_id)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    total = sum(r.final_amount or Decimal("0") for r in rows)
    return FeesPendingSummary(count=len(rows), total_amount=total)


async def _count_pending_homework(
    db: AsyncSession,
    student_id: UUID,
    class_id: Optional[UUID],
    section_id: Optional[UUID],
    ay_id: Optional[UUID],
) -> int:
    if not class_id or not ay_id:
        return 0
    now = datetime.utcnow()
    stmt = (
        select(func.count(HomeworkAssignment.id))
        .join(Homework, HomeworkAssignment.homework_id == Homework.id)
        .where(
            HomeworkAssignment.academic_year_id == ay_id,
            HomeworkAssignment.class_id == class_id,
            HomeworkAssignment.due_date >= now,
            Homework.status == "PUBLISHED",
        )
    )
    if section_id:
        stmt = stmt.where(
            (HomeworkAssignment.section_id == section_id) | (HomeworkAssignment.section_id.is_(None))
        )
    total_result = await db.execute(stmt)
    total = total_result.scalar() or 0

    submitted_stmt = (
        select(func.count(HomeworkAttempt.id))
        .join(HomeworkAssignment, HomeworkAttempt.homework_assignment_id == HomeworkAssignment.id)
        .join(Homework, HomeworkAssignment.homework_id == Homework.id)
        .where(
            HomeworkAttempt.student_id == student_id,
            HomeworkAttempt.completed_at.isnot(None),
            HomeworkAssignment.academic_year_id == ay_id,
            HomeworkAssignment.class_id == class_id,
            HomeworkAssignment.due_date >= now,
            Homework.status == "PUBLISHED",
        )
    )
    submitted_result = await db.execute(submitted_stmt)
    submitted = submitted_result.scalar() or 0
    return max(0, total - submitted)


# ─── Attendance ───────────────────────────────────────────────────────────────

async def get_monthly_attendance(
    db: AsyncSession, student_id: UUID, month: int, year: int
) -> MonthlyAttendanceResponse:
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    result = await db.execute(
        select(StudentDailyAttendanceRecord, StudentDailyAttendance)
        .join(StudentDailyAttendance, StudentDailyAttendanceRecord.daily_attendance_id == StudentDailyAttendance.id)
        .where(
            StudentDailyAttendanceRecord.student_id == student_id,
            StudentDailyAttendance.attendance_date >= start,
            StudentDailyAttendance.attendance_date <= end,
        )
        .order_by(StudentDailyAttendance.attendance_date)
    )
    rows = result.all()

    records = []
    present = absent = late = 0
    for rec, master in rows:
        records.append(AttendanceRecord(
            date=master.attendance_date,
            status=rec.status,
            marked_at=master.created_at,
        ))
        s = rec.status
        if s == "PRESENT":
            present += 1
        elif s == "ABSENT":
            absent += 1
        elif s == "LATE":
            late += 1

    total = len(records)
    pct = round((present / total * 100), 1) if total > 0 else 0.0
    stats = AttendanceStats(total_days=total, present=present, absent=absent, late=late, percentage=pct)
    return MonthlyAttendanceResponse(month=month, year=year, records=records, stats=stats)


async def get_attendance_stats(db: AsyncSession, student_id: UUID, month: int, year: int) -> AttendanceStats:
    resp = await get_monthly_attendance(db, student_id, month, year)
    return resp.stats


async def get_single_day_attendance(
    db: AsyncSession, student_id: UUID, attendance_date: date
) -> Optional[AttendanceRecord]:
    result = await db.execute(
        select(StudentDailyAttendanceRecord, StudentDailyAttendance)
        .join(StudentDailyAttendance, StudentDailyAttendanceRecord.daily_attendance_id == StudentDailyAttendance.id)
        .where(
            StudentDailyAttendanceRecord.student_id == student_id,
            StudentDailyAttendance.attendance_date == attendance_date,
        )
    )
    row = result.first()
    if not row:
        return None
    rec, master = row
    return AttendanceRecord(date=master.attendance_date, status=rec.status, marked_at=master.created_at)


# ─── Fees ────────────────────────────────────────────────────────────────────

async def _fee_assignment_view(db: AsyncSession, fa: StudentFeeAssignment) -> FeeAssignmentParentView:
    fee_name = "Fee"
    if fa.class_fee_structure_id:
        cfs = await db.get(ClassFeeStructure, fa.class_fee_structure_id)
        if cfs:
            comp = await db.get(FeeComponent, cfs.fee_component_id)
            fee_name = comp.name if comp else fee_name
            due_date = cfs.due_date
        else:
            due_date = None
    else:
        fee_name = fa.custom_name or fee_name
        due_date = None

    paid_result = await db.execute(
        select(func.coalesce(func.sum(PaymentTransaction.amount_paid), 0)).where(
            PaymentTransaction.student_fee_assignment_id == fa.id,
            PaymentTransaction.payment_status == "success",
        )
    )
    amount_paid = Decimal(str(paid_result.scalar() or 0))
    balance = (fa.final_amount or Decimal("0")) - amount_paid

    return FeeAssignmentParentView(
        id=fa.id,
        fee_name=fee_name,
        base_amount=fa.base_amount or Decimal("0"),
        total_discount=fa.total_discount or Decimal("0"),
        final_amount=fa.final_amount or Decimal("0"),
        amount_paid=amount_paid,
        balance=balance,
        status=fa.status,
        due_date=due_date,
    )


async def get_all_fees(
    db: AsyncSession, tenant_id: UUID, student_id: UUID, ay_id: Optional[UUID]
) -> List[FeeAssignmentParentView]:
    stmt = select(StudentFeeAssignment).where(
        StudentFeeAssignment.tenant_id == tenant_id,
        StudentFeeAssignment.student_id == student_id,
        StudentFeeAssignment.is_active.is_(True),
    )
    if ay_id:
        stmt = stmt.where(StudentFeeAssignment.academic_year_id == ay_id)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [await _fee_assignment_view(db, fa) for fa in rows]


async def get_pending_fees(
    db: AsyncSession, tenant_id: UUID, student_id: UUID, ay_id: Optional[UUID]
) -> List[FeeAssignmentParentView]:
    stmt = select(StudentFeeAssignment).where(
        StudentFeeAssignment.tenant_id == tenant_id,
        StudentFeeAssignment.student_id == student_id,
        StudentFeeAssignment.is_active.is_(True),
        StudentFeeAssignment.status.in_(["unpaid", "partial"]),
    )
    if ay_id:
        stmt = stmt.where(StudentFeeAssignment.academic_year_id == ay_id)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [await _fee_assignment_view(db, fa) for fa in rows]


async def get_fee_history(
    db: AsyncSession, tenant_id: UUID, student_id: UUID, ay_id: Optional[UUID]
) -> List[PaymentHistoryItem]:
    stmt = (
        select(PaymentTransaction, StudentFeeAssignment)
        .join(StudentFeeAssignment, PaymentTransaction.student_fee_assignment_id == StudentFeeAssignment.id)
        .where(
            PaymentTransaction.tenant_id == tenant_id,
            StudentFeeAssignment.student_id == student_id,
            PaymentTransaction.payment_status == "success",
        )
        .order_by(PaymentTransaction.paid_at.desc())
    )
    if ay_id:
        stmt = stmt.where(StudentFeeAssignment.academic_year_id == ay_id)
    result = await db.execute(stmt)
    rows = result.all()

    items = []
    for txn, fa in rows:
        fee_name = fa.custom_name or "Fee"
        if fa.class_fee_structure_id:
            cfs = await db.get(ClassFeeStructure, fa.class_fee_structure_id)
            if cfs:
                comp = await db.get(FeeComponent, cfs.fee_component_id)
                fee_name = comp.name if comp else fee_name
        items.append(PaymentHistoryItem(
            id=txn.id,
            fee_name=fee_name,
            amount_paid=txn.amount_paid,
            payment_mode=txn.payment_mode,
            transaction_reference=txn.transaction_reference,
            paid_at=txn.paid_at,
        ))
    return items


async def create_razorpay_order(
    db: AsyncSession, tenant_id: UUID, student_id: UUID, fee_assignment_id: UUID
) -> dict:
    from app.core.payments.razorpay_client import get_razorpay_client

    fa_result = await db.execute(
        select(StudentFeeAssignment).where(
            StudentFeeAssignment.id == fee_assignment_id,
            StudentFeeAssignment.tenant_id == tenant_id,
            StudentFeeAssignment.student_id == student_id,
            StudentFeeAssignment.is_active.is_(True),
        )
    )
    fa = fa_result.scalar_one_or_none()
    if not fa:
        raise ServiceError("Fee assignment not found", status.HTTP_404_NOT_FOUND)
    if fa.status == "paid":
        raise ServiceError("This fee has already been paid", status.HTTP_409_CONFLICT)

    paid_result = await db.execute(
        select(func.coalesce(func.sum(PaymentTransaction.amount_paid), 0)).where(
            PaymentTransaction.student_fee_assignment_id == fa.id,
            PaymentTransaction.payment_status == "success",
        )
    )
    amount_paid = Decimal(str(paid_result.scalar() or 0))
    balance = (fa.final_amount or Decimal("0")) - amount_paid
    if balance <= 0:
        raise ServiceError("No outstanding balance", status.HTTP_409_CONFLICT)

    rz = get_razorpay_client()
    amount_paise = int(balance * 100)
    order = rz.order.create({"amount": amount_paise, "currency": "INR", "payment_capture": 1})
    return {
        "razorpay_order_id": order["id"],
        "amount": amount_paise,
        "currency": "INR",
        "key_id": settings.razorpay_key_id,
        "fee_assignment_id": fee_assignment_id,
    }


async def verify_razorpay_payment(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    fee_assignment_id: UUID,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> dict:
    # Verify signature
    body = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected = hmac.new(
        settings.razorpay_key_secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, razorpay_signature):
        raise ServiceError("Invalid payment signature", status.HTTP_400_BAD_REQUEST)

    # Check idempotency
    existing = await db.execute(
        select(PaymentTransaction).where(
            PaymentTransaction.transaction_reference == razorpay_payment_id
        )
    )
    if existing.scalar_one_or_none():
        raise ServiceError("Payment already recorded", status.HTTP_409_CONFLICT)

    fa_result = await db.execute(
        select(StudentFeeAssignment).where(
            StudentFeeAssignment.id == fee_assignment_id,
            StudentFeeAssignment.tenant_id == tenant_id,
            StudentFeeAssignment.student_id == student_id,
        )
    )
    fa = fa_result.scalar_one_or_none()
    if not fa:
        raise ServiceError("Fee assignment not found", status.HTTP_404_NOT_FOUND)

    paid_result = await db.execute(
        select(func.coalesce(func.sum(PaymentTransaction.amount_paid), 0)).where(
            PaymentTransaction.student_fee_assignment_id == fa.id,
            PaymentTransaction.payment_status == "success",
        )
    )
    amount_paid_so_far = Decimal(str(paid_result.scalar() or 0))
    balance = (fa.final_amount or Decimal("0")) - amount_paid_so_far

    txn = PaymentTransaction(
        tenant_id=tenant_id,
        academic_year_id=fa.academic_year_id,
        student_fee_assignment_id=fa.id,
        amount_paid=balance,
        payment_mode="UPI",
        transaction_reference=razorpay_payment_id,
        payment_status="success",
        paid_at=datetime.utcnow(),
    )
    db.add(txn)

    new_paid = amount_paid_so_far + balance
    if new_paid >= (fa.final_amount or Decimal("0")):
        fa.status = "paid"
    else:
        fa.status = "partial"

    await db.commit()
    await db.refresh(txn)
    return {"success": True, "payment_id": txn.id}


async def get_payment_receipt_payload(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    payment_id: UUID,
) -> dict:
    result = await db.execute(
        select(PaymentTransaction, StudentFeeAssignment)
        .join(StudentFeeAssignment, PaymentTransaction.student_fee_assignment_id == StudentFeeAssignment.id)
        .where(
            PaymentTransaction.id == payment_id,
            PaymentTransaction.tenant_id == tenant_id,
            StudentFeeAssignment.student_id == student_id,
        )
    )
    row = result.first()
    if not row:
        raise ServiceError("Payment receipt not found", status.HTTP_404_NOT_FOUND)
    txn, fee = row
    return {
        "payment_id": txn.id,
        "student_fee_assignment_id": fee.id,
        "amount_paid": txn.amount_paid,
        "payment_mode": txn.payment_mode,
        "transaction_reference": txn.transaction_reference,
        "paid_at": txn.paid_at,
    }


# ─── Homework ─────────────────────────────────────────────────────────────────

async def get_homework_list(
    db: AsyncSession,
    student_id: UUID,
    class_id: Optional[UUID],
    section_id: Optional[UUID],
    ay_id: Optional[UUID],
    status_filter: Optional[str] = None,
) -> List[HomeworkParentItem]:
    if not class_id or not ay_id:
        return []

    stmt = (
        select(HomeworkAssignment, Homework)
        .join(Homework, HomeworkAssignment.homework_id == Homework.id)
        .where(
            HomeworkAssignment.academic_year_id == ay_id,
            HomeworkAssignment.class_id == class_id,
            Homework.status == "PUBLISHED",
        )
    )
    if section_id:
        stmt = stmt.where(
            (HomeworkAssignment.section_id == section_id) | (HomeworkAssignment.section_id.is_(None))
        )
    result = await db.execute(stmt.order_by(HomeworkAssignment.due_date.desc()))
    rows = result.all()

    items = []
    for assignment, hw in rows:
        attempt_result = await db.execute(
            select(HomeworkAttempt).where(
                HomeworkAttempt.homework_assignment_id == assignment.id,
                HomeworkAttempt.student_id == student_id,
            ).order_by(HomeworkAttempt.attempt_number.desc()).limit(1)
        )
        attempt = attempt_result.scalar_one_or_none()

        sub_status = "not_started"
        if attempt:
            if attempt.completed_at:
                sub_status = "submitted"
            else:
                sub_status = "in_progress"

        if status_filter and status_filter != sub_status:
            continue

        subject_name = None
        if assignment.subject_id:
            subj = await db.get(SchoolSubject, assignment.subject_id)
            subject_name = subj.name if subj else None

        items.append(HomeworkParentItem(
            homework_id=hw.id,
            assignment_id=assignment.id,
            title=hw.title,
            description=hw.description,
            subject_name=subject_name,
            due_date=assignment.due_date,
            submission_status=sub_status,
        ))
    return items


async def get_homework_detail(
    db: AsyncSession, student_id: UUID, assignment_id: UUID
) -> HomeworkParentDetail:
    result = await db.execute(
        select(HomeworkAssignment, Homework)
        .join(Homework, HomeworkAssignment.homework_id == Homework.id)
        .where(HomeworkAssignment.id == assignment_id, Homework.status == "PUBLISHED")
    )
    row = result.first()
    if not row:
        raise ServiceError("Homework not found", status.HTTP_404_NOT_FOUND)
    assignment, hw = row

    attempt_result = await db.execute(
        select(HomeworkAttempt).where(
            HomeworkAttempt.homework_assignment_id == assignment.id,
            HomeworkAttempt.student_id == student_id,
        ).order_by(HomeworkAttempt.attempt_number.desc()).limit(1)
    )
    attempt = attempt_result.scalar_one_or_none()

    sub_status = "not_started"
    if attempt:
        sub_status = "submitted" if attempt.completed_at else "in_progress"

    from app.core.models.homework import HomeworkQuestion
    q_count_result = await db.execute(
        select(func.count(HomeworkQuestion.id)).where(HomeworkQuestion.homework_id == hw.id)
    )
    total_q = q_count_result.scalar() or 0

    subject_name = None
    if assignment.subject_id:
        subj = await db.get(SchoolSubject, assignment.subject_id)
        subject_name = subj.name if subj else None

    return HomeworkParentDetail(
        homework_id=hw.id,
        assignment_id=assignment.id,
        title=hw.title,
        description=hw.description,
        subject_name=subject_name,
        due_date=assignment.due_date,
        submission_status=sub_status,
        total_questions=total_q,
    )


# ─── Assessments ─────────────────────────────────────────────────────────────

async def get_assessments(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    class_id: Optional[UUID],
    section_id: Optional[UUID],
    ay_id: Optional[UUID],
) -> List[AssessmentParentItem]:
    if not class_id or not ay_id:
        return []

    stmt = select(OnlineAssessment).where(
        OnlineAssessment.tenant_id == tenant_id,
        OnlineAssessment.academic_year_id == ay_id,
        OnlineAssessment.class_id == class_id,
        OnlineAssessment.status.in_(["ACTIVE", "UPCOMING", "COMPLETED"]),
    )
    if section_id:
        stmt = stmt.where(
            (OnlineAssessment.section_id == section_id) | (OnlineAssessment.section_id.is_(None))
        )
    result = await db.execute(stmt.order_by(OnlineAssessment.due_date.desc()))
    assessments = result.scalars().all()

    items = []
    for a in assessments:
        attempt_result = await db.execute(
            select(AssessmentAttempt).where(
                AssessmentAttempt.assessment_id == a.id,
                AssessmentAttempt.student_id == student_id,
                AssessmentAttempt.status == "SUBMITTED",
            ).order_by(AssessmentAttempt.submitted_at.desc()).limit(1)
        )
        attempt = attempt_result.scalar_one_or_none()

        pct = None
        if attempt and attempt.score is not None and a.total_marks > 0:
            pct = round(attempt.score / a.total_marks * 100, 1)

        subject_name = None
        if a.subject_id:
            subj = await db.get(SchoolSubject, a.subject_id)
            subject_name = subj.name if subj else None

        items.append(AssessmentParentItem(
            assessment_id=a.id,
            title=a.title,
            subject_name=subject_name,
            due_date=a.due_date,
            status=a.status,
            attempt_status=attempt.status if attempt else None,
            score=attempt.score if attempt else None,
            total_marks=a.total_marks,
            percentage=pct,
        ))
    return items


async def get_assessment_result(
    db: AsyncSession, tenant_id: UUID, student_id: UUID, assessment_id: UUID
) -> AssessmentParentResult:
    a_result = await db.execute(
        select(OnlineAssessment).where(
            OnlineAssessment.id == assessment_id,
            OnlineAssessment.tenant_id == tenant_id,
        )
    )
    assessment = a_result.scalar_one_or_none()
    if not assessment:
        raise ServiceError("Assessment not found", status.HTTP_404_NOT_FOUND)

    attempt_result = await db.execute(
        select(AssessmentAttempt).where(
            AssessmentAttempt.assessment_id == assessment_id,
            AssessmentAttempt.student_id == student_id,
            AssessmentAttempt.status == "SUBMITTED",
        ).order_by(AssessmentAttempt.submitted_at.desc()).limit(1)
    )
    attempt = attempt_result.scalar_one_or_none()

    pct = None
    if attempt and attempt.score is not None and assessment.total_marks > 0:
        pct = round(attempt.score / assessment.total_marks * 100, 1)

    return AssessmentParentResult(
        assessment_id=assessment.id,
        title=assessment.title,
        total_marks=assessment.total_marks,
        score=attempt.score if attempt else None,
        percentage=pct,
        correct_count=attempt.correct_count if attempt else None,
        wrong_count=attempt.wrong_count if attempt else None,
        skipped_count=attempt.skipped_count if attempt else None,
        time_taken_seconds=attempt.time_taken_seconds if attempt else None,
        submitted_at=attempt.submitted_at if attempt else None,
    )


# ─── Timetable ────────────────────────────────────────────────────────────────

async def get_weekly_timetable(
    db: AsyncSession,
    tenant_id: UUID,
    class_id: Optional[UUID],
    section_id: Optional[UUID],
    ay_id: Optional[UUID],
) -> WeeklyTimetable:
    if not class_id or not ay_id:
        return WeeklyTimetable()

    result = await db.execute(
        select(Timetable, TimeSlot, User, SchoolSubject)
        .join(TimeSlot, Timetable.slot_id == TimeSlot.id)
        .join(User, Timetable.teacher_id == User.id)
        .join(SchoolSubject, Timetable.subject_id == SchoolSubject.id)
        .where(
            Timetable.tenant_id == tenant_id,
            Timetable.academic_year_id == ay_id,
            Timetable.class_id == class_id,
            Timetable.section_id == section_id,
        )
        .order_by(Timetable.day_of_week, TimeSlot.order_index)
    )
    rows = result.all()

    weekly: Dict[str, List[TimetableSlot]] = {d: [] for d in _DAY_NAMES}
    for tt, slot, teacher, subject in rows:
        day = _DAY_NAMES[tt.day_of_week] if 0 <= tt.day_of_week <= 6 else "monday"
        period = slot.order_index + 1
        weekly[day].append(TimetableSlot(
            period=period,
            subject_name=subject.name,
            teacher_name=teacher.full_name,
            start_time=slot.start_time,
            end_time=slot.end_time,
            slot_type=slot.slot_type,
        ))

    return WeeklyTimetable(**weekly)


# ─── Notifications ────────────────────────────────────────────────────────────

async def get_notifications(
    db: AsyncSession, parent_id: UUID, is_read: Optional[bool] = None
) -> List[NotificationItem]:
    stmt = select(ParentNotification).where(
        ParentNotification.parent_id == parent_id
    ).order_by(ParentNotification.sent_at.desc())
    if is_read is not None:
        stmt = stmt.where(ParentNotification.is_read == is_read)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        NotificationItem(
            id=n.id, type=n.type, title=n.title, body=n.body,
            is_read=n.is_read, sent_at=n.sent_at, student_id=n.student_id,
        )
        for n in rows
    ]


async def mark_notification_read(db: AsyncSession, parent_id: UUID, notification_id: UUID) -> None:
    result = await db.execute(
        select(ParentNotification).where(
            ParentNotification.id == notification_id,
            ParentNotification.parent_id == parent_id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise ServiceError("Notification not found", status.HTTP_404_NOT_FOUND)
    notif.is_read = True
    await db.commit()


async def mark_all_read(db: AsyncSession, parent_id: UUID) -> None:
    await db.execute(
        update(ParentNotification)
        .where(ParentNotification.parent_id == parent_id, ParentNotification.is_read.is_(False))
        .values(is_read=True)
    )
    await db.commit()


async def get_notification_preferences(db: AsyncSession, parent_id: UUID) -> NotificationPreferenceResponse:
    result = await db.execute(
        select(NotificationPreference).where(NotificationPreference.parent_id == parent_id)
    )
    pref = result.scalar_one_or_none()
    if not pref:
        return NotificationPreferenceResponse(
            sms_enabled=True, email_enabled=True, push_enabled=True, types_muted=[]
        )
    return NotificationPreferenceResponse(
        sms_enabled=pref.sms_enabled,
        email_enabled=pref.email_enabled,
        push_enabled=pref.push_enabled,
        types_muted=pref.types_muted or [],
    )


async def update_notification_preferences(
    db: AsyncSession, parent_id: UUID, payload: NotificationPreferenceUpdate
) -> NotificationPreferenceResponse:
    result = await db.execute(
        select(NotificationPreference).where(NotificationPreference.parent_id == parent_id)
    )
    pref = result.scalar_one_or_none()
    if not pref:
        pref = NotificationPreference(parent_id=parent_id)
        db.add(pref)

    if payload.sms_enabled is not None:
        pref.sms_enabled = payload.sms_enabled
    if payload.email_enabled is not None:
        pref.email_enabled = payload.email_enabled
    if payload.push_enabled is not None:
        pref.push_enabled = payload.push_enabled
    if payload.types_muted is not None:
        pref.types_muted = payload.types_muted

    await db.commit()
    await db.refresh(pref)
    return NotificationPreferenceResponse(
        sms_enabled=pref.sms_enabled,
        email_enabled=pref.email_enabled,
        push_enabled=pref.push_enabled,
        types_muted=pref.types_muted or [],
    )


# ─── Dispatch notification (called from other modules) ────────────────────────

async def dispatch_absent_notification(
    db: AsyncSession, tenant_id: UUID, student_id: UUID, attendance_date: date
) -> None:
    student = await db.get(User, student_id)
    name = student.full_name if student else "your child"

    links_result = await db.execute(
        select(ParentStudentLink).where(
            ParentStudentLink.student_id == student_id,
            ParentStudentLink.is_primary.is_(True),
        )
    )
    links = links_result.scalars().all()
    for link in links:
        parent = await db.get(Parent, link.parent_id)
        if not parent or not parent.is_active:
            continue

        pref_result = await db.execute(
            select(NotificationPreference).where(NotificationPreference.parent_id == parent.id)
        )
        pref = pref_result.scalar_one_or_none()
        types_muted = (pref.types_muted or []) if pref else []
        if "attendance_absent" in types_muted:
            continue

        notif = ParentNotification(
            tenant_id=tenant_id,
            parent_id=parent.id,
            student_id=student_id,
            type="attendance_absent",
            title=f"Attendance Alert — {name}",
            body=f"{name} was marked absent on {attendance_date.strftime('%d %b %Y')}.",
        )
        db.add(notif)
    await db.commit()


async def dispatch_fee_due_notification(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    title: str,
    body: str,
) -> None:
    links_result = await db.execute(
        select(ParentStudentLink).where(ParentStudentLink.student_id == student_id)
    )
    for link in links_result.scalars().all():
        db.add(
            ParentNotification(
                tenant_id=tenant_id,
                parent_id=link.parent_id,
                student_id=student_id,
                type="fee_due",
                title=title,
                body=body,
            )
        )
    await db.commit()


async def dispatch_homework_due_notification(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    title: str,
    body: str,
) -> None:
    links_result = await db.execute(
        select(ParentStudentLink).where(ParentStudentLink.student_id == student_id)
    )
    for link in links_result.scalars().all():
        db.add(
            ParentNotification(
                tenant_id=tenant_id,
                parent_id=link.parent_id,
                student_id=student_id,
                type="homework_due",
                title=title,
                body=body,
            )
        )
    await db.commit()


async def dispatch_exam_schedule_notification(
    db: AsyncSession,
    tenant_id: UUID,
    class_id: UUID,
    section_id: UUID,
    academic_year_id: UUID,
    title: str,
    body: str,
) -> None:
    student_result = await db.execute(
        select(StudentAcademicRecord.student_id).where(
            StudentAcademicRecord.tenant_id == tenant_id,
            StudentAcademicRecord.class_id == class_id,
            StudentAcademicRecord.section_id == section_id,
            StudentAcademicRecord.academic_year_id == academic_year_id,
            StudentAcademicRecord.status == "ACTIVE",
        )
    )
    student_ids = [row[0] for row in student_result.all()]
    if not student_ids:
        return
    links_result = await db.execute(
        select(ParentStudentLink).where(ParentStudentLink.student_id.in_(student_ids))
    )
    for link in links_result.scalars().all():
        db.add(
            ParentNotification(
                tenant_id=tenant_id,
                parent_id=link.parent_id,
                student_id=link.student_id,
                type="exam_schedule",
                title=title,
                body=body,
            )
        )
    await db.commit()


async def dispatch_circular_notification(
    db: AsyncSession,
    tenant_id: UUID,
    title: str,
    body: str,
) -> None:
    parents_result = await db.execute(
        select(Parent.id).where(
            Parent.tenant_id == tenant_id,
            Parent.is_active.is_(True),
        )
    )
    parent_ids = [row[0] for row in parents_result.all()]
    for parent_id in parent_ids:
        db.add(
            ParentNotification(
                tenant_id=tenant_id,
                parent_id=parent_id,
                student_id=None,
                type="circular",
                title=title,
                body=body,
            )
        )
    await db.commit()


# ─── Messaging ────────────────────────────────────────────────────────────────

async def _thread_preview(db: AsyncSession, thread: MessageThread) -> ThreadPreview:
    last_msg_result = await db.execute(
        select(Message).where(Message.thread_id == thread.id).order_by(Message.sent_at.desc()).limit(1)
    )
    last_msg = last_msg_result.scalar_one_or_none()

    unread_result = await db.execute(
        select(func.count(Message.id)).where(
            Message.thread_id == thread.id,
            Message.sender_role == "teacher",
            Message.is_read.is_(False),
        )
    )
    unread = unread_result.scalar() or 0

    teacher = await db.get(User, thread.teacher_id)
    student = await db.get(User, thread.student_id)

    return ThreadPreview(
        id=thread.id,
        teacher_id=thread.teacher_id,
        teacher_name=teacher.full_name if teacher else "",
        student_id=thread.student_id,
        student_name=student.full_name if student else "",
        subject=thread.subject,
        last_message_at=thread.last_message_at,
        unread_count=unread,
        last_message_preview=last_msg.body[:100] if last_msg else None,
    )


async def list_message_threads(db: AsyncSession, parent_id: UUID) -> List[ThreadPreview]:
    result = await db.execute(
        select(MessageThread).where(MessageThread.parent_id == parent_id)
        .order_by(MessageThread.last_message_at.desc())
    )
    threads = result.scalars().all()
    return [await _thread_preview(db, t) for t in threads]


async def get_thread_detail(db: AsyncSession, parent_id: UUID, thread_id: UUID) -> ThreadDetail:
    result = await db.execute(
        select(MessageThread).where(
            MessageThread.id == thread_id,
            MessageThread.parent_id == parent_id,
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise ServiceError("Thread not found", status.HTTP_404_NOT_FOUND)

    msgs_result = await db.execute(
        select(Message).where(Message.thread_id == thread_id).order_by(Message.sent_at)
    )
    messages = msgs_result.scalars().all()

    await db.execute(
        update(Message)
        .where(
            Message.thread_id == thread_id,
            Message.sender_role == "teacher",
            Message.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await db.commit()

    teacher = await db.get(User, thread.teacher_id)
    student = await db.get(User, thread.student_id)

    return ThreadDetail(
        id=thread.id,
        teacher_id=thread.teacher_id,
        teacher_name=teacher.full_name if teacher else "",
        student_id=thread.student_id,
        student_name=student.full_name if student else "",
        subject=thread.subject,
        created_at=thread.created_at,
        messages=[
            MessageItem(
                id=m.id, sender_role=m.sender_role, sender_id=m.sender_id,
                body=m.body, sent_at=m.sent_at, is_read=m.is_read,
            )
            for m in messages
        ],
    )


async def create_thread(
    db: AsyncSession,
    tenant_id: UUID,
    parent: Parent,
    teacher_id: UUID,
    student_id: UUID,
    subject: str,
    first_message: str,
) -> ThreadDetail:
    teacher = await db.get(User, teacher_id)
    if not teacher or teacher.tenant_id != tenant_id or teacher.user_type != "employee":
        raise ServiceError("Teacher not found in this tenant", status.HTTP_400_BAD_REQUEST)

    ay = await _get_active_academic_year(db, tenant_id)
    if not ay:
        raise ServiceError("No active academic year", status.HTTP_403_FORBIDDEN)

    student_record = await _get_student_record(db, student_id, ay.id)
    if not student_record:
        raise ServiceError("Student is not active in current academic year", status.HTTP_400_BAD_REQUEST)

    class_teacher_result = await db.execute(
        select(ClassTeacherAssignment).where(
            ClassTeacherAssignment.tenant_id == tenant_id,
            ClassTeacherAssignment.academic_year_id == ay.id,
            ClassTeacherAssignment.class_id == student_record.class_id,
            ClassTeacherAssignment.section_id == student_record.section_id,
            ClassTeacherAssignment.teacher_id == teacher_id,
        )
    )
    if not class_teacher_result.scalar_one_or_none():
        raise ServiceError(
            "Teacher must be assigned to this student's class/section",
            status.HTTP_400_BAD_REQUEST,
        )

    thread = MessageThread(
        tenant_id=tenant_id,
        parent_id=parent.id,
        teacher_id=teacher_id,
        student_id=student_id,
        subject=subject,
    )
    db.add(thread)
    await db.flush()

    msg = Message(
        thread_id=thread.id,
        sender_role="parent",
        sender_id=parent.id,
        body=first_message,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(thread)

    student = await db.get(User, student_id)
    return ThreadDetail(
        id=thread.id,
        teacher_id=teacher_id,
        teacher_name=teacher.full_name,
        student_id=student_id,
        student_name=student.full_name if student else "",
        subject=thread.subject,
        created_at=thread.created_at,
        messages=[
            MessageItem(
                id=msg.id, sender_role=msg.sender_role, sender_id=msg.sender_id,
                body=msg.body, sent_at=msg.sent_at, is_read=msg.is_read,
            )
        ],
    )


async def reply_to_thread(
    db: AsyncSession, parent_id: UUID, thread_id: UUID, body: str
) -> MessageItem:
    result = await db.execute(
        select(MessageThread).where(
            MessageThread.id == thread_id,
            MessageThread.parent_id == parent_id,
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise ServiceError("Thread not found", status.HTTP_404_NOT_FOUND)

    msg = Message(
        thread_id=thread.id,
        sender_role="parent",
        sender_id=parent_id,
        body=body,
    )
    db.add(msg)
    thread.last_message_at = datetime.utcnow()
    await db.commit()
    await db.refresh(msg)
    return MessageItem(
        id=msg.id, sender_role=msg.sender_role, sender_id=msg.sender_id,
        body=msg.body, sent_at=msg.sent_at, is_read=msg.is_read,
    )


# ─── Admin ────────────────────────────────────────────────────────────────────

async def admin_create_parent(
    db: AsyncSession, tenant_id: UUID, payload: CreateParentRequest
) -> CreateParentResponse:
    from app.api.v1.modules.users.service import _check_email_exists_globally

    if await _check_email_exists_globally(db, payload.email):
        raise ServiceError("Email already exists", status.HTTP_409_CONFLICT)

    for child_link in payload.children:
        student = await db.get(User, child_link.student_id)
        if not student or student.tenant_id != tenant_id or student.user_type != "student":
            raise ServiceError(
                f"Student {child_link.student_id} not found in this tenant",
                status.HTTP_400_BAD_REQUEST,
            )

    user = User(
        tenant_id=tenant_id,
        full_name=payload.full_name,
        email=payload.email,
        mobile=payload.phone,
        password_hash=hash_password(payload.password),
        role="PARENT",
        status="ACTIVE",
        source="PARENT",
        user_type="parent",
    )
    db.add(user)
    await db.flush()

    parent = Parent(
        tenant_id=tenant_id,
        user_id=user.id,
        full_name=payload.full_name,
        phone=payload.phone,
        email=payload.email,
    )
    db.add(parent)
    await db.flush()
    user.parent_id = parent.id

    for child_link in payload.children:
        link = ParentStudentLink(
            parent_id=parent.id,
            student_id=child_link.student_id,
            relation=child_link.relation,
            is_primary=child_link.is_primary,
        )
        db.add(link)

    pref = NotificationPreference(parent_id=parent.id)
    db.add(pref)

    await db.commit()

    return CreateParentResponse(parent_id=parent.id, invite_sent=False, invite_token=None)


async def admin_list_parents(
    db: AsyncSession,
    tenant_id: UUID,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
) -> List[ParentListItem]:
    active_ay = await _get_active_academic_year(db, tenant_id)
    stmt = select(Parent).where(Parent.tenant_id == tenant_id)
    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(
            func.lower(Parent.full_name).like(term) | func.lower(Parent.email).like(term)
        )
    stmt = stmt.offset((page - 1) * limit).limit(limit).order_by(Parent.created_at.desc())
    result = await db.execute(stmt)
    parents = result.scalars().all()

    items = []
    for p in parents:
        links_result = await db.execute(
            select(ParentStudentLink).where(ParentStudentLink.parent_id == p.id)
        )
        links = links_result.scalars().all()
        children = []
        for link in links:
            student = await db.get(User, link.student_id)
            if student:
                class_name = None
                section_name = None
                roll_number = None
                if active_ay:
                    sar = await _get_student_record(db, link.student_id, active_ay.id)
                    if sar:
                        school_class = await db.get(SchoolClass, sar.class_id)
                        section = await db.get(Section, sar.section_id)
                        class_name = school_class.name if school_class else None
                        section_name = section.name if section else None
                        roll_number = sar.roll_number
                children.append(ChildSummary(
                    student_id=link.student_id,
                    full_name=student.full_name,
                    class_name=class_name,
                    section_name=section_name,
                    roll_number=roll_number,
                    relation=link.relation,
                    is_primary=link.is_primary,
                ))
        items.append(ParentListItem(
            id=p.id, full_name=p.full_name, email=p.email, phone=p.phone,
            is_active=p.is_active, children=children, created_at=p.created_at,
        ))
    return items


async def admin_get_parent(db: AsyncSession, tenant_id: UUID, parent_id: UUID) -> ParentDetail:
    p = await _get_parent_by_id(db, parent_id, tenant_id)
    if not p:
        raise ServiceError("Parent not found", status.HTTP_404_NOT_FOUND)

    active_ay = await _get_active_academic_year(db, tenant_id)
    links_result = await db.execute(
        select(ParentStudentLink).where(ParentStudentLink.parent_id == p.id)
    )
    links = links_result.scalars().all()
    children = []
    for link in links:
        student = await db.get(User, link.student_id)
        if student:
            class_name = None
            section_name = None
            roll_number = None
            if active_ay:
                sar = await _get_student_record(db, link.student_id, active_ay.id)
                if sar:
                    school_class = await db.get(SchoolClass, sar.class_id)
                    section = await db.get(Section, sar.section_id)
                    class_name = school_class.name if school_class else None
                    section_name = section.name if section else None
                    roll_number = sar.roll_number
            children.append(ChildSummary(
                student_id=link.student_id,
                full_name=student.full_name,
                class_name=class_name,
                section_name=section_name,
                roll_number=roll_number,
                relation=link.relation,
                is_primary=link.is_primary,
            ))

    user = await db.get(User, p.user_id)
    last_login = None
    if user:
        token_result = await db.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
            .order_by(RefreshToken.expires_at.desc()).limit(1)
        )
        rt = token_result.scalar_one_or_none()
        if rt:
            last_login = rt.expires_at

    return ParentDetail(
        id=p.id, full_name=p.full_name, email=p.email, phone=p.phone,
        is_active=p.is_active, children=children, created_at=p.created_at,
        last_login=last_login,
    )


async def admin_update_parent(
    db: AsyncSession, tenant_id: UUID, parent_id: UUID, payload: UpdateParentRequest
) -> ParentDetail:
    p = await _get_parent_by_id(db, parent_id, tenant_id)
    if not p:
        raise ServiceError("Parent not found", status.HTTP_404_NOT_FOUND)

    if payload.full_name is not None:
        p.full_name = payload.full_name
    if payload.phone is not None:
        p.phone = payload.phone
    if payload.email is not None:
        existing = await db.execute(
            select(Parent).where(
                Parent.tenant_id == tenant_id,
                func.lower(Parent.email) == func.lower(payload.email),
                Parent.id != parent_id,
            )
        )
        if existing.scalar_one_or_none():
            raise ServiceError("Email already in use", status.HTTP_409_CONFLICT)
        p.email = payload.email
        user = await db.get(User, p.user_id)
        if user:
            user.email = payload.email
    if payload.password is not None:
        user = await db.get(User, p.user_id)
        if not user:
            raise ServiceError("Linked user not found", status.HTTP_404_NOT_FOUND)
        user.password_hash = hash_password(payload.password)

    if payload.children is not None:
        existing_links_result = await db.execute(
            select(ParentStudentLink).where(ParentStudentLink.parent_id == parent_id)
        )
        existing_links = {str(lnk.student_id): lnk for lnk in existing_links_result.scalars().all()}
        incoming_ids = {str(child.student_id) for child in payload.children}

        for sid, link in existing_links.items():
            if sid not in incoming_ids:
                await db.delete(link)

        for child_link in payload.children:
            sid = str(child_link.student_id)
            if sid in existing_links:
                existing_links[sid].relation = child_link.relation
                existing_links[sid].is_primary = child_link.is_primary
            else:
                student = await db.get(User, child_link.student_id)
                if not student or student.tenant_id != tenant_id:
                    raise ServiceError(f"Student {child_link.student_id} not found", status.HTTP_400_BAD_REQUEST)
                db.add(ParentStudentLink(
                    parent_id=parent_id,
                    student_id=child_link.student_id,
                    relation=child_link.relation,
                    is_primary=child_link.is_primary,
                ))

    await db.commit()
    return await admin_get_parent(db, tenant_id, parent_id)


async def admin_reset_parent_password(
    db: AsyncSession,
    tenant_id: UUID,
    parent_id: UUID,
    password: str,
) -> dict:
    p = await _get_parent_by_id(db, parent_id, tenant_id)
    if not p:
        raise ServiceError("Parent not found", status.HTTP_404_NOT_FOUND)
    user = await db.get(User, p.user_id)
    if not user:
        raise ServiceError("Linked user not found", status.HTTP_404_NOT_FOUND)
    user.password_hash = hash_password(password)
    await db.commit()
    return {"success": True, "message": "Parent password updated successfully"}


async def admin_deactivate_parent(db: AsyncSession, tenant_id: UUID, parent_id: UUID) -> None:
    p = await _get_parent_by_id(db, parent_id, tenant_id)
    if not p:
        raise ServiceError("Parent not found", status.HTTP_404_NOT_FOUND)
    p.is_active = False
    user = await db.get(User, p.user_id)
    if user:
        user.status = "INACTIVE"
    await db.commit()


async def admin_resend_invite(
    db: AsyncSession, tenant_id: UUID, parent_id: UUID
) -> CreateParentResponse:
    p = await _get_parent_by_id(db, parent_id, tenant_id)
    if not p:
        raise ServiceError("Parent not found", status.HTTP_404_NOT_FOUND)

    from datetime import timedelta
    expiry_hours = getattr(settings, "parent_invite_token_expiry_hours", 48)
    raw_token = secrets.token_urlsafe(48)
    reset_token = PasswordResetToken(
        user_id=p.user_id,
        token=raw_token,
        expires_at=datetime.utcnow() + timedelta(hours=expiry_hours),
    )
    db.add(reset_token)
    await db.commit()
    return CreateParentResponse(parent_id=p.id, invite_sent=False, invite_token=raw_token)


async def admin_bulk_import(
    db: AsyncSession, tenant_id: UUID, rows: List[BulkImportRow]
) -> dict:
    created = 0
    failed: List[Dict[str, Any]] = []

    for row in rows:
        try:
            from app.api.v1.modules.users.service import _check_email_exists_globally
            if await _check_email_exists_globally(db, row.email):
                failed.append({"email": row.email, "reason": "Email already exists"})
                continue

            student_result = await db.execute(
                select(User).where(
                    User.tenant_id == tenant_id,
                    User.user_type == "student",
                )
            )
            students = student_result.scalars().all()
            student_match = None
            for s in students:
                from app.auth.models import StudentProfile
                profile_result = await db.execute(
                    select(StudentProfile).where(StudentProfile.user_id == s.id)
                )
                profile = profile_result.scalar_one_or_none()
                if profile and profile.roll_number == row.student_admission_number:
                    student_match = s
                    break

            if not student_match:
                failed.append({"email": row.email, "reason": f"Student with admission number {row.student_admission_number} not found"})
                continue

            imported_password = secrets.token_urlsafe(12)
            response = await admin_create_parent(
                db,
                tenant_id,
                CreateParentRequest(
                    full_name=row.full_name,
                    email=row.email,
                    phone=row.phone,
                    password=imported_password,
                    confirm_password=imported_password,
                    children=[ChildLinkInput(
                        student_id=student_match.id,
                        relation=row.relation,
                        is_primary=row.is_primary,
                    )],
                ),
            )
            created += 1
        except ServiceError as e:
            failed.append({"email": row.email, "reason": e.message})
        except Exception as e:
            failed.append({"email": row.email, "reason": str(e)})

    return {"created": created, "failed": failed}
