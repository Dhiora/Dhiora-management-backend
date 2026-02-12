"""Class Teacher Assignment service. One teacher per class-section per academic year.
No subject or timetable logic."""

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
    ClassTeacherAssignment,
    SchoolClass,
    Section,
)

from app.api.v1.classes import service as class_service
from app.api.v1.sections import service as section_service

from .schemas import (
    ClassTeacherAssignmentCreate,
    ClassTeacherAssignmentResponse,
    ClassTeacherAssignmentUpdate,
)


def _to_response(a: ClassTeacherAssignment) -> ClassTeacherAssignmentResponse:
    return ClassTeacherAssignmentResponse(
        id=a.id,
        tenant_id=a.tenant_id,
        academic_year_id=a.academic_year_id,
        class_id=a.class_id,
        section_id=a.section_id,
        teacher_id=a.teacher_id,
        created_at=a.created_at,
    )


async def create_class_teacher_assignment(
    db: AsyncSession,
    tenant_id: UUID,
    payload: ClassTeacherAssignmentCreate,
) -> ClassTeacherAssignmentResponse:
    ay = await db.get(AcademicYear, payload.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid academic year.", status.HTTP_400_BAD_REQUEST)
    if ay.status != "ACTIVE":
        raise ServiceError("Academic year is not active.", status.HTTP_400_BAD_REQUEST)

    cl = await class_service.get_class_by_id_for_tenant(db, tenant_id, payload.class_id, active_only=True)
    if not cl:
        raise ServiceError("Invalid class for this tenant.", status.HTTP_400_BAD_REQUEST)

    sec = await section_service.get_section_by_id_for_tenant(
        db, tenant_id, payload.section_id, active_only=True, academic_year_id=payload.academic_year_id
    )
    if not sec or sec.class_id != payload.class_id:
        raise ServiceError("Section does not belong to this class.", status.HTTP_400_BAD_REQUEST)

    teacher = await db.get(User, payload.teacher_id)
    if not teacher or teacher.tenant_id != tenant_id:
        raise ServiceError("Selected teacher is not eligible.", status.HTTP_400_BAD_REQUEST)
    if teacher.user_type != "employee":
        raise ServiceError("Selected teacher is not eligible.", status.HTTP_400_BAD_REQUEST)

    existing = await get_class_teacher_by_context(
        db, tenant_id, payload.academic_year_id, payload.class_id, payload.section_id
    )
    if existing:
        raise ServiceError(
            "Class teacher already assigned for this class and section.",
            status.HTTP_409_CONFLICT,
        )

    try:
        obj = ClassTeacherAssignment(
            tenant_id=tenant_id,
            academic_year_id=payload.academic_year_id,
            class_id=payload.class_id,
            section_id=payload.section_id,
            teacher_id=payload.teacher_id,
        )
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return _to_response(obj)
    except IntegrityError:
        await db.rollback()
        raise ServiceError(
            "Class teacher already assigned for this class and section.",
            status.HTTP_409_CONFLICT,
        )


async def list_class_teacher_assignments(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID] = None,
    teacher_id: Optional[UUID] = None,
    class_id: Optional[UUID] = None,
    section_id: Optional[UUID] = None,
    teacher_only_see_own: bool = False,
    current_user_id: Optional[UUID] = None,
) -> List[ClassTeacherAssignmentResponse]:
    stmt = select(ClassTeacherAssignment).where(ClassTeacherAssignment.tenant_id == tenant_id)
    if academic_year_id is not None:
        stmt = stmt.where(ClassTeacherAssignment.academic_year_id == academic_year_id)
    if teacher_id is not None:
        stmt = stmt.where(ClassTeacherAssignment.teacher_id == teacher_id)
    if class_id is not None:
        stmt = stmt.where(ClassTeacherAssignment.class_id == class_id)
    if section_id is not None:
        stmt = stmt.where(ClassTeacherAssignment.section_id == section_id)
    if teacher_only_see_own and current_user_id is not None:
        stmt = stmt.where(ClassTeacherAssignment.teacher_id == current_user_id)
    stmt = stmt.order_by(ClassTeacherAssignment.academic_year_id, ClassTeacherAssignment.class_id, ClassTeacherAssignment.section_id)
    result = await db.execute(stmt)
    return [_to_response(a) for a in result.scalars().all()]


async def get_class_teacher_assignment(
    db: AsyncSession,
    tenant_id: UUID,
    assignment_id: UUID,
    teacher_only_see_own: bool = False,
    current_user_id: Optional[UUID] = None,
) -> Optional[ClassTeacherAssignmentResponse]:
    result = await db.execute(
        select(ClassTeacherAssignment).where(
            ClassTeacherAssignment.id == assignment_id,
            ClassTeacherAssignment.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return None
    if teacher_only_see_own and current_user_id is not None and obj.teacher_id != current_user_id:
        return None
    return _to_response(obj)


async def update_class_teacher_assignment(
    db: AsyncSession,
    tenant_id: UUID,
    assignment_id: UUID,
    payload: ClassTeacherAssignmentUpdate,
) -> Optional[ClassTeacherAssignmentResponse]:
    result = await db.execute(
        select(ClassTeacherAssignment).where(
            ClassTeacherAssignment.id == assignment_id,
            ClassTeacherAssignment.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return None

    teacher = await db.get(User, payload.teacher_id)
    if not teacher or teacher.tenant_id != tenant_id:
        raise ServiceError("Selected teacher is not eligible.", status.HTTP_400_BAD_REQUEST)
    if teacher.user_type != "employee":
        raise ServiceError("Selected teacher is not eligible.", status.HTTP_400_BAD_REQUEST)

    obj.teacher_id = payload.teacher_id
    await db.commit()
    await db.refresh(obj)
    return _to_response(obj)


async def delete_class_teacher_assignment(
    db: AsyncSession,
    tenant_id: UUID,
    assignment_id: UUID,
) -> bool:
    result = await db.execute(
        select(ClassTeacherAssignment).where(
            ClassTeacherAssignment.id == assignment_id,
            ClassTeacherAssignment.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return False
    await db.delete(obj)
    await db.commit()
    return True


# ----- Helpers for attendance & leave modules -----


async def get_class_teacher_by_context(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    class_id: UUID,
    section_id: UUID,
) -> Optional[ClassTeacherAssignment]:
    """Get class teacher for (academic_year_id, class_id, section_id)."""
    result = await db.execute(
        select(ClassTeacherAssignment).where(
            ClassTeacherAssignment.tenant_id == tenant_id,
            ClassTeacherAssignment.academic_year_id == academic_year_id,
            ClassTeacherAssignment.class_id == class_id,
            ClassTeacherAssignment.section_id == section_id,
        )
    )
    return result.scalar_one_or_none()


async def is_user_class_teacher(
    db: AsyncSession,
    user_id: UUID,
    academic_year_id: UUID,
    class_id: UUID,
    section_id: UUID,
    tenant_id: UUID,
) -> bool:
    """True if user is the class teacher for this class-section in this academic year."""
    result = await db.execute(
        select(ClassTeacherAssignment.id).where(
            ClassTeacherAssignment.tenant_id == tenant_id,
            ClassTeacherAssignment.academic_year_id == academic_year_id,
            ClassTeacherAssignment.class_id == class_id,
            ClassTeacherAssignment.section_id == section_id,
            ClassTeacherAssignment.teacher_id == user_id,
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None
