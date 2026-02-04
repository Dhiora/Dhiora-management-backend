"""
Admission requests and admission students. Track immutable, status mutable.
Approval creates admission_student (INACTIVE); activation creates User + StudentProfile + StudentAcademicRecord.
"""

from datetime import date, datetime
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import StudentProfile, User, TeacherReferral
from app.auth.security import hash_password
from app.core.exceptions import ServiceError
from app.core.models import (
    AcademicYear,
    AdmissionRequest,
    AdmissionStudent,
    StudentAcademicRecord,
)
from app.core.models.admission_request import (
    ADMISSION_STATUS_APPROVED,
    ADMISSION_STATUS_PENDING,
    ADMISSION_STATUS_REJECTED,
    TRACK_ADMIN_RAISED,
    TRACK_CAMPAIGN_REFERRAL,
    TRACK_PARENT_DIRECT,
    TRACK_TEACHER_RAISED,
    TRACK_WEBSITE_FORM,
)
from app.core.models.admission_student import STUDENT_STATUS_ACTIVE, STUDENT_STATUS_INACTIVE

from app.api.v1.academic_years import service as academic_year_service
from app.api.v1.classes import service as class_service
from app.api.v1.sections import service as section_service
from app.api.v1.modules.users import service as users_service

from . import audit_service
from .schemas import (
    AdmissionRequestCreate,
    AdmissionRequestApprove,
    AdmissionRequestReject,
    AdmissionRequestResponse,
    AdmissionStudentResponse,
)


def _to_uuid(val):
    if val is None:
        return None
    return val if isinstance(val, UUID) else UUID(str(val))


# ----- Track resolution (immutable; set only at creation) -----

async def _resolve_track(
    db: AsyncSession,
    tenant_id: UUID,
    current_user_role: str,
    is_teacher: bool,
    referral_code: Optional[str],
    raised_via_website_form: bool,
) -> Tuple[str, Optional[UUID]]:
    """
    Returns (track, referral_teacher_id).
    Priority: 1 Teacher raised, 2 Valid referral_code -> CAMPAIGN_REFERRAL, 3 Website form, 4 Admin raised, 5 Parent direct.
    """
    if is_teacher:
        return TRACK_TEACHER_RAISED, None
    code = (referral_code or "").strip().upper()
    if code:
        ref = await db.execute(
            select(TeacherReferral).where(
                TeacherReferral.tenant_id == tenant_id,
                TeacherReferral.referral_code == code,
            )
        )
        tr = ref.scalar_one_or_none()
        if tr:
            return TRACK_CAMPAIGN_REFERRAL, tr.teacher_id
    if raised_via_website_form:
        return TRACK_WEBSITE_FORM, None
    if current_user_role in ("ADMIN", "SUPER_ADMIN", "PLATFORM_ADMIN"):
        return TRACK_ADMIN_RAISED, None
    return TRACK_PARENT_DIRECT, None


def _request_to_response(r: AdmissionRequest) -> AdmissionRequestResponse:
    return AdmissionRequestResponse(
        id=r.id,
        tenant_id=r.tenant_id,
        student_name=r.student_name,
        parent_name=r.parent_name,
        mobile=r.mobile,
        email=r.email,
        class_applied_for=r.class_applied_for,
        section_applied_for=r.section_applied_for,
        academic_year_id=r.academic_year_id,
        track=r.track,
        status=r.status,
        raised_by_user_id=r.raised_by_user_id,
        raised_by_role=r.raised_by_role,
        referral_teacher_id=r.referral_teacher_id,
        approved_by_user_id=r.approved_by_user_id,
        approved_by_role=r.approved_by_role,
        approved_at=r.approved_at,
        remarks=r.remarks,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _student_to_response(s: AdmissionStudent) -> AdmissionStudentResponse:
    return AdmissionStudentResponse(
        id=s.id,
        tenant_id=s.tenant_id,
        admission_request_id=s.admission_request_id,
        user_id=s.user_id,
        student_name=s.student_name,
        parent_name=s.parent_name,
        mobile=s.mobile,
        email=s.email,
        class_id=s.class_id,
        section_id=s.section_id,
        academic_year_id=s.academic_year_id,
        track=s.track,
        status=s.status,
        joined_date=s.joined_date,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


# ----- Admission requests -----

async def create_admission_request(
    db: AsyncSession,
    tenant_id: UUID,
    payload: AdmissionRequestCreate,
    raised_by_user_id: UUID,
    raised_by_role: str,
) -> AdmissionRequestResponse:
    """Raise an admission request. Teachers need ADMISSION_RAISE; track set by backend."""
    ay = await academic_year_service.get_admission_open_academic_year(db, tenant_id)
    if not ay:
        raise ServiceError(
            "No academic year is open for admissions. Create an academic year with is_current=true, status=ACTIVE, admissions_allowed=true.",
            status.HTTP_400_BAD_REQUEST,
        )
    school_class = await class_service.get_class_by_id_for_tenant(
        db, tenant_id, payload.class_applied_for, active_only=True
    )
    if not school_class:
        raise ServiceError("Invalid or inactive class for this tenant", status.HTTP_400_BAD_REQUEST)
    section_id = payload.section_applied_for
    if section_id:
        section = await section_service.get_section_by_id_for_tenant(db, tenant_id, section_id, active_only=True)
        if not section or section.class_id != payload.class_applied_for:
            raise ServiceError("Invalid or inactive section for the selected class", status.HTTP_400_BAD_REQUEST)

    is_teacher = raised_by_role == "Teacher"
    track, referral_teacher_id = await _resolve_track(
        db,
        tenant_id,
        raised_by_role,
        is_teacher,
        payload.referral_code,
        payload.raised_via_website_form,
    )

    req = AdmissionRequest(
        tenant_id=tenant_id,
        student_name=payload.student_name.strip(),
        parent_name=payload.parent_name.strip() if payload.parent_name else None,
        mobile=payload.mobile.strip() if payload.mobile else None,
        email=payload.email.strip() if payload.email else None,
        class_applied_for=payload.class_applied_for,
        section_applied_for=payload.section_applied_for,
        academic_year_id=ay.id,
        track=track,
        status=ADMISSION_STATUS_PENDING,
        raised_by_user_id=raised_by_user_id,
        raised_by_role=raised_by_role,
        referral_teacher_id=referral_teacher_id,
    )
    db.add(req)
    await db.flush()
    await audit_service.log_audit(
        db,
        tenant_id,
        "admission_request",
        req.id,
        "admission_request_created",
        track=track,
        to_status=ADMISSION_STATUS_PENDING,
        performed_by=raised_by_user_id,
        performed_by_role=raised_by_role,
    )
    await db.commit()
    await db.refresh(req)
    return _request_to_response(req)


async def list_my_admission_requests(
    db: AsyncSession,
    tenant_id: UUID,
    raised_by_user_id: UUID,
) -> List[AdmissionRequestResponse]:
    """List admission requests raised by the current user."""
    result = await db.execute(
        select(AdmissionRequest)
        .where(
            AdmissionRequest.tenant_id == tenant_id,
            AdmissionRequest.raised_by_user_id == raised_by_user_id,
        )
        .order_by(AdmissionRequest.created_at.desc())
    )
    rows = result.scalars().all()
    return [_request_to_response(r) for r in rows]


async def list_admission_requests(
    db: AsyncSession,
    tenant_id: UUID,
    status_filter: Optional[str] = None,
) -> List[AdmissionRequestResponse]:
    """List all admission requests for tenant, optionally filter by status."""
    q = select(AdmissionRequest).where(AdmissionRequest.tenant_id == tenant_id)
    if status_filter:
        q = q.where(AdmissionRequest.status == status_filter)
    q = q.order_by(AdmissionRequest.created_at.desc())
    result = await db.execute(q)
    rows = result.scalars().all()
    return [_request_to_response(r) for r in rows]


async def get_admission_request(
    db: AsyncSession,
    tenant_id: UUID,
    request_id: UUID,
) -> Optional[AdmissionRequest]:
    return (await db.execute(
        select(AdmissionRequest).where(
            AdmissionRequest.id == request_id,
            AdmissionRequest.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()


async def approve_admission_request(
    db: AsyncSession,
    tenant_id: UUID,
    request_id: UUID,
    payload: AdmissionRequestApprove,
    approved_by_user_id: UUID,
    approved_by_role: str,
) -> AdmissionRequestResponse:
    """Approve request: status PENDING_APPROVAL -> APPROVED; create admission_student INACTIVE. Requires ADMISSION_APPROVE."""
    req = await get_admission_request(db, tenant_id, request_id)
    if not req:
        raise ServiceError("Admission request not found", status.HTTP_404_NOT_FOUND)
    if req.status != ADMISSION_STATUS_PENDING:
        raise ServiceError(
            f"Invalid status transition: only PENDING_APPROVAL can be approved (current: {req.status})",
            status.HTTP_400_BAD_REQUEST,
        )
    section = await section_service.get_section_by_id_for_tenant(
        db, tenant_id, payload.section_id, active_only=True
    )
    if not section or section.class_id != req.class_applied_for:
        raise ServiceError("Section must belong to the applied class", status.HTTP_400_BAD_REQUEST)

    from_status = req.status
    req.status = ADMISSION_STATUS_APPROVED
    req.approved_by_user_id = approved_by_user_id
    req.approved_by_role = approved_by_role
    req.approved_at = datetime.utcnow()
    req.remarks = payload.remarks
    await db.flush()

    student = AdmissionStudent(
        tenant_id=tenant_id,
        admission_request_id=req.id,
        student_name=req.student_name,
        parent_name=req.parent_name,
        mobile=req.mobile,
        email=req.email,
        class_id=req.class_applied_for,
        section_id=payload.section_id,
        academic_year_id=req.academic_year_id,
        track=req.track,
        status=STUDENT_STATUS_INACTIVE,
    )
    db.add(student)
    await db.flush()

    await audit_service.log_audit(
        db,
        tenant_id,
        "admission_request",
        req.id,
        "admission_approved",
        track=req.track,
        from_status=from_status,
        to_status=ADMISSION_STATUS_APPROVED,
        performed_by=approved_by_user_id,
        performed_by_role=approved_by_role,
        remarks=payload.remarks,
    )
    await audit_service.log_audit(
        db,
        tenant_id,
        "admission_student",
        student.id,
        "student_created",
        track=student.track,
        to_status=STUDENT_STATUS_INACTIVE,
        performed_by=approved_by_user_id,
        performed_by_role=approved_by_role,
    )
    await db.commit()
    await db.refresh(req)
    await db.refresh(student)
    return _request_to_response(req)


async def reject_admission_request(
    db: AsyncSession,
    tenant_id: UUID,
    request_id: UUID,
    payload: AdmissionRequestReject,
    rejected_by_user_id: UUID,
    rejected_by_role: str,
) -> AdmissionRequestResponse:
    """Reject request: PENDING_APPROVAL -> REJECTED."""
    req = await get_admission_request(db, tenant_id, request_id)
    if not req:
        raise ServiceError("Admission request not found", status.HTTP_404_NOT_FOUND)
    if req.status != ADMISSION_STATUS_PENDING:
        raise ServiceError(
            f"Invalid status transition: only PENDING_APPROVAL can be rejected (current: {req.status})",
            status.HTTP_400_BAD_REQUEST,
        )
    from_status = req.status
    req.status = ADMISSION_STATUS_REJECTED
    req.approved_by_user_id = rejected_by_user_id
    req.approved_by_role = rejected_by_role
    req.approved_at = datetime.utcnow()
    req.remarks = payload.remarks
    await audit_service.log_audit(
        db,
        tenant_id,
        "admission_request",
        req.id,
        "admission_rejected",
        track=req.track,
        from_status=from_status,
        to_status=ADMISSION_STATUS_REJECTED,
        performed_by=rejected_by_user_id,
        performed_by_role=rejected_by_role,
        remarks=payload.remarks,
    )
    await db.commit()
    await db.refresh(req)
    return _request_to_response(req)


# ----- Admission students -----

async def list_admission_students(
    db: AsyncSession,
    tenant_id: UUID,
    status_filter: Optional[str] = None,
) -> List[AdmissionStudentResponse]:
    q = select(AdmissionStudent).where(AdmissionStudent.tenant_id == tenant_id)
    if status_filter:
        q = q.where(AdmissionStudent.status == status_filter)
    q = q.order_by(AdmissionStudent.created_at.desc())
    result = await db.execute(q)
    rows = result.scalars().all()
    return [_student_to_response(s) for s in rows]


async def get_admission_student(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
) -> Optional[AdmissionStudent]:
    return (await db.execute(
        select(AdmissionStudent).where(
            AdmissionStudent.id == student_id,
            AdmissionStudent.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()


async def activate_admission_student(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    password: str,
    joined_date: Optional[date] = None,
    activated_by_user_id: Optional[UUID] = None,
    activated_by_role: Optional[str] = None,
) -> AdmissionStudentResponse:
    """
    Activate student: create User + StudentProfile + StudentAcademicRecord; set admission_student.user_id, status=ACTIVE, joined_date.
    Requires STUDENT_ACTIVATE permission.
    """
    student = await get_admission_student(db, tenant_id, student_id)
    if not student:
        raise ServiceError("Admission student not found", status.HTTP_404_NOT_FOUND)
    if student.status == STUDENT_STATUS_ACTIVE:
        raise ServiceError("Student is already active", status.HTTP_400_BAD_REQUEST)
    if student.user_id:
        raise ServiceError("Student already linked to a user account", status.HTTP_400_BAD_REQUEST)

    ay = await db.get(AcademicYear, student.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid academic year", status.HTTP_400_BAD_REQUEST)
    if await users_service._check_duplicate_email(db, tenant_id, student.email or ""):
        raise ServiceError("Email already exists for this tenant", status.HTTP_409_CONFLICT)
    if student.mobile and await users_service._check_duplicate_mobile(db, tenant_id, student.mobile):
        raise ServiceError("Mobile number already exists for this tenant", status.HTTP_409_CONFLICT)

    role = await users_service._get_student_role(db, tenant_id)
    if not role:
        raise ServiceError("No STUDENT role found for this tenant", status.HTTP_400_BAD_REQUEST)

    email = (student.email or "").strip() or f"student-{student.id}@admission.local"
    try:
        password_hash = hash_password(password)
        user = User(
            tenant_id=tenant_id,
            full_name=student.student_name,
            email=email,
            mobile=student.mobile,
            password_hash=password_hash,
            role=role.name,
            role_id=role.id,
            status="ACTIVE",
            source="STUDENT",
            user_type="student",
        )
        db.add(user)
        await db.flush()
        sp = StudentProfile(user_id=user.id, roll_number=None)
        db.add(sp)
        await db.flush()
        rec = StudentAcademicRecord(
            student_id=user.id,
            academic_year_id=student.academic_year_id,
            class_id=student.class_id,
            section_id=student.section_id,
            roll_number=None,
            status="ACTIVE",
        )
        db.add(rec)
        await db.flush()

        join_date = joined_date or date.today()
        student.user_id = user.id
        student.status = STUDENT_STATUS_ACTIVE
        student.joined_date = join_date
        await db.flush()

        await audit_service.log_audit(
            db,
            tenant_id,
            "admission_student",
            student.id,
            "student_activated",
            track=student.track,
            from_status=STUDENT_STATUS_INACTIVE,
            to_status=STUDENT_STATUS_ACTIVE,
            performed_by=activated_by_user_id,
            performed_by_role=activated_by_role,
        )
        await db.commit()
        await db.refresh(student)
        return _student_to_response(student)
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Duplicate email or mobile for this tenant", status.HTTP_409_CONFLICT)
