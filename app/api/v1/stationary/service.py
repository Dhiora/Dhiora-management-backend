"""Stationary service: school management items + resell marketplace."""

import asyncio
import logging
import mimetypes
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import razorpay
from fastapi import status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ServiceError
from app.core.models.stationary_resell import StationaryItem, StationaryResellItem, StationaryResellPayment
from app.core.payments.razorpay_client import get_razorpay_client

from .schemas import ResellItemUpdate, StationaryItemUpdate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# S3 helpers (specific to resell images)
# ---------------------------------------------------------------------------


def _upload_resell_image_sync(content: bytes, key: str, content_type: str) -> str:
    import boto3

    client = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    client.put_object(
        Bucket=settings.s3_bucket_name,
        Key=key,
        Body=content,
        ContentType=content_type,
    )
    if settings.s3_base_url:
        return f"{settings.s3_base_url.rstrip('/')}/{key}"
    return f"https://{settings.s3_bucket_name}.s3.{settings.aws_region}.amazonaws.com/{key}"


async def _upload_resell_image(content: bytes, filename: str, tenant_id: str, item_id: str) -> str:
    if not settings.s3_bucket_name or not settings.aws_access_key_id:
        raise ServiceError("S3 not configured", status.HTTP_500_INTERNAL_SERVER_ERROR)
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ".jpg"
    key = f"stationary-resell/{tenant_id}/{item_id}/{uuid.uuid4().hex}{ext}"
    content_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
    return await asyncio.to_thread(_upload_resell_image_sync, content, key, content_type)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_txn_id() -> str:
    return f"txn_{uuid.uuid4().hex[:16]}"


def _validate_seller_type(seller_type: str) -> None:
    if seller_type not in ("STUDENT", "PARENT"):
        raise ServiceError("seller_type must be STUDENT or PARENT", status.HTTP_400_BAD_REQUEST)


def _validate_condition(condition: str) -> None:
    if condition not in ("NEW", "LIKE_NEW", "GOOD", "FAIR"):
        raise ServiceError(
            "condition must be one of: NEW, LIKE_NEW, GOOD, FAIR",
            status.HTTP_400_BAD_REQUEST,
        )


def _validate_status(item_status: str) -> None:
    valid = {"PENDING_APPROVAL", "APPROVED", "REJECTED", "SOLD", "INACTIVE"}
    if item_status not in valid:
        raise ServiceError(
            f"status must be one of: {', '.join(sorted(valid))}",
            status.HTTP_400_BAD_REQUEST,
        )


# ---------------------------------------------------------------------------
# Payment: create order
# ---------------------------------------------------------------------------


async def create_resell_payment_order(
    db: AsyncSession,
    tenant_id: UUID,
    seller_type: str,
    seller_id: str,
    amount: int,
    currency: str,
) -> dict:
    """Create a Razorpay listing-fee order and persist a PENDING payment record."""
    _validate_seller_type(seller_type)

    client = get_razorpay_client()
    amount_paise = amount * 100
    order = client.order.create(
        {
            "amount": amount_paise,
            "currency": currency,
            "payment_capture": 1,
            "notes": {
                "tenant_id": str(tenant_id),
                "seller_type": seller_type,
                "seller_id": seller_id,
                "type": "STATIONARY_RESELL_LISTING_FEE",
            },
        }
    )

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    payment = StationaryResellPayment(
        tenant_id=tenant_id,
        order_id=order["id"],
        seller_type=seller_type,
        seller_id=seller_id,
        amount=amount,
        currency=currency,
        status="PENDING",
        expires_at=expires_at,
    )
    db.add(payment)
    await db.commit()

    return {
        "order_id": order["id"],
        "amount": amount,
        "currency": currency,
        "gateway_key": settings.razorpay_key_id,
        "expires_at": expires_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Payment: verify
# ---------------------------------------------------------------------------


async def verify_resell_payment(
    db: AsyncSession,
    tenant_id: UUID,
    order_id: str,
    payment_id: str,
    signature: str,
    seller_id: str,
) -> dict:
    """Verify Razorpay signature, mark payment PAID, return txn_id."""
    result = await db.execute(
        select(StationaryResellPayment).where(
            StationaryResellPayment.order_id == order_id,
            StationaryResellPayment.tenant_id == tenant_id,
        )
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise ServiceError("Payment order not found", status.HTTP_404_NOT_FOUND)

    if payment.status == "PAID":
        return {"payment_status": "PAID", "payment_txn_id": payment.txn_id}

    if payment.status == "FAILED":
        raise ServiceError(
            "Payment already marked as failed",
            status.HTTP_400_BAD_REQUEST,
        )

    client = get_razorpay_client()
    try:
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            }
        )
    except razorpay.errors.SignatureVerificationError:
        payment.status = "FAILED"
        await db.commit()
        raise ServiceError(
            "Payment verification failed",
            status.HTTP_400_BAD_REQUEST,
        )

    txn_id = _generate_txn_id()
    payment.payment_id = payment_id
    payment.signature = signature
    payment.status = "PAID"
    payment.txn_id = txn_id
    await db.commit()

    return {"payment_status": "PAID", "payment_txn_id": txn_id}


# ---------------------------------------------------------------------------
# Resell items
# ---------------------------------------------------------------------------


async def create_resell_item(
    db: AsyncSession,
    tenant_id: UUID,
    title: str,
    description: Optional[str],
    category: str,
    condition: str,
    price: float,
    seller_type: str,
    seller_id: str,
    payment_txn_id: str,
    image_files: list,  # list of (filename, bytes)
) -> StationaryResellItem:
    """Create a resell listing. Validates payment, uploads images, persists item."""
    _validate_seller_type(seller_type)
    _validate_condition(condition)

    if len(image_files) > 5:
        raise ServiceError("Maximum 5 images allowed", status.HTTP_400_BAD_REQUEST)

    # Validate payment
    pay_result = await db.execute(
        select(StationaryResellPayment).where(
            StationaryResellPayment.txn_id == payment_txn_id,
            StationaryResellPayment.tenant_id == tenant_id,
        )
    )
    payment = pay_result.scalar_one_or_none()
    if not payment:
        raise ServiceError(
            "Invalid payment_txn_id",
            status.HTTP_400_BAD_REQUEST,
        )
    if payment.status != "PAID":
        raise ServiceError(
            "Listing fee payment has not been completed",
            status.HTTP_400_BAD_REQUEST,
        )

    # Ensure txn_id not already used for another listing
    used_result = await db.execute(
        select(StationaryResellItem).where(
            StationaryResellItem.payment_txn_id == payment_txn_id,
            StationaryResellItem.is_active == True,  # noqa: E712
        )
    )
    if used_result.scalar_one_or_none():
        raise ServiceError(
            "This payment has already been used for a listing",
            status.HTTP_409_CONFLICT,
        )

    # Pre-assign item id so S3 path is deterministic
    item_id = uuid.uuid4()

    # Upload images
    image_urls: list[str] = []
    for filename, content in image_files:
        url = await _upload_resell_image(content, filename, str(tenant_id), str(item_id))
        image_urls.append(url)

    item = StationaryResellItem(
        id=item_id,
        tenant_id=tenant_id,
        title=title,
        description=description,
        category=category,
        condition=condition,
        price=price,
        seller_type=seller_type,
        seller_id=seller_id,
        payment_txn_id=payment_txn_id,
        images=image_urls,
        status="PENDING_APPROVAL",
        is_active=True,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def list_resell_items(
    db: AsyncSession,
    tenant_id: UUID,
    item_status: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    search: Optional[str] = None,
) -> tuple[list[StationaryResellItem], int]:
    """Return paginated resell items for a tenant."""
    base = (
        select(StationaryResellItem)
        .where(
            StationaryResellItem.tenant_id == tenant_id,
            StationaryResellItem.is_active == True,  # noqa: E712
        )
        .order_by(StationaryResellItem.created_at.desc())
    )

    if item_status:
        _validate_status(item_status)
        base = base.where(StationaryResellItem.status == item_status)

    if search:
        term = f"%{search}%"
        base = base.where(
            or_(
                StationaryResellItem.title.ilike(term),
                StationaryResellItem.description.ilike(term),
                StationaryResellItem.category.ilike(term),
            )
        )

    count_stmt = select(func.count()).select_from(base.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    offset = (page - 1) * limit
    paginated = base.offset(offset).limit(limit)
    result = await db.execute(paginated)
    items = result.scalars().all()
    return list(items), total


async def get_resell_item(
    db: AsyncSession,
    tenant_id: UUID,
    item_id: UUID,
) -> StationaryResellItem:
    result = await db.execute(
        select(StationaryResellItem).where(
            StationaryResellItem.id == item_id,
            StationaryResellItem.tenant_id == tenant_id,
            StationaryResellItem.is_active == True,  # noqa: E712
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise ServiceError("Resell item not found", status.HTTP_404_NOT_FOUND)
    return item


async def update_resell_item(
    db: AsyncSession,
    tenant_id: UUID,
    item_id: UUID,
    seller_id: str,
    payload: ResellItemUpdate,
    is_admin: bool = False,
) -> StationaryResellItem:
    """Update a listing. Only owner or admin can update."""
    item = await get_resell_item(db, tenant_id, item_id)

    if not is_admin and item.seller_id != seller_id:
        raise ServiceError("Not authorized to update this listing", status.HTTP_403_FORBIDDEN)

    if payload.title is not None:
        item.title = payload.title
    if payload.description is not None:
        item.description = payload.description
    if payload.category is not None:
        item.category = payload.category
    if payload.condition is not None:
        _validate_condition(payload.condition)
        item.condition = payload.condition
    if payload.price is not None:
        item.price = payload.price
    if payload.status is not None:
        _validate_status(payload.status)
        item.status = payload.status

    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    return item


async def delete_resell_item(
    db: AsyncSession,
    tenant_id: UUID,
    item_id: UUID,
    seller_id: str,
    is_admin: bool = False,
) -> None:
    """Soft-delete a listing. Only owner or admin can delete."""
    item = await get_resell_item(db, tenant_id, item_id)

    if not is_admin and item.seller_id != seller_id:
        raise ServiceError("Not authorized to delete this listing", status.HTTP_403_FORBIDDEN)

    item.is_active = False
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()


# ---------------------------------------------------------------------------
# School management items
# ---------------------------------------------------------------------------


async def create_stationary_item(
    db: AsyncSession,
    tenant_id: UUID,
    payload,  # StationaryItemCreate
    image_files: list,  # list of (filename, bytes)
) -> StationaryItem:
    """Create a school-managed stationary item with optional S3 images."""
    if len(image_files) > 5:
        raise ServiceError("Maximum 5 images allowed", status.HTTP_400_BAD_REQUEST)

    item_id = uuid.uuid4()
    image_urls: list[str] = []
    for filename, content in image_files:
        url = await _upload_resell_image(content, filename, str(tenant_id), str(item_id))
        image_urls.append(url)

    item = StationaryItem(
        id=item_id,
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
        brand=payload.brand,
        category=payload.category,
        unit=payload.unit,
        price=payload.price,
        original_price=payload.original_price,
        stock_quantity=payload.stock_quantity,
        class_level=payload.class_level,
        academic_year=payload.academic_year,
        condition=payload.condition,
        images=image_urls,
        is_active=True,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def list_stationary_items(
    db: AsyncSession,
    tenant_id: UUID,
    category: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    search: Optional[str] = None,
    active_only: bool = True,
) -> tuple[list[StationaryItem], int]:
    """Return paginated school-managed stationary items."""
    base = (
        select(StationaryItem)
        .where(StationaryItem.tenant_id == tenant_id)
        .order_by(StationaryItem.category, StationaryItem.name)
    )

    if active_only:
        base = base.where(StationaryItem.is_active == True)  # noqa: E712

    if category:
        base = base.where(StationaryItem.category == category)

    if search:
        term = f"%{search}%"
        base = base.where(
            or_(
                StationaryItem.name.ilike(term),
                StationaryItem.description.ilike(term),
                StationaryItem.category.ilike(term),
            )
        )

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    result = await db.execute(base.offset((page - 1) * limit).limit(limit))
    return list(result.scalars().all()), total


async def get_stationary_item(
    db: AsyncSession,
    tenant_id: UUID,
    item_id: UUID,
) -> StationaryItem:
    result = await db.execute(
        select(StationaryItem).where(
            StationaryItem.id == item_id,
            StationaryItem.tenant_id == tenant_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise ServiceError("Stationary item not found", status.HTTP_404_NOT_FOUND)
    return item


async def update_stationary_item(
    db: AsyncSession,
    tenant_id: UUID,
    item_id: UUID,
    payload: StationaryItemUpdate,
) -> StationaryItem:
    item = await get_stationary_item(db, tenant_id, item_id)

    if payload.name is not None:
        item.name = payload.name
    if payload.description is not None:
        item.description = payload.description
    if payload.brand is not None:
        item.brand = payload.brand
    if payload.category is not None:
        item.category = payload.category
    if payload.unit is not None:
        item.unit = payload.unit
    if payload.price is not None:
        item.price = payload.price
    if payload.original_price is not None:
        item.original_price = payload.original_price
    if payload.stock_quantity is not None:
        item.stock_quantity = payload.stock_quantity
    if payload.class_level is not None:
        item.class_level = payload.class_level
    if payload.academic_year is not None:
        item.academic_year = payload.academic_year
    if payload.condition is not None:
        item.condition = payload.condition
    if payload.is_active is not None:
        item.is_active = payload.is_active

    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    return item


async def upload_stationary_item_images(
    db: AsyncSession,
    tenant_id: UUID,
    item_id: UUID,
    image_files: list,  # list of (filename, bytes)
) -> StationaryItem:
    """Upload images for an existing stationary item (replaces existing images)."""
    item = await get_stationary_item(db, tenant_id, item_id)

    if len(image_files) > 5:
        raise ServiceError("Maximum 5 images allowed", status.HTTP_400_BAD_REQUEST)

    image_urls: list[str] = []
    for filename, content in image_files:
        url = await _upload_resell_image(content, filename, str(tenant_id), str(item_id))
        image_urls.append(url)

    item.images = image_urls
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    return item


async def delete_stationary_item(
    db: AsyncSession,
    tenant_id: UUID,
    item_id: UUID,
) -> None:
    """Soft-delete a school-managed stationary item."""
    item = await get_stationary_item(db, tenant_id, item_id)
    item.is_active = False
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
