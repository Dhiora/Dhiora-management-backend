"""Subscription API schemas (student AI + tenant ERP/AI with Razorpay)."""

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class StudentAISubscriptionCreateOrder(BaseModel):
    tier: Literal["BASIC", "PRO", "ULTRA"]


class StudentAISubscriptionVerify(BaseModel):
    tier: Literal["BASIC", "PRO", "ULTRA"]
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class TenantSubscriptionCreateOrder(BaseModel):
    plan_id: UUID
    category: Literal["ERP", "AI"]


class TenantSubscriptionVerify(BaseModel):
    subscription_id: UUID
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class RazorpayOrderResponse(BaseModel):
    order_id: Optional[str] = None
    amount: int
    currency: str
    key_id: Optional[str] = None
    notes: dict = {}
    subscription_id: Optional[UUID] = None  # For tenant flow: send in verify
