from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import ServiceError
from app.core.models import (
    AcademicYear,
    SchoolClass,
    SchoolSubject,
    Section,
    TeacherSubjectAssignment,
)

from app.api.v1.class_subjects import service as class_subjects_service

from .schemas import TeacherSubjectAssignmentCreate, TeacherSubjectAssignmentResponse


def _to_response(t: TeacherSubjectAssignment) -> TeacherSubjectAssignmentResponse:
    return TeacherSubjectAssignmentResponse(
        id=t.id,
        tenant_id=t.tenant_id,
        academic_year_id=t.academic_year_id,
        teacher_id=t.teacher_id,
        class_id=t.class_id,
        section_id=t.section_id,
        subject_id=t.subject_id,
        created_at=t.created_at,
    )


async def create_teacher_subject_assignment(
    db: AsyncSession,
    tenant_id: UUID,
    payload: TeacherSubjectAssignmentCreate,
) -> TeacherSubjectAssignmentResponse:
    ay = await db.get(AcademicYear, payload.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid academic year", status.HTTP_400_BAD_REQUEST)
    if ay.status != "ACTIVE":
        raise ServiceError("Cannot assign for a CLOSED academic year", status.HTTP_400_BAD_REQUEST)
    teacher = await db.get(User, payload.teacher_id)
    if not teacher or teacher.tenant_id != tenant_id or teacher.user_type != "employee":
        raise ServiceError("Invalid teacher (must be employee)", status.HTTP_400_BAD_REQUEST)
    cl = await db.get(SchoolClass, payload.class_id)
    if not cl or cl.tenant_id != tenant_id:
        raise ServiceError("Invalid class", status.HTTP_400_BAD_REQUEST)
    sec = await db.get(Section, payload.section_id)
    if not sec or sec.tenant_id != tenant_id or sec.class_id != payload.class_id:
        raise ServiceError("Invalid section for this class", status.HTTP_400_BAD_REQUEST)
    subj = await db.get(SchoolSubject, payload.subject_id)
    if not subj or subj.tenant_id != tenant_id:
        raise ServiceError("Invalid subject", status.HTTP_400_BAD_REQUEST)
    if not await class_subjects_service.check_subject_in_class_for_year(
        db, tenant_id, payload.academic_year_id, payload.class_id, payload.subject_id
    ):
        raise ServiceError(
            "Subject must be in class_subjects for this academic year first",
            status.HTTP_400_BAD_REQUEST,
        )
    try:
        obj = TeacherSubjectAssignment(
            tenant_id=tenant_id,
            academic_year_id=payload.academic_year_id,
            teacher_id=payload.teacher_id,
            class_id=payload.class_id,
            section_id=payload.section_id,
            subject_id=payload.subject_id,
        )
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return _to_response(obj)
    except IntegrityError:
        await db.rollback()
        raise ServiceError("This teacher-subject assignment already exists", status.HTTP_409_CONFLICT)


async def list_teacher_subject_assignments(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    teacher_id: Optional[UUID] = None,
    class_id: Optional[UUID] = None,
) -> List[TeacherSubjectAssignmentResponse]:
    stmt = select(TeacherSubjectAssignment).where(
        TeacherSubjectAssignment.tenant_id == tenant_id,
        TeacherSubjectAssignment.academic_year_id == academic_year_id,
    )
    if teacher_id is not None:
        stmt = stmt.where(TeacherSubjectAssignment.teacher_id == teacher_id)
    if class_id is not None:
        stmt = stmt.where(TeacherSubjectAssignment.class_id == class_id)
    stmt = stmt.order_by(TeacherSubjectAssignment.teacher_id, TeacherSubjectAssignment.class_id)
    result = await db.execute(stmt)
    return [_to_response(t) for t in result.scalars().all()]


async def teacher_can_override_for_subject(
    db: AsyncSession,
    teacher_id: UUID,
    academic_year_id: UUID,
    class_id: UUID,
    section_id: UUID,
    subject_id: UUID,
) -> bool:
    result = await db.execute(
        select(TeacherSubjectAssignment.id).where(
            TeacherSubjectAssignment.teacher_id == teacher_id,
            TeacherSubjectAssignment.academic_year_id == academic_year_id,
            TeacherSubjectAssignment.class_id == class_id,
            TeacherSubjectAssignment.section_id == section_id,
            TeacherSubjectAssignment.subject_id == subject_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def teacher_can_assign_homework_for_subject(
    db: AsyncSession,
    teacher_id: UUID,
    academic_year_id: UUID,
    class_id: UUID,
    section_id: Optional[UUID],
    subject_id: UUID,
) -> bool:
    """True if teacher has a teacher_subject_assignment for this class and subject (and section if given)."""
    stmt = select(TeacherSubjectAssignment.id).where(
        TeacherSubjectAssignment.teacher_id == teacher_id,
        TeacherSubjectAssignment.academic_year_id == academic_year_id,
        TeacherSubjectAssignment.class_id == class_id,
        TeacherSubjectAssignment.subject_id == subject_id,
    )
    if section_id is not None:
        stmt = stmt.where(TeacherSubjectAssignment.section_id == section_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def delete_teacher_subject_assignment(
    db: AsyncSession,
    tenant_id: UUID,
    assignment_id: UUID,
) -> bool:
    result = await db.execute(
        select(TeacherSubjectAssignment).where(
            TeacherSubjectAssignment.id == assignment_id,
            TeacherSubjectAssignment.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return False
    await db.delete(obj)
    await db.commit()
    return True
