"""Subscription API: student AI + tenant ERP/AI with Razorpay."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.core.config import settings
from app.core.exceptions import ServiceError
from app.db.session import get_db

from . import service
from .schemas import (
    RazorpayOrderResponse,
    StudentAISubscriptionCreateOrder,
    StudentAISubscriptionVerify,
    TenantSubscriptionCreateOrder,
    TenantSubscriptionVerify,
)

router = APIRouter(prefix="/api/v1/subscriptions", tags=["subscriptions"])


def _require_admin_or_employee(current_user: CurrentUser) -> None:
    if current_user.user_type == "employee" or current_user.role in (
        "SUPER_ADMIN",
        "PLATFORM_ADMIN",
        "ADMIN",
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only admins or employees can perform this action",
    )


@router.post(
    "/ai/student/create-order",
    response_model=RazorpayOrderResponse,
    dependencies=[Depends(get_current_user)],
)
async def create_student_ai_order(
    payload: StudentAISubscriptionCreateOrder,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create Razorpay order for student AI tier (PRO/ULTRA). BASIC is applied immediately with no payment."""
    try:
        data = await service.create_student_ai_order(
            db,
            current_user.id,
            current_user.tenant_id,
            payload,
        )
        return RazorpayOrderResponse(**data)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/ai/student/verify",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_user)],
)
async def verify_student_ai_payment(
    payload: StudentAISubscriptionVerify,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Verify Razorpay payment and activate student AI subscription tier."""
    try:
        await service.verify_student_ai_payment(
            db,
            current_user.id,
            current_user.tenant_id,
            payload,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/tenant/create-order",
    response_model=RazorpayOrderResponse,
    dependencies=[Depends(get_current_user)],
)
async def create_tenant_subscription_order(
    payload: TenantSubscriptionCreateOrder,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create Razorpay order for tenant ERP or AI subscription. Admin/employee only."""
    _require_admin_or_employee(current_user)
    try:
        sub, order = await service.create_tenant_subscription_order(
            db,
            current_user.tenant_id,
            payload,
        )
        return RazorpayOrderResponse(
            order_id=order["id"],
            amount=order["amount"],
            currency=order["currency"],
            key_id=settings.razorpay_key_id,
            notes=order.get("notes", {}),
            subscription_id=sub.id,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/tenant/verify",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_user)],
)
async def verify_tenant_subscription(
    payload: TenantSubscriptionVerify,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Verify Razorpay payment and activate tenant subscription. For ERP, enables plan modules. Admin/employee only."""
    _require_admin_or_employee(current_user)
    try:
        await service.verify_tenant_subscription(
            db,
            current_user.tenant_id,
            payload,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
