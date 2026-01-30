from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import StudentProfile
from app.core.exceptions import ServiceError
from app.core.models import Section

from app.api.v1.classes import service as class_service

from .schemas import SectionBulkCreate, SectionCreate, SectionResponse, SectionUpdate


def _to_uuid(val):
    if val is None:
        return None
    return val if isinstance(val, UUID) else UUID(str(val))


def _section_to_response(s: Section) -> SectionResponse:
    return SectionResponse(
        id=_to_uuid(s.id),
        tenant_id=_to_uuid(s.tenant_id),
        class_id=_to_uuid(s.class_id),
        name=s.name,
        display_order=s.display_order,
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
    try:
        obj = Section(
            tenant_id=tenant_id,
            class_id=payload.class_id,
            name=name,
            display_order=payload.display_order,
            is_active=True,
        )
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return _section_to_response(obj)
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
            obj = Section(
                tenant_id=tenant_id,
                class_id=payload.class_id,
                name=item.name.strip(),
                display_order=item.order,
                is_active=True,
            )
            db.add(obj)
            await db.flush()
            created.append(obj)
        await db.commit()
        for obj in created:
            await db.refresh(obj)
        return [_section_to_response(s) for s in created]
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Section name already exists for this class (duplicate in bulk or existing)", status.HTTP_409_CONFLICT)


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
    return [_section_to_response(s) for s in rows]


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
    return _section_to_response(obj) if obj else None


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
    if payload.is_active is not None:
        obj.is_active = payload.is_active
    try:
        await db.commit()
        await db.refresh(obj)
        return _section_to_response(obj)
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
            select(StudentProfile.id).where(StudentProfile.section_id == section_id).limit(1)
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
