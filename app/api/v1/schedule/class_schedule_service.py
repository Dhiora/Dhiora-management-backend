"""Class schedule service: derive weekly schedule from timetable with optional filters."""

from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import ServiceError
from app.core.models import SchoolClass, Section, SchoolSubject, TimeSlot, Timetable

from .schemas import ClassScheduleItemResponse, ClassScheduleResponse, ClassScheduleSlot

DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


async def get_class_section_schedule(
    db: AsyncSession,
    tenant_id: UUID,
    class_id: UUID,
    section_id: UUID,
    academic_year_id: UUID,
    teacher_name: Optional[str] = None,
    class_name: Optional[str] = None,
    section_name: Optional[str] = None,
) -> ClassScheduleResponse:
    """
    Return weekly class schedule from timetable for the given class/section and academic year.
    Optional filters (ilike): teacher_name (User.full_name), class_name (SchoolClass.name), section_name (Section.name).
    """
    stmt = (
        select(Timetable, TimeSlot, SchoolClass, Section, SchoolSubject, User)
        .join(TimeSlot, Timetable.slot_id == TimeSlot.id)
        .join(SchoolClass, Timetable.class_id == SchoolClass.id)
        .join(Section, Timetable.section_id == Section.id)
        .join(SchoolSubject, Timetable.subject_id == SchoolSubject.id)
        .join(User, Timetable.teacher_id == User.id)
        .where(
            Timetable.tenant_id == tenant_id,
            Timetable.academic_year_id == academic_year_id,
            Timetable.class_id == class_id,
            Timetable.section_id == section_id,
        )
    )
    if teacher_name and teacher_name.strip():
        stmt = stmt.where(User.full_name.ilike(f"%{teacher_name.strip()}%"))
    if class_name and class_name.strip():
        stmt = stmt.where(SchoolClass.name.ilike(f"%{class_name.strip()}%"))
    if section_name and section_name.strip():
        stmt = stmt.where(Section.name.ilike(f"%{section_name.strip()}%"))

    stmt = stmt.order_by(Timetable.day_of_week, TimeSlot.start_time)
    result = await db.execute(stmt)
    rows = result.all()

    day_slots: Dict[str, List[ClassScheduleSlot]] = {d: [] for d in DAY_NAMES}
    for t, slot, cl, sec, subj, teacher in rows:
        day_key = DAY_NAMES[t.day_of_week] if 0 <= t.day_of_week <= 6 else "monday"
        day_slots[day_key].append(
            ClassScheduleSlot(
                subject_id=str(t.subject_id),
                teacher_id=str(t.teacher_id),
                start_time=slot.start_time.strftime("%H:%M") if slot.start_time else "",
                end_time=slot.end_time.strftime("%H:%M") if slot.end_time else "",
                subject_name=subj.name if subj else None,
                teacher_name=teacher.full_name if teacher else None,
            )
        )

    return ClassScheduleResponse.from_day_lists(day_slots)


async def get_all_schedules(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    class_id: Optional[UUID] = None,
    section_id: Optional[UUID] = None,
    teacher_name: Optional[str] = None,
    class_name: Optional[str] = None,
    section_name: Optional[str] = None,
) -> List[ClassScheduleItemResponse]:
    """
    Return weekly schedules for all class/section combinations (or filtered by class_id/section_id).
    academic_year_id is required; class_id and section_id are optional filters.
    Optional text filters: teacher_name, class_name, section_name (ilike).
    """
    stmt = (
        select(Timetable, TimeSlot, SchoolClass, Section, SchoolSubject, User)
        .join(TimeSlot, Timetable.slot_id == TimeSlot.id)
        .join(SchoolClass, Timetable.class_id == SchoolClass.id)
        .join(Section, Timetable.section_id == Section.id)
        .join(SchoolSubject, Timetable.subject_id == SchoolSubject.id)
        .join(User, Timetable.teacher_id == User.id)
        .where(
            Timetable.tenant_id == tenant_id,
            Timetable.academic_year_id == academic_year_id,
        )
    )
    if class_id is not None:
        stmt = stmt.where(Timetable.class_id == class_id)
    if section_id is not None:
        stmt = stmt.where(Timetable.section_id == section_id)
    if teacher_name and teacher_name.strip():
        stmt = stmt.where(User.full_name.ilike(f"%{teacher_name.strip()}%"))
    if class_name and class_name.strip():
        stmt = stmt.where(SchoolClass.name.ilike(f"%{class_name.strip()}%"))
    if section_name and section_name.strip():
        stmt = stmt.where(Section.name.ilike(f"%{section_name.strip()}%"))

    stmt = stmt.order_by(Timetable.class_id, Timetable.section_id, Timetable.day_of_week, TimeSlot.start_time)
    result = await db.execute(stmt)
    rows = result.all()

    # Group by (class_id, section_id)
    grouped: Dict[tuple, List] = {}
    for t, slot, cl, sec, subj, teacher in rows:
        key = (t.class_id, t.section_id)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append((t, slot, cl, sec, subj, teacher))

    out: List[ClassScheduleItemResponse] = []
    for (cid, sid), group_rows in grouped.items():
        day_slots: Dict[str, List[ClassScheduleSlot]] = {d: [] for d in DAY_NAMES}
        class_name_val = None
        section_name_val = None
        for t, slot, cl, sec, subj, teacher in group_rows:
            if cl:
                class_name_val = cl.name
            if sec:
                section_name_val = sec.name
            day_key = DAY_NAMES[t.day_of_week] if 0 <= t.day_of_week <= 6 else "monday"
            day_slots[day_key].append(
                ClassScheduleSlot(
                    subject_id=str(t.subject_id),
                    teacher_id=str(t.teacher_id),
                    start_time=slot.start_time.strftime("%H:%M") if slot.start_time else "",
                    end_time=slot.end_time.strftime("%H:%M") if slot.end_time else "",
                    subject_name=subj.name if subj else None,
                    teacher_name=teacher.full_name if teacher else None,
                )
            )
        out.append(
            ClassScheduleItemResponse(
                class_id=cid,
                section_id=sid,
                class_name=class_name_val,
                section_name=section_name_val,
                monday=day_slots["monday"],
                tuesday=day_slots["tuesday"],
                wednesday=day_slots["wednesday"],
                thursday=day_slots["thursday"],
                friday=day_slots["friday"],
                saturday=day_slots["saturday"],
                sunday=day_slots["sunday"],
            )
        )
    return out
