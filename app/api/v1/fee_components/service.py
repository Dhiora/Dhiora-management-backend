"""Fee component service layer."""

from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.core.models import FeeComponent
from app.core.enums import FeeComponentCategory

from .schemas import FeeComponentCreate, FeeComponentResponse, FeeComponentUpdate


def _to_uuid(val):
    if val is None:
        return None
    return val if isinstance(val, UUID) else UUID(str(val))


def _to_response(fc: FeeComponent) -> FeeComponentResponse:
    return FeeComponentResponse(
        id=_to_uuid(fc.id),
        tenant_id=_to_uuid(fc.tenant_id),
        name=fc.name,
        code=fc.code,
        description=fc.description,
        component_category=fc.component_category,
        allow_discount=fc.allow_discount,
        is_mandatory_default=fc.is_mandatory_default,
        is_active=fc.is_active,
        created_at=fc.created_at,
        updated_at=fc.updated_at,
    )


async def create_fee_component(
    db: AsyncSession,
    tenant_id: UUID,
    payload: FeeComponentCreate,
) -> FeeComponentResponse:
    code = payload.code.strip().upper()[:50]
    name = payload.name.strip()
    category = payload.component_category.value if isinstance(payload.component_category, FeeComponentCategory) else str(payload.component_category)
    try:
        fc = FeeComponent(
            tenant_id=tenant_id,
            name=name,
            code=code,
            description=(payload.description or "").strip() or None,
            component_category=category.strip().upper(),
            allow_discount=payload.allow_discount,
            is_mandatory_default=payload.is_mandatory_default,
            is_active=True,
        )
        db.add(fc)
        await db.commit()
        await db.refresh(fc)
        return _to_response(fc)
    except IntegrityError:
        await db.rollback()
        raise ServiceError(
            "Fee component code already exists for this tenant",
            status.HTTP_409_CONFLICT,
        )


async def list_fee_components(
    db: AsyncSession,
    tenant_id: UUID,
    active_only: bool = True,
) -> List[FeeComponentResponse]:
    stmt = select(FeeComponent).where(FeeComponent.tenant_id == tenant_id)
    if active_only:
        stmt = stmt.where(FeeComponent.is_active.is_(True))
    stmt = stmt.order_by(FeeComponent.name)
    result = await db.execute(stmt)
    return [_to_response(fc) for fc in result.scalars().all()]


async def get_fee_component(
    db: AsyncSession,
    tenant_id: UUID,
    fee_component_id: UUID,
) -> Optional[FeeComponentResponse]:
    result = await db.execute(
        select(FeeComponent).where(
            FeeComponent.id == fee_component_id,
            FeeComponent.tenant_id == tenant_id,
        )
    )
    fc = result.scalar_one_or_none()
    return _to_response(fc) if fc else None


async def update_fee_component(
    db: AsyncSession,
    tenant_id: UUID,
    fee_component_id: UUID,
    payload: FeeComponentUpdate,
) -> Optional[FeeComponentResponse]:
    result = await db.execute(
        select(FeeComponent).where(
            FeeComponent.id == fee_component_id,
            FeeComponent.tenant_id == tenant_id,
        )
    )
    fc = result.scalar_one_or_none()
    if not fc:
        return None
    if payload.name is not None:
        fc.name = payload.name.strip()
    if payload.description is not None:
        fc.description = payload.description.strip() or None
    if payload.component_category is not None:
        category = payload.component_category.value if isinstance(payload.component_category, FeeComponentCategory) else str(payload.component_category)
        fc.component_category = category.strip().upper()
    if payload.allow_discount is not None:
        fc.allow_discount = payload.allow_discount
    if payload.is_mandatory_default is not None:
        fc.is_mandatory_default = payload.is_mandatory_default
    if payload.is_active is not None:
        fc.is_active = payload.is_active
    try:
        await db.commit()
        await db.refresh(fc)
        return _to_response(fc)
    except IntegrityError:
        await db.rollback()
        raise ServiceError(
            "Fee component update conflict",
            status.HTTP_409_CONFLICT,
        )
