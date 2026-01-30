from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import Role
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser, RoleCreate, RoleResponse, RoleUpdate
from app.core.models import Tenant
from app.db.session import get_db

router = APIRouter(prefix="/api/v1/auth/roles", tags=["roles"])

PLATFORM_TENANT_NAME = "Platform"


def _to_uuid(value):  # asyncpg UUID or uuid.UUID -> uuid.UUID
    if value is None:
        return None
    return value if isinstance(value, UUID) else UUID(str(value))


async def _get_platform_tenant_id(db: AsyncSession) -> Optional[UUID]:
    result = await db.execute(select(Tenant.id).where(Tenant.organization_name == PLATFORM_TENANT_NAME))
    raw = result.scalars().first()
    return _to_uuid(raw)


@router.post(
    "",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("roles", "create"))],
)
async def create_role(
    payload: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> RoleResponse:
    role = Role(
        tenant_id=current_user.tenant_id,
        name=payload.name,
        permissions=payload.permissions,
    )
    db.add(role)
    try:
        await db.commit()
        await db.refresh(role)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A role with this name already exists for this tenant.",
        )
    except Exception as e:  # pragma: no cover - generic DB failure
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create role",
        ) from e
    platform_tenant_id = await _get_platform_tenant_id(db)
    is_default = platform_tenant_id is not None and _to_uuid(role.tenant_id) == platform_tenant_id
    return RoleResponse(id=_to_uuid(role.id), name=role.name, permissions=role.permissions, is_default=is_default)


@router.get(
    "",
    response_model=List[RoleResponse],
    dependencies=[Depends(check_permission("roles", "read"))],
)
async def list_roles(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[RoleResponse]:
    platform_tenant_id = await _get_platform_tenant_id(db)
    # Tenant's own roles
    stmt = (
        select(Role)
        .where(Role.tenant_id == current_user.tenant_id)
        .order_by(Role.name)
    )
    result = await db.execute(stmt)
    tenant_roles = result.scalars().all()
    out = [RoleResponse(id=_to_uuid(r.id), name=r.name, permissions=r.permissions, is_default=False) for r in tenant_roles]
    # Append default roles (platform tenant) for all tenants so they can see and use them
    if platform_tenant_id and current_user.tenant_id != platform_tenant_id:
        default_stmt = (
            select(Role)
            .where(Role.tenant_id == platform_tenant_id)
            .order_by(Role.name)
        )
        default_result = await db.execute(default_stmt)
        default_roles = default_result.scalars().all()
        out.extend(
            RoleResponse(id=_to_uuid(r.id), name=r.name, permissions=r.permissions, is_default=True) for r in default_roles
        )
    return out


@router.put(
    "/{role_id}",
    response_model=RoleResponse,
    dependencies=[Depends(check_permission("roles", "update"))],
)
async def update_role(
    role_id: UUID,
    payload: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> RoleResponse:
    role_stmt = select(Role).where(Role.id == role_id)
    role_result = await db.execute(role_stmt)
    role = role_result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    platform_tenant_id = await _get_platform_tenant_id(db)
    is_default_role = platform_tenant_id and _to_uuid(role.tenant_id) == platform_tenant_id
    if is_default_role and current_user.role != "PLATFORM_ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only platform admin can update default roles")
    if not is_default_role and _to_uuid(role.tenant_id) != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    if payload.name is not None:
        role.name = payload.name
    if payload.permissions is not None:
        role.permissions = payload.permissions

    try:
        await db.commit()
        await db.refresh(role)
    except Exception as e:  # pragma: no cover
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update role",
        ) from e

    return RoleResponse(id=_to_uuid(role.id), name=role.name, permissions=role.permissions, is_default=is_default_role)


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("roles", "delete"))],
)
async def delete_role(
    role_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    stmt = select(Role).where(Role.id == role_id)
    result = await db.execute(stmt)
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    platform_tenant_id = await _get_platform_tenant_id(db)
    is_default_role = platform_tenant_id and _to_uuid(role.tenant_id) == platform_tenant_id
    if is_default_role and current_user.role != "PLATFORM_ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only platform admin can delete default roles")
    if not is_default_role and _to_uuid(role.tenant_id) != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    try:
        await db.delete(role)
        await db.commit()
    except Exception as e:  # pragma: no cover
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete role",
        ) from e

