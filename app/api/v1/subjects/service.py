from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.core.models import SchoolSubject
from app.api.v1.departments import service as department_service

from .schemas import SubjectCreate, SubjectDropdownItem, SubjectResponse, SubjectUpdate


def _to_response(s: SchoolSubject) -> SubjectResponse:
    return SubjectResponse(
        id=s.id,
        tenant_id=s.tenant_id,
        department_id=s.department_id,
        name=s.name,
        code=s.code,
        display_order=s.display_order,
        is_active=s.is_active,
        created_at=s.created_at,
    )


async def create_subject(
    db: AsyncSession,
    tenant_id: UUID,
    payload: SubjectCreate,
) -> SubjectResponse:
    dept = await department_service.get_department_by_id_for_tenant(db, tenant_id, payload.department_id, active_only=True)
    if not dept:
        raise ServiceError("Invalid department", status.HTTP_400_BAD_REQUEST)
    code = payload.code.strip().upper()
    name = payload.name.strip()
    try:
        obj = SchoolSubject(
            tenant_id=tenant_id,
            department_id=payload.department_id,
            name=name,
            code=code,
            display_order=payload.display_order,
            is_active=True,
        )
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return _to_response(obj)
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Subject code already exists for this tenant", status.HTTP_409_CONFLICT)


async def list_subjects(
    db: AsyncSession,
    tenant_id: UUID,
    active_only: bool = True,
) -> List[SubjectResponse]:
    stmt = select(SchoolSubject).where(SchoolSubject.tenant_id == tenant_id)
    if active_only:
        stmt = stmt.where(SchoolSubject.is_active.is_(True))
    stmt = stmt.order_by(SchoolSubject.display_order.nullslast(), SchoolSubject.name)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [_to_response(s) for s in rows]


async def get_subject(
    db: AsyncSession,
    tenant_id: UUID,
    subject_id: UUID,
) -> Optional[SubjectResponse]:
    result = await db.execute(
        select(SchoolSubject).where(
            SchoolSubject.id == subject_id,
            SchoolSubject.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    return _to_response(obj) if obj else None


async def get_subject_by_id_for_tenant(
    db: AsyncSession,
    tenant_id: UUID,
    subject_id: UUID,
    active_only: bool = True,
) -> Optional[SchoolSubject]:
    stmt = select(SchoolSubject).where(
        SchoolSubject.id == subject_id,
        SchoolSubject.tenant_id == tenant_id,
    )
    if active_only:
        stmt = stmt.where(SchoolSubject.is_active.is_(True))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_subject(
    db: AsyncSession,
    tenant_id: UUID,
    subject_id: UUID,
    payload: SubjectUpdate,
) -> Optional[SubjectResponse]:
    result = await db.execute(
        select(SchoolSubject).where(
            SchoolSubject.id == subject_id,
            SchoolSubject.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return None
    if payload.department_id is not None:
        dept = await department_service.get_department_by_id_for_tenant(db, tenant_id, payload.department_id, active_only=True)
        if not dept:
            raise ServiceError("Invalid department", status.HTTP_400_BAD_REQUEST)
        obj.department_id = payload.department_id
    if payload.name is not None:
        obj.name = payload.name.strip()
    if payload.code is not None:
        obj.code = payload.code.strip().upper()
    if payload.display_order is not None:
        obj.display_order = payload.display_order
    if payload.is_active is not None:
        obj.is_active = payload.is_active
    try:
        await db.commit()
        await db.refresh(obj)
        return _to_response(obj)
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Subject code already exists for this tenant", status.HTTP_409_CONFLICT)


async def get_subject_dropdown(
    db: AsyncSession,
    tenant_id: UUID,
) -> List[SubjectDropdownItem]:
    subjects = await list_subjects(db, tenant_id, active_only=True)
    return [SubjectDropdownItem(label=s.name, value=s.id) for s in subjects]
