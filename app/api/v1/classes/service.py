from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import StudentProfile
from app.core.exceptions import ServiceError
from app.core.models import SchoolClass

from .schemas import ClassBulkItem, ClassCreate, ClassResponse, ClassUpdate


def _to_uuid(val):
    if val is None:
        return None
    return val if isinstance(val, UUID) else UUID(str(val))


def _class_to_response(c: SchoolClass) -> ClassResponse:
    return ClassResponse(
        id=_to_uuid(c.id),
        tenant_id=_to_uuid(c.tenant_id),
        name=c.name,
        display_order=c.display_order,
        is_active=c.is_active,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


async def create_class(
    db: AsyncSession,
    tenant_id: UUID,
    payload: ClassCreate,
) -> ClassResponse:
    name = payload.name.strip()
    try:
        obj = SchoolClass(
            tenant_id=tenant_id,
            name=name,
            display_order=payload.display_order,
            is_active=True,
        )
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return _class_to_response(obj)
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Class name already exists for this tenant", status.HTTP_409_CONFLICT)


async def create_classes_bulk(
    db: AsyncSession,
    tenant_id: UUID,
    payload: List[ClassBulkItem],
) -> List[ClassResponse]:
    """Create multiple classes in one request. All-or-nothing: rollback on first duplicate name."""
    if not payload:
        return []
    try:
        created = []
        for item in payload:
            obj = SchoolClass(
                tenant_id=tenant_id,
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
        return [_class_to_response(c) for c in created]
    except IntegrityError:
        await db.rollback()
        raise ServiceError("One or more class names already exist for this tenant", status.HTTP_409_CONFLICT)


async def list_classes(
    db: AsyncSession,
    tenant_id: UUID,
    active_only: bool = True,
) -> List[ClassResponse]:
    stmt = select(SchoolClass).where(SchoolClass.tenant_id == tenant_id)
    if active_only:
        stmt = stmt.where(SchoolClass.is_active.is_(True))
    stmt = stmt.order_by(SchoolClass.display_order.nullslast(), SchoolClass.name)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [_class_to_response(c) for c in rows]


async def get_class(
    db: AsyncSession,
    tenant_id: UUID,
    class_id: UUID,
) -> Optional[ClassResponse]:
    result = await db.execute(
        select(SchoolClass).where(
            SchoolClass.id == class_id,
            SchoolClass.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    return _class_to_response(obj) if obj else None


async def update_class(
    db: AsyncSession,
    tenant_id: UUID,
    class_id: UUID,
    payload: ClassUpdate,
) -> Optional[ClassResponse]:
    result = await db.execute(
        select(SchoolClass).where(
            SchoolClass.id == class_id,
            SchoolClass.tenant_id == tenant_id,
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
        return _class_to_response(obj)
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Class name already exists for this tenant", status.HTTP_409_CONFLICT)


async def delete_class(
    db: AsyncSession,
    tenant_id: UUID,
    class_id: UUID,
    block_if_used: bool = True,
) -> bool:
    result = await db.execute(
        select(SchoolClass).where(
            SchoolClass.id == class_id,
            SchoolClass.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return False
    if block_if_used:
        used = await db.execute(
            select(StudentProfile.id).where(StudentProfile.class_id == class_id).limit(1)
        )
        if used.scalar_one_or_none() is not None:
            raise ServiceError("Cannot delete class: it is used by students", status.HTTP_400_BAD_REQUEST)
    await db.delete(obj)
    await db.commit()
    return True


async def get_class_by_id_for_tenant(
    db: AsyncSession,
    tenant_id: UUID,
    class_id: UUID,
    active_only: bool = True,
) -> Optional[SchoolClass]:
    stmt = select(SchoolClass).where(
        SchoolClass.id == class_id,
        SchoolClass.tenant_id == tenant_id,
    )
    if active_only:
        stmt = stmt.where(SchoolClass.is_active.is_(True))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
