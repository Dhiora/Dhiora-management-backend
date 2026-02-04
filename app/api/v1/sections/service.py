from typing import Dict, List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.core.models import AcademicYear, Section, StudentAcademicRecord

from app.api.v1.classes import service as class_service

from .schemas import SectionBulkCreate, SectionCreate, SectionResponse, SectionUpdate


def _to_uuid(val):
    if val is None:
        return None
    return val if isinstance(val, UUID) else UUID(str(val))


def _section_to_response(s: Section, occupied: int = 0) -> SectionResponse:
    capacity = getattr(s, "capacity", 50)
    return SectionResponse(
        id=_to_uuid(s.id),
        tenant_id=_to_uuid(s.tenant_id),
        class_id=_to_uuid(s.class_id),
        name=s.name,
        display_order=s.display_order,
        capacity=capacity,
        occupied=occupied,
        is_active=s.is_active,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


async def create_section(
    db: AsyncSession,
    tenant_id: UUID,
    payload: SectionCreate,
) -> SectionResponse:
    school_class = await class_service.get_class_by_id_for_tenant(db, tenant_id, payload.class_id, active_only=True)
    if not school_class:
        raise ServiceError("Invalid or inactive class for this tenant", status.HTTP_400_BAD_REQUEST)
    name = payload.name.strip()
    capacity = getattr(payload, "capacity", 50) or 50
    try:
        obj = Section(
            tenant_id=tenant_id,
            class_id=payload.class_id,
            name=name,
            display_order=payload.display_order,
            capacity=capacity,
            is_active=True,
        )
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return _section_to_response(obj, occupied=0)
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Section name already exists for this class", status.HTTP_409_CONFLICT)


async def create_sections_bulk(
    db: AsyncSession,
    tenant_id: UUID,
    payload: SectionBulkCreate,
) -> List[SectionResponse]:
    """Create multiple sections for a class in one request. All-or-nothing: rollback on first duplicate name."""
    school_class = await class_service.get_class_by_id_for_tenant(db, tenant_id, payload.class_id, active_only=True)
    if not school_class:
        raise ServiceError("Invalid or inactive class for this tenant", status.HTTP_400_BAD_REQUEST)
    try:
        created = []
        for item in payload.sections:
            capacity = getattr(item, "capacity", 50) or 50
            obj = Section(
                tenant_id=tenant_id,
                class_id=payload.class_id,
                name=item.name.strip(),
                display_order=item.order,
                capacity=capacity,
                is_active=True,
            )
            db.add(obj)
            await db.flush()
            created.append(obj)
        await db.commit()
        for obj in created:
            await db.refresh(obj)
        return [_section_to_response(s, occupied=0) for s in created]
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Section name already exists for this class (duplicate in bulk or existing)", status.HTTP_409_CONFLICT)


async def _get_current_academic_year_id(db: AsyncSession, tenant_id: UUID) -> Optional[UUID]:
    """Current academic year (is_current=true) for tenant, or None."""
    r = await db.execute(
        select(AcademicYear.id).where(
            AcademicYear.tenant_id == tenant_id,
            AcademicYear.is_current.is_(True),
        )
    )
    row = r.scalar_one_or_none()
    return row if row is not None else None


async def _get_occupied_by_section(
    db: AsyncSession,
    academic_year_id: UUID,
    section_ids: List[UUID],
) -> Dict[UUID, int]:
    """Return map section_id -> count of students (ACTIVE records) in that section for the academic year."""
    if not section_ids:
        return {}
    r = await db.execute(
        select(StudentAcademicRecord.section_id, func.count(StudentAcademicRecord.id).label("cnt"))
        .where(
            StudentAcademicRecord.academic_year_id == academic_year_id,
            StudentAcademicRecord.section_id.in_(section_ids),
            StudentAcademicRecord.status == "ACTIVE",
        )
        .group_by(StudentAcademicRecord.section_id)
    )
    return {row.section_id: row.cnt for row in r.all()}


async def list_sections(
    db: AsyncSession,
    tenant_id: UUID,
    active_only: bool = True,
    class_id: Optional[UUID] = None,
) -> List[SectionResponse]:
    stmt = select(Section).where(Section.tenant_id == tenant_id)
    if class_id is not None:
        stmt = stmt.where(Section.class_id == class_id)
    if active_only:
        stmt = stmt.where(Section.is_active.is_(True))
    stmt = stmt.order_by(Section.display_order.nullslast(), Section.name)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    section_ids = [s.id for s in rows]
    ay_id = await _get_current_academic_year_id(db, tenant_id)
    occupied_map: Dict[UUID, int] = {}
    if ay_id and section_ids:
        occupied_map = await _get_occupied_by_section(db, ay_id, section_ids)
    return [_section_to_response(s, occupied=occupied_map.get(s.id, 0)) for s in rows]


async def get_section(
    db: AsyncSession,
    tenant_id: UUID,
    section_id: UUID,
) -> Optional[SectionResponse]:
    result = await db.execute(
        select(Section).where(
            Section.id == section_id,
            Section.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return None
    ay_id = await _get_current_academic_year_id(db, tenant_id)
    occupied = 0
    if ay_id:
        occupied_map = await _get_occupied_by_section(db, ay_id, [obj.id])
        occupied = occupied_map.get(obj.id, 0)
    return _section_to_response(obj, occupied=occupied)


async def update_section(
    db: AsyncSession,
    tenant_id: UUID,
    section_id: UUID,
    payload: SectionUpdate,
) -> Optional[SectionResponse]:
    result = await db.execute(
        select(Section).where(
            Section.id == section_id,
            Section.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return None
    if payload.name is not None:
        obj.name = payload.name.strip()
    if payload.display_order is not None:
        obj.display_order = payload.display_order
    if getattr(payload, "capacity", None) is not None:
        obj.capacity = payload.capacity
    if payload.is_active is not None:
        obj.is_active = payload.is_active
    try:
        await db.commit()
        await db.refresh(obj)
        ay_id = await _get_current_academic_year_id(db, tenant_id)
        occupied = 0
        if ay_id:
            occupied_map = await _get_occupied_by_section(db, ay_id, [obj.id])
            occupied = occupied_map.get(obj.id, 0)
        return _section_to_response(obj, occupied=occupied)
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Section name already exists for this class", status.HTTP_409_CONFLICT)


async def delete_section(
    db: AsyncSession,
    tenant_id: UUID,
    section_id: UUID,
    block_if_used: bool = True,
) -> bool:
    result = await db.execute(
        select(Section).where(
            Section.id == section_id,
            Section.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return False
    if block_if_used:
        used = await db.execute(
            select(StudentAcademicRecord.id).where(StudentAcademicRecord.section_id == section_id).limit(1)
        )
        if used.scalar_one_or_none() is not None:
            raise ServiceError("Cannot delete section: it is used by students", status.HTTP_400_BAD_REQUEST)
    await db.delete(obj)
    await db.commit()
    return True


async def get_section_by_id_for_tenant(
    db: AsyncSession,
    tenant_id: UUID,
    section_id: UUID,
    active_only: bool = True,
) -> Optional[Section]:
    stmt = select(Section).where(
        Section.id == section_id,
        Section.tenant_id == tenant_id,
    )
    if active_only:
        stmt = stmt.where(Section.is_active.is_(True))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
