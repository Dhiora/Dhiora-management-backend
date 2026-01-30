from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import (
    DepartmentCreate,
    DepartmentDropdownItem,
    DepartmentResponse,
    DepartmentUpdate,
)
from . import service

router = APIRouter(prefix="/api/v1/departments", tags=["departments"])


@router.post(
    "",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("departments", "create"))],
)
async def create_department(
    payload: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DepartmentResponse:
    try:
        return await service.create_department(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "",
    response_model=List[DepartmentResponse],
    dependencies=[Depends(check_permission("departments", "read"))],
)
async def list_departments(
    active_only: bool = Query(True, description="Return only is_active=true by default"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[DepartmentResponse]:
    return await service.list_departments(db, current_user.tenant_id, active_only=active_only)


@router.get(
    "/dropdown",
    response_model=List[DepartmentDropdownItem],
    dependencies=[Depends(check_permission("departments", "read"))],
)
async def department_dropdown(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[DepartmentDropdownItem]:
    return await service.get_department_dropdown(db, current_user.tenant_id)


@router.get(
    "/{department_id}",
    response_model=DepartmentResponse,
    dependencies=[Depends(check_permission("departments", "read"))],
)
async def get_department(
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DepartmentResponse:
    dept = await service.get_department(db, current_user.tenant_id, department_id)
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    return dept


@router.put(
    "/{department_id}",
    response_model=DepartmentResponse,
    dependencies=[Depends(check_permission("departments", "update"))],
)
async def update_department(
    department_id: UUID,
    payload: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DepartmentResponse:
    try:
        dept = await service.update_department(db, current_user.tenant_id, department_id, payload)
        if not dept:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        return dept
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/{department_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("departments", "delete"))],
)
async def delete_department(
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    try:
        deleted = await service.delete_department(db, current_user.tenant_id, department_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
