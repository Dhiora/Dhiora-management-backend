from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums (kept as string literals to avoid coupling with Python Enum machinery)
# ---------------------------------------------------------------------------

SELLER_TYPES = {"STUDENT", "PARENT"}
CONDITIONS = {"NEW", "LIKE_NEW", "GOOD", "FAIR"}
STATUSES = {"PENDING_APPROVAL", "APPROVED", "REJECTED", "SOLD", "INACTIVE"}


# ---------------------------------------------------------------------------
# Payment schemas
# ---------------------------------------------------------------------------


class CreateOrderRequest(BaseModel):
    seller_type: str = Field(..., description="STUDENT or PARENT")
    seller_id: str = Field(..., min_length=1, max_length=100)
    amount: int = Field(..., gt=0, description="Listing fee in INR (rupees)")
    currency: str = Field("INR", max_length=10)


class CreateOrderResponse(BaseModel):
    success: bool = True
    data: dict


class VerifyPaymentRequest(BaseModel):
    order_id: str = Field(..., description="Razorpay order_id")
    payment_id: str = Field(..., description="Razorpay payment_id")
    signature: str = Field(..., description="Razorpay HMAC signature")
    seller_id: str = Field(..., min_length=1, max_length=100)


class VerifyPaymentResponse(BaseModel):
    success: bool = True
    data: dict


# ---------------------------------------------------------------------------
# Resell item schemas
# ---------------------------------------------------------------------------


class ResellItemResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    title: str
    description: Optional[str] = None
    category: str
    condition: str
    price: Decimal
    seller_type: str
    seller_id: str
    payment_txn_id: str
    images: List[str]
    status: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ResellItemUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=100)
    condition: Optional[str] = None
    price: Optional[Decimal] = Field(None, gt=0)
    status: Optional[str] = None


class ResellItemListResponse(BaseModel):
    success: bool = True
    data: List[ResellItemResponse]
    total: int
    page: int
    limit: int


class ResellItemDetailResponse(BaseModel):
    success: bool = True
    data: ResellItemResponse


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error_code: Optional[str] = None


# ---------------------------------------------------------------------------
# School management item schemas
# ---------------------------------------------------------------------------


class StationaryItemCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    brand: Optional[str] = Field(None, max_length=150)
    category: str = Field(..., max_length=100)
    unit: str = Field("per piece", max_length=50)
    price: Decimal = Field(..., gt=0)
    original_price: Optional[Decimal] = Field(None, gt=0)
    stock_quantity: int = Field(0, ge=0)
    class_level: Optional[str] = Field(None, max_length=50)
    academic_year: Optional[str] = Field(None, max_length=20)
    condition: Optional[str] = Field(None, max_length=20)


class StationaryItemResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    description: Optional[str] = None
    brand: Optional[str] = None
    category: str
    unit: str
    price: Decimal
    original_price: Optional[Decimal] = None
    stock_quantity: int
    class_level: Optional[str] = None
    academic_year: Optional[str] = None
    condition: Optional[str] = None
    images: List[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StationaryItemUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    brand: Optional[str] = Field(None, max_length=150)
    category: Optional[str] = Field(None, max_length=100)
    unit: Optional[str] = Field(None, max_length=50)
    price: Optional[Decimal] = Field(None, gt=0)
    original_price: Optional[Decimal] = Field(None, gt=0)
    stock_quantity: Optional[int] = Field(None, ge=0)
    class_level: Optional[str] = Field(None, max_length=50)
    academic_year: Optional[str] = Field(None, max_length=20)
    condition: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None


class StationaryItemListResponse(BaseModel):
    success: bool = True
    data: List[StationaryItemResponse]
    total: int
    page: int
    limit: int


class StationaryItemDetailResponse(BaseModel):
    success: bool = True
    data: StationaryItemResponse
