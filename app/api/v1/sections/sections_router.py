from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import SectionBulkCreate, SectionCreate, SectionResponse, SectionUpdate
from . import service

router = APIRouter(prefix="/api/v1/sections", tags=["sections"])


@router.post(
    "",
    response_model=SectionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("sections", "create"))],
)
async def create_section(
    payload: SectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SectionResponse:
    try:
        return await service.create_section(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/bulk",
    response_model=List[SectionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("sections", "create"))],
)
async def create_sections_bulk(
    payload: SectionBulkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[SectionResponse]:
    """Create multiple sections for a class. Body: class_id + sections list [{ name, order }]. All-or-nothing on duplicate name."""
    try:
        return await service.create_sections_bulk(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "",
    response_model=List[SectionResponse],
    dependencies=[Depends(check_permission("sections", "read"))],
)
async def list_sections(
    active_only: bool = Query(True, description="Return only is_active=true by default"),
    class_id: Optional[UUID] = Query(None, description="Filter by class (sections under this class)"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[SectionResponse]:
    return await service.list_sections(db, current_user.tenant_id, active_only=active_only, class_id=class_id)


@router.get(
    "/{section_id}",
    response_model=SectionResponse,
    dependencies=[Depends(check_permission("sections", "read"))],
)
async def get_section(
    section_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SectionResponse:
    obj = await service.get_section(db, current_user.tenant_id, section_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    return obj


@router.put(
    "/{section_id}",
    response_model=SectionResponse,
    dependencies=[Depends(check_permission("sections", "update"))],
)
async def update_section(
    section_id: UUID,
    payload: SectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SectionResponse:
    try:
        obj = await service.update_section(db, current_user.tenant_id, section_id, payload)
        if not obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
        return obj
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/{section_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("sections", "delete"))],
)
async def delete_section(
    section_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    try:
        deleted = await service.delete_section(db, current_user.tenant_id, section_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
