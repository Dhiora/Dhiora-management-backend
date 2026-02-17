from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ServiceError
from app.core.models import AcademicYear, ClassSubject, SchoolClass, SchoolSubject

from .schemas import ClassSubjectCreate, ClassSubjectResponse, ClassSubjectBulkCreate, ClassSubjectUpdate


def _to_response(
    cs: ClassSubject,
    class_name: Optional[str] = None,
    subject_name: Optional[str] = None,
) -> ClassSubjectResponse:
    if class_name is None and hasattr(cs, "school_class") and cs.school_class is not None:
        class_name = getattr(cs.school_class, "name", None)
    if subject_name is None and hasattr(cs, "subject") and cs.subject is not None:
        subject_name = getattr(cs.subject, "name", None)
    return ClassSubjectResponse(
        id=cs.id,
        tenant_id=cs.tenant_id,
        academic_year_id=cs.academic_year_id,
        class_id=cs.class_id,
        subject_id=cs.subject_id,
        created_at=cs.created_at,
        class_name=class_name,
        subject_name=subject_name,
    )


async def create_class_subject(
    db: AsyncSession,
    tenant_id: UUID,
    payload: ClassSubjectCreate,
) -> ClassSubjectResponse:
    ay = await db.get(AcademicYear, payload.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid academic year", status.HTTP_400_BAD_REQUEST)
    if ay.status != "ACTIVE":
        raise ServiceError("Cannot assign subjects to a CLOSED academic year", status.HTTP_400_BAD_REQUEST)
    cl = await db.get(SchoolClass, payload.class_id)
    if not cl or cl.tenant_id != tenant_id:
        raise ServiceError("Invalid class", status.HTTP_400_BAD_REQUEST)
    subj = await db.get(SchoolSubject, payload.subject_id)
    if not subj or subj.tenant_id != tenant_id:
        raise ServiceError("Invalid subject", status.HTTP_400_BAD_REQUEST)
    try:
        obj = ClassSubject(
            tenant_id=tenant_id,
            academic_year_id=payload.academic_year_id,
            class_id=payload.class_id,
            subject_id=payload.subject_id,
        )
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return _to_response(obj)
    except IntegrityError:
        await db.rollback()
        raise ServiceError("This class already has this subject for this academic year", status.HTTP_409_CONFLICT)


async def create_class_subjects_bulk(
    db: AsyncSession,
    tenant_id: UUID,
    payload: ClassSubjectBulkCreate,
) -> List[ClassSubjectResponse]:
    ay = await db.get(AcademicYear, payload.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid academic year", status.HTTP_400_BAD_REQUEST)
    if ay.status != "ACTIVE":
        raise ServiceError("Cannot assign subjects to a CLOSED academic year", status.HTTP_400_BAD_REQUEST)
    cl = await db.get(SchoolClass, payload.class_id)
    if not cl or cl.tenant_id != tenant_id:
        raise ServiceError("Invalid class", status.HTTP_400_BAD_REQUEST)
    created = []
    for subject_id in payload.subject_ids:
        subj = await db.get(SchoolSubject, subject_id)
        if not subj or subj.tenant_id != tenant_id:
            raise ServiceError(f"Invalid subject: {subject_id}", status.HTTP_400_BAD_REQUEST)
        try:
            obj = ClassSubject(
                tenant_id=tenant_id,
                academic_year_id=payload.academic_year_id,
                class_id=payload.class_id,
                subject_id=subject_id,
            )
            db.add(obj)
            await db.flush()
            created.append(obj)
        except IntegrityError:
            await db.rollback()
            raise ServiceError("One or more class-subject assignments already exist", status.HTTP_409_CONFLICT)
    await db.commit()
    for obj in created:
        await db.refresh(obj)
    return [_to_response(c) for c in created]


async def list_class_subjects(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    class_id: Optional[UUID] = None,
) -> List[ClassSubjectResponse]:
    stmt = (
        select(ClassSubject)
        .where(
            ClassSubject.tenant_id == tenant_id,
            ClassSubject.academic_year_id == academic_year_id,
        )
        .options(
            selectinload(ClassSubject.school_class),
            selectinload(ClassSubject.subject),
        )
    )
    if class_id is not None:
        stmt = stmt.where(ClassSubject.class_id == class_id)
    stmt = stmt.order_by(ClassSubject.class_id, ClassSubject.subject_id)
    result = await db.execute(stmt)
    return [_to_response(cs) for cs in result.scalars().all()]


async def check_subject_in_class_for_year(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    class_id: UUID,
    subject_id: UUID,
) -> bool:
    result = await db.execute(
        select(ClassSubject.id).where(
            ClassSubject.tenant_id == tenant_id,
            ClassSubject.academic_year_id == academic_year_id,
            ClassSubject.class_id == class_id,
            ClassSubject.subject_id == subject_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def update_class_subject(
    db: AsyncSession,
    tenant_id: UUID,
    class_subject_id: UUID,
    payload: ClassSubjectUpdate,
) -> Optional[ClassSubjectResponse]:
    if payload.class_id is None and payload.subject_id is None:
        raise ServiceError("Provide at least one of class_id or subject_id to update", status.HTTP_400_BAD_REQUEST)
    result = await db.execute(
        select(ClassSubject).where(
            ClassSubject.id == class_subject_id,
            ClassSubject.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return None
    ay = await db.get(AcademicYear, obj.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid academic year", status.HTTP_400_BAD_REQUEST)
    if ay.status != "ACTIVE":
        raise ServiceError("Cannot update class-subject for a CLOSED academic year", status.HTTP_400_BAD_REQUEST)
    new_class_id = payload.class_id if payload.class_id is not None else obj.class_id
    new_subject_id = payload.subject_id if payload.subject_id is not None else obj.subject_id
    if payload.class_id is not None:
        cl = await db.get(SchoolClass, payload.class_id)
        if not cl or cl.tenant_id != tenant_id:
            raise ServiceError("Invalid class", status.HTTP_400_BAD_REQUEST)
    if payload.subject_id is not None:
        subj = await db.get(SchoolSubject, payload.subject_id)
        if not subj or subj.tenant_id != tenant_id:
            raise ServiceError("Invalid subject", status.HTTP_400_BAD_REQUEST)
    if (new_class_id, new_subject_id) != (obj.class_id, obj.subject_id):
        existing = await db.execute(
            select(ClassSubject.id).where(
                ClassSubject.tenant_id == tenant_id,
                ClassSubject.academic_year_id == obj.academic_year_id,
                ClassSubject.class_id == new_class_id,
                ClassSubject.subject_id == new_subject_id,
                ClassSubject.id != class_subject_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ServiceError(
                "Another class-subject assignment already exists for this academic year, class, and subject",
                status.HTTP_409_CONFLICT,
            )
    obj.class_id = new_class_id
    obj.subject_id = new_subject_id
    try:
        await db.commit()
        await db.refresh(obj)
        return _to_response(obj)
    except IntegrityError:
        await db.rollback()
        raise ServiceError(
            "Another class-subject assignment already exists for this academic year, class, and subject",
            status.HTTP_409_CONFLICT,
        )


async def delete_class_subject(
    db: AsyncSession,
    tenant_id: UUID,
    class_subject_id: UUID,
) -> bool:
    result = await db.execute(
        select(ClassSubject).where(
            ClassSubject.id == class_subject_id,
            ClassSubject.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return False
    await db.delete(obj)
    await db.commit()
    return True
