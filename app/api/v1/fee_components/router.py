"""Fee components router."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import FeeComponentCreate, FeeComponentResponse, FeeComponentUpdate
from . import service

router = APIRouter(prefix="/api/v1/fee-components", tags=["fee-components"])


@router.post(
    "",
    response_model=FeeComponentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("fees", "create"))],
)
async def create_fee_component(
    payload: FeeComponentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> FeeComponentResponse:
    try:
        return await service.create_fee_component(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "",
    response_model=List[FeeComponentResponse],
    dependencies=[Depends(check_permission("fees", "read"))],
)
async def list_fee_components(
    active_only: bool = Query(True, description="Return only active components by default"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[FeeComponentResponse]:
    return await service.list_fee_components(
        db, current_user.tenant_id, active_only=active_only
    )


@router.patch(
    "/{fee_component_id}",
    response_model=FeeComponentResponse,
    dependencies=[Depends(check_permission("fees", "update"))],
)
async def update_fee_component(
    fee_component_id: UUID,
    payload: FeeComponentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> FeeComponentResponse:
    try:
        fc = await service.update_fee_component(
            db, current_user.tenant_id, fee_component_id, payload
        )
        if not fc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fee component not found",
            )
        return fc
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
