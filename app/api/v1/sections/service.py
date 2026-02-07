from typing import Dict, List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.core.models import AcademicYear, Section, StudentAcademicRecord

from app.api.v1.classes import service as class_service

from .schemas import CopySectionsToYearRequest, SectionBulkCreate, SectionCreate, SectionResponse, SectionUpdate


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
        academic_year_id=_to_uuid(getattr(s, "academic_year_id", None)),
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
    academic_year_id: UUID,
    payload: SectionCreate,
) -> SectionResponse:
    if not academic_year_id:
        raise ServiceError("Academic year is required to create a section (use current year from token)", status.HTTP_400_BAD_REQUEST)
    school_class = await class_service.get_class_by_id_for_tenant(db, tenant_id, payload.class_id, active_only=True)
    if not school_class:
        raise ServiceError("Invalid or inactive class for this tenant", status.HTTP_400_BAD_REQUEST)
    # Ensure academic year belongs to tenant
    ay = await db.get(AcademicYear, academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid or inactive academic year for this tenant", status.HTTP_400_BAD_REQUEST)
    name = payload.name.strip()
    capacity = getattr(payload, "capacity", 50) or 50
    try:
        obj = Section(
            tenant_id=tenant_id,
            class_id=payload.class_id,
            academic_year_id=academic_year_id,
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
        raise ServiceError("Section name already exists for this class in this academic year", status.HTTP_409_CONFLICT)


async def create_sections_bulk(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    payload: SectionBulkCreate,
) -> List[SectionResponse]:
    """Create multiple sections for a class in one request. All-or-nothing: rollback on first duplicate name."""
    if not academic_year_id:
        raise ServiceError("Academic year is required to create sections (use current year from token)", status.HTTP_400_BAD_REQUEST)
    school_class = await class_service.get_class_by_id_for_tenant(db, tenant_id, payload.class_id, active_only=True)
    if not school_class:
        raise ServiceError("Invalid or inactive class for this tenant", status.HTTP_400_BAD_REQUEST)
    ay = await db.get(AcademicYear, academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid or inactive academic year for this tenant", status.HTTP_400_BAD_REQUEST)
    try:
        created = []
        for item in payload.sections:
            capacity = getattr(item, "capacity", 50) or 50
            obj = Section(
                tenant_id=tenant_id,
                class_id=payload.class_id,
                academic_year_id=academic_year_id,
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
        raise ServiceError("Section name already exists for this class in this academic year (duplicate in bulk or existing)", status.HTTP_409_CONFLICT)


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
    academic_year_id: Optional[UUID] = None,
    active_only: bool = True,
    class_id: Optional[UUID] = None,
) -> List[SectionResponse]:
    """List sections for tenant. Default academic_year_id = current year from token; pass explicitly to list another year."""
    stmt = select(Section).where(Section.tenant_id == tenant_id)
    if academic_year_id is not None:
        stmt = stmt.where(Section.academic_year_id == academic_year_id)
    if class_id is not None:
        stmt = stmt.where(Section.class_id == class_id)
    if active_only:
        stmt = stmt.where(Section.is_active.is_(True))
    stmt = stmt.order_by(Section.display_order.nullslast(), Section.name)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    section_ids = [s.id for s in rows]
    ay_id = academic_year_id or await _get_current_academic_year_id(db, tenant_id)
    occupied_map: Dict[UUID, int] = {}
    if ay_id and section_ids:
        occupied_map = await _get_occupied_by_section(db, ay_id, section_ids)
    return [_section_to_response(s, occupied=occupied_map.get(s.id, 0)) for s in rows]


async def get_section(
    db: AsyncSession,
    tenant_id: UUID,
    section_id: UUID,
    academic_year_id: Optional[UUID] = None,
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
    ay_id = academic_year_id or getattr(obj, "academic_year_id", None) or await _get_current_academic_year_id(db, tenant_id)
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
    academic_year_id: Optional[UUID] = None,
) -> Optional[Section]:
    stmt = select(Section).where(
        Section.id == section_id,
        Section.tenant_id == tenant_id,
    )
    if academic_year_id is not None:
        stmt = stmt.where(Section.academic_year_id == academic_year_id)
    if active_only:
        stmt = stmt.where(Section.is_active.is_(True))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def copy_sections_to_academic_year(
    db: AsyncSession,
    tenant_id: UUID,
    payload: CopySectionsToYearRequest,
) -> List[SectionResponse]:
    """
    Copy all sections from source academic year to target academic year (e.g. when year ends).
    Creates new section rows with same class_id, name, capacity, display_order; old data remains unchanged.
    """
    ay_source = await db.get(AcademicYear, payload.source_academic_year_id)
    ay_target = await db.get(AcademicYear, payload.target_academic_year_id)
    if not ay_source or ay_source.tenant_id != tenant_id:
        raise ServiceError("Source academic year not found or does not belong to this tenant", status.HTTP_404_NOT_FOUND)
    if not ay_target or ay_target.tenant_id != tenant_id:
        raise ServiceError("Target academic year not found or does not belong to this tenant", status.HTTP_404_NOT_FOUND)
    if payload.source_academic_year_id == payload.target_academic_year_id:
        raise ServiceError("Source and target academic year must be different", status.HTTP_400_BAD_REQUEST)

    stmt = select(Section).where(
        Section.tenant_id == tenant_id,
        Section.academic_year_id == payload.source_academic_year_id,
        Section.is_active.is_(True),
    ).order_by(Section.class_id, Section.display_order.nullslast(), Section.name)
    result = await db.execute(stmt)
    source_sections = result.scalars().all()
    if not source_sections:
        return []

    created = []
    try:
        for s in source_sections:
            new_section = Section(
                tenant_id=tenant_id,
                class_id=s.class_id,
                academic_year_id=payload.target_academic_year_id,
                name=s.name,
                display_order=s.display_order,
                capacity=getattr(s, "capacity", 50) or 50,
                is_active=True,
            )
            db.add(new_section)
            await db.flush()
            created.append(new_section)
        await db.commit()
        for obj in created:
            await db.refresh(obj)
        return [_section_to_response(s, occupied=0) for s in created]
    except IntegrityError:
        await db.rollback()
        raise ServiceError(
            "One or more sections already exist for the target academic year (same class and name). Copy aborted.",
            status.HTTP_409_CONFLICT,
        )
