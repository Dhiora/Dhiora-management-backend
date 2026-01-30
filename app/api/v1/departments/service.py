from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import StaffProfile
from app.core.exceptions import ServiceError
from app.core.models import Department

from .schemas import (
    DepartmentCreate,
    DepartmentDropdownItem,
    DepartmentResponse,
    DepartmentUpdate,
)


def _to_uuid(val):
    if val is None:
        return None
    return val if isinstance(val, UUID) else UUID(str(val))


async def create_department(
    db: AsyncSession,
    tenant_id: UUID,
    payload: DepartmentCreate,
) -> DepartmentResponse:
    code = payload.code.strip().upper()[:20]
    name = payload.name.strip()
    description = payload.description.strip() if payload.description else None
    try:
        dept = Department(
            tenant_id=tenant_id,
            code=code,
            name=name,
            description=description,
            is_active=True,
        )
        db.add(dept)
        await db.commit()
        await db.refresh(dept)
        return DepartmentResponse(
            id=_to_uuid(dept.id),
            tenant_id=_to_uuid(dept.tenant_id),
            code=dept.code,
            name=dept.name,
            description=dept.description,
            is_active=dept.is_active,
            created_at=dept.created_at,
            updated_at=dept.updated_at,
        )
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Department code or name already exists for this tenant", status.HTTP_409_CONFLICT)


async def list_departments(
    db: AsyncSession,
    tenant_id: UUID,
    active_only: bool = True,
) -> List[DepartmentResponse]:
    stmt = select(Department).where(Department.tenant_id == tenant_id)
    if active_only:
        stmt = stmt.where(Department.is_active.is_(True))
    stmt = stmt.order_by(Department.name)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        DepartmentResponse(
            id=_to_uuid(d.id),
            tenant_id=_to_uuid(d.tenant_id),
            code=d.code,
            name=d.name,
            description=d.description,
            is_active=d.is_active,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in rows
    ]


async def get_department(
    db: AsyncSession,
    tenant_id: UUID,
    department_id: UUID,
) -> Optional[DepartmentResponse]:
    result = await db.execute(
        select(Department).where(
            Department.id == department_id,
            Department.tenant_id == tenant_id,
        )
    )
    dept = result.scalar_one_or_none()
    if not dept:
        return None
    return DepartmentResponse(
        id=_to_uuid(dept.id),
        tenant_id=_to_uuid(dept.tenant_id),
        code=dept.code,
        name=dept.name,
        description=dept.description,
        is_active=dept.is_active,
        created_at=dept.created_at,
        updated_at=dept.updated_at,
    )


async def update_department(
    db: AsyncSession,
    tenant_id: UUID,
    department_id: UUID,
    payload: DepartmentUpdate,
) -> Optional[DepartmentResponse]:
    result = await db.execute(
        select(Department).where(
            Department.id == department_id,
            Department.tenant_id == tenant_id,
        )
    )
    dept = result.scalar_one_or_none()
    if not dept:
        return None
    if payload.name is not None:
        dept.name = payload.name.strip()
    if payload.description is not None:
        dept.description = payload.description.strip() or None
    if payload.is_active is not None:
        dept.is_active = payload.is_active
    try:
        await db.commit()
        await db.refresh(dept)
        return DepartmentResponse(
            id=_to_uuid(dept.id),
            tenant_id=_to_uuid(dept.tenant_id),
            code=dept.code,
            name=dept.name,
            description=dept.description,
            is_active=dept.is_active,
            created_at=dept.created_at,
            updated_at=dept.updated_at,
        )
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Department name already exists for this tenant", status.HTTP_409_CONFLICT)


async def delete_department(
    db: AsyncSession,
    tenant_id: UUID,
    department_id: UUID,
    block_if_used: bool = True,
) -> bool:
    result = await db.execute(
        select(Department).where(
            Department.id == department_id,
            Department.tenant_id == tenant_id,
        )
    )
    dept = result.scalar_one_or_none()
    if not dept:
        return False
    if block_if_used:
        used = await db.execute(
            select(StaffProfile.id).where(StaffProfile.department_id == department_id).limit(1)
        )
        if used.scalar_one_or_none() is not None:
            raise ServiceError("Cannot delete department: it is used by employees", status.HTTP_400_BAD_REQUEST)
    dept.is_active = False
    await db.commit()
    return True


async def get_department_dropdown(
    db: AsyncSession,
    tenant_id: UUID,
) -> List[DepartmentDropdownItem]:
    result = await db.execute(
        select(Department.id, Department.name)
        .where(Department.tenant_id == tenant_id, Department.is_active.is_(True))
        .order_by(Department.name)
    )
    rows = result.all()
    return [DepartmentDropdownItem(label=name, value=_to_uuid(id_)) for id_, name in rows]


async def get_department_by_id_for_tenant(
    db: AsyncSession,
    tenant_id: UUID,
    department_id: UUID,
    active_only: bool = True,
) -> Optional[Department]:
    """Validate department exists, belongs to tenant, and optionally is active. Used for employee create/update."""
    stmt = select(Department).where(
        Department.id == department_id,
        Department.tenant_id == tenant_id,
    )
    if active_only:
        stmt = stmt.where(Department.is_active.is_(True))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
