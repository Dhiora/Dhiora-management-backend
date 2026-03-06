"""Exam management service: exam types, exams, schedule, invigilator with business rules."""

from datetime import date, time
from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import ServiceError
from app.core.models import (
    Exam,
    ExamSchedule,
    ExamType,
    SchoolClass,
    SchoolSubject,
    Section,
)

from .schemas import (
    ExamCreate,
    ExamResponse,
    ExamScheduleCreate,
    ExamScheduleResponse,
    ExamTypeCreate,
    ExamTypeResponse,
    InvigilatorUpdate,
)


def _parse_time(s: str) -> time:
    """Parse 'HH:MM' or 'HH:MM:SS' to time."""
    s = (s or "").strip()
    parts = s.split(":")
    if len(parts) >= 2:
        h, m = int(parts[0]), int(parts[1])
        if 0 <= h <= 23 and 0 <= m <= 59:
            return time(hour=h, minute=m, second=0)
    raise ServiceError("Invalid time format; use HH:MM", status.HTTP_400_BAD_REQUEST)


# ----- Exam Types -----
async def create_exam_type(
    db: AsyncSession,
    tenant_id: UUID,
    payload: ExamTypeCreate,
) -> ExamTypeResponse:
    et = ExamType(
        tenant_id=tenant_id,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
    )
    db.add(et)
    await db.commit()
    await db.refresh(et)
    return ExamTypeResponse.model_validate(et)


async def list_exam_types(db: AsyncSession, tenant_id: UUID) -> List[ExamTypeResponse]:
    result = await db.execute(
        select(ExamType).where(ExamType.tenant_id == tenant_id).order_by(ExamType.name)
    )
    return [ExamTypeResponse.model_validate(et) for et in result.scalars().all()]


# ----- Exams -----
async def create_exam(
    db: AsyncSession,
    tenant_id: UUID,
    payload: ExamCreate,
) -> ExamResponse:
    et = await db.get(ExamType, payload.exam_type_id)
    if not et or et.tenant_id != tenant_id:
        raise ServiceError("Invalid exam type", status.HTTP_400_BAD_REQUEST)
    cl = await db.get(SchoolClass, payload.class_id)
    if not cl or cl.tenant_id != tenant_id:
        raise ServiceError("Invalid class", status.HTTP_400_BAD_REQUEST)
    sec = await db.get(Section, payload.section_id)
    if not sec or sec.tenant_id != tenant_id or sec.class_id != payload.class_id:
        raise ServiceError("Invalid section for this class", status.HTTP_400_BAD_REQUEST)
    if payload.end_date < payload.start_date:
        raise ServiceError("end_date must be on or after start_date", status.HTTP_400_BAD_REQUEST)
    if payload.status not in ("draft", "scheduled", "completed"):
        raise ServiceError("status must be draft, scheduled, or completed", status.HTTP_400_BAD_REQUEST)

    exam = Exam(
        tenant_id=tenant_id,
        exam_type_id=payload.exam_type_id,
        name=payload.name.strip(),
        class_id=payload.class_id,
        section_id=payload.section_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=payload.status,
    )
    db.add(exam)
    await db.commit()
    await db.refresh(exam)
    return ExamResponse.model_validate(exam)


async def list_exams(
    db: AsyncSession,
    tenant_id: UUID,
    class_id: Optional[UUID] = None,
    section_id: Optional[UUID] = None,
    status_filter: Optional[str] = None,
) -> List[ExamResponse]:
    q = select(Exam).where(Exam.tenant_id == tenant_id)
    if class_id is not None:
        q = q.where(Exam.class_id == class_id)
    if section_id is not None:
        q = q.where(Exam.section_id == section_id)
    if status_filter is not None:
        q = q.where(Exam.status == status_filter)
    q = q.order_by(Exam.start_date.desc(), Exam.created_at.desc())
    result = await db.execute(q)
    return [ExamResponse.model_validate(e) for e in result.scalars().all()]


# ----- Exam Schedule -----
def _overlaps(s1: time, e1: time, s2: time, e2: time) -> bool:
    return s1 < e2 and s2 < e1


async def _check_schedule_conflicts(
    db: AsyncSession,
    tenant_id: UUID,
    exam_date: date,
    start_time: time,
    end_time: time,
    class_id: UUID,
    section_id: UUID,
    room_number: Optional[str],
    invigilator_teacher_id: Optional[UUID],
    exclude_schedule_id: Optional[UUID] = None,
) -> None:
    """Raise ServiceError if any business rule is violated."""
    # 1) Same class/section cannot have two exams at same time
    q_class = select(ExamSchedule).where(
        ExamSchedule.tenant_id == tenant_id,
        ExamSchedule.class_id == class_id,
        ExamSchedule.section_id == section_id,
        ExamSchedule.exam_date == exam_date,
    )
    if exclude_schedule_id:
        q_class = q_class.where(ExamSchedule.id != exclude_schedule_id)
    result = await db.execute(q_class)
    for row in result.scalars().all():
        if _overlaps(row.start_time, row.end_time, start_time, end_time):
            raise ServiceError(
                "A class cannot have two exams at the same time.",
                status.HTTP_400_BAD_REQUEST,
            )

    # 2) Same room cannot have two exams at same time (if room_number provided)
    if room_number and room_number.strip():
        q_room = select(ExamSchedule).where(
            ExamSchedule.tenant_id == tenant_id,
            ExamSchedule.exam_date == exam_date,
            ExamSchedule.room_number == room_number.strip(),
        )
        if exclude_schedule_id:
            q_room = q_room.where(ExamSchedule.id != exclude_schedule_id)
        result = await db.execute(q_room)
        for row in result.scalars().all():
            if _overlaps(row.start_time, row.end_time, start_time, end_time):
                raise ServiceError(
                    "This room already has an exam scheduled at the same time.",
                    status.HTTP_400_BAD_REQUEST,
                )

    # 3) Same invigilator cannot invigilate two exams at same time
    if invigilator_teacher_id:
        q_inv = select(ExamSchedule).where(
            ExamSchedule.tenant_id == tenant_id,
            ExamSchedule.exam_date == exam_date,
            ExamSchedule.invigilator_teacher_id == invigilator_teacher_id,
        )
        if exclude_schedule_id:
            q_inv = q_inv.where(ExamSchedule.id != exclude_schedule_id)
        result = await db.execute(q_inv)
        for row in result.scalars().all():
            if _overlaps(row.start_time, row.end_time, start_time, end_time):
                raise ServiceError(
                    "This teacher is already assigned to invigilate another exam at the same time.",
                    status.HTTP_400_BAD_REQUEST,
                )


async def add_exam_schedule(
    db: AsyncSession,
    tenant_id: UUID,
    exam_id: UUID,
    payload: ExamScheduleCreate,
) -> ExamScheduleResponse:
    exam = await db.get(Exam, exam_id)
    if not exam or exam.tenant_id != tenant_id:
        raise ServiceError("Exam not found", status.HTTP_404_NOT_FOUND)
    subj = await db.get(SchoolSubject, payload.subject_id)
    if not subj or subj.tenant_id != tenant_id:
        raise ServiceError("Invalid subject", status.HTTP_400_BAD_REQUEST)
    if payload.class_id != exam.class_id or payload.section_id != exam.section_id:
        raise ServiceError("class_id and section_id must match the exam", status.HTTP_400_BAD_REQUEST)
    if not (exam.start_date <= payload.exam_date <= exam.end_date):
        raise ServiceError("exam_date must be within exam start_date and end_date", status.HTTP_400_BAD_REQUEST)

    start_t = _parse_time(payload.start_time)
    end_t = _parse_time(payload.end_time)
    if end_t <= start_t:
        raise ServiceError("end_time must be after start_time", status.HTTP_400_BAD_REQUEST)

    await _check_schedule_conflicts(
        db,
        tenant_id,
        payload.exam_date,
        start_t,
        end_t,
        payload.class_id,
        payload.section_id,
        payload.room_number,
        payload.invigilator_teacher_id,
        exclude_schedule_id=None,
    )

    if payload.invigilator_teacher_id:
        teacher = await db.get(User, payload.invigilator_teacher_id)
        if not teacher or teacher.tenant_id != tenant_id:
            raise ServiceError("Invalid invigilator teacher", status.HTTP_400_BAD_REQUEST)

    schedule = ExamSchedule(
        tenant_id=tenant_id,
        exam_id=exam_id,
        subject_id=payload.subject_id,
        class_id=payload.class_id,
        section_id=payload.section_id,
        exam_date=payload.exam_date,
        start_time=start_t,
        end_time=end_t,
        room_number=payload.room_number.strip() if payload.room_number else None,
        invigilator_teacher_id=payload.invigilator_teacher_id,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return await _schedule_to_response(db, schedule)


async def _schedule_to_response(db: AsyncSession, s: ExamSchedule) -> ExamScheduleResponse:
    subj = await db.get(SchoolSubject, s.subject_id)
    inv_name = None
    if s.invigilator_teacher_id:
        u = await db.get(User, s.invigilator_teacher_id)
        inv_name = u.full_name if u else None
    return ExamScheduleResponse(
        id=s.id,
        tenant_id=s.tenant_id,
        exam_id=s.exam_id,
        subject_id=s.subject_id,
        class_id=s.class_id,
        section_id=s.section_id,
        exam_date=s.exam_date,
        start_time=s.start_time.strftime("%H:%M") if s.start_time else "",
        end_time=s.end_time.strftime("%H:%M") if s.end_time else "",
        room_number=s.room_number,
        invigilator_teacher_id=s.invigilator_teacher_id,
        created_at=s.created_at,
        subject_name=subj.name if subj else None,
        invigilator_name=inv_name,
    )


async def get_exam_schedule(
    db: AsyncSession,
    tenant_id: UUID,
    exam_id: UUID,
) -> List[ExamScheduleResponse]:
    exam = await db.get(Exam, exam_id)
    if not exam or exam.tenant_id != tenant_id:
        raise ServiceError("Exam not found", status.HTTP_404_NOT_FOUND)
    result = await db.execute(
        select(ExamSchedule)
        .where(
            ExamSchedule.tenant_id == tenant_id,
            ExamSchedule.exam_id == exam_id,
        )
        .order_by(ExamSchedule.exam_date, ExamSchedule.start_time)
    )
    rows = result.scalars().all()
    return [await _schedule_to_response(db, s) for s in rows]


async def update_invigilator(
    db: AsyncSession,
    tenant_id: UUID,
    schedule_id: UUID,
    payload: InvigilatorUpdate,
) -> ExamScheduleResponse:
    schedule = await db.get(ExamSchedule, schedule_id)
    if not schedule or schedule.tenant_id != tenant_id:
        raise ServiceError("Exam schedule not found", status.HTTP_404_NOT_FOUND)

    new_inv = payload.invigilator_teacher_id
    if new_inv is not None:
        teacher = await db.get(User, new_inv)
        if not teacher or teacher.tenant_id != tenant_id:
            raise ServiceError("Invalid invigilator teacher", status.HTTP_400_BAD_REQUEST)
        await _check_schedule_conflicts(
            db,
            tenant_id,
            schedule.exam_date,
            schedule.start_time,
            schedule.end_time,
            schedule.class_id,
            schedule.section_id,
            schedule.room_number,
            new_inv,
            exclude_schedule_id=schedule_id,
        )

    schedule.invigilator_teacher_id = new_inv
    await db.commit()
    await db.refresh(schedule)
    return await _schedule_to_response(db, schedule)
