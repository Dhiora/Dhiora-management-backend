from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.core.models import AcademicYear, SchoolClass, SchoolSubject, Section, Timetable

from app.api.v1.class_subjects import service as class_subjects_service

from .schemas import TimetableSlotCreate, TimetableSlotResponse, TimetableSlotUpdate


def _to_response(t: Timetable) -> TimetableSlotResponse:
    return TimetableSlotResponse(
        id=t.id,
        tenant_id=t.tenant_id,
        academic_year_id=t.academic_year_id,
        class_id=t.class_id,
        section_id=t.section_id,
        subject_id=t.subject_id,
        teacher_id=t.teacher_id,
        day_of_week=t.day_of_week,
        start_time=t.start_time,
        end_time=t.end_time,
        created_at=t.created_at,
    )


async def create_timetable_slot(
    db: AsyncSession,
    tenant_id: UUID,
    payload: TimetableSlotCreate,
) -> TimetableSlotResponse:
    ay = await db.get(AcademicYear, payload.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid academic year", status.HTTP_400_BAD_REQUEST)
    if ay.status != "ACTIVE":
        raise ServiceError("Cannot add timetable slot for a CLOSED academic year", status.HTTP_400_BAD_REQUEST)
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
            "Subject must be assigned to this class for this academic year (class_subjects) first",
            status.HTTP_400_BAD_REQUEST,
        )
    if payload.end_time <= payload.start_time:
        raise ServiceError("end_time must be after start_time", status.HTTP_400_BAD_REQUEST)
    try:
        obj = Timetable(
            tenant_id=tenant_id,
            academic_year_id=payload.academic_year_id,
            class_id=payload.class_id,
            section_id=payload.section_id,
            subject_id=payload.subject_id,
            teacher_id=payload.teacher_id,
            day_of_week=payload.day_of_week,
            start_time=payload.start_time,
            end_time=payload.end_time,
        )
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return _to_response(obj)
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Timetable slot creation failed", status.HTTP_409_CONFLICT)


async def list_timetable_slots(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    class_id: Optional[UUID] = None,
    section_id: Optional[UUID] = None,
) -> List[TimetableSlotResponse]:
    stmt = select(Timetable).where(
        Timetable.tenant_id == tenant_id,
        Timetable.academic_year_id == academic_year_id,
    )
    if class_id is not None:
        stmt = stmt.where(Timetable.class_id == class_id)
    if section_id is not None:
        stmt = stmt.where(Timetable.section_id == section_id)
    stmt = stmt.order_by(Timetable.day_of_week, Timetable.start_time)
    result = await db.execute(stmt)
    return [_to_response(t) for t in result.scalars().all()]


async def get_timetable_slot(
    db: AsyncSession,
    tenant_id: UUID,
    slot_id: UUID,
) -> Optional[TimetableSlotResponse]:
    result = await db.execute(
        select(Timetable).where(
            Timetable.id == slot_id,
            Timetable.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    return _to_response(obj) if obj else None


async def update_timetable_slot(
    db: AsyncSession,
    tenant_id: UUID,
    slot_id: UUID,
    payload: TimetableSlotUpdate,
) -> Optional[TimetableSlotResponse]:
    result = await db.execute(
        select(Timetable).where(
            Timetable.id == slot_id,
            Timetable.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return None
    if payload.teacher_id is not None:
        obj.teacher_id = payload.teacher_id
    if payload.start_time is not None:
        obj.start_time = payload.start_time
    if payload.end_time is not None:
        obj.end_time = payload.end_time
    if payload.start_time is not None or payload.end_time is not None:
        if obj.end_time <= obj.start_time:
            raise ServiceError("end_time must be after start_time", status.HTTP_400_BAD_REQUEST)
    await db.commit()
    await db.refresh(obj)
    return _to_response(obj)


async def delete_timetable_slot(
    db: AsyncSession,
    tenant_id: UUID,
    slot_id: UUID,
) -> bool:
    result = await db.execute(
        select(Timetable).where(
            Timetable.id == slot_id,
            Timetable.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return False
    await db.delete(obj)
    await db.commit()
    return True


async def has_timetable_slot_for_class_section_subject(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    class_id: UUID,
    section_id: UUID,
    subject_id: UUID,
) -> bool:
    result = await db.execute(
        select(Timetable.id).where(
            Timetable.tenant_id == tenant_id,
            Timetable.academic_year_id == academic_year_id,
            Timetable.class_id == class_id,
            Timetable.section_id == section_id,
            Timetable.subject_id == subject_id,
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None
