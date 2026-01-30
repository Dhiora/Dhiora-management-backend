from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from app.api.v1.query import service as query_service
from app.api.v1.query.schemas import ResourceQueryRequest

from .schemas import EmployeeCreate, EmployeePaginatedResponse, EmployeeResponse, EmployeeUpdate
from . import service

router = APIRouter(prefix="/api/v1/employees", tags=["employees"])


@router.post(
    "",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("employees", "create"))],
)
async def create_employee(
    payload: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> EmployeeResponse:
    try:
        return await service.create_employee(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "",
    response_model=List[EmployeeResponse],
    dependencies=[Depends(check_permission("employees", "read"))],
)
async def list_employees(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[EmployeeResponse]:
    return await service.list_employees(db, current_user.tenant_id)


@router.post(
    "/query",
    response_model=EmployeePaginatedResponse,
    dependencies=[Depends(check_permission("employees", "read"))],
)
async def query_employees(
    body: ResourceQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> EmployeePaginatedResponse:
    """
    Query employees with pagination, filters, sort, and search.
    Same capabilities as global query for resource_type=employees; dedicated endpoint for employees.
    """
    try:
        result = await query_service.run_global_query(
            db,
            current_user.tenant_id,
            resource_type="employees",
            page=body.pagination.page if body.pagination else 1,
            page_size=body.pagination.page_size if body.pagination else 20,
            sort=body.sort,
            filters=body.filters,
            search=body.search,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return EmployeePaginatedResponse(
        items=result.items,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
        search_fields=result.search_fields,
    )


@router.get(
    "/{user_id}",
    response_model=EmployeeResponse,
    dependencies=[Depends(check_permission("employees", "read"))],
)
async def get_employee(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> EmployeeResponse:
    employee = await service.get_employee(db, current_user.tenant_id, user_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return employee


@router.put(
    "/{user_id}",
    response_model=EmployeeResponse,
    dependencies=[Depends(check_permission("employees", "update"))],
)
async def update_employee(
    user_id: UUID,
    payload: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> EmployeeResponse:
    try:
        employee = await service.update_employee(db, current_user.tenant_id, user_id, payload)
        if not employee:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
        return employee
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("employees", "delete"))],
)
async def delete_employee(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    deleted = await service.delete_employee(db, current_user.tenant_id, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
