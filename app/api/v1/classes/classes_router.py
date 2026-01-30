from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import ClassBulkItem, ClassCreate, ClassResponse, ClassUpdate
from . import service

router = APIRouter(prefix="/api/v1/classes", tags=["classes"])


@router.post(
    "",
    response_model=ClassResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("classes", "create"))],
)
async def create_class(
    payload: ClassCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ClassResponse:
    try:
        return await service.create_class(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/bulk",
    response_model=List[ClassResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("classes", "create"))],
)
async def create_classes_bulk(
    payload: List[ClassBulkItem],
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[ClassResponse]:
    """Create multiple classes in one request. Payload: [{ \"name\": \"Nursery\", \"order\": 1 }, ...]"""
    try:
        return await service.create_classes_bulk(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "",
    response_model=List[ClassResponse],
    dependencies=[Depends(check_permission("classes", "read"))],
)
async def list_classes(
    active_only: bool = Query(True, description="Return only is_active=true by default"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[ClassResponse]:
    return await service.list_classes(db, current_user.tenant_id, active_only=active_only)


@router.get(
    "/{class_id}",
    response_model=ClassResponse,
    dependencies=[Depends(check_permission("classes", "read"))],
)
async def get_class(
    class_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ClassResponse:
    obj = await service.get_class(db, current_user.tenant_id, class_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    return obj


@router.put(
    "/{class_id}",
    response_model=ClassResponse,
    dependencies=[Depends(check_permission("classes", "update"))],
)
async def update_class(
    class_id: UUID,
    payload: ClassUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ClassResponse:
    try:
        obj = await service.update_class(db, current_user.tenant_id, class_id, payload)
        if not obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
        return obj
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/{class_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("classes", "delete"))],
)
async def delete_class(
    class_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    try:
        deleted = await service.delete_class(db, current_user.tenant_id, class_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
