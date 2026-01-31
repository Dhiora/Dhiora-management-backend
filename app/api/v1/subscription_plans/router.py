from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import require_platform_admin
from app.core.enums import OrganizationType
from app.core.schemas import (
    SubscriptionPlanCreate,
    SubscriptionPlanResponse,
    SubscriptionPlanUpdate,
)
from app.core.services import (
    ServiceError,
    create_subscription_plan,
    delete_subscription_plan,
    get_subscription_plan,
    list_subscription_plans,
    update_subscription_plan,
)
from app.db.session import get_db

router = APIRouter(prefix="/api/v1/subscription-plans", tags=["subscription-plans"])


@router.get("", response_model=list[SubscriptionPlanResponse])
async def list_plans(
    organization_type: Optional[OrganizationType] = Query(None, description="Filter by org type: School, College, Software Company, etc."),
    db: AsyncSession = Depends(get_db),
) -> list[SubscriptionPlanResponse]:
    """List subscription plans, optionally filtered by organization type. No authentication required."""
    return await list_subscription_plans(db, organization_type.value if organization_type else None)


@router.get("/by-organization-type", response_model=list[SubscriptionPlanResponse])
async def list_plans_by_organization_type(
    organization_type: OrganizationType = Query(..., description="School, College, Software Company, etc."),
    db: AsyncSession = Depends(get_db),
) -> list[SubscriptionPlanResponse]:
    """List subscription plans for an organization type (same pattern as modules). No authentication required."""
    return await list_subscription_plans(db, organization_type.value)


@router.get("/{plan_id}", response_model=SubscriptionPlanResponse)
async def get_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionPlanResponse:
    """Get a single subscription plan by id. No authentication required."""
    try:
        return await get_subscription_plan(db, plan_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "",
    response_model=SubscriptionPlanResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_platform_admin)],
)
async def create_plan(
    payload: SubscriptionPlanCreate,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionPlanResponse:
    """Create a subscription plan. Platform Admin only."""
    try:
        return await create_subscription_plan(db, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put(
    "/{plan_id}",
    response_model=SubscriptionPlanResponse,
    dependencies=[Depends(require_platform_admin)],
)
async def update_plan(
    plan_id: UUID,
    payload: SubscriptionPlanUpdate,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionPlanResponse:
    """Update a subscription plan. Platform Admin only."""
    try:
        return await update_subscription_plan(db, plan_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/{plan_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_platform_admin)],
)
async def delete_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a subscription plan. Platform Admin only."""
    try:
        await delete_subscription_plan(db, plan_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
