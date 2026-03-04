"""Subscription service: student AI tiers + tenant ERP/AI with Razorpay."""

from datetime import datetime, timezone
from uuid import UUID

import razorpay
from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.config import settings
from app.core.exceptions import ServiceError
from app.core.models import Module, SubscriptionPlan, Tenant, TenantModule, TenantSubscription
from app.core.payments.razorpay_client import get_razorpay_client

from .schemas import (
    StudentAISubscriptionCreateOrder,
    StudentAISubscriptionVerify,
    TenantSubscriptionCreateOrder,
    TenantSubscriptionVerify,
)

# Student AI tier amount in paise (₹0, ₹499, ₹999)
AI_TIER_AMOUNT_PAISE = {
    "BASIC": 0,
    "PRO": 49900,
    "ULTRA": 99900,
}


async def create_student_ai_order(
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    payload: StudentAISubscriptionCreateOrder,
) -> dict:
    """Create Razorpay order for student AI tier, or set BASIC immediately if free."""
    user = await db.get(User, user_id)
    if not user or user.tenant_id != tenant_id:
        raise ServiceError("User not found", status.HTTP_404_NOT_FOUND)

    tier = payload.tier
    amount = AI_TIER_AMOUNT_PAISE.get(tier)
    if amount is None:
        raise ServiceError("Invalid tier", status.HTTP_400_BAD_REQUEST)

    if amount == 0:
        user.subscription_plan = tier
        await db.commit()
        await db.refresh(user)
        return {
            "order_id": None,
            "amount": 0,
            "currency": "INR",
            "key_id": settings.razorpay_key_id,
            "notes": {"tier": tier, "free": True},
        }

    client = get_razorpay_client()
    order = client.order.create(
        {
            "amount": amount,
            "currency": "INR",
            "payment_capture": 1,
            "notes": {
                "tenant_id": str(tenant_id),
                "user_id": str(user_id),
                "tier": tier,
                "type": "STUDENT_AI",
            },
        }
    )
    return {
        "order_id": order["id"],
        "amount": order["amount"],
        "currency": order["currency"],
        "key_id": settings.razorpay_key_id,
        "notes": order.get("notes", {}),
    }


async def verify_student_ai_payment(
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    payload: StudentAISubscriptionVerify,
) -> None:
    """Verify Razorpay signature and set user.subscription_plan."""
    user = await db.get(User, user_id)
    if not user or user.tenant_id != tenant_id:
        raise ServiceError("User not found", status.HTTP_404_NOT_FOUND)

    client = get_razorpay_client()
    try:
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": payload.razorpay_order_id,
                "razorpay_payment_id": payload.razorpay_payment_id,
                "razorpay_signature": payload.razorpay_signature,
            }
        )
    except razorpay.errors.SignatureVerificationError:
        raise ServiceError("Invalid payment signature", status.HTTP_400_BAD_REQUEST)

    user.subscription_plan = payload.tier
    await db.commit()
    await db.refresh(user)


def _parse_plan_amount_paise(plan: SubscriptionPlan) -> int:
    """Parse plan price to paise. Prefer discount_price, else price. Expects numeric string."""
    raw = plan.discount_price or plan.price or "0"
    s = "".join(c for c in str(raw) if c.isdigit() or c == ".")
    try:
        rupees = float(s) if s else 0
    except ValueError:
        return 0
    return int(rupees * 100)


async def create_tenant_subscription_order(
    db: AsyncSession,
    tenant_id: UUID,
    payload: TenantSubscriptionCreateOrder,
) -> tuple[TenantSubscription, dict]:
    """Create TenantSubscription (PENDING) and Razorpay order. Returns (subscription, order_dict)."""
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise ServiceError("Tenant not found", status.HTTP_404_NOT_FOUND)

    plan = await db.get(SubscriptionPlan, payload.plan_id)
    if not plan:
        raise ServiceError("Subscription plan not found", status.HTTP_404_NOT_FOUND)

    amount_paise = _parse_plan_amount_paise(plan)
    if amount_paise <= 0:
        raise ServiceError("Plan price must be greater than zero", status.HTTP_400_BAD_REQUEST)

    client = get_razorpay_client()
    order = client.order.create(
        {
            "amount": amount_paise,
            "currency": "INR",
            "payment_capture": 1,
            "notes": {
                "tenant_id": str(tenant_id),
                "plan_id": str(plan.id),
                "category": payload.category,
                "type": "TENANT_SUBSCRIPTION",
            },
        }
    )

    sub = TenantSubscription(
        tenant_id=tenant_id,
        subscription_plan_id=plan.id,
        category=payload.category,
        status="PENDING",
        razorpay_order_id=order["id"],
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub, order


async def verify_tenant_subscription(
    db: AsyncSession,
    tenant_id: UUID,
    payload: TenantSubscriptionVerify,
) -> TenantSubscription:
    """Verify Razorpay signature, set subscription ACTIVE, and for ERP enable plan modules."""
    sub = await db.get(TenantSubscription, payload.subscription_id)
    if not sub or sub.tenant_id != tenant_id:
        raise ServiceError("Subscription not found", status.HTTP_404_NOT_FOUND)

    client = get_razorpay_client()
    try:
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": payload.razorpay_order_id,
                "razorpay_payment_id": payload.razorpay_payment_id,
                "razorpay_signature": payload.razorpay_signature,
            }
        )
    except razorpay.errors.SignatureVerificationError:
        raise ServiceError("Invalid payment signature", status.HTTP_400_BAD_REQUEST)

    sub.razorpay_payment_id = payload.razorpay_payment_id
    sub.razorpay_signature = payload.razorpay_signature
    sub.status = "ACTIVE"
    sub.activated_at = datetime.now(timezone.utc)
    await db.flush()

    if sub.category == "ERP" and sub.subscription_plan_id:
        plan = await db.get(SubscriptionPlan, sub.subscription_plan_id)
        if plan and plan.modules_include:
            module_ids = [UUID(str(x)) for x in plan.modules_include]
            mod_result = await db.execute(
                select(Module.id, Module.module_key).where(Module.id.in_(module_ids))
            )
            id_to_key = {row[0]: row[1] for row in mod_result.all()}
            existing = await db.execute(
                select(TenantModule.module_key).where(TenantModule.tenant_id == tenant_id)
            )
            existing_keys = {row[0] for row in existing.all()}
            for mod_id in module_ids:
                module_key = id_to_key.get(mod_id)
                if module_key and module_key not in existing_keys:
                    tm = TenantModule(
                        tenant_id=tenant_id,
                        module_key=module_key,
                        is_enabled=True,
                    )
                    db.add(tm)
                    existing_keys.add(module_key)

    await db.commit()
    await db.refresh(sub)
    return sub
